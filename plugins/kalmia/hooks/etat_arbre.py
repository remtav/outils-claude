"""Instantané de l'arbre de travail pour implementeur-stop-check.py.

Copie de gab_state.py (remtav/template), sans ses règles propres à ce dépôt-là.
Le hook SubagentStart enregistre un instantané au départ de l'implémenteur ; le
contrôle de fin compare l'arbre avec lui, pour ne pas compter les modifications
qui existaient déjà. État rangé dans le dossier temporaire, par clé (agent_id).
"""
import hashlib
import json
import os
import subprocess
import tempfile

def state_path(key):
    directory = os.path.join(tempfile.gettempdir(), "vagues-hooks")
    os.makedirs(directory, exist_ok=True)
    return os.path.join(directory, f"{key or 'default'}.json")


def tree(project_dir):
    """Chemin modifié ou non suivi → empreinte de son contenu (« deleted » si supprimé)."""
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
        if entry[0] in "RC":  # renommage ou copie : le chemin source suit
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
    """Chemins dont l'état diffère entre deux arbres (absent = propre)."""
    return sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))


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
