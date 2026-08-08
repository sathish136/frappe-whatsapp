# Copyright (c) 2026, THS Solution and contributors
# License: MIT. See LICENSE

"""Send WhatsApp templates linked to Quotation, Sales Invoice, Support Ticket."""

from __future__ import annotations

import re

import frappe
from frappe import _
from frappe.utils import flt, formatdate, fmt_money

from ths_whatsapp.api.whatsapp import send_template as _send_template_api


SUPPORTED_DOCTYPES = ("Quotation", "Sales Invoice", "Support Ticket")


def normalize_phone(number: str | None) -> str | None:
	"""Normalize to digits only; convert Sri Lanka 0XXXXXXXXX → 94XXXXXXXXX."""
	if not number:
		return None
	digits = re.sub(r"\D", "", str(number))
	if not digits:
		return None
	if digits.startswith("0") and len(digits) == 10:
		digits = "94" + digits[1:]
	elif len(digits) == 9 and digits.startswith("7"):
		digits = "94" + digits
	return digits


def get_recipient_number(doc) -> str | None:
	"""Resolve mobile number from document / linked contact."""
	doctype = doc.doctype

	if doctype == "Quotation":
		if doc.get("contact_mobile"):
			return normalize_phone(doc.contact_mobile)
		if doc.get("contact_person"):
			mobile = frappe.db.get_value("Contact", doc.contact_person, "mobile_no")
			return normalize_phone(mobile)

	elif doctype == "Sales Invoice":
		if doc.get("contact_mobile"):
			return normalize_phone(doc.contact_mobile)
		if doc.get("contact_person"):
			mobile = frappe.db.get_value("Contact", doc.contact_person, "mobile_no")
			if mobile:
				return normalize_phone(mobile)
		# fallback: customer mobile
		if doc.get("customer"):
			mobile = frappe.db.get_value("Customer", doc.customer, "mobile_no")
			return normalize_phone(mobile)

	elif doctype == "Support Ticket":
		return normalize_phone(doc.get("contact_no"))

	return None


def _money(doc, amount) -> str:
	currency = doc.get("currency") or frappe.db.get_default("currency") or "LKR"
	try:
		return fmt_money(flt(amount), currency=currency)
	except Exception:
		return str(flt(amount))


def build_body_params(doc) -> list[str]:
	"""
	Standard 4 params used by quotation_submit / invoice_due_reminder / support_ticket_update:
	{{1}} name, {{2}} amount|subject, {{3}} doc no, {{4}} date|status
	"""
	doctype = doc.doctype

	if doctype == "Quotation":
		name = doc.get("customer_name") or doc.get("party_name") or "Customer"
		amount = _money(doc, doc.get("grand_total"))
		invoice_no = doc.name
		due = formatdate(doc.get("valid_till")) if doc.get("valid_till") else "-"
		return [str(name), str(amount), str(invoice_no), str(due)]

	if doctype == "Sales Invoice":
		name = doc.get("customer_name") or doc.get("customer") or "Customer"
		amt = doc.get("outstanding_amount")
		if amt is None:
			amt = doc.get("grand_total")
		amount = _money(doc, amt)
		invoice_no = doc.name
		due = formatdate(doc.get("due_date")) if doc.get("due_date") else "-"
		return [str(name), str(amount), str(invoice_no), str(due)]

	if doctype == "Support Ticket":
		name = doc.get("raised_by") or doc.get("company_name") or "Customer"
		detail = doc.get("ticket_subject") or "Support Ticket"
		ticket_no = doc.name
		due_or_status = doc.get("status") or "Open"
		return [str(name), str(detail), str(ticket_no), str(due_or_status)]

	frappe.throw(_("Unsupported DocType: {0}").format(doctype))


def get_template_for_doctype(doctype: str) -> str:
	settings = frappe.get_single("WhatsApp Settings")
	mapping = {
		"Quotation": settings.get("quotation_template"),
		"Sales Invoice": settings.get("sales_invoice_template"),
		"Support Ticket": settings.get("support_ticket_template"),
	}
	linked = mapping.get(doctype) or settings.default_template
	name, _lang = resolve_template_ref(linked)
	return name or "payment_alert"


def resolve_template_ref(value: str | None) -> tuple[str | None, str | None]:
	"""Resolve Settings Link / raw name → (template_name, language)."""
	if not value:
		return None, None
	if frappe.db.exists("WhatsApp Message Template", value):
		row = frappe.db.get_value(
			"WhatsApp Message Template",
			value,
			["template_name", "language"],
			as_dict=True,
		)
		return row.template_name, row.language
	# Legacy raw Meta template name
	return value, None


def _template_header_type(template_ref: str | None) -> str:
	"""Return header_type for a WhatsApp Message Template link or Meta name."""
	if not template_ref:
		return "None"
	if frappe.db.exists("WhatsApp Message Template", template_ref):
		return frappe.db.get_value("WhatsApp Message Template", template_ref, "header_type") or "None"
	# Look up by template_name-language style
	name = frappe.db.get_value(
		"WhatsApp Message Template",
		{"template_name": template_ref},
		"header_type",
	)
	return name or "None"


def _send_document_message(to: str, media_id: str, filename: str, caption: str | None = None) -> dict:
	"""Send a standalone WhatsApp document message (needs open customer window)."""
	from ths_whatsapp.api.whatsapp import _get_settings, _graph_request

	settings, token = _get_settings()
	api_version = settings.api_version or "v25.0"
	url = f"https://graph.facebook.com/{api_version}/{settings.phone_number_id}/messages"
	document = {"id": media_id, "filename": filename}
	if caption:
		document["caption"] = caption[:1024]
	payload = {
		"messaging_product": "whatsapp",
		"to": to,
		"type": "document",
		"document": document,
	}
	return _graph_request(url, token=token, method="POST", payload=payload)


def _send_for_doc(doc, to: str | None = None, template: str | None = None) -> dict:
	settings = frappe.get_single("WhatsApp Settings")
	if not settings.enabled:
		frappe.throw(_("WhatsApp integration is disabled. Enable it in WhatsApp Settings."))

	to = normalize_phone(to) if to else get_recipient_number(doc)
	if not to:
		frappe.throw(_("No mobile number found on {0} {1}").format(doc.doctype, doc.name))

	linked = template
	if not linked:
		mapping = {
			"Quotation": settings.get("quotation_template"),
			"Sales Invoice": settings.get("sales_invoice_template"),
			"Support Ticket": settings.get("support_ticket_template"),
		}
		linked = mapping.get(doc.doctype) or settings.default_template

	template_name, language = resolve_template_ref(linked)
	template_name = template_name or "payment_alert"
	language = language or settings.default_template_lang or "en"
	body_params = build_body_params(doc)

	header_document = None
	pdf_followup = None
	header_type = _template_header_type(linked)
	# Quotation / Sales Invoice: attach PDF with DOCUMENT header, else follow-up document msg
	if doc.doctype in ("Quotation", "Sales Invoice"):
		from ths_whatsapp.api.media import generate_doctype_pdf, upload_media_for_send

		pdf_bytes, filename = generate_doctype_pdf(doc.doctype, doc.name)
		media_id = upload_media_for_send(pdf_bytes, filename, "application/pdf")
		if header_type == "Document":
			header_document = {"id": media_id, "filename": filename}
		else:
			pdf_followup = {"id": media_id, "filename": filename}

	from ths_whatsapp.api.whatsapp import (
		_create_log,
		send_template_request,
	)

	response, payload = send_template_request(
		to=to,
		template=template_name,
		language=language,
		body_params=body_params,
		header_document=header_document,
	)
	log_name = _create_log(
		to=to,
		template=template_name,
		language=language,
		body_params=body_params,
		payload=payload,
		response=response,
		reference_doctype=doc.doctype,
		reference_name=doc.name,
	)

	pdf_sent = bool(header_document)
	pdf_response = None
	if pdf_followup and not response.get("error"):
		pdf_response = _send_document_message(
			to=to,
			media_id=pdf_followup["id"],
			filename=pdf_followup["filename"],
			caption=f"{doc.doctype} {doc.name}",
		)
		pdf_sent = not bool(pdf_response.get("error"))
		if pdf_response.get("error"):
			frappe.log_error(
				title=f"WhatsApp PDF follow-up failed: {doc.doctype} {doc.name}",
				message=frappe.as_json(pdf_response),
			)

	response["_log"] = log_name
	response["_to"] = to
	response["_template"] = template_name
	response["_body_params"] = body_params
	response["_pdf"] = pdf_sent
	response["_pdf_response"] = pdf_response
	return response


@frappe.whitelist()
def send_document_whatsapp(
	doctype: str,
	name: str,
	to: str | None = None,
	template: str | None = None,
) -> dict:
	"""Manual send from Quotation / Sales Invoice / Support Ticket form."""
	if doctype not in SUPPORTED_DOCTYPES:
		frappe.throw(_("WhatsApp send is not supported for {0}").format(doctype))

	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	return _send_for_doc(doc, to=to, template=template)


@frappe.whitelist()
def preview_document_whatsapp(doctype: str, name: str) -> dict:
	"""Return resolved phone + body params without sending."""
	if doctype not in SUPPORTED_DOCTYPES:
		frappe.throw(_("Unsupported DocType: {0}").format(doctype))
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	return {
		"to": get_recipient_number(doc),
		"template": get_template_for_doctype(doctype),
		"body_params": build_body_params(doc),
	}


def _should_auto_send(doc, method: str | None, settings) -> bool:
	"""Decide from WhatsApp Settings 'When to Send' selects."""
	doctype = doc.doctype

	if doctype == "Quotation":
		when = settings.get("quotation_send_when") or "Manual Only"
		if when == "Manual Only" and settings.get("auto_send_quotation"):
			when = "On Submit"
		return when == "On Submit" and method == "on_submit"

	if doctype == "Sales Invoice":
		when = settings.get("sales_invoice_send_when") or "Manual Only"
		if when == "Manual Only" and settings.get("auto_send_sales_invoice"):
			when = "On Submit"
		return when == "On Submit" and method == "on_submit"

	if doctype == "Support Ticket":
		when = settings.get("support_ticket_send_when") or "Manual Only"
		if when == "Manual Only" and settings.get("auto_send_support_ticket"):
			when = "On Create"
		if method == "after_insert":
			return when in ("On Create", "On Create and Status Change")
		if method == "on_update":
			if when not in ("On Status Change", "On Create and Status Change"):
				return False
			before = doc.get_doc_before_save()
			if not before:
				return False
			return before.get("status") != doc.get("status")
		return False

	return False


def maybe_auto_send(doc, method: str | None = None):
	"""Called from doc_events according to WhatsApp Settings when-to-send."""
	try:
		settings = frappe.get_single("WhatsApp Settings")
		if not settings.enabled:
			return
		if not _should_auto_send(doc, method, settings):
			return

		if not get_recipient_number(doc):
			frappe.log_error(
				title=f"WhatsApp auto-send skipped: no mobile ({doc.doctype} {doc.name})",
				message="No recipient number",
			)
			return

		result = _send_for_doc(doc)
		if result.get("error"):
			frappe.log_error(
				title=f"WhatsApp auto-send failed: {doc.doctype} {doc.name}",
				message=frappe.as_json(result),
			)
	except Exception:
		frappe.log_error(title=f"WhatsApp auto-send error: {doc.doctype} {doc.name}")
