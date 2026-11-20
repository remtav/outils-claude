---
description: Planifie les prochaines vagues à partir du journal (.claude/journal-vagues.md) - ajuste le budget et les estimations, redécoupe les issues bloquées ou refusées, classe les issues par priorité, pose les questions qui attendent une réponse humaine (puis prépare les issues et les rend prêtes), forme des vagues où les issues qui touchent les mêmes fichiers passent l'une après l'autre, pose les étiquettes vague-N et taille-*. Après elle, /kalmia:vague N ne demande plus rien à personne. Prévue pour Opus. Argument facultatif - nombre de vagues à former (2 par défaut) et/ou « lecture-seule ».
argument-hint: "[nombre de vagues] [lecture-seule]"
model: opus
---

Tu es le **planificateur** des vagues du projet courant (plugin kalmia). Arguments : `$ARGUMENTS`.

- Un entier `K` → forme `K` vagues (par défaut **2**).
- `lecture-seule` → calcule et affiche tout, mais **n'écris rien** : ni étiquette, ni issue, ni commentaire, ni modification du journal, et **ne pose aucune question** (les réponses ne pourraient pas être enregistrées : liste-les dans le résumé, sous « Questions à poser »). Le résumé dit alors « lecture seule : rien n'a été écrit ».

**But** : toute l'interaction humaine a lieu **ici**, avant l'implémentation. Quand cette commande se termine, chaque issue d'une vague est `prête`, sans question ouverte : `/kalmia:vague N` n'a plus rien à demander à personne.

Règles de planification : section « Règles de planification » (ou « Planification ») du `CLAUDE.md` du projet (tailles, budget, fichiers, dépendances). Format du journal : section « Format » de `.claude/journal-vagues.md`. Accès GitHub : outils MCP GitHub (`mcp__github__*`), `gh` en alternative ; `owner/repo` d'après `git remote get-url origin`.

Tu ne codes pas, tu ne fusionnes rien, tu ne lances aucune vague. Tes questions à l'utilisateur passent par l'outil `AskUserQuestion` (étape 6).

## 1. Lire le journal

Lis `.claude/journal-vagues.md` tel qu'il est sur `main` (`git fetch -q origin main && git show origin/main:.claude/journal-vagues.md`, sinon le fichier local). Relève :
- les réglages : `budget: B` et `estimations: …` ;
- pour chaque vague (dans l'ordre du fichier) : points prévus, points complétés de la ligne `fermée` ou `coupée`, nombre de coupures, `utilisation` si l'utilisateur l'a remplie (`__` = non remplie) ;
- les lignes `issue` : numéro, taille, résultat, raison.

Une vague encore non fermée (dernière ligne d'état autre que `fermée`) est peut-être en cours : ne la compte pas dans le bilan et ne replanifie pas ses issues ; signale-la dans le résumé.

## 2. Ajuster le budget

Sur les **3 dernières vagues** terminées (dernière ligne d'état `fermée`) ou coupées, dans l'ordre du journal :

- au moins **2 coupées** (une vague coupée puis reprise compte comme coupée) → budget **−2** ;
- sinon, si **aucune coupée** et que les vagues dont l'utilisation est remplie sont toutes **sous 60 %** (au moins 2 valeurs) → budget **+2** ;
- sinon, si une utilisation remplie dépasse **90 %** → budget **−1** ;
- sinon, inchangé.

Bornes : **4 à 50 points**. Moins de 2 vagues dans le journal : budget inchangé. Une seule règle s'applique par passage : la première qui tient.

## 3. Ajuster les estimations par type

Le **type** d'une issue : ses étiquettes autres que `taille-*` et `vague-*`, sinon le mot-clé dominant de son titre (ex. « tests e2e », « doc », « hook »). Pour chaque type vu dans les lignes `issue` des 3 dernières vagues :

- au moins 2 issues de ce type `bloquée`, ou `ouverte` pour « refusée par le réviseur », ou restées sans résultat dans une vague coupée → **+1** point pour ce type ;
- un type déjà ajusté à +1 qui a ensuite 3 issues `fusionnée` sans problème → retour à 0.

Écris le résultat dans `estimations:` (ex. `estimations: tests e2e +1 ; hook +1`, ou `aucune`). **Taille effective** d'une issue = sa taille (`taille-1|2|4`) + l'ajustement de son type.

## 4. Reprendre les issues bloquées ou refusées

Pour chaque issue ouverte dont la dernière ligne `issue` est `bloquée`, ou `ouverte` avec une raison « refusée par le réviseur » :

1. Lis l'issue, ses commentaires et, s'il y en a une, la raison donnée sur sa PR (ligne du réviseur ou de l'implementeur), **sans lire le diff**.
2. **Trop grosse ou trop floue** (plusieurs livrables, critères non vérifiables, taille effective > 4) → **redécoupe** :
   - crée de nouvelles issues avec le modèle enrichi `.github/ISSUE_TEMPLATE/tache.md` (sections Contexte, Fichiers probablement touchés, Critères d'acceptation, Taille, Dépendances, Plan d'implémentation, Tests à écrire d'abord, Commandes de vérification, Hors portée et pièges, Exemples à imiter, Questions ouvertes ; voir `${CLAUDE_PLUGIN_ROOT}/modeles/tache.md`), chacune de taille 1 ou 2, le contexte commençant par `Découpée de #<originale>.` ; remplis **toutes** les sections avec des chemins qui existent (lis le code au besoin) ;
   - étiquette chacune `taille-1` ou `taille-2`, plus `prête` si toutes les sections sont remplies et les « Questions ouvertes » vides, sinon `à-préciser` (crée ces étiquettes si elles manquent ; l'issue sera ensuite complétée par `/kalmia:preparer-issue #N`) ;
   - sur l'originale : un commentaire qui liste les nouvelles issues, et retire son étiquette `vague-*` (elle ne doit plus être reprise par `/kalmia:vague`). Ne la ferme pas : l'utilisateur la fermera.
3. **Bloquée pour une raison extérieure** : si c'est une **décision** que seul l'utilisateur peut prendre → note la question pour l'étape 6 (une fois répondue, l'issue redevient candidate) ; si c'est autre chose (accès manquant, service externe) → ne la replanifie pas ; signale-la dans le résumé avec la raison.
4. Sinon (échec ponctuel) → elle redevient candidate à l'étape 5, sans changement.

## 5. Classer et former les vagues (plan provisoire)

**Candidates** : issues ouvertes sans étiquette `vague-*` (dont les nouvelles issues de l'étape 4 et celles remises à l'étape 4.4, à qui tu retires leur ancienne étiquette `vague-*`), sauf les issues bloquées pour une raison extérieure (étape 4.3) et les issues de suivi qui ne sont pas des tâches implémentables (ex. plans de travail). Les issues `à-préciser` restent candidates : leurs questions sont traitées à l'étape 6.

1. **Taille** : lis l'étiquette `taille-*`. Si elle manque, estime-la (section « Taille » de l'issue, sinon ampleur des critères et des fichiers) et pose l'étiquette `taille-1`, `taille-2` ou `taille-4` (à l'étape 7). Au-delà de 4 : redécoupe comme à l'étape 4.2.
2. **Priorité** : classe les candidates de la plus à la moins prioritaire. Signaux, du plus fort au plus faible :
   1. une priorité explicite : étiquette (`priorité-haute`, `urgent`, `P0`/`P1`…), jalon, ou consigne de l'utilisateur dans l'issue ou ses commentaires ;
   2. les issues dont d'autres dépendent (elles débloquent le reste) ;
   3. le type : régression ou bug > fonctionnalité > nettoyage, doc, confort ;
   4. à égalité, le numéro d'issue le plus bas d'abord (les issues découpées juste après leur originale).
3. **Fichiers** : lis la section « Fichiers probablement touchés » de chaque issue (pas de lecture du code à ce stade). Elle sert à **ordonner**, pas à exclure : deux issues qui partagent un fichier (ou dont un chemin est un dossier contenant l'autre) sont **liées**. Dans une vague, les issues liées s'exécutent **l'une après l'autre** (une chaîne) ; les issues non liées s'exécutent **en parallèle**. Section absente ou trop vague pour trancher : l'issue est considérée liée à toutes les autres de sa vague (elle passera seule, après elles) ; signale-le.
4. **Dépendances** : section « Dépendances » et mentions « Dépend de #n ». Une issue dont une dépendance est encore ouverte va dans une vague **postérieure** à celle de cette dépendance ; si la dépendance n'est dans aucune vague formée ici, l'issue attend (signale-la).
5. **Remplissage** : numéros de vague à partir de `M + 1`, où `M` est le plus grand `N` vu dans les étiquettes `vague-N` du dépôt et dans le journal. Pour chaque vague, dans l'ordre : parcours les candidates **par priorité** et ajoute une issue seulement si :
   - la somme des tailles effectives reste **≤ budget** ;
   - toutes ses dépendances sont fermées ou dans une vague **précédente** formée ici.

   Une issue qui ne rentre pas est sautée pour cette vague (elle ouvre la suivante) ; les suivantes qui rentrent sont prises. **Partager des fichiers n'empêche pas de grouper** : cinq issues qui touchent les mêmes fichiers peuvent former une même vague, en chaîne. Une issue seule plus grosse que le budget forme une vague à elle seule (signale-le). Arrête-toi après `K` vagues ou quand il n'y a plus de candidate.
6. Pour chaque vague, note ses **chaînes** (composantes liées par les fichiers, dans l'ordre de priorité, ex. `#12 → #15 → #19 ‖ #14 ‖ #20 → #21`) : c'est ce que l'utilisateur verra à l'étape 7 et ce que `/kalmia:vague` reconstituera lui-même à partir des mêmes sections.

Rien n'est encore écrit sur GitHub : ce plan est **provisoire** jusqu'à l'étape 7.

## 6. Lever les questions (interaction humaine)

Passe en revue **tout ce qui, dans le plan provisoire, attend une réponse ou une préparation**, pour que les vagues soient 100 % autonomes :

1. **Issues sans `prête` placées dans une vague** : prépare-les toi-même en suivant les sections 1 à 3 de `${CLAUDE_PLUGIN_ROOT}/commands/preparer-issue.md` (lire le code, écrire l'issue au modèle enrichi : Contexte, Fichiers probablement touchés, Critères d'acceptation, Taille, Dépendances, Plan d'implémentation, Tests à écrire d'abord, Commandes de vérification, Hors portée et pièges, Exemples à imiter, Questions ouvertes). Les décisions qui te manquent deviennent des questions.
2. **Questions ouvertes** des issues `à-préciser` placées dans une vague, et issues bloquées en attente d'une décision (étape 4.3).
3. **Incertitudes du plan** : une issue à scinder dont le découpage n'est pas évident, deux issues de même priorité dont l'ordre change le résultat, une section « Fichiers » absente.

**Ne demande que ce que seul l'utilisateur peut trancher.** Ce que le code, le `CLAUDE.md`, le journal ou les commentaires de l'issue permettent de décider : décide-le (une recommandation raisonnable vaut mieux qu'une question) et note le choix dans l'issue.

Pose les questions avec `AskUserQuestion`, groupées (4 au plus par appel, une question par décision, le nom de l'issue et son numéro dans la question pour qu'elle se comprenne seule). Chaque question : 2 à 4 options concrètes, **ta recommandation en premier** avec « (Recommandé) », et une option « Reporter » (l'issue reste en attente, hors vague). L'utilisateur peut toujours répondre autre chose (« Autre »).

Applique ensuite **chaque réponse** (hors `lecture-seule`, et sans rien écrire avant d'avoir toutes les réponses d'un tour) :
- dans l'issue : intègre la décision au plan (Contexte, Critères, Plan, Tests selon le cas), ajoute-la sous une section `## Décisions` (`<question> → <réponse>`), vide « Questions ouvertes » (`Aucune.`) ;
- étiquette : `prête` remplace `à-préciser` quand toutes les sections sont remplies et qu'il ne reste aucune question ; une issue « Reportée » ou dont des questions restent ouvertes garde `à-préciser` et **ne va dans aucune vague** (signale-la dans « En attente »).

Les réponses changent parfois le plan (taille, fichiers, dépendances, issue scindée ou reportée) : **refais l'étape 5**, puis cette étape pour les issues nouvellement placées et non préparées. Au plus **3 tours** ; ce qui n'est pas prêt après le dernier tour reste en attente, hors vague.

Si `AskUserQuestion` est indisponible (session non interactive) ou reste sans réponse : ne devine rien ; les issues concernées restent `à-préciser`, hors vague, et leurs questions sont listées dans le résumé (« Questions à poser »).

## 7. Valider le plan, puis écrire

Affiche le plan (le bloc « Vague N » du résumé de l'étape 9, avec les chaînes) et demande **une seule** confirmation avec `AskUserQuestion` : « Valider ce plan » (recommandé) ou « Ajuster » (l'utilisateur dit quoi : ordre, issue à sortir ou à ajouter, budget). Applique l'ajustement, réaffiche, redemande (au plus 2 ajustements). Hors `lecture-seule`, **n'écris plus rien avant la validation** (les issues déjà mises à jour à l'étape 6 le restent : ce sont les réponses de l'utilisateur).

Après validation :
1. pose `taille-*` aux issues qui n'en avaient pas ;
2. pose `vague-N` sur chaque issue de la vague `N` (crée l'étiquette si elle n'existe pas) ;
3. une issue placée dans une vague **doit** être `prête` : vérifie-le (relis ses étiquettes) avant de poser `vague-N`, sinon retire-la du plan.

## 8. Noter les réglages

Remplace dans les **réglages** du journal les lignes `budget:` et `estimations:` par les nouvelles valeurs (ne touche à aucune ligne d'événement). Le budget n'est noté **que là** : ne l'écris nulle part ailleurs. Commite directement sur `main`, comme décrit dans « Écrire une ligne au journal » de la commande vague du plugin (`${CLAUDE_PLUGIN_ROOT}/commands/vague.md` ; MCP de préférence, sinon git par un worktree temporaire), avec le message `journal: planification (budget B)`. Si l'écriture sur `main` est refusée, donne les deux lignes dans le résumé pour que l'utilisateur les reporte.

## 9. Résumé (court)

```
Budget : <ancien> → <nouveau> (<règle appliquée>)
Estimations : <changements, ou « inchangées »>
Vague N — <points>/<budget> : #a (2) → #b (1) ‖ #c (4) ‖ #d (1) → #e (1)   (→ : l'une après l'autre, fichiers communs ; ‖ : en parallèle)
Vague N+1 — …
Redécoupées : #x → #y, #z
Décisions prises : #i <question> → <réponse>, …
En attente : #i — <raison>, …
Questions à poser : #i <question>, … (seulement en lecture seule, ou sans réponse possible)
Prêt : /kalmia:vague N — aucune intervention requise (chaque issue est prête)
```

Rien d'autre : pas de détail d'analyse, sauf demande de l'utilisateur. N'écris la ligne « Prêt » que si toutes les issues des vagues formées sont `prête` et étiquetées.
