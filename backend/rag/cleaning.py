"""
rag/cleaning.py
───────────────
Document cleaning and normalisation utilities.

Preserves:
  - headings (# / ## / ###)
  - code blocks (``` fenced)
  - tables (| col | col |)
  - issue IDs (e.g. PROJ-123)
  - stack traces

Removes:
  - boilerplate navigation fragments
  - duplicate email signatures
  - repeated headers / footers
  - excessive whitespace
"""

import re
from typing import List

# ── Compiled patterns ─────────────────────────────────────────────────────────

# Email / Jira email-notification signature blocks
_SIGNATURE_RE = re.compile(
    r"(-{2,}\s*\n.*?(?:wrote:|sent from|from:|reply above this line).*?\n)+",
    re.IGNORECASE | re.DOTALL,
)

# Navigation / UI junk lines (exact-match after strip + lower)
_NAV_EXACT: set = {
    "home", "back", "next", "previous", "top", "skip to content",
    "login", "logout", "sign in", "sign up", "register",
    "search", "filter", "view all", "load more", "show more",
    "privacy policy", "terms of service", "cookie policy",
    "click here", "read more", "learn more", "see also",
    "share", "report", "vote", "comment", "watch", "follow",
    "like", "subscribe", "unsubscribe",
}

# Navigation patterns (regex)
_NAV_PATTERNS: List[re.Pattern] = [
    re.compile(r"^page \d+ of \d+$", re.IGNORECASE),
    re.compile(r"^[-_=]{5,}$"),
    re.compile(r"^\d+\s*(views?|likes?|shares?|comments?)$", re.IGNORECASE),
    re.compile(r"^(copyright|©|all rights reserved)", re.IGNORECASE),
    re.compile(r"^\s*\|\s*\|\s*$"),           # empty table rows
    re.compile(r"^modified\s+\d{4}-\d{2}-\d{2}", re.IGNORECASE),
]

# Repeated header/footer lines (seen 3+ times in a document → likely boilerplate)
_MIN_REPEAT_COUNT = 3


def _is_nav_junk(line: str) -> bool:
    stripped = line.strip()
    lower = stripped.lower()
    if lower in _NAV_EXACT:
        return True
    for pat in _NAV_PATTERNS:
        if pat.match(lower):
            return True
    return False


def _remove_repeated_lines(lines: List[str]) -> List[str]:
    """Remove lines that appear ≥ _MIN_REPEAT_COUNT times (boilerplate headers/footers)."""
    from collections import Counter
    counts = Counter(ln.strip() for ln in lines if ln.strip())
    repeated = {text for text, count in counts.items() if count >= _MIN_REPEAT_COUNT and len(text) < 120}
    return [ln for ln in lines if ln.strip() not in repeated]


def clean_document(text: str, source_type: str = "generic") -> str:
    """
    Clean and normalise raw document text.

    Args:
        text: Raw text extracted from the source document.
        source_type: Hint for source-specific rules ('jira', 'confluence', 'pdf', 'url').

    Returns:
        Cleaned text suitable for chunking and embedding.
    """
    if not text:
        return ""

    # Remove duplicate email signatures
    text = _SIGNATURE_RE.sub("\n", text)

    # Split into lines for per-line processing
    lines = text.split("\n")

    # Remove boilerplate navigation lines
    lines = [ln for ln in lines if not _is_nav_junk(ln)]

    # Remove repeated header/footer boilerplate
    lines = _remove_repeated_lines(lines)

    # Collapse runs of more than 2 consecutive blank lines
    cleaned: List[str] = []
    blank_run = 0
    for ln in lines:
        if ln.strip() == "":
            blank_run += 1
            if blank_run <= 2:
                cleaned.append("")
        else:
            blank_run = 0
            cleaned.append(ln.rstrip())

    result = "\n".join(cleaned).strip()

    # Collapse 3+ spaces (but not inside code blocks)
    result = _collapse_spaces_outside_code(result)

    return result


def _collapse_spaces_outside_code(text: str) -> str:
    """Collapse 3+ consecutive spaces to 2, but leave code blocks intact."""
    in_code = False
    lines_out: List[str] = []
    for line in text.split("\n"):
        if line.strip().startswith("```"):
            in_code = not in_code
        if not in_code:
            line = re.sub(r" {3,}", "  ", line)
        lines_out.append(line)
    return "\n".join(lines_out)


def clean_html_to_text(html: str) -> str:
    """
    Convert HTML to clean plain text, preserving structure.

    Uses simple regex-based conversion (no external deps beyond stdlib).
    Falls back gracefully if beautifulsoup4 is not installed.
    """
    try:
        from bs4 import BeautifulSoup, NavigableString, Tag

        soup = BeautifulSoup(html, "lxml")

        # Remove script / style / nav / footer elements
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        lines: List[str] = []

        def _walk(node) -> None:
            if isinstance(node, NavigableString):
                text = str(node).strip()
                if text:
                    lines.append(text)
                return

            tag_name = node.name.lower() if node.name else ""

            # Headings
            if tag_name in ("h1", "h2", "h3", "h4", "h5", "h6"):
                level = int(tag_name[1])
                inner = node.get_text(" ", strip=True)
                lines.append("\n" + "#" * level + " " + inner)
                return

            # Code blocks
            if tag_name in ("pre", "code"):
                code = node.get_text()
                lines.append("\n```\n" + code.strip() + "\n```\n")
                return

            # Block-level elements → newline
            if tag_name in ("p", "div", "section", "article", "li", "tr", "blockquote"):
                for child in node.children:
                    _walk(child)
                lines.append("")
                return

            # Tables → preserve as pipe-separated
            if tag_name == "table":
                lines.append(_table_to_text(node))
                return

            # Default: recurse
            for child in node.children:
                _walk(child)

        _walk(soup.body or soup)

        text = "\n".join(lines)
        return clean_document(text, source_type="url")

    except ImportError:
        # Fallback: strip tags with regex
        from html import unescape
        html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
        html = re.sub(r"</?(p|div|li|h[1-6]|tr)[^>]*>", "\n", html, flags=re.IGNORECASE)
        html = re.sub(r"<[^>]+>", "", html)
        return clean_document(unescape(html), source_type="url")


def _table_to_text(table_tag) -> str:
    """Convert a BeautifulSoup table element to a pipe-separated text table."""
    rows = []
    for row in table_tag.find_all("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["td", "th"])]
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows)
