"""Store user feedback from Odoo and turn it into extra training groups.

When the service makes suggestions it saves the features of every candidate under a request id.
When the user accepts a suggestion in Odoo, that candidate becomes the positive label of the group.
"""

import json
from pathlib import Path

import pandas as pd

from .matching import FEATURES, Candidate


class FeedbackStore:
    def __init__(self, directory: Path):
        self.dir = Path(directory)
        (self.dir / "requests").mkdir(parents=True, exist_ok=True)

    def save_request(self, request_id: str, cands: list[Candidate]) -> None:
        rows = [{"invoice_ids": list(c.invoice_ids), **{f: c.features[f] for f in FEATURES}} for c in cands]
        (self.dir / "requests" / f"{request_id}.json").write_text(json.dumps(rows, allow_nan=True))

    def has_request(self, request_id: str) -> bool:
        return (self.dir / "requests" / f"{request_id}.json").exists()

    def record(self, request_id: str, invoice_ids: list[int], accepted: bool) -> None:
        entry = {"request_id": request_id, "invoice_ids": sorted(invoice_ids), "accepted": accepted}
        with (self.dir / "feedback.jsonl").open("a") as fh:
            fh.write(json.dumps(entry) + "\n")


def load_feedback_groups(directory: Path, start_id: int) -> pd.DataFrame:
    """One ranking group per request that has an accepted suggestion."""
    directory = Path(directory)
    log = directory / "feedback.jsonl"
    if not log.exists():
        return pd.DataFrame(columns=["line_id", "invoice_ids", "label", *FEATURES])
    accepted = {}
    for raw in log.read_text().splitlines():
        entry = json.loads(raw)
        if entry["accepted"]:
            accepted[entry["request_id"]] = tuple(entry["invoice_ids"])
    rows = []
    for offset, (request_id, ids) in enumerate(sorted(accepted.items())):
        path = directory / "requests" / f"{request_id}.json"
        if not path.exists():
            continue
        for cand in json.loads(path.read_text()):
            rows.append({"line_id": start_id + offset, "label": int(tuple(cand["invoice_ids"]) == ids), **cand})
    return pd.DataFrame(rows, columns=["line_id", "invoice_ids", "label", *FEATURES])
