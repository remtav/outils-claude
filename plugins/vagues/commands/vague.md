---
description: Orchestre une vague d'issues (étiquette vague-N) avec les sous-agents vagues:implementeur et vagues:reviseur ; fusionne seulement si la CI a réussi et que le réviseur approuve. Argument : un numéro de vague (3 ou vague-3) ou « reprise ».
argument-hint: <N | vague-N | reprise>
---

Tu es l'**orchestrateur** de la vague demandée : `$ARGUMENTS`. Tu coordonnes, tu ne codes pas. Ton contexte doit rester léger : tu ne gardes que les **réponses d'une ligne** des sous-agents et l'état GitHub (numéros, états, vérifications). Tu ne lis **ni les diffs, ni le code, ni les fichiers modifiés** des PR.

Accès GitHub : outils MCP GitHub (`mcp__github__*`) ; `gh` en alternative s'il est disponible. Le dépôt (`owner/repo`) se lit dans `git remote get-url origin`.

## 0. Argument

- `N` ou `vague-N` (N entier) → l'étiquette traitée est `vague-N`.
- `reprise` → lis `.claude/journal-vagues.md` **tel qu'il est sur `main`** (`git fetch -q origin main && git show origin/main:.claude/journal-vagues.md` ; ou `mcp__github__get_file_contents` avec `ref: "main"` ; si les deux échouent, le fichier local). Format : section « Format » du journal. Cherche la **dernière vague non fermée** : la vague dont la dernière ligne d'état (`ouverte`, `reprise`, `coupée` ou `fermée`) n'est pas `fermée` ; s'il y en a plusieurs, celle dont la ligne d'état la plus récente est la plus bas dans le fichier.
  - **Fichier absent ou aucune vague non fermée : réponds exactement `Rien à reprendre` et arrête-toi**, sans aucun autre appel (ni GitHub, ni sous-agent, ni écriture).
  - **Vague encore active** : si la dernière ligne de cette vague (tous événements confondus) date de **moins de 90 minutes** (`date -u`), une autre session y travaille probablement : réponds `Vague N en cours (dernière ligne <heure>) : rien à reprendre` et arrête-toi, sans aucun autre appel.
  - Sinon, lis-y le numéro de vague `N` et continue avec `vague-N` : l'étape 1 la marque `coupée` puis `reprise`.
- Autre chose ou rien → réponds `Usage : /vagues:vague <N | vague-N | reprise>` et arrête-toi.

## 1. État de la vague (idempotence)

Liste les issues étiquetées `vague-N` (`mcp__github__list_issues` avec `labels: ["vague-N"]`, ouvertes **et** fermées ; ou `gh issue list --label vague-N --state all`). Pour chacune, déduis son état de GitHub seulement :

| État GitHub | Étape |
|---|---|
| issue fermée, ou PR liée fusionnée | **terminée** : sauter |
| issue ouverte, sans PR, **sans** l'étiquette `prête` | **bloquée, non préparée** : ne pas l'implémenter, aucun sous-agent (voir ci-dessous) |
| PR ouverte liée (corps contenant `Closes #<issue>`, `Fixes #<issue>` ou `Resolves #<issue>`, le numéro suivi d'une **limite de mot** : `Closes #6` ne désigne pas l'issue 69 ; motif : `(?i)\b(close[sd]?\|fix(e[sd])?\|resolve[sd]?) #<issue>\b`) | passer directement à l'étape 3 (CI + révision) |
| aucune PR | étape 2 (implémentation) |

**Garde « prête ».** Une issue ouverte de la vague **sans** l'étiquette `prête` n'est jamais confiée à l'implémenteur (une issue qui a déjà une PR ouverte suit sa ligne du tableau). Elle est **bloquée** avec la raison `non préparée (lancer /vagues:preparer-issue #N)` : écris-la au journal (ligne `issue #I | taille T | bloquée | — | non préparée (lancer /vagues:preparer-issue #I)`) et mets-la dans « Bloquées » du résumé. **Aucun sous-agent n'est lancé pour elle.** Les issues déjà ouvertes avant l'introduction de `/vagues:preparer-issue` n'ont pas `prête` : c'est voulu, elles passent d'abord par `/vagues:preparer-issue #N`. Une issue `à-préciser` est dans le même cas (ses « Questions ouvertes » attendent une décision).

Relancer `/vagues:vague N` sur une vague partiellement faite reprend donc là où elle en était, sans refaire les issues terminées.

Lis aussi la taille de chaque issue dans ses étiquettes `taille-1`, `taille-2`, `taille-4` (1, 2 ou 4 points ; sans étiquette : 0, et le signaler) : **points prévus** = somme sur toutes les issues de la vague.

Lis enfin le **budget** dans les réglages du journal (ligne `budget:`, seul endroit où il est noté). Si les points prévus le dépassent, signale-le dans le résumé final (`Prévus P > budget B`) ; ne bloque pas la vague.

**Journal** (voir « Écrire une ligne au journal » plus bas) :
1. Pour chaque vague **non fermée** du journal (définition à l'étape 0), y compris `N`, dont la dernière ligne d'état n'est pas déjà `coupée` : écris `coupée | complétés C/P`, avec `P` et `C` calculés pour cette vague-là comme ici et à l'étape 5 (issues de son étiquette `vague-M`).
2. Puis, pour `N` : `reprise | prévus P` si `N` était non fermée (cas de `/vagues:vague reprise`, ou d'un `/vagues:vague N` relancé sur une vague coupée), sinon `ouverte | prévus P`.

## 2. Implémentation

Pour chaque issue à implémenter (étiquette `prête`, sans PR), lance un sous-agent `implementeur` du plugin (outil Agent, `subagent_type: "vagues:implementeur"`, **`isolation: "worktree"`**) avec ce message, **et rien d'autre** :

```
Issue #<numéro>. Réponds en une seule ligne au format de ta définition.
```

- **Toujours `isolation: "worktree"`** : chaque implémenteur travaille dans son propre arbre git, jamais dans la copie de cette session. Sans cela, des implémenteurs lancés en parallèle partagent le même dossier et changent de branche l'un sous l'autre. Si l'outil Agent refuse l'isolation (pas de dépôt git, par ex.), lance les implémenteurs **un à la fois**.
- **Au plus 3 sous-agents `implementeur` en même temps** ; lance le suivant quand l'un répond.
- Garde seulement sa ligne de réponse (`#<issue> → <PR ou —> | réussi|bloqué|partiel | <raison>`).
- `bloqué` ou pas de PR : l'issue est **bloquée** ; passe à la suivante.

**Journal** : pour chaque issue **bloquée**, écris aussitôt `issue #I | taille T | bloquée | <PR #n ou —> | <raison de l'implementeur>`. Les issues qui ont une PR sont notées à l'étape 3 (fusion) ou 5 (restée ouverte).

## 3. CI et révision de chaque PR

Pour chaque PR (nouvelle ou déjà ouverte) :

1. **CI.** Lis l'état des vérifications du dernier commit (`mcp__github__pull_request_read` méthodes `get_check_runs` et `get_status`, ou `gh pr checks <n>`). Tant qu'une vérification est en attente : attends et relis, **espacé** (environ toutes les 2 à 5 minutes ; jamais en boucle serrée), au plus 30 minutes, puis considère-la « en attente » et passe à la suite.
   - **réussie** : toutes les vérifications terminées et vertes ;
   - **échouée** : au moins une rouge ou annulée → la PR reste ouverte ;
   - **absente** : aucune vérification configurée pour cette PR (cas fréquent : le workflow ne se déclenche que sur certains chemins). Note-le. **Règle par défaut : une PR à CI absente n'est pas fusionnée**, même si l'implémenteur rapporte ses tests locaux réussis ; elle reste ouverte avec la raison « CI absente ». Cette commande ne contient aucune règle qui autorise la fusion sans CI.
2. **Révision.** Lance un sous-agent `reviseur` du plugin (`subagent_type: "vagues:reviseur"`), **nouveau pour chaque PR**, avec ce message et rien d'autre (ni résumé de l'implémentation, ni ton avis) :

   ```
   PR #<pr>, issue #<issue>. Réponds en une seule ligne au format de ta définition.
   ```

   Garde seulement sa ligne (`PR #<n> | approuvé` ou `PR #<n> | refusé | <raison>`).
3. **Fusion — seulement si les deux conditions tiennent pour le même dernier commit : CI réussie ET réviseur `approuvé`.** Vérifie juste avant que le SHA de tête n'a pas changé depuis la révision (sinon, nouvelle révision). Fusionne alors (`mcp__github__merge_pull_request` avec `merge_method: "merge"` et `expectedHeadSha`, ou `gh pr merge <n> --merge`). Dans tous les autres cas, **ne fusionne pas** : la PR reste ouverte, avec sa raison (CI échouée, CI absente, CI en attente, refusée par le réviseur).
4. **Garde de fusion.** Le hook `garde-fusion.py` du plugin revérifie au moment de la fusion : CI réussie sur le SHA de tête **et** commentaire du réviseur avec le marqueur `<!-- verdict-reviseur: approuvé sha=<sha de tête> -->`. S'il refuse la fusion (outil bloqué avec un message « Bloqué par le garde de fusion »), **ne réessaie pas** et ne contourne pas (autre outil, `gh api`, autre méthode de fusion) : la PR reste ouverte, avec la raison `refusée par le garde de fusion : <raison>`.

Seule cette session principale fusionne : le garde `garde-agents-vague.py` du plugin bloque la fusion et l'approbation pour `implementeur` et `reviseur`.

**Journal** : après chaque fusion, écris aussitôt `issue #I | taille T | fusionnée | PR #n`. Une PR laissée ouverte est notée à l'étape 5 seulement (l'étape 4 peut encore la faire fusionner).

## 4. Après chaque fusion

Les autres PR ouvertes de la vague peuvent maintenant être en conflit avec `main`. Pour chacune : tente une mise à jour de la branche (`mcp__github__update_pull_request_branch`, ou `gh pr update-branch <n>`). Si la mise à jour échoue, laisse la PR ouverte et signale-la « conflit après fusion ». Une PR mise à jour a un nouveau commit : refais l'étape 3 pour elle (CI puis nouvelle révision).

## 5. Résumé final (court)

```
Vague N — <points complétés>/<points prévus> points
Fusionnées : #<pr> (issue #<i>), …
Ouvertes : #<pr> — <raison>, …
Bloquées : #<issue> — <raison>, …
```

Points complétés = somme des tailles des issues fermées ou dont la PR est fusionnée.

Ajoute au résumé, s'il y a lieu : `Prévus P > budget B`, et `Journal non écrit :` suivi des lignes que tu n'as pas pu écrire (voir ci-dessous).

**Journal**, juste avant le résumé :
1. pour chaque PR de la vague restée ouverte : `issue #I | taille T | ouverte | PR #n | <raison>` (CI échouée, CI absente, CI en attente, refusée par le réviseur, refusée par le garde de fusion, conflit après fusion) ;
2. puis la ligne de fermeture : `fermée | complétés C/P | utilisation: __ %`. Laisse `__` tel quel : l'utilisateur y note le pourcentage d'utilisation affiché dans l'app Claude. Termine le résumé par `Journal : note l'utilisation dans .claude/journal-vagues.md (facultatif).`

Si la session s'arrête avant cette étape (limite atteinte, session fermée), rien n'est écrit : la vague reste non fermée, et le prochain `/vagues:vague reprise` (ou `/vagues:vague N`) la marque `coupée`.

## Écrire une ligne au journal

Le journal (`.claude/journal-vagues.md`) est commité **directement sur `main`**, ligne par ligne, par cette session principale seulement (jamais par un sous-agent : `garde-agents-vague.py` bloque d'ailleurs les écritures sur `main` pour `implementeur` et `reviseur`). Ainsi, une session neuve (par ex. la reprise planifiée décrite dans le README du plugin et le `CLAUDE.md` du projet) voit l'état à jour. Le fichier est sous `.claude/`, en principe hors des chemins de la CI du projet (à vérifier pour chaque projet) : ces commits ne devraient déclencher aucune CI. Pas de PR pour le journal.

Ligne : `- <heure> | vague N | <événement…>` (format exact : section « Format » du journal), heure en UTC donnée par `date -u +%Y-%m-%dT%H:%MZ`. Ajoute-la **à la fin** du fichier, sans toucher aux autres lignes.

1. **Par MCP (de préférence, quelle que soit ta branche locale)** : `mcp__github__get_file_contents` (`path: ".claude/journal-vagues.md"`, `ref: "main"`) pour le contenu et le SHA du fichier, puis `mcp__github__create_or_update_file` (`branch: "main"`, même `path`, contenu + la ligne, `sha`, message `journal: vague N <événement>`). Conflit de SHA : relis et réessaie une fois.
2. **Sinon par git**, sans changer de branche :
   ```
   t=$(mktemp -d) && git fetch -q origin main && git worktree add -q --detach "$t" origin/main \
     && printf '%s\n' "<ligne>" >> "$t/.claude/journal-vagues.md" \
     && git -C "$t" commit -qam "journal: vague N <événement>" && git -C "$t" push -q origin HEAD:main; \
     git worktree remove --force "$t"
   ```
3. **Si les deux échouent** (écriture sur `main` refusée, réseau) : ne bloque pas la vague. Garde la ligne et recopie-la dans le résumé final sous `Journal non écrit :`, pour que l'utilisateur l'ajoute.
