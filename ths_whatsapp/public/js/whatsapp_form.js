// Copyright (c) 2026, THS Solution and contributors
// License: MIT. See LICENSE

frappe.provide("ths_whatsapp");

ths_whatsapp.send_from_form = function (frm) {
	if (frm.is_new()) {
		frappe.msgprint(__("Please save the document first."));
		return;
	}

	frappe.call({
		method: "ths_whatsapp.api.documents.preview_document_whatsapp",
		args: { doctype: frm.doc.doctype, name: frm.doc.name },
		callback(r) {
			if (!r.message) return;
			const preview = r.message;
			if (!preview.to) {
				frappe.msgprint(__("No mobile number found on this document."));
				return;
			}

			const d = new frappe.ui.Dialog({
				title: __("Send WhatsApp"),
				fields: [
					{
						fieldtype: "Data",
						fieldname: "to",
						label: __("To Number"),
						default: preview.to,
						reqd: 1,
						description: __("Digits only, country code included (e.g. 9477…)"),
					},
					{
						fieldtype: "Data",
						fieldname: "template",
						label: __("Template"),
						default: preview.template,
						reqd: 1,
					},
					{
						fieldtype: "Small Text",
						fieldname: "body_params",
						label: __("Body Params ({{1}}, {{2}}, …)"),
						default: (preview.body_params || []).join(", "),
						read_only: 1,
					},
				],
				primary_action_label: __("Send"),
				primary_action(values) {
					d.hide();
					frappe.call({
						method: "ths_whatsapp.api.documents.send_document_whatsapp",
						args: {
							doctype: frm.doc.doctype,
							name: frm.doc.name,
							to: values.to,
							template: values.template,
						},
						freeze: true,
						freeze_message: __("Sending WhatsApp…"),
						callback(res) {
							if (!res.message) return;
							const msg = res.message;
							frappe.msgprint({
								title: msg.error ? __("WhatsApp Failed") : __("WhatsApp Sent"),
								indicator: msg.error ? "red" : "green",
								message: `<pre style="max-height:360px;overflow:auto;white-space:pre-wrap;">${frappe.utils.escape_html(
									JSON.stringify(msg, null, 2)
								)}</pre>`,
							});
						},
					});
				},
			});
			d.show();
		},
	});
};

ths_whatsapp.add_send_button = function (frm) {
	if (frm.is_new()) return;
	frm.add_custom_button(__("Send WhatsApp"), () => ths_whatsapp.send_from_form(frm), __(
		"WhatsApp"
	));
};
