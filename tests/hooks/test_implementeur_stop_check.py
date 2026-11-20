"""Tests de plugins/vagues/hooks/implementeur-stop-check.py par entrées JSON factices.

Lancer : python3 -m unittest discover -s tests/hooks -v
Chaque test travaille dans un dépôt git jetable avec un « origin » nu local, et
avec un dossier temporaire propre pour les instantanés : le vrai dépôt n'est
jamais modifié. La commande de vérification est remplacée par `true` ou `false`.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HOOK = os.path.join(ROOT, "plugins", "vagues", "hooks", "implementeur-stop-check.py")


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state_dir = os.path.join(self.tmp.name, "etat")
        os.mkdir(self.state_dir)
        origin = os.path.join(self.tmp.name, "origin.git")
        git(self.tmp.name, "init", "-q", "--bare", "-b", "main", origin)
        self.project = os.path.join(self.tmp.name, "projet")
        git(self.tmp.name, "clone", "-q", origin, self.project)
        for args in (("config", "user.email", "t@example.com"), ("config", "user.name", "Test"),
                     ("switch", "-q", "-c", "main")):
            git(self.project, *args)
        self.commit("README.md", "x\n")
        git(self.project, "push", "-q", "origin", "main")
        git(self.project, "switch", "-q", "-c", "12-truc")
        self.agent_id = "agent-test"

    def commit(self, rel, content):
        with open(os.path.join(self.project, rel), "w") as f:
            f.write(content)
        git(self.project, "add", rel)
        git(self.project, "commit", "-q", "-m", f"ajout {rel}")

    def push(self):
        git(self.project, "push", "-q", "-u", "origin", "HEAD")

    def run_hook(self, mode=None, agent_type="implementeur", verif="true", extra_env=None, cwd=None):
        event = {"session_id": "s", "agent_id": self.agent_id, "cwd": cwd or self.project}
        if agent_type is not None:
            event["agent_type"] = agent_type
        env = dict(os.environ, CLAUDE_PROJECT_DIR=self.project, TMPDIR=self.state_dir)
        env.pop("HOOKS_QUALITE_DESACTIVES", None)
        env.pop("VERIFICATION_IMPLEMENTEUR", None)
        if verif is not None:
            env["VERIFICATION_IMPLEMENTEUR"] = verif
        env.update(extra_env or {})
        cmd = [sys.executable, HOOK] + ([mode] if mode else [])
        proc = subprocess.run(cmd, input=json.dumps(event), capture_output=True, text=True, env=env)
        return proc.returncode, proc.stdout, proc.stderr

    def assert_blocked(self, mode, *needles, **kw):
        code, out, err = self.run_hook(mode, **kw)
        if mode == "handback":
            self.assertEqual(code, 2, out + err)
            reason = err
        else:
            self.assertEqual(code, 0, err)
            decision = json.loads(out)
            self.assertEqual(decision["decision"], "block")
            reason = decision["reason"]
        for needle in needles:
            self.assertIn(needle, reason)
        return reason

    def assert_passes(self, mode, **kw):
        code, out, err = self.run_hook(mode, **kw)
        self.assertEqual((code, out), (0, ""), err)
        return err

    def travail_fini(self):
        self.commit("a.txt", "a\n")
        self.push()


class Filtrage(Base):
    def test_autres_agents_ignores(self):
        for agent in ("gab", "jf", "reviseur", "implementeur-bis", ""):
            with self.subTest(agent=agent):
                self.assertEqual(self.run_hook("start", agent_type=agent)[0], 0)
                self.assert_passes("handback", agent_type=agent, verif="false")
                self.assert_passes(None, agent_type=agent, verif="false")

    def test_sans_agent_type_ignore(self):
        self.run_hook("start")
        self.assert_passes("handback", agent_type=None, verif="false")

    def test_sans_instantane_rien(self):
        self.assert_passes("handback", verif="false")
        self.assert_passes(None, verif="false")

    def test_prefixe_de_plugin(self):
        self.run_hook("start", agent_type="vagues:implementeur")
        self.assert_blocked("handback", "vérification", agent_type="vagues:implementeur", verif="false")


class Controles(Base):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.run_hook("start")[0], 0)

    def test_tout_est_bon(self):
        self.travail_fini()
        self.assert_passes("handback")
        self.assert_passes(None)

    def test_verification_en_echec(self):
        self.travail_fini()
        reason = self.assert_blocked("handback", "vérification", verif="echo 'erreur de lint ici' >&2; exit 1")
        self.assertIn("erreur de lint ici", reason)
        self.assert_blocked(None, "vérification", verif="false")

    def test_modifications_non_commitees(self):
        self.travail_fini()
        with open(os.path.join(self.project, "a.txt"), "w") as f:
            f.write("modifié\n")
        with open(os.path.join(self.project, "nouveau.txt"), "w") as f:
            f.write("n\n")
        self.assert_blocked("handback", "a.txt", "nouveau.txt")

    def test_sur_main(self):
        git(self.project, "switch", "-q", "main")
        self.assert_blocked("handback", "main")

    def test_branche_non_poussee(self):
        self.commit("a.txt", "a\n")
        self.assert_blocked("handback", "poussée")

    def test_commit_non_pousse(self):
        self.travail_fini()
        self.commit("b.txt", "b\n")
        self.assert_blocked("handback", "poussée")

    def test_tete_detachee(self):
        self.travail_fini()
        git(self.project, "switch", "-q", "--detach")
        self.assert_blocked("handback", "branche")


class AvantLeDepart(Base):
    def test_modification_anterieure_au_depart_ignoree(self):
        with open(os.path.join(self.project, "brouillon.txt"), "w") as f:
            f.write("déjà là\n")
        self.run_hook("start")
        self.travail_fini()
        self.assert_passes("handback")


class Abandon(Base):
    def test_quatrieme_blocage_laisse_finir(self):
        self.run_hook("start")
        self.travail_fini()
        for _ in range(3):
            self.assert_blocked("handback", "vérification", verif="false")
        code, out, err = self.run_hook("handback", verif="false")
        self.assertEqual((code, out), (0, ""))
        self.assertIn("partiel", err)
        self.assertIn("bloqué", err)
        self.assertIn("réussi", err)
        # l'instantané est effacé : un nouvel arrêt ne contrôle plus rien
        self.assert_passes(None, verif="false")

    def test_blocages_partages_entre_remise_et_arret(self):
        self.run_hook("start")
        self.travail_fini()
        self.assert_blocked("handback", verif="false")
        self.assert_blocked(None, verif="false")
        self.assert_blocked("handback", verif="false")
        self.assertIn("partiel", self.run_hook(None, verif="false")[2])

    def test_succes_efface_l_instantane(self):
        self.run_hook("start")
        self.travail_fini()
        self.assert_passes("handback")
        self.assert_passes(None, verif="false")  # plus d'instantané : rien à contrôler


class Configuration(Base):
    def setUp(self):
        super().setUp()
        self.run_hook("start")
        self.travail_fini()

    def write_config(self, content):
        os.makedirs(os.path.join(self.project, ".claude"), exist_ok=True)
        with open(os.path.join(self.project, ".claude", "verification-implementeur"), "w") as f:
            f.write(content)
        git(self.project, "add", ".claude")
        git(self.project, "commit", "-q", "-m", "config")
        self.push()

    def test_commande_lue_dans_le_fichier_du_projet(self):
        self.write_config("# commentaire\n\nexit 3\n")
        self.assert_blocked("handback", "exit 3", verif=None)

    def test_variable_prioritaire_sur_le_fichier(self):
        self.write_config("exit 3\n")
        self.assert_passes("handback", verif="true")

    def test_sans_commande_configuree_bloque(self):
        # Plus de commande par défaut propre à un projet (npm) : sans réglage dans le projet,
        # le contrôle bloque et dit où configurer la commande (échec fermé).
        code, _, err = self.run_hook("handback", verif=None)
        self.assertEqual(code, 2)
        self.assertIn(".claude/verification-implementeur", err)
        self.assertNotIn("npm", err)

    def test_fichier_sans_ligne_utile_bloque(self):
        self.write_config("# seulement un commentaire\n\n")
        code, _, err = self.run_hook("handback", verif=None)
        self.assertEqual(code, 2)
        self.assertIn(".claude/verification-implementeur", err)

    def test_desactivation(self):
        for value in ("implementeur-stop-check", "tous"):
            with self.subTest(value=value):
                self.assert_passes("handback", verif="false", extra_env={"HOOKS_QUALITE_DESACTIVES": value})


class Worktree(Base):
    """L'implémenteur tourne dans son worktree (isolation: "worktree") ; CLAUDE_PROJECT_DIR
    reste la copie principale, sur main et sale : c'est le worktree qui est contrôlé."""

    def setUp(self):
        super().setUp()
        git(self.project, "switch", "-q", "main")
        self.wt = os.path.join(self.tmp.name, "wt")
        git(self.project, "worktree", "add", "-q", "-b", "34-autre", self.wt, "main")
        with open(os.path.join(self.project, "sale.txt"), "w") as f:
            f.write("copie principale\n")

    def test_worktree_pret_passe(self):
        self.run_hook("start", cwd=self.wt)
        with open(os.path.join(self.wt, "b.txt"), "w") as f:
            f.write("b\n")
        git(self.wt, "add", "b.txt")
        git(self.wt, "commit", "-q", "-m", "b")
        git(self.wt, "push", "-q", "-u", "origin", "HEAD")
        self.assert_passes(None, cwd=self.wt)

    def test_worktree_non_pousse_bloque(self):
        self.run_hook("start", cwd=self.wt)
        reason = self.assert_blocked(None, "34-autre", "pas poussée", cwd=self.wt)
        self.assertNotIn("sale.txt", reason)

    def test_sous_dossier_du_worktree(self):
        sub = os.path.join(self.wt, "sous")
        os.mkdir(sub)
        self.run_hook("start", cwd=sub)
        with open(os.path.join(sub, "c.txt"), "w") as f:
            f.write("c\n")
        self.assert_blocked(None, "sous/c.txt", cwd=sub)


if __name__ == "__main__":
    unittest.main()
