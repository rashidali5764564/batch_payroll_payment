from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import timedelta


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    is_payroll_payment = fields.Boolean(
        string='Is Payroll Payment',
        help='True if this payment is for payroll payslips', default=True
    )

    @api.model
    def default_get(self, fields_list):
        """Set is_payroll_payment when wizard opens"""
        # Get active_ids from context BEFORE calling super
        original_active_ids = self.env.context.get("active_ids", [])
        active_model = self.env.context.get("active_model", "")
        
        # Store original active_ids for later use
        active_ids = original_active_ids
        
        # If we have line IDs, try to filter but don't fail if parent rejects them
        if active_model == "account.move.line" and active_ids:
            lines = self.env["account.move.line"].browse(active_ids)
            # Filter to liability/expense/payable/receivable AND ensure they're not reconciled
            valid_lines = lines.filtered(
                lambda l: l.account_id.internal_group in ('liability', 'expense', 'payable', 'receivable') and not l.reconciled
            )
            
            # Try to call parent with filtered lines, but if it fails, use original lines
            try:
                if valid_lines:
                    # Try with payable/receivable first (parent's requirement)
                    payable_receivable_lines = valid_lines.filtered(
                        lambda l: l.account_id.internal_group in ('liability', 'expense', 'payable', 'receivable')
                    )
                    if payable_receivable_lines:
                        active_ids = payable_receivable_lines.ids
                        self = self.with_context(active_ids=active_ids)
                    else:
                        # No payable/receivable, try with all valid lines
                        active_ids = valid_lines.ids
                        self = self.with_context(active_ids=active_ids)
                else:
                    # No valid lines, use original but set empty
                    active_ids = []
                    self = self.with_context(active_ids=active_ids)
                
                # Try calling parent's default_get
                res = super().default_get(fields_list)
                # Restore original active_ids for our logic (use original for payslip detection)
                active_ids = original_active_ids
            except Exception:
                # If parent fails, create default response with journal and payment method
                res = {}
                # Set default journal (first bank journal or first journal)
                journal = self.env['account.journal'].search([
                    ('type', 'in', ['bank', 'cash']),
                    ('company_id', '=', self.env.company.id)
                ], limit=1)
                if not journal:
                    journal = self.env['account.journal'].search([
                        ('company_id', '=', self.env.company.id)
                    ], limit=1)
                if journal:
                    res['journal_id'] = journal.id
                
                # Set default payment method line from journal (outbound for paying employees)
                if journal:
                    # Get outbound payment method line from journal
                    payment_method_line = journal.outbound_payment_method_line_ids[:1]
                    if payment_method_line:
                        res['payment_method_line_id'] = payment_method_line.id
                
                # Set amount from context if available - ensure it's always positive
                if 'default_amount' in self.env.context:
                    amount = self.env.context.get('default_amount', 0)
                    res['amount'] = abs(amount) if amount else 0
                
                # Restore original active_ids for our logic
                active_ids = original_active_ids
        else:
            # No active_model or active_ids, call parent normally
            res = super().default_get(fields_list)

        if active_ids and active_model:
            # Handle both account.move and account.move.line models
            if active_model == "account.move.line":
                # Get moves from line IDs
                lines = self.env["account.move.line"].browse(active_ids)
                move_ids = lines.mapped("move_id").ids
            elif active_model == "account.move":
                # active_ids are move IDs
                move_ids = active_ids
            else:
                move_ids = []

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
        else:
            res['is_payroll_payment'] = False

        return res

    # def _init_payments(self, to_process, edit_mode=False):
    #     """Override to set wizard's currency in payment creation values"""
    #     # Get wizard values from context (set in action_create_payments)
    #     wizard_currency_id = self.env.context.get('wizard_currency_id', False)
    #
    #     # Modify payment creation values to include wizard's currency
    #     if wizard_currency_id:
    #         for payment_vals in to_process:
    #             create_vals = payment_vals.get('create_vals', {})
    #             if wizard_currency_id:
    #                 create_vals['currency_id'] = wizard_currency_id
    #             payment_vals['create_vals'] = create_vals
    #
    #     # Call parent to create payments with modified values
    #     return super()._init_payments(to_process, edit_mode=edit_mode)

    def action_create_payments(self):
        """
        Override to add validation checks:
        1. Check if payslip journal entries are posted
        2. Check if payslips are already paid
        3. Close wizard and show success message after payment
        """
        active_ids = self.env.context.get("active_ids", [])
        active_model = self.env.context.get("active_model", "")

        if not active_ids:
            raise UserError(_("No moves selected for payment."))

        # Handle both account.move and account.move.line models
        if active_model == "account.move.line":
            # Get moves from line IDs - ensure unique move IDs
            lines = self.env["account.move.line"].browse(active_ids)
            move_ids = list(set(lines.mapped("move_id").ids))  # Ensure unique
        elif active_model == "account.move":
            # active_ids are move IDs
            move_ids = list(set(active_ids))  # Ensure unique
        else:
            move_ids = list(set(active_ids))  # Fallback, ensure unique

        if not move_ids:
            raise UserError(_("No moves found for payment."))

        # CRITICAL: Get ONLY the originally selected payslips from context
        # This ensures we process only the payslips user selected, not all payslips with same moves
        selected_payslip_ids = self.env.context.get("selected_payslip_ids", [])
        
        if selected_payslip_ids:
            # Use only the originally selected payslips
            payslips = self.env["hr.payslip"].browse(selected_payslip_ids)
            # Verify these payslips have the correct move_ids and are validated (security check)
            payslips = payslips.filtered(
                lambda p: p.move_id and p.move_id.id in move_ids and p.state == "validated"
            )
        else:
            # Fallback: If no selected payslip IDs in context, search by move_ids
            # (for backward compatibility or non-payroll payments)
            payslips = self.env["hr.payslip"].search([
                ("move_id", "in", move_ids),
            ])

        if not payslips:
            # If no payslips found, proceed with standard flow
            # Update context to use move IDs instead of line IDs to prevent duplicates
            if active_model == "account.move.line":
                self = self.with_context(
                    active_model="account.move",
                    active_ids=move_ids
                )
            return super().action_create_payments()

        # -----------------------------------------
        # 1️⃣ Check if payments already exist for these moves
        # -----------------------------------------
        moves = self.env["account.move"].browse(move_ids)
        move_lines = moves.mapped("line_ids")

        # Check if any move line is already reconciled (payment already done)
        reconciled_lines = move_lines.filtered(lambda l: l.reconciled)
        if reconciled_lines:
            # Get payslips that are already paid
            already_paid = payslips.filtered(lambda p: p.state == "paid")
            if not already_paid:
                # If payslip state not updated but payment exists, check payments
                # Get payment moves from reconciled lines
                payment_moves = reconciled_lines.mapped("matched_debit_ids.debit_move_id.move_id") | \
                                reconciled_lines.mapped("matched_credit_ids.credit_move_id.move_id")
                # Check if any of these moves are payment moves (by checking if they have payment_id via origin_payment_id or payment_id field)
                # Actually, if lines are reconciled, payment already exists
                if payment_moves:
                    # Check if payments exist for these moves
                    payments = self.env["account.payment"].search([
                        ("move_id", "in", payment_moves.ids),
                    ], limit=1)
                    if payments:
                        paid_names = ", ".join(payslips.mapped("name")[:5])
                        if len(payslips) > 5:
                            paid_names += f" and {len(payslips) - 5} more"
                        raise UserError(_(
                            "Payment already done for the following payslips:\n\n%s\n\n"
                            "You cannot create payment again for paid payslips."
                        ) % paid_names)
            else:
                paid_names = ", ".join(already_paid.mapped("name")[:5])
                if len(already_paid) > 5:
                    paid_names += f" and {len(already_paid) - 5} more"
                raise UserError(_(
                    "Payment already done for the following payslips:\n\n%s\n\n"
                    "You cannot create payment again for paid payslips."
                ) % paid_names)

        # Also check payslip state
        already_paid_slips = payslips.filtered(lambda p: p.state == "paid")
        if already_paid_slips:
            paid_names = ", ".join(already_paid_slips.mapped("name")[:5])
            if len(already_paid_slips) > 5:
                paid_names += f" and {len(already_paid_slips) - 5} more"
            raise UserError(_(
                "Payment already done for the following payslips:\n\n%s\n\n"
                "You cannot create payment again for paid payslips."
            ) % paid_names)

        # -----------------------------------------
        # 2️⃣ Check if journal entries are posted
        # -----------------------------------------
        draft_slips = payslips.filtered(
            lambda p: not p.move_id or p.move_id.state != "posted"
        )
        if draft_slips:
            # draft_names = ", ".join(draft_slips.mapped("name")[:5])
            # if len(draft_slips) > 5:
            # draft_names += f" and {len(draft_slips) - 5} more"
            raise UserError(_(
                "The following payslips have journal entries that are not posted:"
                "Please post all payslip journal entries before creating payments."
            ))

        # -----------------------------------------
        # 2.5️⃣ Store wizard currency for payment creation
        # -----------------------------------------
        # Store wizard's currency to apply to payments and their journal entries
        wizard_currency_id = self.currency_id.id if self.currency_id else False

        # For payment JV, line_currency_id should match wizard value
        wizard_line_currency_id = wizard_currency_id

        # -----------------------------------------
        # 3️⃣ Create payments using standard flow
        # -----------------------------------------
        # CRITICAL: Update context to use move IDs instead of line IDs
        # This prevents duplicate payments when multiple lines from same move are selected
        # Store wizard values in context so they can be used during payment creation
        self = self.with_context(
            active_model="account.move",
            active_ids=move_ids,  # Use move IDs, not line IDs
            wizard_currency_id=wizard_currency_id,
            wizard_line_currency_id=wizard_line_currency_id,
        )
        result = super().action_create_payments()

        # -----------------------------------------
        # 4️⃣ Mark payslips as PAID (CRITICAL - must happen immediately)
        # -----------------------------------------
        # Update payslip state to paid - this is critical and must happen
        # Payment was created successfully, so mark payslips as paid
        payslips.write({"state": "paid"})

        # -----------------------------------------
        # 5️⃣ Fetch created payments for reference handling and rate update
        # -----------------------------------------
        # Get payments from move lines that are now reconciled
        moves = self.env["account.move"].browse(move_ids)
        move_lines = moves.mapped("line_ids").filtered(
            lambda l: l.account_id.internal_group in ('payable', 'receivable'))

        # Find payments that reconciled with these move lines
        payments = self.env["account.payment"]
        for line in move_lines:
            # Get reconciled payments from matched lines
            matched_payments = line.matched_debit_ids.mapped("debit_move_id.move_id.payment_id") | \
                               line.matched_credit_ids.mapped("credit_move_id.move_id.payment_id")
            payments |= matched_payments

        # Fallback: If no payments found via reconciliation, search by recent creation
        if not payments:
            payments = self.env["account.payment"].search([
                ("create_date", ">=", fields.Datetime.now() - timedelta(seconds=30)),
                ("state", "in", ["draft", "posted"]),
            ]).filtered(lambda p: any(aml.move_id.id in move_ids for aml in p.move_id.line_ids if aml.reconciled))

        # -----------------------------------------
        # 5.5️⃣ Apply wizard currency to payments (moves already created with correct values)
        # -----------------------------------------
        # NOTE: Payment moves are created with correct values via _init_payments override
        # and _generate_journal_entry in account_payment.py
        # Only update payments if needed (moves should already have correct values)
        if payments and wizard_currency_id:
            # Update payments with wizard's currency (if not already set)
            payment_vals = {}
            if wizard_currency_id:
                payment_vals['currency_id'] = wizard_currency_id

            if payment_vals:
                payments.write(payment_vals)

            # Update payment journal entries (moves) ONLY if they are draft (not posted)
            # Posted moves cannot be modified, so values must be set during creation
            for payment in payments:
                if payment.move_id and payment.move_id.state == 'draft':
                    move_vals = {}
                    # Set line_currency_id if not already set
                    if wizard_line_currency_id and not payment.move_id.line_currency_id:
                        move_vals['line_currency_id'] = wizard_line_currency_id

                    if move_vals:
                        payment.move_id.write(move_vals)

                    # Set employee_id on payment JV from payslip JV
                    # Find payslip move that this payment is paying
                    payslip_move = None
                    if payment.reconciled_invoice_ids:
                        for reconciled_move in payment.reconciled_invoice_ids:
                            if reconciled_move.id in move_ids:
                                payslip_move = reconciled_move
                                break

                    # If not found via reconciliation, find by matching partner
                    if not payslip_move:
                        for slip in payslips:
                            if slip.move_id and slip.move_id.id in move_ids:
                                if slip.move_id.partner_id == payment.partner_id:
                                    payslip_move = slip.move_id
                                    break
        # -----------------------------------------
        # 6️⃣ Reference handling
        # -----------------------------------------
        if payments and self.group_payment:
            batch_name = ", ".join(
                sorted(set(payslips.mapped("batch_name")))
            ) or _("Payroll Batch Payment")
            payments.write({"ref": batch_name})
        elif payments:
            for pay in payments:
                # Find payslip by matching move lines
                pay_move_lines = pay.move_id.line_ids.filtered(
                    lambda l: l.account_id.internal_group in ('payable', 'receivable')
                )
                for pay_line in pay_move_lines:
                    slip = payslips.filtered(
                        lambda p: p.move_id and any(
                            slip_line.id in pay_line.matched_debit_ids.mapped("credit_move_id.id") or
                            slip_line.id in pay_line.matched_credit_ids.mapped("debit_move_id.id")
                            for slip_line in p.move_id.line_ids
                        )
                    )
                    if slip:
                        pay.ref = slip[0].display_name
                        break

        # -----------------------------------------
        # 7️⃣ Close wizard + success message
        # -----------------------------------------
        # Show success notification and close wizard
        # Return action that shows notification
        # Note: Wizard will be closed by JavaScript in the view template
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Success"),
                "message": _("Payments done successfully."),
                "type": "success",
                "sticky": False,
            },
        }
