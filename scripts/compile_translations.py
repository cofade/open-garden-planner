"""Compile Qt .ts translation files to binary .qm format.

Pure-Python replacement for Qt's lrelease tool.
Reads XML .ts files and produces .qm files that QTranslator can load.

Usage:
    python scripts/compile_translations.py

This compiles all .ts files in src/open_garden_planner/resources/translations/
to .qm files in the same directory.

References:
    - Qt .ts format: XML with <context>/<message>/<source>/<translation> structure
    - Qt .qm format: Binary with magic 0x3CB86418, tagged sections for hashes + messages
"""

import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# .qm file constants
QM_MAGIC = b"\x3C\xB8\x64\x18\xCA\xEF\x9C\x95\xCD\x21\x1C\xBF\x60\xA1\xBD\xDD"
# Section tags (from Qt's QTranslatorEntryTypes enum)
TAG_CONTEXTS = 0x2F
TAG_HASHES = 0x42
TAG_MESSAGES = 0x69
TAG_NUMERUS_RULES = 0x88
TAG_DEPENDENCIES = 0x96

# Message field tags (inside the messages section)
MSG_END = 0x01
MSG_SOURCE_TEXT_16 = 0x02  # UTF-16BE encoded source
MSG_TRANSLATION = 0x03  # UTF-16BE encoded translation
MSG_CONTEXT_16 = 0x04  # UTF-16BE encoded context
MSG_OBSOLETE = 0x05
MSG_SOURCE_TEXT_8 = 0x06  # UTF-8 encoded source
MSG_CONTEXT_8 = 0x07  # UTF-8 encoded context
MSG_COMMENT_8 = 0x08  # UTF-8 encoded comment

TRANSLATIONS_DIR = (
    Path(__file__).parent.parent
    / "src"
    / "open_garden_planner"
    / "resources"
    / "translations"
)


def _elf_hash(data: bytes) -> int:
    """Compute the ELF hash used by Qt for translation lookups.

    Must emulate C++ uint32 overflow behavior since Python integers
    are arbitrary precision.
    """
    h = 0
    for byte in data:
        h = ((h << 4) + byte) & 0xFFFFFFFF
        g = h & 0xF0000000
        if g:
            h ^= g >> 24
        h &= (~g) & 0xFFFFFFFF
    return h


def _compute_message_hash(source: str, comment: str = "") -> int:
    """Compute the hash for a translation message.

    Qt hashes sourceText + comment (NOT context) for the offset table
    binary search. The hash is guaranteed to be >= 1 (elfHash_finish).
    """
    source_bytes = source.encode("utf-8")
    comment_bytes = comment.encode("utf-8")

    # Qt computes: elfHash_continue(sourceText, h); elfHash_continue(comment, h);
    combined = source_bytes + comment_bytes
    h = _elf_hash(combined)
    # elfHash_finish: ensure hash is never zero
    if h == 0:
        h = 1
    return h


def _encode_utf16(text: str) -> bytes:
    """Encode text as UTF-16BE with explicit byte length (no BOM)."""
    return text.encode("utf-16-be")


def _build_message_entry(
    source: str, translation: str, context: str, comment: str = ""
) -> bytes:
    """Build a single message entry for the messages section."""
    entry = bytearray()

    # Source text (UTF-8, tag 0x06)
    src_bytes = source.encode("utf-8")
    entry.append(MSG_SOURCE_TEXT_8)
    entry.extend(struct.pack(">I", len(src_bytes) + 1))  # +1 for null terminator
    entry.extend(src_bytes)
    entry.append(0)  # null terminator

    # Context (UTF-8, tag 0x07)
    ctx_bytes = context.encode("utf-8")
    entry.append(MSG_CONTEXT_8)
    entry.extend(struct.pack(">I", len(ctx_bytes) + 1))
    entry.extend(ctx_bytes)
    entry.append(0)

    # Comment (UTF-8, tag 0x08) - include if non-empty
    if comment:
        cmt_bytes = comment.encode("utf-8")
        entry.append(MSG_COMMENT_8)
        entry.extend(struct.pack(">I", len(cmt_bytes) + 1))
        entry.extend(cmt_bytes)
        entry.append(0)

    # Translation (UTF-16BE, tag 0x03)
    trans_utf16 = _encode_utf16(translation)
    entry.append(MSG_TRANSLATION)
    entry.extend(struct.pack(">I", len(trans_utf16)))
    entry.extend(trans_utf16)

    # End marker
    entry.append(MSG_END)

    return bytes(entry)


def parse_ts_file(ts_path: Path) -> list[dict[str, str]]:
    """Parse a Qt .ts file and extract all translation messages.

    Returns a list of dicts with keys: context, source, translation, comment.
    Only includes messages where translation is not empty and not marked
    as unfinished with type="unfinished".
    """
    tree = ET.parse(ts_path)
    root = tree.getroot()
    messages = []

    for ctx_elem in root.findall("context"):
        context_name = ctx_elem.findtext("name", "")

        for msg_elem in ctx_elem.findall("message"):
            source = msg_elem.findtext("source", "")
            if not source:
                continue

            trans_elem = msg_elem.find("translation")
            if trans_elem is None:
                continue

            translation = trans_elem.text or ""

            # Skip unfinished translations (empty or marked unfinished)
            trans_type = trans_elem.get("type", "")
            if trans_type == "unfinished" and not translation:
                continue

            # Use translation if available, otherwise fall back to source
            if not translation:
                translation = source

            comment = msg_elem.findtext("comment", "")

            messages.append(
                {
                    "context": context_name,
                    "source": source,
                    "translation": translation,
                    "comment": comment,
                }
            )

    return messages


def compile_qm(messages: list[dict[str, str]]) -> bytes:
    """Compile parsed messages into .qm binary format."""
    # Build message entries and hash table
    msg_data = bytearray()
    hash_entries: list[tuple[int, int]] = []  # (hash, offset)

    for msg in messages:
        offset = len(msg_data)
        h = _compute_message_hash(msg["source"], msg["comment"])
        hash_entries.append((h, offset))
        msg_data.extend(
            _build_message_entry(
                msg["source"], msg["translation"], msg["context"], msg["comment"]
            )
        )

    # Sort hash entries by hash value (Qt requires this for binary search)
    hash_entries.sort(key=lambda x: x[0])

    # Build hash section: pairs of (hash: u32, offset: u32)
    hash_data = bytearray()
    for h, offset in hash_entries:
        hash_data.extend(struct.pack(">II", h, offset))

    # Build the complete .qm file
    output = bytearray()
    output.extend(QM_MAGIC)

    # Hashes section
    output.append(TAG_HASHES)
    output.extend(struct.pack(">I", len(hash_data)))
    output.extend(hash_data)

    # Messages section
    output.append(TAG_MESSAGES)
    output.extend(struct.pack(">I", len(msg_data)))
    output.extend(msg_data)

    return bytes(output)


def compile_ts_file(ts_path: Path) -> Path:
    """Compile a single .ts file to .qm.

    Returns the path to the generated .qm file.
    """
    messages = parse_ts_file(ts_path)
    qm_data = compile_qm(messages)

    qm_path = ts_path.with_suffix(".qm")
    qm_path.write_bytes(qm_data)

    return qm_path


def main() -> int:
    """Compile all .ts files in the translations directory."""
    if not TRANSLATIONS_DIR.exists():
        print(f"Translations directory not found: {TRANSLATIONS_DIR}")
        return 1

    ts_files = sorted(TRANSLATIONS_DIR.glob("*.ts"))
    if not ts_files:
        print(f"No .ts files found in {TRANSLATIONS_DIR}")
        return 1

    errors = 0
    for ts_path in ts_files:
        try:
            qm_path = compile_ts_file(ts_path)
            messages = parse_ts_file(ts_path)
            print(f"  {ts_path.name} -> {qm_path.name} ({len(messages)} messages)")
        except Exception as e:
            print(f"  ERROR compiling {ts_path.name}: {e}")
            errors += 1

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
