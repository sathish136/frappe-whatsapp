// Copyright (c) 2026, THS Solution and contributors
// License: MIT. See LICENSE

frappe.listview_settings["WhatsApp Message Template"] = {
	add_fields: [
		"status",
		"body_param_count",
		"category",
		"related_doctype",
		"header_type",
		"header_image",
		"header_media",
	],
	onload(listview) {
		listview.page.add_inner_button(__("Sync from Meta"), () => {
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
							[r.message.created || 0, r.message.updated || 0, r.message.synced || 0]
						),
					});
					listview.refresh();
				},
			});
		});
	},
	get_indicator(doc) {
		const colors = {
			DRAFT: "blue",
			PENDING: "orange",
			APPROVED: "green",
			REJECTED: "red",
			PAUSED: "orange",
			DISABLED: "darkgrey",
			IN_APPEAL: "blue",
			UNKNOWN: "grey",
		};
		const labels = {
			PENDING: __("Waiting for Approval"),
			DRAFT: __("Draft"),
			APPROVED: __("Approved"),
			REJECTED: __("Rejected"),
		};
		return [
			labels[doc.status] || __(doc.status || "UNKNOWN"),
			colors[doc.status] || "grey",
			"status,=," + doc.status,
		];
	},
	formatters: {
		header_type(value, df, doc) {
			const type = value || "None";
			const icons = {
				None: "—",
				Text: "📝 Text",
				Image: "🖼 Image",
				Video: "🎬 Video",
				Document: "📄 Document",
			};
			let html = `<span>${icons[type] || frappe.utils.escape_html(type)}</span>`;
			if (type === "Image" && doc.header_image) {
				html += ` <img src="${frappe.utils.escape_html(
					doc.header_image
				)}" style="height:28px;width:28px;object-fit:cover;border-radius:4px;margin-left:6px;vertical-align:middle;border:1px solid #d1d8dd;">`;
			}
			return html;
		},
	},
};
