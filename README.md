# outils-claude

Dépôt de référence des outils Claude Code de remtav. C'est un **marketplace** de plugins Claude Code (nom : `outils-claude`). Il contient pour l'instant un plugin : **`vagues`**.

**Nouveau au workflow ?** Le [guide du workflow des vagues](docs/guide-vagues.html) (une page HTML, lisible sur téléphone) explique le cycle, qui fait quoi, les garde-fous et le dépannage. Ce README reste la référence d'installation.

## Plugin `vagues`

La mécanique des vagues pour développer un projet avec Claude Code, y compris sur le web ou depuis un téléphone :

- **issues** : unités de travail implémentables seules, taillées 1, 2 ou 4 points (étiquettes `taille-1|2|4`) ;
- **vagues** : groupes d'issues indépendantes (étiquette `vague-N`), lancées d'un coup par `/vagues:vague N` ;
- **releases** : plusieurs vagues, closes par `/vagues:release` (tests, audit, nettoyage, notes, tag).

L'orchestrateur reste léger en contexte : il délègue chaque issue à un sous-agent `implementeur` et chaque PR à un sous-agent `reviseur`, qui répondent en une ligne. Un journal permet de reprendre une vague coupée et de calibrer le budget de points.

### Installer dans un projet

1. Ajouter au fichier `.claude/settings.json` du projet (le créer s'il n'existe pas ; s'il existe, **fusionner** ces clés avec les siennes) :

   ```json
   {
     "extraKnownMarketplaces": {
       "outils-claude": {
         "source": { "source": "github", "repo": "remtav/outils-claude" },
         "autoUpdate": true
       }
     },
     "enabledPlugins": {
       "vagues@outils-claude": true
     }
   }
   ```

   `autoUpdate: true` est nécessaire pour recevoir les modifications du plugin : la mise à jour automatique est désactivée par défaut pour les marketplaces autres que ceux d'Anthropic (voir « Mises à jour »).

2. Ouvrir une **nouvelle session** sur le projet, accepter le marketplace et le plugin si Claude Code le demande, puis lancer :

   ```
   /vagues:installer-vagues
   ```

   ou `/vagues:installer-vagues "<commande de vérification>"` pour imposer la commande de vérification rapide. La commande demande l'autorisation d'écrire dans `.claude/` (dossier protégé par Claude Code). Elle n'écrase aucun fichier existant et peut être relancée.

3. Relire et commiter les fichiers créés, puis `/vagues:planifier` et `/vagues:vague 1`.

Hors des sessions cloud, on peut aussi installer à la main : `/plugin marketplace add remtav/outils-claude` puis `/plugin install vagues@outils-claude`.

### Commandes

Les composants d'un plugin portent le préfixe du plugin. **Forme documentée et vérifiée : `/vagues:<commande>`.** Le nom seul (`/vague`) n'est pas documenté par Claude Code : ne pas s'y fier.

| Commande | Rôle |
|---|---|
| `/vagues:installer-vagues [commande]` | Prépare le projet : modèle d'issue, journal, section « Règles de planification » dans `CLAUDE.md`, commandes de vérification, étiquettes `taille-*`. |
| `/vagues:planifier [K] [lecture-seule]` | Lit le journal, ajuste budget et estimations, redécoupe les issues bloquées, forme les `K` prochaines vagues (2 par défaut). Prévue pour le modèle Fable. |
| `/vagues:vague <N \| vague-N \| reprise>` | Orchestre une vague : un `implementeur` par issue (3 au plus en parallèle), un `reviseur` par PR, fusion seulement si CI réussie **et** réviseur `approuvé`. Écrit le journal. |
| `/vagues:release <tag> <N…> [depuis=…]` | Clôt une release : vagues fusionnées, suite complète, audit, PR de nettoyage, issues de consolidation, notes, tag seulement si tout est vert. |

### Agents

Les commandes les lancent sous leur nom de plugin (`subagent_type: "vagues:implementeur"`, etc.). Ils ne sont pas faits pour un usage interactif.

| Agent | Modèle | Rôle |
|---|---|---|
| `vagues:implementeur` | Sonnet | Reçoit un numéro d'issue : branche, code, tests, push, PR ; répond en une ligne. Ne fusionne ni n'approuve. |
| `vagues:reviseur` | Sonnet | Reçoit une PR et son issue : vérifie les critères contre le diff, poste un commentaire avec le marqueur `<!-- verdict-reviseur: approuvé\|refusé sha=… -->` ; lecture seule. |
| `vagues:release-mecanique` | Sonnet | Tâches mécaniques de `/vagues:release` (tests, notes, tag) par `scripts/release.py`. |

### Hooks

Déclarés dans `plugins/vagues/hooks/hooks.json`, donc actifs dès que le plugin est activé : un projet ne peut pas avoir les agents sans leurs garde-fous. (Les agents d'un plugin ignorent le champ `hooks` de leur en-tête : les gardes ne peuvent pas y être.) Les hooks du plugin s'ajoutent à ceux du projet.

| Script | Événement | Rôle | En cas d'erreur |
|---|---|---|---|
| `garde-agents-vague.py` | PreToolUse (Bash, écritures de fichiers, outils MCP GitHub de fusion, d'approbation et d'écriture) | Pour `implementeur` et `reviseur` (avec ou sans préfixe `vagues:`) : pas de fusion, d'approbation, de push sur `main`/`master`, de push forcé ni d'écriture MCP sur `main` ; `reviseur` ne commite, ne pousse ni n'écrit rien. Les autres agents et la session principale passent. | bloque (échec fermé) |
| `garde-fusion.py` | PreToolUse (Bash, MCP de fusion) | Pour **tous**, session principale comprise : avant une fusion de PR, exige une CI présente et réussie sur le SHA de tête **et** le marqueur `approuvé` du réviseur pour ce SHA. Lit GitHub par `gh api` (REST). | bloque (échec fermé) |
| `implementeur-stop-check.py` | SubagentStart, SubagentStop, PreToolUse `SubagentHandback` | L'implémenteur ne termine pas tant que la commande de vérification du projet échoue, qu'il reste des modifications non commitées, ou que sa branche est `main` ou pas poussée. Abandon après 3 blocages (réponse `partiel` ou `bloqué`). | laisse finir après 3 blocages |

Prérequis : **Python 3** (présent dans les sessions cloud), `git`, et `gh` authentifié pour le garde de fusion (dans les sessions cloud, le proxy authentifie `gh api`).

**Désactiver temporairement** un hook de qualité : variable d'environnement `HOOKS_QUALITE_DESACTIVES` (noms séparés par des virgules : `implementeur-stop-check`, `garde-fusion`, ou `tous`). Dans une session cloud : variable de l'environnement. `garde-agents-vague.py` ne se désactive pas.

**Pas de lint dans le plugin** : le lint immédiat d'un fichier modifié dépend des outils de chaque projet (eslint, ruff…). Il reste un hook du projet (ex. `lint-fichier.py` dans `remtav/template`), ce qui évite aussi une double exécution.

### Ce qui reste propre à chaque projet

Le plugin ne contient **aucune donnée de projet**. Commandes et hooks lisent et écrivent dans le projet (`$CLAUDE_PROJECT_DIR`, racine du dépôt), jamais dans le plugin :

| Fichier du projet | Contenu | Lu par |
|---|---|---|
| `.claude/journal-vagues.md` | journal, `budget:` (10 au départ) et `estimations:` | `/vagues:vague`, `/vagues:planifier` |
| `CLAUDE.md`, section « Règles de planification » (ou « Planification ») | règles, budget de départ, commandes de vérification | `/vagues:planifier`, agents |
| `.claude/verification-implementeur` | commande de vérification rapide (1ʳᵉ ligne utile) ; variable `VERIFICATION_IMPLEMENTEUR` prioritaire | contrôle de fin de l'implémenteur |
| `.claude/tests-complets` | suite de tests complète (1ʳᵉ ligne utile) ; variable `RELEASE_TEST_CMD` prioritaire | `/vagues:release` (`release.py tests` et `tag`) |
| `.github/ISSUE_TEMPLATE/tache.md` | modèle d'issue | `/vagues:planifier`, `/vagues:release` |
| hooks propres (lint, gardes d'autres agents) | `.claude/settings.json` du projet | Claude Code |

Sans commande de vérification ni suite complète configurée, les gardes refusent plutôt que de deviner : le contrôle de fin bloque et dit où la configurer, `release.py` s'arrête sans tag.

### Reprise planifiée d'une vague coupée

Étape manuelle, une fois par projet : une **tâche planifiée** Claude Code sur le dépôt, qui démarre une nouvelle session (par ex. toutes les 3 heures, `0 */3 * * *` UTC), avec le prompt :

```
/vagues:vague reprise
```

Sans vague coupée, la commande répond `Rien à reprendre` et s'arrête aussitôt, presque sans coût.

### Mises à jour

**Choix : pas de `version` dans `plugin.json`.** Claude Code prend alors le SHA du commit comme version : chaque commit poussé sur `main` de ce dépôt est une nouvelle version, sans rien incrémenter. Avec une `version` figée, les projets resteraient sur elle tant qu'on ne l'incrémente pas.

Côté projet, `autoUpdate: true` (bloc d'installation ci-dessus) fait rafraîchir le marketplace : dans une session interactive, après le premier message, Claude Code attend un délai aléatoire (dix minutes au plus) puis met à jour les plugins sur le disque ; la modification est active à la session suivante. Pour l'avoir tout de suite : `/plugin marketplace update outils-claude`, puis `/reload-skills` ou une nouvelle session.

### Trois points connus des sessions cloud (Claude Code sur le web)

1. **Accès réseau à GitHub** : l'environnement de la session doit pouvoir joindre GitHub pour récupérer le marketplace (dépôt public `remtav/outils-claude`). Sinon, le plugin n'est pas chargé : ni commandes `/vagues:*`, ni agents, ni garde-fous.
2. **Plugin pas encore actif dans la première session** : un plugin récemment ajouté peut ne pas être chargé tout de suite. Essayer `/reload-skills`, ou ouvrir une nouvelle session. Le marketplace déclaré dans `.claude/settings.json` ne s'applique qu'une fois le dossier du projet approuvé (« trust »).
3. **Pas d'installation automatique au démarrage** : en session cloud, Claude Code n'installe pas tout seul un marketplace et un plugin déclarés dans le `.claude/settings.json` du projet (pas d'invite de confiance dans ces sessions). Ce qui fonctionne : installer à la main, ou mettre ces commandes dans le **script d'installation de l'environnement** :

   ```
   claude plugin marketplace add remtav/outils-claude
   claude plugin install vagues@outils-claude --scope project
   git checkout -- .claude/settings.json
   ```

   (le `git checkout` remet `.claude/settings.json` tel quel : l'installation le réordonne). `claude plugin list` doit alors afficher `vagues@outils-claude` à l'état `enabled`. GitHub reste joignable ; seule l'installation au démarrage manque.

## Développer ce dépôt

```
plugins/vagues/
├── .claude-plugin/plugin.json
├── agents/        implementeur.md, reviseur.md, release-mecanique.md
├── commands/      vague.md, planifier.md, release.md, installer-vagues.md
├── hooks/         hooks.json, garde-agents-vague.py, garde-fusion.py, implementeur-stop-check.py, etat_arbre.py
├── scripts/       release.py
└── modeles/       tache.md, journal-vagues.md, regles-planification.md, verification-implementeur, tests-complets
```

Tests (Python 3, sans dépendance ; aucun appel réseau, dépôts git jetables) :

```
python3 -m unittest discover -s tests/hooks
python3 -m unittest discover -s tests/release
python3 -m unittest discover -s tests/plugin
claude plugin validate .
```

Essai local sans installer : `claude --plugin-dir plugins/vagues`.
