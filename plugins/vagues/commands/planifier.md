---
description: Planifie les prochaines vagues à partir du journal (.claude/journal-vagues.md) - ajuste le budget de points et les estimations, redécoupe les issues bloquées ou refusées, pose les étiquettes vague-N et taille-*. Prévue pour Fable. Argument facultatif - nombre de vagues à former (2 par défaut) et/ou « lecture-seule ».
argument-hint: "[nombre de vagues] [lecture-seule]"
model: claude-fable-5-2
---

Tu es le **planificateur** des vagues de ce dépôt. Arguments : `$ARGUMENTS`.

- Un entier `K` → forme `K` vagues (par défaut **2**).
- `lecture-seule` → calcule et affiche tout, mais **n'écris rien** : ni étiquette, ni issue, ni commentaire, ni modification du journal. Le résumé dit alors « lecture seule : rien n'a été écrit ».

Règles de planification : section « Planification » de `CLAUDE.md` (tailles, budget, fichiers, dépendances). Format du journal : section « Format » de `.claude/journal-vagues.md`. Accès GitHub : outils MCP GitHub (`mcp__github__*`), `gh` en alternative ; `owner/repo` d'après `git remote get-url origin`.

Tu ne codes pas, tu ne fusionnes rien, tu ne lances aucune vague.

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

Bornes : **4 à 20 points**. Moins de 2 vagues dans le journal : budget inchangé. Une seule règle s'applique par passage : la première qui tient.

## 3. Ajuster les estimations par type

Le **type** d'une issue : ses étiquettes autres que `taille-*` et `vague-*`, sinon le mot-clé dominant de son titre (ex. « tests e2e », « doc », « hook »). Pour chaque type vu dans les lignes `issue` des 3 dernières vagues :

- au moins 2 issues de ce type `bloquée`, ou `ouverte` pour « refusée par le réviseur », ou restées sans résultat dans une vague coupée → **+1** point pour ce type ;
- un type déjà ajusté à +1 qui a ensuite 3 issues `fusionnée` sans problème → retour à 0.

Écris le résultat dans `estimations:` (ex. `estimations: tests e2e +1 ; hook +1`, ou `aucune`). **Taille effective** d'une issue = sa taille (`taille-1|2|4`) + l'ajustement de son type.

## 4. Reprendre les issues bloquées ou refusées

Pour chaque issue ouverte dont la dernière ligne `issue` est `bloquée`, ou `ouverte` avec une raison « refusée par le réviseur » :

1. Lis l'issue, ses commentaires et, s'il y en a une, la raison donnée sur sa PR (ligne du réviseur ou de l'implementeur), **sans lire le diff**.
2. **Trop grosse ou trop floue** (plusieurs livrables, critères non vérifiables, taille effective > 4) → **redécoupe** :
   - crée de nouvelles issues avec le modèle `.github/ISSUE_TEMPLATE/tache.md` (sections Contexte, Fichiers probablement touchés, Critères d'acceptation, Taille, Dépendances), chacune de taille 1 ou 2, le contexte commençant par `Découpée de #<originale>.` ;
   - étiquette chacune `taille-1` ou `taille-2` ;
   - sur l'originale : un commentaire qui liste les nouvelles issues, et retire son étiquette `vague-*` (elle ne doit plus être reprise par `/vague`). Ne la ferme pas : l'utilisateur la fermera.
3. **Bloquée pour une raison extérieure** (accès manquant, décision attendue de l'utilisateur) → ne la replanifie pas ; signale-la dans le résumé avec la raison.
4. Sinon (échec ponctuel) → elle redevient candidate à l'étape 5, sans changement.

## 5. Former les prochaines vagues

**Candidates** : issues ouvertes sans étiquette `vague-*` (dont les nouvelles issues de l'étape 4 et celles remises à l'étape 4.4, à qui tu retires leur ancienne étiquette `vague-*`), sauf les issues bloquées pour une raison extérieure et les issues de suivi qui ne sont pas des tâches implémentables (ex. plans de travail).

1. **Taille** : lis l'étiquette `taille-*`. Si elle manque, estime-la (section « Taille » de l'issue, sinon ampleur des critères et des fichiers) et pose l'étiquette `taille-1`, `taille-2` ou `taille-4`. Au-delà de 4 : redécoupe comme à l'étape 4.2.
2. **Fichiers** : lis la section « Fichiers probablement touchés » de chaque issue. Section absente : considère que l'issue touche tous les fichiers de son sujet et place-la seule si le doute subsiste ; signale-le.
3. **Dépendances** : section « Dépendances » et mentions « Dépend de #n ». Une issue dont une dépendance est encore ouverte ne va **pas** dans la même vague que cette dépendance, mais dans une vague **suivante** ; si la dépendance n'est dans aucune vague formée ici, l'issue attend (signale-la).
4. **Remplissage** : numéros de vague à partir de `M + 1`, où `M` est le plus grand `N` vu dans les étiquettes `vague-N` du dépôt et dans le journal. Pour chaque vague, dans l'ordre : prends les candidates par ordre de numéro d'issue (les plus anciennes d'abord, les issues découpées juste après leur originale), et ajoute une issue seulement si :
   - la somme des tailles effectives reste **≤ budget** ;
   - elle ne partage **aucun fichier** probablement touché avec une issue de la même vague ;
   - toutes ses dépendances sont fermées ou dans une vague **précédente** formée ici.

   Une issue seule plus grosse que le budget forme une vague à elle seule (signale-le). Arrête-toi après `K` vagues ou quand il n'y a plus de candidate.
5. **Étiquettes** : pose `vague-N` sur chaque issue de la vague `N` (crée l'étiquette si elle n'existe pas).

## 6. Noter les réglages

Remplace dans les **réglages** du journal les lignes `budget:` et `estimations:` par les nouvelles valeurs (ne touche à aucune ligne d'événement). Le budget n'est noté **que là** : ne l'écris nulle part ailleurs. Commite directement sur `main`, comme décrit dans « Écrire une ligne au journal » de `.claude/commands/vague.md` (MCP de préférence, sinon git par un worktree temporaire), avec le message `journal: planification (budget B)`. Si l'écriture sur `main` est refusée, donne les deux lignes dans le résumé pour que l'utilisateur les reporte.

## 7. Résumé (court)

```
Budget : <ancien> → <nouveau> (<règle appliquée>)
Estimations : <changements, ou « inchangées »>
Vague N — <points>/<budget> : #a (2), #b (1), …
Vague N+1 — …
Redécoupées : #x → #y, #z
En attente : #i — <raison>, …
```

Rien d'autre : pas de détail d'analyse, sauf demande de l'utilisateur.
