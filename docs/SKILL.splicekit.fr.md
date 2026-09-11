---
name: fcp-live
description: Piloter Final Cut Pro en direct depuis Claude (via le MCP SpliceKit) pour monter les vidéos créées ensemble, poser le motion design et les textes dans la charte d'un projet (baair.solutions en premier), et ajouter un voice-over ElevenLabs. Utiliser dès qu'Alexandre dit « monte cette vidéo », « mets-la dans Final Cut », « fais le montage », « ajoute les textes / le motion design », « reel baair », « habille cette vidéo Higgsfield/Kling », « voice-over », « sous-titres dans FCP », ou mentionne Final Cut, FCP, SpliceKit, timeline, titres, brandkit vidéo. L'export final reste à la main d'Alexandre.
---

# fcp-live — montage Final Cut Pro piloté par Claude

## Ce que fait ce skill
1. **Montage** d'une vidéo générée (Higgsfield, Kling, HeyGen…) ou tournée : import, mise en timeline, coupes, rythme.
2. **Motion design / textes** : titres, étiquettes, hooks, CTA, posés en clips connectés et stylés selon le **brand kit du projet** (`brandkits/<projet>.json`).
3. **Transfert de charte** : le même brief donne un reel baair (Fraunces + carré violet + angles droits) ou le reel d'un autre projet, sans retoucher le workflow.
4. **Voice-over** ElevenLabs quand le brief le demande.
5. **Export : jamais automatisé.** Claude prépare tout ; Alexandre exporte (Fichier > Partager).

## Prérequis (état au 2026-09-03)
- FCP patché SpliceKit : `~/Applications/SpliceKit/Final Cut Pro.app` (copie de FCP 12.3, FCP App Store intact).
- Sources SpliceKit : `~/.local/share/splicekit/SpliceKit` (v3.3.9 + 3 correctifs locaux, voir § Maintenance).
- MCP `splicekit` enregistré en scope user dans Claude Code (221 outils). Le pont écoute sur `127.0.0.1:9876` **seulement quand la copie patchée tourne**.
- Télémétrie Sentry **désactivée** via `~/Library/Application Support/SpliceKit/SpliceKitSentryConfig.plist`.
- Client de secours sans MCP : `scripts/skbridge.py METHOD '{json}'` (même protocole JSON-RPC).
- Polices baair installées dans `~/Library/Fonts` le 2026-09-03 (Google Fonts, OFL, variables) : Fraunces, Instrument Serif, Inter, JetBrains Mono.

## Règles de sécurité
- **Une seule instance de FCP** : fermer le FCP standard (AppleScript `quit`, jamais `kill`) avant de lancer la copie patchée.
- **Bibliothèque de travail** : tester dans `Perso` (événement `SpliceKit Test`). Ne toucher `Baair_FCP` que sur demande explicite et sur le projet nommé.
- Avant toute action destructive (delete, replaceWithGap, bladeAll, batch), lister la timeline (`get_timeline_clips`) et annoncer ce qui va changer. `Cmd+Z` existe : `history_action("undo")`.
- Un dialogue macOS de permission (accès Téléchargements, micro…) **bloque le pont** : ne jamais cliquer à la place d'Alexandre, lui demander d'autoriser.
- Ne jamais lancer `share_project`/`batch_export` sans demande explicite.

## Workflow standard (reel 9:16)
1. **Brief** : projet (brand kit), vidéo source, message (hook, 2–4 lignes, CTA), durée cible, voice-over oui/non.
2. **Pont** : `bridge_status()`. Si erreur, ouvrir la copie patchée (`open ~/Applications/SpliceKit/Final\ Cut\ Pro.app`) et attendre le port 9876 (~30 s). Vérifier `dialog.detect` / `detect_dialog()`.
3. **Projet** : écrire un `spec.json` (voir `scripts/build_fcpxml.py`) → `python3 scripts/build_fcpxml.py spec.json > reel.fcpxml` → `import_fcpxml(xml, internal=True)`. Le projet arrive dans la bibliothèque active, événement nommé dans le spec. Puis `open_project(name)`.
   - Alternative pour un projet existant : `import_media(paths, event=…)` puis `browser_append_clip(name=…)`.
4. **Montage** : `get_timeline_clips()` → coupes `blade_at_times`, `timeline_action("delete")`, `trim_clips_to_beats` si musique, `apply_transition` avec parcimonie (charte baair : coupes franches, fondus 6–8 images maxi).
5. **Textes / motion design** : titres = clips connectés (lane 1) générés par `build_fcpxml.py` avec `role` (title / signature / body / label) et `color` du brand kit ; `size` et `position` en pixels du cadre depuis le centre, y vers le haut (`"0 620"` = hook en haut, `"0 -560"` = bas ; zones sûres au § Brand kit). Titres simultanés : lanes attribuées automatiquement. Pour retoucher : `select_clip_in_lane(1)` → `set_inspector_property("positionY", …)`, `get_title_text()` pour vérifier police/taille.
6. **Vérification visuelle obligatoire** : `seek_to_time` sur chaque titre → `capture_viewer()` → lire le PNG. Contrôler : police réellement chargée, débordement, contraste, un seul carré violet.
7. **Voice-over / musique** (optionnel) : générer l'audio (ElevenLabs `generate_tts` écrit dans `~/Movies/ElevenLabs` ; n'importe quel TTS ou un `say` de secours convient), puis le déclarer dans la liste `"audio"` du spec (`start`, `role`, `volume_db`) et mettre `"volume_db": -12` sur les clips dont le son doit passer sous la voix. `build_fcpxml.py` le connecte en lane −1 avec `<adjust-volume>` ; vérifié sur FCP 12.3 (l'export confirme les −12 dB). Sur un projet déjà ouvert : `import_media(path)` + `browser_append_clip` + `timeline_action("connectToPrimaryStoryline")` et `mixer_set_volume`.
8. **Sous-titres** si demandés : `generate_captions` (style via `set_caption_style`, police du brand kit) ou `import_srt_as_markers`.
9. **Livraison** : résumé de la timeline (`analyze_timeline`), captures, et rappel : « prêt à exporter ».

## Brand kit → FCP (valeurs calibrées le 2026-09-03, FCP 12.3, projet 1080×1920)
- Fichier : `brandkits/<id>.json` (couleurs hex + valeurs FCP « r g b a », polices par rôle, règles, formats vidéo, style de motion).
- baair : `ink #0A0A0A`, `ink_paper #FAFAF7`, `purple #8C57E9` (le seul accent, carré, jamais arrondi), Fraunces 700/900 titres, Instrument Serif italique mot-signature, Inter corps, JetBrains Mono étiquettes uppercase.
- Nouveau projet : dupliquer `baair.json`, changer id/couleurs/polices ; le reste du workflow ne bouge pas.
- **Titres = « Basic Title » + `<text-style>`** : les polices installées dans `~/Library/Fonts` sont bien chargées (Fraunces Bold, Instrument Serif Italic, Inter, JetBrains Mono vérifiés au viewer).
- **Échelle Motion = 2× les pixels du cadre** : `build_fcpxml.py` reçoit `size` et `position` en pixels du cadre et divise par `template_scale` (2.0). Mesuré : position « 0 800 » tombe ~740 px au-dessus du centre, « 0 −800 » ~700 px en dessous ; taille 96 px ≈ 97 px rendus.
- **Titres simultanés → lanes distinctes** (auto dans le script). Deux titres dans la même lane au même instant : FCP n'en rend qu'un, sans erreur.
- **Runs** : une ligne peut mélanger les styles (`"runs": [{"text":"Tools, ","role":"title"},{"text":"not decks.","role":"signature"}]`).
- **Carré violet** : titre « ■ » (U+25A0) en `purple`, taille 56 px, placé 140 px au-dessus du hook. Vérifié.
- Zones sûres reel : hook à y ≈ +620 (sous la barre d'état), corps/étiquette à y ≈ −560/−680 (au-dessus de l'UI Instagram). Ne rien poser sous −760.
- Clé FCPXML de position pour Basic Title : `9999/999166631/999166633/1/100/101` (Transform > Position). La clé « Content Position » `9999/10003/1/100/101` du moteur de sous-titres SpliceKit vient d'un autre template et est ignorée ici.
- Projets de test présents dans Perso › « SpliceKit Test » : Test Reel baair, Calib baair, Calib2 baair, Demo baair (supprimables).

## Maintenance SpliceKit
- Après une mise à jour de FCP par l'App Store : `cd ~/.local/share/splicekit/SpliceKit && ./patcher/patch_fcp.sh` (recopie + rebuild + injection + signature). Compte ~7 Go et 3–5 min.
- Rebuild seul : `./patcher/patch_fcp.sh --no-copy`. Désinstaller : `--uninstall` (supprime `~/Applications/SpliceKit`).
- Correctifs locaux appliqués sur v3.3.9 (à réappliquer si `git pull`) :
  1. `Sources/SpliceKitBRAW.mm` : stubs `SpliceKit_bootstrapBRAWAtLaunchPhase` et `SpliceKit_handleBRAWAVProbe` dans la branche sans SDK Blackmagic.
  2. `patcher/patch_fcp.sh` : build via `make all` (la ligne clang embarquée ignorait Sentry) ; détection d'injection sur `@rpath/SpliceKit.framework` (le chemin `~/Applications/SpliceKit` faisait croire à une injection déjà faite) ; `detect_sign_identity` ne renvoie plus deux identités.
- Signature : identité « Apple Development: Alexandre Bruneau », team U42X6U6LT7.
- Logs : `~/Library/Logs/SpliceKit/splicekit.log`.

## Dépannage rapide
- `Cannot connect … 9876` : la copie patchée n'est pas lancée, ou le FCP standard tourne à sa place (`ps -o command= -p $(pgrep -x "Final Cut Pro")`).
- `No active libraries found` : ouvrir une bibliothèque (`open -a "~/Applications/SpliceKit/Final Cut Pro.app" ~/Movies/Perso.fcpbundle`).
- Erreurs `attempt to insert nil object` en rafale + pont muet : un dialogue modal (souvent une permission macOS) attend Alexandre.
- Titre rendu en Helvetica : police absente de `~/Library/Fonts`.
