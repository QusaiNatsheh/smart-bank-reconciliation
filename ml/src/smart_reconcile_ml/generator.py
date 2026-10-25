"""Synthetic accounting data generator: companies, partners, invoices, bank lines and true matches.

See docs/data-spec.md. Usage: python -m smart_reconcile_ml.generator --out data/generated/v1 --seed 42
"""

import argparse
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from .names import ACTIVITIES, COMPANY_FORMS, FAMILY_NAMES, FIRST_NAMES

PROFILES = {
    # profile: (mean days to pay, std, share of invoices paid in parts)
    "punctual": (20, 6, 0.03),
    "late": (55, 20, 0.05),
    "partial_payer": (35, 15, 0.45),
    "batch_payer": (30, 5, 0.02),
}


@dataclass
class NoiseConfig:
    missing_reference: float = 0.30
    reference_typo: float = 0.10
    reference_format_change: float = 0.15
    bank_fee: float = 0.08
    rounding_difference: float = 0.05
    name_language_switch: float = 0.40
    name_noise: float = 0.20
    transliteration: float = 0.15
    third_party_payer: float = 0.03
    unmatched_line_rate: float = 0.08


@dataclass
class GeneratorConfig:
    seed: int = 42
    start: str = "2024-10-01"
    months: int = 24
    companies: list = field(default_factory=lambda: [("JO", "JOD"), ("JO", "JOD"), ("SA", "SAR")])
    partners_per_company: int = 80
    invoices_per_partner_month: float = 1.4
    unpaid_share: float = 0.04
    standard_price_share: float = 0.25  # invoices billed at a company-wide standard amount (fees, subscriptions)
    noise: NoiseConfig = field(default_factory=NoiseConfig)


DECIMALS = {"JOD": 3, "SAR": 2}
FEES = {"JOD": (1.0, 5.0), "SAR": (5.0, 25.0)}


def _add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    return date(d.year + y, m + 1, 1)


class Generator:
    def __init__(self, config: GeneratorConfig):
        self.cfg = config
        self.noise = config.noise
        self.rng = np.random.default_rng(config.seed)
        self.start = date.fromisoformat(config.start)
        self.end = _add_months(self.start, config.months) - timedelta(days=1)

    def _chance(self, p: float) -> bool:
        return bool(self.rng.random() < p)

    def _pick(self, items):
        return items[int(self.rng.integers(len(items)))]

    # ------------------------------------------------------------------ entities
    def make_companies(self):
        return [
            {"company_id": i + 1, "name": f"Demo Company {i + 1}", "country": c, "currency": cur}
            for i, (c, cur) in enumerate(self.cfg.companies)
        ]

    def make_partner_name(self):
        if self._chance(0.25):
            ar_first, en_first, first_variants = self._pick(FIRST_NAMES)
            ar_fam, en_fam, fam_variants = self._pick(FAMILY_NAMES)
            parts = {"first": (ar_first, en_first, first_variants), "family": (ar_fam, en_fam, fam_variants)}
            name_ar = f"مؤسسة {ar_first} {ar_fam}"
            name_en = f"{en_first} {en_fam.replace(' ', '-')} Est."
            return name_ar, name_en, parts
        ar_fam, en_fam, fam_variants = self._pick(FAMILY_NAMES)
        ar_act, en_act = self._pick(ACTIVITIES)
        ar_form, en_form = self._pick(COMPANY_FORMS)
        name_ar = f"{ar_form} {ar_fam} {ar_act}"
        name_en = f"{en_fam} {en_act} {en_form}"
        return name_ar, name_en, {"family": (ar_fam, en_fam, fam_variants), "activity": (ar_act, en_act)}

    def make_partners(self, companies):
        partners, self._name_parts = [], {}
        pid = 1
        for comp in companies:
            used = set()
            while len([p for p in partners if p["company_id"] == comp["company_id"]]) < self.cfg.partners_per_company:
                name_ar, name_en, parts = self.make_partner_name()
                if name_en in used:
                    continue
                used.add(name_en)
                profile = self._pick(list(PROFILES))
                mean, std, _ = PROFILES[profile]
                partners.append(
                    {
                        "partner_id": pid,
                        "company_id": comp["company_id"],
                        "name_en": name_en,
                        "name_ar": name_ar,
                        "payer_profile": profile,
                        "avg_days_to_pay": float(max(3, self.rng.normal(mean, std / 2))),
                    }
                )
                self._name_parts[pid] = parts
                pid += 1
        return partners

    def make_invoices(self, companies, partners):
        invoices, iid = [], 1
        seq = {}
        # Each company bills some invoices at a few standard amounts, so equal amounts across partners are common.
        standard = {
            c["company_id"]: [
                float(x)
                for x in self.rng.choice([150, 250, 300, 500, 750, 1000, 1200, 1500, 2000, 2500], size=4, replace=False)
            ]
            for c in companies
        }
        for month in range(self.cfg.months):
            m_start = _add_months(self.start, month)
            days_in_month = (_add_months(m_start, 1) - m_start).days
            season = 1.0 + 0.25 * math.sin(2 * math.pi * (m_start.month - 3) / 12)
            rows = []
            for p in partners:
                for _ in range(self.rng.poisson(self.cfg.invoices_per_partner_month * season)):
                    rows.append((p, m_start + timedelta(days=int(self.rng.integers(days_in_month)))))
            rows.sort(key=lambda r: (r[1], r[0]["partner_id"]))
            for p, inv_date in rows:
                comp = companies[p["company_id"] - 1]
                key = (comp["company_id"], inv_date.year)
                seq[key] = seq.get(key, 0) + 1
                if self._chance(self.cfg.standard_price_share):
                    amount = self._pick(standard[comp["company_id"]])
                else:
                    amount = float(np.round(self.rng.lognormal(mean=6.6, sigma=0.9), DECIMALS[comp["currency"]]))
                invoices.append(
                    {
                        "invoice_id": iid,
                        "company_id": comp["company_id"],
                        "partner_id": p["partner_id"],
                        "number": f"INV/{inv_date.year}/{seq[key]:05d}",
                        "invoice_date": inv_date,
                        "due_date": inv_date + timedelta(days=30),
                        "amount_total": max(amount, 5.0),
                        "currency": comp["currency"],
                    }
                )
                iid += 1
        return invoices

    # ------------------------------------------------------------------ payments
    def plan_payments(self, partners, invoices):
        """Return payments: dicts with date, partner, list of (invoice, allocated amount)."""
        by_partner = {}
        for inv in invoices:
            by_partner.setdefault(inv["partner_id"], []).append(inv)
        payments = []
        for p in partners:
            invs = by_partner.get(p["partner_id"], [])
            mean, std, partial_share = PROFILES[p["payer_profile"]]
            if p["payer_profile"] == "batch_payer":
                payments += self._batch_payments(p, invs)
                continue
            for inv in invs:
                if self._chance(self.cfg.unpaid_share):
                    continue
                pay_date = inv["invoice_date"] + timedelta(days=int(max(0, self.rng.normal(p["avg_days_to_pay"], std))))
                if self._chance(partial_share):
                    n_parts = int(self.rng.integers(2, 4))
                    weights = self.rng.dirichlet(np.ones(n_parts) * 3)
                    dec = DECIMALS[inv["currency"]]
                    parts = [float(np.round(inv["amount_total"] * w, dec)) for w in weights[:-1]]
                    parts.append(float(np.round(inv["amount_total"] - sum(parts), dec)))
                    d = pay_date
                    for amount in parts:
                        payments.append({"date": d, "partner": p, "allocations": [(inv, amount)]})
                        d += timedelta(days=int(self.rng.integers(7, 35)))
                else:
                    payments.append({"date": pay_date, "partner": p, "allocations": [(inv, inv["amount_total"])]})
        # A grouped payment occasionally comes from non-batch payers too.
        return payments

    def _batch_payments(self, partner, invs):
        payments = []
        day = int(self.rng.integers(25, 31))
        cursor = 0
        invs = sorted(invs, key=lambda i: i["invoice_date"])
        pay_date = _add_months(self.start, 1) + timedelta(days=day - 1)
        while cursor < len(invs) and pay_date <= self.end + timedelta(days=60):
            batch = []
            while cursor < len(invs) and invs[cursor]["invoice_date"] + timedelta(days=10) <= pay_date:
                if not self._chance(self.cfg.unpaid_share):
                    batch.append(invs[cursor])
                cursor += 1
            # Large batches are split so a transfer covers at most 4 invoices.
            for i in range(0, len(batch), 4):
                chunk = batch[i : i + 4]
                d = pay_date + timedelta(days=int(self.rng.integers(0, 3)))
                payments.append({"date": d, "partner": partner, "allocations": [(x, x["amount_total"]) for x in chunk]})
            pay_date = _add_months(pay_date.replace(day=1), 1) + timedelta(days=min(day, 28) - 1)
        return payments

    # ------------------------------------------------------------------ noise
    def noisy_reference(self, allocations, partner):
        n = self.noise
        if self._chance(n.missing_reference):
            return self._pick(
                [
                    "",
                    "TRANSFER",
                    "PAYMENT",
                    f"TRF {self.rng.integers(10**5, 10**7)}",
                    "حوالة",
                    "دفعة",
                    partner["name_en"].upper()[:20],
                ]
            )
        refs = []
        for inv, _ in allocations:
            number = inv["number"]
            year, seq = number.split("/")[1], int(number.split("/")[2])
            if self._chance(n.reference_format_change):
                number = self._pick([f"inv {seq}", f"INV{year}-{seq}", f"{seq:05d}", f"INV-{seq:05d}", f"فاتورة {seq}"])
            if self._chance(n.reference_typo):
                number = self._typo(number)
            refs.append(number)
        prefix = self._pick(["", "Payment ", "PMT ", "Settlement ", "سداد ", "دفعة "])
        suffix = self._pick(["", "", f" {partner['name_en'].split()[0]}", f" REF{self.rng.integers(1000, 99999)}"])
        return f"{prefix}{' + '.join(refs)}{suffix}".strip()

    def _typo(self, text):
        if len(text) < 3:
            return text
        i = int(self.rng.integers(len(text) - 1))
        op = self.rng.integers(3)
        if op == 0:
            return text[:i] + text[i + 1 :]
        if op == 1:
            return text[:i] + text[i + 1] + text[i] + text[i + 2 :]
        return text[:i] + str(self.rng.integers(10)) + text[i + 1 :]

    def noisy_name(self, partner, all_partners):
        n = self.noise
        if self._chance(n.third_party_payer):
            same_company = [p for p in all_partners if p["company_id"] == partner["company_id"] and p is not partner]
            partner = self._pick(same_company)
        parts = self._name_parts[partner["partner_id"]]
        if self._chance(n.transliteration):
            fam_variant = self._pick(parts["family"][2])
            if "first" in parts:
                name = f"{self._pick(parts['first'][2])} {fam_variant}"
            else:
                name = f"{fam_variant} {parts['activity'][1]}"
        elif self._chance(n.name_language_switch):
            name = partner["name_ar"]
        else:
            name = partner["name_en"]
        if self._chance(n.name_noise):
            op = self.rng.integers(3)
            if op == 0:
                name = name[: int(self.rng.integers(10, 20))]
            elif op == 1:
                for w in ("شركة ", "مؤسسة ", " Co.", " Est.", " Group"):
                    name = name.replace(w, "")
            else:
                name = name.replace("ة", "ه").replace("أ", "ا").replace("إ", "ا").replace("ى", "ي")
        if not any("؀" <= c <= "ۿ" for c in name) and self._chance(0.6):
            name = name.upper()  # banks often print Latin names in capitals
        return name[:35]

    # ------------------------------------------------------------------ assemble
    def generate(self):
        companies = self.make_companies()
        partners = self.make_partners(companies)
        invoices = self.make_invoices(companies, partners)
        payments = [p for p in self.plan_payments(partners, invoices) if p["date"] <= self.end]
        payments.sort(key=lambda p: (p["date"], p["partner"]["partner_id"]))

        lines, matches = [], []
        lid = 1
        for pay in payments:
            p = pay["partner"]
            currency = pay["allocations"][0][0]["currency"]
            dec = DECIMALS[currency]
            amount = sum(a for _, a in pay["allocations"])
            if self._chance(self.noise.bank_fee):
                amount -= float(np.round(self.rng.uniform(*FEES[currency]), 0))
            elif self._chance(self.noise.rounding_difference):
                amount += float(self.rng.choice([-1, 1]) * self.rng.uniform(0.01, 1.0))
            lines.append(
                {
                    "line_id": lid,
                    "company_id": p["company_id"],
                    "date": pay["date"],
                    "amount": float(np.round(max(amount, 0.5), dec)),
                    "payment_ref": self.noisy_reference(pay["allocations"], p),
                    "partner_name_raw": self.noisy_name(p, partners),
                    "currency": currency,
                }
            )
            for inv, alloc in pay["allocations"]:
                matches.append({"line_id": lid, "invoice_id": inv["invoice_id"], "allocated_amount": alloc})
            lid += 1

        # Incoming lines with no invoice: transfers, deposits, refunds from suppliers.
        n_unmatched = int(len(lines) * self.noise.unmatched_line_rate)
        total_days = (self.end - self.start).days
        for _ in range(n_unmatched):
            comp = self._pick(companies)
            lines.append(
                {
                    "line_id": lid,
                    "company_id": comp["company_id"],
                    "date": self.start + timedelta(days=int(self.rng.integers(total_days))),
                    "amount": float(np.round(self.rng.lognormal(6.5, 1.0), DECIMALS[comp["currency"]])),
                    "payment_ref": self._pick(
                        [
                            "INTERNAL TRANSFER",
                            "CASH DEPOSIT",
                            "Supplier refund",
                            "إيداع نقدي",
                            "تحويل داخلي",
                            f"POS SETTLEMENT {self.rng.integers(10**5, 10**6)}",
                        ]
                    ),
                    "partner_name_raw": self._pick(["", comp["name"].upper(), "CASH", "VISA SETTLEMENT"]),
                    "currency": comp["currency"],
                }
            )
            lid += 1
        lines.sort(key=lambda r: (r["date"], r["line_id"]))
        return {
            "companies": pd.DataFrame(companies),
            "partners": pd.DataFrame(partners),
            "invoices": pd.DataFrame(invoices),
            "bank_lines": pd.DataFrame(lines),
            "matches": pd.DataFrame(matches),
        }


def save(dataset: dict, out: Path, config: GeneratorConfig):
    out.mkdir(parents=True, exist_ok=True)
    for name, df in dataset.items():
        df.to_parquet(out / f"{name}.parquet", index=False)
    (out / "config.json").write_text(json.dumps(asdict(config), indent=2, default=str))


def load(path: Path) -> dict:
    path = Path(path)
    data = {
        name: pd.read_parquet(path / f"{name}.parquet")
        for name in ("companies", "partners", "invoices", "bank_lines", "matches")
    }
    for df, cols in ((data["invoices"], ["invoice_date", "due_date"]), (data["bank_lines"], ["date"])):
        for c in cols:
            df[c] = pd.to_datetime(df[c]).dt.date
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("data/generated/v1"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--partners", type=int, default=80, help="partners per company")
    parser.add_argument("--months", type=int, default=24)
    args = parser.parse_args(argv)
    config = GeneratorConfig(seed=args.seed, partners_per_company=args.partners, months=args.months)
    dataset = Generator(config).generate()
    save(dataset, args.out, config)
    for name, df in dataset.items():
        print(f"{name}: {len(df)} rows")


if __name__ == "__main__":
    main()
