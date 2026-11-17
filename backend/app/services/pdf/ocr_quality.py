"""OCR quality checks that the recognizer's own confidence cannot provide.

The PaddleOCR recognition models used here (PP-OCRv6_*_rec, and also
PP-OCRv5_*_rec and latin_PP-OCRv5_mobile_rec) have no glyphs for most
Vietnamese tone-marked letters (ạ ả ầ ấ ậ ẩ ẫ ằ ắ ặ ẹ ẻ ẽ ề ế ệ ị ỉ ọ ỏ ồ ố ộ
ổ ỗ ờ ớ ợ ở ỡ ụ ủ ừ ứ ự ử ữ ỳ ỵ ỷ ỹ ...). Those letters are silently dropped
("Kinh nghiệm" -> "Kinh nghim") while the per-line confidence stays near 1.0,
so a low-confidence rule never fires (BUG-026). Vietnamese pages are
therefore detected from the letters the model *can* still produce and are
flagged for review instead of being passed on as trustworthy text.
"""

from __future__ import annotations

import re
import unicodedata

VIETNAMESE_DIACRITICS_UNSUPPORTED = "vietnamese_diacritics_unsupported"
# Kept below the 0.7 review threshold used for CV provenance.
LOSSY_OCR_CONFIDENCE_CAP = 0.5

# Letters that exist (in Latin script) essentially only in Vietnamese.
_STRONG_MARKERS = frozenset("ăơưđĂƠƯĐ")
# Frequent Vietnamese syllables in CVs (accent-folded), as whole words.
_VIETNAMESE_WORDS = frozenset(
    """
    kinh nghiem cong ty nam thang tai va cua cac nhung hoc van ky nang du an
    chuyen nganh truong dai cu nhan thac si lam viec vi tri muc tieu nghe
    nghiep thong tin ca nhan so thich du an hien tai
    """.split()
)
_WORD_PATTERN = re.compile(r"[a-z]+")


def _fold(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c)).replace(
        "đ", "d"
    )


def looks_vietnamese(text: str) -> bool:
    """True when OCR text is (at least partly) Vietnamese."""
    if not text:
        return False
    strong = sum(1 for char in text if char in _STRONG_MARKERS)
    words = _WORD_PATTERN.findall(_fold(text))
    vietnamese_words = sum(1 for word in words if word in _VIETNAMESE_WORDS)
    return (
        strong >= 2
        or (strong >= 1 and vietnamese_words >= 2)
        or vietnamese_words >= 4
    )


def ocr_quality_issues(text: str) -> tuple[str, ...]:
    return (VIETNAMESE_DIACRITICS_UNSUPPORTED,) if looks_vietnamese(text) else ()
