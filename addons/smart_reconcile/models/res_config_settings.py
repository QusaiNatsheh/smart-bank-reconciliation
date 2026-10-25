from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    smart_reconcile_service_url = fields.Char(
        string="Matching Service URL",
        config_parameter="smart_reconcile.service_url",
        default="http://ml:8000",
    )
    smart_reconcile_threshold = fields.Float(
        string="Confidence Threshold",
        config_parameter="smart_reconcile.threshold",
        default=0.8,
        help="Suggestions below this score are shown as low confidence.",
    )
