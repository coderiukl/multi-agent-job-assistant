"""Skill taxonomy: canonical skill names for jobs, CVs and search filters.

Source "skills" are a mix of real skills ("ReactJS", "PostgreSql"), job
categories ("Sales", "Developer", "Customer Support & Success") and noise
("Remote", "Berlin", "Fresher Accepted"). Every label is classified as

* ``skill``     -> replaced by its canonical name ("ReactJS" -> "React"),
* ``category``  -> moved to ``source_metadata.job_categories``,
* ``ignored``   -> dropped,
* ``unmapped``  -> kept as-is and reported (``mart_unmapped_skills``) so the
  taxonomy can be extended.

Canonical skills are also extracted from the job title/description with
conservative patterns (``text`` / ``text_cs`` in the taxonomy file).
The taxonomy lives in ``app/data/skill_taxonomy.json``; bump its ``version``
on every change: it is part of the job content hash, so
``reprocess-raw-jobs`` rewrites (and re-indexes) the affected jobs.
"""

import html
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.utils.skill_keys import skill_key

DEFAULT_TAXONOMY_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "skill_taxonomy.json"
)
MAX_SKILLS_PER_JOB = 50

# Word boundaries that also treat the symbols of "C++", "C#", ".NET" as part
# of a token, so "C" does not match inside "C++" and ".NET" not in "ASP.NET".
_BOUNDARY_BEFORE = r"(?<![\w+#.])"
_BOUNDARY_AFTER = r"(?![\w+#])"


@dataclass(frozen=True)
class SkillNormalization:
    skills: list[str]
    categories: list[str] = field(default_factory=list)
    unmapped: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SkillDefinition:
    name: str
    category: str
    aliases: tuple[str, ...]


def clean_label(value: str) -> str:
    """Unescape HTML entities ("&amp;") and collapse whitespace."""
    return " ".join(html.unescape(value).split())


def _compile_alternation(
    phrases: dict[str, str], *, ignore_case: bool
) -> re.Pattern[str] | None:
    if not phrases:
        return None
    # Longest first so "React Native" wins over "React".
    ordered = sorted(phrases, key=len, reverse=True)
    body = "|".join(re.escape(phrase) for phrase in ordered)
    flags = re.IGNORECASE if ignore_case else 0
    return re.compile(f"{_BOUNDARY_BEFORE}(?:{body}){_BOUNDARY_AFTER}", flags)


class SkillTaxonomy:
    def __init__(self, data: dict[str, Any]) -> None:
        self.version: str = data["version"]
        self.skills: dict[str, SkillDefinition] = {}
        self._skill_by_key: dict[str, str] = {}
        self._category_keys: dict[str, str] = {}
        self._ignored_keys: set[str] = set()
        text_ci: dict[str, str] = {}
        text_cs: dict[str, str] = {}

        for entry in data["skills"]:
            definition = SkillDefinition(
                name=entry["name"],
                category=entry.get("category", "other"),
                aliases=tuple(entry.get("aliases", [])),
            )
            if definition.name in self.skills:
                raise ValueError(f"Duplicate skill in taxonomy: {definition.name}")
            self.skills[definition.name] = definition

            for label in (definition.name, *definition.aliases):
                self._register(
                    self._skill_by_key, skill_key(label), definition.name, label
                )

            text = entry.get("text", True)
            phrases = (
                [definition.name, *definition.aliases]
                if text is True
                else list(text) if isinstance(text, list) else []
            )
            for phrase in phrases:
                text_ci.setdefault(phrase.casefold(), definition.name)
            for phrase in entry.get("text_cs", []):
                text_cs.setdefault(phrase, definition.name)

        for label in data.get("category_labels", []):
            key = skill_key(clean_label(label))
            if key in self._skill_by_key:
                raise ValueError(f"Category label {label!r} is also a skill alias.")
            self._category_keys.setdefault(key, clean_label(label))

        for label in data.get("ignored_labels", []):
            key = skill_key(clean_label(label))
            if key in self._skill_by_key or key in self._category_keys:
                raise ValueError(
                    f"Ignored label {label!r} is also a skill or category."
                )
            self._ignored_keys.add(key)

        self._text_ci = text_ci
        self._text_cs = text_cs
        self._pattern_ci = _compile_alternation(text_ci, ignore_case=True)
        self._pattern_cs = _compile_alternation(text_cs, ignore_case=False)

    @staticmethod
    def _register(index: dict[str, str], key: str, name: str, label: str) -> None:
        if not key:
            raise ValueError(f"Skill label {label!r} has an empty key.")
        existing = index.get(key)
        if existing is not None and existing != name:
            raise ValueError(
                f"Skill alias {label!r} maps to both {existing!r} and {name!r}."
            )
        index[key] = name

    # ------------------------------------------------------------------ lookup
    def canonical_name(self, label: str) -> str | None:
        return self._skill_by_key.get(skill_key(clean_label(label)))

    def is_category(self, label: str) -> bool:
        return skill_key(clean_label(label)) in self._category_keys

    def is_ignored(self, label: str) -> bool:
        return skill_key(clean_label(label)) in self._ignored_keys

    # -------------------------------------------------------------- operations
    def extract_from_text(self, text: str) -> list[str]:
        """Canonical skills mentioned in free text, in order of appearance."""
        if not text:
            return []

        found: list[tuple[int, str]] = []
        if self._pattern_ci is not None:
            for match in self._pattern_ci.finditer(text):
                found.append((match.start(), self._text_ci[match.group(0).casefold()]))
        if self._pattern_cs is not None:
            for match in self._pattern_cs.finditer(text):
                found.append((match.start(), self._text_cs[match.group(0)]))

        found.sort(key=lambda item: item[0])
        return list(dict.fromkeys(name for _, name in found))

    def normalize(
        self,
        labels: list[str],
        *,
        text: str = "",
        categories: list[str] | None = None,
    ) -> SkillNormalization:
        """Classify source labels; add skills found in ``text``.

        Source-provided skills come first (they are the most reliable), then
        skills extracted from the text; capped at ``MAX_SKILLS_PER_JOB``.
        """
        skills: dict[str, None] = {}
        found_categories: dict[str, str] = {}
        unmapped: dict[str, str] = {}

        for raw in categories or []:
            label = clean_label(str(raw))
            if label:
                found_categories.setdefault(label.casefold(), label)

        for raw in labels:
            label = clean_label(str(raw))
            if not label:
                continue
            key = skill_key(label)
            canonical = self._skill_by_key.get(key)
            if canonical is not None:
                skills[canonical] = None
            elif key in self._category_keys:
                found_categories.setdefault(label.casefold(), label)
            elif key in self._ignored_keys or not key:
                continue
            else:
                unmapped.setdefault(key, label)

        # Unmapped labels stay skills (no information is lost) after the
        # canonical ones, deduplicated by skill key.
        for label in unmapped.values():
            if skill_key(label) not in {skill_key(name) for name in skills}:
                skills[label] = None

        for name in self.extract_from_text(text):
            skills.setdefault(name, None)

        return SkillNormalization(
            skills=list(skills)[:MAX_SKILLS_PER_JOB],
            categories=list(found_categories.values()),
            unmapped=list(unmapped.values()),
        )

    def normalize_query_skills(self, labels: list[str]) -> tuple[list[str], list[str]]:
        """Skill filter values -> (skill filter, extra keywords).

        Categories (e.g. "Sales" proposed by the query planner) are not
        skills of any job anymore, so they become keywords instead of a hard
        filter that would return nothing. Unknown values are kept.
        """
        skills: dict[str, None] = {}
        keywords: dict[str, None] = {}

        for raw in labels:
            label = clean_label(str(raw))
            if not label:
                continue
            canonical = self.canonical_name(label)
            if canonical is not None:
                skills[canonical] = None
            elif self.is_category(label) or self.is_ignored(label):
                keywords[label] = None
            else:
                skills[label] = None

        return list(skills), list(keywords)


def load_skill_taxonomy_from(path: Path) -> SkillTaxonomy:
    with path.open(encoding="utf-8") as handle:
        return SkillTaxonomy(json.load(handle))


@lru_cache(maxsize=1)
def get_skill_taxonomy() -> SkillTaxonomy:
    return load_skill_taxonomy_from(DEFAULT_TAXONOMY_PATH)
