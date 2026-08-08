// Copyright (c) 2026, THS Solution and contributors
// License: MIT. See LICENSE

frappe.ui.form.on("WhatsApp Message Template", {
	refresh(frm) {
		frm.add_custom_button(__("Sync All from Meta"), () => {
			frappe.call({
				method: "ths_whatsapp.api.whatsapp.sync_message_templates",
				freeze: true,
				freeze_message: __("Syncing templates from Meta…"),
				callback(r) {
					if (r.message) {
						frappe.show_alert({
							message: __("Synced {0} templates", [r.message.synced || 0]),
							indicator: "green",
						});
						frm.reload_doc();
					}
				},
			});
		});

		if (frm.doc.status === "PENDING") {
			frm.set_intro(
				__("Waiting for Meta approval. Use Refresh Status after Meta reviews this template."),
				"orange"
			);
		} else if (frm.doc.status === "APPROVED") {
			frm.set_intro(__("Approved — ready to send."), "green");
		} else if (frm.doc.status === "REJECTED") {
			frm.set_intro(__("Rejected by Meta. Check Rejection Reason and create a new template."), "red");
		} else if (frm.doc.status === "DRAFT") {
			frm.set_intro(__("Draft — edit content, then Submit for Approval to Meta."), "blue");
		}

		const editable = frm.doc.status === "DRAFT" || frm.is_new();
		[
			"template_name",
			"language",
			"category",
			"related_doctype",
			"header_type",
			"header_text",
			"header_media",
			"body_text",
			"footer_text",
			"sample_values",
		].forEach((f) => frm.set_df_property(f, "read_only", !editable));

		// Related DocType can always be updated (local ERP link, not Meta content)
		frm.set_df_property("related_doctype", "read_only", 0);

		frm.set_query("related_doctype", () => ({
			filters: {
				name: ["in", ["Quotation", "Sales Invoice", "Support Ticket", "Lead", "Customer", "Payment Entry"]],
			},
		}));

		ths_whatsapp_render_body_variable_buttons(frm, editable);
		ths_whatsapp_render_preview(frm);

		if (!frm.is_new() && frm.doc.status === "DRAFT") {
			frm.add_custom_button(
				__("Submit for Approval"),
				() => {
					frappe.confirm(
						__(
							"Submit this template to Meta for approval? Status will become PENDING (waiting for approval)."
						),
						() => {
							frappe.call({
								method: "ths_whatsapp.api.whatsapp.submit_template_for_approval",
								args: { name: frm.doc.name },
								freeze: true,
								freeze_message: __("Submitting to Meta…"),
								callback(r) {
									if (!r.message) return;
									if (r.message.error) {
										frappe.msgprint({
											title: __("Submit Failed"),
											indicator: "red",
											message: `<pre>${frappe.utils.escape_html(
												JSON.stringify(r.message, null, 2)
											)}</pre>`,
										});
									} else {
										frappe.show_alert({
											message: __("Submitted — waiting for Meta approval"),
											indicator: "orange",
										});
										frm.reload_doc();
									}
								},
							});
						}
					);
				},
				__("Actions")
			);
		}

		if (
			!frm.is_new() &&
			["PENDING", "APPROVED", "REJECTED", "PAUSED", "IN_APPEAL"].includes(frm.doc.status)
		) {
			frm.add_custom_button(
				__("Refresh Status"),
				() => {
					frappe.call({
						method: "ths_whatsapp.api.whatsapp.refresh_template_status",
						args: { name: frm.doc.name },
						freeze: true,
						freeze_message: __("Refreshing status from Meta…"),
						callback(r) {
							if (r.message) {
								frappe.show_alert({
									message: __("Status: {0}", [r.message.status || "-"]),
									indicator: r.message.status === "APPROVED" ? "green" : "orange",
								});
								frm.reload_doc();
							}
						},
					});
				},
				__("Actions")
			);
		}
	},

	header_type(frm) {
		ths_whatsapp_render_preview(frm);
	},
	header_text(frm) {
		ths_whatsapp_render_preview(frm);
	},
	header_media(frm) {
		ths_whatsapp_render_preview(frm);
	},
	body_text(frm) {
		ths_whatsapp_update_body_param_count(frm);
		ths_whatsapp_render_preview(frm);
	},
	footer_text(frm) {
		ths_whatsapp_render_preview(frm);
	},
	sample_values(frm) {
		ths_whatsapp_render_preview(frm);
	},
});

function ths_whatsapp_update_body_param_count(frm) {
	const text = frm.doc.body_text || "";
	const matches = [...text.matchAll(/\{\{(\d+)\}\}/g)].map((m) => cint(m[1]));
	frm.set_value("body_param_count", matches.length ? Math.max(...matches) : 0);
}

function ths_whatsapp_next_variable_number(frm) {
	const text = frm.doc.body_text || "";
	const matches = [...text.matchAll(/\{\{(\d+)\}\}/g)].map((m) => cint(m[1]));
	return matches.length ? Math.max(...matches) + 1 : 1;
}

function ths_whatsapp_insert_body_variable(frm, n) {
	const token = `{{${n}}}`;
	const field = frm.fields_dict.body_text;
	const $input = field && field.$input;
	if ($input && $input.length) {
		const el = $input.get(0);
		const start = el.selectionStart != null ? el.selectionStart : (el.value || "").length;
		const end = el.selectionEnd != null ? el.selectionEnd : start;
		const val = el.value || "";
		const new_val = val.substring(0, start) + token + val.substring(end);
		frm.set_value("body_text", new_val).then(() => {
			el.focus();
			const pos = start + token.length;
			if (el.setSelectionRange) {
				el.setSelectionRange(pos, pos);
			}
			ths_whatsapp_update_body_param_count(frm);
			ths_whatsapp_render_preview(frm);
		});
	} else {
		frm.set_value("body_text", (frm.doc.body_text || "") + token).then(() => {
			ths_whatsapp_update_body_param_count(frm);
			ths_whatsapp_render_preview(frm);
		});
	}
}

function ths_whatsapp_render_body_variable_buttons(frm, editable) {
	const field = frm.get_field("body_text");
	if (!field || !field.$wrapper) return;

	field.$wrapper.find(".wa-body-var-btns").remove();
	if (!editable) return;

	const $bar = $(`
		<div class="wa-body-var-btns" style="margin: 8px 0 12px; display:flex; flex-wrap:wrap; gap:6px; align-items:center;">
			<span class="text-muted" style="margin-right:4px;">${__("Insert variable")}:</span>
		</div>
	`);

	for (let i = 1; i <= 8; i++) {
		const $btn = $(
			`<button type="button" class="btn btn-xs btn-default" data-var="${i}">{{${i}}}</button>`
		);
		$btn.on("click", () => ths_whatsapp_insert_body_variable(frm, i));
		$bar.append($btn);
	}

	const $next = $(
		`<button type="button" class="btn btn-xs btn-primary">${__("Next Variable")}</button>`
	);
	$next.on("click", () => {
		const n = ths_whatsapp_next_variable_number(frm);
		ths_whatsapp_insert_body_variable(frm, n);
	});
	$bar.append($next);

	const $anchor = field.$wrapper.find(".control-input-wrapper");
	if ($anchor.length) {
		$anchor.after($bar);
	} else {
		field.$wrapper.append($bar);
	}
}

function ths_whatsapp_escape(s) {
	return frappe.utils.escape_html(s == null ? "" : String(s));
}

function ths_whatsapp_fill_sample_body(body, sample_values) {
	let text = body || "";
	const samples = (sample_values || "")
		.split(",")
		.map((p) => p.trim())
		.filter(Boolean);
	text = text.replace(/\{\{(\d+)\}\}/g, (match, n) => {
		const idx = cint(n) - 1;
		return samples[idx] != null && samples[idx] !== "" ? samples[idx] : match;
	});
	return text;
}

function ths_whatsapp_render_preview(frm) {
	const field = frm.get_field("preview_html");
	if (!field || !field.$wrapper) return;

	const header_type = frm.doc.header_type || "None";
	const body = ths_whatsapp_fill_sample_body(frm.doc.body_text || "", frm.doc.sample_values);
	const footer = frm.doc.footer_text || "";

	let header_html = "";
	if (header_type === "Text" && frm.doc.header_text) {
		header_html = `<div style="font-weight:600;margin-bottom:6px;">${ths_whatsapp_escape(
			frm.doc.header_text
		)}</div>`;
	} else if (header_type === "Image") {
		if (frm.doc.header_media) {
			header_html = `<div style="margin-bottom:8px;"><img src="${ths_whatsapp_escape(
				frm.doc.header_media
			)}" style="width:100%;max-height:160px;object-fit:cover;border-radius:8px;"></div>`;
		} else {
			header_html = `<div style="margin-bottom:8px;background:#d1d7db;border-radius:8px;height:100px;display:flex;align-items:center;justify-content:center;color:#54656f;">🖼 ${__(
				"Image header"
			)}</div>`;
		}
	} else if (header_type === "Video") {
		header_html = `<div style="margin-bottom:8px;background:#d1d7db;border-radius:8px;height:100px;display:flex;align-items:center;justify-content:center;color:#54656f;text-align:center;padding:8px;">🎬 ${__(
			"Video header"
		)}${
			frm.doc.header_media
				? `<br><small>${ths_whatsapp_escape(frm.doc.header_media.split("/").pop())}</small>`
				: ""
		}</div>`;
	} else if (header_type === "Document") {
		header_html = `<div style="margin-bottom:8px;background:#d1d7db;border-radius:8px;padding:12px;display:flex;align-items:center;gap:10px;color:#54656f;">📄 <span>${__(
			"Document header"
		)}${
			frm.doc.header_media
				? ` — ${ths_whatsapp_escape(frm.doc.header_media.split("/").pop())}`
				: ""
		}</span></div>`;
	}

	const body_html = ths_whatsapp_escape(body).replace(/\n/g, "<br>");
	const footer_html = footer
		? `<div style="margin-top:8px;font-size:11px;color:#667781;">${ths_whatsapp_escape(
				footer
		  )}</div>`
		: "";

	const html = `
		<div class="wa-side-preview" style="position:sticky;top:80px;">
			<div style="font-weight:600;margin-bottom:8px;color:#54656f;">${__("Preview")}</div>
			<div style="background:#efeae2;padding:14px;border-radius:10px;">
				<div style="background:#fff;border-radius:10px;padding:10px 12px;box-shadow:0 1px 1px rgba(0,0,0,.08);">
					${header_html}
					<div style="font-size:14px;line-height:1.45;color:#111b21;">${
						body_html ||
						`<span style="color:#8696a0">${__("Body text preview")}</span>`
					}</div>
					${footer_html}
					<div style="text-align:right;font-size:10px;color:#8696a0;margin-top:4px;">12:00 ✓✓</div>
				</div>
				<div style="margin-top:8px;font-size:11px;color:#54656f;">
					${__("Header")}: <b>${ths_whatsapp_escape(header_type)}</b>
					&nbsp;|&nbsp; ${__("Body")}: <b>${__("Text")}</b>
					&nbsp;|&nbsp; ${__("Footer")}: <b>${footer ? __("Text") : __("None")}</b>
				</div>
			</div>
		</div>
	`;

	// Prefer html_field area used by Frappe HTML fields
	let $box = field.$wrapper.find(".wa-preview-host");
	if (!$box.length) {
		field.$wrapper.find(".control-input-wrapper, .form-group, .control-value").empty();
		$box = $('<div class="wa-preview-host"></div>');
		field.$wrapper.append($box);
	}
	$box.html(html);
}
