"""Load exported synthetic data into an Odoo 20 database. Run inside `odoo shell`:

DEMO_JSON=/path/demo.json odoo shell -d <db> --addons-path=... < scripts/load_demo_data.py
"""

import json
import os

from odoo import Command

data = json.load(open(os.environ.get("DEMO_JSON", "/mnt/data/demo.json"), encoding="utf-8"))
company = env.company
currency = env["res.currency"].with_context(active_test=False).search([("name", "=", data["currency"])])
currency.active = True
if not env["account.account"].search_count([("company_ids", "in", company.ids)], limit=1):
    env["account.chart.template"].try_loading("generic_coa", company, install_demo=False)
if company.currency_id != currency and not env["account.move.line"].search_count([], limit=1):
    company.currency_id = currency

if env["account.move"].search_count([("move_type", "=", "out_invoice")], limit=1):
    print("Invoices already exist, demo data not loaded.")
else:
    Partner = env["res.partner"]
    partners = {
        p["ref"]: Partner.create(
            {"name": p["name"], "smart_reconcile_alt_name": p["alt_name"], "ref": p["ref"], "is_company": True}
        )
        for p in data["partners"]
    }
    journal = env["account.journal"].search([("type", "=", "sale"), ("company_id", "=", company.id)], limit=1)
    for inv in data["invoices"]:
        move = env["account.move"].create(
            {
                "move_type": "out_invoice",
                "journal_id": journal.id,
                "partner_id": partners[inv["partner_ref"]].id,
                "invoice_date": inv["invoice_date"],
                "invoice_date_due": inv["due_date"],
                "invoice_line_ids": [
                    Command.create({"name": "Services", "quantity": 1, "price_unit": inv["amount"], "tax_ids": []})
                ],
            }
        )
        move.name = inv["number"]  # keep the synthetic number so bank references point at it
        move.action_post()
    bank = env["account.journal"].search([("type", "=", "bank"), ("company_id", "=", company.id)], limit=1)
    env["account.bank.statement.line"].create(
        [
            {
                "journal_id": bank.id,
                "date": line["date"],
                "amount": line["amount"],
                "payment_ref": line["payment_ref"],
                "partner_name": line["partner_name"],
                "transaction_details": {"demo_ref": line["ref"]},
            }
            for line in data["bank_lines"]
        ]
    )
    env.cr.commit()
    print(f"Loaded {len(partners)} partners, {len(data['invoices'])} invoices, {len(data['bank_lines'])} bank lines")
