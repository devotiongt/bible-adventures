"""Pasa una aldea del Village Generator de Watabou (exportada en JSON) a data/aldea.json.

Uso:
    python3 herramientas/watabou_a_aldea.py referencias/watabou_aldea11.json data/aldea.json [vista.png]

Del generador se toma la forma: el río, las calles, la plaza, dónde va cada casa, los campos y los
árboles. Lo propio de la historia se pone a mano (AJUSTES): la casa de Noé, el prado del arca, la
cantera, los pozos de brea, los corrales y el camino al arca. La vista (opcional, necesita Pillow)
dibuja el resultado con el tamaño real de nuestras casas y sus patios, para revisarlo antes del juego.

Coordenadas del generador: unidades ~metros, y hacia el norte. Las del juego: metros, x al este,
z al sur (norte = -z), con el centro de la plaza en el origen.
"""

import json
import math
import sys

ESCALA = 0.6                 # Las casas del generador miden 7-16 u; las nuestras, 4-9 m.
ORIGEN = (1.0, 0.8)          # Centro de la plaza en el generador.
RIO_ANCHO = 8.0
RIO_PROFUNDIDAD = 1.5

# Lo que el generador no sabe (en coordenadas del generador).
AJUSTES = {
    "casa_noe": (-49.8, 15.4),          # La casa grande al noroeste de la plaza, en el camino del arca.
    "familia": {(-37.4, 23.5): "sem", (-28.9, 1.5): "cam", (-2.3, 33.6): "jafet"},
    "vecinos": {(29.3, 21.0): "vecino_alfarero", (39.9, 63.7 - 3.0): "vecina_tejedora",
                (8.9, 30.1): "vecina_panadera", (52.0, -17.0): "vecino_pastor"},
    "arca": (-128.0, 100.0),            # Prado del arca, al noroeste, más allá del bosque.
    "camino_arca": [(-14.0, 15.0), (-30.0, 33.0), (-55.0, 50.0), (-80.0, 68.0), (-100.0, 84.0), (-112.0, 92.0)],
    "campos_quitar": [6, 12],           # Los que quedan bajo el prado del arca (índices del generador).
    "campos_extra": [((-150.0, 15.0), (42.0, 30.0), 35.0)],   # El trozo sur del campo quitado.
    "huertos": [10],                    # El campo pequeño junto a las casas del norte.
    "cantera": (-82.3, 120.8),          # Al norte del bosque, a medio camino del arca.
    "brea": [(-100.0, 112.0), (-150.0, 75.0), (-95.0, 135.0)],   # Junto al prado del arca.
    "corrales": [(-8.0, 52.0), (-48.0, -60.0), (70.0, -100.0)],
    "talar": [(-35.0, 22.0), (-100.0, 90.0)],   # Caja del bosque que se tala (x0, y0, x1, y1 abajo).
    # Ya en coordenadas del juego: sendas desde la calle más cercana hasta lo que no tiene camino, y un
    # olivar en hileras en el prado vacío del oeste ((centro, (largo, ancho), giro, hileras)).
    "sendas": {"senda de la cantera": [(-48.6, -40.3), (-49.0, -55.0), (-50.0, -66.0)],
               "senda del olivar": [(-33.6, -29.5), (-50.0, -31.0), (-65.0, -31.0), (-76.0, -32.0)],
               "senda del corral del norte": [(-18.6, -19.3), (-12.0, -24.0), (-7.0, -27.0)],
               "senda del corral del río": [(-42.6, 13.7), (-38.0, 24.0), (-32.0, 32.0)],
               "senda del corral del sur": [(-2.5, 36.9), (12.0, 47.0), (28.0, 56.0), (37.0, 59.0)]},
    # Casas que se quitan a mano (sin_choques usa la calle de puntos rectos; el juego, la curva, y alguna
    # se gira distinto y queda pegada).
    "casas_quitar": ["casa_35"],
    "olivares": [((-88.0, -32.0), (24.0, 14.0), 0.0, 3)],
}


def to_game(p):
    return [round((p[0] - ORIGEN[0]) * ESCALA, 2), round(-(p[1] - ORIGEN[1]) * ESCALA, 2)]


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
    """Puntos cada `step` a lo largo de la polilínea."""
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
    """El agua es un polígono: una orilla de ida y la otra de vuelta, con los extremos en el borde del
    mapa. Se parte por esos extremos y se promedian las dos orillas a la misma fracción del largo."""
    # Los cuatro puntos del borde, en orden: e0 → e1 es una orilla; e1 → e2, el borde del mapa; e2 → e3,
    # la otra orilla; e3 → e0, el borde de nuevo.
    e0, e1, e2, e3 = sorted(i for i, p in enumerate(water) if any(dist(p, e) < 0.2 for e in ext))[:4]
    bank_a = water[e0:e1 + 1]
    bank_b = list(reversed(water[e2:e3 + 1]))
    n = 40
    a = resample(bank_a, sum(dist(p, q) for p, q in zip(bank_a, bank_a[1:])) / n)
    b = resample(bank_b, sum(dist(p, q) for p, q in zip(bank_b, bank_b[1:])) / n)
    m = min(len(a), len(b))
    return [((a[i][0] + b[i][0]) / 2, (a[i][1] + b[i][1]) / 2) for i in range(m)]


def obb(poly, shrink=0.85):
    """Rectángulo girado que cubre el polígono (el de menor área entre los lados del polígono),
    algo encogido para que no se salga de sus bordes. -> centro, (largo, ancho), giro en grados."""
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
    half = (max(p[0] for p in earth) * ESCALA, max(p[1] for p in earth) * ESCALA)

    # Calles: las que tocan la plaza son calles anchas; las demás, callejones.
    caminos = []
    for i, r in enumerate(roads):
        main_street = min(dist(r[0], q) for q in square) < 2 or min(dist(r[-1], q) for q in square) < 2
        pts = resample(r, 14.0)
        caminos.append({"nombre": f"calle {i + 1}" if main_street else f"callejón {i + 1}",
                        "tipo": "calle" if main_street else "callejon", "ancho": 2.8 if main_street else 2.0,
                        "puntos": [to_game(p) for p in pts]})
    caminos.append({"nombre": "camino del arca", "tipo": "calle", "ancho": 2.6,
                    "puntos": [to_game(p) for p in AJUSTES["camino_arca"]]})
    for name, pts in AJUSTES["sendas"].items():
        caminos.append({"nombre": name, "tipo": "senda", "ancho": 1.0, "puntos": [list(p) for p in pts]})

    # Puentes: donde una calle cruza la línea del río.
    puentes = []
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
                    puentes.append({"centro": g, "largo": RIO_ANCHO + 5.0, "ancho": 2.6,
                                    "giro": round(math.degrees(math.atan2(-dz, dx)), 1)})   # Giro en Y de Godot.

    # Casas: el modelo según la forma (las largas y hondas, CasaC; las grandes, CasaB; el resto, CasaA).
    named = {**AJUSTES["familia"], **AJUSTES["vecinos"]}
    casas = []
    for k, q in enumerate(houses):
        c = (sum(p[0] for p in q) / 4, sum(p[1] for p in q) / 4)
        e1, e2 = dist(q[0], q[1]) * ESCALA, dist(q[1], q[2]) * ESCALA
        long_side, short_side = max(e1, e2), min(e1, e2)
        if dist(c, AJUSTES["casa_noe"]) < 3:
            model, hid = "CasaNoe", "noe"
        else:
            hid = next((v for p, v in named.items() if dist(c, p) < 4), f"casa_{k + 1}")
            model = "CasaC" if long_side > 7.5 and short_side < 4.6 else ("CasaB" if long_side * short_side > 26 else "CasaA")
        casa = {"id": hid, "modelo": model, "pos": to_game(c), "patio": 0.6, "giro": 0}
        if hid == "vecino_alfarero":
            casa["puesto"] = True
        casas.append(casa)
    casas = sin_choques(casas, caminos, sq_c=to_game(ORIGEN))
    casas.sort(key=lambda h: h["id"] != "noe")          # Noé primero: ahí empieza el juego.

    # Campos (rectángulos girados) y huertos.
    campos, huertos = [], []
    for i, f in enumerate(fields):
        if i in AJUSTES["campos_quitar"]:
            continue
        c, (lx, ly), ang = obb(f)
        entry = {"centro": to_game(c), "tam": [round(lx * ESCALA, 1), round(ly * ESCALA, 1)],
                 "giro": round(-ang, 1)}
        if i in AJUSTES["huertos"]:
            entry["filas"] = max(3, int(entry["tam"][1] / 1.6))
            huertos.append(entry)
        else:
            entry["surcos"] = max(3, int(entry["tam"][1] / 2.2))
            campos.append(entry)
    for c, size, ang in AJUSTES["campos_extra"]:
        campos.append({"centro": to_game(c), "tam": [size[0] * ESCALA, size[1] * ESCALA], "giro": -ang,
                       "surcos": max(3, int(size[1] * ESCALA / 2.2))})

    # Árboles: los del bosque cercano se talan (en grupos); el resto adorna. Los que caen en el prado del
    # arca, la cantera o un corral se quitan.
    (x0, y0), (x1, y1) = AJUSTES["talar"]
    arca = AJUSTES["arca"]
    keep_out = [(arca, 50.0), (AJUSTES["cantera"], 14.0)] + [(c, 12.0) for c in AJUSTES["corrales"]]
    tala, adorno = [], []
    for t in trees:
        if any(dist(t, c) < r for c, r in keep_out) or any(inside(t, f) for f in fields):
            continue
        (tala if min(x0, x1) <= t[0] <= max(x0, x1) and min(y0, y1) <= t[1] <= max(y0, y1) else adorno).append(t)
    groups = []
    for t in tala:
        g = next((g for g in groups if dist(g["c"], t) < 18), None)
        if g:
            g["pts"].append(t)
            g["c"] = (sum(p[0] for p in g["pts"]) / len(g["pts"]), sum(p[1] for p in g["pts"]) / len(g["pts"]))
        else:
            groups.append({"c": t, "pts": [t]})
    bosque = [{"centro": to_game(g["c"]), "radio": round(max(5.0, max(dist(g["c"], p) for p in g["pts"]) * ESCALA + 2), 1),
               "arboles": len(g["pts"])} for g in groups]

    sq = to_game((sum(p[0] for p in square) / len(square), sum(p[1] for p in square) / len(square)))
    plaza = build_plaza(sq, max(dist(p, ORIGEN) for p in square) * ESCALA, caminos)
    data = {
        "_nota": "Aldea generada con el Village Generator de Watabou (referencias/watabou_aldea11.json, "
                 "herramientas/watabou_a_aldea.py) y adaptada a la historia. Metros; x hacia el este, z hacia "
                 "el sur (norte = -z). No editar a mano lo que sale del generador: cambiar AJUSTES y volver a "
                 "generar.",
        "area": [round(-half[0] - 24, 1), round(-half[1] - 24, 1), round(half[0] + 24, 1), round(half[1] + 24, 1)],
        "valle": {"centro": [0, 0], "semiejes": [round(half[0] + 6, 1), round(half[1] + 6, 1)], "forma": 4.0,
                  "ondas": [[2, 0.03, 0.6], [3, 0.025, 2.1], [5, 0.015, 4.0]],
                  "altura_colinas": 9.0, "ancho_colinas": 18.0},
        "rio": {"puntos": [to_game(p) for p in river[::2] + [river[-1]]], "ancho": RIO_ANCHO,
                "profundidad": RIO_PROFUNDIDAD},
        "puentes": puentes,
        "plaza": plaza,
        "arca": {"centro": to_game(arca), "semiejes": [15, 10], "altura": 0.2, "loma": 8.0},   # Prado llano.
        "casas": casas,
        "caminos": caminos,
        "bosque": bosque,
        "arboles": [to_game(t) for t in adorno],
        "cantera": {"centro": to_game(AJUSTES["cantera"]), "radio": 6.0, "rocas": 7},
        "brea": [to_game(p) for p in AJUSTES["brea"]],
        "huertos": huertos,
        "campos": campos,
        "corrales": [{"centro": to_game(c), "radio": 4.5} for c in AJUSTES["corrales"]],
        "arboles_de_sombra": [{"pos": plaza["isla"]["centro"], "tipo": "olivo", "escala": 1.6}]
                             + [{"pos": p, "tipo": "redondo", "escala": 1.0} for p in plaza.pop("arboles")]
                             + olive_rows(),
        "muros": [],
        # La familia y los aldeanos, con sus puntos en coordenadas de su patio (x a lo ancho, y hacia la
        # fachada) y lo que hacen en cada uno (scripts/aldeano.gd).
        "aldeanos": [{"id": "esposa", "casa": "noe", "modelo": "res://assets/personajes/familia/esposa_rig.glb",
                      "prefijo": "Esposa_", "velocidad": 0.627, "brillo": 1.0, "acciones": ["Idle", "Idle_Talking", "Interact"],
                      "puntos": [[-1.8, 5.0], [1.8, 5.4], [0.8, 4.2]]}],
        "animales": [["Donkey", *to_game(AJUSTES["corrales"][0])], ["Alpaca", *to_game(AJUSTES["corrales"][1])],
                     ["Cow", *to_game(AJUSTES["corrales"][2])], ["Deer", *to_game((-75.0, 30.0))],
                     ["Horse", *to_game((95.0, -110.0))], ["Fox", *to_game((60.0, 110.0))]],
    }
    json.dump(data, open(out, "w"), ensure_ascii=False, indent="\t")
    print("casas", len(casas), "caminos", len(caminos), "puentes", len(puentes), "campos", len(campos),
          "huertos", len(huertos), "bosque", [g["arboles"] for g in bosque], "adorno", len(adorno))
    if preview:
        draw(data, preview)


# Plaza (referencias/plaza_gemini.jpg): de tierra (la de los caminos) y forma irregular donde llegan las
# calles; en medio, una isla de pasto con el olivo y bancos; el pozo al oeste, dos fogatas al sudeste, una
# mesa larga al sur; el mercado alrededor del borde (puestos de madera, de lona y a dos aguas, cada uno
# entre dos calles) y, por dentro, los ambulantes: carreta, mantas en el suelo, cajas y barriles; dos
# árboles en los huecos del borde.
PLAZA_RADIO = 13.5
PUESTOS = ["LonaCrema", "puesto_frutas", "TiendaPicoAzul", "LonaAzul", "puesto_telas", "LonaGris", "TiendaPicoCrema",
           "LonaVerde", "puesto_telas2", "Puesto", "LonaSalvia"]
AMBULANTES = ["Carreta", "MantaRoja", "Cajas", "Barriles", "MantaAzul", "Cajas", "Barriles", "Carreta"]


def build_plaza(c, old_radius, caminos):
    def gap(a, b):
        return abs((a - b + math.pi) % (2 * math.pi) - math.pi)

    # Por dónde entran las calles (su punto más cercano a la plaza). La calle se alarga hasta dentro de la
    # plaza, y la plaza se ensancha un poco hacia cada calle (el suelo gastado por el paso).
    entries = []
    for k in caminos:
        for end in (0, -1):
            p = k["puntos"][end]
            if dist(p, c) < old_radius + 4:
                a = math.atan2(p[1] - c[1], p[0] - c[0])
                entries.append(a)
                inner = [round(c[0] + math.cos(a) * PLAZA_RADIO * 0.75, 2), round(c[1] + math.sin(a) * PLAZA_RADIO * 0.75, 2)]
                if end == 0:
                    k["puntos"].insert(0, inner)
                else:
                    k["puntos"].append(inner)

    def radius(a):
        r = PLAZA_RADIO * (1 + 0.1 * math.sin(2 * a + 0.7) + 0.07 * math.sin(3 * a + 2.1) + 0.04 * math.sin(5 * a + 0.4))
        return r + sum(2.5 * math.exp(-(gap(a, e) / 0.28) ** 2) for e in entries)

    def at(a, r):
        return [round(c[0] + math.cos(a) * r, 2), round(c[1] + math.sin(a) * r, 2)]

    contorno = [at(2 * math.pi * k / 32, radius(2 * math.pi * k / 32)) for k in range(32)]
    well_a, fire_a, fire2_a, table_a = math.pi + 0.3, 0.45, 1.4, math.pi / 2 + 0.6

    busy = [(e, 0.26) for e in entries] + [(fire_a, 0.3), (fire2_a, 0.25), (table_a, 0.25), (well_a, 0.22)]
    tiendas = []
    for k in range(144):
        if len(tiendas) == len(PUESTOS):
            break
        a = 2 * math.pi * k / 144 - math.pi / 2
        if all(gap(a, b) > w for b, w in busy) and all(gap(a, t) > 0.33 for t, _ in tiendas):
            tiendas.append((a, PUESTOS[len(tiendas)]))
    free = [2 * math.pi * k / 36 for k in range(36)]
    free = [a for a in free if all(gap(a, e) > 0.35 for e in entries) and all(gap(a, t) > 0.3 for t, _ in tiendas)]
    trees = [free[0], free[len(free) // 2]] if len(free) > 1 else free
    # Bultos del mercado entre puesto y puesto (sacos, cestas, cántaros), algo hacia dentro del borde.
    order = sorted(a for a, _ in tiendas)
    goods = ["Saco", "Cesta", "Cantaro"]
    bultos = []
    for i, a in enumerate(order):
        b = order[(i + 1) % len(order)] + (2 * math.pi if i == len(order) - 1 else 0)
        mid = (a + b) / 2
        if all(gap(mid, e) > 0.3 for e in entries) and gap(mid, fire_a) > 0.4 and gap(mid, table_a) > 0.3:
            bultos.append(at(mid, radius(mid) - 1.6) + [goods[i % 3]])
        for side in (-1, 1):            # Y a un costado de cada puesto.
            s_a = a + side * 0.24
            if all(gap(s_a, e) > 0.3 for e in entries):
                bultos.append(at(s_a, radius(s_a) - 1.3) + [goods[(i + side + 3) % 3]])
    # Los puestos que no caben en el borde forman una segunda fila, más adentro, en los huecos que dejan
    # las calles, el pozo, las fogatas y la mesa.
    inner_busy = [(e, 0.2) for e in entries] + [(well_a, 0.4), (fire_a, 0.45), (fire2_a, 0.45), (table_a, 0.35)]
    inner_stalls = []
    for a in (0.2, 0.75, -1.2, 2.6):     # Huecos del lado este (entre las fogatas y las calles), a mano.
        if len(tiendas) + len(inner_stalls) == len(PUESTOS):
            break
        if all(gap(a, e) > 0.25 for e in entries) and all(gap(a, t) > 0.3 for t, _ in tiendas + inner_stalls) \
                and gap(a, well_a) > 0.4 and gap(a, table_a) > 0.3:
            inner_stalls.append((a, PUESTOS[len(tiendas) + len(inner_stalls)]))
    inner_busy += [(a, 0.35) for a, _ in inner_stalls]
    # Ambulantes, por dentro del mercado, fuera del paso de las calles y lejos del pozo, fogatas y mesa.
    ambulantes = []
    for k in range(48):
        if len(ambulantes) == len(AMBULANTES):
            break
        a = 2 * math.pi * k / 48 + 0.2
        if all(gap(a, b) > w for b, w in inner_busy) and all(gap(a, t) > 0.42 for t, _ in ambulantes):
            ambulantes.append((a, AMBULANTES[len(ambulantes)]))
    isle_c = at(-math.pi / 2 + 0.3, PLAZA_RADIO * 0.1)
    return {
        "centro": c, "contorno": contorno, "suelo": "tierra",
        "isla": {"centro": isle_c, "radio": 3.2, "bancos": 3},
        "pozo": at(well_a, PLAZA_RADIO * 0.5),
        "fogatas": [at(fire_a, PLAZA_RADIO * 0.45), at(fire2_a, PLAZA_RADIO * 0.62)],
        "mesas": [at(table_a, PLAZA_RADIO * 0.45)],
        "tiendas": [at(a, radius(a) - 2.4) + [m] for a, m in tiendas]
                   + [at(a, radius(a) * 0.7) + [m] for a, m in inner_stalls],
        "ambulantes": [at(a, radius(a) * 0.62) + [m] for a, m in ambulantes],
        "bultos": bultos,
        "arboles": [at(a, radius(a) + 1.0) for a in trees],
    }


def olive_rows():
    """Olivos en hileras, a 5 m uno de otro, como se plantan."""
    out = []
    for (cx, cz), (lx, lz), turn, rows in AJUSTES["olivares"]:
        t = math.radians(turn)
        n = int(lx // 5) + 1
        for r in range(rows):
            for i in range(n):
                x, z = -lx / 2 + i * lx / max(1, n - 1), -lz / 2 + r * lz / max(1, rows - 1)
                out.append({"pos": [round(cx + x * math.cos(t) - z * math.sin(t), 2),
                                    round(cz + x * math.sin(t) + z * math.cos(t), 2)], "tipo": "olivo", "escala": 0.85})
    return out


HOUSE_TAM = {"CasaA": (5.6, 3.8, 2.3), "CasaB": (5.6, 4.2, 4.7), "CasaC": (4.4, 8.0, 2.4), "CasaNoe": (8.8, 5.0, 6.6)}
HOUSE_CX = {"CasaA": 0.45, "CasaB": 0.0, "CasaC": 0.0, "CasaNoe": 0.3}     # Como en world.gd (centro_x).
SEPARACION = 1.6               # Distancia mínima entre dos casas con sus patios (un callejón).


def facing(p, streets):
    """Giro de la casa: la fachada mira a la calle o callejón más cercano (como world.gd, house_angle)."""
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
    """Esquinas de la casa con su patio delante (como world.gd, _house_rects), agrandadas `grow`."""
    w, d, front = HOUSE_TAM[h["modelo"]]
    cx = HOUSE_CX[h["modelo"]]
    ang = facing(h["pos"], streets)
    x0, x1 = cx - w / 2 - grow, cx + w / 2 + grow
    y0, y1 = -d / 2 - grow, front + h["patio"] + grow
    out = []
    for lx, ly in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        # Giro de Godot en Y: el eje local +Y (la fachada) apunta a (sin, cos).
        out.append((h["pos"][0] + lx * math.cos(ang) + ly * math.sin(ang),
                    h["pos"][1] - lx * math.sin(ang) + ly * math.cos(ang)))
    return out


def _overlap(a, b):
    """¿Se tocan dos rectángulos girados? (ejes separadores)."""
    for poly in (a, b):
        for i in range(4):
            e = (poly[(i + 1) % 4][0] - poly[i][0], poly[(i + 1) % 4][1] - poly[i][1])
            n = (-e[1], e[0])
            pa = [p[0] * n[0] + p[1] * n[1] for p in a]
            pb = [p[0] * n[0] + p[1] * n[1] for p in b]
            if max(pa) < min(pb) or max(pb) < min(pa):
                return False
    return True


def sin_choques(casas, caminos, sq_c):
    """Quita las casas que se enciman con otra o quedan a menos de SEPARACION (con sus patios). Se quedan
    antes la de Noé, la familia y los vecinos con nombre, y luego las más cercanas a la plaza."""
    streets = [k["puntos"] for k in caminos if k["tipo"] != "senda"]
    order = sorted(casas, key=lambda h: (h["id"].startswith("casa_"), dist(h["pos"], sq_c)))
    kept, shapes = [], []
    for h in order:
        if h["id"] in AJUSTES["casas_quitar"]:
            continue
        f = footprint(h, streets, SEPARACION / 2)
        if any(_overlap(f, g) for g in shapes):
            print("  casa quitada por chocar:", h["id"], h["pos"])
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
    ax, az = data["valle"]["semiejes"]
    g.rectangle([P((-ax, -az)), P((ax, az))], outline=(120, 150, 90), width=3)

    def rect(c, size, ang_deg, fill, outline=None):
        a = math.radians(ang_deg)
        pts = []
        for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            lx, lz = sx * size[0] / 2, sz * size[1] / 2
            pts.append(P((c[0] + lx * math.cos(a) - lz * math.sin(a), c[1] + lx * math.sin(a) + lz * math.cos(a))))
        g.polygon(pts, fill=fill, outline=outline)

    for f in data["campos"]:
        rect(f["centro"], f["tam"], f["giro"], (205, 185, 130))
    for f in data["huertos"]:
        rect(f["centro"], f["tam"], f["giro"], (150, 175, 90))
    a = data["arca"]
    c, s = a["centro"], a["semiejes"]
    L = a["loma"]
    g.ellipse([P((c[0] - s[0] - L, c[1] - s[1] - L)), P((c[0] + s[0] + L, c[1] + s[1] + L))], fill=(185, 200, 130))
    g.ellipse([P((c[0] - s[0], c[1] - s[1])), P((c[0] + s[0], c[1] + s[1]))], fill=(225, 205, 160))
    g.rectangle([P((c[0] - 11, c[1] - 3)), P((c[0] + 11, c[1] + 3))], fill=(150, 100, 60))
    river = data["rio"]["puntos"]
    g.line([P(p) for p in river], fill=(110, 165, 200), width=int(data["rio"]["ancho"] * S), joint="curve")
    for k in data["caminos"]:
        g.line([P(p) for p in k["puntos"]], fill=(225, 195, 140), width=int(k["ancho"] * S), joint="curve")
    g.polygon([P(p) for p in data["plaza"]["contorno"]], fill=(220, 210, 190))
    for b in data["puentes"]:
        rect(b["centro"], (b["largo"], b["ancho"]), -b["giro"], (150, 110, 70))
    for corral in data["corrales"]:
        r = corral["radio"]
        cc = corral["centro"]
        g.ellipse([P((cc[0] - r, cc[1] - r)), P((cc[0] + r, cc[1] + r))], outline=(140, 100, 60), width=3)
    q = data["cantera"]
    g.ellipse([P((q["centro"][0] - q["radio"], q["centro"][1] - q["radio"])),
               P((q["centro"][0] + q["radio"], q["centro"][1] + q["radio"]))], fill=(170, 165, 155))
    for p in data["brea"]:
        g.ellipse([P((p[0] - 1.5, p[1] - 1.5)), P((p[0] + 1.5, p[1] + 1.5))], fill=(40, 30, 25))
    for t in data["arboles"]:
        g.ellipse([P((t[0] - 1.6, t[1] - 1.6)), P((t[0] + 1.6, t[1] + 1.6))], fill=(80, 130, 80))
    for b in data["bosque"]:
        cc, r = b["centro"], b["radio"]
        g.ellipse([P((cc[0] - r, cc[1] - r)), P((cc[0] + r, cc[1] + r))], outline=(40, 100, 50), width=3)
    # Casas con su patio delante, mirando a la calle o callejón más cercano (como world.gd).
    streets = [k["puntos"] for k in data["caminos"]]
    for h in data["casas"]:
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
        w, d, front = HOUSE_TAM[h["modelo"]]
        # Rectángulo de la casa más el patio delante, en coordenadas del mundo.
        cz = (front + h["patio"] - d / 2) / 2
        depth = front + h["patio"] + d / 2
        center = (p[0] + math.sin(ang) * cz, p[1] + math.cos(ang) * cz)
        rect(center, (w, depth), -math.degrees(ang), (225, 190, 150), (150, 100, 70))
        rect(p, (w, d), -math.degrees(ang), (200, 130, 85), (120, 70, 40))
        if h["id"] in ("noe", "sem", "cam", "jafet") or h["id"].startswith("vecin"):
            g.text((P(p)[0] + 10, P(p)[1] - 10), h["id"], fill=(60, 30, 20))
    im.save(path)


if __name__ == "__main__":
    main()
