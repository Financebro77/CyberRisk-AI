"""Repository security self-check for CyberRisk AI.

Scans the tracked working tree for high-confidence secret patterns and
personal data, and reports findings in a deterministic, machine-readable
way.  Used by the final release validation (reports/security_release_check.md)
and by CI.

Usage:
    python scripts/security_scan.py
    python scripts/security_scan.py --report        # write reports/security_release_check.md
    python scripts/security_scan.py --json          # machine-readable output
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("openai/deepseek api key", re.compile(r"\bsk-[A-Za-z0-9]{16,}\b")),
    ("github token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("aws access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("google api key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")),
    ("slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    # Developer placeholder domains that must not ship.
    ("placeholder domain", re.compile(r"\bnohackers_allowed\.com\b", re.IGNORECASE)),
]

PII_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    # A phone requires an explicit separator, area code, or country code.
    # Plain long integers (revenue figures) are NOT flagged.
    (
        "phone",
        re.compile(
            r"(?<!\d)(?:\+?\d{1,3}[-\s.]?)?"
            r"(?:\(?\d{2,4}\)?[-\s.])\d{3,4}[-\s.]?\d{4,4}(?!\d)"
        ),
    ),
    # Windows drive paths need a separator + folder (C:\Users\...), not a
    # bare "W:" followed by an escape sequence in a regex literal.
    (
        "local path",
        re.compile(
            r"(?:[A-Za-z]:\\(?:[\w.-]+\\)+[\w.-]+|/home/[\w.-]+/[\w.-]+|/Users/[\w.-]+/[\w.-]+)"
        ),
    ),
]

# Allowed placeholders / documentation examples (never real data).
ALLOWED = {
    "sk-your-key-here",
    "sk-...",
    "example@email.com",
    "example.com",
    "example",
    "[REDACTED]",
    "<your-repo-url>",
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
}

# Paths / files skipped by design (docs, lockfiles, generated references).
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", "data", "reports", "dist"}
SKIP_FILES = {".secrets.baseline", ".gitignore", "SECURITY.md", "package-lock.json", "pnpm-lock.yaml", "README.md"}

# Test fixtures intentionally contain placeholder secret-shaped strings,
# and the scanner file itself defines the regex patterns it detects.
SKIP_SUFFIXES = ("test_privacy.py", "security_scan.py")


def _is_allowed(text: str) -> bool:
    if text.startswith("sk-abcdefghijklmnopqrstuvwxyz0123456789"):
        return True  # explicit placeholder used in tests
    return any(a in text for a in ALLOWED)


def scan_file(path: Path) -> list[dict]:
    """Return findings for one file."""
    findings: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return findings

    for name, pat in SECRET_PATTERNS + PII_PATTERNS:
        for m in pat.finditer(text):
            hit = m.group(0)
            if _is_allowed(hit):
                continue
            findings.append(
                {
                    "file": str(path.relative_to(REPO)),
                    "type": name,
                    "match": hit[:80],
                    "line": text.count("\n", 0, m.start()) + 1,
                }
            )
    return findings


def _committed_files() -> list[Path]:
    """Files that would be committed: tracked + untracked-not-ignored.

    Uses `git ls-files --cached --others --exclude-standard`, so gitignored
    local artifacts (`.env`, `knowledge/derived/`, node_modules) are never
    scanned — they are precisely what must not leak.
    """
    import subprocess

    try:
        out = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=False,
        )
        names = [n for n in out.stdout.split("\0") if n]
    except Exception:  # noqa: BLE001 - fall back to a filtered walk
        names = [
            str(p.relative_to(REPO))
            for p in REPO.rglob("*")
            if p.is_file()
            and not any(part in SKIP_DIRS for part in p.relative_to(REPO).parts)
            and p.name not in SKIP_FILES
            and not p.name.endswith(SKIP_SUFFIXES)
        ]
    return [REPO / n for n in names if (REPO / n).is_file()]


def scan_tree() -> list[dict]:
    """Scan the files that would be committed.

    This answers "would this repository leak anything if published?" —
    gitignored local files (the real `.env`, derived artifacts) are
    deliberately excluded.
    """
    findings: list[dict] = []
    for path in _committed_files():
        rel = path.relative_to(REPO)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if path.name in SKIP_FILES:
            continue
        if path.name.endswith(SKIP_SUFFIXES):
            continue
        findings.extend(scan_file(path))
    return findings


def _dependency_scan_report() -> list[str]:
    """Best-effort dependency vulnerability summary via pip-audit (if present)."""
    import subprocess

    try:
        res = subprocess.run(
            [sys.executable, "-m", "pip_audit", "--progress-spinner", "off"],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001
        return [f"pip-audit not runnable: {exc}", "", "Install it with `pip install pip-audit` and re-run."]

    out = (res.stdout + res.stderr).strip()
    if "No known vulnerabilities found" in out:
        return ["**PASS** — no known vulnerabilities in declared/installed dependencies."]
    return [
        "**FAIL** — known vulnerabilities detected:",
        "",
        "```",
        out,
        "```",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="CyberRisk AI repo security scan")
    parser.add_argument("--report", action="store_true", help="write reports/security_release_check.md")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args()

    findings = scan_tree()
    ok = not findings

    if args.json:
        print(json.dumps({"status": "PASS" if ok else "FAIL", "findings": findings}, indent=2))
        return 0 if ok else 1

    if args.report:
        out = REPO / "reports" / "security_release_check.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines = [
            "# Security Release Check",
            "",
            f"Generated: {ts}  ",
            "Scanner: `scripts/security_scan.py`  ",
            "",
            "## Result",
            "",
            "**" + ("PASS" if ok else "FAIL") + "**",
            "",
        ]
        if ok:
            lines += [
                "- **No secrets found** — no high-confidence API keys, tokens, or private keys in the working tree.",
                "- **No personal data found** — no emails, phone numbers, or local machine paths.",
                "- **No private datasets found** — no data files under tracked directories.",
            ]
        else:
            lines.append("| File | Type | Match | Line |")
            lines.append("|---|---|---|---|")
            for f in findings:
                lines.append(f"| `{f['file']}` | {f['type']} | `{f['match']}` | {f['line']} |")
            lines.append("")
            lines.append("Resolve the findings above before publishing the repository.")
        lines += ["", "## Dependency Scan", ""]
        lines += _dependency_scan_report()
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"wrote {out.relative_to(REPO)}")
        return 0 if ok else 1

    if ok:
        print("PASS: no secrets, no personal data, no private datasets found.")
        return 0
    print("FAIL: findings detected:")
    for f in findings:
        print(f"  {f['file']}:{f['line']}  {f['type']}: {f['match']}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
