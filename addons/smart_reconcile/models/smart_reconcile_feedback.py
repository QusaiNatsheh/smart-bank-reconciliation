import logging

import requests

from odoo import fields, models

_logger = logging.getLogger(__name__)


class SmartReconcileFeedback(models.Model):
    _name = "smart.reconcile.feedback"
    _description = "Smart Reconciliation Feedback"
    _order = "id desc"

    statement_line_id = fields.Many2one("account.bank.statement.line", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="statement_line_id.company_id", store=True)
    invoice_ids = fields.Many2many("account.move", string="Invoices")
    accepted = fields.Boolean()
    confidence = fields.Float(digits=(3, 2))
    rank = fields.Integer()
    request_id = fields.Char(readonly=True)
    model_version = fields.Char(readonly=True)
    sent = fields.Boolean(string="Sent to Service", readonly=True)

    def _send(self):
        """Send feedback to the ML service. Failures are logged and retried by the cron job."""
        url = self.env["account.bank.statement.line"]._smart_reconcile_service_url()
        for record in self.filtered(lambda r: not r.sent and r.request_id):
            payload = {
                "request_id": record.request_id,
                "invoice_ids": sorted(record.invoice_ids.ids),
                "accepted": record.accepted,
            }
            try:
                response = requests.post(f"{url}/feedback", json=payload, timeout=5)
                response.raise_for_status()
                record.sudo().sent = True  # internal bookkeeping; users only create feedback
            except requests.RequestException as exc:
                _logger.warning("Smart reconciliation feedback not sent: %s", exc)
                break

    def _cron_send_pending(self):
        self.search([("sent", "=", False), ("request_id", "!=", False)], limit=500)._send()
