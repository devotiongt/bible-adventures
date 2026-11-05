"""Converts a village from Watabou's Village Generator (exported as JSON) to data/village.json.

Usage:
    python3 tools/watabou_to_village.py references/watabou_village11.json data/village.json [view.png]

From the generator we take the layout: the river, the streets, the plaza, where each house goes, the
fields and the trees. What belongs to the story is placed by hand (ADJUSTMENTS): Noah's house, the ark
meadow, the quarry, the pitch pits, the pens and the road to the ark. The view (optional, needs
Pillow) draws the result with the real size of our houses and their yards, to check it before the game.

Generator coordinates: units ~meters, y to the north. Game coordinates: meters, x to the east,
z to the south (north = -z), with the center of the plaza at the origin.
"""

import json
import math
import sys

SCALE = 0.6                  # The generator's houses measure 7-16 u; ours, 4-9 m.
ORIGIN = (1.0, 0.8)          # Center of the plaza in the generator.
RIVER_WIDTH = 8.0
RIVER_DEPTH = 1.5

# What the generator doesn't know (in generator coordinates).
ADJUSTMENTS = {
    "noah_house": (-49.8, 15.4),        # The big house northwest of the plaza, on the ark road.
    "family": {(-37.4, 23.5): "shem", (-28.9, 1.5): "ham", (-2.3, 33.6): "japheth"},
    "neighbors": {(29.3, 21.0): "potter_neighbor", (39.9, 63.7 - 3.0): "weaver_neighbor",
                  (8.9, 30.1): "baker_neighbor", (52.0, -17.0): "shepherd_neighbor"},
    "ark": (-128.0, 100.0),             # The ark meadow, to the northwest, beyond the forest.
    "ark_road": [(-14.0, 15.0), (-30.0, 33.0), (-55.0, 50.0), (-80.0, 68.0), (-100.0, 84.0), (-112.0, 92.0)],
    "fields_remove": [6, 12],           # The ones under the ark meadow (generator indices).
    "fields_extra": [((-150.0, 15.0), (42.0, 30.0), 35.0)],   # The south piece of the removed field.
    "gardens": [10],                    # The small field next to the northern houses.
    "quarry": (-82.3, 120.8),           # North of the forest, halfway to the ark.
    "pitch": [(-100.0, 112.0), (-150.0, 75.0), (-95.0, 135.0)],  # Next to the ark meadow.
    "pens": [(-8.0, 52.0), (-48.0, -60.0), (70.0, -100.0)],
    "logging": [(-35.0, 22.0), (-100.0, 90.0)],   # Box of the forest that gets cut down (x0, y0, x1, y1 below).
    # Already in game coordinates: trails from the nearest street to what has no path, and an olive
    # grove in rows in the empty meadow to the west ((center, (length, width), rotation, rows)).
    "trails": {"quarry trail": [(-48.6, -40.3), (-49.0, -55.0), (-50.0, -66.0)],
               "olive grove trail": [(-33.6, -29.5), (-50.0, -31.0), (-65.0, -31.0), (-76.0, -32.0)],
               "north pen trail": [(-18.6, -19.3), (-12.0, -24.0), (-7.0, -27.0)],
               "river pen trail": [(-42.6, 13.7), (-38.0, 24.0), (-32.0, 32.0)],
               "south pen trail": [(-2.5, 36.9), (12.0, 47.0), (28.0, 56.0), (37.0, 59.0)]},
    # Houses removed by hand (no_collisions uses the street of straight points; the game, the curve, and
    # some turn differently and end up touching).
    "houses_remove": ["house_35"],
    "olive_groves": [((-88.0, -32.0), (24.0, 14.0), 0.0, 3)],
}


def to_game(p):
    return [round((p[0] - ORIGIN[0]) * SCALE, 2), round(-(p[1] - ORIGIN[1]) * SCALE, 2)]


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def seg_dist(p, a, b):
    ab = (b[0] - a[0], b[1] - a[1])
    l2 = ab[0] ** 2 + ab[1] ** 2
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) / l2))
    return dist(p, (a[0] + ab[0] * t, a[1] + ab[1] * t))


def poly_dist(p, pts):
    return min(seg_dist(p, pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def inside(p, poly):
    c = False
    for i in range(len(poly)):
        a, b = poly[i], poly[i - 1]
        if (a[1] > p[1]) != (b[1] > p[1]) and p[0] < (b[0] - a[0]) * (p[1] - a[1]) / (b[1] - a[1]) + a[0]:
            c = not c
    return c


def resample(pts, step):
    """Points every `step` along the polyline."""
    out = [pts[0]]
    acc = 0.0
    for a, b in zip(pts, pts[1:]):
        d = dist(a, b)
        while acc + d >= step:
            t = (step - acc) / d
            a = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            d = dist(a, b)
            out.append(a)
            acc = 0.0
        acc += d
    if dist(out[-1], pts[-1]) > step * 0.3:
        out.append(pts[-1])
    return out


def river_centerline(water, ext):
    """The water is a polygon: one bank going and the other coming back, with the ends on the edge of
    the map. It is split at those ends and the two banks are averaged at the same fraction of the length."""
    # The four edge points, in order: e0 -> e1 is one bank; e1 -> e2, the map edge; e2 -> e3,
    # the other bank; e3 -> e0, the edge again.
    e0, e1, e2, e3 = sorted(i for i, p in enumerate(water) if any(dist(p, e) < 0.2 for e in ext))[:4]
    bank_a = water[e0:e1 + 1]
    bank_b = list(reversed(water[e2:e3 + 1]))
    n = 40
    a = resample(bank_a, sum(dist(p, q) for p, q in zip(bank_a, bank_a[1:])) / n)
    b = resample(bank_b, sum(dist(p, q) for p, q in zip(bank_b, bank_b[1:])) / n)
    m = min(len(a), len(b))
    return [((a[i][0] + b[i][0]) / 2, (a[i][1] + b[i][1]) / 2) for i in range(m)]


def obb(poly, shrink=0.85):
    """Rotated rectangle that covers the polygon (the smallest-area one among the polygon's sides),
    shrunk a bit so it doesn't stick out of its edges. -> center, (length, width), rotation in degrees."""
    best = None
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        ang = math.atan2(b[1] - a[1], b[0] - a[0])
        ca, sa = math.cos(-ang), math.sin(-ang)
        xs = [p[0] * ca - p[1] * sa for p in poly]
        ys = [p[0] * sa + p[1] * ca for p in poly]
        area = (max(xs) - min(xs)) * (max(ys) - min(ys))
        if best is None or area < best[0]:
            cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
            c = (cx * math.cos(ang) - cy * math.sin(ang), cx * math.sin(ang) + cy * math.cos(ang))
            best = (area, c, (max(xs) - min(xs)) * shrink, (max(ys) - min(ys)) * shrink, ang)
    return best[1], (best[2], best[3]), math.degrees(best[4])


def main():
    src, out = sys.argv[1], sys.argv[2]
    preview = sys.argv[3] if len(sys.argv) > 3 else None
    F = {f["id"]: f for f in json.load(open(src))["features"]}
    houses = [b[0] for b in F["buildings"]["coordinates"]]
    roads = [[tuple(p) for p in r["coordinates"]] for r in F["roads"]["geometries"] if len(r["coordinates"]) > 1]
    square = [tuple(p) for p in F["squares"]["coordinates"][0][0]]
    water = [tuple(p) for p in F["water"]["coordinates"][0][0]]
    river = river_centerline(water, [tuple(p) for p in F["extendable"]["coordinates"]])
    fields = [[tuple(p) for p in f[0]] for f in F["fields"]["coordinates"]]
    trees = [tuple(p) for p in F["trees"]["coordinates"]]
    earth = F["earth"]["coordinates"][0]
    half = (max(p[0] for p in earth) * SCALE, max(p[1] for p in earth) * SCALE)

    # Streets: the ones touching the plaza are wide streets; the rest, alleys.
    paths = []
    for i, r in enumerate(roads):
        main_street = min(dist(r[0], q) for q in square) < 2 or min(dist(r[-1], q) for q in square) < 2
        pts = resample(r, 14.0)
        paths.append({"name": f"street {i + 1}" if main_street else f"alley {i + 1}",
                      "type": "street" if main_street else "alley", "width": 2.8 if main_street else 2.0,
                      "points": [to_game(p) for p in pts]})
    paths.append({"name": "ark road", "type": "street", "width": 2.6,
                  "points": [to_game(p) for p in ADJUSTMENTS["ark_road"]]})
    for name, pts in ADJUSTMENTS["trails"].items():
        paths.append({"name": name, "type": "trail", "width": 1.0, "points": [list(p) for p in pts]})

    # Bridges: where a street crosses the river line.
    bridges = []
    for r in roads:
        for a, b in zip(r, r[1:]):
            for c, d in zip(river, river[1:]):
                den = (b[0] - a[0]) * (d[1] - c[1]) - (b[1] - a[1]) * (d[0] - c[0])
                if abs(den) < 1e-9:
                    continue
                t = ((c[0] - a[0]) * (d[1] - c[1]) - (c[1] - a[1]) * (d[0] - c[0])) / den
                u = ((c[0] - a[0]) * (b[1] - a[1]) - (c[1] - a[1]) * (b[0] - a[0])) / den
                if 0 <= t <= 1 and 0 <= u <= 1:
                    p = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
                    g = to_game(p)
                    dx, dz = (b[0] - a[0]), -(b[1] - a[1])
                    bridges.append({"center": g, "length": RIVER_WIDTH + 5.0, "width": 2.6,
                                    "rotation": round(math.degrees(math.atan2(-dz, dx)), 1)})   # Godot Y rotation.

    # Houses: the model by shape (the long and deep ones, HouseC; the big ones, HouseB; the rest, HouseA).
    named = {**ADJUSTMENTS["family"], **ADJUSTMENTS["neighbors"]}
    houses_out = []
    for k, q in enumerate(houses):
        c = (sum(p[0] for p in q) / 4, sum(p[1] for p in q) / 4)
        e1, e2 = dist(q[0], q[1]) * SCALE, dist(q[1], q[2]) * SCALE
        long_side, short_side = max(e1, e2), min(e1, e2)
        if dist(c, ADJUSTMENTS["noah_house"]) < 3:
            model, hid = "NoahHouse", "noah"
        else:
            hid = next((v for p, v in named.items() if dist(c, p) < 4), f"house_{k + 1}")
            model = "HouseC" if long_side > 7.5 and short_side < 4.6 else ("HouseB" if long_side * short_side > 26 else "HouseA")
        house = {"id": hid, "model": model, "pos": to_game(c), "yard": 0.6, "rotation": 0}
        if hid == "potter_neighbor":
            house["stall"] = True
        houses_out.append(house)
    houses_out = no_collisions(houses_out, paths, sq_c=to_game(ORIGIN))
    houses_out.sort(key=lambda h: h["id"] != "noah")    # Noah first: the game starts there.

    # Fields (rotated rectangles) and gardens.
    fields_out, gardens = [], []
    for i, f in enumerate(fields):
        if i in ADJUSTMENTS["fields_remove"]:
            continue
        c, (lx, ly), ang = obb(f)
        entry = {"center": to_game(c), "size": [round(lx * SCALE, 1), round(ly * SCALE, 1)],
                 "rotation": round(-ang, 1)}
        if i in ADJUSTMENTS["gardens"]:
            entry["rows"] = max(3, int(entry["size"][1] / 1.6))
            gardens.append(entry)
        else:
            entry["furrows"] = max(3, int(entry["size"][1] / 2.2))
            fields_out.append(entry)
    for c, size, ang in ADJUSTMENTS["fields_extra"]:
        fields_out.append({"center": to_game(c), "size": [size[0] * SCALE, size[1] * SCALE], "rotation": -ang,
                           "furrows": max(3, int(size[1] * SCALE / 2.2))})

    # Trees: the ones in the nearby forest get cut down (in groups); the rest are decoration. The ones that
    # fall in the ark meadow, the quarry or a pen are removed.
    (x0, y0), (x1, y1) = ADJUSTMENTS["logging"]
    ark = ADJUSTMENTS["ark"]
    keep_out = [(ark, 50.0), (ADJUSTMENTS["quarry"], 14.0)] + [(c, 12.0) for c in ADJUSTMENTS["pens"]]
    felled, decor = [], []
    for t in trees:
        if any(dist(t, c) < r for c, r in keep_out) or any(inside(t, f) for f in fields):
            continue
        (felled if min(x0, x1) <= t[0] <= max(x0, x1) and min(y0, y1) <= t[1] <= max(y0, y1) else decor).append(t)
    groups = []
    for t in felled:
        g = next((g for g in groups if dist(g["c"], t) < 18), None)
        if g:
            g["pts"].append(t)
            g["c"] = (sum(p[0] for p in g["pts"]) / len(g["pts"]), sum(p[1] for p in g["pts"]) / len(g["pts"]))
        else:
            groups.append({"c": t, "pts": [t]})
    forest = [{"center": to_game(g["c"]), "radius": round(max(5.0, max(dist(g["c"], p) for p in g["pts"]) * SCALE + 2), 1),
               "trees": len(g["pts"])} for g in groups]

    sq = to_game((sum(p[0] for p in square) / len(square), sum(p[1] for p in square) / len(square)))
    plaza = build_plaza(sq, max(dist(p, ORIGIN) for p in square) * SCALE, paths)
    data = {
        "_note": "Village generated with Watabou's Village Generator (references/watabou_village11.json, "
                 "tools/watabou_to_village.py) and adapted to the story. Meters; x to the east, z to the "
                 "south (north = -z). Don't hand-edit what comes out of the generator: change ADJUSTMENTS and "
                 "regenerate.",
        "area": [round(-half[0] - 24, 1), round(-half[1] - 24, 1), round(half[0] + 24, 1), round(half[1] + 24, 1)],
        "valley": {"center": [0, 0], "semi_axes": [round(half[0] + 6, 1), round(half[1] + 6, 1)], "shape": 4.0,
                   "waves": [[2, 0.03, 0.6], [3, 0.025, 2.1], [5, 0.015, 4.0]],
                   "hill_height": 9.0, "hill_width": 18.0},
        "river": {"points": [to_game(p) for p in river[::2] + [river[-1]]], "width": RIVER_WIDTH,
                  "depth": RIVER_DEPTH},
        "bridges": bridges,
        "plaza": plaza,
        "ark": {"center": to_game(ark), "semi_axes": [15, 10], "height": 0.2, "hill": 8.0},   # Flat meadow.
        "houses": houses_out,
        "paths": paths,
        "forest": forest,
        "trees": [to_game(t) for t in decor],
        "quarry": {"center": to_game(ADJUSTMENTS["quarry"]), "radius": 6.0, "rocks": 7},
        "pitch": [to_game(p) for p in ADJUSTMENTS["pitch"]],
        "gardens": gardens,
        "fields": fields_out,
        "pens": [{"center": to_game(c), "radius": 4.5} for c in ADJUSTMENTS["pens"]],
        "shade_trees": [{"pos": plaza["island"]["center"], "type": "olive", "scale": 1.6}]
                       + [{"pos": p, "type": "round", "scale": 1.0} for p in plaza.pop("trees")]
                       + olive_rows(),
        "walls": [],
        # The family and the villagers, with their points in their yard's coordinates (x across, y toward
        # the facade) and what they do at each one (scripts/villager.gd).
        "villagers": [{"id": "wife", "house": "noah", "model": "res://assets/characters/family/wife_rig.glb",
                       "prefix": "Wife_", "speed": 0.627, "shine": 1.0, "actions": ["Idle", "Idle_Talking", "Interact"],
                       "points": [[-1.8, 5.0], [1.8, 5.4], [0.8, 4.2]]}],
        "animals": [["Donkey", *to_game(ADJUSTMENTS["pens"][0])], ["Alpaca", *to_game(ADJUSTMENTS["pens"][1])],
                    ["Cow", *to_game(ADJUSTMENTS["pens"][2])], ["Deer", *to_game((-75.0, 30.0))],
                    ["Horse", *to_game((95.0, -110.0))], ["Fox", *to_game((60.0, 110.0))]],
    }
    json.dump(data, open(out, "w"), ensure_ascii=False, indent="\t")
    print("houses", len(houses_out), "paths", len(paths), "bridges", len(bridges), "fields", len(fields_out),
          "gardens", len(gardens), "forest", [g["trees"] for g in forest], "decor", len(decor))
    if preview:
        draw(data, preview)


# Plaza (references/plaza_gemini.jpg): dirt (the same as the paths) and an irregular shape where the
# streets arrive; in the middle, a grass island with the olive tree and benches; the well to the west, two
# campfires to the southeast, a long table to the south; the market around the edge (wooden, tarp and
# gabled stalls, each one between two streets) and, inside, the wanderers: cart, blankets on the ground,
# crates and barrels; two trees in the gaps of the edge.
PLAZA_RADIUS = 13.5
STALLS = ["TarpCream", "fruit_stall", "TentPeakBlue", "TarpBlue", "cloth_stall", "TarpGray", "TentPeakCream",
          "TarpGreen", "cloth_stall2", "Stall", "TarpSage"]
WANDERERS = ["Cart", "BlanketRed", "Crates", "Barrels", "BlanketBlue", "Crates", "Barrels", "Cart"]


def build_plaza(c, old_radius, paths):
    def gap(a, b):
        return abs((a - b + math.pi) % (2 * math.pi) - math.pi)

    # Where the streets come in (their point closest to the plaza). The street is extended into the
    # plaza, and the plaza widens a bit toward each street (the ground worn by foot traffic).
    entries = []
    for k in paths:
        for end in (0, -1):
            p = k["points"][end]
            if dist(p, c) < old_radius + 4:
                a = math.atan2(p[1] - c[1], p[0] - c[0])
                entries.append(a)
                inner = [round(c[0] + math.cos(a) * PLAZA_RADIUS * 0.75, 2), round(c[1] + math.sin(a) * PLAZA_RADIUS * 0.75, 2)]
                if end == 0:
                    k["points"].insert(0, inner)
                else:
                    k["points"].append(inner)

    def radius(a):
        r = PLAZA_RADIUS * (1 + 0.1 * math.sin(2 * a + 0.7) + 0.07 * math.sin(3 * a + 2.1) + 0.04 * math.sin(5 * a + 0.4))
        return r + sum(2.5 * math.exp(-(gap(a, e) / 0.28) ** 2) for e in entries)

    def at(a, r):
        return [round(c[0] + math.cos(a) * r, 2), round(c[1] + math.sin(a) * r, 2)]

    outline = [at(2 * math.pi * k / 32, radius(2 * math.pi * k / 32)) for k in range(32)]
    well_a, fire_a, fire2_a, table_a = math.pi + 0.3, 0.45, 1.4, math.pi / 2 + 0.6

    busy = [(e, 0.26) for e in entries] + [(fire_a, 0.3), (fire2_a, 0.25), (table_a, 0.25), (well_a, 0.22)]
    tents = []
    for k in range(144):
        if len(tents) == len(STALLS):
            break
        a = 2 * math.pi * k / 144 - math.pi / 2
        if all(gap(a, b) > w for b, w in busy) and all(gap(a, t) > 0.33 for t, _ in tents):
            tents.append((a, STALLS[len(tents)]))
    free = [2 * math.pi * k / 36 for k in range(36)]
    free = [a for a in free if all(gap(a, e) > 0.35 for e in entries) and all(gap(a, t) > 0.3 for t, _ in tents)]
    trees = [free[0], free[len(free) // 2]] if len(free) > 1 else free
    # Market bundles between one stall and the next (sacks, baskets, jugs), a bit inside the edge.
    order = sorted(a for a, _ in tents)
    goods = ["Sack", "Basket", "Jug"]
    bundles = []
    for i, a in enumerate(order):
        b = order[(i + 1) % len(order)] + (2 * math.pi if i == len(order) - 1 else 0)
        mid = (a + b) / 2
        if all(gap(mid, e) > 0.3 for e in entries) and gap(mid, fire_a) > 0.4 and gap(mid, table_a) > 0.3:
            bundles.append(at(mid, radius(mid) - 1.6) + [goods[i % 3]])
        for side in (-1, 1):            # And to one side of each stall.
            s_a = a + side * 0.24
            if all(gap(s_a, e) > 0.3 for e in entries):
                bundles.append(at(s_a, radius(s_a) - 1.3) + [goods[(i + side + 3) % 3]])
    # The stalls that don't fit on the edge form a second row, further in, in the gaps left by the
    # streets, the well, the campfires and the table.
    inner_busy = [(e, 0.2) for e in entries] + [(well_a, 0.4), (fire_a, 0.45), (fire2_a, 0.45), (table_a, 0.35)]
    inner_stalls = []
    for a in (0.2, 0.75, -1.2, 2.6):     # Gaps on the east side (between the campfires and the streets), by hand.
        if len(tents) + len(inner_stalls) == len(STALLS):
            break
        if all(gap(a, e) > 0.25 for e in entries) and all(gap(a, t) > 0.3 for t, _ in tents + inner_stalls) \
                and gap(a, well_a) > 0.4 and gap(a, table_a) > 0.3:
            inner_stalls.append((a, STALLS[len(tents) + len(inner_stalls)]))
    inner_busy += [(a, 0.35) for a, _ in inner_stalls]
    # Wanderers, inside the market, out of the way of the streets and far from the well, campfires and table.
    wanderers = []
    for k in range(48):
        if len(wanderers) == len(WANDERERS):
            break
        a = 2 * math.pi * k / 48 + 0.2
        if all(gap(a, b) > w for b, w in inner_busy) and all(gap(a, t) > 0.42 for t, _ in wanderers):
            wanderers.append((a, WANDERERS[len(wanderers)]))
    isle_c = at(-math.pi / 2 + 0.3, PLAZA_RADIUS * 0.1)
    return {
        "center": c, "outline": outline, "ground": "dirt",
        "island": {"center": isle_c, "radius": 3.2, "benches": 3},
        "well": at(well_a, PLAZA_RADIUS * 0.5),
        "campfires": [at(fire_a, PLAZA_RADIUS * 0.45), at(fire2_a, PLAZA_RADIUS * 0.62)],
        "tables": [at(table_a, PLAZA_RADIUS * 0.45)],
        "tents": [at(a, radius(a) - 2.4) + [m] for a, m in tents]
                 + [at(a, radius(a) * 0.7) + [m] for a, m in inner_stalls],
        "wanderers": [at(a, radius(a) * 0.62) + [m] for a, m in wanderers],
        "bundles": bundles,
        "trees": [at(a, radius(a) + 1.0) for a in trees],
    }


def olive_rows():
    """Olive trees in rows, 5 m apart, the way they are planted."""
    out = []
    for (cx, cz), (lx, lz), turn, rows in ADJUSTMENTS["olive_groves"]:
        t = math.radians(turn)
        n = int(lx // 5) + 1
        for r in range(rows):
            for i in range(n):
                x, z = -lx / 2 + i * lx / max(1, n - 1), -lz / 2 + r * lz / max(1, rows - 1)
                out.append({"pos": [round(cx + x * math.cos(t) - z * math.sin(t), 2),
                                    round(cz + x * math.sin(t) + z * math.cos(t), 2)], "type": "olive", "scale": 0.85})
    return out


HOUSE_SIZE = {"HouseA": (5.6, 3.8, 2.3), "HouseB": (5.6, 4.2, 4.7), "HouseC": (4.4, 8.0, 2.4), "NoahHouse": (8.8, 5.0, 6.6)}
HOUSE_CX = {"HouseA": 0.45, "HouseB": 0.0, "HouseC": 0.0, "NoahHouse": 0.3}     # As in world.gd (center_x).
SEPARATION = 1.6               # Minimum distance between two houses with their yards (an alley).


def facing(p, streets):
    """House rotation: the facade faces the nearest street or alley (like world.gd, house_angle)."""
    best, near = 1e9, (p[0], p[1] + 1)
    for pts in streets:
        for a_, b_ in zip(pts, pts[1:]):
            ab = (b_[0] - a_[0], b_[1] - a_[1])
            l2 = ab[0] ** 2 + ab[1] ** 2
            t = max(0, min(1, ((p[0] - a_[0]) * ab[0] + (p[1] - a_[1]) * ab[1]) / l2))
            q = (a_[0] + ab[0] * t, a_[1] + ab[1] * t)
            if dist(p, q) < best:
                best, near = dist(p, q), q
    return math.atan2(near[0] - p[0], near[1] - p[1])


def footprint(h, streets, grow=0.0):
    """Corners of the house with its yard in front (like world.gd, _house_rects), enlarged by `grow`."""
    w, d, front = HOUSE_SIZE[h["model"]]
    cx = HOUSE_CX[h["model"]]
    ang = facing(h["pos"], streets)
    x0, x1 = cx - w / 2 - grow, cx + w / 2 + grow
    y0, y1 = -d / 2 - grow, front + h["yard"] + grow
    out = []
    for lx, ly in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        # Godot Y rotation: the local +Y axis (the facade) points to (sin, cos).
        out.append((h["pos"][0] + lx * math.cos(ang) + ly * math.sin(ang),
                    h["pos"][1] - lx * math.sin(ang) + ly * math.cos(ang)))
    return out


def _overlap(a, b):
    """Do two rotated rectangles touch? (separating axes)."""
    for poly in (a, b):
        for i in range(4):
            e = (poly[(i + 1) % 4][0] - poly[i][0], poly[(i + 1) % 4][1] - poly[i][1])
            n = (-e[1], e[0])
            pa = [p[0] * n[0] + p[1] * n[1] for p in a]
            pb = [p[0] * n[0] + p[1] * n[1] for p in b]
            if max(pa) < min(pb) or max(pb) < min(pa):
                return False
    return True


def no_collisions(houses, paths, sq_c):
    """Removes the houses that overlap another or are closer than SEPARATION (with their yards). Noah's,
    the family's and the named neighbors' are kept first, and then the ones closest to the plaza."""
    streets = [k["points"] for k in paths if k["type"] != "trail"]
    order = sorted(houses, key=lambda h: (h["id"].startswith("house_"), dist(h["pos"], sq_c)))
    kept, shapes = [], []
    for h in order:
        if h["id"] in ADJUSTMENTS["houses_remove"]:
            continue
        f = footprint(h, streets, SEPARATION / 2)
        if any(_overlap(f, g) for g in shapes):
            print("  house removed for colliding:", h["id"], h["pos"])
            continue
        kept.append(h)
        shapes.append(f)
    return kept


def draw(data, path):
    from PIL import Image, ImageDraw
    x0, z0, x1, z1 = data["area"]
    S = 4
    im = Image.new("RGB", (int((x1 - x0) * S), int((z1 - z0) * S)), (170, 205, 130))
    g = ImageDraw.Draw(im)
    P = lambda p: ((p[0] - x0) * S, (p[1] - z0) * S)
    ax, az = data["valley"]["semi_axes"]
    g.rectangle([P((-ax, -az)), P((ax, az))], outline=(120, 150, 90), width=3)

    def rect(c, size, ang_deg, fill, outline=None):
        a = math.radians(ang_deg)
        pts = []
        for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            lx, lz = sx * size[0] / 2, sz * size[1] / 2
            pts.append(P((c[0] + lx * math.cos(a) - lz * math.sin(a), c[1] + lx * math.sin(a) + lz * math.cos(a))))
        g.polygon(pts, fill=fill, outline=outline)

    for f in data["fields"]:
        rect(f["center"], f["size"], f["rotation"], (205, 185, 130))
    for f in data["gardens"]:
        rect(f["center"], f["size"], f["rotation"], (150, 175, 90))
    a = data["ark"]
    c, s = a["center"], a["semi_axes"]
    L = a["hill"]
    g.ellipse([P((c[0] - s[0] - L, c[1] - s[1] - L)), P((c[0] + s[0] + L, c[1] + s[1] + L))], fill=(185, 200, 130))
    g.ellipse([P((c[0] - s[0], c[1] - s[1])), P((c[0] + s[0], c[1] + s[1]))], fill=(225, 205, 160))
    g.rectangle([P((c[0] - 11, c[1] - 3)), P((c[0] + 11, c[1] + 3))], fill=(150, 100, 60))
    river = data["river"]["points"]
    g.line([P(p) for p in river], fill=(110, 165, 200), width=int(data["river"]["width"] * S), joint="curve")
    for k in data["paths"]:
        g.line([P(p) for p in k["points"]], fill=(225, 195, 140), width=int(k["width"] * S), joint="curve")
    g.polygon([P(p) for p in data["plaza"]["outline"]], fill=(220, 210, 190))
    for b in data["bridges"]:
        rect(b["center"], (b["length"], b["width"]), -b["rotation"], (150, 110, 70))
    for pen in data["pens"]:
        r = pen["radius"]
        cc = pen["center"]
        g.ellipse([P((cc[0] - r, cc[1] - r)), P((cc[0] + r, cc[1] + r))], outline=(140, 100, 60), width=3)
    q = data["quarry"]
    g.ellipse([P((q["center"][0] - q["radius"], q["center"][1] - q["radius"])),
               P((q["center"][0] + q["radius"], q["center"][1] + q["radius"]))], fill=(170, 165, 155))
    for p in data["pitch"]:
        g.ellipse([P((p[0] - 1.5, p[1] - 1.5)), P((p[0] + 1.5, p[1] + 1.5))], fill=(40, 30, 25))
    for t in data["trees"]:
        g.ellipse([P((t[0] - 1.6, t[1] - 1.6)), P((t[0] + 1.6, t[1] + 1.6))], fill=(80, 130, 80))
    for b in data["forest"]:
        cc, r = b["center"], b["radius"]
        g.ellipse([P((cc[0] - r, cc[1] - r)), P((cc[0] + r, cc[1] + r))], outline=(40, 100, 50), width=3)
    # Houses with their yard in front, facing the nearest street or alley (like world.gd).
    streets = [k["points"] for k in data["paths"]]
    for h in data["houses"]:
        p = h["pos"]
        best, near = 1e9, (p[0], p[1] + 1)
        for pts in streets:
            for a_, b_ in zip(pts, pts[1:]):
                ab = (b_[0] - a_[0], b_[1] - a_[1])
                l2 = ab[0] ** 2 + ab[1] ** 2
                t = max(0, min(1, ((p[0] - a_[0]) * ab[0] + (p[1] - a_[1]) * ab[1]) / l2))
                qq = (a_[0] + ab[0] * t, a_[1] + ab[1] * t)
                if dist(p, qq) < best:
                    best, near = dist(p, qq), qq
        ang = math.atan2(near[0] - p[0], near[1] - p[1])
        w, d, front = HOUSE_SIZE[h["model"]]
        # Rectangle of the house plus the yard in front, in world coordinates.
        cz = (front + h["yard"] - d / 2) / 2
        depth = front + h["yard"] + d / 2
        center = (p[0] + math.sin(ang) * cz, p[1] + math.cos(ang) * cz)
        rect(center, (w, depth), -math.degrees(ang), (225, 190, 150), (150, 100, 70))
        rect(p, (w, d), -math.degrees(ang), (200, 130, 85), (120, 70, 40))
        if h["id"] in ("noah", "shem", "ham", "japheth") or h["id"].endswith("_neighbor"):
            g.text((P(p)[0] + 10, P(p)[1] - 10), h["id"], fill=(60, 30, 20))
    im.save(path)


if __name__ == "__main__":
    main()
