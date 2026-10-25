"""Candidate generation and feature engineering, shared by training and the online service.

A candidate is a set of one or more open invoices that one bank line may pay. Grouped payments are
covered by multi-invoice candidates; partial payments by single invoices whose residual exceeds the line.
"""

from dataclasses import dataclass, field
from datetime import date
from itertools import combinations

import numpy as np

from .text import best_name_similarity, reference_features

FEE_TOLERANCE = {"JOD": 5.0, "SAR": 25.0}
DEFAULT_FEE_TOLERANCE = 5.0
MAX_SINGLE = 25
MAX_COMBO = 15
COMBO_PARTNERS = 4
COMBO_POOL = 10
COMBO_MAX_SIZE = 4

FEATURES = [
    "n_invoices",
    "amount_diff",
    "amount_diff_rel",
    "amount_ratio",
    "exact_amount",
    "fee_like",
    "partial_plausible",
    "days_since_invoice_min",
    "days_since_invoice_max",
    "days_past_due",
    "days_vs_partner_avg",
    "ref_exact_frac",
    "ref_seq_frac",
    "ref_fuzzy_max",
    "ref_hits_uncovered",
    "ref_empty",
    "name_sim",
    "name_sim_gap",
    "amount_diff_rank",
    "partner_open_count",
]


@dataclass
class BankLine:
    amount: float
    date: date
    payment_ref: str = ""
    partner_name_raw: str = ""
    currency: str = ""


@dataclass
class OpenInvoice:
    invoice_id: int
    number: str
    partner_id: int
    partner_names: list[str]
    invoice_date: date
    due_date: date
    amount_residual: float
    partner_avg_days: float | None = None


@dataclass
class Candidate:
    invoices: list[OpenInvoice]
    features: dict[str, float] = field(default_factory=dict)

    @property
    def invoice_ids(self) -> tuple[int, ...]:
        return tuple(sorted(i.invoice_id for i in self.invoices))


def _tolerance(line: BankLine) -> float:
    return max(FEE_TOLERANCE.get(line.currency, DEFAULT_FEE_TOLERANCE), 0.01 * abs(line.amount))


def generate_candidates(line: BankLine, open_invoices: list[OpenInvoice]) -> list[Candidate]:
    """Pick plausible invoice sets for a line and compute their features."""
    if not open_invoices or line.amount <= 0:
        return []
    tol = _tolerance(line)

    name_sim_by_partner: dict[int, float] = {}
    for inv in open_invoices:
        if inv.partner_id not in name_sim_by_partner:
            name_sim_by_partner[inv.partner_id] = best_name_similarity(line.partner_name_raw, inv.partner_names)
    ref_by_invoice = {inv.invoice_id: reference_features(line.payment_ref, inv.number) for inv in open_invoices}
    ref_hits = {i for i, r in ref_by_invoice.items() if r["ref_exact"] or r["ref_seq_match"]}

    def quick_score(inv: OpenInvoice) -> float:
        diff = abs(line.amount - inv.amount_residual)
        amount_score = 1.0 if diff <= tol else (0.3 if line.amount < inv.amount_residual else 0.0)
        ref = ref_by_invoice[inv.invoice_id]
        return 3 * max(ref["ref_exact"], ref["ref_seq_match"]) + 2 * name_sim_by_partner[inv.partner_id] + amount_score

    ranked = sorted(open_invoices, key=quick_score, reverse=True)
    candidates = {(inv.invoice_id,): Candidate([inv]) for inv in ranked[:MAX_SINGLE]}

    # Multi-invoice candidates: subsets of a likely partner's open invoices whose total fits the amount.
    partner_score: dict[int, float] = {}
    for inv in open_invoices:
        score = name_sim_by_partner[inv.partner_id] + (1.0 if inv.invoice_id in ref_hits else 0.0)
        partner_score[inv.partner_id] = max(partner_score.get(inv.partner_id, 0.0), score)
    top_partners = sorted(partner_score, key=partner_score.get, reverse=True)[:COMBO_PARTNERS]
    combos: list[tuple[float, list[OpenInvoice]]] = []
    for pid in top_partners:
        pool = sorted((i for i in open_invoices if i.partner_id == pid), key=lambda i: i.invoice_date)
        pool = pool[-COMBO_POOL:]
        for size in range(2, min(COMBO_MAX_SIZE, len(pool)) + 1):
            for subset in combinations(pool, size):
                diff = abs(line.amount - sum(i.amount_residual for i in subset))
                if diff <= tol:
                    combos.append((diff, list(subset)))
    referenced = [i for i in open_invoices if i.invoice_id in ref_hits]
    if 2 <= len(referenced) <= COMBO_MAX_SIZE:
        combos.append((0.0, referenced))
    combos.sort(key=lambda c: c[0])
    for _, subset in combos[:MAX_COMBO]:
        cand = Candidate(subset)
        candidates.setdefault(cand.invoice_ids, cand)

    result = list(candidates.values())
    open_count: dict[int, int] = {}
    for inv in open_invoices:
        open_count[inv.partner_id] = open_count.get(inv.partner_id, 0) + 1
    for cand in result:
        cand.features = _features(line, cand, tol, name_sim_by_partner, ref_by_invoice, ref_hits, open_count)
    _add_relative_features(result)
    return result


def _features(line, cand, tol, name_sim_by_partner, ref_by_invoice, ref_hits, open_count) -> dict[str, float]:
    invs = cand.invoices
    residual = sum(i.amount_residual for i in invs)
    diff = line.amount - residual
    days = [(line.date - i.invoice_date).days for i in invs]
    avg_days = [i.partner_avg_days for i in invs if i.partner_avg_days is not None]
    refs = [ref_by_invoice[i.invoice_id] for i in invs]
    ids = {i.invoice_id for i in invs}
    return {
        "n_invoices": len(invs),
        "amount_diff": abs(diff),
        "amount_diff_rel": abs(diff) / max(line.amount, 1e-9),
        "amount_ratio": line.amount / residual if residual else 0.0,
        "exact_amount": float(abs(diff) < 0.01),
        "fee_like": float(0 < -diff <= tol),
        "partial_plausible": float(line.amount < residual - tol),
        "days_since_invoice_min": float(min(days)),
        "days_since_invoice_max": float(max(days)),
        "days_past_due": float(max((line.date - i.due_date).days for i in invs)),
        "days_vs_partner_avg": float(np.mean(days) - np.mean(avg_days)) if avg_days else np.nan,
        "ref_exact_frac": float(np.mean([r["ref_exact"] for r in refs])),
        "ref_seq_frac": float(np.mean([r["ref_seq_match"] for r in refs])),
        "ref_fuzzy_max": max(r["ref_fuzzy"] for r in refs),
        "ref_hits_uncovered": float(len(ref_hits - ids)),
        "ref_empty": float(not (line.payment_ref or "").strip()),
        "name_sim": max(name_sim_by_partner[i.partner_id] for i in invs),
        "partner_open_count": float(max(open_count[i.partner_id] for i in invs)),
    }


def _add_relative_features(cands: list[Candidate]) -> None:
    best_name = max(c.features["name_sim"] for c in cands)
    order = np.argsort(np.argsort([c.features["amount_diff"] for c in cands], kind="stable"))
    for cand, rank in zip(cands, order, strict=True):
        cand.features["name_sim_gap"] = cand.features["name_sim"] - best_name
        cand.features["amount_diff_rank"] = float(rank)


def feature_matrix(cands: list[Candidate]) -> np.ndarray:
    return np.array([[c.features[f] for f in FEATURES] for c in cands], dtype=float)


def baseline_score(features: dict[str, float]) -> float:
    """Hand-written rules in the style of a reconciliation model: reference, amount, then name."""
    return (
        3.0 * features["ref_exact_frac"]
        + 2.0 * features["ref_seq_frac"]
        + 2.0 * features["exact_amount"]
        + 1.0 * features["fee_like"]
        + 2.0 * features["name_sim"]
        - 1.0 * min(features["amount_diff_rel"], 1.0)
    )
