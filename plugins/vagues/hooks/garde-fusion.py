#!/usr/bin/env python3
"""Garde de fusion (PreToolUse, tous les agents et la session principale ; hooks/hooks.json du plugin vagues).

Avant une fusion de PR, quel que soit le chemin :
- outils MCP `mcp__github__merge_pull_request` et `mcp__github__enable_pr_auto_merge` ;
- Bash `gh pr merge …` (y compris `--auto`) et `gh api … pulls/<n>/merge` ;
vérifie, pour le SHA de tête de la PR :
1. CI : au moins une vérification (check run ou statut de commit), toutes terminées
   et réussies (`success`, ou `neutral`/`skipped` à côté d'au moins un succès) ;
2. réviseur : le dernier marqueur `<!-- verdict-reviseur: approuvé|refusé sha=<sha> -->`
   (commentaire ou revue de la PR) qui porte ce SHA complet dit `approuvé`.
   Un nouveau commit invalide donc l'approbation.

L'API GitHub est lue par `gh api` (REST ; GraphQL est refusé dans les sessions cloud,
où le proxy fournit l'authentification). Sortie 2 = fusion bloquée, raison sur stderr.
Toute erreur (gh absent, API en échec, entrée illisible) bloque : échec fermé.
Désactivation temporaire : HOOKS_QUALITE_DESACTIVES contient `garde-fusion` ou `tous`.
"""
import json
import os
import re
import shlex
import subprocess
import sys

NOM = "garde-fusion"
MCP_MERGE_TOOLS = ("mcp__github__merge_pull_request", "mcp__github__enable_pr_auto_merge")
MARQUEUR = re.compile(r"<!--\s*verdict-reviseur:\s*(approuvé|refusé)\s+sha=([0-9a-f]{40})\s*-->", re.IGNORECASE)
API_MERGE = re.compile(r"(?:^|/)repos/([^/\s]+)/([^/\s]+)/pulls/(\d+)/merge/?$")
PR_URL = re.compile(r"github\.com/([^/\s]+)/([^/\s]+)/pull/(\d+)")
GH_PR_MERGE_VALUE_FLAGS = ("-R", "--repo", "-b", "--body", "-F", "--body-file", "-t", "--subject",
                           "-A", "--author-email", "--match-head-commit")


class Refus(Exception):
    """Fusion refusée, avec la raison."""


def desactive():
    valeurs = {v.strip() for v in os.environ.get("HOOKS_QUALITE_DESACTIVES", "").split(",")}
    return NOM in valeurs or "tous" in valeurs


def segments(command):
    for segment in re.split(r"[;&|\n]+", command):
        try:
            yield shlex.split(segment)
        except ValueError:
            yield segment.split()


def cibles_bash(command):
    """Fusions demandées par une commande Bash : liste de (repo « o/r » ou None, sélecteur ou None)."""
    cibles = []
    for words in segments(command):
        for i, word in enumerate(words):
            if os.path.basename(word) != "gh":
                continue
            rest = words[i + 1:]
            if rest[:2] == ["pr", "merge"]:
                args = rest[2:]
                if "--disable-auto" in args:
                    continue
                repo, selecteur, j = None, None, 0
                while j < len(args):
                    a = args[j]
                    if a in ("-R", "--repo"):
                        repo = args[j + 1] if j + 1 < len(args) else ""
                        j += 2
                        continue
                    if a.startswith("--repo="):
                        repo = a.split("=", 1)[1]
                    elif a in GH_PR_MERGE_VALUE_FLAGS:
                        j += 2
                        continue
                    elif not a.startswith("-") and selecteur is None:
                        selecteur = a
                    j += 1
                cibles.append((repo, selecteur))
            elif rest[:1] == ["api"]:
                for a in rest[1:]:
                    m = API_MERGE.search(a)
                    if m:
                        cibles.append((f"{m.group(1)}/{m.group(2)}", m.group(3)))
    return cibles


def gh_api(endpoint):
    try:
        proc = subprocess.run(["gh", "api", endpoint], capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        raise Refus("`gh` est introuvable : impossible de vérifier la CI et le réviseur.")
    except subprocess.TimeoutExpired:
        raise Refus(f"`gh api {endpoint}` ne répond pas.")
    if proc.returncode != 0:
        raise Refus(f"`gh api {endpoint}` a échoué : {(proc.stderr or proc.stdout).strip()[:300]}")
    return json.loads(proc.stdout)


def gh_api_pages(endpoint, cle=None):
    """Toutes les pages d'une liste (100 par page)."""
    items, page = [], 1
    while True:
        data = gh_api(f"{endpoint}{'&' if '?' in endpoint else '?'}per_page=100&page={page}")
        lot = data[cle] if cle else data
        items.extend(lot)
        if len(lot) < 100:
            return items, data
        page += 1


def depot_origine(project_dir):
    url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=project_dir,
                         capture_output=True, text=True, check=True).stdout.strip()
    parts = [p for p in re.split(r"[/:]", url.removesuffix(".git").rstrip("/")) if p]
    if len(parts) < 2:
        raise Refus(f"dépôt de l'origine illisible : {url}")
    return parts[-2], parts[-1]


def branche_courante(project_dir):
    return subprocess.run(["git", "symbolic-ref", "--short", "HEAD"], cwd=project_dir,
                          capture_output=True, text=True, check=True).stdout.strip()


def resoudre(repo, selecteur, project_dir):
    """(owner, repo, numéro) d'une cible `gh pr merge`."""
    if selecteur:
        m = PR_URL.search(selecteur)
        if m:
            return m.group(1), m.group(2), int(m.group(3))
    if repo:
        owner, _, name = repo.rpartition("/")
        owner = owner.rpartition("/")[2]  # accepte HOST/OWNER/REPO
        if not owner or not name:
            raise Refus(f"dépôt illisible : {repo!r}")
    else:
        owner, name = depot_origine(project_dir)
    if selecteur and selecteur.lstrip("#").isdigit():
        return owner, name, int(selecteur.lstrip("#"))
    branche = selecteur or branche_courante(project_dir)
    pulls = gh_api(f"repos/{owner}/{name}/pulls?head={owner}:{branche}&state=open&per_page=100")
    if len(pulls) != 1:
        raise Refus(f"aucune PR ouverte unique pour la branche {branche!r} de {owner}/{name}.")
    return owner, name, int(pulls[0]["number"])


def verifier(owner, repo, numero):
    """Lève Refus si la PR ne peut pas être fusionnée."""
    base = f"repos/{owner}/{repo}"
    pull = gh_api(f"{base}/pulls/{numero}")
    sha = pull["head"]["sha"]
    court = sha[:7]
    problemes = []

    checks, _ = gh_api_pages(f"{base}/commits/{sha}/check-runs", "check_runs")
    statuts = gh_api(f"{base}/commits/{sha}/status").get("statuses", [])
    resultats = [(c["name"], c.get("status"), c.get("conclusion")) for c in checks]
    resultats += [(s.get("context", "?"), "completed", s.get("state")) for s in statuts]
    if not resultats:
        problemes.append(f"aucune vérification CI sur le commit de tête {court} (CI absente).")
    else:
        en_cours = [n for n, st, _ in resultats if st != "completed"]
        rouges = [f"{n} ({c})" for n, st, c in resultats if st == "completed" and c not in ("success", "neutral", "skipped")]
        if en_cours:
            problemes.append(f"CI en cours sur {court} : {', '.join(en_cours)}.")
        if rouges:
            problemes.append(f"CI en échec sur {court} : {', '.join(rouges)}.")
        if not en_cours and not rouges and not any(c == "success" for _, _, c in resultats):
            problemes.append(f"aucune vérification CI réussie sur {court}.")

    commentaires, _ = gh_api_pages(f"{base}/issues/{numero}/comments")
    revues, _ = gh_api_pages(f"{base}/pulls/{numero}/reviews")
    verdicts = [m.group(1).lower() for item in commentaires + revues
                for m in MARQUEUR.finditer(item.get("body") or "") if m.group(2).lower() == sha.lower()]
    if not verdicts:
        problemes.append(f"aucune approbation du réviseur pour le commit de tête {court} "
                         f"(marqueur attendu : <!-- verdict-reviseur: approuvé sha={sha} -->).")
    elif verdicts[-1] != "approuvé":
        problemes.append(f"le dernier verdict du réviseur pour {court} est « {verdicts[-1]} ».")

    if problemes:
        raise Refus(f"PR #{numero} de {owner}/{repo} : " + " ".join(problemes))


def main():
    event = json.load(sys.stdin)
    if desactive():
        return 0
    tool = event.get("tool_name", "")
    tool_input = event.get("tool_input") or {}
    project_dir = os.path.realpath(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or os.getcwd())

    if tool in MCP_MERGE_TOOLS:
        if not isinstance(tool_input, dict) or not all(tool_input.get(k) for k in ("owner", "repo", "pullNumber")):
            raise Refus("entrée de l'outil de fusion incomplète (owner, repo, pullNumber).")
        cibles = [(str(tool_input["owner"]), str(tool_input["repo"]), int(tool_input["pullNumber"]))]
    elif tool == "Bash":
        cibles = [resoudre(r, s, project_dir) for r, s in cibles_bash(str(tool_input.get("command", "")))]
    else:
        return 0

    for owner, repo, numero in cibles:
        verifier(owner, repo, numero)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Refus as e:
        print(f"Bloqué par le garde de fusion : {e} Laisse la PR ouverte avec cette raison ; ne réessaie pas en boucle.",
              file=sys.stderr)
        sys.exit(2)
    except Exception as e:  # échec fermé
        print(f"Erreur du garde de fusion, fusion bloquée : {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(2)
