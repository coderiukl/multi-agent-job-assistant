"""Comparison keys for skill names.

``normalize_deduplication_text`` drops every non-alphanumeric character, which
collapses "C++", "C#" and "C" (also "F#"/"F", ".NET"/"NET") into the same key,
so a skill filter for "C++" also matched C# jobs. Symbol-bearing technology
names are rewritten to words first. ``normalized_skill_sql`` in
``app/repositories/postgres_job_search.py`` applies the same replacements in
SQL and must stay in sync with :data:`SKILL_KEY_REPLACEMENTS`.
"""

from app.utils.job_deduplication import normalize_deduplication_text

# Applied in this order on the lower-cased value.
SKILL_KEY_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("c++", " cpp "),
    ("c#", " csharp "),
    ("f#", " fsharp "),
    (".net", " dotnet "),
)


def skill_key(value: str) -> str:
    lowered = value.casefold()

    for symbol, replacement in SKILL_KEY_REPLACEMENTS:
        lowered = lowered.replace(symbol, replacement)

    return normalize_deduplication_text(lowered)
