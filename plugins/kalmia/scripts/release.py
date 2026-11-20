#!/usr/bin/env python3
"""Tâches mécaniques de la commande /release du plugin kalmia : notes, tests et tag.

  release.py notes <tag> [--depuis <commit|tag|date>] [--sortie <fichier>]
      Liste les PR fusionnées dans HEAD depuis le tag précédent (ou depuis
      --depuis, ou depuis le début s'il n'y a aucun tag), en Markdown.

  release.py tests
      Lance la suite de tests complète du projet, sans rien créer.

  release.py tag <tag> --notes <fichier>
      Vérifie : nom valide, tag inexistant (local et origin), branche main,
      arbre propre, main à jour avec origin/main, notes non vides. Lance
      ensuite la suite de tests complète. Seulement si elle réussit : tag
      annoté sur HEAD, puis push du tag seul vers origin. Sinon : aucun tag.

Suite de tests complète : variable RELEASE_TEST_CMD, sinon première ligne utile
(non vide, sans « # ») du fichier .claude/tests-complets du dépôt courant.
Aucune commande par défaut : sans réglage, arrêt (aucun tag).
Le script travaille dans le dépôt courant (le projet), jamais dans le plugin.

Code de sortie 0 = réussi ; autre = arrêt, raison sur stderr, aucun tag.
"""
import argparse
import os
import re
import subprocess
import sys

BRANCH = "main"
TEST_CONFIG = os.path.join(".claude", "tests-complets")
MERGE_RE = re.compile(r"^Merge pull request #(\d+) from ")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SQUASH_RE = re.compile(r"\(#(\d+)\)\s*$")


class Stop(Exception):
    """Arrêt sans tag ; le message dit pourquoi."""


def git(*args, check=True):
    proc = subprocess.run(["git", *args], capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise Stop(f"git {' '.join(args)} : {proc.stderr.strip()}")
    return proc


def previous_tag():
    proc = git("describe", "--tags", "--abbrev=0", "HEAD", check=False)
    return proc.stdout.strip() if proc.returncode == 0 else None


def is_commit(ref):
    return git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False).returncode == 0


def merged_prs(since):
    """Renvoie (description de la base, [(numéro, titre)]) dans l'ordre chronologique."""
    if since is None:
        since = previous_tag()
        if since is None:
            base, args = "depuis le début (aucun tag précédent)", ["HEAD"]
        else:
            base, args = f"depuis le tag {since}", [f"{since}..HEAD"]
    elif is_commit(since):
        base, args = f"depuis {since}", [f"{since}..HEAD"]
    elif DATE_RE.match(since):
        base, args = f"depuis le {since}", ["HEAD", f"--since={since}T00:00:00"]
    else:
        raise Stop(f"--depuis {since!r} : ni commit/tag connu, ni date AAAA-MM-JJ")
    log = git("log", "--first-parent", "--reverse", "--format=%s%x1f%b%x1e", *args).stdout
    prs = []
    for entry in log.split("\x1e"):
        if not entry.strip():
            continue
        subject, _, body = entry.strip("\n").partition("\x1f")
        merge = MERGE_RE.match(subject)
        if merge:
            title = next((line.strip() for line in body.splitlines() if line.strip()), subject)
            prs.append((int(merge.group(1)), title))
            continue
        squash = SQUASH_RE.search(subject)
        if squash:
            prs.append((int(squash.group(1)), SQUASH_RE.sub("", subject).strip()))
    return base, prs


def cmd_notes(args):
    base, prs = merged_prs(args.depuis)
    lines = [f"# {args.tag}", "", f"PR fusionnées {base} :", ""]
    if prs:
        for number, title in prs:
            title = re.sub(r"\s*\(#\d+\)\s*$", "", title)  # titre qui porte déjà son numéro d'issue
            lines.append(f"- {title} (#{number})")
    else:
        lines.append("Aucune PR fusionnée.")
    text = "\n".join(lines) + "\n"
    if args.sortie:
        with open(args.sortie, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"{len(prs)} PR, {base} → {args.sortie}")
    else:
        sys.stdout.write(text)
    return 0


def test_command():
    """Commande de la suite complète, lue dans le projet ; Stop si absente."""
    if os.environ.get("RELEASE_TEST_CMD"):
        return os.environ["RELEASE_TEST_CMD"]
    root = git("rev-parse", "--show-toplevel").stdout.strip()
    try:
        with open(os.path.join(root, TEST_CONFIG), encoding="utf-8") as f:
            for line in f:
                if line.strip() and not line.lstrip().startswith("#"):
                    return line.strip()
    except OSError:
        pass
    raise Stop(f"aucune commande de tests configurée : écris-la sur la première ligne de {TEST_CONFIG} "
               "dans le projet (ou lance /kalmia:installer-vagues), ou définis RELEASE_TEST_CMD")


def run_tests():
    test_cmd = test_command()
    print(f"Tests : {test_cmd}", flush=True)
    if subprocess.run(test_cmd, shell=True).returncode != 0:
        raise Stop(f"tests échoués ({test_cmd})")
    return test_cmd


def cmd_tests(args):
    test_cmd = run_tests()
    print(f"Tests réussis : {test_cmd}")
    return 0


def cmd_tag(args):
    tag = args.tag
    if tag.startswith("-") or tag in (BRANCH, "master", "HEAD") or \
            git("check-ref-format", f"refs/tags/{tag}", check=False).returncode != 0:
        raise Stop(f"nom de tag invalide : {tag!r}")
    try:
        with open(args.notes, encoding="utf-8") as f:
            if not f.read().strip():
                raise Stop(f"notes vides : {args.notes}")
    except OSError as e:
        raise Stop(f"notes illisibles : {e}")
    branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if branch != BRANCH:
        raise Stop(f"il faut être sur {BRANCH} (branche actuelle : {branch})")
    if git("status", "--porcelain").stdout.strip():
        raise Stop("arbre de travail modifié ; il doit être propre")
    git("fetch", "--quiet", "--tags", "origin", BRANCH)
    head, remote = git("rev-parse", "HEAD").stdout.strip(), git("rev-parse", "FETCH_HEAD").stdout.strip()
    if head != remote:
        raise Stop(f"{BRANCH} local ({head[:7]}) différent de origin/{BRANCH} ({remote[:7]}) ; mettre à jour d'abord")
    if is_commit(f"refs/tags/{tag}"):
        raise Stop(f"le tag {tag} existe déjà")
    if git("ls-remote", "--tags", "origin", f"refs/tags/{tag}").stdout.strip():
        raise Stop(f"le tag {tag} existe déjà sur origin")

    run_tests()
    if git("status", "--porcelain").stdout.strip():
        raise Stop("les tests ont modifié l'arbre de travail")

    git("tag", "-a", tag, "-F", args.notes, head)
    git("push", "origin", f"refs/tags/{tag}")
    print(f"Tag {tag} créé sur {head[:7]} et poussé")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    notes = sub.add_parser("notes")
    notes.add_argument("tag")
    notes.add_argument("--depuis")
    notes.add_argument("--sortie")
    tag = sub.add_parser("tag")
    tag.add_argument("tag")
    tag.add_argument("--notes", required=True)
    sub.add_parser("tests")
    args = parser.parse_args()
    try:
        return {"notes": cmd_notes, "tests": cmd_tests, "tag": cmd_tag}[args.cmd](args)
    except Stop as e:
        print(f"Arrêt, aucun tag : {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
