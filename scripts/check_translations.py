"""Read-only source/catalog/binary gate for every registered language (#496)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.i18n_catalog import (
    CatalogError,
    active_messages,
    describe,
    read_catalog,
    validate_messages,
)
from scripts.i18n_sources import inventory, supported_languages


def check(root: Path, *, binaries: bool = True) -> list[str]:
    """Aggregate failures across locales; never synthesize or write translations."""
    from scripts.compile_translations import compile_qm, parse_ts_file

    sources = inventory(root)
    errors = []
    directory = root / "src/open_garden_planner/resources/translations"
    for locale in supported_languages(root):
        path = directory / f"open_garden_planner_{locale}.ts"
        try:
            language, messages = read_catalog(path)
            normalized = language.replace("-", "_").casefold()
            registered = locale.replace("-", "_").casefold()
            if normalized != registered and not normalized.startswith(registered + "_"):
                errors.append(f"{locale}: {path.name}: language metadata is {language!r}")
            locale_errors = validate_messages(messages, locale)
            keys = {message.key for message in active_messages(messages)}
            for key in sorted(sources.keys() - keys):
                locations = ", ".join(f"{file}:{line}" for file, line in sorted(sources[key]))
                locale_errors.append(f"{locale}: missing {describe(key)} ({locations})")
            for key in sorted(keys - sources.keys()):
                locale_errors.append(
                    f"{locale}: extra active key {describe(key)}; retire it or declare its live source"
                )
            errors.extend(locale_errors)
            if binaries and not locale_errors:
                qm = path.with_suffix(".qm")
                try:
                    content = qm.read_bytes()
                except OSError as exc:
                    errors.append(f"{locale}: cannot read compiled catalog: {exc}")
                    continue
                expected = compile_qm(parse_ts_file(path))
                if content != expected:
                    errors.append(
                        f"{locale}: {qm.name} is stale/corrupt; recompile its validated source"
                    )
                    continue
                from PyQt6.QtCore import QTranslator

                translator = QTranslator()
                if not translator.load(str(qm)):
                    errors.append(f"{locale}: Qt cannot load {qm.name}")
                    continue
                for message in active_messages(messages):
                    key = message.key
                    # char* arguments must carry UTF-8, including ellipses and
                    # degree signs in English source text.
                    translated = translator.translate(
                        key.context.encode("utf-8"),
                        key.source.encode("utf-8"),
                        key.comment.encode("utf-8") if key.comment else None,
                    )
                    if translated != message.translation:
                        errors.append(f"{locale}: compiled lookup differs for {describe(key)}")
        except CatalogError as exc:
            errors.append(f"{locale}: {exc}")
    return errors


def main() -> int:
    if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        errors = check(args.root.resolve())
    except (CatalogError, OSError, ValueError, SyntaxError) as exc:
        errors = [str(exc)]
    if errors:
        for error in errors:
            print(error)
        print(f"Translation gate failed: {len(errors)} error(s).")
        return 1
    print(
        "Translation gate passed: all registered locales match current source and compiled catalogs."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
