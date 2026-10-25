"""HTTP service that ranks invoice matches for a bank line. Run: uvicorn smart_reconcile_ml.service:app"""

import os
import uuid
from datetime import date
from functools import lru_cache
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from .feedback import FeedbackStore
from .matching import BankLine, OpenInvoice, generate_candidates
from .model import Model

MAX_INVOICES = 2000


class LineIn(BaseModel):
    amount: float = Field(gt=0, lt=1e12)
    date: date
    payment_ref: str = Field("", max_length=500)
    partner_name: str = Field("", max_length=200)
    currency: str = Field("", max_length=3)


class InvoiceIn(BaseModel):
    id: int
    number: str = Field(max_length=100)
    partner_id: int
    partner_names: list[str] = Field(max_length=5)
    invoice_date: date
    due_date: date | None = None
    amount_residual: float = Field(gt=0)
    partner_avg_days: float | None = None


class SuggestIn(BaseModel):
    line: LineIn
    invoices: list[InvoiceIn] = Field(max_length=MAX_INVOICES)
    top_k: int = Field(3, ge=1, le=10)


class SuggestionOut(BaseModel):
    invoice_ids: list[int]
    score: float
    confidence: float
    reasons: list[str]


class SuggestOut(BaseModel):
    request_id: str
    model_version: str
    suggestions: list[SuggestionOut]


class FeedbackIn(BaseModel):
    request_id: str = Field(max_length=64)
    invoice_ids: list[int] = Field(max_length=50)
    accepted: bool


@lru_cache
def get_model() -> Model:
    return Model(Path(os.environ.get("MODEL_DIR", "models/latest")))


@lru_cache
def get_store() -> FeedbackStore:
    return FeedbackStore(Path(os.environ.get("FEEDBACK_DIR", "feedback")))


app = FastAPI(title="Smart Reconcile ML service", version="1.0.0")


@app.get("/health")
def health(model: Model = Depends(get_model)):
    return {"status": "ok", "model_version": model.version}


@app.post("/suggest", response_model=SuggestOut)
def suggest(body: SuggestIn, model: Model = Depends(get_model), store: FeedbackStore = Depends(get_store)):
    line = BankLine(body.line.amount, body.line.date, body.line.payment_ref, body.line.partner_name, body.line.currency)
    invoices = [
        OpenInvoice(
            i.id,
            i.number,
            i.partner_id,
            i.partner_names,
            i.invoice_date,
            i.due_date or i.invoice_date,
            i.amount_residual,
            i.partner_avg_days,
        )
        for i in body.invoices
    ]
    cands = generate_candidates(line, invoices)
    request_id = uuid.uuid4().hex
    if cands:
        store.save_request(request_id, cands)
    suggestions = [
        SuggestionOut(invoice_ids=list(s.invoice_ids), score=s.score, confidence=s.confidence, reasons=s.reasons)
        for s in model.rank(cands, top_k=body.top_k)
    ]
    return SuggestOut(request_id=request_id, model_version=model.version, suggestions=suggestions)


@app.post("/feedback")
def feedback(body: FeedbackIn, store: FeedbackStore = Depends(get_store)):
    if not body.request_id.isalnum() or not store.has_request(body.request_id):
        raise HTTPException(status_code=404, detail="Unknown request_id")
    store.record(body.request_id, body.invoice_ids, body.accepted)
    return {"status": "recorded"}
