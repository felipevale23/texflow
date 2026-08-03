import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def _run(cmd: list[str]) -> int:
    return subprocess.run(cmd, cwd=ROOT, check=False).returncode


def lint() -> None:
    sys.exit(_run(["ruff", "check", "src"]))


def lint_fix() -> None:
    sys.exit(_run(["ruff", "check", "--fix", "src"]))


def format_() -> None:
    sys.exit(_run(["ruff", "format", "src"]))


def format_check() -> None:
    sys.exit(_run(["ruff", "format", "--check", "src"]))


def test() -> None:
    sys.exit(_run(["pytest"]))


def build_dist() -> None:
    sys.exit(_run(["uv", "build"]))


def clean() -> None:
    for path in (ROOT / "dist", ROOT / "build", ROOT / "src" / "TexFlow.egg-info"):
        shutil.rmtree(path, ignore_errors=True)
    for cache in ROOT.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)


def check() -> None:
    commands = [
        ["ruff", "check", "src"],
        ["ruff", "format", "--check", "src"],
        ["pytest"],
    ]
    code = 0
    for cmd in commands:
        result = _run(cmd)
        if result != 0:
            code = result
    sys.exit(code)
