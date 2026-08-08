// Copyright (c) 2026, THS Solution and contributors
// License: MIT. See LICENSE

frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		ths_whatsapp.add_send_button(frm);
	},
});
