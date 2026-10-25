from smart_reconcile_ml.generator import Generator, GeneratorConfig, load


def test_generation_is_reproducible():
    a = Generator(GeneratorConfig(seed=3, partners_per_company=5, months=6)).generate()
    b = Generator(GeneratorConfig(seed=3, partners_per_company=5, months=6)).generate()
    assert a["bank_lines"].equals(b["bank_lines"])


def test_dataset_consistency(small_dataset):
    d = load(small_dataset)
    inv = d["invoices"].set_index("invoice_id")
    m = d["matches"]
    assert m["invoice_id"].isin(inv.index).all()
    assert m["line_id"].isin(d["bank_lines"]["line_id"]).all()
    # An invoice is never allocated more than its total.
    allocated = m.groupby("invoice_id")["allocated_amount"].sum()
    assert (allocated <= inv.loc[allocated.index, "amount_total"] + 0.01).all()
    # Every payment happens on or after the invoice date.
    lines = d["bank_lines"].set_index("line_id")
    pay_dates = lines.loc[m["line_id"], "date"].to_numpy()
    assert (pay_dates >= inv.loc[m["invoice_id"], "invoice_date"].to_numpy()).all()
    # The noise includes grouped payments and Arabic names.
    assert (m.groupby("line_id").size() > 1).any()
    assert d["bank_lines"]["partner_name_raw"].str.contains("[؀-ۿ]").any()
