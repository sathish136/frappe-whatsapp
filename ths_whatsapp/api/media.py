# Copyright (c) 2026, THS Solution and contributors
# License: MIT. See LICENSE

"""WhatsApp / Meta media upload helpers (send media + template sample handles)."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import frappe
from frappe import _
from frappe.utils.pdf import get_pdf


def get_meta_app_id(token: str | None = None) -> str:
	"""Resolve Meta App ID from WhatsApp Settings or by debugging the access token."""
	from ths_whatsapp.api.whatsapp import _get_settings, _graph_request

	settings = frappe.get_single("WhatsApp Settings")
	app_id = (settings.get("meta_app_id") or "").strip()
	if app_id:
		return app_id

	if not token:
		_, token = _get_settings()
	api_version = settings.api_version or "v25.0"
	url = (
		f"https://graph.facebook.com/{api_version}/debug_token"
		f"?input_token={token}&access_token={token}"
	)
	data = _graph_request(url, token=token)
	app_id = ((data.get("data") or {}).get("app_id")) or ""
	if not app_id:
		frappe.throw(
			_("Could not resolve Meta App ID. Set Meta App ID in WhatsApp Settings.")
		)
	return str(app_id)


def generate_doctype_pdf(doctype: str, name: str, print_format: str | None = None) -> tuple[bytes, str]:
	"""Return (pdf_bytes, filename) for a document print."""
	html = frappe.get_print(doctype, name, print_format=print_format)
	pdf_bytes = get_pdf(html)
	safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
	filename = f"{doctype.replace(' ', '_')}_{safe_name}.pdf"
	return pdf_bytes, filename


def upload_media_for_send(
	file_bytes: bytes,
	filename: str,
	mime_type: str = "application/pdf",
) -> str:
	"""
	Upload media to WhatsApp Cloud API for use in outbound messages.
	Returns media id.
	"""
	from ths_whatsapp.api.whatsapp import _get_settings

	settings, token = _get_settings()
	api_version = settings.api_version or "v25.0"
	phone_number_id = settings.phone_number_id
	url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/media"

	boundary = "----thswhatsappboundary"
	body = b""
	body += f"--{boundary}\r\n".encode()
	body += b'Content-Disposition: form-data; name="messaging_product"\r\n\r\n'
	body += b"whatsapp\r\n"
	body += f"--{boundary}\r\n".encode()
	body += b'Content-Disposition: form-data; name="type"\r\n\r\n'
	body += f"{mime_type}\r\n".encode()
	body += f"--{boundary}\r\n".encode()
	body += (
		f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
	).encode()
	body += f"Content-Type: {mime_type}\r\n\r\n".encode()
	body += file_bytes + b"\r\n"
	body += f"--{boundary}--\r\n".encode()

	req = urllib.request.Request(
		url,
		data=body,
		method="POST",
		headers={
			"Authorization": f"Bearer {token}",
			"Content-Type": f"multipart/form-data; boundary={boundary}",
		},
	)
	try:
		with urllib.request.urlopen(req, timeout=120) as resp:
			parsed = json.loads(resp.read().decode("utf-8"))
	except urllib.error.HTTPError as e:
		err = e.read().decode("utf-8", errors="replace")
		try:
			parsed = json.loads(err)
		except json.JSONDecodeError:
			parsed = {"error": {"message": err, "code": e.code}}
		frappe.throw(_("WhatsApp media upload failed: {0}").format(parsed.get("error") or parsed))

	media_id = parsed.get("id")
	if not media_id:
		frappe.throw(_("WhatsApp media upload failed: {0}").format(parsed))
	return str(media_id)


def upload_header_handle(
	file_bytes: bytes,
	filename: str,
	mime_type: str = "application/pdf",
) -> str:
	"""
	Upload a sample file via Meta Resumable Upload API and return header_handle
	for template creation (DOCUMENT / IMAGE / VIDEO headers).
	"""
	from ths_whatsapp.api.whatsapp import _get_settings, _graph_request

	settings, token = _get_settings()
	api_version = settings.api_version or "v25.0"
	app_id = get_meta_app_id(token)

	start_url = (
		f"https://graph.facebook.com/{api_version}/{app_id}/uploads"
		f"?file_name={urllib.parse.quote(filename)}"
		f"&file_length={len(file_bytes)}"
		f"&file_type={urllib.parse.quote(mime_type)}"
		f"&access_token={urllib.parse.quote(token)}"
	)
	start = _graph_request(start_url, token=token, method="POST")
	session_id = start.get("id")
	if not session_id:
		frappe.throw(_("Meta upload session failed: {0}").format(start))

	upload_url = f"https://graph.facebook.com/{api_version}/{session_id}"
	req = urllib.request.Request(
		upload_url,
		data=file_bytes,
		method="POST",
		headers={
			"Authorization": f"OAuth {token}",
			"file_offset": "0",
			"Content-Type": "application/octet-stream",
		},
	)
	try:
		with urllib.request.urlopen(req, timeout=120) as resp:
			parsed = json.loads(resp.read().decode("utf-8"))
	except urllib.error.HTTPError as e:
		err = e.read().decode("utf-8", errors="replace")
		try:
			parsed = json.loads(err)
		except json.JSONDecodeError:
			parsed = {"error": {"message": err, "code": e.code}}
		frappe.throw(_("Meta file upload failed: {0}").format(parsed.get("error") or parsed))

	handle = parsed.get("h")
	if not handle:
		frappe.throw(_("Meta file upload did not return a handle: {0}").format(parsed))
	return str(handle)


def build_document_header_component(header_handle: str) -> dict[str, Any]:
	return {
		"type": "HEADER",
		"format": "DOCUMENT",
		"example": {"header_handle": [header_handle]},
	}
