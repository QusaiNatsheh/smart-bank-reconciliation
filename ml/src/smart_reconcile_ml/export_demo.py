"""Export one company's last months as JSON for loading into Odoo (scripts/load_demo_data.py).

Invoices open at the cutoff date are exported with their remaining amount, so earlier payments do not
need to be loaded. Usage: python -m smart_reconcile_ml.export_demo --data data/generated/v1 --out demo.json
"""

import argparse
import json
from datetime import date
from pathlib import Path

from .generator import load


def export(data: dict, company_id: int, cutoff: date) -> dict:
    invoices = data["invoices"][data["invoices"]["company_id"] == company_id]
    lines = data["bank_lines"][data["bank_lines"]["company_id"] == company_id]
    matches = data["matches"].merge(lines[["line_id", "date"]], on="line_id")
    paid_before = matches[matches["date"] < cutoff].groupby("invoice_id")["allocated_amount"].sum()
    invoices = invoices.assign(
        open_amount=(invoices["amount_total"] - invoices["invoice_id"].map(paid_before).fillna(0)).round(3)
    )
    invoices = invoices[invoices["open_amount"] > 0.005]
    later_lines = lines[lines["date"] >= cutoff]
    truth = matches[matches["line_id"].isin(later_lines["line_id"])]
    numbers = invoices.set_index("invoice_id")["number"]
    truth_by_line = (
        truth.groupby("line_id")["invoice_id"]
        .apply(lambda s: sorted(numbers.get(i, f"missing-{i}") for i in s))
        .to_dict()
    )
    partners = data["partners"][data["partners"]["partner_id"].isin(invoices["partner_id"])]
    company = data["companies"].set_index("company_id").loc[company_id]
    return {
        "currency": company["currency"],
        "cutoff": cutoff.isoformat(),
        "partners": [
            {"ref": f"P{r.partner_id}", "name": r.name_en, "alt_name": r.name_ar} for r in partners.itertuples()
        ],
        "invoices": [
            {
                "number": r.number,
                "partner_ref": f"P{r.partner_id}",
                "invoice_date": r.invoice_date.isoformat(),
                "due_date": r.due_date.isoformat(),
                "amount": float(r.open_amount),
            }
            for r in invoices.sort_values(["invoice_date", "invoice_id"]).itertuples()
        ],
        "bank_lines": [
            {
                "ref": f"L{r.line_id}",
                "date": r.date.isoformat(),
                "amount": float(r.amount),
                "payment_ref": r.payment_ref or "/",
                "partner_name": r.partner_name_raw,
                "true_invoices": truth_by_line.get(r.line_id, []),
            }
            for r in later_lines.sort_values(["date", "line_id"]).itertuples()
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data/generated/v1"))
    parser.add_argument("--out", type=Path, default=Path("data/generated/demo.json"))
    parser.add_argument("--company", type=int, default=1)
    parser.add_argument("--cutoff", default="2026-08-01")
    args = parser.parse_args(argv)
    payload = export(load(args.data), args.company, date.fromisoformat(args.cutoff))
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    print(f"{len(payload['invoices'])} invoices, {len(payload['bank_lines'])} bank lines -> {args.out}")


if __name__ == "__main__":
    main()
