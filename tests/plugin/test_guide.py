"""Garde-fous du guide HTML (docs/guide-vagues.html), sans navigateur.

Lancer : python3 -m unittest discover -s tests/plugin -v
Vérifie : HTML bien formé, sept sections, trois étapes dans « Installer dans un nouveau projet »,
aucune ressource externe, et que chaque commande /kalmia:… et chaque agent kalmia:… cités existent.
"""
import os
import re
import unittest
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GUIDE = os.path.join(ROOT, "docs", "guide-vagues.html")
PLUGIN = os.path.join(ROOT, "plugins", "kalmia")
VOID = {"meta", "br", "img", "link", "hr", "input"}


class Arbre(HTMLParser):
    def __init__(self):
        super().__init__()
        self.pile, self.erreurs, self.balises = [], [], []
        self.h2, self.etapes_installer = 0, 0
        self.section = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.balises.append((tag, attrs))
        if tag == "section":
            self.section = attrs.get("id")
        if tag == "h2":
            self.h2 += 1
        if tag == "li" and self.section == "installer" and "etapes" in [
                c for t, a in [self.pile[-1]] if t == "ol" for c in a.get("class", "").split()]:
            self.etapes_installer += 1
        if tag not in VOID:
            self.pile.append((tag, attrs))

    def handle_endtag(self, tag):
        if not self.pile or self.pile[-1][0] != tag:
            self.erreurs.append((tag, self.getpos()))
        else:
            self.pile.pop()
        if tag == "section":
            self.section = None


def lire():
    with open(GUIDE, encoding="utf-8") as f:
        return f.read()


class Guide(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.texte = lire()
        cls.arbre = Arbre()
        cls.arbre.feed(cls.texte)

    def test_html_bien_forme(self):
        self.assertEqual(self.arbre.erreurs, [])
        self.assertEqual(self.arbre.pile, [])

    def test_sept_sections(self):
        self.assertEqual(self.arbre.h2, 7)

    def test_installer_a_trois_etapes(self):
        self.assertEqual(self.arbre.etapes_installer, 3)

    def test_aucune_ressource_externe(self):
        for tag, attrs in self.arbre.balises:
            self.assertNotIn(tag, ("script", "iframe", "img", "object", "embed"))
            if tag == "link":
                self.fail("balise <link> inattendue")
            for nom in ("src", "href"):
                self.assertFalse(re.match(r"(https?:)?//", attrs.get(nom, "")), attrs)
        self.assertNotIn("@import", self.texte)
        self.assertNotIn("url(", self.texte)

    def test_guide_decrit_preparer_puis_vague(self):
        self.assertIn("/kalmia:preparer-issue", self.texte)
        for mot in ("Opus", "Sonnet", "<code>prête</code>", "<code>à-préciser</code>"):
            self.assertIn(mot, self.texte)

    def test_commandes_et_agents_existent(self):
        commandes = {f[:-3] for f in os.listdir(os.path.join(PLUGIN, "commands")) if f.endswith(".md")}
        agents = {f[:-3] for f in os.listdir(os.path.join(PLUGIN, "agents")) if f.endswith(".md")}
        cites_c = set(re.findall(r"/kalmia:([a-z-]+)", self.texte))
        self.assertTrue(cites_c)
        self.assertLessEqual(cites_c - commandes, set())
        for nom in re.findall(r"<code>kalmia:([a-z-]+)</code>", self.texte):
            if nom not in commandes:
                self.assertIn(nom, agents)


if __name__ == "__main__":
    unittest.main()
