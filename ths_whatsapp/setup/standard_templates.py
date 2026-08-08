# Copyright (c) 2026, THS Solution and contributors
# License: MIT. See LICENSE

"""Create standard WhatsApp templates and wire document automation."""

from __future__ import annotations

import frappe
from frappe.utils import add_days, getdate, nowdate


STANDARD_TEMPLATES = [
	{
		"template_name": "quotation_submit",
		"language": "en",
		"category": "UTILITY",
		"related_doctype": "Quotation",
		"header_type": "Text",
		"header_text": "Quotation Submitted",
		"body_text": (
			"Hello {{1}},\n\n"
			"Your quotation {{3}} amounting to {{2}} has been submitted.\n\n"
			"Valid till: {{4}}\n\n"
			"Thank you for choosing Live U."
		),
		"footer_text": "Live U (Pvt) Ltd",
		"sample_values": "Mr Customer, Rs. 25000.00, SAL-QTN-2026-00001, 31-08-2026",
	},
	{
		"template_name": "quotation_with_pdf",
		"language": "en",
		"category": "UTILITY",
		"related_doctype": "Quotation",
		"header_type": "Document",
		"header_text": None,
		"body_text": (
			"Hello {{1}},\n\n"
			"Your quotation {{3}} amounting to {{2}} is attached as a PDF.\n\n"
			"Valid till: {{4}}\n\n"
			"Thank you for choosing Live U."
		),
		"footer_text": "Live U (Pvt) Ltd",
		"sample_values": "Mr Customer, Rs. 25000.00, SAL-QTN-2026-00001, 31-08-2026",
	},
	{
		"template_name": "invoice_due_reminder",
		"language": "en",
		"category": "UTILITY",
		"related_doctype": "Sales Invoice",
		"header_type": "Text",
		"header_text": "Payment Reminder",
		"body_text": (
			"Hello {{1}},\n\n"
			"Payment of {{2}} is pending for invoice {{3}}.\n\n"
			"Due date: {{4}}\n\n"
			"Kindly complete the payment at the earliest."
		),
		"footer_text": "Live U (Pvt) Ltd",
		"sample_values": "Mr Customer, Rs. 15000.00, ACC-SINV-2026-00001, 10-08-2026",
	},
	{
		"template_name": "support_ticket_update",
		"language": "en",
		"category": "UTILITY",
		"related_doctype": "Support Ticket",
		"header_type": "Text",
		"header_text": "Support Ticket Update",
		"body_text": (
			"Hello {{1}},\n\n"
			"Support ticket {{3}} has been updated.\n\n"
			"Subject: {{2}}\n"
			"Status: {{4}}\n\n"
			"Our team will assist you shortly."
		),
		"footer_text": "Live U (Pvt) Ltd",
		"sample_values": "Pradeep, CCTV not working, SUP-TKT-00001, Open",
	},
]


def _ensure_sample_pdf(doc) -> None:
	"""Attach a small sample PDF for DOCUMENT header Meta submission."""
	if (doc.get("header_type") or "") != "Document":
		return
	if doc.get("header_media"):
		return

	from frappe.utils.file_manager import save_file

	# Minimal valid PDF
	pdf_bytes = (
		b"%PDF-1.4\n1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n"
		b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n"
		b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] "
		b"/Contents 4 0 R /Resources<< /Font<< /F1 5 0 R >> >> >>endobj\n"
		b"4 0 obj<< /Length 55 >>stream\nBT /F1 18 Tf 40 80 Td (Sample Quotation) Tj ET\n"
		b"endstream\nendobj\n"
		b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n"
		b"xref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n"
		b"0000000115 00000 n \n0000000266 00000 n \n0000000371 00000 n \n"
		b"trailer<< /Size 6 /Root 1 0 R >>\nstartxref\n448\n%%EOF\n"
	)
	file_doc = save_file(
		f"{doc.template_name}_sample.pdf",
		pdf_bytes,
		"WhatsApp Message Template",
		doc.name,
		decode=False,
		is_private=1,
		df="header_media",
	)
	doc.db_set("header_media", file_doc.file_url, update_modified=False)
	doc.header_media = file_doc.file_url


def ensure_standard_templates(submit_to_meta: bool = True) -> dict:
	"""Create local template docs and optionally submit to Meta for approval."""
	from ths_whatsapp.api.whatsapp import submit_template_for_approval

	created = []
	submitted = []
	errors = []

	for spec in STANDARD_TEMPLATES:
		docname = f"{spec['template_name']}-{spec['language']}"
		clean = {k: v for k, v in spec.items() if v is not None}
		if frappe.db.exists("WhatsApp Message Template", docname):
			doc = frappe.get_doc("WhatsApp Message Template", docname)
			doc.flags.ignore_status_lock = True
			# Always keep related_doctype / local metadata in sync
			doc.related_doctype = clean.get("related_doctype")
			if doc.status == "DRAFT":
				doc.update(clean)
			doc.save(ignore_permissions=True)
		else:
			doc = frappe.get_doc({"doctype": "WhatsApp Message Template", "status": "DRAFT", **clean})
			doc.insert(ignore_permissions=True)
			created.append(doc.name)

		try:
			_ensure_sample_pdf(doc)
		except Exception as e:
			errors.append({"template": doc.name, "error": f"sample pdf: {e}"})

		if submit_to_meta and doc.status in ("DRAFT", "REJECTED"):
			try:
				# reload after sample attach
				doc = frappe.get_doc("WhatsApp Message Template", doc.name)
				result = submit_template_for_approval(doc.name)
				if result.get("error"):
					errors.append({"template": doc.name, "error": result.get("error")})
				else:
					submitted.append(doc.name)
			except Exception as e:
				errors.append({"template": doc.name, "error": str(e)})

	_apply_document_settings()
	return {"created": created, "submitted": submitted, "errors": errors}


def _apply_document_settings():
	"""Point WhatsApp Settings to the new templates and enable triggers."""
	s = frappe.get_single("WhatsApp Settings")
	s.flags.ignore_permissions = True

	if frappe.db.exists("WhatsApp Message Template", "quotation_with_pdf-en"):
		status = frappe.db.get_value("WhatsApp Message Template", "quotation_with_pdf-en", "status")
		if status == "APPROVED":
			s.quotation_template = "quotation_with_pdf-en"
		elif frappe.db.exists("WhatsApp Message Template", "quotation_submit-en"):
			s.quotation_template = "quotation_submit-en"
	elif frappe.db.exists("WhatsApp Message Template", "quotation_submit-en"):
		s.quotation_template = "quotation_submit-en"
	if frappe.db.exists("WhatsApp Message Template", "invoice_due_reminder-en"):
		s.sales_invoice_template = "invoice_due_reminder-en"
	if frappe.db.exists("WhatsApp Message Template", "support_ticket_update-en"):
		s.support_ticket_template = "support_ticket_update-en"

	s.quotation_send_when = "On Submit"
	# Invoice: due reminder scheduler (not on submit)
	s.sales_invoice_send_when = "Manual Only"
	s.support_ticket_send_when = "On Create and Status Change"

	if hasattr(s, "invoice_due_reminder_enabled"):
		s.invoice_due_reminder_enabled = 1
	if hasattr(s, "invoice_due_reminder_days"):
		s.invoice_due_reminder_days = s.invoice_due_reminder_days or 3

	s.save()


def send_invoice_due_reminders():
	"""
	Daily job: WhatsApp reminder for Sales Invoices with outstanding amount,
	once every N days (default 3).
	"""
	settings = frappe.get_single("WhatsApp Settings")
	if not settings.enabled:
		return
	if not getattr(settings, "invoice_due_reminder_enabled", 0):
		return

	days = cint_safe(getattr(settings, "invoice_due_reminder_days", None), 3)
	template_link = settings.get("sales_invoice_template") or "invoice_due_reminder-en"

	from ths_whatsapp.api.documents import _send_for_doc, get_recipient_number

	invoices = frappe.get_all(
		"Sales Invoice",
		filters={
			"docstatus": 1,
			"outstanding_amount": [">", 0],
			"is_return": 0,
		},
		fields=["name", "due_date", "outstanding_amount", "customer_name"],
		limit_page_length=500,
	)

	sent = 0
	skipped = 0
	today = getdate(nowdate())

	for inv in invoices:
		# Only remind if due date reached/passed, or always when outstanding?
		# User asked: pending due amount every 3 days — include outstanding past/near due
		due = getdate(inv.due_date) if inv.due_date else None
		if due and due > today:
			# not yet due — skip until due date
			skipped += 1
			continue

		last = frappe.db.sql(
			"""
			SELECT MAX(creation) FROM `tabWhatsApp Message Log`
			WHERE reference_doctype=%s AND reference_name=%s
			  AND template_name=%s AND status='Sent'
			""",
			("Sales Invoice", inv.name, "invoice_due_reminder"),
		)
		last_dt = last[0][0] if last and last[0][0] else None
		if last_dt and getdate(last_dt) > add_days(today, -days):
			skipped += 1
			continue

		doc = frappe.get_doc("Sales Invoice", inv.name)
		if not get_recipient_number(doc):
			skipped += 1
			continue

		try:
			result = _send_for_doc(doc, template=template_link)
			if not result.get("error"):
				sent += 1
			else:
				frappe.log_error(
					title=f"Invoice due WhatsApp failed: {inv.name}",
					message=frappe.as_json(result),
				)
		except Exception:
			frappe.log_error(title=f"Invoice due WhatsApp error: {inv.name}")

	return {"sent": sent, "skipped": skipped, "checked": len(invoices)}


def cint_safe(val, default=0):
	try:
		return int(val) if val not in (None, "") else default
	except Exception:
		return default
