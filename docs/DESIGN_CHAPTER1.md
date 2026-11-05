# Chapter 1: Noah's village (design)

Design of the chapter 1 setting. It replaces the randomly generated island with a hand-designed village,
*cute* and *cozy*.

**Decided (Oct 21, 2026):** valley with a river (no sea); Noah's wife has no name (true to the
text); first the village and terrain, then the characters. Everything must feel **organic**:
soft curves and things where they make sense, never random scattering.

## 1. Idea

Noah lives in a small village in a green valley, with his wife, his three sons (Shem, Ham and Japheth) and
their wives (Genesis 6:10, 7:13). God asks him to build the ark (Genesis 6:14). The village is
home: calm, warm, full of life. The ark rises in a meadow on a hill, outside the
village but in sight of the plaza, so every stage built can be seen from home.

Tone: a soft, sunny afternoon, like Animal Crossing or Tiny Glade. Nothing loud: pastel and
warm colors, soft shadows, low contrast between zones and lots of small detail.

## 2. Map and zones

**Layout (Oct 22, 2026): the village grows along its street.** A radial layout (circular
plaza with paths in a star and evenly spaced houses facing the center) looks drawn with a compass. Now
there's a main street that comes from the valley, winds through the village and climbs the ark's hill.
The plaza is the irregular widening where it crosses the river path. The houses cluster with their
fronts toward their street, and some yards share a low wall. The paths have a hierarchy: wide street,
alleys that join in a Y, and trails that fade into the grass. The width varies and the edges have
trampled grass and pebbles.

**Zones: following the sketch `references/noah_village_sketch.jpg`.** The ark
is at the top of a hill to the north (10 m), with a winding trail. The river runs along the west, with a
stone and wood bridge. In the center there's a market plaza with awnings, a campfire, a well and tables, and the
houses surround it (most of them to the east). The gardens are to the west, there are three pens (west, south and
east), a dense forest to the east, and the road to the valley leaves to the south between the hills. The houses
are still adobe, to stay true to the story. The table below is the initial proposal and
serves as a reference for what each zone is for; the real positions are in `data/village.json`.

The valley is closed in by gentle hills, with no sea: a natural edge instead of water all around.
It measures about 110 × 90 m, more compact than the current island, so everything is a few steps away.

| Zone | Where | What's there | What it's for |
|---|---|---|---|
| Plaza | Center | Well, large olive tree, benches, jugs | Landmark and meeting place |
| Noah's house | North of the plaza | Biggest house with a yard, bread oven (tannur), loom, garden | Start of the chapter; the wife is there |
| Sons' houses | Around the plaza | 3 small houses with yards | Shem, Ham, Japheth and their wives |
| Neighbors | South and east | 3 or 4 houses, pottery stall | People who comment on (and doubt) the ark |
| River | West | Stream with a wooden bridge, reeds, stones | Fiber (reeds) |
| Forest | Southwest | Cypresses and round trees in groups | Gopher wood (chop) |
| Quarry | Northwest, at the foot of the hill | Large lilac rocks | Stone (mine) |
| Fields and pen | East | Strips of wheat and barley, low fence, sheep and goats | Ambience; later, animals |
| Ark meadow | Hill to the east | Flat clearing, scaffolds, wood piles, pitch pits at the edge | Building the ark |

The paths come from how the space is used: from each door to the plaza, and from the plaza to each work
zone (river, forest, quarry, ark). No filler paths.

## 3. Rules so it doesn't look random

- **Hand placement:** houses, important trees, fences and paths have a fixed position in a
  data file (`data/village.json`). Randomness is only used to vary the rotation, size
  and tone of small pieces a little.
- **Groups, not rain:** tall grass, flowers and bushes appear in groups of 3 to 9 where
  they make sense: at the foot of walls, next to fences, on path edges, under
  trees, on the riverbank and in flowerpots and gardens. In the middle of meadows, short grass and almost
  nothing else.
- **Forbidden:** grass on top of paths, plazas, yards and house floors, and flowers in the dense
  forest.
- **Terrain:** almost flat in the village. A gentle hill leads to the ark, and the edge hills close
  the valley. Dirt steps are only used on purpose: a retaining wall by the river and
  terraces in the garden. No more random contour lines.
- **Density:** more detail near the plaza and the houses; the forest dense but in patches; the
  meadows clear so the paths read well.

## 4. Palette (less saturated)

| Use | Color | | Use | Color |
|---|---|---|---|---|
| Grass | `#9cc27a` | | Adobe walls | `#e8cfa6` |
| Grass in shade | `#7fae64` | | Adobe in shade | `#cfae84` |
| Dirt path | `#d8b98c` | | Wood | `#a87b55` |
| Plaza (packed earth) | `#e6d3ad` | | Cloth, awnings | `#e7a48f` / `#9fb7c9` |
| Leaves | `#7fa35c` / `#6f9a52` | | Rocks | `#b3abc0` |
| Water | `#9fc7d6` | | Sky | `#a9d3ec` → `#f4e9d8` |

The light is warm and soft: low golden sun, shadows with a bit of blue and normal saturation (without the
current ×1.3). The diorama effect stays only as a soft vignette.

## 5. Proportions

Noah is 1.55 m tall (chibi, big head). Everything is measured against him:

| Piece | Size | | Piece | Size |
|---|---|---|---|---|
| Door | 1.9 × 1.1 m | | Well | Ø 1.4 m, 0.7 m curb |
| House wall | 2.4 m high | | Plaza olive tree | 4.5 m |
| Small house | 5 × 4 m | | Forest trees | 3.5 to 5 m |
| Noah's house | 8 × 6 m with yard | | Fence | 0.8 m |
| Oven (tannur) | Ø 0.8 m, 0.9 m high | | Sheep | 0.7 m high |
| Path | 1.6 to 2.2 m wide | | Tall grass clump | 0.3 to 0.5 m |

People have the same chibi proportions as Noah: 1.3 to 1.6 m tall, with the sons and
daughters-in-law a bit shorter.

## 6. Characters

- **Noah's wife:** no name, as in the Bible.
- **Shem, Ham and Japheth, and their wives.**
- **3 or 4 neighbors** with a couple of lines each.
- **How to make them:** with the same pipeline as Noah (turnaround sheet → Rodin → polish → rig with
  `rig_noah.py`, which already works for any character in the same pose). Each one takes
  work, so it's best to start with the wife and the sons, and leave the neighbors for later.

## 7. Assets: what's generated, what's modeled and what's reused

| Piece | How | Why |
|---|---|---|
| Adobe houses (3 variants + Noah's house) | Blender script, like `ark.py` | Simple shapes (rounded boxes, flat roof, stairs); this way we control the exact sizes |
| Well, oven, benches, fences, jugs, baskets | Blender script or code | Small, repeated pieces; same style |
| Plaza olive tree, loom, pottery stall, sheep and goats | 3D generator (Rodin) | Organic shapes; they look better generated |
| Plants, rocks and grass | `stylized.gd` (already exists) | The palette gets readjusted and cypresses and olive trees are added |
| Characters | Rodin + `rig_noah.py` | Same style as Noah |

CC0 packs reviewed: [KayKit Medieval Hexagon](https://kaylousberg.itch.io/kaykit-medieval-hexagon),
[Kenney Fantasy Town Kit](https://opengameart.org/content/fantasy-town-kit) and
[Quaternius Medieval Village](https://opengameart.org/content/lowpoly-medieval-village-pack). They're
European (tiled roofs, timber framing) and don't fit a Mesopotamian village. They only
serve as inspiration for the level of detail.

Historical references: one- or two-room adobe houses with a flat roof (used for sleeping and
working), a yard with a bread oven and animals near the house
([historyonthenet](https://www.historyonthenet.com/daily-life-in-the-mesopotamian-countryside),
[TheCollector](https://www.thecollector.com/daily-life-ancient-mesopotamia/)).

## 8. Chapter walkthrough

1. Noah wakes up in his house. His wife talks to him in the yard (tutorial for moving and interacting).
2. The Genesis 6:13-14 moment: the instruction to build the ark.
3. The sons help: Shem in the forest, Ham in the quarry, Japheth at the river. Each one explains a
   resource.
4. Crafting happens in Noah's yard and building in the meadow, in 5 stages. The neighbors comment in
   the plaza.
5. Ending: the animals arrive two by two (next phase).

## 9. Work order

1. New valley terrain (flat, hill, river, hills), paths and zones from `data/village.json`,
   new palette and lighting.
2. Village houses and pieces (Blender script), placed by hand.
3. Vegetation in groups following the rules in section 3.
4. Characters: wife and sons.
5. Dialogue and chapter walkthrough.
6. Neighbors, sheep and details.

Each step is checked with screenshots against the references before moving on.
