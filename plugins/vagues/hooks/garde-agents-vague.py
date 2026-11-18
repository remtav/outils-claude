#!/usr/bin/env python3
"""Garde des agents de vague (PreToolUse, déclaré dans hooks/hooks.json du plugin vagues).

Règles `implementeur` et `reviseur` extraites de `agent-guard.py` (remtav/template) :
- aucun des deux ne fusionne (Bash `gh pr merge`, MCP `merge_pull_request` et
  `enable_pr_auto_merge`) ni n'approuve (`gh pr review --approve`, MCP
  `pull_request_review_write` avec `event: APPROVE`) ;
- pas de push sur main/master, pas de push forcé ni de suppression de branche ;
- écritures MCP de fichiers seulement sur une branche autre que main/master ;
- `reviseur` en plus : ni commit, ni push, ni écriture de fichier.

L'agent vient de `agent_type` (dans un sous-agent, avec le préfixe du plugin :
`vagues:implementeur`) ou de argv[1] (mode agent principal) ; les deux formes, avec
ou sans préfixe, sont acceptées. Tout autre agent, et la session principale, passent :
leurs règles éventuelles restent dans le projet.

Sortie 2 = appel bloqué, raison sur stderr. Toute erreur bloque aussi (échec fermé).
"""
import json
import os
import re
import shlex
import sys

RULES = {
    # seul l'orchestrateur (session principale) fusionne
    "implementeur": {"dirs": None, "no_git_write": False},
    "reviseur": {"dirs": (), "no_git_write": True},
}
PREFIX = "vagues:"
PROTECTED_BRANCHES = ("main", "master")
FILE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
MCP_MERGE_TOOLS = ("mcp__github__merge_pull_request", "mcp__github__enable_pr_auto_merge")
MCP_APPROVE_TOOL = "mcp__github__pull_request_review_write"
MCP_FILE_WRITE_TOOLS = ("mcp__github__push_files", "mcp__github__create_or_update_file", "mcp__github__delete_file")


def segments(command):
    for segment in re.split(r"[;&|\n]+", command):
        try:
            yield shlex.split(segment)
        except ValueError:
            yield segment.split()


def git_verbs(command):
    """Sous-commande de chaque appel à git, options globales sautées."""
    for words in segments(command):
        for i, word in enumerate(words):
            if os.path.basename(word) != "git":
                continue
            j = i + 1
            while j < len(words) and words[j].startswith("-"):
                j += 2 if words[j] in ("-C", "-c", "--git-dir", "--work-tree") else 1
            if j < len(words):
                yield words[j]


def bash_reason(command):
    """Pourquoi une commande Bash pousse sur main, force, fusionne ou approuve ; sinon None."""
    for words in segments(command):
        if "git" in map(os.path.basename, words) and "push" in words:
            args = words[words.index("push") + 1:]
            if any(a in ("-f", "--force", "--force-with-lease", "--mirror", "--delete", "-d") or a.startswith("--force")
                   for a in args):
                return "pas de push forcé ni de suppression de branche."
            if any(a.split(":")[-1].removeprefix("+").removeprefix("refs/heads/") in PROTECTED_BRANCHES for a in args):
                return "pas de push sur main : pousse une branche et ouvre une PR."
        if words[:3] == ["gh", "pr", "merge"]:
            return "cet agent ne fusionne pas ; seul l'orchestrateur (session principale) fusionne."
        if words[:3] == ["gh", "pr", "review"] and ("--approve" in words or "-a" in words):
            return "les agents n'approuvent pas de PR ; le verdict est un commentaire."
    return None


def mcp_reason(agent, rules, tool, tool_input):
    """Pourquoi un appel MCP GitHub fusionne, approuve ou écrit où il ne doit pas ; sinon None."""
    if tool in MCP_MERGE_TOOLS:
        return "cet agent ne fusionne pas ; seul l'orchestrateur (session principale) fusionne."
    if tool == MCP_APPROVE_TOOL and str(tool_input.get("event", "")).upper() == "APPROVE":
        return "les agents n'approuvent pas de PR ; le verdict est un commentaire."
    if tool in MCP_FILE_WRITE_TOOLS:
        if rules["dirs"] == ():
            return f"{agent} n'écrit aucun fichier."
        branch = str(tool_input.get("branch") or "").removeprefix("refs/heads/")
        if not branch or branch in PROTECTED_BRANCHES:
            return f"pas d'écriture MCP sur {branch or 'la branche par défaut'} ; écris sur la branche de la PR."
    return None


def check(agent, event):
    """Raison de bloquer, ou None."""
    rules = RULES[agent]
    tool = event.get("tool_name", "")
    tool_input = event.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        raise ValueError("tool_input n'est pas un objet")  # échec fermé

    if tool.startswith("mcp__"):
        return mcp_reason(agent, rules, tool, tool_input)

    if tool == "Bash":
        command = str(tool_input.get("command", ""))
        if rules["no_git_write"] and any(verb in ("commit", "push") for verb in git_verbs(command)):
            return f"{agent} ne commite ni ne pousse."
        return bash_reason(command)

    if tool in FILE_TOOLS and rules["dirs"] == ():
        path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
        return f"{agent} n'écrit aucun fichier (reçu : {path})."
    return None


def main():
    event = json.load(sys.stdin)
    if not isinstance(event, dict):
        raise ValueError("entrée du hook illisible")
    agent = sys.argv[1] if len(sys.argv) > 1 else event.get("agent_type")
    agent = str(agent or "").removeprefix(PREFIX) if str(agent or "").startswith(PREFIX) else agent
    if agent not in RULES:
        return 0
    reason = check(agent, event)
    if reason:
        print(f"Bloqué par le garde des agents de vague ({agent}) : {reason}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # échec fermé
        print(f"Erreur du garde des agents de vague, appel bloqué : {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(2)
