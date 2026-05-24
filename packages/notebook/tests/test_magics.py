"""Tests for the Penumbra IPython bridge."""

from __future__ import annotations

import pytest
from penumbra_notebook import PenumbraNotebookError, cell_magic, line_magic


def test_snapshot_without_connect_raises() -> None:
    import penumbra_notebook

    penumbra_notebook._SESSION.base_url = None  # reset
    with pytest.raises(PenumbraNotebookError):
        line_magic("snapshot")


def test_unknown_subcommand_raises() -> None:
    with pytest.raises(PenumbraNotebookError):
        line_magic("does_not_exist")


def test_empty_line_returns_usage() -> None:
    result = line_magic("")
    assert isinstance(result, dict)
    assert "usage" in result


def test_cell_magic_runs_valid_policy() -> None:
    src = "def policy(state, observation):\n    return 42\n"
    result = cell_magic("attack demo", src)
    assert result["ok"] is True
    assert result["result"] == 42
    assert result["name"] == "demo"


def test_cell_magic_rejects_import() -> None:
    src = "import os\ndef policy(s, o):\n    return 0\n"
    result = cell_magic("attack bad", src)
    assert result["ok"] is False
    assert "parse" in result["error"]


def test_cell_magic_rejects_non_attack_keyword() -> None:
    with pytest.raises(PenumbraNotebookError):
        cell_magic("not_attack name", "def policy(s, o):\n    return 0\n")
