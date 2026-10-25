"""Turn a generated dataset into ranking groups (one group of candidates per bank line).

Lines are replayed in date order, so each line only sees invoices open on that date and payment
history from earlier lines. Nothing from the future leaks into features.
"""

from collections import defaultdict
from datetime import date

import numpy as np
import pandas as pd

from .matching import FEATURES, BankLine, OpenInvoice, generate_candidates

HISTORY_MASK_RATE = 0.2  # Share of lines trained without partner history, as happens in a fresh Odoo database.


def month_index(start: date, d: date) -> int:
    return (d.year - start.year) * 12 + d.month - start.month


def split_of(month: int, train_months: int = 16, valid_months: int = 4) -> str:
    if month < train_months:
        return "train"
    return "valid" if month < train_months + valid_months else "test"


def build_groups(data: dict, seed: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (candidate rows, line summary)."""
    rng = np.random.default_rng(seed)
    partners = data["partners"].set_index("partner_id")
    invoices = data["invoices"].sort_values(["invoice_date", "invoice_id"])
    lines = data["bank_lines"].sort_values(["date", "line_id"])
    matches = data["matches"]
    truth = matches.groupby("line_id")["invoice_id"].apply(lambda s: tuple(sorted(s))).to_dict()
    allocations = (
        matches.groupby("line_id")[["invoice_id", "allocated_amount"]]
        .apply(lambda df: list(df.itertuples(index=False, name=None)))
        .to_dict()
    )
    inv_total = invoices.set_index("invoice_id")["amount_total"].to_dict()
    start = min(lines["date"].min(), invoices["invoice_date"].min())

    pending = defaultdict(list)  # company -> invoices not yet issued
    for row in invoices.itertuples(index=False):
        p = partners.loc[row.partner_id]
        pending[row.company_id].append(
            OpenInvoice(
                invoice_id=row.invoice_id,
                number=row.number,
                partner_id=row.partner_id,
                partner_names=[p["name_en"], p["name_ar"]],
                invoice_date=row.invoice_date,
                due_date=row.due_date,
                amount_residual=row.amount_total,
            )
        )
    cursor = defaultdict(int)
    open_by_company: dict[int, dict[int, OpenInvoice]] = defaultdict(dict)
    history: dict[int, list[int]] = defaultdict(list)

    rows, summary = [], []
    for line in lines.itertuples(index=False):
        comp = line.company_id
        queue = pending[comp]
        while cursor[comp] < len(queue) and queue[cursor[comp]].invoice_date <= line.date:
            inv = queue[cursor[comp]]
            open_by_company[comp][inv.invoice_id] = inv
            cursor[comp] += 1
        open_invs = list(open_by_company[comp].values())
        masked = rng.random() < HISTORY_MASK_RATE
        for inv in open_invs:
            past = history.get(inv.partner_id)
            inv.partner_avg_days = None if masked or not past else float(np.mean(past[-20:]))

        bl = BankLine(line.amount, line.date, line.payment_ref, line.partner_name_raw, line.currency)
        cands = generate_candidates(bl, open_invs)
        true_set = truth.get(line.line_id)
        found = False
        for c in cands:
            label = int(c.invoice_ids == true_set)
            found |= bool(label)
            rows.append({"line_id": line.line_id, "invoice_ids": list(c.invoice_ids), "label": label, **c.features})

        allocs = allocations.get(line.line_id, [])
        if not true_set:
            kind = "unmatched"
        elif len(true_set) > 1:
            kind = "grouped"
        elif allocs[0][1] < inv_total[allocs[0][0]] - 0.001:
            kind = "partial"
        else:
            kind = "single"
        month = month_index(start, line.date)
        summary.append(
            {
                "line_id": line.line_id,
                "split": split_of(month),
                "kind": kind,
                "has_match": bool(true_set),
                "found": found,
                "n_candidates": len(cands),
            }
        )

        # Apply the true payment so later lines see updated residuals and history.
        for invoice_id, amount in allocs:
            inv = open_by_company[comp].get(invoice_id)
            if inv is None:
                continue
            inv.amount_residual = round(inv.amount_residual - amount, 3)
            history[inv.partner_id].append((line.date - inv.invoice_date).days)
            if inv.amount_residual <= 0.005:
                del open_by_company[comp][invoice_id]

    cand_df = pd.DataFrame(rows, columns=["line_id", "invoice_ids", "label", *FEATURES])
    return cand_df, pd.DataFrame(summary)
