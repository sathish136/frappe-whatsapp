# Copyright (c) 2026, THS Solution and contributors
# License: MIT. See LICENSE

"""WhatsApp Meta Cloud API client and whitelisted helpers."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

import frappe
from frappe import _


def _get_settings():
	settings = frappe.get_single("WhatsApp Settings")
	if not settings.enabled:
		frappe.throw(_("WhatsApp integration is disabled. Enable it in WhatsApp Settings."))
	token = settings.get_password("access_token")
	if not token:
		frappe.throw(_("Access Token is not set in WhatsApp Settings."))
	if not settings.phone_number_id:
		frappe.throw(_("Phone Number ID is not set in WhatsApp Settings."))
	return settings, token


def _graph_request(
	url: str,
	*,
	token: str,
	method: str = "GET",
	payload: dict | None = None,
) -> dict:
	data = None
	headers = {"Authorization": f"Bearer {token}"}
	if payload is not None:
		data = json.dumps(payload).encode("utf-8")
		headers["Content-Type"] = "application/json"

	req = urllib.request.Request(url, data=data, method=method, headers=headers)
	try:
		with urllib.request.urlopen(req, timeout=30) as resp:
			body = resp.read().decode("utf-8")
			return json.loads(body) if body else {}
	except urllib.error.HTTPError as e:
		err = e.read().decode("utf-8", errors="replace")
		try:
			parsed = json.loads(err)
		except json.JSONDecodeError:
			parsed = {"error": {"message": err, "code": e.code}}
		parsed["_http_status"] = e.code
		return parsed


def list_templates_request(waba_id: str | None = None, with_components: bool = False) -> dict:
	settings, token = _get_settings()
	wid = waba_id or settings.waba_id
	if not wid:
		frappe.throw(_("Set WABA ID in WhatsApp Settings to list templates."))
	api_version = settings.api_version or "v25.0"
	fields = "name,status,language,category,id"
	if with_components:
		fields += ",components"
	url = (
		f"https://graph.facebook.com/{api_version}/{wid}/message_templates"
		f"?fields={fields}&limit=100"
	)
	return _graph_request(url, token=token)


def send_template_request(
	to: str,
	template: str | None = None,
	language: str | None = None,
	body_params: list[str] | None = None,
) -> tuple[dict, dict]:
	"""Send a template message. Returns (response, request_payload)."""
	settings, token = _get_settings()
	template = template or settings.default_template
	language = language or settings.default_template_lang or "en"
	api_version = settings.api_version or "v25.0"
	phone_number_id = settings.phone_number_id

	payload: dict[str, Any] = {
		"messaging_product": "whatsapp",
		"to": to,
		"type": "template",
		"template": {
			"name": template,
			"language": {"code": language},
		},
	}

	if body_params:
		payload["template"]["components"] = [
			{
				"type": "body",
				"parameters": [{"type": "text", "text": str(p)} for p in body_params],
			}
		]

	url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
	response = _graph_request(url, token=token, method="POST", payload=payload)
	return response, payload


def _create_log(
	*,
	to: str,
	template: str,
	language: str,
	body_params: list[str] | None,
	payload: dict,
	response: dict,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
) -> str:
	has_error = bool(response.get("error")) or bool(response.get("_http_status"))
	message_id = None
	messages = response.get("messages") or []
	if messages:
		message_id = messages[0].get("id")

	error_message = None
	if has_error:
		err = response.get("error") or {}
		if isinstance(err, dict):
			error_message = err.get("message") or json.dumps(err)
		else:
			error_message = str(err)

	doc = frappe.get_doc(
		{
			"doctype": "WhatsApp Message Log",
			"status": "Failed" if has_error else "Sent",
			"to_number": to,
			"template_name": template,
			"language": language,
			"body_params": ", ".join(body_params) if body_params else None,
			"request_payload": json.dumps(payload, indent=2),
			"response_json": json.dumps(response, indent=2),
			"message_id": message_id,
			"error_message": error_message,
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
		}
	)
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return doc.name


@frappe.whitelist()
def list_templates(waba_id: str | None = None) -> dict:
	"""List message templates for the configured WABA."""
	frappe.only_for("System Manager")
	return list_templates_request(waba_id)


def _count_body_params(components: list | None) -> tuple[int, str | None]:
	import re

	body_text = None
	count = 0
	for comp in components or []:
		if str(comp.get("type") or "").upper() != "BODY":
			continue
		body_text = comp.get("text") or ""
		nums = [int(n) for n in re.findall(r"\{\{(\d+)\}\}", body_text)]
		count = max(nums) if nums else 0
		break
	return count, body_text


VALID_TEMPLATE_STATUSES = (
	"DRAFT",
	"PENDING",
	"APPROVED",
	"REJECTED",
	"PAUSED",
	"DISABLED",
	"IN_APPEAL",
	"UNKNOWN",
)


def _normalize_status(status: str | None) -> str:
	s = (status or "UNKNOWN").upper()
	return s if s in VALID_TEMPLATE_STATUSES else "UNKNOWN"


def _build_components_from_doc(doc) -> list[dict]:
	"""Build Meta components array from WhatsApp Message Template fields."""
	import re

	components: list[dict] = []
	header_type = (doc.get("header_type") or "None").strip()

	if header_type == "Text":
		if not doc.header_text:
			frappe.throw(_("Header Text is required when Header Type is Text."))
		components.append(
			{
				"type": "HEADER",
				"format": "TEXT",
				"text": doc.header_text,
			}
		)
	elif header_type in ("Image", "Video", "Document"):
		# Meta requires a media sample handle for template creation.
		# Local attach is used for ERP preview; submit needs Meta upload handle.
		# For now create with format + note — Media templates should use sample via Meta Manager
		# if handle upload is not configured. Prefer Text header for API create until App ID upload is added.
		frappe.throw(
			_(
				"Header Type {0} needs Meta media upload (header_handle). "
				"Use Header Type = Text for API submit, or create Image/Video/Document templates in WhatsApp Manager and Sync."
			).format(header_type)
		)

	body: dict[str, Any] = {"type": "BODY", "text": doc.body_text}
	nums = [int(n) for n in re.findall(r"\{\{(\d+)\}\}", doc.body_text or "")]
	param_count = max(nums) if nums else 0
	if param_count:
		samples = []
		if doc.sample_values:
			samples = [p.strip() for p in str(doc.sample_values).split(",") if p.strip()]
		if len(samples) < param_count:
			frappe.throw(
				_("Sample Values must include {0} comma-separated example values (one for each placeholder).").format(
					param_count
				)
			)
		body["example"] = {"body_text": [samples[:param_count]]}
	components.append(body)

	if doc.footer_text:
		components.append({"type": "FOOTER", "text": doc.footer_text})

	return components


@frappe.whitelist()
def submit_template_for_approval(name: str) -> dict:
	"""Create template on Meta WABA and set status to PENDING (waiting for approval)."""
	frappe.only_for("System Manager")
	doc = frappe.get_doc("WhatsApp Message Template", name)
	if doc.status not in ("DRAFT", "REJECTED"):
		frappe.throw(_("Only DRAFT or REJECTED templates can be submitted. Current status: {0}").format(doc.status))
	if not doc.body_text:
		frappe.throw(_("Body Text is required."))

	settings, token = _get_settings()
	if not settings.waba_id:
		frappe.throw(_("Set WABA ID in WhatsApp Settings."))

	components = _build_components_from_doc(doc)
	payload = {
		"name": doc.template_name,
		"language": doc.language or "en",
		"category": doc.category or "UTILITY",
		"components": components,
	}
	api_version = settings.api_version or "v25.0"
	url = f"https://graph.facebook.com/{api_version}/{settings.waba_id}/message_templates"
	response = _graph_request(url, token=token, method="POST", payload=payload)

	if response.get("error"):
		return response

	doc.flags.ignore_status_lock = True
	doc.status = _normalize_status(response.get("status") or "PENDING")
	doc.meta_template_id = response.get("id")
	doc.components_json = json.dumps(components, indent=2)
	doc.body_param_count = _count_body_params(components)[0]
	doc.last_synced_on = frappe.utils.now_datetime()
	doc.rejection_reason = None
	doc.save(ignore_permissions=True)
	frappe.db.commit()

	return {
		"ok": True,
		"status": doc.status,
		"meta_template_id": doc.meta_template_id,
		"message": _("Submitted to Meta — waiting for approval"),
		"response": response,
	}


@frappe.whitelist()
def refresh_template_status(name: str) -> dict:
	"""Refresh one template's approval status from Meta."""
	frappe.only_for("System Manager")
	doc = frappe.get_doc("WhatsApp Message Template", name)
	data = list_templates_request(with_components=True)
	if data.get("error"):
		frappe.throw(_(data["error"].get("message") or str(data["error"])))

	match = None
	for item in data.get("data") or []:
		if item.get("name") == doc.template_name and (item.get("language") or "en") == (doc.language or "en"):
			match = item
			break

	if not match:
		frappe.throw(_("Template not found on Meta yet. Try Sync All, or wait a few minutes."))

	components = match.get("components") or []
	body_param_count, body_text = _count_body_params(components)
	doc.flags.ignore_status_lock = True
	doc.status = _normalize_status(match.get("status"))
	doc.category = match.get("category") or doc.category
	doc.meta_template_id = match.get("id") or doc.meta_template_id
	doc.body_param_count = body_param_count
	if body_text:
		doc.body_text = body_text
	# Extract header/footer if present
	header_type = "None"
	for comp in components:
		ctype = str(comp.get("type") or "").upper()
		fmt = str(comp.get("format") or "TEXT").upper()
		if ctype == "HEADER":
			if fmt == "TEXT":
				header_type = "Text"
				doc.header_text = comp.get("text")
			elif fmt == "IMAGE":
				header_type = "Image"
			elif fmt == "VIDEO":
				header_type = "Video"
			elif fmt == "DOCUMENT":
				header_type = "Document"
		elif ctype == "FOOTER" and comp.get("text"):
			doc.footer_text = comp.get("text")
	doc.header_type = header_type
	doc.components_json = json.dumps(components, indent=2)
	doc.last_synced_on = frappe.utils.now_datetime()
	# rejected_reason sometimes in quality_score or rejected_reason fields
	doc.rejection_reason = match.get("rejected_reason") or match.get("rejection_info") or doc.rejection_reason
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return {"status": doc.status, "meta_template_id": doc.meta_template_id}


@frappe.whitelist()
def sync_message_templates(waba_id: str | None = None) -> dict:
	"""Fetch templates from Meta and upsert into WhatsApp Message Template DocType."""
	frappe.only_for("System Manager")

	data = list_templates_request(waba_id, with_components=True)
	if data.get("error"):
		frappe.throw(_(data["error"].get("message") or str(data["error"])))

	created = 0
	updated = 0
	now = frappe.utils.now_datetime()
	synced_names = []

	for item in data.get("data") or []:
		template_name = item.get("name")
		language = item.get("language") or "en"
		if not template_name:
			continue

		docname = f"{template_name}-{language}"
		components = item.get("components") or []
		body_param_count, body_text = _count_body_params(components)
		status = _normalize_status(item.get("status"))

		header_text = None
		footer_text = None
		header_type = "None"
		for comp in components:
			ctype = str(comp.get("type") or "").upper()
			fmt = str(comp.get("format") or "TEXT").upper()
			if ctype == "HEADER":
				if fmt == "TEXT":
					header_type = "Text"
					header_text = comp.get("text")
				elif fmt == "IMAGE":
					header_type = "Image"
				elif fmt == "VIDEO":
					header_type = "Video"
				elif fmt == "DOCUMENT":
					header_type = "Document"
			elif ctype == "FOOTER" and comp.get("text"):
				footer_text = comp.get("text")

		values = {
			"template_name": template_name,
			"language": language,
			"status": status,
			"category": item.get("category") or "UTILITY",
			"meta_template_id": item.get("id"),
			"body_param_count": body_param_count,
			"body_text": body_text or "",
			"header_type": header_type,
			"header_text": header_text,
			"footer_text": footer_text,
			"components_json": json.dumps(components, indent=2),
			"last_synced_on": now,
			"rejection_reason": item.get("rejected_reason"),
		}

		if frappe.db.exists("WhatsApp Message Template", docname):
			doc = frappe.get_doc("WhatsApp Message Template", docname)
			doc.flags.ignore_status_lock = True
			# Keep ERP Related DocType link — Meta sync must not clear it
			related = doc.related_doctype
			doc.update(values)
			doc.related_doctype = related
			doc.save(ignore_permissions=True)
			updated += 1
		else:
			doc = frappe.get_doc({"doctype": "WhatsApp Message Template", **values})
			doc.insert(ignore_permissions=True)
			created += 1
			docname = doc.name
		synced_names.append(docname)

	frappe.db.commit()
	return {
		"created": created,
		"updated": updated,
		"synced": created + updated,
		"templates": synced_names,
	}


@frappe.whitelist()
def send_template(
	to: str,
	template: str | None = None,
	language: str | None = None,
	body_params: list | str | None = None,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
) -> dict:
	"""
	Send a WhatsApp Cloud API template message.

	body_params: list of strings for {{1}}, {{2}}, … or JSON string / comma-separated.
	"""
	frappe.only_for("System Manager")

	if isinstance(body_params, str):
		body_params = body_params.strip()
		if not body_params:
			body_params = None
		else:
			try:
				parsed = json.loads(body_params)
				body_params = parsed if isinstance(parsed, list) else [str(parsed)]
			except json.JSONDecodeError:
				body_params = [p.strip() for p in body_params.split(",") if p.strip()]

	settings = frappe.get_single("WhatsApp Settings")
	template = template or settings.default_template
	language = language or settings.default_template_lang or "en"

	# Resolve WhatsApp Message Template Link → Meta template name + language
	if template and frappe.db.exists("WhatsApp Message Template", template):
		row = frappe.db.get_value(
			"WhatsApp Message Template",
			template,
			["template_name", "language"],
			as_dict=True,
		)
		template = row.template_name
		language = language or row.language or "en"

	response, payload = send_template_request(
		to=to,
		template=template,
		language=language,
		body_params=body_params,
	)
	log_name = _create_log(
		to=to,
		template=template,
		language=language,
		body_params=body_params,
		payload=payload,
		response=response,
		reference_doctype=reference_doctype,
		reference_name=reference_name,
	)
	response["_log"] = log_name
	return response
