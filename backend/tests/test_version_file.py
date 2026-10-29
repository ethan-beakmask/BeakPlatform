import re
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.module_loader import ModuleLoader


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_version_file_exists_and_is_semver():
    version_file = REPO_ROOT / "VERSION"
    assert version_file.is_file()
    assert re.fullmatch(r"\d+\.\d+\.\d+", version_file.read_text(encoding="utf-8").strip())


def test_pyproject_version_matches_version_file():
    version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    with (REPO_ROOT / "pyproject.toml").open("rb") as pyproject_file:
        pyproject = tomllib.load(pyproject_file)
    assert pyproject["project"]["version"] == version


def test_module_loader_version_matches_version_file():
    version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert ModuleLoader.PLATFORM_VERSION == version
