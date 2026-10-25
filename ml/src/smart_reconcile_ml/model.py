"""Load a trained model and turn candidates into ranked, explained suggestions."""

import json
from dataclasses import dataclass
from pathlib import Path

import lightgbm as lgb
import numpy as np

from .matching import FEATURES, Candidate, feature_matrix

REASONS = {
    "ref_exact_frac": lambda f: "Reference contains the invoice number" if f["ref_exact_frac"] else None,
    "ref_seq_frac": lambda f: "Reference mentions the invoice sequence number" if f["ref_seq_frac"] else None,
    "exact_amount": lambda f: "Amount matches exactly" if f["exact_amount"] else None,
    "fee_like": lambda f: (
        f"Amount is {f['amount_diff']:.2f} short, consistent with a bank fee" if f["fee_like"] else None
    ),
    "name_sim": lambda f: f"Payer name matches the partner ({f['name_sim']:.0%})" if f["name_sim"] >= 0.7 else None,
    "n_invoices": lambda f: (
        f"Total of {int(f['n_invoices'])} open invoices fits the amount" if f["n_invoices"] > 1 else None
    ),
    "partial_plausible": lambda f: "Looks like a partial payment" if f["partial_plausible"] else None,
    "days_vs_partner_avg": lambda f: (
        "Payment timing is typical for this partner"
        if f["days_vs_partner_avg"] == f["days_vs_partner_avg"] and abs(f["days_vs_partner_avg"]) <= 10
        else None
    ),
    "amount_diff_rank": lambda f: "Closest amount among open invoices" if f["amount_diff_rank"] == 0 else None,
}


@dataclass
class Suggestion:
    invoice_ids: tuple[int, ...]
    score: float
    confidence: float
    reasons: list[str]


class Model:
    def __init__(self, path: Path):
        path = Path(path)
        self.booster = lgb.Booster(model_file=str(path / "model.txt"))
        meta = json.loads((path / "meta.json").read_text())
        if meta["features"] != FEATURES:
            raise ValueError("Model features do not match the code version")
        self.meta = meta
        self.calibration = meta["calibration"]

    @property
    def version(self) -> str:
        return self.meta["version"]

    def confidence(self, scores: np.ndarray) -> float:
        """Probability that the top suggestion is correct, from the top score and its margin."""
        if len(scores) == 0:
            return 0.0
        top = np.sort(scores)[::-1]
        margin = top[0] - top[1] if len(top) > 1 else 5.0
        c = self.calibration
        z = c["intercept"] + c["coef"][0] * top[0] + c["coef"][1] * margin
        return float(1 / (1 + np.exp(-z)))

    def rank(self, cands: list[Candidate], top_k: int = 3) -> list[Suggestion]:
        if not cands:
            return []
        x = feature_matrix(cands)
        scores = self.booster.predict(x)
        contrib = self.booster.predict(x, pred_contrib=True)[:, :-1]  # last column is the bias
        conf = self.confidence(scores)
        order = np.argsort(-scores)[:top_k]
        suggestions = []
        for rank, i in enumerate(order):
            suggestions.append(
                Suggestion(
                    invoice_ids=cands[i].invoice_ids,
                    score=float(scores[i]),
                    confidence=conf if rank == 0 else 0.0,
                    reasons=explain(cands[i].features, contrib[i]),
                )
            )
        return suggestions


def explain(features: dict[str, float], contributions: np.ndarray, limit: int = 3) -> list[str]:
    """Plain-language reasons for the features that pushed this candidate up the most (SHAP values)."""
    reasons = []
    for j in np.argsort(-contributions):
        if contributions[j] <= 0 or len(reasons) >= limit:
            break
        text = REASONS.get(FEATURES[j], lambda f: None)(features)
        if text:
            reasons.append(text)
    return reasons
