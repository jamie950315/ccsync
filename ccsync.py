#!/usr/bin/env python3
"""ccsync - Sync ~/.claude/CLAUDE.md and ~/.claude/skills/ between devices via git repo."""

import argparse
import difflib
import shutil
import subprocess
from pathlib import Path

CLAUDE_HOME = Path.home() / ".claude"
SYNC_DIR = "config"
SYNC_TARGETS = {
    "CLAUDE.md": CLAUDE_HOME / "CLAUDE.md",
    "skills": CLAUDE_HOME / "skills",
}
IGNORE_PATTERNS = {".DS_Store", "__pycache__", ".pyc"}


def get_repo_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True,
    )
    return Path(result.stdout.strip())


def should_ignore(path: Path) -> bool:
    return any(part in IGNORE_PATTERNS or part.endswith(".pyc") for part in path.parts)


def collect_files(base: Path, rel: Path = Path(".")) -> list[Path]:
    """Recursively collect relative file paths under base, excluding ignored patterns."""
    result = []
    full = base / rel
    if full.is_file():
        if not should_ignore(rel):
            result.append(rel)
    elif full.is_dir():
        for child in sorted(full.iterdir()):
            result.extend(collect_files(base, rel / child.name))
    return result


def read_text_safe(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, IsADirectoryError):
        return None
    except UnicodeDecodeError:
        return None


def show_diff(label: str, old: str | None, new: str | None) -> list[str]:
    old_lines = (old or "").splitlines(keepends=True)
    new_lines = (new or "").splitlines(keepends=True)
    return list(difflib.unified_diff(old_lines, new_lines, fromfile=f"a/{label}", tofile=f"b/{label}"))


def print_diff(diff_lines: list[str]) -> None:
    for line in diff_lines:
        if line.startswith("+++") or line.startswith("---"):
            print(f"\033[1m{line}\033[0m", end="")
        elif line.startswith("+"):
            print(f"\033[32m{line}\033[0m", end="")
        elif line.startswith("-"):
            print(f"\033[31m{line}\033[0m", end="")
        elif line.startswith("@@"):
            print(f"\033[36m{line}\033[0m", end="")
        else:
            print(line, end="")


def confirm(prompt: str) -> bool:
    answer = input(f"{prompt} [y/N] ").strip().lower()
    return answer in ("y", "yes")


def build_changes(src_base: Path, dst_base: Path) -> list[dict]:
    """Compare source to destination and return a list of file changes."""
    changes = []
    for name in SYNC_TARGETS:
        src, dst = src_base / name, dst_base / name
        if src.is_file():
            sc, dc = read_text_safe(src), read_text_safe(dst)
            if sc is not None and sc != dc:
                action = "update" if dst.exists() else "create"
                changes.append({"name": name, "src": src, "dst": dst, "action": action,
                                "diff": show_diff(name, dc, sc), "is_dir": False})
        elif src.is_dir():
            src_files = collect_files(src)
            dst_files = collect_files(dst) if dst.exists() else []
            for rel in sorted(set(src_files) | set(dst_files)):
                sf, df = src / rel, dst / rel
                label = f"{name}/{rel}"
                sc, dc = read_text_safe(sf), read_text_safe(df)
                if sc is not None and dc is None:
                    changes.append({"name": label, "src": sf, "dst": df, "action": "create",
                                    "diff": show_diff(label, None, sc), "is_dir": False})
                elif sc is None and dc is not None:
                    changes.append({"name": label, "src": sf, "dst": df, "action": "delete",
                                    "diff": show_diff(label, dc, None), "is_dir": False})
                elif sc is not None and sc != dc:
                    changes.append({"name": label, "src": sf, "dst": df, "action": "update",
                                    "diff": show_diff(label, dc, sc), "is_dir": False})
    return changes


def apply_changes(changes: list[dict], interactive: bool = True) -> int:
    applied = 0
    for change in changes:
        action = change["action"]
        name = change["name"]

        if change["diff"]:
            print(f"\n{'=' * 60}")
            print(f"  {action.upper()}: {name}")
            print(f"{'=' * 60}")
            print_diff(change["diff"])

        if action == "delete":
            print(f"\n  DELETE: {name}")
            if change["is_dir"]:
                print(f"  (entire directory: {change['dst']})")

        if interactive:
            if not confirm(f"Apply {action} to {change['dst']}?"):
                print(f"  Skipped: {name}")
                continue

        dst = change["dst"]
        if action in ("create", "update"):
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(change["src"], dst)
            print(f"  ✓ {action}: {name}")
            applied += 1
        elif action == "delete":
            if change["is_dir"]:
                shutil.rmtree(dst)
            else:
                dst.unlink(missing_ok=True)
            print(f"  ✓ deleted: {name}")
            applied += 1

    return applied


def git_operations(repo: Path, message: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=repo, capture_output=True,
    )
    if result.returncode == 0:
        print("No staged changes to commit.")
        return
    subprocess.run(["git", "commit", "-m", message], cwd=repo, check=True)
    print("\nPushing to remote...")
    subprocess.run(["git", "push"], cwd=repo, check=True)
    print("✓ Pushed successfully.")


def cmd_push(args: argparse.Namespace) -> None:
    """Push local ~/.claude config to repo."""
    repo = get_repo_root()
    sync_dir = repo / SYNC_DIR
    sync_dir.mkdir(parents=True, exist_ok=True)
    print(f"Comparing local (~/.claude) → repo ({sync_dir})")

    changes = build_changes(CLAUDE_HOME, sync_dir)
    if not changes:
        print("✓ Everything is in sync. No changes needed.")
        return

    print(f"\nFound {len(changes)} change(s):\n")
    applied = apply_changes(changes, interactive=not args.yes)

    if applied > 0:
        msg = args.message or "sync: update claude config"
        git_operations(repo, msg)
    else:
        print("\nNo changes applied.")


def cmd_pull(args: argparse.Namespace) -> None:
    """Pull repo config to local ~/.claude."""
    repo = get_repo_root()
    sync_dir = repo / SYNC_DIR

    if not args.no_fetch:
        print("Fetching latest from remote...")
        subprocess.run(["git", "pull", "--ff-only"], cwd=repo, check=True)

    print(f"Comparing repo ({sync_dir}) → local (~/.claude)")

    changes = build_changes(sync_dir, CLAUDE_HOME)
    if not changes:
        print("✓ Everything is in sync. No changes needed.")
        return

    print(f"\nFound {len(changes)} change(s):\n")
    applied = apply_changes(changes, interactive=not args.yes)
    print(f"\n✓ Applied {applied} change(s) to ~/.claude")


def cmd_diff(args: argparse.Namespace) -> None:
    """Show diff between local and repo without applying changes."""
    repo = get_repo_root()
    sync_dir = repo / SYNC_DIR
    direction = args.direction

    if direction == "push":
        print(f"Diff: local (~/.claude) → repo ({sync_dir})\n")
        changes = build_changes(CLAUDE_HOME, sync_dir)
    else:
        print(f"Diff: repo ({sync_dir}) → local (~/.claude)\n")
        changes = build_changes(sync_dir, CLAUDE_HOME)

    if not changes:
        print("✓ No differences found.")
        return

    for change in changes:
        if change["diff"]:
            print_diff(change["diff"])
            print()


def cmd_status(_args: argparse.Namespace) -> None:
    """Show sync status overview."""
    repo = get_repo_root()
    sync_dir = repo / SYNC_DIR
    print(f"Repo: {sync_dir}")
    print(f"Local: {CLAUDE_HOME}\n")

    for name, local_path in SYNC_TARGETS.items():
        repo_path = sync_dir / name
        local_exists = local_path.exists()
        repo_exists = repo_path.exists()

        print(f"  {name}:")
        print(f"    local: {'✓' if local_exists else '✗'} {local_path}")
        print(f"    repo:  {'✓' if repo_exists else '✗'} {repo_path}")

        if local_exists and repo_exists:
            if local_path.is_file():
                lc = read_text_safe(local_path)
                rc = read_text_safe(repo_path)
                status = "in sync" if lc == rc else "differs"
            else:
                lf = set(collect_files(local_path))
                rf = set(collect_files(repo_path))
                only_local = lf - rf
                only_repo = rf - lf
                common = lf & rf
                diffs = sum(1 for f in common if read_text_safe(local_path / f) != read_text_safe(repo_path / f))
                parts = []
                if only_local:
                    parts.append(f"{len(only_local)} local only")
                if only_repo:
                    parts.append(f"{len(only_repo)} repo only")
                if diffs:
                    parts.append(f"{diffs} differ")
                status = ", ".join(parts) if parts else "in sync"
            print(f"    status: {status}")
        elif local_exists:
            print("    status: local only (not in repo)")
        elif repo_exists:
            print("    status: repo only (not on local)")
        else:
            print("    status: missing")
        print()


def main():
    parser = argparse.ArgumentParser(
        prog="ccsync",
        description="Sync ~/.claude/CLAUDE.md and ~/.claude/skills/ between devices via git repo.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_push = sub.add_parser("push", help="Push local config to repo and git push")
    p_push.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompts")
    p_push.add_argument("-m", "--message", help="Custom commit message")

    p_pull = sub.add_parser("pull", help="Pull repo config to local ~/.claude")
    p_pull.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompts")
    p_pull.add_argument("--no-fetch", action="store_true", help="Skip git pull before syncing")

    p_diff = sub.add_parser("diff", help="Show diff without applying changes")
    p_diff.add_argument("direction", nargs="?", default="push", choices=["push", "pull"],
                        help="Direction to diff (default: push)")

    sub.add_parser("status", help="Show sync status overview")

    args = parser.parse_args()
    cmds = {"push": cmd_push, "pull": cmd_pull, "diff": cmd_diff, "status": cmd_status}
    cmds[args.command](args)


if __name__ == "__main__":
    main()
