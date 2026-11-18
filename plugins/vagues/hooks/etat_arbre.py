"""Working-tree snapshot for gab-stop-check.py.

The SubagentStart hook saves a snapshot when gab starts; the SubagentStop hook
compares the tree with it, so changes that existed before gab started are not
counted as gab's. Snapshots are keyed by the subagent's agent_id.
"""
import hashlib
import json
import os
import subprocess
import tempfile

ALLOWED_DIRS = ("research", "data")


def state_path(key):
    directory = os.path.join(tempfile.gettempdir(), "gab-hooks")
    os.makedirs(directory, exist_ok=True)
    return os.path.join(directory, f"{key or 'default'}.json")


def tree(project_dir):
    """Map each changed or untracked path to a hash of its content."""
    out = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "-uall"],
        cwd=project_dir, capture_output=True, check=True,
    ).stdout.decode()
    entries = out.split("\0")
    paths, i = [], 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if len(entry) < 4:
            continue
        paths.append(entry[3:])
        if entry[0] in "RC":  # renames and copies carry the source path next
            paths.append(entries[i])
            i += 1
    result = {}
    for path in paths:
        full = os.path.join(project_dir, path)
        if os.path.isfile(full):
            with open(full, "rb") as f:
                result[path] = hashlib.sha256(f.read()).hexdigest()
        else:
            result[path] = "deleted"
    return result


def changed(before, after):
    """Paths whose state differs between two trees (absent means clean)."""
    return sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))


def is_allowed(path):
    return any(path == d or path.startswith(d + "/") for d in ALLOWED_DIRS)


def load(key):
    try:
        with open(state_path(key), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def save(key, state):
    with open(state_path(key), "w", encoding="utf-8") as f:
        json.dump(state, f)


def clear(key):
    try:
        os.remove(state_path(key))
    except FileNotFoundError:
        pass
