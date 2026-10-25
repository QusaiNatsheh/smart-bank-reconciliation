import logging

import requests

from odoo import Command, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

SERVICE_TIMEOUT = 10
MAX_OPEN_INVOICES = 2000
HISTORY_INVOICES = 500


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    smart_reconcile_feedback_ids = fields.One2many("smart.reconcile.feedback", "statement_line_id")

    def _smart_reconcile_service_url(self):
        url = self.env["ir.config_parameter"].sudo().get_str("smart_reconcile.service_url")
        return (url or "http://ml:8000").rstrip("/")

    # ------------------------------------------------------------------ payload
    def _smart_reconcile_open_invoices(self):
        """Posted customer invoices of the line's company that are still open on the line date."""
        self.ensure_one()
        return self.env["account.move"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("move_type", "=", "out_invoice"),
                ("state", "=", "posted"),
                ("payment_state", "in", ("not_paid", "partial")),
                ("invoice_date", "<=", self.date),
                ("amount_residual", ">", 0),
            ],
            order="invoice_date desc, id desc",
            limit=MAX_OPEN_INVOICES,
        )

    def _smart_reconcile_partner_history(self, partners):
        """Average days from invoice date to full payment, over each partner's recent paid invoices."""
        paid = self.env["account.move"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("move_type", "=", "out_invoice"),
                ("payment_state", "in", ("paid", "in_payment")),
                ("commercial_partner_id", "in", partners.ids),
            ],
            order="invoice_date desc",
            limit=HISTORY_INVOICES,
        )
        days = {}
        for move in paid:
            receivable = move.line_ids.filtered(lambda aml: aml.account_type == "asset_receivable")
            dates = receivable.matched_credit_ids.mapped("max_date")
            if dates and move.invoice_date:
                days.setdefault(move.commercial_partner_id.id, []).append((max(dates) - move.invoice_date).days)
        return {pid: sum(v[:20]) / len(v[:20]) for pid, v in days.items()}

    def _smart_reconcile_payload(self, invoices):
        self.ensure_one()
        history = self._smart_reconcile_partner_history(invoices.commercial_partner_id)
        return {
            "line": {
                "amount": self.amount,
                "date": fields.Date.to_string(self.date),
                "payment_ref": self.payment_ref or "",
                "partner_name": self.partner_name or self.partner_id.name or "",
                "currency": self.currency_id.name,
            },
            "invoices": [
                {
                    "id": inv.id,
                    "number": inv.name,
                    "partner_id": inv.commercial_partner_id.id,
                    "partner_names": [
                        n
                        for n in (inv.commercial_partner_id.name, inv.commercial_partner_id.smart_reconcile_alt_name)
                        if n
                    ],
                    "invoice_date": fields.Date.to_string(inv.invoice_date),
                    "due_date": fields.Date.to_string(inv.invoice_date_due or inv.invoice_date),
                    "amount_residual": inv.amount_residual,
                    "partner_avg_days": history.get(inv.commercial_partner_id.id),
                }
                for inv in invoices
            ],
            "top_k": 3,
        }

    def _smart_reconcile_call_service(self, payload):
        url = self._smart_reconcile_service_url()
        try:
            response = requests.post(f"{url}/suggest", json=payload, timeout=SERVICE_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            _logger.warning("Smart reconciliation service error: %s", exc)
            raise UserError(
                self.env._(
                    "The matching service at %(url)s is not available. You can still reconcile this line manually.",
                    url=url,
                )
            ) from exc

    # ------------------------------------------------------------------ actions
    def action_smart_suggest(self):
        self.ensure_one()
        if self.is_reconciled:
            raise UserError(self.env._("This bank line is already reconciled."))
        if self.amount <= 0:
            raise UserError(self.env._("Suggestions are only available for incoming payments."))
        if self.currency_id != self.company_id.currency_id or self.foreign_currency_id:
            raise UserError(self.env._("Suggestions are only available for lines in the company currency."))
        invoices = self._smart_reconcile_open_invoices()
        result = self._smart_reconcile_call_service(self._smart_reconcile_payload(invoices))
        threshold = self.env["ir.config_parameter"].sudo().get_float("smart_reconcile.threshold") or 0.8
        valid_ids = set(invoices.ids)
        wizard = self.env["smart.reconcile.wizard"].create(
            {
                "statement_line_id": self.id,
                "request_id": result.get("request_id"),
                "model_version": result.get("model_version"),
                "threshold": threshold,
                "suggestion_ids": [
                    Command.create(
                        {
                            "rank": rank,
                            "invoice_ids": [Command.set([i for i in s["invoice_ids"] if i in valid_ids])],
                            "score": s["score"],
                            "confidence": s["confidence"],
                            "reasons": "\n".join(s.get("reasons") or []),
                        }
                    )
                    for rank, s in enumerate(result.get("suggestions", []), start=1)
                    if set(s["invoice_ids"]) <= valid_ids
                ],
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Match Suggestions"),
            "res_model": "smart.reconcile.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
            "context": {"dialog_size": "extra-large"},
        }

    def _smart_reconcile_apply(self, invoices):
        """Reconcile this line with the given invoices, oldest first.

        The suspense line of the statement entry is replaced by one receivable line per invoice. Any amount
        left over stays on the suspense account. If the line is smaller than the invoices, the last invoice
        stays partly open.
        """
        self.ensure_one()
        _liquidity, suspense, other = self.with_context(skip_account_move_synchronization=True)._seek_for_lines()
        if other or len(suspense) != 1:
            raise UserError(self.env._("This bank line is already partly reconciled."))
        if any(inv.company_id != self.company_id or inv.move_type != "out_invoice" for inv in invoices):
            raise UserError(self.env._("Only customer invoices of the same company can be matched."))

        currency = self.company_id.currency_id
        left = -suspense.balance  # what the entry actually holds, already rounded to the currency
        to_reconcile = []
        commands = []
        for inv in invoices.sorted(lambda m: (m.invoice_date, m.id)):
            if currency.compare_amounts(left, 0) <= 0:
                break
            receivable = inv.line_ids.filtered(
                lambda aml: aml.account_type == "asset_receivable" and not aml.reconciled
            )
            if not receivable:
                continue
            allocated = min(left, inv.amount_residual)
            left = currency.round(left - allocated)
            commands.append(
                Command.create(
                    {
                        "name": inv.name,
                        "account_id": receivable[0].account_id.id,
                        "partner_id": inv.commercial_partner_id.id,
                        "balance": -allocated,
                        "amount_currency": -allocated,
                        "currency_id": currency.id,
                    }
                )
            )
            to_reconcile.append(receivable)
        if not commands:
            raise UserError(self.env._("The selected invoices have nothing left to pay."))
        if currency.is_zero(left):
            commands.append(Command.unlink(suspense.id))
        else:
            commands.append(Command.update(suspense.id, {"balance": -left, "amount_currency": -left}))

        move = self.move_id.with_context(skip_account_move_synchronization=True)
        move.button_draft()
        move.write({"line_ids": commands})
        move.action_post()
        partner = invoices.commercial_partner_id[:1]
        if partner and not self.partner_id:
            self.with_context(skip_account_move_synchronization=True).partner_id = partner
        new_lines = move.line_ids.filtered(lambda aml: aml.account_type == "asset_receivable" and not aml.reconciled)
        for receivable in to_reconcile:
            counterpart = new_lines.filtered(
                lambda aml, r=receivable: (
                    aml.account_id == r.account_id
                    and aml.partner_id == r.partner_id.commercial_partner_id
                    and aml.name == r.move_id.name
                )
            )
            (counterpart + receivable).reconcile()
