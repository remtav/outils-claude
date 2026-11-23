"""Structure du marketplace et du plugin kalmia, sans Claude Code.

Lancer : python3 -m unittest discover -s tests/plugin -v
Vérifie les manifestes, les chemins de hooks.json et des fichiers Markdown, les noms
préfixés des sous-agents, et qu'aucune donnée propre à un projet n'est dans le plugin.
"""
import glob
import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PLUGIN = os.path.join(ROOT, "plugins", "kalmia")


def load(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return json.load(f)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def frontmatter(path):
    text = read(path)
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not m:
        raise AssertionError(f"pas d'en-tête YAML : {path}")
    return m.group(1)


def plugin_files(*patterns):
    files = []
    for pattern in patterns:
        files += glob.glob(os.path.join(PLUGIN, pattern), recursive=True)
    return sorted(f for f in files if os.path.isfile(f) and "__pycache__" not in f)


class Manifestes(unittest.TestCase):
    def test_marketplace(self):
        market = load(ROOT, ".claude-plugin", "marketplace.json")
        self.assertEqual(market["name"], "outils-claude")
        self.assertTrue(market["owner"]["name"])
        entries = {p["name"]: p for p in market["plugins"]}
        self.assertEqual(entries["kalmia"]["source"], "./plugins/kalmia")
        self.assertTrue(os.path.isdir(os.path.join(ROOT, entries["kalmia"]["source"])))

    def test_plugin(self):
        plugin = load(PLUGIN, ".claude-plugin", "plugin.json")
        self.assertEqual(plugin["name"], "kalmia")
        self.assertTrue(plugin["description"])
        self.assertTrue(plugin["author"]["name"])
        # Seul plugin.json se trouve dans .claude-plugin/ ; le reste est à la racine du plugin.
        self.assertEqual(os.listdir(os.path.join(PLUGIN, ".claude-plugin")), ["plugin.json"])

    def test_version_a_un_seul_endroit(self):
        market = load(ROOT, ".claude-plugin", "marketplace.json")
        plugin = load(PLUGIN, ".claude-plugin", "plugin.json")
        entry = next(p for p in market["plugins"] if p["name"] == "kalmia")
        self.assertFalse("version" in plugin and "version" in entry, "version dans les deux manifestes")


class Hooks(unittest.TestCase):
    def setUp(self):
        self.hooks = load(PLUGIN, "hooks", "hooks.json")["hooks"]

    def commands(self):
        for event, entries in self.hooks.items():
            for entry in entries:
                for hook in entry["hooks"]:
                    yield event, entry.get("matcher", ""), hook["command"]

    def test_scripts_existent_dans_le_plugin(self):
        for _, _, command in self.commands():
            m = re.search(r'"\$\{CLAUDE_PLUGIN_ROOT\}/([^"]+)"', command)
            self.assertIsNotNone(m, command)
            self.assertTrue(command.startswith("python3 "), command)
            self.assertTrue(os.path.isfile(os.path.join(PLUGIN, m.group(1))), command)
            self.assertNotIn("CLAUDE_PROJECT_DIR", command)

    def test_matcher_implementeur(self):
        for event in ("SubagentStart", "SubagentStop"):
            for entry in self.hooks[event]:
                for name in ("implementeur", "kalmia:implementeur"):
                    self.assertTrue(re.search(entry["matcher"], name), (event, name))
                for name in ("gab", "reviseur", "kalmia:reviseur", "autre:implementeur", "implementeur2"):
                    self.assertFalse(re.search(entry["matcher"], name), (event, name))

    def test_evenements_connus(self):
        self.assertEqual(set(self.hooks), {"PreToolUse", "SubagentStart", "SubagentStop"})

    def test_pas_de_lint_dans_le_plugin(self):
        # lint-fichier.py reste dans chaque projet : pas de double exécution possible.
        self.assertNotIn("PostToolUse", self.hooks)
        self.assertFalse(os.path.exists(os.path.join(PLUGIN, "hooks", "lint-fichier.py")))


class Composants(unittest.TestCase):
    def test_agents_sans_champs_ignores(self):
        # Ignorés pour un agent de plugin (doc des sous-agents) : les gardes sont dans hooks.json.
        for path in plugin_files("agents/*.md"):
            head = frontmatter(path)
            name = os.path.basename(path)[:-3]
            self.assertIn(f"name: {name}\n", head + "\n", path)
            for field in ("hooks:", "mcpServers:", "permissionMode:"):
                self.assertNotIn(field, head, path)

    def test_commandes_ont_une_description(self):
        names = [os.path.basename(p)[:-3] for p in plugin_files("commands/*.md")]
        self.assertEqual(sorted(names), ["installer-vagues", "planifier", "preparer-issue", "release", "vague"])
        for path in plugin_files("commands/*.md"):
            self.assertRegex(frontmatter(path), r"(?m)^description: \S", path)

    def test_sous_agents_prefixes(self):
        agents = {os.path.basename(p)[:-3] for p in plugin_files("agents/*.md")}
        for path in plugin_files("commands/*.md"):
            for value in re.findall(r'subagent_type: "([^"]+)"', read(path)):
                self.assertTrue(value.startswith("kalmia:"), (path, value))
                self.assertIn(value.removeprefix("kalmia:"), agents, (path, value))

    def test_chemins_du_plugin_existent(self):
        for path in plugin_files("**/*.md"):
            for rel in re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/([\w./-]+[\w-])", read(path)):
                if rel.endswith("/"):
                    continue
                target = os.path.join(PLUGIN, rel)
                self.assertTrue(os.path.exists(target) or os.path.isdir(os.path.dirname(target)), (path, rel))

    def test_modeles_de_l_installateur(self):
        text = read(os.path.join(PLUGIN, "commands", "installer-vagues.md"))
        for model in ("tache.md", "journal-vagues.md", "verification-implementeur", "tests-complets",
                      "regles-planification.md"):
            self.assertIn(f"`{model}`" if model != "regles-planification.md" else model, text)
            self.assertTrue(os.path.isfile(os.path.join(PLUGIN, "modeles", model)), model)


class PreparerIssue(unittest.TestCase):
    """Étape « préparer (Opus) → vague (Sonnet) » : commande, modèle d'issue enrichi, garde-fou de /vague."""

    SECTIONS = ["Plan d'implémentation", "Tests à écrire d'abord", "Commandes de vérification",
                "Hors portée et pièges", "Exemples à imiter", "Questions ouvertes"]

    def test_commande_sur_opus(self):
        path = os.path.join(PLUGIN, "commands", "preparer-issue.md")
        self.assertTrue(os.path.isfile(path))
        self.assertRegex(frontmatter(path), r"(?m)^model: opus$")

    def test_planifier_sur_opus_sans_mention_de_fable(self):
        path = os.path.join(PLUGIN, "commands", "planifier.md")
        self.assertRegex(frontmatter(path), r"(?m)^model: opus$")
        self.assertIn("Prévue pour Opus.", read(path))
        self.assertNotRegex(read(path), r"(?i)fable")

    def test_release_sur_opus_sans_mention_de_fable(self):
        path = os.path.join(PLUGIN, "commands", "release.md")
        self.assertRegex(frontmatter(path), r"(?m)^model: opus$")
        self.assertNotRegex(read(path), r"(?i)fable")

    def test_planifier_borne_le_budget_a_50(self):
        text = read(os.path.join(PLUGIN, "commands", "planifier.md"))
        self.assertIn("**4 à 50 points**", text)

    def test_modele_a_les_six_sections_dans_l_ordre(self):
        text = read(os.path.join(PLUGIN, "modeles", "tache.md"))
        titres = re.findall(r"(?m)^## (.+)$", text)
        self.assertEqual(titres, ["Contexte", "Fichiers probablement touchés", "Critères d'acceptation",
                                  "Taille", "Dépendances"] + self.SECTIONS)

    def test_chaque_nouvelle_section_a_un_commentaire(self):
        text = read(os.path.join(PLUGIN, "modeles", "tache.md"))
        for section in self.SECTIONS:
            corps = text.split(f"## {section}\n", 1)[1].split("\n## ", 1)[0]
            self.assertIn("<!--", corps, section)
            self.assertIn("implémenteur", corps, section)

    def test_vague_saute_les_issues_sans_etiquette_prete(self):
        text = read(os.path.join(PLUGIN, "commands", "vague.md"))
        self.assertIn("`prête`", text)
        self.assertIn("non préparée (lancer /kalmia:preparer-issue #", text)

    def test_planifier_et_release_utilisent_le_modele_enrichi(self):
        for name in ("planifier", "release"):
            text = read(os.path.join(PLUGIN, "commands", f"{name}.md"))
            for section in self.SECTIONS:
                self.assertIn(section, text, name)
            self.assertIn("`prête`", text, name)
            self.assertIn("`à-préciser`", text, name)

    def test_preparer_issue_ne_pose_pas_vague_n(self):
        text = read(os.path.join(PLUGIN, "commands", "preparer-issue.md"))
        for mot in ("`prête`", "`à-préciser`", "brouillon", "#N", "Demande d'origine"):
            self.assertIn(mot, text)
        self.assertRegex(text, r"[Jj]amais .*`vague-N`")

    def test_implementeur_suit_le_plan(self):
        text = read(os.path.join(PLUGIN, "agents", "implementeur.md"))
        self.assertIn("Plan d'implémentation", text)
        self.assertIn("Commandes de vérification", text)
        self.assertRegex(frontmatter(os.path.join(PLUGIN, "agents", "implementeur.md")), r"(?m)^model: sonnet$")


class AucuneDonneeDeProjet(unittest.TestCase):
    """Rien de propre à un projet (remtav/template ou autre) dans le plugin."""

    INTERDITS = [
        r"\bnpm\b", r"\beslint\b", r"espace-interne", r"Rémi",
        r"\.claude/hooks/", r"\.claude/scripts/", r"\.claude/agents/", r"\.claude/commands/",
        r"reviewer\.md", r"agents? (jf|gab|azan|habib|laurence|hibou)\b", r"templates/projet",
    ]

    def test_pas_de_reference_propre_au_projet(self):
        # installer-vagues.md cite npm, pytest, cargo… comme exemples de déduction : exclu.
        files = [f for f in plugin_files("**/*") if not f.endswith("installer-vagues.md")]
        for path in files:
            text = read(path)
            for pattern in self.INTERDITS:
                self.assertIsNone(re.search(pattern, text), (os.path.relpath(path, ROOT), pattern))

    def test_journal_modele_sans_vague(self):
        text = read(os.path.join(PLUGIN, "modeles", "journal-vagues.md"))
        self.assertRegex(text, r"(?m)^budget: 10$")
        self.assertRegex(text, r"(?m)^estimations: aucune$")
        events = text.split("## Événements", 1)[1]
        self.assertEqual(events.strip(), "")

    def test_commandes_de_verification_a_remplir(self):
        for model, key in (("verification-implementeur", "{{VERIFICATION}}"), ("tests-complets", "{{TESTS_COMPLETS}}")):
            lines = [l for l in read(os.path.join(PLUGIN, "modeles", model)).splitlines()
                     if l.strip() and not l.startswith("#")]
            self.assertEqual(lines, [key], model)

    def test_pas_de_fichier_de_projet(self):
        for name in ("journal-vagues.md", "verification-implementeur", "tests-complets", "settings.json", "CLAUDE.md"):
            found = [f for f in plugin_files(f"**/{name}") if "/modeles/" not in f]
            self.assertEqual(found, [], name)


if __name__ == "__main__":
    unittest.main()


class AccesWeb(unittest.TestCase):
    def outils(self, agent):
        with open(os.path.join(PLUGIN, "agents", agent + ".md"), encoding="utf-8") as f:
            ligne = next(l for l in f if l.startswith("tools:"))
        return [t.strip() for t in ligne[len("tools:"):].split(",")]

    def test_implementeur_a_websearch_et_webfetch(self):
        outils = self.outils("implementeur")
        self.assertIn("WebSearch", outils)
        self.assertIn("WebFetch", outils)

    def test_reviseur_a_webfetch_sans_ecriture(self):
        outils = self.outils("reviseur")
        self.assertIn("WebFetch", outils)
        for interdit in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
            self.assertNotIn(interdit, outils)
