from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    smart_reconcile_alt_name = fields.Char(
        string="Alternative Name",
        help="Name in another language or spelling (for example Arabic), used to match bank statement lines.",
    )
