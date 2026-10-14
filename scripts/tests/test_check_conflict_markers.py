"""The CI check for conflict markers: what it flags, what it leaves alone, and its exit status."""

import importlib.util
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check_conflict_markers.py"
_spec = importlib.util.spec_from_file_location("check_conflict_markers", SCRIPT)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
conflict_lines = _module.conflict_lines
OURS, BASE, THEIRS = "<" * 7, "=" * 7, ">" * 7  # never a literal marker in this file


def repo(
    tmp_path: Path, files: dict[str, bytes], untracked: dict[str, bytes] | None = None
) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for name, data in files.items():
        (tmp_path / name).write_bytes(data)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    for name, data in (untracked or {}).items():
        (tmp_path / name).write_bytes(data)
    return tmp_path


def conflict() -> bytes:
    return f"a = 1\n{OURS} HEAD\nb = 2\n{BASE}\nb = 3\n{THEIRS} feature\n".encode()


def test_every_marker_line_of_a_tracked_text_file_is_named(tmp_path: Path) -> None:
    root = repo(tmp_path, {"app.py": conflict(), "notes.md": f"x\n{BASE} \n".encode()})
    assert conflict_lines(root) == [
        f"app.py:2: {OURS} HEAD",
        f"app.py:4: {BASE}",
        f"app.py:6: {THEIRS} feature",
        f"notes.md:2: {BASE} ",
    ]


def test_markers_inside_a_line_binary_files_and_untracked_files_are_left_alone(
    tmp_path: Path,
) -> None:
    files = {
        "ok.py": f'MARK = "{OURS} "\n# {BASE}\n{BASE}=\nTitle\n{"=" * 5}\n'.encode(),
        "audio.mp3": b"\x00\x01" + conflict(),
    }
    root = repo(tmp_path, files, untracked={"scratch.txt": conflict()})
    assert conflict_lines(root) == []


def test_it_exits_1_on_a_marker_and_0_without(tmp_path: Path) -> None:
    dirty = repo(tmp_path / "dirty", {"a.txt": conflict()})
    clean = repo(tmp_path / "clean", {"a.txt": b"fine\n"})
    run = [sys.executable, str(SCRIPT)]
    assert subprocess.run(run, cwd=dirty, capture_output=True).returncode == 1
    assert subprocess.run(run, cwd=clean, capture_output=True).returncode == 0
