"""Fail if anything that looks like a secret is in source, docs or fixtures (not .env)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {
    ".venv",
    "node_modules",
    "staticfiles",
    "media",
    ".test-media",
    "__pycache__",
    ".pytest_cache",
    "htmlcov",
    "test-results",
    "playwright-report",
    ".git",
}
SKIP_FILES = {".env", ".env.example"}
PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"tvly-[A-Za-z0-9_-]{16,}"),
    re.compile(r"pk\.eyJ[A-Za-z0-9._-]{20,}"),
    re.compile(r"(?i)(api[_-]?key|secret|token)\s*[=:]\s*['\"][A-Za-z0-9_\-]{24,}['\"]"),
    re.compile(r"\b[a-f0-9]{32}\b(?=.*(?i:key))"),
]
TEXT = {
    ".py",
    ".md",
    ".html",
    ".js",
    ".css",
    ".json",
    ".toml",
    ".yml",
    ".yaml",
    ".txt",
    ".sh",
    ".cfg",
    ".ini",
    "",
}


def main() -> int:
    env_values = set()
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                name, value = (part.strip() for part in line.split("=", 1))
                secretish = any(w in name for w in ("KEY", "SECRET", "TOKEN", "PASSWORD"))
                if secretish and len(value) >= 16:
                    env_values.add(value)
    hits = []
    for path in ROOT.rglob("*"):
        if path.is_dir() or path.name in SKIP_FILES or set(path.parts) & SKIP_DIRS:
            continue
        if path.suffix not in TEXT or path.stat().st_size > 2_000_000:
            continue
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        for value in env_values:
            if value in text:
                hits.append(f"{path.relative_to(ROOT)}: contains a value from .env")
        for pat in PATTERNS:
            if pat.search(text):
                hits.append(f"{path.relative_to(ROOT)}: matches {pat.pattern[:30]}")
    for h in hits:
        print(h)
    print("secret scan:", "FAIL" if hits else "clean")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
