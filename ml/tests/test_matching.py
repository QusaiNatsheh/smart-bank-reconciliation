from datetime import date

from smart_reconcile_ml.matching import FEATURES, BankLine, OpenInvoice, generate_candidates


def _inv(i, partner, amount, number=None, names=("Al Nour Trading Co.", "شركة النور للتجارة")):
    return OpenInvoice(
        i, number or f"INV/2026/{i:05d}", partner, list(names), date(2026, 1, i), date(2026, 2, i), amount
    )


def test_grouped_payment_creates_combo_candidate():
    invoices = [
        _inv(1, 1, 100.0),
        _inv(2, 1, 250.0),
        _inv(3, 1, 75.0),
        _inv(4, 2, 350.0, names=("Al Hayat Pharmacy", "صيدلية الحياة")),
    ]
    line = BankLine(350.0, date(2026, 3, 1), "", "شركة النور", "JOD")
    cands = generate_candidates(line, invoices)
    ids = {c.invoice_ids for c in cands}
    assert (1, 2) in ids and (4,) in ids
    for c in cands:
        assert set(c.features) == set(FEATURES)


def test_no_candidates_for_empty_input():
    assert generate_candidates(BankLine(10.0, date(2026, 1, 1)), []) == []
