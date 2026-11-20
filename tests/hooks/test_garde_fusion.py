"""Tests de plugins/kalmia/hooks/garde-fusion.py par entrées JSON factices.

Lancer : python3 -m unittest discover -s tests/hooks -v
Aucun appel réseau : un faux `gh` (placé en tête du PATH) répond à partir d'un
dictionnaire « point d'accès de l'API → JSON » passé dans la variable FAUX_GH.
"""
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HOOK = os.path.join(ROOT, "plugins", "kalmia", "hooks", "garde-fusion.py")

HEAD = "a" * 40
OLD = "b" * 40

FAUX_GH = textwrap.dedent("""\
    #!/usr/bin/env python3
    import json, os, sys
    with open(os.environ["FAUX_GH_LOG"], "a") as log:
        log.write(" ".join(sys.argv[1:]) + "\\n")
    reponses = json.loads(os.environ.get("FAUX_GH", "{}"))
    if len(sys.argv) < 3 or sys.argv[1] != "api" or sys.argv[2] not in reponses:
        print("gh: HTTP 404: Not Found", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(reponses[sys.argv[2]]))
    """)


def marqueur(verdict, sha):
    return {"body": f"Revue faite.\n<!-- verdict-reviseur: {verdict} sha={sha} -->"}


def api(owner="o", repo="r", pr=12, head=HEAD, checks=None, statuses=None, comments=None, reviews=None,
        branch="12-truc"):
    """Réponses factices de l'API REST pour une PR."""
    base = f"repos/{owner}/{repo}"
    pull = {"number": pr, "state": "open", "head": {"sha": head, "ref": branch}}
    return {
        f"{base}/pulls/{pr}": pull,
        f"{base}/pulls?head={owner}:{branch}&state=open&per_page=100": [pull],
        f"{base}/commits/{head}/check-runs?per_page=100&page=1": {
            "total_count": len(checks or []), "check_runs": checks or []},
        f"{base}/commits/{head}/status": {"state": "success" if statuses else "pending", "statuses": statuses or []},
        f"{base}/issues/{pr}/comments?per_page=100&page=1": comments or [],
        f"{base}/pulls/{pr}/reviews?per_page=100&page=1": reviews or [],
    }


OK_CHECK = {"name": "tests", "status": "completed", "conclusion": "success"}
OK_API = api(checks=[OK_CHECK], comments=[marqueur("approuvé", HEAD)])
MERGE = ("mcp__github__merge_pull_request", {"owner": "o", "repo": "r", "pullNumber": 12, "merge_method": "merge"})


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bin = os.path.join(self.tmp.name, "bin")
        os.mkdir(self.bin)
        gh = os.path.join(self.bin, "gh")
        with open(gh, "w") as f:
            f.write(FAUX_GH)
        os.chmod(gh, 0o755)
        self.log = os.path.join(self.tmp.name, "gh.log")
        open(self.log, "w").close()
        # projet factice : un dépôt git dont l'origine est o/r, sur la branche 12-truc
        self.project = os.path.join(self.tmp.name, "projet")
        os.mkdir(self.project)
        for cmd in (["git", "init", "-q", "-b", "12-truc"],
                    ["git", "remote", "add", "origin", "https://github.com/o/r.git"]):
            subprocess.run(cmd, cwd=self.project, check=True)

    def run_hook(self, tool, tool_input, reponses=None, agent_type=None, extra_env=None, path=None, raw=None):
        event = {"tool_name": tool, "tool_input": tool_input, "cwd": self.project}
        if agent_type:
            event["agent_type"] = agent_type
        env = dict(os.environ, CLAUDE_PROJECT_DIR=self.project, FAUX_GH=json.dumps(reponses or {}),
                   FAUX_GH_LOG=self.log, PATH=path if path is not None else self.bin + os.pathsep + os.environ["PATH"])
        env.pop("HOOKS_QUALITE_DESACTIVES", None)
        env.update(extra_env or {})
        proc = subprocess.run([sys.executable, HOOK], input=raw if raw is not None else json.dumps(event),
                              capture_output=True, text=True, env=env, cwd=self.project)
        return proc.returncode, proc.stderr

    def gh_calls(self):
        with open(self.log) as f:
            return f.read().splitlines()


class HorsFusion(Base):
    def test_commandes_ordinaires_sans_appel_github(self):
        for command in ("ls -la", "git status", "gh pr view 12", "gh pr checks 12", "npm test",
                        "echo 'gh pr merge 12'", "gh pr merge --disable-auto 12"):
            with self.subTest(command=command):
                self.assertEqual(self.run_hook("Bash", {"command": command})[0], 0)
        self.assertEqual(self.gh_calls(), [])

    def test_autres_outils_ignores(self):
        for tool in ("Write", "mcp__github__pull_request_read", "mcp__github__create_pull_request"):
            with self.subTest(tool=tool):
                self.assertEqual(self.run_hook(tool, {"file_path": "x", "pullNumber": 12})[0], 0)
        self.assertEqual(self.gh_calls(), [])


class FusionMcp(Base):
    def test_ci_verte_et_approbation_sur_la_tete_autorise(self):
        code, err = self.run_hook(*MERGE, OK_API)
        self.assertEqual(code, 0, err)

    def test_vaut_pour_tous_les_agents(self):
        for agent in (None, "jf", "implementeur", "kalmia:implementeur"):
            with self.subTest(agent=agent):
                self.assertEqual(self.run_hook(*MERGE, api(checks=[OK_CHECK]), agent_type=agent)[0], 2)

    def test_sans_marqueur_refuse(self):
        code, err = self.run_hook(*MERGE, api(checks=[OK_CHECK]))
        self.assertEqual(code, 2)
        self.assertIn("réviseur", err)

    def test_approbation_sur_un_ancien_commit_refuse(self):
        code, err = self.run_hook(*MERGE, api(checks=[OK_CHECK], comments=[marqueur("approuvé", OLD)]))
        self.assertEqual(code, 2)
        self.assertIn(HEAD[:7], err)

    def test_dernier_verdict_refuse_l_emporte(self):
        comments = [marqueur("approuvé", HEAD), marqueur("refusé", HEAD)]
        self.assertEqual(self.run_hook(*MERGE, api(checks=[OK_CHECK], comments=comments))[0], 2)

    def test_approbation_apres_refus_autorise(self):
        comments = [marqueur("refusé", HEAD), marqueur("approuvé", HEAD)]
        self.assertEqual(self.run_hook(*MERGE, api(checks=[OK_CHECK], comments=comments))[0], 0)

    def test_marqueur_dans_une_revue_github_compte(self):
        reviews = [{"body": marqueur("approuvé", HEAD)["body"], "commit_id": HEAD}]
        self.assertEqual(self.run_hook(*MERGE, api(checks=[OK_CHECK], reviews=reviews))[0], 0)

    def test_sha_abrege_ou_texte_libre_ne_comptent_pas(self):
        for body in (f"<!-- verdict-reviseur: approuvé sha={HEAD[:7]} -->", "Approuvé, verdict-reviseur ok",
                     f"verdict-reviseur: approuvé sha={HEAD}"):
            with self.subTest(body=body):
                self.assertEqual(self.run_hook(*MERGE, api(checks=[OK_CHECK], comments=[{"body": body}]))[0], 2)

    def test_ci_absente_refuse(self):
        code, err = self.run_hook(*MERGE, api(comments=[marqueur("approuvé", HEAD)]))
        self.assertEqual(code, 2)
        self.assertIn("CI", err)

    def test_ci_rouge_refuse(self):
        checks = [OK_CHECK, {"name": "e2e", "status": "completed", "conclusion": "failure"}]
        code, err = self.run_hook(*MERGE, api(checks=checks, comments=[marqueur("approuvé", HEAD)]))
        self.assertEqual(code, 2)
        self.assertIn("e2e", err)

    def test_ci_en_cours_refuse(self):
        checks = [OK_CHECK, {"name": "e2e", "status": "in_progress", "conclusion": None}]
        self.assertEqual(self.run_hook(*MERGE, api(checks=checks, comments=[marqueur("approuvé", HEAD)]))[0], 2)

    def test_statut_de_commit_rouge_refuse(self):
        statuses = [{"context": "ci/autre", "state": "failure"}]
        self.assertEqual(self.run_hook(*MERGE, api(checks=[OK_CHECK], statuses=statuses,
                                                   comments=[marqueur("approuvé", HEAD)]))[0], 2)

    def test_statuts_de_commit_seuls_verts_autorise(self):
        statuses = [{"context": "ci/autre", "state": "success"}]
        self.assertEqual(self.run_hook(*MERGE, api(statuses=statuses, comments=[marqueur("approuvé", HEAD)]))[0], 0)

    def test_vérification_ignorée_mais_une_réussie_autorise(self):
        checks = [OK_CHECK, {"name": "e2e", "status": "completed", "conclusion": "skipped"}]
        self.assertEqual(self.run_hook(*MERGE, api(checks=checks, comments=[marqueur("approuvé", HEAD)]))[0], 0)

    def test_fusion_automatique_aussi_gardee(self):
        tool = ("mcp__github__enable_pr_auto_merge", {"owner": "o", "repo": "r", "pullNumber": 12})
        self.assertEqual(self.run_hook(*tool, api(checks=[OK_CHECK]))[0], 2)
        self.assertEqual(self.run_hook(*tool, OK_API)[0], 0)


class EchecFerme(Base):
    def test_erreur_api_bloque(self):
        code, err = self.run_hook(*MERGE, {})
        self.assertEqual(code, 2)
        self.assertIn("garde de fusion", err.lower())

    def test_gh_absent_bloque(self):
        empty = os.path.join(self.tmp.name, "vide")
        os.mkdir(empty)
        code, _ = self.run_hook(*MERGE, OK_API, path=empty + os.pathsep + os.path.dirname(sys.executable))
        self.assertEqual(code, 2)

    def test_entree_incomplete_bloque(self):
        self.assertEqual(self.run_hook("mcp__github__merge_pull_request", {"owner": "o", "repo": "r"}, OK_API)[0], 2)

    def test_json_invalide_bloque(self):
        self.assertEqual(self.run_hook("Bash", {}, raw="pas du json")[0], 2)


class FusionBash(Base):
    def test_gh_pr_merge_numero_depot_de_l_origine(self):
        self.assertEqual(self.run_hook("Bash", {"command": "gh pr merge 12 --merge"}, OK_API)[0], 0)
        self.assertEqual(self.run_hook("Bash", {"command": "gh pr merge 12 --merge"}, api(checks=[OK_CHECK]))[0], 2)

    def test_gh_pr_merge_dans_une_commande_composee(self):
        command = "git fetch -q && gh pr merge 12 --squash --delete-branch"
        self.assertEqual(self.run_hook("Bash", {"command": command}, api(checks=[OK_CHECK]))[0], 2)

    def test_gh_pr_merge_sans_numero_branche_courante(self):
        self.assertEqual(self.run_hook("Bash", {"command": "gh pr merge --merge"}, OK_API)[0], 0)
        self.assertEqual(self.run_hook("Bash", {"command": "gh pr merge --merge"}, api(checks=[OK_CHECK]))[0], 2)

    def test_gh_pr_merge_autre_depot_et_url(self):
        reponses = api(owner="x", repo="y", pr=5, checks=[OK_CHECK], comments=[marqueur("approuvé", HEAD)])
        for command in ("gh pr merge 5 -R x/y --merge", "gh pr merge --repo=x/y 5",
                        "gh pr merge https://github.com/x/y/pull/5 --merge"):
            with self.subTest(command=command):
                self.assertEqual(self.run_hook("Bash", {"command": command}, reponses)[0], 0)
        self.assertEqual(self.run_hook("Bash", {"command": "gh pr merge 5 -R x/y"}, api(owner="x", repo="y", pr=5))[0], 2)

    def test_gh_pr_merge_auto_garde(self):
        self.assertEqual(self.run_hook("Bash", {"command": "gh pr merge 12 --auto --merge"}, api(checks=[OK_CHECK]))[0], 2)

    def test_gh_api_put_merge_garde(self):
        command = "gh api -X PUT repos/o/r/pulls/12/merge -f merge_method=merge"
        self.assertEqual(self.run_hook("Bash", {"command": command}, api(checks=[OK_CHECK]))[0], 2)
        self.assertEqual(self.run_hook("Bash", {"command": command}, OK_API)[0], 0)


class Desactivation(Base):
    def test_variable_d_environnement(self):
        for value in ("garde-fusion", "lint-fichier,garde-fusion", "tous"):
            with self.subTest(value=value):
                code, _ = self.run_hook(*MERGE, {}, extra_env={"HOOKS_QUALITE_DESACTIVES": value})
                self.assertEqual(code, 0)
        self.assertEqual(self.run_hook(*MERGE, {}, extra_env={"HOOKS_QUALITE_DESACTIVES": "lint-fichier"})[0], 2)


if __name__ == "__main__":
    unittest.main()
