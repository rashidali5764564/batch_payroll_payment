from odoo import models, fields, api, _
from odoo.exceptions import UserError


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    is_payroll_payment = fields.Boolean(
        string='Is Payroll Payment',
        help='True if this payment is for payroll payslips'
    )

    @api.model
    def default_get(self, fields_list):
        """Set is_payroll_payment when wizard opens"""
        res = super().default_get(fields_list)
        
        # Get move IDs from context
        move_ids = self.env.context.get("active_ids", [])
        
        if move_ids:
            # Check if any move is related to payslip
            payslips = self.env["hr.payslip"].search([
                ("move_id", "in", move_ids),
            ], limit=1)
            
            if payslips:
                # This is a payroll payment
                res['is_payroll_payment'] = True
            else:
                # This is not a payroll payment
                res['is_payroll_payment'] = False
        else:
            res['is_payroll_payment'] = False
        
        return res

    def action_create_payments(self):
        """
        Override to add validation checks:
        1. Check if payslip journal entries are posted
        2. Check if payslips are already paid
        3. Close wizard and show success message after payment
        Optimized for large batches (3000+ payslips)
        """
        move_ids = self.env.context.get("active_ids", [])

        if not move_ids:
            raise UserError(_("No moves selected for payment."))

        # Get payslips related to selected moves - use SQL for speed
        payslips = self.env["hr.payslip"].search([
            ("move_id", "in", move_ids),
        ])

        if not payslips:
            # If no payslips found, proceed with standard flow
            return super().action_create_payments()

        # Store counts for message
        payslip_count = len(payslips)
        payslip_run_ids = self.env.context.get("payslip_run_ids", [])

        # -----------------------------------------
        # 1️⃣ Fast validation - check payslip state only (skip complex reconciliation)
        # -----------------------------------------
        # Use read() for faster access instead of filtered
        payslip_states = payslips.read(["state", "name", "move_id"])
        already_paid_slips_data = [p for p in payslip_states if p["state"] == "paid"]
        
        if already_paid_slips_data:
            paid_names = ", ".join([p["name"] for p in already_paid_slips_data[:5]])
            if len(already_paid_slips_data) > 5:
                paid_names += f" and {len(already_paid_slips_data) - 5} more"
            raise UserError(_(
                "Payment already done for the following payslips:\n\n%s\n\n"
                "You cannot create payment again for paid payslips."
            ) % paid_names)

        # -----------------------------------------
        # 2️⃣ Fast check if journal entries are posted
        # -----------------------------------------
        # Use read() to get move states efficiently
        move_ids_list = [p["move_id"][0] for p in payslip_states if p.get("move_id")]
        if move_ids_list:
            moves = self.env["account.move"].browse(move_ids_list)
            move_states = moves.read(["state", "id"])
            draft_moves = {m["id"]: m["state"] for m in move_states if m["state"] != "posted"}
            
            if draft_moves:
                # Find payslips with draft moves
                draft_slips_data = [
                    p for p in payslip_states 
                    if p.get("move_id") and p["move_id"][0] in draft_moves
                ]
                draft_names = ", ".join([p["name"] for p in draft_slips_data[:5]])
                if len(draft_slips_data) > 5:
                    draft_names += f" and {len(draft_slips_data) - 5} more"
                raise UserError(_(
                    "The following payslips have journal entries that are not posted:\n\n%s\n\n"
                    "Please post all payslip journal entries before creating payments."
                ) % draft_names)

        # -----------------------------------------
        # 3️⃣ Create payments using standard flow
        # -----------------------------------------
        result = super().action_create_payments()

        # -----------------------------------------
        # 4️⃣ Mark payslips as PAID (BULK UPDATE - FAST)
        # -----------------------------------------
        # Use SQL for bulk update - much faster than ORM write()
        if payslips:
            payslip_ids = payslips.ids
            if payslip_ids:
                # Use tuple for IN clause - faster than ORM
                self.env.cr.execute(
                    "UPDATE hr_payslip SET state = 'paid' WHERE id IN %s",
                    (tuple(payslip_ids),)
                )
                # Invalidate cache to reflect changes
                payslips.invalidate_recordset(["state"])
        
        # -----------------------------------------
        # 4.5️⃣ Mark payslip runs as PAID if payment is from batch (OPTIMIZED)
        # -----------------------------------------
        if payslip_run_ids:
            # Use SQL to check and update batch states efficiently
            payslip_runs = self.env["hr.payslip.run"].browse(payslip_run_ids)
            
            # Get state field info once
            state_field = payslip_runs._fields.get("state") if payslip_runs else None
            has_paid_state = False
            has_close_state = False
            if state_field and hasattr(state_field, "selection"):
                # selection can be a list or a callable
                if callable(state_field.selection):
                    selection_list = state_field.selection(payslip_runs[0] if payslip_runs else None)
                else:
                    selection_list = state_field.selection
                state_values = [val[0] for val in selection_list] if selection_list else []
                has_paid_state = "paid" in state_values
                has_close_state = "close" in state_values
            
            # Use SQL to check which batches have all payslips paid - batch update for speed
            if payslip_runs:
                run_ids = payslip_runs.ids
                # Single SQL query to check all batches at once
                self.env.cr.execute("""
                    SELECT 
                        payslip_run_id,
                        COUNT(*) as total,
                        COUNT(*) FILTER (WHERE state = 'paid') as paid_count
                    FROM hr_payslip
                    WHERE payslip_run_id IN %s
                    GROUP BY payslip_run_id
                """, (tuple(run_ids),))
                results = self.env.cr.dictfetchall()
                
                # Update batches that have all payslips paid
                target_state = "paid" if has_paid_state else ("close" if has_close_state else None)
                if target_state:
                    batches_to_update = [
                        r["payslip_run_id"] 
                        for r in results 
                        if r["total"] > 0 and r["total"] == r["paid_count"]
                    ]
                    if batches_to_update:
                        self.env.cr.execute(
                            "UPDATE hr_payslip_run SET state = %s WHERE id IN %s",
                            (target_state, tuple(batches_to_update))
                        )
                        # Invalidate cache
                        self.env["hr.payslip.run"].browse(batches_to_update).invalidate_recordset(["state"])

        # -----------------------------------------
        # 5️⃣ Success message (return immediately - no slow operations)
        # -----------------------------------------
        if payslip_run_ids:
            batch_count = len(payslip_run_ids)
            message = _(
                "Payments created successfully for %(payslip_count)d payslip(s) "
                "from %(batch_count)d batch(es). All payslips and batches have been marked as paid."
            ) % {
                "payslip_count": payslip_count,
                "batch_count": batch_count,
            }
        else:
            message = _(
                "Payments created successfully for %(payslip_count)d payslip(s). "
                "All payslips have been marked as paid."
            ) % {
                "payslip_count": payslip_count,
            }
        
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Success"),
                "message": message,
                "type": "success",
                "sticky": False,
            },
        }
