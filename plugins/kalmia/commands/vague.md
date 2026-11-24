---
description: Orchestre une vague d'issues (étiquette vague-N) avec les sous-agents kalmia:implementeur et kalmia:reviseur ; fusionne seulement si la CI a réussi et que le réviseur approuve. Argument : un numéro de vague (3 ou vague-3) ou « reprise ».
argument-hint: <N | vague-N | reprise>
---

Tu es l'**orchestrateur** de la vague demandée : `$ARGUMENTS`. Tu coordonnes, tu ne codes pas. Ton contexte doit rester léger : tu ne gardes que les **réponses d'une ligne** des sous-agents et l'état GitHub (numéros, états, vérifications). Tu ne lis **ni les diffs, ni le code, ni les fichiers modifiés** des PR.

Accès GitHub : outils MCP GitHub (`mcp__github__*`) ; `gh` en alternative s'il est disponible. Le dépôt (`owner/repo`) se lit dans `git remote get-url origin`.

**Aucune intervention humaine.** Les questions et décisions ont été réglées en amont par `/kalmia:planifier` (issues `prête`, sans question ouverte). Pendant la vague, tu ne poses **aucune question** à l'utilisateur (pas d'`AskUserQuestion`) : ce qui manque bloque l'issue concernée, avec sa raison au journal, et la vague continue.

## 0. Argument

- `N` ou `vague-N` (N entier) → l'étiquette traitée est `vague-N`.
- `reprise` → lis `.claude/journal-vagues.md` **tel qu'il est sur `main`** (`git fetch -q origin main && git show origin/main:.claude/journal-vagues.md` ; ou `mcp__github__get_file_contents` avec `ref: "main"` ; si les deux échouent, le fichier local). Format : section « Format » du journal. Cherche la **dernière vague non fermée** : la vague dont la dernière ligne d'état (`ouverte`, `reprise`, `coupée` ou `fermée`) n'est pas `fermée` ; s'il y en a plusieurs, celle dont la ligne d'état la plus récente est la plus bas dans le fichier.
  - **Fichier absent ou aucune vague non fermée : réponds exactement `Rien à reprendre` et arrête-toi**, sans aucun autre appel (ni GitHub, ni sous-agent, ni écriture).
  - **Vague encore active** : si la dernière ligne de cette vague (tous événements confondus) date de **moins de 90 minutes** (`date -u`), une autre session y travaille probablement : réponds `Vague N en cours (dernière ligne <heure>) : rien à reprendre` et arrête-toi, sans aucun autre appel.
  - Sinon, lis-y le numéro de vague `N` et continue avec `vague-N` : l'étape 1 la marque `coupée` puis `reprise`.
- Autre chose ou rien → réponds `Usage : /kalmia:vague <N | vague-N | reprise>` et arrête-toi.

## 1. État de la vague (idempotence)

Liste les issues étiquetées `vague-N` (`mcp__github__list_issues` avec `labels: ["vague-N"]`, ouvertes **et** fermées ; ou `gh issue list --label vague-N --state all`). Pour chacune, déduis son état de GitHub seulement :

| État GitHub | Étape |
|---|---|
| issue fermée, ou PR liée fusionnée | **terminée** : sauter (mais voir « Suivi après fusion » ci-dessous) |
| issue ouverte, sans PR, **sans** l'étiquette `prête` | **bloquée, non préparée** : ne pas l'implémenter, aucun sous-agent (voir ci-dessous) |
| PR **en brouillon** liée (travail interrompu : l'implémenteur ouvre sa PR en brouillon dès son premier commit) | étape 2 : relancer l'implémenteur, qui reprend sa branche |
| PR ouverte liée, **hors brouillon** (corps contenant `Closes #<issue>`, `Fixes #<issue>` ou `Resolves #<issue>`, le numéro suivi d'une **limite de mot** : `Closes #6` ne désigne pas l'issue 69 ; motif : `(?i)\b(close[sd]?\|fix(e[sd])?\|resolve[sd]?) #<issue>\b`) | passer directement à l'étape 3 (CI + révision) |
| aucune PR | étape 2 (implémentation) |

**Garde « prête ».** `/kalmia:planifier` ne place dans une vague que des issues `prête` ; cette garde couvre les étiquettes posées à la main. Une issue ouverte de la vague **sans** l'étiquette `prête` n'est jamais confiée à l'implémenteur (une issue qui a déjà une PR ouverte suit sa ligne du tableau). Elle est **bloquée** avec la raison `non préparée (lancer /kalmia:preparer-issue #N)` : écris-la au journal (ligne `issue #I | taille T | bloquée | — | non préparée (lancer /kalmia:preparer-issue #I)`) et mets-la dans « Bloquées » du résumé. **Aucun sous-agent n'est lancé pour elle.** Les issues déjà ouvertes avant l'introduction de `/kalmia:preparer-issue` n'ont pas `prête` : c'est voulu, elles passent d'abord par `/kalmia:preparer-issue #N`. Une issue `à-préciser` est dans le même cas (ses « Questions ouvertes » attendent une décision).

Relancer `/kalmia:vague N` sur une vague partiellement faite reprend donc là où elle en était, sans refaire les issues terminées.

**Suivi après fusion.** Pour chaque PR de la vague déjà fusionnée, compare le dernier commit de sa branche (`git ls-remote origin <branche>`, ou `mcp__github__list_commits` sur la branche) au SHA de tête que la PR avait à la fusion. S'ils diffèrent, des commits ont été poussés **après** la fusion et ne sont pas dans `main` : liste-les dans le résumé sous `Suivi à reprendre :` (`PR #n : <branche> <sha court>`) et note-le au journal (`issue #I | … | fusionnée | PR #n | suivi : commits non fusionnés <sha court>`). Liste aussi, sous `Branches orphelines :`, les branches `<numéro>-<slug>` des issues de la vague qui n'ont aucune PR ouverte ni fusionnée (travail interrompu : `reprise` les reprend, sinon l'utilisateur les supprime). Tu ne supprimes aucune branche toi-même.

Lis aussi la taille de chaque issue dans ses étiquettes `taille-1`, `taille-2`, `taille-4` (1, 2 ou 4 points ; sans étiquette : 0, et le signaler) : **points prévus** = somme sur toutes les issues de la vague.

Lis enfin le **budget** dans les réglages du journal (ligne `budget:`, seul endroit où il est noté). Si les points prévus le dépassent, signale-le dans le résumé final (`Prévus P > budget B`) ; ne bloque pas la vague.

**Catégories de raison.** Toute raison écrite au journal (issue `ouverte` ou `bloquée`) commence par une **catégorie**, pour que `/kalmia:planifier` distingue ce qui relève de l'humain de ce qui relève d'un échec de la vague : `humain :` (approbation de la personne responsable, décision, entente écrite à confirmer), `dépendance :` (issue ou PR dont elle dépend, non fusionnée), `refusée :` (refusée par le réviseur), `CI :` (vérification échouée, absente ou en panne), `coupure :` (limite d'utilisation, session coupée), `externe :` (service ou accès indisponible), `autre :`.

**Journal** (voir « Écrire une ligne au journal » plus bas) :
1. Pour chaque vague **non fermée** du journal (définition à l'étape 0), y compris `N`, dont la dernière ligne d'état n'est pas déjà `coupée` : écris `coupée | complétés C/P`, avec `P` et `C` calculés pour cette vague-là comme ici et à l'étape 5 (issues de son étiquette `vague-M`).
2. Puis, pour `N` : `reprise | prévus P` si `N` était non fermée (cas de `/kalmia:vague reprise`, ou d'un `/kalmia:vague N` relancé sur une vague coupée), sinon `ouverte | prévus P`.

## 2. Implémentation : chaînes en parallèle, issues liées en séquence

Les issues d'une vague ne sont pas toutes lancées en même temps : celles qui touchent les **mêmes fichiers** passent **l'une après l'autre**, pour que leurs PR n'entrent pas en conflit à la fusion ; les autres passent en parallèle.

**Former les chaînes.** Pour les issues à implémenter (étiquette `prête`, sans PR), lis la section « Fichiers probablement touchés » de chacune (corps de l'issue seulement, jamais le code). Deux issues sont **liées** si elles partagent un chemin, ou si un chemin de l'une est un dossier qui contient un chemin de l'autre. Une **chaîne** est un ensemble d'issues liées (directement ou par transitivité), dans l'ordre des numéros d'issue croissants. Une issue sans section exploitable est considérée liée à toutes les autres : elle forme une chaîne à part, lancée **seule**, quand toutes les autres chaînes sont terminées. Une issue qui n'est liée à aucune autre est une chaîne d'une seule issue. Les issues dont la PR est déjà ouverte (étape 1, reprise) sont traitées d'abord à l'étape 3 et comptent comme précédentes dans leur chaîne.

**Exécution.**
- **Chaînes différentes : en parallèle**, **au plus 3 sous-agents `implementeur` en même temps** ; lance la suite quand l'un répond.
- **Dans une chaîne : l'une après l'autre.** L'issue suivante d'une chaîne n'est lancée qu'après que la précédente a **abouti à sa fin** : PR fusionnée (étape 3), ou laissée ouverte/bloquée avec sa raison. Ainsi l'implémenteur suivant repart d'un `main` qui contient déjà la fusion précédente. Une chaîne continue même si l'issue précédente a échoué (elle repart alors d'un `main` sans elle ; une éventuelle PR laissée ouverte sera signalée « conflit après fusion » à l'étape 4 si elle finit par entrer en conflit).
- **Dépendances, avant chaque lancement.** Lis la section « Dépendances » de l'issue (corps seulement) : pour chaque `#n` cité, l'issue `n` doit être **fermée** ou sa PR **fusionnée**. Sinon, **ne lance aucun implémenteur** : l'issue est `bloquée` avec la raison `dépendance : #n non fusionnée (non lancée)`, écrite au journal une seule fois, et la chaîne passe à l'issue suivante. Vérifie au moment du lancement, pas seulement au début de la vague : une dépendance fusionnée plus tôt dans la vague la débloque.
- **PR empilées (chaîne dont la précédente attend).** Si la précédente d'une chaîne est restée ouverte parce qu'elle **attend un humain** (`humain :`) ou la fin de sa CI/révision, et **non** parce qu'elle est refusée, l'issue suivante peut être lancée **empilée** : ajoute au message `Base : <branche de la précédente> (PR #<p>).` L'implémenteur part de cette branche et ouvre sa PR avec elle pour base. Une PR empilée n'est jamais fusionnée avant sa base : une fois la base fusionnée, passe la PR sur `main` (`mcp__github__update_pull_request` avec `base: "main"`), mets sa branche à jour, puis refais l'étape 3. Sans cette condition, la chaîne attend la fin de la précédente comme avant.
- Pour chaque issue, lance un sous-agent `implementeur` du plugin (outil Agent, `subagent_type: "kalmia:implementeur"`, **`isolation: "worktree"`**) avec ce message, **et rien d'autre** :

```
Issue #<numéro>. Réponds en une seule ligne au format de ta définition.
```

- **Toujours `isolation: "worktree"`** : chaque implémenteur travaille dans son propre arbre git, jamais dans la copie de cette session. Sans cela, des implémenteurs lancés en parallèle partagent le même dossier et changent de branche l'un sous l'autre. Si l'outil Agent refuse l'isolation (pas de dépôt git, par ex.), lance les implémenteurs **un à la fois**.
- Garde seulement sa ligne de réponse (`#<issue> → <PR ou —> | réussi|bloqué|partiel | <raison>`).
- `bloqué` ou pas de PR : l'issue est **bloquée** ; passe à la suivante de sa chaîne.
- Dès qu'un implémenteur répond avec une PR, fais l'étape 3 pour cette PR **sans attendre** les autres chaînes (c'est elle qui débloque la suite de sa chaîne).

**Journal** : pour chaque issue **bloquée**, écris aussitôt `issue #I | taille T | bloquée | <PR #n ou —> | <raison de l'implementeur>`. Les issues qui ont une PR sont notées à l'étape 3 (fusion) ou 5 (restée ouverte).

**Panne systémique : s'arrêter plutôt que s'user.** Si, pour **deux PR différentes** de la vague, la **même** vérification (même nom) échoue **sans verdict** (erreur d'exécution de l'action, fin en moins de 2 minutes, y compris après une relance), la cause est probablement commune (jeton expiré, secret manquant, service en panne), pas les PR. Alors : **ne lance plus aucun implémenteur** ; les issues non lancées restent simplement non lancées (aucune ligne `bloquée` par issue) ; écris **une seule** ligne `suspendue | CI : <vérification> en erreur sans verdict sur #a, #b ; cause probable commune` ; mets la panne en tête du résumé (`Vague suspendue : …`) avec les issues non lancées en une ligne. Continue seulement la révision des PR déjà ouvertes, puis ferme la vague (étape 5).

## 3. CI et révision de chaque PR

Pour chaque PR (nouvelle ou déjà ouverte) :

1. **CI.** Lis l'état des vérifications du dernier commit (`mcp__github__pull_request_read` méthodes `get_check_runs` et `get_status`, ou `gh pr checks <n>`). Tant qu'une vérification est en attente : **programme ton réveil** (section « Attendre sans s'arrêter » plus bas) puis relis, **espacé** (environ toutes les 2 à 5 minutes ; jamais en boucle serrée), au plus **30 minutes** pour cette PR. Au-delà, considère-la « en attente » : écris aussitôt au journal `issue #I | taille T | ouverte | PR #n | CI : en attente après 30 min`, et passe à la suite (la PR sera relue à chaque réveil suivant et fusionnée si sa CI devient verte).
   - **réussie** : toutes les vérifications terminées et vertes ;
   - **échouée** : au moins une rouge ou annulée → la PR reste ouverte ;
   - **absente** : aucune vérification configurée pour cette PR (cas fréquent : le workflow ne se déclenche que sur certains chemins). Note-le. **Règle par défaut : une PR à CI absente n'est pas fusionnée**, même si l'implémenteur rapporte ses tests locaux réussis ; elle reste ouverte avec la raison « CI absente ». Cette commande ne contient aucune règle qui autorise la fusion sans CI.
2. **Révision.** Lance un sous-agent `reviseur` du plugin (`subagent_type: "kalmia:reviseur"`), **nouveau pour chaque PR**, avec ce message et rien d'autre (ni résumé de l'implémentation, ni ton avis) :

   ```
   PR #<pr>, issue #<issue>. Réponds en une seule ligne au format de ta définition.
   ```

   Garde seulement sa ligne (`PR #<n> | approuvé` ou `PR #<n> | refusé | <raison>`).
3. **Fusion — seulement si les deux conditions tiennent pour le même dernier commit : CI réussie ET réviseur `approuvé`.** Vérifie juste avant que le SHA de tête n'a pas changé depuis la révision (sinon, nouvelle révision). Fusionne alors (`mcp__github__merge_pull_request` avec `merge_method: "merge"` et `expectedHeadSha`, ou `gh pr merge <n> --merge`). Dans tous les autres cas, **ne fusionne pas** : la PR reste ouverte, avec sa raison (CI échouée, CI absente, CI en attente, refusée par le réviseur).
4. **Garde de fusion.** Le hook `garde-fusion.py` du plugin revérifie au moment de la fusion : CI réussie sur le SHA de tête **et** commentaire du réviseur avec le marqueur `<!-- verdict-reviseur: approuvé sha=<sha de tête> -->`. S'il refuse la fusion (outil bloqué avec un message « Bloqué par le garde de fusion »), **ne réessaie pas** et ne contourne pas (autre outil, `gh api`, autre méthode de fusion) : la PR reste ouverte, avec la raison `refusée par le garde de fusion : <raison>`.

Seule cette session principale fusionne : le garde `garde-agents-vague.py` du plugin bloque la fusion et l'approbation pour `implementeur` et `reviseur`.

**Journal** : après chaque fusion, écris aussitôt `issue #I | taille T | fusionnée | PR #n`. Une PR laissée ouverte est notée à l'étape 5 seulement (l'étape 4 peut encore la faire fusionner).

## 4. Après chaque fusion

Les autres PR ouvertes de la vague peuvent maintenant être en conflit avec `main`. Pour chacune : tente une mise à jour de la branche (`mcp__github__update_pull_request_branch`, ou `gh pr update-branch <n>`). Si la mise à jour échoue, laisse la PR ouverte et signale-la « conflit après fusion ». Une PR mise à jour a un nouveau commit : refais l'étape 3 pour elle (CI puis nouvelle révision) ; sa nouvelle CI s'attend de la même façon, avec réveil programmé.

## Attendre sans s'arrêter (réveil)

Quand plus aucun sous-agent ne tourne, **rien ne te réveille** : si tu termines ton tour en disant « je revérifie plus tard », la vague reste arrêtée jusqu'à ce que l'utilisateur écrive. Un `sleep` en avant-plan est d'ailleurs bloqué.

**Règle.** Tant qu'une PR de la vague a une CI en attente (étape 3 ou 4), ou qu'une chaîne attend la fusion de sa précédente, tu **ne termines pas ton tour sans avoir programmé ton réveil**. Terminer son tour sans réveil n'est permis que si la vague est **fermée** (étape 5), ou **suspendue** avec sa raison au journal. Un sous-agent encore en cours compte comme réveil (sa réponse te réveille) : pas besoin d'en programmer un autre.

**Mécanisme**, dans cet ordre de préférence :
1. **Commande de fond qui surveille la CI** : `Bash` avec `run_in_background: true` et `timeout: 1800000` (30 min). La fin de la commande te réveille. Si `gh` fonctionne (`gh auth status`) :
   ```
   for i in $(seq 20); do for p in <n1> <n2>; do gh pr checks "$p" >/dev/null 2>&1; [ $? -eq 8 ] || exit 0; done; sleep 90; done
   ```
   (`<n1> <n2>` : les PR dont la CI est en attente. `gh pr checks` sort avec le code 8 tant qu'une vérification est en attente : la commande se termine dès qu'une des PR n'a plus rien en attente, ou après 30 min.)
2. **Sinon, minuterie de fond** (sans `gh`, accès GitHub par MCP seulement) : `Bash` avec `run_in_background: true`, commande `sleep 180` (3 min). À sa fin, relis l'état par MCP, puis reprogramme-la si l'attente continue. L'outil `Monitor` (boucle `until`) convient aussi s'il est disponible.
3. **En dernier recours**, si les commandes de fond sont indisponibles : un réveil unique programmé dans **cette** session dans 3 à 5 minutes (`ScheduleWakeup`, `CronCreate` ou `send_later`, selon ce qui existe), à reprogrammer à chaque passage, et à supprimer s'il n'a plus d'objet.

Préfère 1 ou 2 : une commande de fond meurt avec la session, alors qu'un réveil programmé peut arriver après une coupure (voir « À chaque réveil »).

**À chaque réveil** (fin d'une commande de fond, réveil programmé, **ou réponse d'un sous-agent implémenteur ou réviseur**) :
1. **Une autre session a-t-elle repris la vague ?** Relis le journal sur `main` (comme à l'étape 0). Si une ligne `coupée` ou `reprise` de la vague `N` a été écrite **après** ta propre ligne `ouverte` ou `reprise`, la vague a été reprise ailleurs (cas de la limite d'utilisation atteinte puis de la reprise planifiée) : **arrête-toi sans rien écrire** ni fusionner, et réponds `Vague N reprise par une autre session : arrêt`. Les réponses de sous-agents en cours dans cette session ne déclenchent pas cette relecture ; les réveils de fond et programmés, si.
2. **Relis l'état de toutes les PR ouvertes de la vague**, pas seulement celle qui t'a réveillé : CI, verdict du réviseur, SHA de tête. Fusionne (étape 3, point 3) chacune dont la CI est devenue verte entre-temps et qui a son approbation sur ce SHA ; lance la révision de celles dont la CI vient de se terminer sans révision ; débloque la suite de leurs chaînes.
3. S'il reste de l'attente, reprogramme un réveil avant de finir ton tour.

## 5. Résumé final (court)

```
Vague N — <points complétés>/<points prévus> points
Fusionnées : #<pr> (issue #<i>), …
Ouvertes : #<pr> — <raison>, …
Bloquées : #<issue> — <raison>, …
À décider par un humain : #<pr> — <ce qui est attendu : approbation (fichier ou règle), décision, entente>, …
```

« À décider par un humain » regroupe toutes les PR dont la raison est `humain :` (une ligne chacune, avec l'action attendue), pour que la personne responsable n'ait pas à relire le journal. Omets la ligne s'il n'y en a pas.

Points complétés = somme des tailles des issues fermées ou dont la PR est fusionnée.

Ajoute au résumé, s'il y a lieu : `Prévus P > budget B`, `Suivi à reprendre :` et `Branches orphelines :` (étape 1), et `Journal non écrit :` suivi des lignes que tu n'as pas pu écrire (voir ci-dessous).

**Journal**, juste avant le résumé :
1. pour chaque PR de la vague restée ouverte : `issue #I | taille T | ouverte | PR #n | <catégorie> : <raison>` (CI échouée, CI absente, CI en attente, refusée par le réviseur, refusée par le garde de fusion, conflit après fusion, attend l'approbation). **Ne réécris pas** une ligne identique à la **dernière ligne de cette issue** au journal (même PR, même catégorie, même raison) : si rien n'a changé depuis une vague précédente, ne l'écris pas, mais garde-la dans le résumé ;
2. puis la ligne de fermeture : `fermée | complétés C/P | durée HhMM | utilisation: __ %` (`durée` = temps écoulé depuis la ligne `ouverte` ou `reprise` de cette session, calculé avec `date -u`). Laisse `__` tel quel : l'utilisateur y note le pourcentage d'utilisation affiché dans l'app Claude. Termine le résumé par `Journal : note l'utilisation dans .claude/journal-vagues.md (facultatif).`

Si la session s'arrête avant cette étape (limite atteinte, session fermée), rien n'est écrit : la vague reste non fermée, et le prochain `/kalmia:vague reprise` (ou `/kalmia:vague N`) la marque `coupée`.

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
