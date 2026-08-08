# Copyright (c) 2026, THS Solution and contributors
# License: MIT. See LICENSE

from . import __version__ as app_version

app_name = "ths_whatsapp"
app_title = "THS WhatsApp"
app_publisher = "THS Solution"
app_description = "WhatsApp Meta Cloud API integration for ERPNext"
app_email = "info@thssolution.com"
app_license = "MIT"
app_copyright = "Copyright (c) 2026 THS Solution"

# Includes in <head>
# ------------------

app_include_js = "/assets/ths_whatsapp/js/whatsapp_form.js"

# Installation
# ------------

after_install = "ths_whatsapp.install.after_install"

# Client scripts for forms
# ------------------------

doctype_js = {
	"Quotation": "public/js/quotation.js",
	"Sales Invoice": "public/js/sales_invoice.js",
	"Support Ticket": "public/js/support_ticket.js",
}

# Document Events
# ---------------

doc_events = {
	"Quotation": {
		"on_submit": "ths_whatsapp.api.documents.maybe_auto_send",
	},
	"Sales Invoice": {
		"on_submit": "ths_whatsapp.api.documents.maybe_auto_send",
	},
	"Support Ticket": {
		"after_insert": "ths_whatsapp.api.documents.maybe_auto_send",
		"on_update": "ths_whatsapp.api.documents.maybe_auto_send",
	},
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"daily": [
		"ths_whatsapp.setup.standard_templates.send_invoice_due_reminders",
	],
}
