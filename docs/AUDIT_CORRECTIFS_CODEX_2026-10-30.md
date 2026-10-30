# Audit technique et plan de correctifs — Majoor VideoTools / HyperKut

**Date :** 2026-10-30  
**Dépôt :** MajoorWaldi/ComfyUI-Majoor-VideoTools  
**Référence auditée :** main @ 03c444e13c2ff46e53ccf4fe0082bb9e2f1a74fb (2026-10-29)  
**Statut :** checklist initiale ; aucune correction de code n'est revendiquée par ce document.  
**Destinataire :** Codex et mainteneurs du projet.

> IMPORTANT — Ceci est un audit statique. L'inspection des sources, des trois JSON de workflow, des tests et de la documentation ne constitue **pas** une exécution de ComfyUI, des tests Pytest, des modèles H3/YuE2 ou d'un rendu réel. Les points sont qualifiés ci-dessous comme **confirmés dans le code**, **risques à reproduire** ou **évolutions recommandées**. Ne pas marquer un item comme corrigé sans preuve et test de non-régression.

## Mission pour Codex

1. Créer des PRs **petites et séparées par problème** (P1 avant P2, P3 seulement après qualification), sans modifier les poids des modèles ni installer des runtimes facultatifs implicitement.
2. Pour chaque ticket : reproduire par un test rouge si possible, corriger le plus localement possible, exécuter les suites ciblées, ajouter un test de régression, renseigner les résultats et cocher uniquement les cases réellement terminées.
3. Conserver les contrats existants des manifests, takes et workflows ; si une migration de schéma est nécessaire, documenter migration, rétrocompatibilité et rollback.
4. Tester les workflows **REMIX / TEXT / MUSIC** et l'app externe **HyperKut Studio** séparément ; ne pas confondre les workflows visuels et les graphes API exportés.
5. Préserver le comportement **non destructif**, le cache, les données locales et les warnings explicites. Ne pas transformer un warning de qualité du modèle en « test réussi ».
6. Tenir à jour les cases cochées, l'identifiant de PR/commit, la commande de test et son résultat dans ce document ou dans la description des PRs.

## Résumé exécutif et périmètre

- Moteur actuel : Scene Detect & Split, Create Timeline, Select Shot, Apply Shot Metadata, manifest de projets et takes, Timeline Edit, Shot Assemble, musique/SFX/dialogue, finishing HyperFrames/Tone optionnel.
- HyperKut Studio est une **application beta distincte** ; les mêmes contrats de médias, timelines et workspaces doivent y être vérifiés.
- Workflows présents : SECATOR Remix (136 nodes / 170 liens au niveau racine), SECATOR Creative Text (152 / 199), SECATOR Creative Music (154 / 202). Les liens principaux référencent des IDs présents ; cette vérification ne valide ni le wiring interne des subgraphs, ni l'exécution avec les modèles.
- Points positifs identifiés : données de shots immuables et manifest validé, vérification de sortie du répertoire projet, FileLock pour certaines opérations, écriture atomique des manifests, exécution FFmpeg sans shell et annulation, édition non destructive, tests de rendu FFmpeg et tests JS/integration préexistants.
- **Objectif :** solidifier l'architecture avant de multiplier les effets et les backends.

### Checklist globale

- [ ] G0 — Revoir les licences des modèles et les usages prévus.
- [ ] G1 — Corriger les collisions d'exports concurrents.
- [ ] G2 — Unifier les chemins média et URLs des workspaces isolés.
- [ ] G3 — Clarifier et valider les politiques audio après montage.
- [ ] G4 — Corriger les bornes des sub-cuts après source offset / slip.
- [ ] G5 — Prouver la reproductibilité des trois parcours modèle et de l'installation.
- [ ] G6 — Corriger le test regex du câblage mathématique et prouver qu'il échoue en cas de rupture.
- [ ] G7 — Rejeter NaN / inf / valeurs non finies dans les paramètres d'effets.
- [ ] G8 — Rendre persistante la provenance des WAV temporaires.
- [ ] G9 — Réconcilier force_refresh et le manifest persistant.
- [ ] G10 — Qualifier VFR, PTS, rotation et conversions de résolution.
- [ ] G11 — Vérifier la parité preview/export et les cycles de vie du player.
- [ ] G12 — Durcir les caches et sidecars (score, delivery, export) sous concurrence.
- [ ] G13 — Séparer les profils de livraison social / master VFX.
- [ ] G14 — Unifier la structure éditoriale pour Remix/Text/Music (RFC).
- [ ] G15 — Ajouter des tests de fidélité éditoriale et de continuité narrative.
- [ ] G16 — Qualification sécurité/permissions du fonctionnement distant et des références utilisateurs.
- [ ] G17 — Documenter le statut beta, les limites, les résultats de tests et les décisions go/no-go.

---

## P0 — Gate juridique et distribution

### G0 — Licences H3, YuE2, GSAP et assets (gate de diffusion, pas bug Python)

**Constat :** LICENSES.md distingue correctement le code MIT des termes des poids et dépendances. Selon cette documentation, l'utilisation locale des poids H3 fait l'objet de restrictions territoriales et YuE2 impose des conditions distinctes pour les personnes et les entreprises. Il faut **vérifier les licences officielles et l'autorisation exacte applicable** à la date de publication ; ce document n'est pas un avis juridique.

**Fichiers :** LICENSES.md, docs/models-and-downloads.md, THIRD_PARTY_NOTICES.md, docs/submission-readiness.md, documentation de HyperKut Studio.

**Correction / action :**
- [ ] Établir un inventaire par modèle, quantization, provider, révision, territoire, mode d'utilisation personnel/commercial.
- [ ] Vérifier auprès des sources officielles les termes H3, YuE2, GSAP et des composants redistribués (incluant les restrictions territoriales et d'hébergement) ; joindre dates/URLs.
- [ ] Marquer les workflows/licences incompatibles avec une distribution visée et définir les options licites : autorisation spécifique, backend alternatif ou restriction de disponibilité.
- [ ] Séparer la sélection du backend vidéo/musique du noyau éditorial ; ne jamais faire croire que le code MIT autorise les poids.
- [ ] Contrôler les droits des vidéos, musiques, voix, visages, polices et assets des démos.

**Acceptation :** registre de conformité revu, conditions d'exploitation documentées, aucune assertion de droits non vérifiée, décision formelle go/no-go.

---

## P1 — Correctifs de robustesse prioritaires

### G1 — Collision d'exports FFmpeg sur deux workers

**Type :** risque confirmé à la lecture du code ; reproduction concurrente encore à effectuer.  
**Preuve :** core/assembler.py — assemble_shots, bloc plan_key/out/partial/FFmpeg/rename (environ L619-L679). Plusieurs exécutions identiques ciblent le même export, le même .partial et le même script filtre ; aucun lock ne couvre le cycle complet.

**Impact :** deux workers avec stockage partagé peuvent effacer/écrire le même fichier intermédiaire ou modifier les logs ; échec, résultat incomplet ou course de cache.

**Correction :**
- [ ] Poser un verrou **par clé canonique d'export** autour de cache-check → encode → probe/QA → normalisation → commit final → sidecars ; verrou accessible à tous les processes/instances du même stockage.
- [ ] Générer les fichiers de travail uniques (UUID/PID) **dans le même dossier/volume** pour garantir un rename atomique ; ne plus supprimer le .partial d'un autre worker.
- [ ] Vérifier le rendu existant après acquisition du lock ; rendre la reprise idempotente et le nettoyage limité aux fichiers détenus par le worker courant.
- [ ] Éviter l'écriture concurrente du même filter script / optional-audio.json / score / delivery JSON.
- [ ] Définir et tester timeout, annulation et comportement du lock sur Windows/SMB.

**Tests :**
- [ ] Deux processes demandent simultanément exactement la même clé → un seul encodage effectif, mêmes octets finaux ou même export vérifié, aucun .partial orphelin.
- [ ] Deux clés différentes → travail parallèle possible sans collision.
- [ ] Interruption d'un encodeur → le second peut terminer, export final toujours valide.
- [ ] Réexécution → cache réutilisé et sidecars cohérents.

### G2 — Racines de workspace et URLs des previews

**Type :** incohérence de chemins vérifiée ; scénarios utilisateurs à reproduire.  
**Preuve :** adapters/comfy_video.py:projects_root accepte _hyperkut_workspaces/<worker>/projects ; nodes/preview.py:shots_payload, nodes/timeline_edit.py:editor_payload et nodes/shot_assemble.py reconstituent des chemins fixes via OUTPUT_SUBFOLDER / MajoorVideoTools/<project_id>.

**Impact :** clips, thumbs, dialogues, music preview ou export invisibles lorsque le projet n'est plus dans le dossier historique.

**Correction :**
- [ ] Introduire une seule couche de media locator : (storage_root, project_id, relative_path) → URI de média valide pour l'API ComfyUI, avec contrôle strict de l'ancrage au répertoire output.
- [ ] Construire les payloads depuis la localisation réelle, pas depuis la constante historique ; contrôler la visibilité et la confidentialité des workspaces.
- [ ] Migrer shots_payload, editor_payload, Shot Assemble preview, lecteurs JS et tout autre producteur de /view.
- [ ] Prévoir explicitement l'accès local, multi-worker sur stockage partagé et cas **remote artifact transfer non pris en charge** plutôt que fournir une fausse URL.
- [ ] Aucun chemin absolu du serveur ne doit être divulgué dans les URLs de navigateur.

**Tests :**
- [ ] Projet historique output/MajoorVideoTools/p_<id> et projet isolé output/_hyperkut_workspaces/<id>/projects/p_<id>.
- [ ] Thumbnails, source, tous les takes, onde sonore, dialogue, export Final et Compare Video sont chargés par le player.
- [ ] Path traversal (../, symlink, URL encodée), mauvais workspace et autres projets rejetés.

### G3 — Politique audio lors des opérations éditoriales

**Type :** comportement confirmé mais à expliciter ; pas forcément un bug selon le mode choisi.  
**Preuve :** core/assembler.py:_filter_graph ; source_master prend le flux audio continu de la source et le coupe/pad à la durée finale, même après reorder des clips. Le code émet un warning. shot_audio et dialogue indépendant sont d'autres modes.

**Impact :** une timeline C–A–B peut afficher les images C–A–B et produire le son A–B–C lorsque source_master est choisi. Correct pour une musique verrouillée ; faux pour du son synchrone.

**Correction :**
- [ ] Définir les contrats explicites Music Locked, Audio Follows Picture et Independent Dialogue (et leurs combinaisons), avec mapping clair des réglages existants.
- [ ] Implémenter ou documenter distinctement le véritable audio « follow source windows » : clip id, media ref, in/out, slip, duplications, trims, silence par défaut, canaux.
- [ ] Clarifier la priorité voice_shots / replace_source_audio / audio_policy / preserve_dialogue / audio input ; avertissement non ambigu dans UI.
- [ ] Respecter durée, fades, phase musicale, ducking et loudness sans tronquer silencieusement une phrase.
- [ ] Ne pas changer silencieusement l'ancienne sémantique de source_master ; migration/config explicite si nouvelle politique.

**Tests :**
- [ ] Source vidéo rouge/bleue avec audio 440/880 Hz ; ordre C–A–B, duplication, slip et trim → fréquence associée à chaque segment quand Follow Picture.
- [ ] Source Master continue après réordonnancement, mais libellé et warning corrects.
- [ ] Dialogue plus long que vidéo → erreur explicite.
- [ ] Music Locked → musique inchangée au montage et export conforme.

### G4 — Limites des fenêtres de sub-cuts avec source offset

**Type :** risque calculatoire confirmé par lecture ; reproduire avec médias synthétiques.  
**Preuve :** core/assembler.py:_plan transmet la durée totale generated.duration à _fx_segments et passe séparément source_offset ; _fx_segments borne les offsets de sub-cuts par actual sans soustraire systématiquement la portion initialement consommée.

**Impact :** take de 5 s glissé à +2 s ne possède que 3 s disponibles ; des sous-coupes peuvent être bornées à tort puis lire hors de l'intervalle, produire un gel ou réutiliser un mauvais passage.

**Correction :**
- [ ] Utiliser un modèle de fenêtres **[available_start, available_end)** en temps rationnel / frames, unique pour timeline, previews et assembleur.
- [ ] Calculer remaining_duration = file_duration - source_start avant toute découpe et tout speed mapping.
- [ ] Appliquer les limites également aux layers self, overlay, split et aux speed ramps.
- [ ] Définir la politique de dépassement : erreur explicite, ou padding uniquement s'il est demandé et documenté.
- [ ] Éviter les accumulations de floats pour des séquences fractionnelles 24000/1001 ou 30000/1001.

**Tests :**
- [ ] Source bicolore/tonalités de 5 s, slip 2 s puis sub-cuts [1s, 1s, 1s] : aucune lecture après 5 s.
- [ ] Fenêtre qui demanderait 4 s restants : erreur contrôlée plutôt que succès silencieux.
- [ ] Layers composites et source_offset testés séparément.
- [ ] FPS 24 / 25 / 29.97 ; montage final en frames exacts.

### G5 — Qualification d'installation et de générations modèle

**Type :** gate de release ; documentation indique elle-même que le clean install n'est pas qualifié.  
**Preuve :** README.md, ROADMAP.md, docs/submission-readiness.md, tests/integration/test_workflows.py et docs/models-and-downloads.md.

**Correction :**
- [ ] Pinner versions ComfyUI, custom nodes, chemins/SHAs des checkpoints et révisions de graphes API.
- [ ] Vérifier qu'une installation Windows propre fonctionne avec Python ComfyUI, FFmpeg/ffprobe, nodes requis, permissions et espace disque.
- [ ] Tester séparément Remix, Text, Music sur assets autorisés ; définir les modèles acceptés sans téléchargement implicite.
- [ ] Vérifier le mode sans son, vidéo avec son, refs 1 à 5, plusieurs takes, rerender d'un shot, cancel et reprise.
- [ ] Vérifier les exports UI et les exports API de HyperKut Studio ; ce sont deux chemins distincts.
- [ ] Ne pas revendiquer un benchmark GPU, la fidélité identité ou la continuité sans mesures et exemples autorisés.

**Acceptation :** matrice environnement/versions/commandes/logs, clips QC, tests reproductibles et limites de plateforme explicites.

---

## P2 — Correctifs de tests, validation et diagnostics

### G6 — Regex invalide dans le test de math wiring

**Type :** défaut vérifié du fichier de test.  
**Preuve :** tests/integration/test_workflows.py:test_every_variable_of_a_math_expression_is_wired contient des octets backspace (0x08) autour de [a-z] au lieu du délimiteur regex \b.

**Correction :**
- [ ] Remplacer les caractères de contrôle par la vraie regex brute r"\b[a-z]\b".
- [ ] Tester le fonctionnement sur une expression connue, et pas seulement sur les JSON existants.
- [ ] Ajouter un mutation test : retirer un câble d'une variable utilisée doit faire échouer le test.
- [ ] Auditer les autres caractères de contrôle accidentels dans les tests et textes source.

**Acceptation :** test rouge lors d'une suppression volontaire de lien, vert sur workflow intact.

### G7 — Paramètres d'effet non finis

**Type :** défaut de validation vérifié.  
**Preuve :** core/fx.py:_number convertit en float et compare aux bornes, mais ne teste pas explicitement math.isfinite.

**Correction :**
- [ ] Rejeter NaN, +inf, -inf, bool et types incompatibles avant la logique de clamp.
- [ ] Préserver le clamp existant pour nombres finis hors bornes lorsque c'est le contrat voulu.
- [ ] Vérifier speed, zoom, focus, start, transition, text, opacity et positions transitives.
- [ ] Émettre un message indiquant champ, shot et cause au lieu d'envoyer NaN à FFmpeg.

**Tests :** paramétrer toutes les entrées numériques pertinentes en NaN/inf, valeurs normales et bornes.

### G8 — Chemins WAV temporaires dans les rapports

**Type :** traçabilité invalide dans certaines exécutions.  
**Preuve :** nodes/create_timeline.py:audio_file crée/supprime un WAV temporaire ; core/assembler.py:delivery_timeline utilise str(opts.music) comme audio_source.

**Correction :**
- [ ] Remplacer la provenance volatile par des champs durables (asset id, sha256, durée, sample rate, provenance/rights, éventuel chemin persistant projet).
- [ ] Conserver les assets requis à la reprise ou établir une politique explicite de nettoyage/refetch.
- [ ] Ne pas stocker un chemin temporaire supprimé comme identité définitive du média.
- [ ] Versionner le schéma des sidecars et migrer proprement les anciens rapports.

**Tests :** après la fin du context manager et après relance de ComfyUI, les métadonnées identifient toujours le même asset.

### G9 — force_refresh et manifeste de shots existant

**Type :** divergence possible du disque et de l'objet retourné.  
**Preuve :** core/scene_detection.py:detect_scenes peut recalculer les cuts tandis que persist_manifest(... only_if_absent=True) garde un manifest.json déjà présent.

**Correction :**
- [ ] Calculer une signature des frontières/PTS/paramètres et comparer explicitement le nouvel état au manifest.
- [ ] Si identique : retourner le manifest courant avec ses takes, sans effacer les révisions.
- [ ] Si différent : créer une nouvelle révision/identité de collection ou lancer une migration explicite des takes, jamais une réconciliation implicite risquant de mal assigner SHOT_003.
- [ ] Rendre force_refresh idempotent et décrire son action sur les caches et thumbnails.
- [ ] Ajouter diagnostic clair si le même project_id référence des découpages incompatibles.

**Tests :** simulateur de nouvelles boundaries sous même source/détecteur, manifests persistés et reload.

### G10 — VFR, timestamps, rotation, audio offset et format image

**Type :** limitation explicitement non qualifiée, pas un bug universel.  
**Preuve :** README.md / ROADMAP.md, core/media_probe.py, core/timeline.py, core/assembler.py.

**Correction :**
- [ ] Constituer fixtures CFR 24/25/30, 24000/1001, VFR, 90/270° metadata, B-frames, sources audio-first, sans son, pistes multiples.
- [ ] Définir une timebase canonique (Fraction) pour le planning, synchroniser PTS/durée/framerate au rendu et à la preview.
- [ ] Comparer l'orientation affichée en entrée et sortie ; expliciter quand on bake la rotation.
- [ ] Vérifier dimensions paires, aspect ratio, padding, pixel aspect ratio, transfert colorimétrique et métadonnées.
- [ ] Ne pas considérer ±2 frames de tolérance de durée comme preuve d'une exactitude frame-accurate.

**Acceptation :** rapport image, audio, PTS et nombre de frames pour chaque fixture.

### G11 — Preview/export : cohérence et lifecycle

**Type :** qualité non entièrement qualifiée.  
**Preuve :** web/timeline_edit_panel.js et web/majoor_timeline_edit.js ; README signale que les previews peuvent s'interrompre aux changements de source.

**Correction :**
- [ ] Comparer preview et rendu sur trim, cut, slip, duplicate, reorder, take change, audio/dialogue et frontières.
- [ ] Garantir le seek à frame entière et un comportement correct pour autoplay bloqué, buffering, end-of-media, abort, undo/redo.
- [ ] Tester ouverture/fermeture répétées, suppression de node et changement de graph ; pas de listeners, lecteurs ou object URLs orphelins.
- [ ] Rendre l'état « preview approximative / export autoritatif » visible lorsqu'un effet n'est pas simulé dans le player.
- [ ] Vérifier le même montage via interface ComfyUI et adapter HyperKut Studio.

### G12 — Intégrité des sidecars et des caches

**Type :** durcissement recommandé ; découle notamment de G1 et G8.  
**Fichiers :** core/assembler.py, core/motion_score.py, core/delivery_review.py, core/hyperframes.py, core/fingerprints.py.

**Correction :**
- [ ] Inclure dépendances réelles dans chaque cache key (sources, versions, scripts, options, audio, masques, presets, overlays).
- [ ] Écrire sidecars et outputs via transaction/rename atomique sous lock ; indiquer version, source fingerprint, export fingerprint, build ID.
- [ ] Cache hit uniquement après probe du média et validation de version des sidecars ; reconstruire proprement les sidecars manquants/obsolètes.
- [ ] Documenter invalidation des caches, nettoyage des orphelins et limite d'espace disque.
- [ ] Vérifier que les chemins absolus temporaires ne deviennent pas des clés ou preuves de provenance durables.

**Tests :** cache hit, modif d'asset sans changement de nom, kill au milieu de l'export, concurrent write.

### G16 — Sécurité des workflows locaux et d'un usage distant

**Type :** gate pour déploiement multi-utilisateur / public ; l'app est actuellement documentée comme locale et single-user.  
**Preuve :** docs/submission-readiness.md, ROADMAP.md ; core/paths.py met déjà en place un confinement utile.

**Correction :**
- [ ] Distinguer ComfyUI local, deux workers sur partage commun et serveur accessible à d'autres utilisateurs.
- [ ] Auditer les routes aiohttp (/majoor/*), workspace IDs, autorisations d'accès aux médias, SSRF, symlinks et chemins encodés avant tout hébergement exposé.
- [ ] Ajouter authentification/autorisation, quotas GPU/disque, isolation et nettoyage des workspaces si déploiement multi-user envisagé.
- [ ] Conserver subprocess shell=False et interdire injection de filtre/argument arbitraire depuis les champs JSON.
- [ ] Tester les entrées malformées, fichiers volumineux, annulation, temps limites et ressources non bornées.

**Acceptation :** threat model et tests de refus ; pas de promesse d'hébergement public avant qualification.

---

## P3 — Evolution du moteur vers une chaîne éditoriale haut de gamme

### G13 — Profils de rendu et color management

**Type :** fonctionnalité à concevoir, pas un bug du profil social existant.  
**Preuve :** core/assembler.py normalise la vidéo en yuv420p puis produit libx264 / CRF 18 ; OPTIONS exposes h264/MP4/MOV.

**Correction :**
- [ ] Conserver un profil « social » stable et ajouter profil master VFX explicite, sans modifier les sorties historiques.
- [ ] Étudier ProRes/DNxHR, 10-bit 4:2:2, 4:4:4/alpha selon containers/codecs disponibles, image sequences si pertinent.
- [ ] Définir color space, range, transfer, primaries et éventuel workflow OCIO sans conversions implicites.
- [ ] Ajouter tests de round-trip de niveaux, gamut, alpha, taille et métadonnées.
- [ ] Définir l'upscale 4K comme étape versionnée, optionnelle, évaluée visuellement.

### G14 — RFC : Editorial Decision Graph canonique

**Type :** proposition d'architecture pour éviter la divergence des contrats.  
**Fichiers concernés :** core/models.py, core/timeline_edit.py, core/assembler.py, core/motion_score.py, frontend et Studio adapter.

**Correction :**
- [ ] Rédiger une RFC et un schéma versionné de composition : clip occurrence ID, shot/take ID, sources, fractions/frame positions, vidéo, audio bus, FX, layers, transitions, flags de génération, provenance.
- [ ] Créer un **compilateur unique** depuis le projet vers le graph éditorial, puis des renderers/preview consumers ; éviter trois interprétations indépendantes du timing.
- [ ] Distinguer opérations non génératives (cut/trim/slip/effect/audio) et génératives (new take, semantic replacement).
- [ ] Définir determinism, hashing, incremental rebuild et backward-compatible import des manifests existants.
- [ ] Versionner l'interface ComfyUI et l'interface HyperKut indépendamment du backend H3.

**Acceptation :** démonstrateur identique rendu depuis l'éditeur manuel et depuis un workflow automatique, sans régénération inutile.

### G15 — Fidélité Katana-like et continuité narrative

**Type :** R&D, non démontrable par tests unitaires seuls.

**Correction :**
- [ ] Définir benchmark autorisé de vidéos de 5–15 s : cuts, transitions, silence, speed ramps, structure, sujet/action changés.
- [ ] Mesurer erreur de coupe en frames, durée, couverture des effets, synchronisation musicale, nombre de segments et cohérence source→sortie.
- [ ] Développer une représentation explicite des **constraints** : locked structure, constrained subjects/actions, open creative details.
- [ ] Ajouter shot-to-shot continuity state (personnage, tenue, position, décors, lumière, vecteur de mouvement, mouvement caméra) et review humaine.
- [ ] Conserver provenance et seed par shot ; retake d'un seul shot sans reconstruction du reste.
- [ ] Prévoir un bouton QC/approval sans inventer de score sémantique fiable à partir d'heuristiques basiques.
- [ ] Évaluer visuellement texte/typo, temporalité des effets, match musique et poses avant d'affirmer équivalence Katana.

### G17 — Release readiness et documentation

**Correction :**
- [ ] Mise à jour README, ROADMAP, CHANGELOG et docs/submission-readiness.md à partir de résultats observables.
- [ ] Documenter limites de résolution, GPU/RAM effectivement mesurées, performances, dépendances, licences et modules expérimentaux.
- [ ] Maintenir une table des tests exécutés et non exécutés, versions et statut beta.
- [ ] Publier les trois exemples minimaux sur médias autorisés, avec audit des droits.
- [ ] Ne pas confondre conformité du schéma, reproduction visuelle et validation qualité éditoriale.

---

## Matrice d'acceptation end-to-end

| Cas | Entrée | Attendu | Statut |
|---|---|---|---|
| E2E-01 | Remix 15 s / référence 5 shots | Ordre, nombre de frames, audio mode, export vérifiés | [ ] |
| E2E-02 | Text 15 s / 5 images | Plan, références, génération et montage reproductibles | [ ] |
| E2E-03 | Music 15 s / WAV, BPM détecté | Coupes/accents explicitement vérifiés, pas de BPM inventé | [ ] |
| E2E-04 | Source sans audio | Aucun crash, bus de sortie explicite | [ ] |
| E2E-05 | Source avec dialogue, reorder | Comportement conforme à la politique choisie | [ ] |
| E2E-06 | Timeline cut/trim/slip/dup/reorder | Manifest source intact, résultat frame-accurate | [ ] |
| E2E-07 | Regenerate SHOT_003 seul | Les 19 autres shots ne rerun pas | [ ] |
| E2E-08 | Workers 8188/8189 même export | Aucun conflit filesystem, cache correct | [ ] |
| E2E-09 | Worker isolé + preview navigateur | URLs résolues et cloisonnées | [ ] |
| E2E-10 | VFR + rotation | Durées, orientation, A/V sync cohérentes | [ ] |
| E2E-11 | Annulation pendant FFmpeg | Pas d'export final corrompu, reprise saine | [ ] |
| E2E-12 | HyperFrames désactivé / indisponible | Pas de téléchargement silencieux, fallback explicite | [ ] |
| E2E-13 | Fichier audio temporaire détruit | Rapport conserve une provenance valide | [ ] |
| E2E-14 | Nouvelle révision d'une source | Cache invalidé ou projet migré explicitement | [ ] |
| E2E-15 | Licence / assets | Usage et redistribution autorisés documentés | [ ] |

### Commandes initiales de test

~~~bash
python -m pytest tests/integration -q
python -m pytest tests/comfy -q
node --test tests/web/*.mjs
~~~

**Attention :** adapter les commandes à l'environnement ComfyUI qui expose les dépendances réelles ; les scripts tests/comfy/check_*.py peuvent être des scripts d'intégration plutôt que des tests Pytest autonomes. Vérifier leur mode d'invocation avant de considérer une suite « verte ». Pour chaque E2E, relever versions Python/Torch/ComfyUI/FFmpeg, commit, modèle/checkpoint, seed, logs, vidéo finale et rapport QC.

## Ordre d'exécution recommandé

1. **Lot A (priorité opérationnelle)** : G1 + G2 + G4 + G6 + G7. Tests rouges avant correctifs, PRs indépendantes.
2. **Lot B (timeline/audio)** : G3 + G8 + G9 + G12. Priorité à cohérence d'export et à persistance.
3. **Lot C (qualification)** : G5 + G10 + G11 + G16 + G0. Corriger les blocages réels relevés par E2E.
4. **Lot D (roadmap)** : G13 + G14 + G15 + G17. Commencer par RFC et benchmark avant grandes refontes.

### Définition de Done commune

Un ticket est terminé seulement si :
- [ ] comportement problématique reproduit ou risque clairement caractérisé ;
- [ ] correction petite, isolée et expliquée ;
- [ ] tests de non-régression ajoutés, exécutés et résultats consignés ;
- [ ] aucune régression des manifests, takes, caches et anciens workflows ;
- [ ] comportement Windows/shared workspace testé lorsque pertinent ;
- [ ] liens commits/PR, logs, captures ou médias de preuve ajoutés ;
- [ ] documentation/migrations/limitations mises à jour.

## Prompt de démarrage à donner à Codex

> Travaille sur MajoorWaldi/ComfyUI-Majoor-VideoTools en lisant docs/AUDIT_CORRECTIFS_CODEX_2026-10-30.md. Démarre uniquement avec le lot A (G1/G2/G4/G6/G7). Revalide chaque constat sur HEAD, écris d'abord les tests qui reproduisent le défaut, applique des correctifs minimalistes en conservant les manifests, l'API ComfyUI v3 et les workflows existants. Exécute les suites appropriées et rapporte séparément PASS, FAIL, SKIP, NOT RUN. Ne coche une case que si la validation correspondante a réellement été exécutée. Ouvre une PR par sujet ou un ensemble strictement atomique. N'installe pas de modèles/runtimes facultatifs, ne revendique pas de droit de licence, ne change pas la qualité artistique ou les backends vidéo sans demande explicite.

## Liens de référence internes

- core/assembler.py, core/paths.py, core/timeline_edit.py, core/scene_detection.py, core/revisions.py
- adapters/comfy_video.py, adapters/ffmpeg.py
- nodes/preview.py, nodes/timeline_edit.py, nodes/shot_assemble.py
- web/timeline_edit_panel.js, web/majoor_timeline_edit.js, web/timeline_edit_logic.js
- tests/integration/test_workflows.py, tests/integration/test_pipeline.py, tests/integration/test_timeline_edit.py, tests/integration/test_take_trim.py
- README.md, ROADMAP.md, CHANGELOG.md, LICENSES.md, docs/submission-readiness.md

**Fin du document : aucun item n'a été coché artificiellement.**
