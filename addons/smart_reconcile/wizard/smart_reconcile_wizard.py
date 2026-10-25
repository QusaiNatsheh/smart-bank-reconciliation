from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError


class SmartReconcileWizard(models.TransientModel):
    _name = "smart.reconcile.wizard"
    _description = "Smart Reconciliation Suggestions"

    statement_line_id = fields.Many2one("account.bank.statement.line", required=True, ondelete="cascade")
    currency_id = fields.Many2one(related="statement_line_id.currency_id")
    amount = fields.Monetary(related="statement_line_id.amount")
    payment_ref = fields.Char(related="statement_line_id.payment_ref")
    partner_name = fields.Char(related="statement_line_id.partner_name")
    request_id = fields.Char()
    model_version = fields.Char()
    threshold = fields.Float(digits=(3, 2))
    suggestion_ids = fields.One2many("smart.reconcile.suggestion", "wizard_id")


class SmartReconcileSuggestion(models.TransientModel):
    _name = "smart.reconcile.suggestion"
    _description = "Smart Reconciliation Suggestion"
    _order = "rank"

    wizard_id = fields.Many2one("smart.reconcile.wizard", required=True, ondelete="cascade")
    rank = fields.Integer()
    invoice_ids = fields.Many2many("account.move", string="Invoices")
    partner_id = fields.Many2one("res.partner", compute="_compute_totals")
    currency_id = fields.Many2one(related="wizard_id.currency_id")
    amount_residual = fields.Monetary(string="Open Amount", compute="_compute_totals")
    score = fields.Float(digits=(6, 3))
    confidence = fields.Float(digits=(3, 2))
    low_confidence = fields.Boolean(compute="_compute_low_confidence")
    reasons = fields.Text()

    @api.depends("invoice_ids")
    def _compute_totals(self):
        for s in self:
            s.amount_residual = sum(s.invoice_ids.mapped("amount_residual"))
            s.partner_id = s.invoice_ids.commercial_partner_id[:1]

    @api.depends("confidence", "wizard_id.threshold", "rank")
    def _compute_low_confidence(self):
        for s in self:
            s.low_confidence = s.rank != 1 or s.confidence < s.wizard_id.threshold

    def _record_feedback(self, accepted):
        wizard = self.wizard_id
        feedback = self.env["smart.reconcile.feedback"].create(
            {
                "statement_line_id": wizard.statement_line_id.id,
                "invoice_ids": [(6, 0, self.invoice_ids.ids)],
                "accepted": accepted,
                "confidence": self.confidence,
                "rank": self.rank,
                "request_id": wizard.request_id,
                "model_version": wizard.model_version,
            }
        )
        feedback._send()

    def action_accept(self):
        self.ensure_one()
        if not self.invoice_ids:
            raise UserError(self.env._("This suggestion has no invoices."))
        # Invoicing users register and reconcile customer payments in standard Odoo, but changing a bank
        # statement line's journal items needs the "Basic" accounting group, which Community admins often lack.
        # So: check the user's right explicitly, then run only the reconciliation itself with elevated rights.
        if not self.env.user.has_group("account.group_account_invoice"):
            raise AccessError(self.env._("Only Invoicing users can reconcile bank lines."))
        line = self.wizard_id.statement_line_id
        line.sudo()._smart_reconcile_apply(self.invoice_ids.sudo())
        self._record_feedback(accepted=True)
        return {"type": "ir.actions.act_window_close"}

    def action_reject(self):
        self.ensure_one()
        wizard = self.wizard_id
        self._record_feedback(accepted=False)
        self.unlink()
        return {
            "type": "ir.actions.act_window",
            "res_model": "smart.reconcile.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
            "context": {"dialog_size": "extra-large"},
        }
