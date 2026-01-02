from odoo import models, _
from odoo.exceptions import UserError


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    def action_open_batch_payment_wizard(self):
        payslips = self.filtered(lambda p: p.state == "validated" and p.move_id)

        if not payslips:
            raise UserError(_("Please select done payslips with journal entries."))

        moves = payslips.mapped("move_id")
        move_ids = moves.ids
        # Calculate total net amount - ensure it's always positive for outbound payments
        total_net_amount = abs(sum(payslips.mapped("net_wage")))
        
        # Get payable/receivable line IDs from the moves for Odoo 19 compatibility
        # In Odoo 19, payment registration wizard may need line IDs instead of move IDs
        # Include expense and liability in initial filter, but payment wizard will only process payable/receivable
        line_ids = moves.mapped("line_ids").filtered(
            lambda l: l.account_id.internal_group in ('liability', 'expense', 'payable', 'receivable') and not l.reconciled
        ).ids

        
        if not line_ids:
            raise UserError(_("No payable/receivable lines found to pay. Please check if the journal entries are properly configured."))

        return {
            "type": "ir.actions.act_window",
            "name": _("Register Payroll Payments"),
            "res_model": "account.payment.register",
            "view_mode": "form",
            "target": "new",
            "context": {
                "active_model": "account.move.line",
                "active_ids": line_ids,
                "default_amount": total_net_amount,
                "skip_account_move_synchronization": True,
                "disable_auto_reconcile": True,
                "allowed_company_ids": self.env.companies.ids,
                # CRITICAL: Store original selected payslip IDs to process only these
                "selected_payslip_ids": payslips.ids,
            },
        }
