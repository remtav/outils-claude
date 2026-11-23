## Règles de planification

Mécanique des vagues fournie par le plugin `kalmia` (marketplace `outils-claude`). Le travail est découpé en **issues** (une unité implémentable seule, modèle [`tache.md`](.github/ISSUE_TEMPLATE/tache.md)), regroupées en **vagues** (étiquette `vague-N`, lancées par `/kalmia:vague N`), puis en **releases** (`/kalmia:release`).

- **Préparation** : une issue est **préparée** par `/kalmia:preparer-issue` (Opus : plan d'implémentation, tests, commandes de vérification, pièges) ou par `/kalmia:planifier` pour les issues qu'il place dans une vague, puis implémentée par `/kalmia:vague` (Sonnet). Étiquette `prête` = toutes les sections du modèle remplies, aucune question ouverte ; `à-préciser` = une décision manque (voir « Questions ouvertes »). `/kalmia:vague` ne lance pas l'implémenteur sur une issue sans `prête`.
- **Tailles** : petite = 1, moyenne = 2, grosse = 4 points, posées en étiquette `taille-1`, `taille-2` ou `taille-4`. Au-delà de 4, scinder l'issue.
- **Budget par vague** : 10 points au départ, ajusté par `/kalmia:planifier`. La valeur courante est notée à **un seul endroit** : la ligne `budget:` des réglages de [`.claude/journal-vagues.md`](.claude/journal-vagues.md). La somme des tailles d'une vague ne dépasse pas le budget (une issue seule plus grosse forme sa propre vague).
- **Estimations calibrées** : ligne `estimations:` des réglages du même journal (ajustements par type d'issue, tenus par `/kalmia:planifier`).
- **Priorité** : `/kalmia:planifier` classe les issues (priorité explicite, issues qui en débloquent d'autres, bugs avant fonctionnalités avant nettoyage, puis numéro) et remplit les vagues dans cet ordre, dans la limite du budget.
- **Fichiers** : des issues qui touchent les mêmes fichiers (section « Fichiers probablement touchés » du modèle) peuvent être dans la même vague ; `/kalmia:vague` les exécute **l'une après l'autre** (chaîne), les autres en parallèle.
- **Interaction humaine** : elle a lieu dans `/kalmia:planifier` (questions, décisions, validation du plan). Une fois les vagues formées, `/kalmia:vague` ne demande rien.
- **Dépendances** : une issue qui dépend d'une autre va dans une vague postérieure à la sienne, et seulement une fois la dépendance **fusionnée** (une PR ouverte ne suffit pas : `/kalmia:vague` ne lance pas l'issue dépendante).
- **Approbation humaine** : [`.claude/approbation-humaine`](.claude/approbation-humaine) liste les fichiers dont la modification exige l'approbation d'une personne avant fusion (source unique : la règle de fusion de ce fichier y renvoie). Les issues qui les touchent portent l'étiquette `approbation-humaine`, passent en fin de vague, et leur attente ne compte pas comme un échec. Les fichiers binaires qu'un implémenteur peut ajouter se déclarent dans [`.claude/binaires-autorises`](.claude/binaires-autorises) ; sinon le contrôle de fin les refuse.
- **Journal** : toute raison de blocage commence par une catégorie (`humain :`, `dépendance :`, `refusée :`, `CI :`, `coupure :`, `externe :`) ; une ligne identique à la dernière de la même issue n'est pas réécrite.
- **Fusion** : seulement si la CI a réussi **et** que le réviseur a approuvé le dernier commit (garde de fusion du plugin).

**Commandes de vérification** (lues par les hooks du plugin, dans ce projet) :
- rapide, avant qu'un implémenteur termine : `{{VERIFICATION}}` — fichier [`.claude/verification-implementeur`](.claude/verification-implementeur) (la variable `VERIFICATION_IMPLEMENTEUR` la remplace) ;
- suite complète, avant un tag de release : `{{TESTS_COMPLETS}}` — fichier [`.claude/tests-complets`](.claude/tests-complets) (la variable `RELEASE_TEST_CMD` la remplace).

Commandes : `/kalmia:preparer-issue <idée | #N> [brouillon]`, `/kalmia:planifier [K] [lecture-seule]` (pose les questions, prépare, forme les vagues), `/kalmia:vague <N | reprise>`, `/kalmia:release <tag> <N…>`. Le journal est commité directement sur `main` par la session qui lance `/kalmia:vague` ou `/kalmia:planifier`, sans PR.
