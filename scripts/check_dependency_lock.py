"""Read-only lock/export consistency gate (#404); never repairs tracked files."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPORT_ARGS = ["export", "--locked", "--all-extras", "--group", "build",
               "--no-emit-project", "--no-header", "--format", "pylock.toml"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--uv", default="uv")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        for name in ("uv.lock", "pylock.toml"):
            if not (root / name).is_file():
                raise ValueError(f"Missing {name}")
        manifest = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        expected = manifest["tool"]["uv"]["required-version"].removeprefix("==")
        version = subprocess.run([args.uv, "--version"], capture_output=True, text=True,
                                 check=True, timeout=30).stdout.split()
        if len(version) < 2 or version[1] != expected:
            raise ValueError("uv does not match the project pin")
        subprocess.run([args.uv, "lock", "--check"], cwd=root, check=True, timeout=180)
        with tempfile.TemporaryDirectory(prefix="ogp-lock-check-") as tmp:
            output = Path(tmp) / "pylock.toml"
            subprocess.run([args.uv, *EXPORT_ARGS, "--output-file", str(output)], cwd=root,
                           capture_output=True, check=True, timeout=180)
            if output.read_bytes() != (root / "pylock.toml").read_bytes():
                raise ValueError("pylock.toml differs from the locked export")
        print("Dependency lock and PEP 751 export agree")
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(f"Dependency lock check failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
