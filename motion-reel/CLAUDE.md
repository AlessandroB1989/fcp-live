# motion-reel — règles de maison

Lues à chaque exécution du skill. Elles priment sur toute préférence esthétique. `scripts/render.py` en fait respecter une partie de façon automatique (erreurs bloquantes) ; les autres relèvent de la boucle de critique.

## Interdits
- Timers, `requestAnimationFrame`, `Date.now()`, état mutable entre deux frames, `Math.random` : le renderer est une fonction pure `draw(ctx, t, spec, kit)`. Le seul aléa autorisé vient de `noise.js`, seedé par `spec.seed`.
- Ease-in-out par défaut. Seuls trois easings existent : `cut`, `linear`, `spring` (forme close, ζ et ω explicites).
- Dégradés décoratifs, ombres portées floues, emoji. Les primitives n'en proposent pas : n'essaie pas de les contourner.
- Plus d'une couleur d'accent par plan (calques `"accent": true`).
- Du texte hors de la zone sûre : marge du brand kit sur les 4 côtés, plus les 250 px réservés à l'interface Instagram en bas d'un 9:16.
- Une valeur de marque (couleur, police, taille de référence, marge, style de mouvement) écrite en dur ailleurs que dans `brandkits/<id>.json` : le spec n'utilise que les **noms** de couleur et les **rôles** de police du kit.
- Un repli de police silencieux. Si une police manque, le rendu échoue : installe-la, ne la remplace pas.

## Obligatoires
- Une grille de temps (`beats`, en secondes) qui commence à 0, finit à `duration` et tombe sur des frames entières. Chaque état (`t0`) et chaque plan démarre sur un beat.
- Chaque plan (`shots`) décrit un **état de départ → un état d'arrivée**. Un seul morph de forme (changement de `w`/`h`) par plan.
- Les apparitions (opacité 0 → >0) se font par `cut` ou par un fondu `linear` d'exactement `motion.durations.fade_frames` images (ou `fade_s` × fps pour les kits qui l'expriment en secondes).
- Dans un plan, l'accent apparaît **avant** le texte.
- Un ressort doit être arrivé à destination avant `t1` (écart résiduel < 0,5 %). Sinon, allonge l'état ou augmente ω.
- Respecte aussi les `rules` et le `motion.style` du brand kit (par exemple, pour baair : angles à 90°, aucun rebond, donc ζ ≥ 1).

## Boucle de critique (obligatoire avant de livrer)
1. `python3 scripts/render.py <spec> --format <f>` produit une planche-contact de 12 vignettes réparties sur la durée, avec les zones sûres en pointillé.
2. **Lis la planche** avec l'outil Read, puis réponds par écrit à cette checklist :
   - La bonne police est-elle chargée dans chaque rôle ? (Fraunces n'est pas Times, Instrument Serif italique n'est pas une italique synthétique.)
   - Y a-t-il un débordement ou un texte collé à la marge ?
   - Le contraste est-il d'au moins 4,5:1 sur la frame la plus claire ? (Le rendu vérifie la couleur de fond `preview` ; sur une vraie vidéo, vérifie à l'œil.)
   - Y a-t-il un seul accent par plan ?
   - Le rythme suit-il la grille, sans moment mort ni surcharge ?
3. Corrige le spec et relance le rendu. **Trois itérations maximum**, puis remets le travail à l'utilisateur avec la planche et ce qui reste discutable.

## Sorties (jamais ailleurs)
- `<dossier médias Raccord>/<slug>-<format>.mov` : ProRes 4444 avec alpha, à plat dans le dossier médias (Raccord refuse les sous-dossiers), prêt pour `clips[].media`.
- `~/Movies/Raccord/motion/<slug>-<format>/` : `<slug>-<format>.mp4` (H.264 de contrôle sur le fond `preview`), `contact-sheet.png` et `spec.json` (le spec résolu, tel que rendu).
- Le dossier médias est lu dans `~/Library/Application Support/Raccord/config.json` (`mediaDirectory`), par défaut `~/Movies/Raccord/media`.
