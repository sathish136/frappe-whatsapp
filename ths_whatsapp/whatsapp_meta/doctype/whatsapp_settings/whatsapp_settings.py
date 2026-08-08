# Copyright (c) 2026, THS Solution and contributors
# License: MIT. See LICENSE

import frappe
from frappe.model.document import Document


class WhatsAppSettings(Document):
	def validate(self):
		if self.enabled and not self.get_password("access_token"):
			frappe.throw("Access Token is required when WhatsApp is enabled.")

		# Keep legacy checkboxes in sync with Select "when to send"
		self.auto_send_quotation = 1 if self.quotation_send_when == "On Submit" else 0
		self.auto_send_sales_invoice = 1 if self.sales_invoice_send_when == "On Submit" else 0
		self.auto_send_support_ticket = 1 if self.support_ticket_send_when in (
			"On Create",
			"On Create and Status Change",
		) else 0
