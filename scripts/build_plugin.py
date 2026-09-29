"""Validate and build a reproducible QGIS plugin ZIP."""

import argparse
import configparser
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "kakao_qgis_bridge"
REQUIRED = {"__init__.py", "metadata.txt", "plugin.py", "icon.png"}
EXCLUDED_NAMES = {"settings.json", ".gitignore"}


def validate():
    missing = sorted(name for name in REQUIRED if not (PLUGIN / name).is_file())
    if missing:
        raise SystemExit(f"Missing required plugin files: {', '.join(missing)}")
    metadata = configparser.ConfigParser()
    metadata.read(PLUGIN / "metadata.txt", encoding="utf-8")
    required_fields = {
        "name",
        "version",
        "qgisminimumversion",
        "qgismaximumversion",
        "description",
        "author",
    }
    present = {key.lower() for key in metadata["general"]}
    missing_fields = sorted(required_fields - present)
    if missing_fields:
        raise SystemExit(f"Missing metadata fields: {', '.join(missing_fields)}")


def included_files():
    for path in sorted(PLUGIN.rglob("*")):
        if not path.is_file():
            continue
        if path.name in EXCLUDED_NAMES or path.suffix in {".pyc", ".pyo"}:
            continue
        if "__pycache__" in path.parts:
            continue
        yield path


def build(output):
    validate()
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED, compresslevel=9) as archive:
        for path in included_files():
            relative = path.relative_to(ROOT).as_posix()
            info = ZipInfo(relative, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "dist" / "kakao_qgis_bridge.zip",
    )
    args = parser.parse_args()
    output = build(args.output.resolve())
    print(output)


if __name__ == "__main__":
    main()
