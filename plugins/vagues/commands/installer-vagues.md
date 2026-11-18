---
description: Prépare le projet courant pour la mécanique des vagues (plugin vagues) - modèle d'issue, journal, règles de planification dans CLAUDE.md, commandes de vérification, étiquettes taille-*, prête et à-préciser. Idempotent - n'écrase jamais un fichier existant. Argument facultatif - la commande de vérification rapide.
argument-hint: "[commande de vérification]"
---

Tu prépares le **projet courant** (racine du dépôt git, `git rev-parse --show-toplevel`) pour les vagues. Argument : `$ARGUMENTS`.

Les modèles sont dans le plugin, en lecture seule : `${CLAUDE_PLUGIN_ROOT}/modeles/`. Tu écris **seulement dans le projet**, jamais dans le plugin. Tu n'écrases et ne réécris **aucun fichier existant** : pour chaque fichier déjà présent, tu le laisses tel quel et tu le notes « déjà en place ». Seule exception, l'ajout d'une section à la fin de `CLAUDE.md` (étape 3), et seulement si elle n'y est pas déjà.

Ne crée ni branche, ni commit, ni PR : l'utilisateur relit et commite lui-même.

## 1. Commandes de vérification

Détermine deux commandes, dans cet ordre de priorité :

- **Vérification rapide** (lancée avant qu'un implémenteur termine ; lint + tests unitaires, pas de tests lents) :
  1. l'argument, s'il est donné ;
  2. sinon la première ligne utile d'un `.claude/verification-implementeur` existant ;
  3. sinon déduite du projet : `package.json` (scripts `lint`, `test:unit`, `test:node`, `test`, ex. `npm run lint && npm test`), `pyproject.toml` / `setup.cfg` / `pytest.ini` (`python3 -m pytest -q`), `Makefile` (cible `test` ou `check`), `Cargo.toml` (`cargo test`), `go.mod` (`go test ./...`) ;
  4. sinon, demande-la à l'utilisateur (une question, avec ta meilleure proposition). S'il n'y en a vraiment aucune, utilise `true` et signale-le dans le résumé.
- **Suite complète** (lancée par `/vagues:release` avant un tag) : la première ligne utile d'un `.claude/tests-complets` existant, sinon la suite complète déduite du projet (ex. `npm ci && npm test`), sinon la vérification rapide.

## 2. Fichiers à créer s'ils manquent

| Fichier du projet | Modèle | Remplacement |
|---|---|---|
| `.github/ISSUE_TEMPLATE/tache.md` | `tache.md` | — |
| `.claude/journal-vagues.md` | `journal-vagues.md` (réglages, format, aucune vague) | — |
| `.claude/verification-implementeur` | `verification-implementeur` | `{{VERIFICATION}}` → vérification rapide |
| `.claude/tests-complets` | `tests-complets` | `{{TESTS_COMPLETS}}` → suite complète |

Pour chacun : s'il existe, « déjà en place » ; sinon, lis le modèle (`${CLAUDE_PLUGIN_ROOT}/modeles/<modèle>`), fais le remplacement, et écris le fichier (crée les dossiers au besoin).

## 3. `CLAUDE.md`

- `CLAUDE.md` absent : crée-le avec un titre `# CLAUDE.md`, une ligne vide, puis le contenu de `${CLAUDE_PLUGIN_ROOT}/modeles/regles-planification.md` (remplacements `{{VERIFICATION}}` et `{{TESTS_COMPLETS}}` faits).
- `CLAUDE.md` présent **sans** section `## Règles de planification` ni `## Planification` : ajoute ce même contenu **à la fin**, précédé d'une ligne vide, sans toucher au reste.
- Section déjà présente : « déjà en place » ; ne la modifie pas. Si elle ne mentionne pas les commandes de vérification, signale-le dans le résumé.

## 4. Étiquettes

Crée les étiquettes `taille-1`, `taille-2`, `taille-4`, `prête` (issue préparée par `/vagues:preparer-issue`, lancée par `/vagues:vague`) et `à-préciser` (issue qui attend une décision) si elles n'existent pas (dépôt `owner/repo` d'après `git remote get-url origin`) : outils MCP GitHub s'il y en a un pour les étiquettes, sinon `gh label create taille-1 --description "1 point" --force` (de même pour 2 et 4 ; `prête` : `--description "Issue préparée, prête pour une vague"`, `à-préciser` : `--description "Décision manquante, voir Questions ouvertes"`) si `gh` est disponible et authentifié. Si aucun accès ne le permet, ne bloque pas : liste-les « à créer » dans le résumé. Dis aussi que les issues déjà ouvertes n'ont pas `prête` : elles passent par `/vagues:preparer-issue #N` avant `/vagues:vague`. Les étiquettes `vague-N` sont créées plus tard par `/vagues:planifier`.

## 5. Résumé (court)

```
Vagues installées dans <owner/repo ou dossier>
Créés : <fichiers>
Déjà en place : <fichiers>
CLAUDE.md : section ajoutée|créé|déjà en place
Vérification : <commande rapide> ; suite complète : <commande>
Étiquettes : créées|déjà là|à créer : taille-1, taille-2, taille-4, prête, à-préciser
Prochaine étape : relire et commiter ces fichiers, puis /vagues:preparer-issue #N (issues existantes), /vagues:planifier, puis /vagues:vague 1
```

Ajoute une ligne `À vérifier :` si une commande a été devinée ou vaut `true`.
