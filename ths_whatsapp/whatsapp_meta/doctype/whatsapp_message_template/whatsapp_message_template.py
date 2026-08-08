# Copyright (c) 2026, THS Solution and contributors
# License: MIT. See LICENSE

import re

import frappe
from frappe.model.document import Document


class WhatsAppMessageTemplate(Document):
	def validate(self):
		name = (self.template_name or "").strip().lower()
		if not re.fullmatch(r"[a-z][a-z0-9_]*", name or ""):
			frappe.throw(
				"Template Name must start with a letter and contain only lowercase letters, numbers, and underscores."
			)
		self.template_name = name
		self.language = (self.language or "en").strip()

		if self.body_text:
			nums = [int(n) for n in re.findall(r"\{\{(\d+)\}\}", self.body_text)]
			self.body_param_count = max(nums) if nums else 0
		else:
			self.body_param_count = 0

		# Locked fields after submit to Meta (except refresh via sync)
		if self.status not in ("DRAFT",) and not self.flags.ignore_status_lock:
			before = self.get_doc_before_save()
			if before and before.status not in ("DRAFT",):
				for field in (
					"template_name",
					"language",
					"category",
					"header_type",
					"header_text",
					"header_media",
					"body_text",
					"footer_text",
				):
					if self.get(field) != before.get(field):
						frappe.throw(f"Cannot change {field} after template is submitted to Meta. Status: {self.status}")

		if not self.status:
			self.status = "DRAFT"
		if not self.header_type:
			self.header_type = "None"
