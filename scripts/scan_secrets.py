#!/usr/bin/env python3
"""
FINN — Secret Scanner
Scans tracked, staged, and working tree files for exposed API keys.
Exits 0 if clean, exits 1 if any pattern matching AQ. or AIza keys is detected.
Never prints the secret itself.
"""

import os
import re
import sys
import subprocess
from pathlib import Path

# Pattern matching Google AI Studio / Gemini API keys:
# - AQ.<20+ chars> (new AI Studio format)
# - AIza<20+ chars> (legacy Google Cloud / Firebase / AI Studio format)
KEY_PATTERN = re.compile(r"(AQ\.[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{20,})")

IGNORE_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", ".next"}
IGNORE_EXTS = {".pdf", ".pyc", ".png", ".jpg", ".jpeg", ".ico", ".svg", ".zip"}

def get_git_files() -> list[str]:
    """Get list of tracked and staged files from git if available."""
    files = set()
    try:
        tracked = subprocess.check_output(["git", "ls-files"], text=True, errors="ignore").splitlines()
        files.update(tracked)
    except Exception:
        pass
    try:
        staged = subprocess.check_output(["git", "diff", "--cached", "--name-only"], text=True, errors="ignore").splitlines()
        files.update(staged)
    except Exception:
        pass
    return sorted(files)

def scan_file(file_path: Path) -> list[int]:
    """Scan a file for key patterns. Returns matching line numbers (1-indexed)."""
    if not file_path.exists() or file_path.is_dir():
        return []
    if file_path.suffix.lower() in IGNORE_EXTS:
        return []
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    
    matches = []
    for idx, line in enumerate(content.splitlines(), 1):
        if KEY_PATTERN.search(line):
            matches.append(idx)
    return matches

def main():
    root = Path(__file__).resolve().parent.parent
    os.chdir(root)

    print("[SECRET SCAN] Scanning repo files for exposed Gemini/Google API keys...")

    # 1. Check git-tracked and staged files
    git_files = get_git_files()
    files_to_scan = set()
    for f in git_files:
        p = root / f
        if p.exists() and p.is_file():
            files_to_scan.add(p)

    # 2. Also check common config / script / doc files in working tree
    for p in root.iterdir():
        if p.is_file() and p.suffix.lower() not in IGNORE_EXTS:
            files_to_scan.add(p)

    # Also walk backend, scripts, frontend/src, docs
    for subdir in ["backend", "scripts", "docs", "frontend/src"]:
        subpath = root / subdir
        if subpath.exists():
            for p in subpath.rglob("*"):
                if p.is_file() and not any(part in p.parts for part in IGNORE_DIRS) and p.suffix.lower() not in IGNORE_EXTS:
                    files_to_scan.add(p)

    violations = []
    for file_path in sorted(files_to_scan):
        rel_path = file_path.relative_to(root)
        lines = scan_file(file_path)
        if lines:
            violations.append((rel_path, lines))

    if violations:
        print("\n[SECRET SCAN] FAIL: Potential API key detected in:")
        for rel_path, lines in violations:
            print(f"  - {rel_path} (lines: {lines})")
        print("\nAction required: Remove keys from files immediately. Use environment variables only.")
        sys.exit(1)
    else:
        print(f"[SECRET SCAN] PASS: Scanned {len(files_to_scan)} files. No API keys found in tracked or working tree files.")
        sys.exit(0)

if __name__ == "__main__":
    main()
