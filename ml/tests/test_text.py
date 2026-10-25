import pytest
from smart_reconcile_ml.text import name_similarity, normalize_name, reference_features, skeleton


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("شركة النور للتجارة", "Al Nour Trading Co."),
        ("ALNOOR TRADING", "Al Nour Trading Co."),
        ("El-Nour", "النور"),
        ("مؤسسه العتيبي للادويه", "مؤسسة العتيبي للأدوية"),
        ("MHD ALKHATEEB", "Mohammad Al-Khatib Est."),
    ],
)
def test_same_partner_scores_high(a, b):
    assert name_similarity(a, b) >= 0.85


def test_different_partners_score_low():
    assert name_similarity("Al Nour Trading Co.", "Al Hayat Pharmacy") < 0.6


def test_arabic_letter_variants_are_unified():
    assert normalize_name("أحمد") == normalize_name("احمد")
    assert skeleton("النور") == skeleton("Al-Noor")


@pytest.mark.parametrize(
    ("ref", "exact", "seq"),
    [
        ("Payment INV/2025/00042", 1.0, 1.0),
        ("inv 42", 0.0, 1.0),
        ("INV2025-00042", 1.0, 1.0),
        ("فاتورة ٤٢", 0.0, 1.0),
        ("TRF 884213", 0.0, 0.0),
        ("", 0.0, 0.0),
    ],
)
def test_reference_features(ref, exact, seq):
    f = reference_features(ref, "INV/2025/00042")
    assert (f["ref_exact"], f["ref_seq_match"]) == (exact, seq)
