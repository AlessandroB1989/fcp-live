# Prompt — skill `motion-reel` (étapes a + b)

À coller tel quel dans une nouvelle session Claude Code ouverte sur `MCP & Skills/fcp-live` (modèle conseillé : Claude Opus 5.5).

---

Tu travailles dans le repo `fcp-live` (skill Claude Code qui pilote Final Cut Pro via l'app Raccord, MCP `raccord`). Raccord est validé de bout en bout le 2026-09-28 : profil → proposition → import FCP → tête de lecture → capture du viewer (voir `../Raccord/validation/REPORT.md`, dernière section). Ne touche pas à Raccord.

Objectif : ajouter au repo un skill **`motion-reel`** qui génère des séquences de motion design **en code déterministe**, rendues en vidéo, prêtes à être déposées dans le dossier médias de Raccord et posées sur la timeline FCP comme n'importe quel clip. Méthode inspirée du cours de @0xMovez « motion design studio with Opus 5.5 » : renderer `seek(t)` pur + Playwright headless + ffmpeg, règles de maison, boucle de critique par planche-contact.

## Contraintes non négociables
1. **Sécurité** : aucune injection, aucun plugin, aucun accès réseau à l'exécution (les dépendances sont installées une fois : `playwright` + Chromium, `ffmpeg` via Homebrew). Pas de `eval`, pas de code téléchargé. Le renderer tourne dans un navigateur headless sur des fichiers locaux uniquement.
2. **Déterminisme** : une fonction `draw(ctx, t, spec)` sans état, sans `setTimeout`/`requestAnimationFrame`/`Date.now()`, bruit seedé (`mulberry32`), ressorts en forme close (pas de simulation pas-à-pas). Deux rendus du même spec donnent des PNG identiques (test à écrire : hash des frames).
3. **Multi-branding** : tout ce qui est couleur, police, taille, marge, style de mouvement vient de `brandkits/<id>.json` (déjà existants : `baair`, `ia-explorateurs`, `ia-pilotes`). Aucune valeur de marque codée en dur.
4. **Formats** : 9:16 (1080×1920), 1:1 (1080×1080), 16:9 (1920×1080), fps du brand kit (`video.reel.fps`). Sortie ProRes 4444 (alpha conservé pour la superposition dans FCP) **et** H.264 de contrôle.
5. Polices : chargées depuis `~/Library/Fonts` via `@font-face` `file://` ; si une police manque, **échec explicite**, jamais de repli silencieux sur Helvetica.

## (a) Règles de maison — `motion-reel/CLAUDE.md`
Écris un `CLAUDE.md` court et impératif, lu par le skill à chaque exécution :
- Interdits : timers, état mutable entre frames, `Math.random` non seedé, ease-in-out par défaut, dégradés décoratifs, ombres portées floues, plus d'une couleur d'accent par plan, texte en dessous de la zone sûre, emoji.
- Obligatoires : grille de temps (beat grid) déclarée en secondes dans le spec ; chaque plan = **état de départ → état d'arrivée** (liste d'états, un seul morph de forme par plan) ; apparitions par coupe ou fondu de `motion.durations.fade_frames` images ; l'accent (carré violet pour baair) apparaît avant le texte ; zones sûres du brand kit.
- Boucle de critique obligatoire avant de livrer : rendre une planche-contact (12 vignettes réparties sur la durée), la **lire** avec l'outil Read, répondre à une checklist (police chargée ? débordement ? contraste ≥ 4.5:1 sur la frame la plus claire ? un seul accent ? rythme aligné sur la grille ?), corriger le spec, re-rendre. Maximum 3 itérations, puis remettre à l'utilisateur avec la planche.
- Sortie toujours dans `~/Movies/Raccord/media/motion/<slug>-<format>.mov` (+ `.mp4` de contrôle + `contact-sheet.png` + `spec.json`), jamais ailleurs.

## (b) Renderer + pipeline — `motion-reel/`
Structure attendue :
```
motion-reel/
  SKILL.md               # déclencheurs FR/EN ("motion design", "animation de titre", "intro animée", "générique", "lower third", "fais un motion")
  CLAUDE.md              # (a)
  renderer/index.html    # canvas 2D, charge spec.json + brandkit, expose window.seek(t) qui dessine la frame t et résout quand c'est peint
  renderer/draw.js       # draw(ctx, t, spec, kit) pur ; primitives : texte (rôles title/signature/body/label), carré accent, ligne, rectangle, masque de révélation, morph rect→ligne
  renderer/easing.js     # springs analytiques (closed-form, paramètres ζ et ω), linear, cut ; aucun ease-in-out par défaut
  renderer/noise.js      # mulberry32 + value noise 1D seedé
  scripts/render.py      # Playwright headless : ouvre index.html en file://, pour f in frames: await page.evaluate(seek(f/fps)) → screenshot PNG ; puis ffmpeg → ProRes 4444 + H.264 ; --contact-sheet ; --format 9x16|1x1|16x9 ; --brandkit <id>
  scripts/check.py       # tests : déterminisme (2 rendus = même hash), police présente, spec valide (jsonschema), durée = beat grid
  spec.schema.json       # schéma fermé du spec (états, plans, beats, textes, format, brandkit)
  examples/baair-hook.json   # "Tools, not decks." 9:16, 4 s : carré → hook (Fraunces + Instrument Serif italic) → label BAAIR.SOLUTIONS
  examples/baair-lower-third.json
```
Le spec est une **liste d'états** par calque : `{layer, from:{x,y,scale,rotation,opacity,...}, to:{...}, t0, t1, easing:{type:"spring", zeta, omega}|{type:"linear"}|{type:"cut"}}`, en pixels du format cible, y vers le haut comme dans Raccord. Réutilise les rôles de police et les noms de couleur du brand kit exactement comme le skill `fcp-live` (`brandkits/baair.json`).

## Intégration avec fcp-live
- Dans `SKILL.md` de `fcp-live`, ajoute une étape « motion design » : si le brief demande une séquence animée, appeler le skill `motion-reel`, puis référencer le `.mov` produit comme `clips[].media` (lane positive au-dessus du plan) dans le spec Raccord. Le `.mov` est dans le dossier médias du profil, donc `raccord_list_media` le voit.
- Documente dans `motion-reel/SKILL.md` la boucle de critique côté FCP : après import, `raccord_seek_playhead` sur chaque beat + `raccord_capture_viewer`, lire les PNG, corriger.

## Livrables et critères d'acceptation
1. `python3 scripts/render.py examples/baair-hook.json --format 9x16` produit le `.mov`, le `.mp4`, la planche-contact et `spec.json` dans `~/Movies/Raccord/media/motion/` en moins de 60 s sur ce Mac.
2. `python3 scripts/check.py` passe : déterminisme, polices, schéma, durée.
3. Tu **lis** la planche-contact et tu appliques la checklist du `CLAUDE.md` ; tu montres la planche finale à l'utilisateur.
4. Démo finale : proposer via `raccord_propose_edit` un reel 9:16 de 8 s = `higgsfield-bureau.mp4` + le `.mov` du hook en lane 2 ; l'utilisateur clique Importer ; tu vérifies par `raccord_seek_playhead` + `raccord_capture_viewer` à 1,0 s et 3,0 s que le motion est bien superposé (alpha) et lisible.
5. README de `fcp-live` : section « Motion design » (5 lignes) + le badge « validé le <date> ».
6. Commit + push sur `main` (GitHub AlessandroB1989/fcp-live) avec la ligne `Co-Authored-By` habituelle. Aucun secret, aucune clé dans le repo.

Environnement : macOS 26.5, FCP 12.3, Xcode 27 (utiliser `/opt/homebrew/bin/python3.12` et `/Applications/Xcode.app/Contents/Developer/usr/bin/git`, les shims `/usr/bin` sont bloqués par la licence). Playwright : `pip3.12 install playwright && playwright install chromium`. ffmpeg : `brew install ffmpeg` si absent. Polices baair déjà installées (Fraunces, Instrument Serif, Inter, JetBrains Mono).

Commence par (a), montre-le moi, puis (b). Ne demande pas de confirmation entre les fichiers de (b) ; demande-la seulement avant l'installation de dépendances et avant la démo finale dans FCP.
