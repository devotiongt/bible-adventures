# Bible Adventures: process and status (Oct 21, 2026)

Summary of everything done, how it's done and what's left, to pick it up in another session.

## 1. The game

- **Engine:** Godot 4.7 (Forward+ on PC, Mobile on phones). Open: `open -n -a /Applications/Godot.app --args --path .`
- **Chapter 1 (Noah's Ark):** island with trees, rocks, reeds and pitch pits; gathering, crafting (`data/recipes.json`), ark in 5 stages (`data/ark.json`), Genesis 6 texts, autosave.
- **Art:** Quaternius CC0 (animals, animations), custom shaders (wind, sea, wood, diorama, terrain), ark made by script in Blender.
- **Setting: Noah's village** (design in `docs/DESIGN_CHAPTER1.md`, data in `data/village.json`):
  - The layout comes from [Watabou's Village Generator](https://watabou.github.io/village-generator/) (seed 11, tags `river,farmland,dense`, 420 × 315), exported as JSON to `references/watabou_village11.json`. `tools/watabou_to_village.py` scales it (0.6) and turns it into `data/village.json`: river, two bridges, streets, plaza, 38 houses (the model depends on its shape), fields, garden and trees. The story parts (Noah's house and family, ark meadow, quarry, pitch, pens, animals, road to the ark) go in `ADJUSTMENTS` inside the script; don't hand-edit what comes out of the generator. With a third argument it draws a view with the real size of houses and yards:
    ```bash
    ~/tools/Hunyuan3D-2/.venv/bin/python tools/watabou_to_village.py references/watabou_village11.json data/village.json view.png
    ```
    The previous, hand-made village is kept in `references/village_previous.json`.
  - `scripts/world.gd`: valley with hills around it, river with bridges, ark hill, curved paths (Catmull-Rom) and trails from each door to the nearest path, vegetation grouped by rules (path edges, foot of trees, yards, meadow patches). The dirt edges are cut by `shaders/terrain.gdshader`.
  - `scripts/village.gd`: houses facing the plaza, objects in each yard, well and benches, pen and wheat fields.
  - `tools/blender/houses.py` → `assets/village/village.glb`: adobe houses (NoahHouse, HouseA/B/C, with shutters, curtains and plaster stains), well, oven, bench, jug, basket, firewood, fence, stall, flowerpot, sack, rug, clothesline, loom, trough and the ark worksite (awning, workbench, sawhorses, planks, scaffold, pitch pot; placed in `SITE` in `scripts/ark_site.gd`):
    ```bash
    blender --background --factory-startup --python tools/blender/houses.py -- assets/village/village.glb
    ```
  - AI-generated objects: Hunyuan3D-2mini runs locally (`~/tools/Hunyuan3D-2`, server at
    `localhost:8081`; start it with `cd ~/tools/Hunyuan3D-2 && PYTORCH_ENABLE_MPS_FALLBACK=1 .venv/bin/python api_server.py --host 127.0.0.1 --port 8081 --device mps`).
    Cutouts from `references/village_objects.jpg` in `references/cutouts/`, shapes in `tools/blender/generated/`,
    processed (cleaned, scaled, reduced and painted with the cutout's colors) with `tools/blender/process_generated.py`
    → `assets/village/generated.glb`. `scripts/pieces.gd` uses the generated version of each piece when it exists. Each object has its own file for hand touch-ups in `tools/blender/objects/<name>.blend` (discarded versions in `tools/blender/objects/versions/`); `tools/blender/export_objects.py` puts them together in the `.glb`. The market stalls are assembled with `tools/blender/build_stalls.py`: an empty stall and the goods generated separately (`references/market_parts.png`, pieces in `tools/blender/objects/stall_parts/`); the awning takes each stall's color and the stripes are drawn by the shader. Painting by materials (what works best): `tools/blender/gemini_views.py <object>` renders 4 gray views (`references/views/`); Gemini paints each one with flat colors per material (prompt #17, one per conversation; it may redraw or mirror them); they are saved as `references/views/<object>_<view>_materials.png` and `tools/blender/paint_materials.py <object>` fits them on its own, paints the detailed model and bakes a clean texture onto the light one (list of materials in `MATERIALS`). Wood gets a common brown and grain drawn by `shaders/props.gdshader` (`wood_color`).
  - `scripts/stylized.gd`: trees, olive tree, pines, bushes, flowers, shrubs, wheat and rocks in a soft palette.
  - The island takes ~7 s to generate (the new map is about three times bigger). Quaternius's nature models (`assets/nature/`) are no longer used.

## 2. Noah

**Current Noah (short tunic, with legs):** Gemini T-pose sheet (prompt #22, `references/noah_legs_turnaround.webp`),
TRELLIS with only the front view (seed 7) → `tools/blender/generated/noah_trellis/front_s7.glb`,
`clean_trellis.py` (height 1.5) → `assets/characters/noah_trellis/noah_front_s7.glb`, without the strip of skin TRELLIS
painted on the skirt (`clean_skirt_stain.py ... 0.35 0.62 0.34`), and rig:
```bash
blender --background --factory-startup --python tools/blender/rig_noah.py -- assets/characters/noah_trellis/noah_front_s7.glb assets/characters/noah_trellis/noah_short_rig.glb --profile tools/blender/profiles/noah_short.json
```
Natural speeds (printed by the rig) in `scripts/noah_rig.gd`; Noah moves at `SPEED := 2.3`. The long tunic
made separately (`rig_noah_chains.py`, `skirt_springs.gd`, draped with Blender physics) was tried and didn't turn out
well: it looked like a sack.

### Previous Noah (Rodin, long tunic): how it was made (full pipeline)

1. **References** (`references/`): Noah's turnaround sheet, head, palette, etc., generated with Gemini from `references/PROMPTS.md`.
2. **AI 3D model:** Hyper3D Rodin, sending the 4 views of the turnaround sheet (`condition_mode=concat`, Regular tier). Result: `assets/characters/rodin/noah_rodin_original.glb` (98,000 triangles). Silhouette match: 95% from the front, 86% at 3/
3. **Polish** (`tools/blender/polish_rodin.py`): no metallic look, colors brought to the palette, eye sockets filled (geometry, color and normal map), new eyes half sunk into the face, painted blush.
4. **Polygon reduction:** 2,500 body triangles. Automatic distribution by **thickness** (protects fingers, wrists and nose), optional extra priority on the shoulders. The original detail is baked into a normal map.
5. **Texture** (`tools/blender/texture.py`, steps in order):
   `step_unfold_folds` → `step_brows` → `step_uv` → `step_bake` → `step_paint` → `step_tuck_flap` → `step_unfold_folds` → `step_uv` → `step_bake` → `step_paint` → `step_shoulders` → `step_paint` → `step_export`.
   - Texture unwrap with no overlapping triangles (overlapping ones are moved to a separate strip).
   - Painting by parts with the palette: each triangle belongs to a part (hair, skin, nose, tunic, vest, sleeve, rope, sandal), with position rules on the body, straight vest opening, sandals (sole + strap), linen weave, soft occlusion.
   - Eyebrows as separate pieces (measurements in `references/noah_brows.json`).
   - Result: `assets/characters/rodin/noah_game.glb` (3,220 triangles in total, 2.5 MB) and `noah_texture.blend` (+ `noah_texture_backup.blend`).
6. **Rig** (`tools/blender/rig_noah.py`, in the background, ~2 min):
   ```bash
   blender --background --factory-startup --python tools/blender/rig_noah.py -- assets/characters/rodin/noah_game.glb assets/characters/rodin/noah_rig.glb
   ```
   - Universal Animation Library skeleton (65 bones) fitted to Noah's joints.
   - Automatic weights + rules: head/beard/hair rigid with the head, torso clothes only with spine and legs, skirt blending pelvis and legs, belt rope rigid with the pelvis (detected by its color in the texture).
   - 9 animations copying each bone's orientation (Idle, Walk, Jog_Fwd, Sprint, Interact, Sword_Attack, Fixing_Kneeling, PickUp_Table, Idle_Talking).
   - Prints the natural walk/jog/run speed: copy it into `scripts/noah_rig.gd` if the proportions change.
7. **In the game** (`scripts/noah_rig.gd`): loads `noah_rig.glb`; jog with 65% of the original's back lean and arm swing and no hip sway; matte material at 74% brightness. When chopping he holds an axe and when mining a pick in his right hand (low poly pieces made in code, attached to the `hand_r` bone; `GRIP_*` and `TOOL_TWIST` place them). Noah's speed: `SPEED := 3.1` (Jog_Fwd jog; the tunic has 8 skirt bone chains from `rig_noah.py`, moved in the game by springs with collision against the legs: `scripts/skirt_springs.gd`) in `scripts/player.gd`. Physics interpolation enabled (removes the jitter in fullscreen).

### The family and villagers with TRELLIS (free, what works best)

1. Turnaround sheet in Gemini (prompt #20, with Noah's attached) **in T-pose** (arms horizontal, sleeves
   apart from the body): with the arms down, the generator merges the sleeve with the side and that
   cloth stretches when walking. Gemini tends to copy the pose of the attached image: ask for it as a NEW sheet, using the
   previous one only as a design reference. Its side and back views usually come out wrong in T-pose: the front is enough.
2. TRELLIS on Hugging Face (Space `trellis-community/TRELLIS`, with the free account already connected via
   `hf auth login`): first remove the background of each view (`/preprocess_image`) and then send the 4 views
   together to `/generate_and_extract_glb` with `multiimage_algo="multidiffusion"`. It comes out textured in ~30 s.
   Save in `tools/blender/generated/<name>_trellis/`.
3. `tools/blender/clean_trellis.py <trellis.glb> <output.glb> <height> <turn>`: joins the pieces,
   matte material (it comes metallic), smooth surface, standing and at its height; if ankles are missing, it adds them.
4. Rig with `rig_noah.py` and its profile (joint measurements), and in `data/village.json` ("villagers")
   with `"shine": 1.0`.

### The family and villagers by painting the local shape (discarded: looks worse)

1. Turnaround sheet in Gemini with Noah's attached (prompt #20 for the wife) and the same sheet recolored
   with a pure color per part (prompt #21). The 4 views of each, tightly cropped, in
   `references/character_views/<name>_<view>.png` and `<name>_parts_<view>.png`.
2. Shape with Hunyuan3D locally (from the front view) → `tools/blender/generated/<name>.glb`.
3. `tools/blender/paint_character.py`: fits each view by its silhouette, uses a depth buffer to see
   which views see each point, votes the part with the pure-color map, cleans it in patches
   (the folds of the clothes) and bakes a clean texture onto a 12,000-face model.
   ```bash
   blender --background --factory-startup --python tools/blender/paint_character.py -- tools/blender/generated/wife.glb wife 1.45 assets/characters/family/wife.glb
   ```
   The parts and their colors (`PARTS`, `FLATS`) are the wife's: for another character, change them.
4. Rig with the same Noah script and a measurements profile (`tools/blender/profiles/<name>.json`):
   ```bash
   blender --background --factory-startup --python tools/blender/rig_noah.py -- assets/characters/family/wife.glb assets/characters/family/wife_rig.glb --profile tools/blender/profiles/wife.json
   ```
5. In the game, `scripts/villager.gd` (data in `data/village.json`, "villagers", which come from
   `tools/watabou_to_village.py`): strolls slowly between its yard points and at each one stays
   standing, talking or working.

### To bring your Blender edits into the game

1. In Blender: save the texture image (Image → Save) and export `noah_game.glb` (body `NoahLow2500`, eyes and eyebrows; "Selected Objects" and "Apply Modifiers").
2. Run the rig (command above).
3. Reimport and open the game. Only the Godot editor reimports on its own; if you open the game directly
   (`godot --path .`), you first need to run `godot --headless --import --path .` or the old model will stay.

**Careful:** running `step_paint` or other steps of `texture.py` again rewrites the texture and erases what was hand-painted.

## 3. Working with Blender live

- blender-mcp installed (add-on enabled, server at `localhost:9876`, starts when Blender opens).
- `tools/blender/live.py` sends functions of a script to the open window:
  `python3 tools/blender/live.py texture step_paint`
- Godot ignores `.blend` files (`import/blender/enabled=false` in `project.godot`).

## 4. Lessons learned (they save hours of testing)

- **glTF splits vertices at texture seams.** When reimporting, merge them (`remove_doubles`) before smoothing or weighting; otherwise the mesh opens up in cracks.
- **Overlapping triangles in the texture** make one part get painted with another's color (stains on the sleeves). Always check with `_overlapping_faces`.
- **Rotating edges** (straightening folds) breaks the unwrap of those triangles: afterwards, repeat `step_uv` + bake + paint.
- **The normal map also "paints" shapes:** if you flatten the mesh (eyes, eyebrows, shoulders), also flatten the normals in that area.
- **Loading meshes from a `.blend` leaves it open as a library** and blocks saving it: remove the library afterwards.
- **Ctrl + number in Blender adds subdivision** (it pushed the eyes to 46,000 triangles). The export now warns if the total goes over 4,000.
- **Colors in Blender:** the brush uses linear space (sRGB^2.2).
- **More polygons don't always help:** on the shoulders the Rodin model's flap shows up again.

## 5. To do

- Finish the hand touch-ups of the texture and bring them into the game (section 2).
- Check the chop, gather and build actions in the game (only reviewed in Blender).
- Soft facets on the ankles; shoulder flap to be reviewed by hand.
- License of the Rodin model (section 2.2).
- Next phases: animals arriving at the ark two by two, touch controls for mobile, export to web/mobile (include `*.json` in the export).
