"""Fails when a tracked text file has a conflict marker line (CI's repo job runs it).

pre-commit's check-merge-conflict runs only when the pre-commit hook does, so a commit that skips
it gets past: commits replayed by `git rebase` (a picked commit runs no pre-commit hook),
`git commit --no-verify`, a merge commit made before `make setup` installed the pre-merge-commit
hook. This reads every file git tracks, whatever made the commit. The markers are
pre-commit-hooks' own: a line that starts with seven <, = or > and a space, or is seven =.
"""

import subprocess
import sys
from pathlib import Path

STARTS = (b"<<<<<<< ", b"======= ", b">>>>>>> ")


def conflict_lines(root: Path) -> list[str]:
    listed = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True)
    found = []
    for name in filter(None, listed.stdout.decode().split("\0")):
        path = root / name
        if path.is_symlink() or not path.is_file():
            continue
        data = path.read_bytes()
        if b"\0" in data[:8192]:  # binary, as git decides it
            continue
        for number, line in enumerate(data.splitlines(), start=1):
            if line.startswith(STARTS) or line == b"=======":
                found.append(f"{name}:{number}: {line.decode(errors='replace')}")
    return found


if __name__ == "__main__":
    lines = conflict_lines(Path.cwd())
    print(*lines, sep="\n", file=sys.stderr)
    print(f"{len(lines)} conflict marker lines in tracked files")
    sys.exit(1 if lines else 0)
