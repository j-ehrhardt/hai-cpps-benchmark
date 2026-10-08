"""Build the GitHub Pages site from the editable files in ``_sources``."""

from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILES = ROOT / "_sources"


def main() -> int:
    with TemporaryDirectory(prefix="hai-cpps-docs-") as temporary:
        temporary = Path(temporary)
        source = temporary / "source"
        source.mkdir()

        for path in SOURCE_FILES.rglob("*.txt"):
            target = source / path.relative_to(SOURCE_FILES).with_suffix("")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)

        for asset_dir in ("_static", "_images"):
            source_asset_dir = ROOT / asset_dir
            if source_asset_dir.exists():
                shutil.copytree(source_asset_dir, source / asset_dir)

        shutil.copy2(ROOT / "docs" / "conf.py", source / "conf.py")

        command = [
            sys.executable,
            "-m",
            "sphinx",
            "-b",
            "html",
            "-W",
            "--keep-going",
            "-c",
            str(source),
            "-d",
            str(temporary / "doctrees"),
            str(source),
            str(ROOT),
        ]
        subprocess.run(command, check=True, cwd=ROOT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
