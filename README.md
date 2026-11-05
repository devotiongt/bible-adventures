# Bible Adventures · Chapter 1: Noah's Ark

Full process, status and to-dos: [docs/PROCESS.md](docs/PROCESS.md).

Low poly exploration, gathering and building game made with **Godot 4.7**. It uses the *Forward+* renderer on PC and Mac and *Mobile* on phones.

## Play

On Mac, double-click **Play.command** (it reimports new models and opens the game). From the terminal:

```bash
godot --path .
```

Or open the folder in the Godot editor and press ▶.

| Action | Keyboard | Gamepad |
|---|---|---|
| Move | WASD / arrows | Left stick |
| Action (chop, gather, build) | E / Space (hold to repeat) | A |
| Crafting panel | C / Tab | Y |
| Rotate camera | Q / R, or drag with right click | LB / RB |
| Zoom | Mouse wheel | — |
| Restart game | F9 | — |

## Game loop

1. Chop trees (wood), gather reeds (fiber) and mine rocks (stone).
2. Craft rope and a **hammer**, which you need to build.
3. Build the ark in 5 stages: keel, hull, sealing with pitch (you need a **bucket**), decks, and roof with door.
4. Each stage shows a passage from Genesis 6.

## Structure

- `data/`: items, recipes and ark stages in JSON. They can be tweaked or extended without touching code.
- `scripts/game_state.gd`: `Game` autoload with the inventory, crafting, the ark, controls and saving.
- `scripts/world.gd`: generates the island (terrain, sea, grass, vegetation, resources and clouds).
- `scripts/resource_node.gd`: trees, rocks, reeds and pitch pits.
- `scripts/ark_site.gd`: the ark in stages (Blender model), with a "ghost" of the next one and real collision.
- `scripts/player.gd` and `scripts/camera_rig.gd`: Noah and the camera.
- `scripts/hud.gd`: the interface.
- `scripts/noah_rig.gd`: the in-game Noah (Rodin model, polished and rigged) with his animations. `noah_model.gd` is the previous version, no longer used.
- `scripts/robe_cloth.gd`: skirt simulated as cloth (inertia, gravity and collision with the legs) that deforms the pleated skirt made in Blender.
- `scripts/animal.gd`: ambient animals.
- `scripts/models.gd` and `scripts/effects.gd`: model loading, wind and particles.
- `shaders/`: wind on leaves and grass, sea, ark wood, gray hair and diorama effect.
- `scripts/debug.gd`: automated tests and screenshots.

## Models made in Blender

The ark and Noah's clothes are generated with Blender scripts, so they can be tweaked and regenerated:

```bash
blender --background --factory-startup --python tools/blender/ark.py -- assets/ark/ark.glb
```

```bash
blender --background --factory-startup --python tools/blender/tunic.py -- assets/characters/tunic.glb
```

Add a folder as a second argument to save renders. The measurements are at the top of each script.

- [ark.py](tools/blender/ark.py): hull of curved planks, frames, deck, rooms, roof, door and ramp; one object per stage.
- [tunic.py](tools/blender/tunic.py): slims the base body (which is "superhero" shaped), pulls the tunic out of the body itself (fitted, no layers and with the same weights) with the mantle and sash as color zones, and creates the pleated skirt that the cloth simulation moves.

**Watch it live:** with Blender open, [live.py](tools/blender/live.py) sends a script step by step to the blender-mcp add-on and the scene builds up in the window:

```bash
python3 tools/blender/live.py tunic step_import step_slim step_tunic step_knot step_skirt --pause 2
```

The project also registers [blender-mcp](https://github.com/ahujasid/blender-mcp) in `.mcp.json`: with Blender open, Claude Code can model directly in the scene (the add-on starts its server when Blender opens).

### Noah: from editing to the game

1. Edit `assets/characters/rodin/noah_texture.blend` in Blender (shape and texture).
2. Save the texture image (Image → Save) and export `noah_game.glb` (body, eyes and eyebrows).
3. Rig and transfer animations (in the background, about 2 minutes):

```bash
blender --background --factory-startup --python tools/blender/rig_noah.py -- assets/characters/rodin/noah_game.glb assets/characters/rodin/noah_rig.glb
```

The game loads `noah_rig.glb`. The script prints the natural walk and jog speeds; if the proportions change, update them in `scripts/noah_rig.gd`.

## Art credits

3D models by [Quaternius](https://quaternius.com) under the CC0 license (public domain), in `assets/`:
- Stylized Nature MegaKit (trees, rocks, plants, grass).
- Ultimate Animated Animal Pack.
- Universal Base Characters and Universal Animation Library.

## Tests

```bash
godot --headless --path . -- --no_save --new --no_intro --autotest
```

Useful arguments after `--`:
- `--new`: starts a new game.
- `--no_save`: doesn't touch the saved game.
- `--demo`: fills the inventory.
- `--stages=N`: starts with N ark stages built.
- `--pos=x,z`: places Noah at that point.
- `--zoom=N`: camera distance.
- `--screenshot=file.png`: saves a screenshot and closes the game.
- `--no_diorama`, `--no_glow`, `--no_ssao`: turn off effects to compare.
- `--walk=0.3`: makes Noah walk (1 = jog) during the screenshot. With `--dir=move_right`, `--turn=1.9` and `--dir2=move_left` he changes direction halfway.
