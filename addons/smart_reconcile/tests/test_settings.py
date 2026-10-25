from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestSettings(TransactionCase):
    def test_settings_stored_as_parameters(self):
        settings = self.env["res.config.settings"].create(
            {
                "smart_reconcile_service_url": "http://localhost:9999",
                "smart_reconcile_threshold": 0.65,
            }
        )
        settings.execute()
        params = self.env["ir.config_parameter"].sudo()
        self.assertEqual(params.get_str("smart_reconcile.service_url"), "http://localhost:9999")
        self.assertEqual(params.get_float("smart_reconcile.threshold"), 0.65)
