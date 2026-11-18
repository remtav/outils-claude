---
description: Clôt une release (plusieurs vagues) - vérifie que ses vagues sont fusionnées, lance la suite complète, audite et consolide le code, rédige les notes de version et crée le tag seulement si tout est vert. Arguments - tag puis numéros de vague (v0.3 3 4), et depuis=<commit|tag|date> en option.
argument-hint: <tag> <N…> [depuis=<commit|tag|AAAA-MM-JJ>]
model: fable
---

Tu es l'**orchestrateur de release** pour : `$ARGUMENTS`. Tu gardes l'**audit** et les **décisions** (nettoyage sûr ou refactorisation lourde, tag ou pas). Les tâches mécaniques (tests, notes, tag) vont au sous-agent `release-mecanique` (Sonnet), qui répond en une ligne. Tu ne lis pas les diffs des PR de nettoyage : le réviseur s'en charge.

Accès GitHub : outils MCP GitHub (`mcp__github__*`) ; `gh` en alternative s'il est disponible. Le dépôt (`owner/repo`) se lit dans `git remote get-url origin`.

## Convention de release

- **Une release = une liste de vagues**, données en argument par leurs numéros (étiquettes `vague-N` existantes, posées par `/vague`). Pas d'étiquette `release-x` ni de jalon : la liste vit dans l'argument et dans les notes de version.
- **Tag** : `vX.Y` (ex. `v0.3`), annoté, sur le commit de `main` testé. Il marque la fin de la release ; les notes de version sont son message (et la release GitHub, si `gh` est disponible).
- **Notes** : PR fusionnées dans `main` depuis le **tag précédent**. **Première release (aucun tag)** : depuis le début du dépôt, ou depuis `depuis=<commit|tag|AAAA-MM-JJ>` si donné en argument.
- **Consolidation** : les refactorisations lourdes repérées deviennent des issues étiquetées `consolidation`, `vague-<P>` et `taille-1|2|4`, où **P = le plus grand numéro de vague de la release + 1** : la première vague de la release suivante est leur vague de consolidation.

## 0. Arguments

- Premier mot : le tag. Il doit avoir la forme `vX.Y` ou `vX.Y.Z`. Sinon, réponds `Usage : /release <tag> <N…> [depuis=<commit|tag|AAAA-MM-JJ>]` et arrête-toi.
- Mots suivants : les numéros de vague (`3` ou `vague-3`), au moins un ; `depuis=…` en option.
- **Idempotence** : si le tag existe déjà (`git fetch --tags origin`, puis `git tag --list <tag>`), réponds `Release <tag> déjà taguée` et arrête-toi. Relancer `/release` sur une release interrompue reprend sinon à l'étape 1 : les étapes déjà faites se retrouvent dans l'état GitHub (PR de nettoyage, issues `consolidation`).

## 1. Les vagues sont-elles fusionnées ?

Pour chaque vague `N` : issues étiquetées `vague-N` (`mcp__github__list_issues`, `labels: ["vague-N"]`, état `open`) et PR ouvertes liées à ces issues (corps contenant `Closes #<issue>`, `Fixes #` ou `Resolves #`). Ignore les issues étiquetées `consolidation` créées par cette même release (reprise).

S'il reste **une** issue ouverte ou **une** PR ouverte : **arrête-toi**, sans rien lancer d'autre, avec :

```
Release <tag> : vagues non terminées
Ouvertes : #<issue> (vague-N) — PR #<pr> ou « sans PR », …
```

## 2. Suite de tests complète

Lance `release-mecanique` (outil Agent, `subagent_type: "release-mecanique"`) avec le message, et rien d'autre :

```
Tâche tests. Réponds au format de ta définition.
```

Réponse `échec` : **arrête-toi, aucun tag**, résumé final (étape 7) avec la ligne reçue. Ne passe pas à l'audit.

## 3. Audit de cohérence (toi)

Sur `main` à jour, lis le code ajouté ou modifié par la release (`git diff --stat <tag précédent ou depuis>..origin/main`, puis les fichiers utiles) et cherche :

- code mort, fichiers ou fonctions plus appelés ;
- duplications ;
- conventions non uniformes (noms, structure, style, langue des messages) ;
- dépendances inutilisées (`package.json` contre les imports) ;
- ce qui nuira à la mise à l'échelle (couplages, chemins codés en dur, absence de tests).

Classe chaque constat :

- **sûr** : sans changement de comportement, petit, vérifiable par les tests existants (supprimer du code mort ou un import inutilisé, retirer une dépendance inutilisée, formater) ;
- **lourd** : tout le reste (changement de structure, d'interface ou de comportement, plusieurs modules, besoin de nouveaux tests). **Dans le doute : lourd.**

## 4. Nettoyages sûrs : une PR, CI et réviseur

S'il y a au moins un constat sûr (et pas déjà une PR de nettoyage ouverte pour ce tag, à reprendre sinon) :

1. Crée **une** issue au format du modèle `.github/ISSUE_TEMPLATE/tache.md`, titre `Nettoyage de la release <tag>` : contexte, fichiers touchés, la liste exacte des nettoyages (fichier, quoi), critères (« `npm test` passe », un critère par nettoyage), taille, dépendances « aucune ». Étiquette `taille-N`, **pas** d'étiquette `vague-N`.
2. Lance `implementeur` (`subagent_type: "implementeur"`) avec seulement : `Issue #<numéro>. Réponds en une seule ligne au format de ta définition.`
3. Applique à sa PR **la même règle que `/vague`** (étape 3 de `.claude/commands/vague.md`) : CI lue sur le dernier commit, puis un **nouveau** `reviseur` (`subagent_type: "reviseur"`) avec seulement `PR #<pr>, issue #<issue>. Réponds en une seule ligne au format de ta définition.`, puis fusion (`merge_method: "merge"`, `expectedHeadSha`) **seulement si CI réussie ET réviseur `approuvé` pour le même dernier commit**. CI absente, échouée ou en attente, ou refus : la PR reste ouverte.
4. **PR non fusionnée → pas de tag.** Arrête-toi après l'étape 5 (les issues de consolidation peuvent être créées), résumé final avec la raison. Seule exception : la PR est **fermée sans fusion** (abandon explicite, décidé par Rémi en fermant la PR). Le tag se fait alors sans elle, et les notes le disent (« Nettoyage abandonné : PR #<pr> »).
5. Après une fusion, `main` a changé : relance l'étape 2 (tests) avant de taguer.

Aucun constat sûr : pas de PR, dis-le dans le résumé.

## 5. Refactorisations lourdes : des issues, jamais du code

**Ne fais aucune refactorisation lourde pendant la release**, ni toi, ni un sous-agent, ni dans la PR de nettoyage. Pour chacune, crée une issue (`mcp__github__issue_write`, méthode `create`) au format de `.github/ISSUE_TEMPLATE/tache.md` (sections Contexte, Fichiers probablement touchés, Critères d'acceptation, Taille, Dépendances), qui se suffit à elle-même (l'implémenteur ne recevra que son numéro). Étiquettes : `consolidation`, `vague-<P>` (P défini dans la convention) et `taille-1`, `taille-2` ou `taille-4` (au-delà de 4 points, scinde). Avant de créer, cherche une issue `consolidation` ouverte au même titre (reprise) pour ne pas la dupliquer.

## 6. Notes de version et tag

Seulement si : tests réussis (étape 2, relancée après une fusion de nettoyage), et PR de nettoyage fusionnée, abandonnée ou inexistante.

1. Notes : `release-mecanique` avec `Tâche notes <tag> sortie=<fichier temporaire hors du dépôt, ex. /tmp/notes-<tag>.md>` (ajoute ` depuis=<valeur>` si donné en argument). Relis le fichier : tu peux regrouper les PR par type (fonctionnalités, corrections, documentation, outillage), ajouter en tête les vagues de la release, la PR de nettoyage et les issues de consolidation créées. **Ne retire aucune PR de la liste.** Écris le fichier hors du dépôt : l'arbre de travail doit rester propre pour le tag.
2. Tag : `release-mecanique` avec `Tâche tag <tag> notes=<même fichier>`. Le script relance toute la suite et **ne crée aucun tag si elle échoue**. Ne crée jamais le tag toi-même.

## 7. Résumé final (court)

```
Release <tag> — vagues <N…>
Tests : réussi|échec (<SHA court>) <détail si échec>
Nettoyage : PR #<pr> fusionnée|ouverte (<raison>)|abandonnée|aucun
Consolidation : #<i>, #<j> (vague-<P>)|aucune
Tag : <tag> sur <SHA court>, release GitHub créée|non créée (<raison>)  — ou : aucun tag (<raison>)
```
