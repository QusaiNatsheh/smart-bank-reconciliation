{
    "name": "Smart Bank Reconciliation",
    "summary": "Ranks likely invoice matches for bank statement lines using a trained model",
    "version": "20.0.1.0.0",
    "category": "Accounting/Accounting",
    "author": "Qusai Natsheh",
    "website": "https://github.com/QusaiNatsheh/smart-bank-reconciliation",
    "license": "LGPL-3",
    "depends": ["account"],
    "external_dependencies": {"python": ["requests"]},
    "data": [
        "security/ir.access.csv",
        "data/ir_cron.xml",
        "views/res_config_settings_views.xml",
        "views/res_partner_views.xml",
        "views/account_bank_statement_line_views.xml",
        "wizard/smart_reconcile_wizard_views.xml",
    ],
}
