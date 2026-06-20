"""Tests for arasul_tui.agent.context.*"""

from __future__ import annotations

from pathlib import Path

import pytest

from arasul_tui.agent.context.budget import TokenBudget
from arasul_tui.agent.context.pruner import prune_conversation, truncate_tool_result
from arasul_tui.agent.context.repo_map import RepoMap, _extract_symbols


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_messages(*contents: tuple[str, str]) -> list[dict]:
    """Create messages from (role, content) tuples."""
    return [{"role": r, "content": c} for r, c in contents]


# ---------------------------------------------------------------------------
# _extract_symbols
# ---------------------------------------------------------------------------


def test_extract_python_functions(tmp_path):
    f = tmp_path / "auth.py"
    f.write_text(
        "def login(user, pw):\n"
        "    pass\n\n"
        "async def logout():\n"
        "    pass\n\n"
        "class User:\n"
        "    pass\n"
    )
    syms = _extract_symbols(f)
    assert "login" in syms
    assert "logout" in syms
    assert "User" in syms


def test_extract_python_skips_private(tmp_path):
    f = tmp_path / "internal.py"
    f.write_text("def _helper():\n    pass\ndef public():\n    pass\n")
    syms = _extract_symbols(f)
    assert "_helper" not in syms
    assert "public" in syms


def test_extract_typescript(tmp_path):
    f = tmp_path / "api.ts"
    f.write_text(
        "export async function fetchUser(id: string) {}\n"
        "export class AuthService {}\n"
        "export interface UserDTO {}\n"
        "export type Role = 'admin' | 'user';\n"
    )
    syms = _extract_symbols(f)
    assert "fetchUser" in syms
    assert "AuthService" in syms
    assert "UserDTO" in syms


def test_extract_go(tmp_path):
    f = tmp_path / "handler.go"
    f.write_text(
        "func Login(w http.ResponseWriter, r *http.Request) {}\n"
        "func (s *Server) Logout() {}\n"
        "type UserStore struct {}\n"
    )
    syms = _extract_symbols(f)
    assert "Login" in syms
    assert "Logout" in syms
    assert "UserStore" in syms


def test_extract_rust(tmp_path):
    f = tmp_path / "lib.rs"
    f.write_text(
        "pub fn process_data(input: &str) -> String {}\n"
        "pub struct DataStore;\n"
        "pub enum Status { Active, Inactive }\n"
    )
    syms = _extract_symbols(f)
    assert "process_data" in syms
    assert "DataStore" in syms
    assert "Status" in syms


def test_extract_unknown_extension(tmp_path):
    f = tmp_path / "data.csv"
    f.write_text("a,b,c\n1,2,3\n")
    assert _extract_symbols(f) == []


def test_extract_empty_file(tmp_path):
    f = tmp_path / "empty.py"
    f.write_text("")
    assert _extract_symbols(f) == []


def test_extract_caps_at_max_symbols(tmp_path):
    f = tmp_path / "big.py"
    lines = "\n".join(f"def func_{i}(): pass" for i in range(20))
    f.write_text(lines)
    syms = _extract_symbols(f)
    assert len(syms) <= 10  # _MAX_SYMBOLS_PER_FILE


# ---------------------------------------------------------------------------
# RepoMap.render
# ---------------------------------------------------------------------------


@pytest.fixture
def small_project(tmp_path) -> Path:
    """A tiny realistic project tree."""
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)

    (tmp_path / "src" / "auth.py").write_text(
        "def login(user, pw): pass\nclass User: pass\n"
    )
    (tmp_path / "src" / "models.py").write_text(
        "class UserModel: pass\ndef get_user(): pass\n"
    )
    (tmp_path / "tests" / "test_auth.py").write_text(
        "def test_login(): pass\ndef test_logout(): pass\n"
    )
    (tmp_path / "node_modules" / "pkg" / "index.js").write_text(
        "function secretNoise() {}\n"
    )
    return tmp_path


def test_repo_map_contains_symbols(small_project):
    rm = RepoMap(small_project)
    result = rm.render()
    assert "login" in result
    assert "User" in result
    assert "UserModel" in result


def test_repo_map_excludes_node_modules(small_project):
    rm = RepoMap(small_project)
    result = rm.render()
    assert "secretNoise" not in result


def test_repo_map_starts_with_header(small_project):
    rm = RepoMap(small_project)
    result = rm.render()
    assert result.startswith("Repository map:")


def test_repo_map_empty_project(tmp_path):
    rm = RepoMap(tmp_path)
    result = rm.render()
    assert result == ""


def test_repo_map_token_budget_limits_output(small_project):
    rm = RepoMap(small_project)
    # Very tight budget — should truncate
    result = rm.render(token_budget=20)
    # Either empty or very short
    assert len(result) < 300


def test_repo_map_hint_prioritizes_mentioned_files(tmp_path):
    (tmp_path / "auth.py").write_text("def login(): pass\n")
    (tmp_path / "utils.py").write_text("def helper(): pass\n")
    (tmp_path / "payment.py").write_text("def charge(): pass\n")

    rm = RepoMap(tmp_path)
    result = rm.render(hint="fix the authentication login bug")
    # auth.py should appear before utils.py
    auth_pos = result.find("auth.py")
    utils_pos = result.find("utils.py")
    assert auth_pos != -1
    assert auth_pos < utils_pos


def test_repo_map_no_duplicate_symbols(tmp_path):
    (tmp_path / "f.py").write_text(
        "def login(): pass\ndef login(): pass\n"  # duplicate defs
    )
    rm = RepoMap(tmp_path)
    result = rm.render()
    # login should appear only once in the symbol list
    assert result.count("login") == 1


# ---------------------------------------------------------------------------
# TokenBudget
# ---------------------------------------------------------------------------


def test_budget_initial_state():
    b = TokenBudget(max_tokens=1000)
    assert b.used == 0
    assert b.remaining == 1000
    assert b.utilization == 0.0


def test_budget_consume_text():
    b = TokenBudget(max_tokens=1000)
    cost = b.consume("a" * 400)  # 400 chars → 100 tokens
    assert cost == 100
    assert b.used == 100
    assert b.remaining == 900


def test_budget_can_fit_within():
    b = TokenBudget(max_tokens=1000)
    b.consume("a" * 400)  # 100 tokens used, 900 remaining
    assert b.can_fit("b" * 1000, safety_margin=0) is True  # 250 tokens


def test_budget_can_fit_exceeds():
    b = TokenBudget(max_tokens=200)
    b.consume("a" * 400)  # 100 tokens used, 100 remaining
    assert b.can_fit("b" * 800, safety_margin=0) is False  # 200 tokens needed


def test_budget_can_fit_respects_safety_margin():
    b = TokenBudget(max_tokens=1000)
    b.consume("a" * 3600)  # 900 tokens used, 100 remaining
    # 50 tokens of content but 200-token safety margin → doesn't fit
    assert b.can_fit("b" * 200, safety_margin=200) is False


def test_budget_remaining_floors_at_zero():
    b = TokenBudget(max_tokens=100)
    b.consume("a" * 800)  # 200 tokens — over budget
    assert b.remaining == 0


def test_budget_reset():
    b = TokenBudget(max_tokens=1000)
    b.consume("a" * 400)
    b.reset()
    assert b.used == 0


def test_budget_snapshot_restore():
    b = TokenBudget(max_tokens=1000)
    b.consume("a" * 400)
    snap = b.snapshot()
    b.consume("b" * 400)
    assert b.used == 200
    b.restore(snap)
    assert b.used == 100


def test_budget_str():
    b = TokenBudget(max_tokens=1000)
    b.consume("a" * 400)
    s = str(b)
    assert "100/1000" in s
    assert "10%" in s


def test_budget_consume_messages():
    b = TokenBudget(max_tokens=10000)
    msgs = [
        {"role": "user", "content": "a" * 400},   # 100 tokens
        {"role": "assistant", "content": "b" * 400},  # 100 tokens
    ]
    cost = b.consume_messages(msgs)
    assert cost == 200
    assert b.used == 200


# ---------------------------------------------------------------------------
# prune_conversation
# ---------------------------------------------------------------------------


def test_prune_no_op_when_fits():
    msgs = make_messages(
        ("user", "fix the bug"),
        ("assistant", "ok"),
        ("tool", "result"),
    )
    result = prune_conversation(msgs, max_tokens=100_000)
    assert result == msgs


def test_prune_empty_returns_empty():
    assert prune_conversation([], max_tokens=1000) == []


def test_prune_keeps_first_and_last():
    msgs = make_messages(
        ("user", "a" * 800),    # first — always kept
        ("assistant", "b" * 800),
        ("tool", "c" * 800),
        ("assistant", "d" * 800),
        ("user", "e" * 800),    # recent
        ("assistant", "f" * 800),  # recent
    )
    # Budget too small for all, but first + last 2 should survive
    result = prune_conversation(msgs, max_tokens=300, keep_last=2)
    # First message preserved
    assert result[0]["content"] == msgs[0]["content"]
    # Last 2 messages preserved
    last_contents = {m["content"] for m in result[-2:]}
    assert msgs[-1]["content"] in last_contents
    assert msgs[-2]["content"] in last_contents
    # Middle dropped
    assert msgs[1]["content"] not in {m["content"] for m in result}


def test_prune_inserts_placeholder():
    msgs = make_messages(
        ("user", "original task " * 10),
        ("assistant", "step 1 " * 50),
        ("tool", "result 1 " * 50),
        ("assistant", "step 2 " * 50),
        ("user", "follow up " * 20),
        ("assistant", "answer " * 20),
    )
    result = prune_conversation(msgs, max_tokens=100, keep_last=2)
    contents = [m["content"] for m in result]
    assert any("omitted" in c.lower() or "truncated" in c.lower() for c in contents)


def test_prune_short_conversation_not_pruned():
    msgs = make_messages(
        ("user", "hi"),
        ("assistant", "hello"),
    )
    result = prune_conversation(msgs, max_tokens=10, keep_last=6)
    # keep_last >= len — should return as-is (overlap branch)
    assert len(result) <= len(msgs) + 1  # maybe placeholder but not more


# ---------------------------------------------------------------------------
# truncate_tool_result
# ---------------------------------------------------------------------------


def test_truncate_tool_result_short():
    short = "x" * 100
    assert truncate_tool_result(short) == short


def test_truncate_tool_result_long():
    long = "x" * 100_000
    result = truncate_tool_result(long, max_tokens=100)
    assert len(result) < len(long)
    assert "truncated" in result


def test_truncate_tool_result_preserves_start():
    content = "IMPORTANT_START " + "x" * 50_000
    result = truncate_tool_result(content, max_tokens=10)
    assert result.startswith("IMPORTANT_START")
