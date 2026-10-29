# Timeline Edit - implementation et checklist

## Objectif

Ajouter `MajoorTimelineEdit` entre la generation et `MajoorShotAssemble`.
Entrees : `MAJOOR_SHOT_LIST`, document JSON de montage, musique `AUDIO`
optionnelle. Sorties : nouvelle `MAJOOR_SHOT_LIST` et musique inchangee.
Aucune modification du workflow de generation, aucun remplacement des sources,
aucun appel de modele pendant un geste de montage.

## Contrat

- Document versionne, project_id, empreinte des sources/prises et cadence
  rationnelle. Les bornes sont des images entieres, fin exclusive.
- Une occurrence possede un identifiant unique, shot_id, revision_id,
  in_frame et out_frame. Sa place dans le tableau determine son ordre.
- Une piste video sequentielle, sans trous ni superpositions, pour le premier
  lot. Les coupes, suppressions et trims sont ripple.
- La compilation cree des shots derives contigus, avec leur propre identite
  et un lien de provenance vers le shot original. Elle ne reecrit pas le
  manifest de generation et ne copie pas les videos.
- Une prise trop courte est refusee, jamais completee silencieusement.
- Document invalide ou source incompatible : erreur explicite. Aucun reset
  automatique d'un montage enregistre.
- Le JSON du widget est la sauvegarde du montage dans le workflow.
  Undo/redo concerne les commandes de montage; l'historique temporaire n'est
  pas sauvegarde.
- Les fichiers d'apercu et la musique sont adresses par leur contenu.
  Les URLs utilisent le `/view` standard de ComfyUI, sans route de fichier libre.

## Premiere version : montage des medias bruts

L'editeur travaille sur les prises, pas sur l'ancien MP4 final. Il doit annoncer
clairement que les effets du plan automatique (sub-cuts, vitesse, textes,
motion layers) ne sont pas reappliques aux occurrences de montage : leurs
timings ne sont pas valides apres une coupe arbitraire. Les plans sources
conservent leurs effets. Leur adaptation au montage est un lot distinct.

La musique reste fixe a t=0, sans edition de volume/decalage dans ce lot.
La sortie AUDIO inchangee doit etre branchee a `music` de Shot Assemble;
utiliser audio_policy=mute et music_fade=0 pour comparer l'apercu musical.
L'ecoute des voix/SFX des prises et le mixage multipiste sont un lot ulterieur.

## Plan et checklist

### A - Recherche et contrat

- [x] Examiner les prises, les bornes, le stockage et l'assemblage existants.
- [x] Verifier la cible locale : Core v0.43.0, frontend requis 1.57.4.
- [x] Verifier la derniere release officielle : v0.43.0 (2026-10-27).
- [x] Verifier les hooks officiels nodeCreated / afterConfigureGraph.
- [ ] Terminer la comparaison Registry et les regressions frontend connues.

### B - Moteur non destructif

- [x] Document versionne, signature source, validation stricte.
- [x] Compilation vers SHOT_LIST : reorder, cut, duplicate, delete.
- [x] Trim, slip et choix de prise par occurrence.
- [x] Bornes exactes imposees a l'assemblage, meme avec keep_generated.
- [x] Tests : immutabilite, roundtrip, sources incompatibles, prises courtes.
- [x] Test media reel : ordre des images, nombre d'images, audio et cache.

### C - Node et editeur

- [x] Enregistrer le node V3 sans modifier les contrats existants.
- [x] Publier la bibliotheque des prises et la waveform musicale mesuree.
- [x] Bouton ouvrir/fermer, timeline zoomable, curseur, selection.
- [x] Lecture/pause, seek, pas image; musique comme horloge en lecture.
- [x] Trim/slip numeriques, coupe au curseur, duplication, suppression.
- [x] Reorder par drag/drop et boutons; remplacement de prise local.
- [x] Undo/redo, sauvegarde dans le widget, restauration apres rechargement.
- [x] Nettoyage des lecteurs et callbacks a la fermeture.
- [x] Tests frontend et verification navigateur de la synchronisation de base.

### D - UX avancee

- [x] Poignees de trim directes et pas clavier d'une image.
- [ ] Slip par glissement et aimantation aux beats (slip numerique disponible).
- [ ] Proxys video et prechargement pour lecture fluide aux raccords.
- [x] Mesure A/V de base et etat de chargement explicite.
- [ ] Qualification A/V sur medias longs/VFR et prechargement aux raccords.
- [x] Exemple de cablage API portable et aide EN/FR.
- [x] Execution Comfy reelle, sauvegarde/reload/copie, cache au second run.

### E - Generation explicite (pas de bouton factice)

- [ ] Selection du contexte source et du prompt pour Regenerate.
- [ ] Soumission explicite via graphe/queue, progression et annulation.
- [ ] Comparaison et acceptation d'une nouvelle prise sans toucher aux autres.
- [ ] Extension avant/apres : verifier le conditionnement temporel H3.
- [ ] Provenance, cout et gestion d'une prise trop courte.

### F - Evolution

- [ ] Retiming des textes, effets et calques; ancrages clip/timeline/musique.
- [ ] Decalage/volume/trim musique transmis au rendu.
- [ ] Voix et SFX des clips, transitions puis pistes superposees.
- [x] Integration OpenKatana reutilisant le meme contrat de montage.

## Verification attendue

Un montage `1,2,3,4,5` devient `1,4,2,3,5`; couper et dupliquer conserve
des identites distinctes et les memes references de fichiers. Le rendu doit
respecter les in/out a une image pres, sans changer le manifest source.
Un montage sauvegarde puis recharge doit produire le meme rendu et reutiliser
le cache. Une simple edition ne doit soumettre aucun travail de generation.
La waveform doit correspondre aux echantillons AUDIO et non a un dessin fictif.
La lecture navigateur n'est pas qualifiee frame-perfect avant mesure.

## Resultats du premier lot (28 octobre 2026)

- Node enregistre parmi les 32 schemas du pack sur Core 0.43.0.
- Execution reelle sur un serveur Comfy CPU isole, sans redemarrer le serveur
  utilisateur : Load Shot List + Load Project Music + Timeline Edit + Assemble.
  Sortie de 72 images avec musique; second lancement avec nodes mis en cache.
- Rendu de test rouge/bleu : reorder, in/out, duplication, frequences audio
  880/440/880 Hz, source manifest inchange et reutilisation de l'export.
  Conversion de cadence 24 -> 30 testee separement, y compris les inserts
  d'une image : arrondi des frontieres cumulees pour ne pas accumuler la derive.
  Une cadence de sortie trop faible pour representer une coupe est refusee.
- 50 tests backend cibles passent (montage, pipeline, slip et fidelite), ainsi
  que les commandes editoriales JS et les regressions des widgets existants.
- Waveform mesuree : musique, silence, batch/canaux invalides et NaN testes.
  Le cache distingue mono/stereo meme si les octets PCM sont identiques.
- Navigateur Comfy : waveform non vide, lecture/pause, passage des raccords,
  fin de musique avant fin du montage, trim par poignee, undo/redo et
  sauvegarde/rechargement/copie du node verifies.
  Lecture sans musique, drag/drop, coupe au curseur et refus d'un slip hors
  limites verifies aussi. Le workflow API a ete execute sans musique.
- Ecart entre currentTime video et audio observe d'environ 60-71 ms en debut
  de lecture sur ces petites fixtures. Le correcteur resynchronise au-dela
  de 120 ms. Cela ne qualifie pas la sortie sonore materielle et ne remplace
  pas une mesure longue duree; ne pas presenter cet apercu comme frame-perfect.
- Le script general check_schemas.py construit les 32 schemas puis echoue sur
  une assertion preexistante de texte de skill musical, sans rapport avec ce
  node. Le controle dedie check_timeline_edit.py passe.

Le lot E est desormais commence dans le Studio, derriere un drapeau experimental.
Il n'est pas encore valide pour une utilisation de production ou pour le
remplacement d'une occurrence du node Timeline Edit.

## Prototype Studio : candidates IA, avant validation complete

Activation volontaire dans l'environnement du backend OpenKatana :

```powershell
$env:SECATOR_EXPERIMENTAL_AI_EDIT = '1'
```

Le backend doit etre lance avec cet environnement, en mode reel (pas
`SECATOR_MOCK=1`), avec le proxy SDK et les modeles du workflow text disponibles.
Le chemin existant Regenerate n'est pas remplace. Aucun serveur utilisateur
n'a ete redemarre et aucune generation GPU n'a ete lancee pendant ces tests.

### Contrat implemente

- [x] Experimental desactive par defaut.
- [x] Plan source genere uniquement : prise active, non verrouillee.
- [x] Prompt exact de la prise comme point de depart, modifiable independamment.
- [x] Une seule chaine H3 issue du workflow text configure, sans planner,
  plate, retry, ApplyShotMetadata ni assemblage final.
- [x] References image conservees; pose/control Remix, reference video,
  voix et effets de finition volontairement exclus.
- [x] Regenerate produit une nouvelle prise brute de la longueur selectionnee.
- [x] Extend avant/apres : image de raccord fournie au node natif
  MiniMaxH3AddGuide, respectivement a l'image -1 / 0 de la generation.
- [x] Retrait de l'image de guidage du segment ajoute pour ne pas doubler
  l'image de raccord; source conservee, reencodage H264 a cadence constante.
- [x] 0,25 a 10 secondes supplementaires; traitement a 24 images/s.
  Generation arrondie a 5 + 17k images, minimum 124, maximum 362
  (plage entrainee indiquee par le node natif). Le surplus est decoupe,
  jamais remplace par un gel ou une repetition du dernier frame.
- [x] Audio des segments conserve, silence pour une piste absente,
  concat stereo 48 kHz; aucun fondu sonore automatique revendique.
- [x] Apercu candidat distinct, acceptation avec confirmation ou rejet.
- [x] Aucun changement de prise active, de manifest ou d'export avant acceptation.
- [x] Acceptation ajoute une revision compatible et active `keep_generated`,
  avec prompt exact, empreinte et parent; anciennes prises conservees.
- [x] Refus si prise, slip, fenetre source, type de source, fichier source
  ou apercu ont change. Acceptation repetee sans duplication.
- [x] Annulation via le seul handle SDK de cette operation; attend la fin
  du traitement CPU deja commence. Pas de relance GPU automatique.
- [x] Persistance des candidates dans le projet et reprise de leur liste apres
  rechargement; une operation interrompue n'est pas reprise automatiquement.
- [x] Interface EN/FR, erreurs explicites, preview video, boutons accepter/rejeter.

### Limites intentionnelles du test

Le perimetre est le **plan source**, pas une occurrence editoriale. L'acceptation
change sa prise active pour tous ses usages. L'extension actualise les durees
affichees et les positions suivantes sans reecrire les coordonnees de generation.
La source de generation, son schema et son ancien media restent inchanges.

L'export precedent reste disponible mais n'est **pas** mis a jour automatiquement :
utiliser **Style du montage > Remonter** et verifier musique et calques.
`keep_generated` consomme la prise brute complete et ne reapplique pas les
sub-cuts/effets temporels de l'ancien plan. Les calques globaux et la musique
ne sont pas recales automatiquement.

Les documents deja sauvegardes dans le node Timeline Edit ne sont pas rebases
automatiquement lors de l'ajout d'une revision. Leur signature source peut donc
refuser la nouvelle liste. Conserver leur JSON; ne pas le reinitialiser
silencieusement. Le remplacement local d'une occurrence et un rebase explicite
restent une etape ulterieure.

- [ ] Qualifier sur un vrai calcul H3 les trois operations et la continuite
  mouvement/identite/lumiere/son : une image de raccord n'est pas une garantie.
- [ ] Tester VRAM, annulation et proxy sur une generation GPU reelle.
- [ ] Inserer/accepter dans une occurrence independante du montage manuel.
- [ ] Rebase explicite et sans perte d'un document Timeline Edit existant.
- [ ] Recaler musique/calques apres changement de longueur.
- [ ] Valider un export final complet Studio apres acceptation.

### Verification

Les tests backend couvrent la topologie du graphe, les references, l'immutabilite,
les trois operations sur de vrais fichiers FFmpeg, les couleurs/durees/cadences,
les prises obsoletes, acceptation/rejet, annulation, erreurs SDK et persistance.
Le SDK et ses sorties H3 sont simules; le montage et le decodage ne le sont pas.
Les trois prompts ont aussi ete passes au validateur reel du Core 0.43.0 avec
ses chemins de modeles configures, sans execution du modele.

Les tests frontend couvrent le drapeau off, le prompt exact, les deux directions,
les controles verrouilles, confirmation, rejet, erreurs et annulation.
Le build TypeScript/Vite passe.

Verification de ce lot : 65 tests backend cibles et 73 tests frontend passent.
Le lint cible ne signale pas de nouvelle alerte; des avertissements React
preexistants demeurent dans App et ShotPanel.
Navigateur sur serveur de test isole : extension apres (apercu de 2 s),
acceptation avec confirmation, revision ajoutee et plan suivant decale;
extension avant (apercu de 2,5 s), rejet sans changement de la prise active;
liste conservee au rechargement. Les sorties H3 de ce test navigateur sont
des fixtures FFmpeg, pas des generations de modele. Le serveur isole et ses
medias temporaires ont ete nettoyes apres verification.

La suite complete backend contient un echec sans rapport avec ce prototype :
le preset `remix-wild-counterpoint` utilise volontairement `music_volume=1`,
alors que `test_preset_refresh` exige zero pour tous les presets.
Ce preset n'a pas ete modifie dans ce lot.

## Integration Studio : montage manuel

Le panneau Shot garde une seule action Regenerate et un seul prompt editable.
L'ajout IA est limite a Extend avant/apres et une duree, avec les details
experimentaux replies. L'extension reutilise le prompt courant du plan; en
Remix elle ajoute la correction courante au prompt exact de la prise.
La previsualisation/acceptation/rejet de candidate reste explicite, sans
dupliquer l'apercu de la prise source deja visible.

L'onglet **Manual montage / Montage manuel** ouvre exactement le meme editeur
que le node. Les deux modules JS sont servis localement depuis le pack adjacent;
le backend charge seulement son core pur, sans importer Comfy/PyTorch dans
l'environnement du Studio.

### Checklist du lot

- [x] Trim gauche/droite par poignee et numerique, slip numerique.
- [x] Coupe au curseur, deplacement/reordre par drag/drop et boutons.
- [x] Suppression/trim ripple, duplication, remplacement de prise par occurrence.
- [x] Undo/redo, seek, pas image, play/pause et waveform musicale mesuree.
- [x] Sauvegarde serveur separee dans `editor/timeline.json`, sans modifier le
  manifest de generation. Comparaison de version pour refuser les ecrasements.
- [x] Brouillon local recupere a la reouverture; conflit explicite avec
  telechargement JSON et abandon volontaire. Reset soumis a confirmation.
- [x] Activation/desactivation sans perdre le montage. Le style automatique
  refuse de s'appliquer tant que le montage manuel est actif.
- [x] Rebase explicite apres ajout/suppression de prises inutilisees, seulement
  si les medias et bornes de chaque occurrence restent identiques.
- [x] Protection des prises referencees contre le nettoyage des versions.
- [x] Export SDK reel vers Load Shot List -> Timeline Edit -> Shot Assemble ->
  SaveVideo, avec validation de la duree avant remplacement de l'ancien export.
- [x] Presentation distincte du montage exporte et des plans sources; pas de
  correspondance temporelle fictive avec la timeline de generation/comparaison Remix.
- [x] Theme Studio isole : surfaces prune, controles lavande, actions/waveform
  citron, panneau avec icones et badges, erreurs et focus clavier coherents.
  Les controles des candidates IA utilisent aussi les tokens du Studio.
  Le node Comfy garde son apparence par defaut. Verification navigateur de la
  modale sur grand ecran, a 640 px et avec zoom; pas de debordement horizontal
  hors de la piste de montage volontairement scrollable.

### Utilisation et limites

1. Apres generation, ouvrir l'onglet Montage manuel puis Timeline Edit.
2. Monter les occurrences. Les commandes ne soumettent aucun modele.
3. **Sauvegarder le montage** conserve le document sans changer l'ancien MP4.
   **Sauvegarder et exporter** lance uniquement le graphe d'assemblage.
4. Apres un ajout de prise, fermer l'editeur puis utiliser **Rebaser les prises
   inchangees**, rouvrir et choisir la nouvelle prise sur l'occurrence voulue.
   Une prise referencee dont le slip/media a change empeche le rebase.
5. Pour reutiliser les styles automatiques, choisir **Utiliser le montage
   automatique**. Le montage manuel reste sauvegarde, mais l'ancien MP4 ne
   change qu'au prochain export.

Le montage est sequentiel et travaille sur les prises brutes. Ni les effets,
ni les textes, ni les motion layers du montage automatique ne sont reappliques.
La musique conserve sa position a zero : piste retenue, musique source, puis
audio de la video source Remix si aucune piste separee n'existe. Avec musique,
le son des prises est coupe a l'export; sans musique il est conserve.
L'apercu du node garde toujours les prises muettes.

Regenerate/Extend IA restent dans le panneau experimental des **plans sources** :
generer, comparer, accepter, puis rebaser le montage et remplacer explicitement
la prise de l'occurrence. Aucune acceptation automatique d'une candidate IA
sur une occurrence. La qualification artistique H3 reste ouverte.

Le Studio et le pack doivent rester adjacents. Un Comfy deja lance avant
l'ajout du node doit etre redemarre : l'export indique clairement cette exigence
et conserve le montage sauvegarde. Aucun redemarrage utilisateur n'est implicite.

### Verification de l'integration

- Tests backend dedies : contrat partage, waveform reelle, CAS, invalides,
  rebase, manifest intact, purge protegee, routes medias/modules, reprise,
  isolation des lectures, export et refus de remplacer l'ancien MP4 si la
  duree ne correspond pas.
- Tests React : ouverture du module partage, brouillon, sauvegarde/export,
  conflits, erreurs, rebase/desactivation, fermeture et chargement interrompu
  par une operation; presentation separee des sources et du montage exporte.
- Verification finale : 14 tests backend dedies, 22 tests core de montage et
  les commandes JS passent; 82 tests frontend et le build TypeScript/Vite
  passent. Le lint configure oxlint ne rapporte pas de nouvelle alerte sur
  l'adaptateur manuel; des avertissements existants restent dans Preview et
  Timeline. Suite backend complete : 186 passent, 6 skips GPU, l'unique echec
  connu reste le test de volume du preset Wild Counterpoint decrit plus haut.
- SDK/proxy reels et serveur Comfy CPU isole : 48 images bleu/rouge/bleu,
  trims et duplication verifies par pixels, bande musicale 660 Hz distincte
  du son des prises, branche sans musique, cache compiler/assembler au second
  run, manifest byte-identique.
- Navigateur Studio isole : module partage, waveform 1024 points, prises
  decodables, duplication, reordre, undo/redo, slip, sauvegarde et export reel
  de quatre occurrences sur 2,5 s. Le navigateur integre masque cette page :
  sa politique d'economie d'energie interrompt la lecture video en arriere-plan;
  l'erreur est visible. Ce test ne qualifie pas la lecture continue ni la
  synchronisation sonore materielle.

## References verifiees

- https://github.com/Comfy-Org/ComfyUI/releases/tag/v0.43.0
- https://docs.comfy.org/custom-nodes/js/javascript_hooks
- API locale : comfy_api/latest/_io.py et comfy_api/version_list.py.
- Le pack utilise deja comfy_api.latest et exige Core >=0.41.0.
  Cette fonctionnalite doit etre testee sur 0.43.0 avant d'annoncer sa compatibilite.
