"""Tests de plugins/kalmia/scripts/release.py (sous-commandes notes, tests et tag de /release).

Lancer : python3 -m unittest discover -s tests/release -v

Chaque test travaille dans un dépôt git jetable (dossier temporaire) avec un dépôt
« origin » nu, local : aucun tag n'est jamais créé ni poussé dans le vrai dépôt.
La commande de tests de la release est remplacée par RELEASE_TEST_CMD
(« true » = tests réussis, « false » = tests échoués), ou lue dans le fichier
.claude/tests-complets du dépôt jetable (classe CommandeDuProjet).
"""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.environ.get("RELEASE_SCRIPT") or os.path.join(ROOT, "plugins", "kalmia", "scripts", "release.py")


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


class DepotJetable(unittest.TestCase):
    """Un dépôt « travail » cloné d'un dépôt nu « origin », sur main."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = self.tmp.name
        self.origin = os.path.join(base, "origin.git")
        self.work = os.path.join(base, "travail")
        git(base, "init", "-q", "--bare", "-b", "main", self.origin)
        git(base, "clone", "-q", self.origin, self.work)
        for key, value in (("user.name", "Test"), ("user.email", "test@example.invalid"),
                           ("commit.gpgsign", "false"), ("tag.gpgsign", "false")):
            git(self.work, "config", key, value)
        git(self.work, "switch", "-q", "-c", "main")
        self.commit("depart")
        git(self.work, "push", "-q", "-u", "origin", "main")

    def commit(self, name):
        with open(os.path.join(self.work, name), "w") as f:
            f.write(name)
        git(self.work, "add", name)
        git(self.work, "commit", "-q", "-m", name)

    def merge_pr(self, number, title, branch=None):
        """Simule une PR fusionnée par un commit de fusion, comme GitHub."""
        branch = branch or f"b{number}"
        git(self.work, "switch", "-q", "-c", branch)
        self.commit(f"f{number}")
        git(self.work, "switch", "-q", "main")
        git(self.work, "merge", "-q", "--no-ff", branch,
            "-m", f"Merge pull request #{number} from o/{branch}", "-m", title)
        git(self.work, "push", "-q", "origin", "main")

    def run_script(self, *args, test_cmd="true"):
        env = dict(os.environ, RELEASE_TEST_CMD=test_cmd)
        if test_cmd is None:
            env.pop("RELEASE_TEST_CMD")
        return subprocess.run([sys.executable, SCRIPT, *args], cwd=self.work,
                              capture_output=True, text=True, env=env)

    def notes_file(self, text="Notes\n"):
        path = os.path.join(self.tmp.name, "notes.md")
        with open(path, "w") as f:
            f.write(text)
        return path

    def tags(self, where=None):
        return git(where or self.work, "tag", "--list").split()


class Tag(DepotJetable):
    def test_aucun_tag_si_les_tests_echouent(self):
        proc = self.run_script("tag", "v0.1", "--notes", self.notes_file(), test_cmd="false")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("aucun tag", proc.stdout + proc.stderr)
        self.assertEqual(self.tags(), [])
        self.assertEqual(self.tags(self.origin), [])

    def test_tag_annote_et_pousse_si_les_tests_reussissent(self):
        proc = self.run_script("tag", "v0.1", "--notes", self.notes_file("Notes v0.1\n"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.tags(self.origin), ["v0.1"])
        self.assertEqual(git(self.work, "cat-file", "-t", "v0.1"), "tag")  # annoté
        self.assertIn("Notes v0.1", git(self.work, "tag", "-l", "--format=%(contents)", "v0.1"))
        self.assertEqual(git(self.work, "rev-parse", "v0.1^{commit}"), git(self.work, "rev-parse", "origin/main"))

    def test_les_tests_tournent_avant_le_tag(self):
        marker = os.path.join(self.tmp.name, "tests-lances")
        proc = self.run_script("tag", "v0.1", "--notes", self.notes_file(), test_cmd=f"touch {marker}")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(os.path.exists(marker))

    def test_refuse_un_tag_existant(self):
        git(self.work, "tag", "v0.1")
        proc = self.run_script("tag", "v0.1", "--notes", self.notes_file())
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(self.tags(self.origin), [])

    def test_refuse_si_main_local_nest_pas_a_jour(self):
        other = os.path.join(self.tmp.name, "autre")
        git(self.tmp.name, "clone", "-q", self.origin, other)
        git(other, "config", "user.name", "T")
        git(other, "config", "user.email", "t@example.invalid")
        with open(os.path.join(other, "x"), "w") as f:
            f.write("x")
        git(other, "add", "x")
        git(other, "commit", "-q", "-m", "x")
        git(other, "push", "-q", "origin", "main")
        proc = self.run_script("tag", "v0.1", "--notes", self.notes_file())
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(self.tags(self.origin), [])

    def test_refuse_hors_de_main(self):
        git(self.work, "switch", "-q", "-c", "autre")
        proc = self.run_script("tag", "v0.1", "--notes", self.notes_file())
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(self.tags(self.origin), [])

    def test_refuse_un_arbre_de_travail_modifie(self):
        with open(os.path.join(self.work, "depart"), "w") as f:
            f.write("modifié")
        proc = self.run_script("tag", "v0.1", "--notes", self.notes_file())
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(self.tags(self.origin), [])

    def test_refuse_des_notes_vides_ou_absentes(self):
        for notes in (self.notes_file("  \n"), os.path.join(self.tmp.name, "absent.md")):
            proc = self.run_script("tag", "v0.1", "--notes", notes)
            self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(self.tags(self.origin), [])

    def test_refuse_un_nom_de_tag_invalide(self):
        for name in ("main", "-v1", "v 1", "v0.1..x"):
            proc = self.run_script("tag", name, "--notes", self.notes_file())
            self.assertNotEqual(proc.returncode, 0, name)
        self.assertEqual(self.tags(self.origin), [])


class Notes(DepotJetable):
    def test_sans_tag_precedent_depuis_le_debut(self):
        self.merge_pr(1, "Première PR")
        self.merge_pr(2, "Deuxième PR")
        proc = self.run_script("notes", "v0.1")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Première PR (#1)", proc.stdout)
        self.assertIn("Deuxième PR (#2)", proc.stdout)
        self.assertIn("depuis le début", proc.stdout)

    def test_depuis_le_tag_precedent(self):
        self.merge_pr(1, "Avant le tag")
        git(self.work, "tag", "-a", "v0.1", "-m", "v0.1")
        self.merge_pr(2, "Après le tag")
        proc = self.run_script("notes", "v0.2")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Après le tag (#2)", proc.stdout)
        self.assertNotIn("Avant le tag", proc.stdout)
        self.assertIn("v0.1", proc.stdout)

    def test_depuis_un_commit_donne(self):
        self.merge_pr(1, "Ancienne")
        start = git(self.work, "rev-parse", "HEAD")
        self.merge_pr(2, "Nouvelle")
        proc = self.run_script("notes", "v0.1", "--depuis", start)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Nouvelle (#2)", proc.stdout)
        self.assertNotIn("Ancienne", proc.stdout)

    def test_depuis_une_date_future_ne_liste_rien(self):
        self.merge_pr(1, "Ancienne")
        proc = self.run_script("notes", "v0.1", "--depuis", "2099-01-01")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("Ancienne", proc.stdout)
        self.assertIn("Aucune PR fusionnée", proc.stdout)

    def test_refuse_un_depuis_inconnu(self):
        proc = self.run_script("notes", "v0.1", "--depuis", "pas-un-commit")
        self.assertNotEqual(proc.returncode, 0)

    def test_pr_fusionnee_par_squash(self):
        self.commit("squash")
        git(self.work, "commit", "-q", "--amend", "-m", "Titre écrasé (#7)")
        proc = self.run_script("notes", "v0.1")
        self.assertIn("Titre écrasé (#7)", proc.stdout)

    def test_ignore_les_commits_des_branches_fusionnees(self):
        self.merge_pr(3, "La PR")
        proc = self.run_script("notes", "v0.1")
        self.assertNotIn("f3", proc.stdout)  # message du commit interne à la PR

    def test_ecrit_dans_un_fichier(self):
        self.merge_pr(1, "Une PR")
        out = os.path.join(self.tmp.name, "sortie.md")
        proc = self.run_script("notes", "v0.1", "--sortie", out)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        with open(out) as f:
            self.assertIn("Une PR (#1)", f.read())


class CommandeDuProjet(DepotJetable):
    """Commande de tests lue dans le projet (plus de « npm ci && npm test » par défaut)."""

    def write_config(self, content):
        os.makedirs(os.path.join(self.work, ".claude"), exist_ok=True)
        with open(os.path.join(self.work, ".claude", "tests-complets"), "w") as f:
            f.write(content)
        git(self.work, "add", ".claude")
        git(self.work, "commit", "-q", "-m", "config")
        git(self.work, "push", "-q", "origin", "main")

    def test_commande_lue_dans_le_fichier_du_projet(self):
        marker = os.path.join(self.tmp.name, "tests-lances")
        self.write_config(f"# commentaire\n\ntouch {marker}\n")
        proc = self.run_script("tag", "v0.1", "--notes", self.notes_file(), test_cmd=None)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(os.path.exists(marker))
        self.assertEqual(self.tags(self.origin), ["v0.1"])

    def test_variable_prioritaire_sur_le_fichier(self):
        self.write_config("false\n")
        proc = self.run_script("tag", "v0.1", "--notes", self.notes_file(), test_cmd="true")
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_sans_commande_configuree_aucun_tag(self):
        proc = self.run_script("tag", "v0.1", "--notes", self.notes_file(), test_cmd=None)
        self.assertNotEqual(proc.returncode, 0)
        sortie = proc.stdout + proc.stderr
        self.assertIn("aucun tag", sortie)
        self.assertIn(".claude/tests-complets", sortie)
        self.assertNotIn("npm", sortie)
        self.assertEqual(self.tags(self.origin), [])


class Tests(DepotJetable):
    """Sous-commande `tests` : lance la suite complète du projet, sans rien créer."""

    def test_reussie(self):
        proc = self.run_script("tests", test_cmd="true")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("réussi", proc.stdout)

    def test_echouee(self):
        proc = self.run_script("tests", test_cmd="false")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("tests échoués", proc.stderr)
        self.assertEqual(self.tags(), [])

    def test_sans_commande_configuree(self):
        proc = self.run_script("tests", test_cmd=None)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn(".claude/tests-complets", proc.stderr)


if __name__ == "__main__":
    unittest.main()
