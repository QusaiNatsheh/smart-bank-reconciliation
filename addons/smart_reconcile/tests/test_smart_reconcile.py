from unittest.mock import MagicMock, patch

import requests

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

REQUESTS_POST = "odoo.addons.smart_reconcile.models.account_bank_statement_line.requests.post"
FEEDBACK_POST = "odoo.addons.smart_reconcile.models.smart_reconcile_feedback.requests.post"


def _response(payload):
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


@tagged("post_install", "-at_install")
class TestSmartReconcile(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner_a.smart_reconcile_alt_name = "شركة النور للتجارة"
        cls.inv_1 = cls._make_invoice(100.0, "2026-01-05")
        cls.inv_2 = cls._make_invoice(250.0, "2026-01-20")
        cls.inv_3 = cls._make_invoice(400.0, "2026-01-25")
        cls.bank_journal = cls.company_data["default_journal_bank"]

    @classmethod
    def _make_invoice(cls, amount, invoice_date):
        return cls._create_invoice(
            partner_id=cls.partner_a,
            invoice_date=invoice_date,
            invoice_line_ids=[Command.create({"name": "Service", "quantity": 1, "price_unit": amount, "tax_ids": []})],
            post=True,
        )

    def _line(self, amount, ref="Payment"):
        return self.env["account.bank.statement.line"].create(
            {
                "journal_id": self.bank_journal.id,
                "date": "2026-03-01",
                "amount": amount,
                "payment_ref": ref,
                "partner_name": "ALNOOR TRADING",
            }
        )

    def _suggest(self, line, suggestions):
        payload = {"request_id": "abc123", "model_version": "test", "suggestions": suggestions}
        with patch(REQUESTS_POST, return_value=_response(payload)) as post:
            action = line.action_smart_suggest()
        return self.env["smart.reconcile.wizard"].browse(action["res_id"]), post

    def test_payload_contains_open_invoices_and_alt_name(self):
        line = self._line(350.0)
        _wizard, post = self._suggest(line, [])
        sent = post.call_args.kwargs["json"]
        self.assertEqual(sent["line"]["amount"], 350.0)
        sent_ids = {i["id"] for i in sent["invoices"]}
        self.assertTrue({self.inv_1.id, self.inv_2.id, self.inv_3.id} <= sent_ids)
        names = next(i["partner_names"] for i in sent["invoices"] if i["id"] == self.inv_1.id)
        self.assertIn("شركة النور للتجارة", names)
        self.assertEqual(post.call_args.kwargs["timeout"], 10)

    def test_accept_grouped_suggestion_reconciles_all_invoices(self):
        line = self._line(350.0)
        wizard, _post = self._suggest(
            line,
            [
                {
                    "invoice_ids": [self.inv_1.id, self.inv_2.id],
                    "score": 5.0,
                    "confidence": 0.95,
                    "reasons": ["Reference contains the invoice number"],
                },
                {"invoice_ids": [self.inv_3.id], "score": 1.0, "confidence": 0.0, "reasons": []},
            ],
        )
        self.assertEqual(len(wizard.suggestion_ids), 2)
        top = wizard.suggestion_ids.filtered(lambda s: s.rank == 1)
        self.assertFalse(top.low_confidence)
        with patch(FEEDBACK_POST, return_value=_response({"status": "recorded"})) as fb_post:
            top.action_accept()
        self.assertTrue(line.is_reconciled)
        self.assertEqual(self.inv_1.payment_state, self.inv_1._get_invoice_in_payment_state())
        self.assertEqual(self.inv_2.payment_state, self.inv_2._get_invoice_in_payment_state())
        self.assertEqual(self.inv_3.payment_state, "not_paid")
        feedback = line.smart_reconcile_feedback_ids
        self.assertTrue(feedback.accepted and feedback.sent)
        self.assertEqual(fb_post.call_args.kwargs["json"]["invoice_ids"], sorted([self.inv_1.id, self.inv_2.id]))

    def test_partial_payment_leaves_invoice_partly_open(self):
        line = self._line(150.0)
        wizard, _post = self._suggest(
            line,
            [
                {"invoice_ids": [self.inv_3.id], "score": 2.0, "confidence": 0.9, "reasons": []},
            ],
        )
        with patch(FEEDBACK_POST, return_value=_response({})):
            wizard.suggestion_ids.action_accept()
        self.assertTrue(line.is_reconciled)
        self.assertEqual(self.inv_3.payment_state, "partial")
        self.assertAlmostEqual(self.inv_3.amount_residual, 250.0)

    def test_overpayment_keeps_remainder_on_suspense(self):
        line = self._line(120.0)
        wizard, _post = self._suggest(
            line,
            [
                {"invoice_ids": [self.inv_1.id], "score": 2.0, "confidence": 0.9, "reasons": []},
            ],
        )
        with patch(FEEDBACK_POST, return_value=_response({})):
            wizard.suggestion_ids.action_accept()
        self.assertFalse(line.is_reconciled)
        self.assertAlmostEqual(self.inv_1.amount_residual, 0.0)
        _liquidity, suspense, _other = line._seek_for_lines()
        self.assertAlmostEqual(suspense.balance, -20.0)

    def test_reject_records_feedback_and_removes_suggestion(self):
        line = self._line(350.0)
        wizard, _post = self._suggest(
            line,
            [
                {"invoice_ids": [self.inv_3.id], "score": 1.0, "confidence": 0.3, "reasons": []},
            ],
        )
        self.assertTrue(wizard.suggestion_ids.low_confidence)
        with patch(FEEDBACK_POST, side_effect=requests.ConnectionError("down")):
            wizard.suggestion_ids.action_reject()
        self.assertFalse(wizard.suggestion_ids)
        feedback = line.smart_reconcile_feedback_ids
        self.assertFalse(feedback.accepted)
        self.assertFalse(feedback.sent, "Feedback stays pending when the service is down")

    def test_service_down_raises_friendly_error(self):
        line = self._line(350.0)
        with patch(REQUESTS_POST, side_effect=requests.ConnectionError("down")), self.assertRaises(UserError):
            line.action_smart_suggest()

    def test_unknown_invoice_ids_from_service_are_ignored(self):
        line = self._line(350.0)
        wizard, _post = self._suggest(
            line,
            [
                {"invoice_ids": [999999], "score": 1.0, "confidence": 0.9, "reasons": []},
            ],
        )
        self.assertFalse(wizard.suggestion_ids)

    def test_outgoing_line_is_refused(self):
        with self.assertRaises(UserError):
            self._line(-50.0).action_smart_suggest()


@tagged("post_install", "-at_install")
class TestSmartReconcileAccess(AccountTestInvoicingCommon):
    """Runs as a real Invoicing user (not the superuser), so access rules apply."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.invoice = cls._create_invoice(
            partner_id=cls.partner_a,
            invoice_date="2026-01-05",
            invoice_line_ids=[Command.create({"name": "Service", "quantity": 1, "price_unit": 100.0, "tax_ids": []})],
            post=True,
        )
        cls.line = cls.env["account.bank.statement.line"].create(
            {
                "journal_id": cls.company_data["default_journal_bank"].id,
                "date": "2026-03-01",
                "amount": 100.0,
                "payment_ref": "INV payment",
            }
        )
        cls.billing_user = new_test_user(
            cls.env, login="billing_user", groups="account.group_account_invoice", company_id=cls.env.company.id
        )
        cls.plain_user = new_test_user(
            cls.env, login="plain_user", groups="base.group_user", company_id=cls.env.company.id
        )

    def _wizard(self, user):
        payload = {
            "request_id": "r1",
            "model_version": "t",
            "suggestions": [{"invoice_ids": [self.invoice.id], "score": 1.0, "confidence": 0.9, "reasons": []}],
        }
        with patch(REQUESTS_POST, return_value=_response(payload)):
            action = self.line.with_user(user).action_smart_suggest()
        return self.env["smart.reconcile.wizard"].with_user(user).browse(action["res_id"])

    def test_invoicing_user_can_accept(self):
        wizard = self._wizard(self.billing_user)
        with patch(FEEDBACK_POST, return_value=_response({})):
            wizard.suggestion_ids.action_accept()
        self.assertTrue(self.line.is_reconciled)
        self.assertEqual(self.line.smart_reconcile_feedback_ids.create_uid, self.billing_user)

    def test_other_users_cannot_accept(self):
        wizard = self._wizard(self.billing_user)
        with self.assertRaises(AccessError):
            wizard.suggestion_ids.with_user(self.plain_user).action_accept()
        self.assertFalse(self.line.is_reconciled)
