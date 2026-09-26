"""Checks that every relative Markdown link and #anchor in the repo docs resolves. Standard library only.

Run from the repo root:  python tests/check_docs.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = [ROOT / "README.md", ROOT / "CLAUDE.md", *sorted((ROOT / "docs").rglob("*.md")), *sorted((ROOT / ".claude").rglob("*.md"))]
LINK = re.compile(r"(?<!\!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def strip_fences(text: str) -> str:
    out, fenced = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced:
            out.append(line)
    return "\n".join(out)


def slug(heading: str) -> str:
    s = re.sub(r"[`*_~]", lambda m: "_" if m.group() == "_" else "", heading.strip().lower())
    s = re.sub(r"[^\w\- ]", "", s)
    return s.replace(" ", "-")


def anchors(path: Path) -> set[str]:
    found, seen = set(), {}
    for line in strip_fences(path.read_text(encoding="utf-8")).splitlines():
        m = re.match(r"#{1,6}\s+(.*?)\s*#*$", line)
        if m:
            base = slug(m[1])
            n = seen.get(base, 0)
            found.add(base if n == 0 else f"{base}-{n}")
            seen[base] = n + 1
    return found


problems, checked = [], 0
for f in FILES:
    text = strip_fences(f.read_text(encoding="utf-8"))
    for target in LINK.findall(text):
        if re.match(r"^(https?:|mailto:)", target):
            continue
        checked += 1
        path_part, _, frag = target.partition("#")
        dest = (f.parent / path_part).resolve() if path_part else f
        rel = f.relative_to(ROOT)
        if not dest.exists():
            problems.append(f"{rel}: broken link -> {target}")
        elif frag and dest.suffix == ".md" and frag not in anchors(dest):
            problems.append(f"{rel}: missing anchor -> {target}")

for p in problems:
    print("FAIL", p)
print(f"{len(FILES)} files, {checked} relative links checked, {len(problems)} problem(s)")
sys.exit(1 if problems else 0)
