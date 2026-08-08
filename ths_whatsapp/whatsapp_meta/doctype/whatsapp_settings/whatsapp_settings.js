// Copyright (c) 2026, THS Solution and contributors
// License: MIT. See LICENSE

frappe.ui.form.on("WhatsApp Settings", {
	refresh(frm) {
		frm.set_intro(
			__(
				"In section 2, choose when WhatsApp messages should be sent for Quotation, Sales Invoice, and Support Ticket. The manual Send WhatsApp button is always available on each form."
			)
		);

		frm.set_query("quotation_template", () => ({
			filters: { related_doctype: "Quotation" },
		}));
		frm.set_query("sales_invoice_template", () => ({
			filters: { related_doctype: "Sales Invoice" },
		}));
		frm.set_query("support_ticket_template", () => ({
			filters: { related_doctype: "Support Ticket" },
		}));

		frm.add_custom_button(__("Sync Templates"), () => {
			frappe.call({
				method: "ths_whatsapp.api.whatsapp.sync_message_templates",
				freeze: true,
				freeze_message: __("Syncing templates from Meta…"),
				callback(r) {
					if (!r.message) return;
					frappe.msgprint({
						title: __("Templates Synced"),
						indicator: "green",
						message: __(
							"Created: {0}, Updated: {1}, Total: {2}",
							[
								r.message.created || 0,
								r.message.updated || 0,
								r.message.synced || 0,
							]
						),
					});
					frm.reload_doc();
				},
			});
		});

		frm.add_custom_button(__("Open Templates"), () => {
			frappe.set_route("List", "WhatsApp Message Template");
		});

		frm.add_custom_button(__("Send Test Template"), () => {
			const to = frm.doc.default_to_number;
			if (!to) {
				frappe.msgprint(__("Set Default To Number first."));
				return;
			}
			if (!frm.doc.test_body_params) {
				frappe.msgprint(
					__(
						"Set Test Body Params (comma-separated). payment_alert needs 4 values, e.g. Name, 1500, INV-001, 08-04-2026"
					)
				);
				return;
			}
			const params = frm.doc.test_body_params
				.split(",")
				.map((p) => p.trim())
				.filter(Boolean);
			const expected = cint(frm.doc.default_body_param_count || 0);
			if (expected && params.length !== expected) {
				frappe.msgprint(
					__("This template expects {0} body params. You entered {1}.").format(
						expected,
						params.length
					)
				);
				return;
			}
			frappe.call({
				method: "ths_whatsapp.api.whatsapp.send_template",
				args: {
					to: to,
					template: frm.doc.default_template,
					language: frm.doc.default_template_lang,
					body_params: params,
				},
				freeze: true,
				freeze_message: __("Sending WhatsApp template…"),
				callback(r) {
					if (r.message) {
						frappe.msgprint({
							title: __("Send Result"),
							message: `<pre style="max-height:420px;overflow:auto;white-space:pre-wrap;">${frappe.utils.escape_html(
								JSON.stringify(r.message, null, 2)
							)}</pre>`,
							indicator: r.message.error ? "red" : "green",
						});
					}
				},
			});
		});

		frm.add_custom_button(__("Open Message Log"), () => {
			frappe.set_route("List", "WhatsApp Message Log");
		});
	},
});
