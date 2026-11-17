"""Deterministic checks that LLM-cited "CV evidence" really comes from the CV.

Job Matching already resolves evidence through ID catalogs. The free-text
agents (cover letter, career advice, CV analysis) return evidence as text, so
it is verified here against the candidate's own CV content (BUG-015).

A claim is grounded when
* every number it states appears in the CV (a "N years" figure must be
  supported by the CV's computed total experience), and
* its distinctive *anchor* words - technology names, organisations, degrees,
  any word that is not common Vietnamese/English vocabulary - appear in the
  CV. Ordinary words are ignored so that a faithful translation of CV content
  ("Built REST APIs with FastAPI" -> "Xây dựng REST API với FastAPI") is
  still accepted.
Claims without anchors fall back to word overlap. Ungrounded evidence is
dropped and reported as a warning; output is never "corrected" with invented
content.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from typing import Any

from app.schemas.cv_profile import CVProfile

_TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9+#]*(?:\.[a-z0-9+#]+)*")
_RAW_TOKEN_PATTERN = re.compile(r"[^\W_][\w+#]*(?:\.[\w+#]+)*", re.UNICODE)
_NUMBER_PATTERN = re.compile(r"^\d+(?:[.,]\d+)?$")
_YEARS_CLAIM_PATTERN = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*\+?\s*(?:năm|nam|years?|yrs?)\b", re.IGNORECASE
)

# Common vocabulary (accent-folded) that is never evidence by itself.
_COMMON_WORDS = frozenset(
    """
    a an and as at be by for from has have i in is it my of on or the to with
    over into via per about across within than more most very also both all
    using use used work worked working experience experienced year years yrs
    skill skills knowledge strong good solid team project projects build built
    develop developed developing design designed implement implemented create
    created lead led manage managed improve improved reduce reduced increase
    increased deliver delivered support supported maintain maintained system
    systems application applications product products feature features service
    services company role position job responsible responsibility
    va voi cua cho tai trong cac nhung la co duoc mot nhieu da dang khi tu den
    nam thang kinh nghiem lam viec ky nang du an kien thuc tot su toi minh ban
    xay dung phat trien thiet ke trien khai quan ly cai thien giam tang toi uu
    he thong ung dung san pham tinh nang dich vu cong ty vi tri nhom doi
    bang cu nhan thac si tien khoa hoc may tinh nganh chuyen truong dai hoc
    cong nghe thong tin ngon ngu tieng anh lap trinh phan mem do tre hieu suat
    su dung thuc hien tham gia ho tro bao tri van hanh nguoi dung khach hang
    """.split()
)
_MIN_GROUNDED_RATIO = 0.6


def fold_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    folded = "".join(char for char in decomposed if not unicodedata.combining(char))
    return folded.replace("đ", "d")


def _key(token: str) -> str:
    """Light plural folding so "APIs" supports "API" and vice versa."""
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _tokens(value: str) -> list[str]:
    return _TOKEN_PATTERN.findall(fold_text(value))


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item)


def _number_value(token: str) -> float:
    return float(token.replace(",", "."))


def _has_diacritics(token: str) -> bool:
    return fold_text(token) != token.casefold() or "đ" in token.casefold()


class CVGroundingChecker:
    """Verifies free-text claims against one CV profile."""

    def __init__(self, profile: CVProfile) -> None:
        # Local import: keeps the schema -> utils import graph acyclic.
        from app.services.job_matching_context import calculate_total_experience_years

        payload = profile.model_dump(
            mode="json",
            exclude={"personal_information": {"email", "phone", "linkedin_url",
                                              "github_url", "portfolio_url"}},
            exclude_none=True,
        )
        texts = list(_strings(payload))
        self._corpus = " \n ".join(fold_text(text) for text in texts)
        self._keys = {_key(token) for text in texts for token in _tokens(text)}
        self.total_years = calculate_total_experience_years(profile)
        self.full_name = profile.personal_information.full_name

    def _year_claims_grounded(self, claim: str) -> tuple[bool, set[str]]:
        """Check "N years/năm" figures against the CV's total experience."""
        figures: set[str] = set()
        for match in _YEARS_CLAIM_PATTERN.finditer(claim):
            figures.add(match.group(1))
            if match.group(1) in self._keys:
                continue
            value = _number_value(match.group(1))
            if self.total_years is None or value > self.total_years + 0.5:
                return False, figures
        return True, figures

    def is_grounded(self, claim: str) -> bool:
        folded = fold_text(claim).strip()
        if not folded or folded in self._corpus:
            return True

        years_ok, year_figures = self._year_claims_grounded(claim)
        if not years_ok:
            return False

        numbers = [t for t in _tokens(claim) if _NUMBER_PATTERN.match(t)]
        if any(n not in self._keys for n in numbers if n not in year_figures):
            return False

        raw_tokens = _RAW_TOKEN_PATTERN.findall(claim)
        anchors = [
            _key(fold_text(token))
            for token in raw_tokens
            if not _NUMBER_PATTERN.match(token)
            and not _has_diacritics(token)
            and len(token) > 1
            and fold_text(token) not in _COMMON_WORDS
        ]
        if anchors:
            present = sum(1 for anchor in anchors if anchor in self._keys)
            return present / len(anchors) >= _MIN_GROUNDED_RATIO

        if numbers:
            # Only common words plus numbers that all occur in the CV, e.g.
            # "Giảm độ trễ hệ thống 30%" for "Reduced latency by 30%".
            return True

        words = [_key(t) for t in _tokens(claim) if len(t) > 1]
        if not words:
            return True
        present = sum(1 for word in words if word in self._keys)
        return present / len(words) >= _MIN_GROUNDED_RATIO

    def split(self, claims: Iterable[str]) -> tuple[list[str], list[str]]:
        grounded: list[str] = []
        ungrounded: list[str] = []
        for claim in claims:
            (grounded if self.is_grounded(claim) else ungrounded).append(claim)
        return grounded, ungrounded

    def overstated_years(self, text: str) -> list[float]:
        """Years-of-experience figures in ``text`` that the CV cannot support."""
        overstated: list[float] = []
        for match in _YEARS_CLAIM_PATTERN.finditer(text):
            value = _number_value(match.group(1))
            if self.total_years is None or value > self.total_years + 0.5:
                overstated.append(value)
        return overstated
