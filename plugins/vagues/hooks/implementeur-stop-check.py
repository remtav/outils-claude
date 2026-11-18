#!/usr/bin/env python3
"""Contrôle de fin de l'agent implementeur (hooks/hooks.json du plugin vagues).

Repris de remtav/template (#73), rendu générique (#72) :
- `start` (SubagentStart) : instantané de l'arbre de travail au départ.
- `handback` (PreToolUse sur SubagentHandback) : bloque la remise (sortie 2,
  raison sur stderr) tant qu'un contrôle échoue.
- sans argument (SubagentStop) : même contrôle ; décision JSON « block ».
Contrôles :
- la commande de vérification du projet réussit : variable VERIFICATION_IMPLEMENTEUR,
  sinon première ligne utile (non vide, sans « # ») de .claude/verification-implementeur
  dans le projet ($CLAUDE_PROJECT_DIR). Aucune commande par défaut : sans réglage,
  le contrôle bloque et dit où le configurer (échec fermé ; /installer-vagues crée le fichier) ;
- aucune modification non commitée depuis le départ (fichiers déjà modifiés au
  départ exclus) ;
- branche courante ni main/master ni tête détachée, et poussée sur origin.
Abandon après 3 blocages : laisse finir et demande de répondre `partiel` ou `bloqué`.
Ignore les autres agents (accepte `implementeur` et `vagues:implementeur`) et ne
fait rien sans instantané. Désactivation temporaire : HOOKS_QUALITE_DESACTIVES
contient `implementeur-stop-check` ou `tous`.
"""
import json
import os
import subprocess
import sys

sys.dont_write_bytecode = True  # pas de __pycache__ dans le dépôt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import etat_arbre  # noqa: E402  (instantané d'arbre et état, à côté de ce script)

NOM = "implementeur-stop-check"
AGENTS = ("implementeur", "vagues:implementeur")
MAX_BLOCKS = 3
PROTECTED = ("main", "master")
CONFIG = os.path.join(".claude", "verification-implementeur")
TIMEOUT = 540
MAX_SORTIE = 30


def desactive():
    valeurs = {v.strip() for v in os.environ.get("HOOKS_QUALITE_DESACTIVES", "").split(",")}
    return NOM in valeurs or "tous" in valeurs


def commande_verif(project_dir):
    if os.environ.get("VERIFICATION_IMPLEMENTEUR"):
        return os.environ["VERIFICATION_IMPLEMENTEUR"]
    try:
        with open(os.path.join(project_dir, CONFIG), encoding="utf-8") as f:
            for line in f:
                if line.strip() and not line.lstrip().startswith("#"):
                    return line.strip()
    except OSError:
        pass
    return None


def git(project_dir, *args):
    return subprocess.run(["git", *args], cwd=project_dir, capture_output=True, text=True)


def problemes_git(state, project_dir):
    problems = []
    after = etat_arbre.tree(project_dir)
    dirty = [p for p in etat_arbre.changed(state["tree"], after) if p in after]
    if dirty:
        problems.append("modifications non commitées (commite-les ou annule-les) : " + ", ".join(dirty))
    branch = git(project_dir, "symbolic-ref", "--quiet", "--short", "HEAD").stdout.strip()
    if not branch:
        problems.append("pas sur une branche (tête détachée) : travaille sur une branche N-<slug>.")
    elif branch in PROTECTED:
        problems.append(f"branche courante {branch} : travaille sur une branche N-<slug>, jamais sur main.")
    elif git(project_dir, "merge-base", "--is-ancestor", "HEAD", f"refs/remotes/origin/{branch}").returncode != 0:
        problems.append(f"branche {branch} pas poussée (ou commits non poussés) : git push -u origin {branch}.")
    return problems


def probleme_verif(project_dir):
    cmd = commande_verif(project_dir)
    if not cmd:
        return (f"aucune commande de vérification configurée : écris-la sur la première ligne de {CONFIG} "
                "dans le projet (ou lance /vagues:installer-vagues), ou définis VERIFICATION_IMPLEMENTEUR.")
    try:
        proc = subprocess.run(cmd, shell=True, cwd=project_dir, capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return f"vérification `{cmd}` : plus de {TIMEOUT} s."
    if proc.returncode == 0:
        return None
    sortie = (proc.stdout + proc.stderr).strip().splitlines()[-MAX_SORTIE:]
    return f"vérification `{cmd}` en échec (code {proc.returncode}) :\n" + "\n".join(sortie)


def main():
    event = json.load(sys.stdin)
    if event.get("agent_type") not in AGENTS or desactive():
        return 0
    mode = sys.argv[1] if len(sys.argv) > 1 else "stop"
    key = "implementeur-" + str(event.get("agent_id") or event.get("session_id") or "default")
    project_dir = os.path.realpath(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or os.getcwd())

    if mode == "start":
        etat_arbre.save(key, {"tree": etat_arbre.tree(project_dir), "blocks": 0})
        return 0

    state = etat_arbre.load(key)
    if state is None:  # pas d'instantané (hook ajouté en cours de route, ou déjà terminé)
        return 0

    problems = problemes_git(state, project_dir)
    verif = probleme_verif(project_dir)
    if verif:
        problems.append(verif)

    if problems and state["blocks"] < MAX_BLOCKS:
        state["blocks"] += 1
        etat_arbre.save(key, state)
        reason = (f"Contrôle de fin de l'implémenteur (blocage {state['blocks']}/{MAX_BLOCKS}) : "
                  "corrige avant de terminer :\n- " + "\n- ".join(problems))
        if mode == "handback":
            print(reason, file=sys.stderr)
            return 2
        print(json.dumps({"decision": "block", "reason": reason}))
        return 0

    etat_arbre.clear(key)
    if problems:
        print("Contrôle de fin de l'implémenteur : toujours en échec après 3 tentatives. Ne réponds pas `réussi` : "
              "réponds `partiel` ou `bloqué`, avec la raison :\n- " + "\n- ".join(problems), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
