"""Create a self-contained source bundle and refresh public-safe static evidence."""

import hashlib
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site/dist"
DOCS = ("README.md", "VALIDATION.md", "ENGINEERING.md", "SNOWFLAKE.md", "LICENSE")
SITE.mkdir(parents=True, exist_ok=True)
shutil.copytree(ROOT / "demo", SITE, dirs_exist_ok=True)
shutil.copytree(ROOT / "docs", SITE / "docs", dirs_exist_ok=True)
(SITE / ".nojekyll").touch()
for name in DOCS:
    shutil.copyfile(ROOT / name, SITE / name)
shutil.copytree(ROOT / "evidence", SITE / "evidence", dirs_exist_ok=True)
cases = json.loads((ROOT / "examples/cases.json").read_text())
data = {
    "summary": json.loads((ROOT / "evidence/summary.json").read_text()),
    "reports": {
        c["id"]: json.loads((ROOT / "evidence" / c["id"] / "report.json").read_text())
        for c in cases
    },
}
(SITE / "data.js").write_text(
    "window.FLOE_DATA = " + json.dumps(data, separators=(",", ":")) + ";\n"
)
page = (SITE / "index.html").read_text()
for asset in ("app.js", "data.js", "style.css"):
    version = hashlib.sha256((SITE / asset).read_bytes()).hexdigest()[:12]
    page = page.replace(f'"{asset}"', f'"{asset}?v={version}"')
(SITE / "index.html").write_text(page)
paths = [ROOT / p for p in (*DOCS, "pyproject.toml", ".gitignore", ".gitattributes")]
for folder in ("src", "tests", "scripts", "examples", "evidence", "demo", "docs", ".github"):
    paths += [p for p in (ROOT / folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts]
manifest = {
    str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)
}
with zipfile.ZipFile(SITE / "floe-source.zip", "w", zipfile.ZIP_DEFLATED) as archive:
    for p in sorted(paths):
        info = zipfile.ZipInfo(
            "floe/" + str(p.relative_to(ROOT)), date_time=(2026, 10, 15, 0, 0, 0)
        )
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        archive.writestr(info, p.read_bytes())
    archive.writestr("floe/SOURCE-MANIFEST.json", json.dumps(manifest, indent=2) + "\n")
archive_hash = hashlib.sha256((SITE / "floe-source.zip").read_bytes()).hexdigest()
(SITE / "floe-source.zip.sha256").write_text(archive_hash + "  floe-source.zip\n")
print(
    json.dumps(
        {
            "files": len(paths) + 1,
            "archive_sha256": archive_hash,
            "bytes": (SITE / "floe-source.zip").stat().st_size,
        }
    )
)
