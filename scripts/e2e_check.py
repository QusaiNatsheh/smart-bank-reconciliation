"""End-to-end check through Odoo and the running ML service. Run inside `odoo shell` after loading demo data.

For each bank line in date order it asks for suggestions, scores the top one against the known truth,
then accepts the true match (as a user would), so later lines see correct open amounts.
"""

import json
import os

from odoo.exceptions import UserError

data = json.load(open(os.environ.get("DEMO_JSON", "/mnt/data/demo.json"), encoding="utf-8"))
truth = {line["ref"]: line["true_invoices"] for line in data["bank_lines"]}
threshold = env["ir.config_parameter"].sudo().get_float("smart_reconcile.threshold") or 0.8
Move = env["account.move"]
lines = env["account.bank.statement.line"].search([("is_reconciled", "=", False)], order="date, id")
stats = {"matched": 0, "top1": 0, "top3": 0, "unmatched": 0, "confident": 0, "confident_right": 0, "errors": 0}
for line in lines:
    expected = truth.get((line.transaction_details or {}).get("demo_ref"), [])
    try:
        wizard = env["smart.reconcile.wizard"].browse(line.action_smart_suggest()["res_id"])
    except UserError as exc:
        stats["errors"] += 1
        print("error", line.id, exc)
        continue
    ranked = [sorted(s.invoice_ids.mapped("name")) for s in wizard.suggestion_ids.sorted("rank")]
    top = wizard.suggestion_ids.sorted("rank")[:1]
    right = bool(ranked) and ranked[0] == expected
    if top and top.confidence >= threshold:
        stats["confident"] += 1
        stats["confident_right"] += int(right)
    if not expected:
        stats["unmatched"] += 1
        continue
    stats["matched"] += 1
    stats["top1"] += int(right)
    stats["top3"] += int(expected in ranked[:3])
    invoices = Move.search([("name", "in", expected), ("move_type", "=", "out_invoice")])
    if len(invoices) == len(expected):
        line._smart_reconcile_apply(invoices)
env.cr.commit()
n = stats["matched"] or 1
print(json.dumps(stats))
print(
    f"Top-1 {stats['top1'] / n:.3f}  Top-3 {stats['top3'] / n:.3f}  over {stats['matched']} matched lines; "
    f"confident {stats['confident']} of {len(lines)} lines, precision "
    f"{stats['confident_right'] / max(stats['confident'], 1):.3f}"
)
