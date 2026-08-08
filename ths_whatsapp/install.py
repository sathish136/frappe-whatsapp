# Copyright (c) 2026, THS Solution and contributors
# License: MIT. See LICENSE

import frappe


def after_install():
	"""Seed safe defaults after install. Credentials must be set in WhatsApp Settings."""
	if not frappe.db.exists("DocType", "WhatsApp Settings"):
		return

	settings = frappe.get_single("WhatsApp Settings")
	if not settings.api_version:
		settings.api_version = "v25.0"
	if not settings.default_template_lang:
		settings.default_template_lang = "en"
	if not settings.get("quotation_send_when"):
		settings.quotation_send_when = "Manual Only"
	if not settings.get("sales_invoice_send_when"):
		settings.sales_invoice_send_when = "Manual Only"
	if not settings.get("support_ticket_send_when"):
		settings.support_ticket_send_when = "Manual Only"
	if hasattr(settings, "invoice_due_reminder_days") and not settings.get("invoice_due_reminder_days"):
		settings.invoice_due_reminder_days = 3
	settings.flags.ignore_permissions = True
	settings.save()
	frappe.db.commit()
