"""Text normalization and similarity for Arabic/English partner names and payment references."""

import re
import unicodedata

from rapidfuzz import fuzz

_ARABIC_DIACRITICS = re.compile("[ً-ْٰـ]")  # harakat, superscript alef, tatweel
_ARABIC_LETTER_VARIANTS = str.maketrans(
    {"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي", "ؤ": "و", "ئ": "ي"}
)
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

# Simple one-way romanization. It is used only to compare names across scripts, not for display.
_ARABIC_TO_LATIN = {
    "ا": "a",
    "ب": "b",
    "ت": "t",
    "ث": "th",
    "ج": "j",
    "ح": "h",
    "خ": "kh",
    "د": "d",
    "ذ": "dh",
    "ر": "r",
    "ز": "z",
    "س": "s",
    "ش": "sh",
    "ص": "s",
    "ض": "d",
    "ط": "t",
    "ظ": "z",
    "ع": "",
    "غ": "gh",
    "ف": "f",
    "ق": "q",
    "ك": "k",
    "ل": "l",
    "م": "m",
    "ن": "n",
    "ه": "h",
    "و": "w",
    "ي": "y",
    "ء": "",
}

# Legal-form and filler words that carry no identity. Compared after normalization.
_STOP_WORDS = {
    "co",
    "company",
    "est",
    "establishment",
    "llc",
    "ltd",
    "inc",
    "corp",
    "group",
    "and",
    "the",
    "for",
    "of",
    "al",
    "el",
    "شركه",
    "مؤسسه",
    "مجموعه",
    "ذمم",
    "و",
}

# Common business words, mapped to one English form so "للتجارة" and "Trading" compare as equal.
# Keys are in normalized form (after normalize_arabic and the "لل" -> "ال" rewrite).
_GLOSSARY = {
    "التجاره": "trading",
    "تجاره": "trading",
    "المقاولات": "contracting",
    "الادويه": "pharma",
    "صيدليه": "pharmacy",
    "الصناعات": "industries",
    "الغذائيه": "food",
    "التكنولوجيا": "technology",
    "السياحه": "tourism",
    "السفر": "travel",
    "الخدمات": "services",
    "اللوجستيه": "logistics",
    "الاستشارات": "consulting",
    "الهندسيه": "engineering",
    "الطباعه": "printing",
    "النشر": "publishing",
    "مطاعم": "restaurants",
    "المطاعم": "restaurants",
    "الاثاث": "furniture",
    "الالكترونيات": "electronics",
    "العقارات": "real estate",
    "النقل": "transport",
    "الكهربائيه": "electrical",
    "الطبيه": "medical",
    "المستلزمات": "supplies",
    "مستلزمات": "supplies",
    "الزراعيه": "agricultural",
    "الاستيراد": "import",
    "التصدير": "export",
    "مكتب": "office",
    "مصنع": "factory",
    "مخابز": "bakeries",
}


def normalize_arabic(text: str) -> str:
    text = _ARABIC_DIACRITICS.sub("", text)
    return text.translate(_ARABIC_LETTER_VARIANTS).translate(_ARABIC_DIGITS)


def has_arabic(text: str) -> bool:
    return any("؀" <= ch <= "ۿ" for ch in text)


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def normalize_name(text: str | None) -> str:
    """Lowercase, unify Arabic letter variants, drop punctuation and legal-form words."""
    if not text:
        return ""
    text = normalize_arabic(_strip_accents(text.lower()))
    text = text.replace("ذ.م.م", " ")
    text = re.sub(r"[^\w\s]", " ", text)
    tokens = []
    for tok in text.split():
        if tok.startswith("لل") and len(tok) > 4:  # "للتجاره" -> "التجاره"
            tok = "ال" + tok[2:]
        tok = _GLOSSARY.get(tok, tok)
        if tok not in _STOP_WORDS:
            tokens.append(tok)
    return " ".join(tokens)


def romanize(text: str) -> str:
    return "".join(_ARABIC_TO_LATIN.get(ch, ch) for ch in text)


def skeleton(text: str | None) -> str:
    """Consonant skeleton that is stable across Arabic script and varied Latin spellings.

    "النور" -> "nr", "Al-Nour" -> "nr", "Alnoor" -> "nr".
    """
    words = []
    for word in normalize_name(text).split():
        if has_arabic(word):
            word = romanize(word)
        word = re.sub(r"^(al|el)(?=[a-z]{2,})", "", word)  # definite article
        word = word.replace("ou", "u").replace("ee", "i").replace("q", "k").replace("kh", "h")
        word = word.replace("dh", "z").replace("th", "t").replace("ph", "f").replace("c", "k")
        word = re.sub(r"[aeiouwy\d_]", "", word)
        word = re.sub(r"(.)\1+", r"\1", word)
        if word:
            words.append(word)
    return " ".join(words)


def name_similarity(a: str | None, b: str | None) -> float:
    """Similarity in [0, 1] using the best of plain and cross-script comparison."""
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    plain = fuzz.token_set_ratio(na, nb)
    sa, sb = skeleton(a), skeleton(b)
    skel = fuzz.token_set_ratio(sa, sb) if sa and sb else 0.0
    return max(plain, skel) / 100.0


def best_name_similarity(raw: str | None, names: list[str | None]) -> float:
    return max((name_similarity(raw, n) for n in names if n), default=0.0)


_NUMBER = re.compile(r"\d+")


def invoice_sequence(number: str) -> tuple[str, int] | None:
    """Split "INV/2025/00042" into ("2025", 42)."""
    nums = _NUMBER.findall(number or "")
    if not nums:
        return None
    year = nums[-2] if len(nums) >= 2 else ""
    return year, int(nums[-1])


def reference_features(ref: str | None, number: str) -> dict[str, float]:
    """How strongly a free-text payment reference points at one invoice number."""
    ref = normalize_arabic(ref or "").upper()
    compact_ref = re.sub(r"[^A-Z0-9]", "", ref)
    compact_num = re.sub(r"[^A-Z0-9]", "", number.upper())
    exact = float(bool(compact_num) and compact_num in compact_ref)
    seq = invoice_sequence(number)
    seq_match = 0.0
    if seq:
        year, n = seq
        ref_numbers = [int(x) for x in _NUMBER.findall(ref) if len(x) <= 7]
        if n in ref_numbers:
            seq_match = 1.0
        elif any(len(x) > 5 and x.endswith(str(n).zfill(5)) for x in _NUMBER.findall(ref)):
            seq_match = 1.0  # "INV2025-00042" glued into one number
    fuzzy = fuzz.partial_ratio(compact_num, compact_ref) / 100.0 if compact_ref and compact_num else 0.0
    return {"ref_exact": exact, "ref_seq_match": seq_match, "ref_fuzzy": fuzzy}
