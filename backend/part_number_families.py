from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FAMILIES_PATH = ROOT / "config" / "part_number_families.local.json"


@dataclass(frozen=True)
class PartNumberFamily:
    prefix: str
    name: str
    keywords: tuple[str, ...]
    verified: bool
    source: str

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["keywords"] = list(self.keywords)
        return value


FALLBACK_FAMILIES = (
    PartNumberFamily(
        prefix="629",
        name="Bracket",
        keywords=("bracket", "brkt", "mounting bracket"),
        verified=False,
        source="Inferred from the supplied HE115-style workbook; verify against REF0178.",
    ),
)


class PartNumberFamilyCatalog:
    def __init__(self, families: tuple[PartNumberFamily, ...] | None = None):
        self.families = families or load_part_number_families()

    def identify(self, prompt: str, requested_prefix: str = "") -> tuple[PartNumberFamily | None, list[dict[str, Any]]]:
        requested = requested_prefix.strip()
        if requested:
            family = next((item for item in self.families if item.prefix == requested), None)
            return family, [family.to_dict()] if family else []

        normalized = prompt.casefold()
        ranked: list[tuple[int, PartNumberFamily]] = []
        for family in self.families:
            score = sum(len(keyword) for keyword in family.keywords if keyword.casefold() in normalized)
            if score:
                ranked.append((score, family))
        ranked.sort(key=lambda item: (-item[0], item[1].prefix))
        candidates = [family.to_dict() for _score, family in ranked]
        if not ranked:
            return None, []
        if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
            return None, candidates
        return ranked[0][1], candidates


def load_part_number_families() -> tuple[PartNumberFamily, ...]:
    configured = os.environ.get("PART_NUMBER_FAMILIES_PATH", "").strip()
    path = Path(configured) if configured else DEFAULT_FAMILIES_PATH
    if not path.exists():
        return FALLBACK_FAMILIES

    payload = json.loads(path.read_text(encoding="utf-8"))
    values = payload.get("families") if isinstance(payload, dict) else payload
    if not isinstance(values, list):
        raise ValueError("Part-number family config must contain a families list.")

    families = []
    for item in values:
        if not isinstance(item, dict):
            raise ValueError("Each part-number family must be an object.")
        prefix = str(item.get("prefix", "")).strip()
        if len(prefix) != 3 or not prefix.isdigit():
            raise ValueError(f"Invalid part-number family prefix {prefix!r}; expected three digits.")
        keywords = tuple(str(value).strip() for value in item.get("keywords", []) if str(value).strip())
        families.append(
            PartNumberFamily(
                prefix=prefix,
                name=str(item.get("name", prefix)).strip() or prefix,
                keywords=keywords,
                verified=bool(item.get("verified", False)),
                source=str(item.get("source", "Local configuration")).strip(),
            )
        )
    return tuple(families)
