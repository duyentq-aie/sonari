"""Guard: a file with conflict markers must not get past pre-commit or CI.

`check-merge-conflict` was missing from the config, so a merge commit with unresolved
markers in three files (73e09d1) went through. Two details make the hook easy to defeat
without noticing, and this test pins both:

* by default the hook does nothing unless a merge is in progress (`MERGE_MSG` plus
  `MERGE_HEAD`, or a rebase directory), so an ordinary commit of a file with markers
  passes, and so does CI, whose `pre-commit run --all-files` is never "in a merge".
  `--assume-in-merge` makes it always check;
* pre-commit hooks that narrow what they see (`files`, `exclude`, `types`, `stages`) would
  skip some file types or commits.
"""

import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / ".pre-commit-config.yaml"
HOOKS_REPO = "https://github.com/pre-commit/pre-commit-hooks"
HOOK_ID = "check-merge-conflict"
# Keys that would make the hook look at fewer files, or in fewer situations, than its default.
NARROWING_KEYS = {"files", "exclude", "types", "types_or", "exclude_types", "stages"}


@pytest.fixture(scope="module")
def config() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    return loaded


def merge_conflict_hook(config: dict[str, Any]) -> dict[str, Any]:
    for repo in config["repos"]:
        if repo["repo"] == HOOKS_REPO:
            for hook in repo["hooks"]:
                if hook["id"] == HOOK_ID:
                    found: dict[str, Any] = hook
                    return found
    pytest.fail(f"{HOOK_ID} from {HOOKS_REPO} is not in {CONFIG.name}")


def test_the_merge_conflict_hook_is_configured(config: dict[str, Any]) -> None:
    merge_conflict_hook(config)


def test_it_checks_even_when_no_merge_is_in_progress(config: dict[str, Any]) -> None:
    assert "--assume-in-merge" in merge_conflict_hook(config).get("args", [])


def test_the_hook_is_not_narrowed_to_some_files_or_stages(config: dict[str, Any]) -> None:
    assert NARROWING_KEYS.isdisjoint(merge_conflict_hook(config))
    assert "files" not in config


def test_it_runs_at_commit_time(config: dict[str, Any]) -> None:
    assert "pre-commit" in config.get("default_stages", ["pre-commit"])


def test_it_runs_on_a_merge_commit_too_and_make_setup_installs_that_hook(
    config: dict[str, Any],
) -> None:
    assert "pre-merge-commit" in config.get("default_stages", ["pre-commit"])
    setup = (
        (ROOT / "Makefile").read_text(encoding="utf-8").split("\nsetup:\n", 1)[1].split("\n\n")[0]
    )
    assert "pre-commit install --hook-type pre-merge-commit" in setup


def test_the_global_exclude_hides_no_tracked_file_except_claude_settings(
    config: dict[str, Any],
) -> None:
    exclude = config.get("exclude")
    if exclude is None:
        return
    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split("\0")
    hidden = [p for p in tracked if p and re.search(exclude, p) and not p.startswith(".claude/")]
    assert hidden == []
