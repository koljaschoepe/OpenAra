"""Repo map: compressed symbol index of the project for the LLM's context.

Extracts function/class names from source files using language-specific regex
patterns. Tree-sitter gives better accuracy but is an optional upgrade — the
regex approach is good enough for 14B models and has zero extra dependencies.

Output example (fits ~100 files in ~2000 tokens):
    Repository map:
    src/auth.py: login, logout, verify_token, User
    src/models.py: UserModel, create_user, get_user
    tests/test_auth.py: test_login, test_logout
"""

from __future__ import annotations

import re
from pathlib import Path

from arasul_tui.agent.llm import estimate_tokens
from arasul_tui.agent.tools.search_tools import _SKIP_DIRS

_MAX_SYMBOLS_PER_FILE = 10
_MAX_FILES = 200

# (extensions, list of (prefix_label, regex_pattern))
# Each pattern must have exactly one capture group: the symbol name.
_EXTRACTORS: dict[frozenset[str], list[tuple[str, re.Pattern]]] = {
    frozenset({".py"}): [
        ("", re.compile(r"^(?:async\s+)?def\s+(\w+)", re.MULTILINE)),
        ("", re.compile(r"^class\s+(\w+)", re.MULTILINE)),
    ],
    frozenset({".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}): [
        ("", re.compile(r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w+)", re.MULTILINE)),
        ("", re.compile(r"^(?:export\s+)?(?:abstract\s+)?class\s+(\w+)", re.MULTILINE)),
        ("", re.compile(r"^(?:export\s+)?(?:const|let)\s+(\w+)\s*[:=].*(?:=>|\bfunction\b)", re.MULTILINE)),
        ("", re.compile(r"^(?:export\s+)?(?:interface|type|enum)\s+(\w+)", re.MULTILINE)),
    ],
    frozenset({".go"}): [
        ("", re.compile(r"^func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*\(", re.MULTILINE)),
        ("", re.compile(r"^type\s+(\w+)\s+(?:struct|interface)", re.MULTILINE)),
    ],
    frozenset({".rs"}): [
        ("", re.compile(r"^(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+(\w+)", re.MULTILINE)),
        ("", re.compile(r"^(?:pub(?:\([^)]*\))?\s+)?(?:struct|enum|trait|impl)\s+(\w+)", re.MULTILINE)),
    ],
    frozenset({".java", ".kt"}): [
        ("", re.compile(r"(?:^|\s)(?:public|private|protected)\s+(?:static\s+)?(?:\w+\s+)+(\w+)\s*\(", re.MULTILINE)),
        ("", re.compile(r"(?:^|\s)(?:data\s+)?class\s+(\w+)", re.MULTILINE)),
    ],
    frozenset({".rb"}): [
        ("", re.compile(r"^\s*def\s+(?:self\.)?(\w+)", re.MULTILINE)),
        ("", re.compile(r"^class\s+(\w+)", re.MULTILINE)),
    ],
    frozenset({".cs"}): [
        ("", re.compile(r"(?:public|private|protected|internal|static|\s)+\w+\s+(\w+)\s*\(", re.MULTILINE)),
        ("", re.compile(r"(?:^|\s)(?:public\s+)?(?:abstract\s+)?class\s+(\w+)", re.MULTILINE)),
    ],
    frozenset({".sh", ".bash", ".zsh"}): [
        ("", re.compile(r"^(\w+)\s*\(\)", re.MULTILINE)),
    ],
}

# Build extension → extractors index
_EXT_INDEX: dict[str, list[tuple[str, re.Pattern]]] = {}
for exts, patterns in _EXTRACTORS.items():
    for ext in exts:
        _EXT_INDEX[ext] = patterns

_IGNORE_SYMBOLS = frozenset({
    # Common test/fixture noise
    "test", "setUp", "tearDown", "setUpClass", "tearDownClass",
    "main", "__init__", "__str__", "__repr__", "__eq__", "__hash__",
    "__enter__", "__exit__", "__len__", "__iter__", "__next__",
})


def _extract_symbols(path: Path) -> list[str]:
    patterns = _EXT_INDEX.get(path.suffix.lower())
    if not patterns:
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    seen: dict[str, None] = {}  # ordered set via dict
    for _, rx in patterns:
        for match in rx.finditer(text):
            name = match.group(1)
            if name and not name.startswith("_") and name not in _IGNORE_SYMBOLS:
                seen[name] = None

    symbols = list(seen.keys())[:_MAX_SYMBOLS_PER_FILE]
    return symbols


def _is_skippable(path: Path) -> bool:
    return any(part in _SKIP_DIRS or part.endswith(".egg-info") for part in path.parts)


def _rank_key(path: Path, hint_words: frozenset[str], root: Path) -> tuple:
    """Lower tuple = higher priority."""
    rel = str(path.relative_to(root))
    name = path.stem.lower()

    # Match if any hint word appears in path, OR the file stem appears in any hint word
    # (e.g. stem "auth" matches hint word "authentication")
    rel_lower = rel.lower()
    hint_score = 0 if (
        any(w in rel_lower for w in hint_words) or
        any(name in w or w in name for w in hint_words if len(w) >= 3)
    ) else 1

    # Tests and __init__ files are lower priority
    kind_score = 2 if ("test" in name or name == "__init__") else (1 if name.startswith("_") else 0)

    # Recently modified files are more likely relevant
    try:
        mtime = -path.stat().st_mtime  # negative → recently modified = lower value
    except OSError:
        mtime = 0.0

    return (hint_score, kind_score, mtime)


class RepoMap:
    def __init__(self, project_root: Path) -> None:
        self.root = project_root

    def render(self, token_budget: int = 2048, hint: str = "") -> str:
        """Build a repo map that fits within *token_budget* tokens.

        *hint* is the user's task description — files mentioned there
        are ranked higher so the model sees the most relevant context first.
        """
        hint_words = frozenset(
            w.lower() for w in re.split(r"\W+", hint) if len(w) > 3
        )

        source_files = self._find_source_files()
        ranked = sorted(source_files, key=lambda f: _rank_key(f, hint_words, self.root))

        lines: list[str] = []
        tokens_used = 0

        for f in ranked[:_MAX_FILES]:
            symbols = _extract_symbols(f)
            rel = str(f.relative_to(self.root))
            line = f"  {rel}: {', '.join(symbols)}" if symbols else f"  {rel}"
            cost = estimate_tokens(line)
            if tokens_used + cost > token_budget:
                remaining = len(ranked) - len(lines)
                if remaining > 0:
                    lines.append(f"  ... ({remaining} more files not shown)")
                break
            lines.append(line)
            tokens_used += cost

        if not lines:
            return ""
        return "Repository map:\n" + "\n".join(lines)

    def _find_source_files(self) -> list[Path]:
        result: list[Path] = []
        for f in self.root.rglob("*"):
            if not f.is_file():
                continue
            if _is_skippable(f):
                continue
            if f.suffix.lower() in _EXT_INDEX:
                result.append(f)
        return result
