"""Shared, Qt-free catalog parsing and validation (issue #496).

The source inventory is built independently by i18n_sources. Catalog contents
never determine which messages the application requires.
"""

from __future__ import annotations

import re
import string
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, order=True)
class Key:
    context: str
    source: str
    comment: str = ""


@dataclass
class Message:
    key: Key
    translation: str
    state: str = ""
    numerus: bool = False
    locations: list[tuple[str, str]] = field(default_factory=list)


class CatalogError(ValueError):
    """A first-party source/catalog does not satisfy the translation contract."""


def describe(key: Key) -> str:
    suffix = f" (comment={key.comment!r})" if key.comment else ""
    return f"[{key.context}] {key.source!r}{suffix}"


def read_catalog(path: Path) -> tuple[str, list[Message]]:
    """Preserve records (including duplicates) so validation cannot hide them."""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise CatalogError(f"{path}: cannot read catalog: {exc}") from exc
    if root.tag != "TS":
        raise CatalogError(f"{path}: expected a TS document")
    messages = []
    for context in root.findall("context"):
        name = context.findtext("name", "")
        for node in context.findall("message"):
            translation = node.find("translation")
            state = translation.get("type", "") if translation is not None else "missing"
            if not name or not node.findtext("source"):
                raise CatalogError(f"{path}: empty context/source")
            if (
                translation is not None
                and list(translation)
                and state not in {"obsolete", "vanished"}
            ):
                # The current compiler is singular-only. Never flatten plural
                # forms/length variants into an apparently completed message.
                raise CatalogError(f"{path}: unsupported plural/variant translation in {name}")
            messages.append(
                Message(
                    Key(name, node.findtext("source", ""), node.findtext("comment", "")),
                    translation.text or "" if translation is not None else "",
                    state,
                    node.get("numerus", "no") == "yes",
                    [
                        (loc.get("filename", ""), loc.get("line", ""))
                        for loc in node.findall("location")
                    ],
                )
            )
    return root.get("language", ""), messages


def _fields(text: str) -> Counter[tuple[str, str | None, str]]:
    """Include conversions/specs and recursively nested format fields."""
    result: Counter[tuple[str, str | None, str]] = Counter()
    for _, name, spec, conversion in string.Formatter().parse(text):
        if name is not None:
            result[name, conversion, spec] += 1
            result.update(_fields(spec))
    return result


def placeholder_error(source: str, translation: str) -> str | None:
    # UI prose can contain literal braces (e.g. documentation/examples). Only
    # treat valid Python format strings as such; an invalid target paired with
    # a valid source containing fields is still an error.
    try:
        original = _fields(source)
    except ValueError:
        original = Counter()
    try:
        target = _fields(translation)
    except ValueError:
        return "malformed Python format placeholders" if original else None
    if original != target:
        return "Python format placeholders/conversions/specifications differ"
    token = r"(?<!%)%(?:L?[1-9][0-9]*|L?n)"
    if Counter(re.findall(token, source)) != Counter(re.findall(token, translation)):
        return "Qt placeholders differ"
    return None


def validate_messages(messages: list[Message], locale: str) -> list[str]:
    errors = []
    seen: set[Key] = set()
    for message in messages:
        if message.state in {"vanished", "obsolete"}:
            continue
        prefix = f"{locale}: {describe(message.key)}"
        if message.key in seen:
            errors.append(f"{prefix}: duplicate active key")
        seen.add(message.key)
        if message.numerus:
            errors.append(
                f"{prefix}: numerus is unsupported by the compiler; add tested plural support first"
            )
        if message.state:
            errors.append(f"{prefix}: translation is {message.state}")
        if not message.translation.strip():
            errors.append(f"{prefix}: empty translation")
        elif error := placeholder_error(message.key.source, message.translation):
            errors.append(f"{prefix}: {error}")
        if locale == "en" and message.translation != message.key.source:
            errors.append(f"{prefix}: English template must contain the source identity")
    return errors


def active_messages(messages: list[Message]) -> list[Message]:
    return [message for message in messages if message.state not in {"vanished", "obsolete"}]
