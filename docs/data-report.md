# Data Report (dataset v1, seed 42)

Produced with `python -m smart_reconcile_ml.generator --out data/generated/v1` (default config). All data is
synthetic.

## Size
| Entity | Rows |
|---|---|
| Companies | 3 (2 in Jordan / JOD, 1 in Saudi Arabia / SAR) |
| Partners | 240 (80 per company) |
| Invoices | 7,968 |
| Bank lines | 8,600 |

## Bank line types
| Type | Lines | Share |
|---|---|---|
| Single invoice, full payment | 5,141 | 59.8% |
| Partial payment | 2,331 | 27.1% |
| Grouped payment (2–4 invoices) | 491 | 5.7% |
| No matching invoice (transfers, deposits, refunds) | 637 | 7.4% |

## Noise actually present
- 30.7% of bank lines show the payer name in Arabic script.
- 70% of payment references contain at least one digit. The rest have no number at all.
- 25% of invoices use one of 4 company-wide standard amounts, so equal amounts across partners are common.
  This was added after the first model ranked an unrelated invoice first only because its amount matched
  exactly.

## Splits (by date, no shuffling)
| Split | Months | Bank lines |
|---|---|---|
| Train | 1–16 | 5,410 |
| Validation | 17–20 | 1,374 |
| Test | 21–24 | 1,816 |

## Candidates
On average, 25.3 candidates are generated per line, single and multi-invoice. The correct invoice set is among
them for 99.5% of matched test lines.
