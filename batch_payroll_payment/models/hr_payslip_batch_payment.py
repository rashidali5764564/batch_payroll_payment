from odoo import models, _
from odoo.exceptions import UserError


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    def action_open_batch_payment_wizard(self):
        payslips = self.filtered(lambda p: p.state == "done" and p.move_id)

        if not payslips:
            raise UserError(_("Please select done payslips with journal entries."))

        move_ids = payslips.mapped("move_id").ids
        total_net_amount = sum(payslips.mapped("net_wage"))

        return {
            "type": "ir.actions.act_window",
            "name": _("Register Payroll Payments"),
            "res_model": "account.payment.register",
            "view_mode": "form",
            "target": "new",
            "context": {
                "active_model": "account.move",
                "active_ids": move_ids,
                "default_amount": total_net_amount,
                "skip_account_move_synchronization": True,
                "disable_auto_reconcile": True,
                "allowed_company_ids": self.env.companies.ids,
            },
        }


class HrPayslipRun(models.Model):
    _inherit = "hr.payslip.run"

    def action_open_batch_payment_wizard(self):
        """
        Open payment wizard for all payslips in the selected batch(es).
        This method collects all done payslips with journal entries from
        the selected payslip batch(es) and opens the payment register wizard.
        """
        # Get all payslips from selected batch(es)
        payslips = self.mapped("slip_ids").filtered(
            lambda p: p.state == "done" and p.move_id
        )

        if not payslips:
            raise UserError(
                _("No done payslips with journal entries found in the selected batch(es).")
            )

        move_ids = payslips.mapped("move_id").ids
        total_net_amount = sum(payslips.mapped("net_wage"))
        # Pass payslip_run_ids in context to identify that payment is from batch
        payslip_run_ids = self.ids

        return {
            "type": "ir.actions.act_window",
            "name": _("Register Payroll Payments"),
            "res_model": "account.payment.register",
            "view_mode": "form",
            "target": "new",
            "context": {
                "active_model": "account.move",
                "active_ids": move_ids,
                "default_amount": total_net_amount,
                "skip_account_move_synchronization": True,
                "disable_auto_reconcile": True,
                "allowed_company_ids": self.env.companies.ids,
                "payslip_run_ids": payslip_run_ids,  # To identify payment from batch
            },
        }