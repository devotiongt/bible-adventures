"""Textura final de Noé (versión ligera NoeLow1500, ver pulir_rodin.py).

    paso_uv          despliegue UV nuevo: pocas piezas grandes y bien empaquetadas
    paso_hornear     hornea desde la malla original de Rodin: color, normales y oclusión ambiental
    paso_pintar      repinta por partes con los colores de referencias/paleta.png: color plano,
                     sombreado suave de la oclusión, trama de lino en la túnica y mangas, tejido en el
                     chaleco; la piel conserva su pintura (nariz, rubor)
    paso_exportar    .glb para el juego

En vivo:
    python3 herramientas/blender/en_vivo.py textura paso_uv paso_hornear paso_pintar "paso_exportar('...')"
"""

import math
import os

import bpy
import numpy as np
from mathutils import Vector

ROOT = globals().get("PROJECT_ROOT", os.getcwd())
OUT_DIR = os.path.join(ROOT, "assets/personajes/rodin")
LOW = "NoeLow2500"
SIZE = 1024

# Partes y su color (sRGB) según la paleta de referencia.
PARTS = {
    "piel": "FCD4B7", "nariz": "EDA88A", "canas": "EFEFEF", "tunica": "DDD3C0",
    "manto": "A55B2E", "manga": "C8AE86", "cuerda": "5E3918", "sandalia": "3F2A1D",
}
SKIN_FAMILY = ("piel", "nariz")       # Conservan su pintura (rubor, nariz), solo se limpian.


def _hex(h):
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], np.float32) / 255


def _low():
    return bpy.data.objects[LOW]


def _select_only(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.hide_viewport = False
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def _uv_coverage(obj, layer):
    """Fracción del cuadrado UV cubierta por triángulos."""
    me = obj.data
    me.calc_loop_triangles()
    uv = me.uv_layers[layer].data
    area = 0.0
    for tri in me.loop_triangles:
        a, b, c = (uv[i].uv for i in tri.loops)
        area += abs((b.x - a.x) * (c.y - a.y) - (c.x - a.x) * (b.y - a.y)) / 2
    return area


def _overlapping_faces(obj, size=1024):
    """Caras cuyo triángulo UV comparte píxeles con otro triángulo."""
    me = obj.data
    me.calc_loop_triangles()
    uv = me.uv_layers["UVJuego"].data
    count = np.zeros((size, size), np.int32)
    cover = []
    for tri in me.loop_triangles:
        uvs = np.array([uv[i].uv[:] for i in tri.loops], np.float64) * size
        x0, y0 = np.floor(uvs.min(0)).astype(int)
        x1, y1 = np.ceil(uvs.max(0)).astype(int) + 1
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, size), min(y1, size)
        if x1 <= x0 or y1 <= y0:
            cover.append(None)
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1) + .5, np.arange(y0, y1) + .5)
        (ax, ay), (bx, by), (cx, cy) = uvs
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-12:
            cover.append(None)
            continue
        l1 = ((by - cy) * (xs - cx) + (cx - bx) * (ys - cy)) / den
        l2 = ((cy - ay) * (xs - cx) + (ax - cx) * (ys - cy)) / den
        inside = (l1 >= 0) & (l2 >= 0) & (1 - l1 - l2 >= 0)
        count[y0:y1, x0:x1] += inside
        cover.append((x0, y0, x1, y1, inside, tri.polygon_index))
    bad = set()
    for c in cover:
        if c is None:
            continue
        x0, y0, x1, y1, inside, poly = c
        if (count[y0:y1, x0:x1][inside] > 1).any():
            bad.add(poly)
    return bad


def _move_overlaps(obj, strip=0.06, attempt=0):
    """Triángulos plegados unos sobre otros: en esos píxeles una parte del cuerpo se pintaría con el
    color de otra. Se encoge todo el despliegue para dejar una franja libre arriba y a la derecha,
    y cada cara superpuesta se lleva a esa franja (cada esquina tiene su propia coordenada UV, así
    que se separa de su pieza sin mover a los vecinos)."""
    me = obj.data
    uv = me.uv_layers["UVJuego"].data
    bad = sorted(_overlapping_faces(obj))
    print("caras superpuestas", len(bad))
    if not bad:
        return
    k = 1 - strip
    for d in uv:
        d.uv = d.uv * k
    # Celdas en la franja: columna derecha y fila de arriba.
    half = strip / 2
    cell = half * 0.85
    slots = [(k + half * c + half * 0.07, y * half) for c in (0, 1) for y in range(int(k / half))] + \
            [(x * half, k + half * r + half * 0.07) for r in (0, 1) for x in range(int(k / half))]
    assert len(slots) >= len(bad), (len(slots), len(bad))
    for n, f in enumerate(bad):
        loops = list(me.polygons[f].loop_indices)
        us = [uv[i].uv.copy() for i in loops]
        mn = Vector((min(u.x for u in us), min(u.y for u in us)))
        size = max(max(u.x for u in us) - mn.x, max(u.y for u in us) - mn.y, 1e-6)
        scale = min(1.0, cell / size)
        ox, oy = slots[n]
        for i, u in zip(loops, us):
            uv[i].uv = Vector((ox, oy)) + (u - mn) * scale
    left = len(_overlapping_faces(obj))
    print("tras moverlas", left, "superpuestas")
    if left and attempt < 3:
        _move_overlaps(obj, strip, attempt + 1)


def paso_uv():
    """Despliegue automático + empaquetado. Probé ángulos 45-80 y métodos AABB/convexo/cóncavo:
    esta combinación es la que más aprovecha (~57 %); por encima haría falta marcar costuras a mano."""
    low = _low()
    me = low.data
    layer = me.uv_layers.get("UVJuego") or me.uv_layers.new(name="UVJuego")
    me.uv_layers.active = layer
    _select_only(low)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(70), island_margin=0.004, area_weight=0.6,
                             correct_aspect=True, scale_to_bounds=False)
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(rotate=True, margin=0.004)
    bpy.ops.object.mode_set(mode="OBJECT")
    _move_overlaps(low)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.object.mode_set(mode="OBJECT")
    layer.active_render = True
    print("aprovechamiento", f"{_uv_coverage(low, 'UVJuego'):.0%}")


def _new_image(name, data=False):
    old = bpy.data.images.get(name)
    if old:
        bpy.data.images.remove(old)
    img = bpy.data.images.new(name, SIZE, SIZE, is_data=data)
    if data:
        img.colorspace_settings.name = "Non-Color"
    return img


def paso_picos():
    """Quita los picos que dejó la reducción de polígonos en las cejas: cada vértice de esa zona
    que sobresale mucho respecto a sus vecinos se lleva a la media de ellos."""
    import bmesh
    low = _low()
    mw = low.matrix_world
    inv = mw.inverted()
    bm = bmesh.new()
    bm.from_mesh(low.data)
    fixed = 0
    for _ in range(3):
        for v in bm.verts:
            w = mw @ v.co
            if not (1.31 < w.z < 1.42 and abs(w.x) < 0.14 and w.y < -0.08):
                continue
            nb = [e.other_vert(v).co for e in v.link_edges]
            if not nb:
                continue
            c = sum(nb, Vector()) / len(nb)
            edge = sum((n - v.co).length for n in nb) / len(nb)
            if (v.co - c).length > 0.6 * edge:
                v.co = v.co.lerp(c, 0.8)
                fixed += 1
    bm.to_mesh(low.data)
    bm.free()
    low.data.update()
    print("vertices corregidos", fixed)


BROW_ZONE = (0.025, 0.14, 1.335, 1.41)     # |x| min/max, z min/max (frente, delante).


def _in_brow_zone(x, z, y):
    return BROW_ZONE[0] < abs(x) < BROW_ZONE[1] and BROW_ZONE[2] < z < BROW_ZONE[3] and y < -0.1


def paso_cejas():
    """Cejas como piezas propias (como los ojos): con 1.500 triángulos la malla no puede formar un
    relieve tan pequeño y dejaba cuñas afiladas. Se alisa esa zona de la frente y se añaden dos
    "churros" con el recorrido y grosor medidos en la malla original (referencias/noe_cejas.json)."""
    import json
    from mathutils.bvhtree import BVHTree
    low = _low()
    # 2. Superficie de la frente sin cejas: polinomio de grado 2 ajustado a la malla original
    #    fuera de la franja de las cejas.
    high = bpy.data.objects["model"]
    hidden = high.hide_viewport
    high.hide_viewport = False
    bpy.context.view_layer.update()
    bvh = BVHTree.FromObject(high, bpy.context.evaluated_depsgraph_get())
    hm = high.matrix_world
    hinv = hm.inverted()
    d = (hinv.to_3x3() @ Vector((0, 1, 0))).normalized()
    rows = []
    for x in np.arange(-0.15, 0.151, 0.004):
        for z in np.arange(1.30, 1.451, 0.004):
            if 1.34 < z < 1.42 or abs(x) > 0.13:
                continue
            hit, _n, _i, _d = bvh.ray_cast(hinv @ Vector((x, -2, z)), d)
            if hit is not None:
                rows.append((x, z, (hm @ hit).y))
    high.hide_viewport = hidden
    r = np.array(rows)
    A = np.stack([np.ones(len(r)), r[:, 0], r[:, 1], r[:, 0] ** 2, r[:, 1] ** 2, r[:, 0] * r[:, 1]], -1)
    coef = np.linalg.lstsq(A, r[:, 2], rcond=None)[0]
    surface = lambda x, z: float(coef @ np.array([1, x, z, x * x, z * z, x * z]))
    # 3. Los vértices de la zona que sobresalen de esa superficie se llevan a ella (solo en Y).
    mw = low.matrix_world
    inv = mw.inverted()
    moved = 0
    for v in low.data.vertices:
        w = mw @ v.co
        if _in_brow_zone(w.x, w.z, w.y):
            target = surface(w.x, w.z)
            if w.y < target:
                w.y = target
                v.co = inv @ w
                moved += 1
    low.data.update()
    print("vertices proyectados a la frente", moved)

    data = json.load(open(os.path.join(ROOT, "referencias/noe_cejas.json")))
    root = bpy.data.objects["RodinGiro"]
    mat = bpy.data.materials.get("CejaNoe") or bpy.data.materials.new("CejaNoe")
    mat.use_nodes = True
    b = mat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*[c ** 2.2 for c in _hex(PARTS["canas"])], 1)
    b.inputs["Roughness"].default_value = 0.75
    for o in [o for o in bpy.data.objects if o.name.startswith("CejaNoe")]:
        bpy.data.objects.remove(o)
    import bmesh as bmm
    for key, side in (("1", "I"), ("-1", "D")):
        pts = [q for q in data[key] if q[4] > 0.006]
        pts.sort(key=lambda q: abs(q[0]))
        # Muestreo cada ~6 mm y suavizado de la curva.
        pts = pts[::5]
        n = len(pts)
        sm = []
        for i in range(n):
            lo, hi = max(0, i - 1), min(n, i + 2)
            sm.append([sum(q[k] for q in pts[lo:hi]) / (hi - lo) for k in range(5)])
        bm2 = bmm.new()
        rings = []
        seg = 8
        for i, (x, z, yfront, semi, sale) in enumerate(sm):
            t = i / (n - 1)
            taper = math.sin(math.pi * (0.12 + 0.76 * t)) ** 0.6     # Más fina en las puntas.
            rz = min(max(semi, 0.007), 0.012) * taper
            ry = 0.0085 * taper
            center = Vector((x, yfront + ry * 0.8, z))
            a = Vector(sm[max(i - 1, 0)][:2]); c = Vector(sm[min(i + 1, n - 1)][:2])
            tang = Vector((c.x - a.x, 0, c.y - a.y)).normalized()
            up = Vector((-tang.z, 0, tang.x))
            if up.z < 0:
                up = -up
            fwd = Vector((0, -1, 0))
            rings.append([bm2.verts.new(center + up * math.cos(k * math.tau / seg) * rz
                                        + fwd * math.sin(k * math.tau / seg) * ry) for k in range(seg)])
        for i in range(len(rings) - 1):
            for k in range(seg):
                k2 = (k + 1) % seg
                bm2.faces.new((rings[i][k], rings[i][k2], rings[i + 1][k2], rings[i + 1][k]))
        for ring in (rings[0], rings[-1]):
            cap = bmm.ops.contextual_create(bm2, geom=ring)
        bmm.ops.recalc_face_normals(bm2, faces=bm2.faces)
        me = bpy.data.meshes.new(f"CejaNoe{side}")
        bm2.to_mesh(me)
        bm2.free()
        o = bpy.data.objects.new(f"CejaNoe{side}", me)
        bpy.context.scene.collection.objects.link(o)
        o.data.materials.append(mat)
        for poly in me.polygons:
            poly.use_smooth = True
        o.parent = root
        o.matrix_parent_inverse = root.matrix_world.inverted()
        print("ceja", side, "triangulos", sum(len(p.vertices) - 2 for p in me.polygons))


def paso_desplegar_pliegues(max_angle=150):
    """Triángulos volteados que dejó la reducción de polígonos (dos caras vecinas casi opuestas,
    la malla se dobla sobre sí misma y se ve una línea). Se lleva cada vértice de esas aristas
    a la media de sus vecinos hasta que no quede ninguno."""
    import bmesh
    low = _low()
    bm = bmesh.new()
    bm.from_mesh(low.data)
    for it in range(20):
        bm.normal_update()
        bad = [e for e in bm.edges if len(e.link_faces) == 2
               and math.degrees(e.link_faces[0].normal.angle(e.link_faces[1].normal, 0)) > max_angle]
        if not bad:
            break
        verts = {v for e in bad for v in e.verts}
        for v in verts:
            nb = [e.other_vert(v).co for e in v.link_edges]
            v.co = v.co.lerp(sum(nb, Vector()) / len(nb), 0.5)
        print("vuelta", it, "aristas plegadas", len(bad))
    # Lo que queda (y los dobleces fuertes en la cara): girar la arista compartida, si eso deja las
    # dos caras más alineadas.
    bm.normal_update()
    mw = low.matrix_world
    rotated = 0
    for e in list(bm.edges):
        if len(e.link_faces) != 2 or not e.is_valid:
            continue
        ang = math.degrees(e.link_faces[0].normal.angle(e.link_faces[1].normal, 0))
        c = mw @ ((e.verts[0].co + e.verts[1].co) / 2)
        face_zone = c.z > 1.15 and c.y < -0.05
        if ang > max_angle or (face_zone and ang > 100):
            res = bmesh.ops.rotate_edges(bm, edges=[e], use_ccw=False)
            new = res["edges"]
            if new:
                bm.normal_update()
                ne = new[0]
                ang2 = math.degrees(ne.link_faces[0].normal.angle(ne.link_faces[1].normal, 0)) \
                    if len(ne.link_faces) == 2 else 180
                if ang2 >= ang:
                    bmesh.ops.rotate_edges(bm, edges=[ne], use_ccw=True)
                else:
                    rotated += 1
    print("aristas giradas", rotated)
    bm.to_mesh(low.data)
    bm.free()
    low.data.update()


def paso_restaurar_malla():
    """Vuelve a la malla guardada en noe_textura.blend (misma topología): posiciones y UV."""
    low = _low()
    with bpy.data.libraries.load(os.path.join(OUT_DIR, "noe_textura.blend")) as (src, dst):
        dst.objects = [LOW]
    saved = dst.objects[0]
    assert len(saved.data.vertices) == len(low.data.vertices), "topología distinta"
    for v, sv in zip(low.data.vertices, saved.data.vertices):
        v.co = sv.co
    for l, sl in zip(low.data.uv_layers["UVJuego"].data, saved.data.uv_layers["UVJuego"].data):
        l.uv = sl.uv
    low.data.update()
    lib = saved.library
    bpy.data.meshes.remove(saved.data)
    for o in [o for o in bpy.data.objects if lib is not None and o.library is lib]:
        bpy.data.objects.remove(o)
    if lib is not None:
        bpy.data.libraries.remove(lib)
    print("malla restaurada")


def paso_hombros(radio=0.015, vueltas=0):
    """Quita la pestaña y el pliegue de la costura manga/chaleco: alisa la malla en una franja
    alrededor de la costura y marca esos triángulos para dejar plano su mapa de normales."""
    import bmesh
    low = _low()
    me = low.data
    names = list(PARTS)
    parte = np.zeros(len(me.polygons), np.int32)
    me.attributes["parte"].data.foreach_get("value", parte)
    gi, mi = names.index("manga"), names.index("manto")
    mw = low.matrix_world
    inv = mw.inverted()
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    seam = set()
    for e in bm.edges:
        if len(e.link_faces) != 2:
            continue
        a, b = (parte[f.index] for f in e.link_faces)
        c = mw @ ((e.verts[0].co + e.verts[1].co) / 2)
        if {a, b} == {gi, mi} and 0.9 < c.z < 1.12 and 0.17 < abs(c.x) < 0.32:
            seam.update(e.verts)
    seam_pts = [mw @ v.co for v in seam]
    zone = [v for v in bm.verts if min(((mw @ v.co) - q).length for q in seam_pts) < radio] if seam_pts else []
    print("vertices en la costura", len(seam), "en la franja", len(zone))
    # Alisado tipo Laplace sin encoger (ida y vuelta, método de Taubin).
    for it in range(vueltas):
        for lam in (0.5, -0.53):
            new = {}
            for v in zone:
                nb = [e.other_vert(v).co for e in v.link_edges]
                c = sum(nb, Vector()) / len(nb)
                new[v] = v.co + (c - v.co) * lam
            for v, co in new.items():
                v.co = co
    flagged = set(f.index for v in zone for f in v.link_faces)
    bm.to_mesh(me)
    bm.free()
    me.update()
    attr = me.attributes.get("costura_hombro") or me.attributes.new("costura_hombro", "INT", "FACE")
    vals = np.zeros(len(me.polygons), np.int32)
    vals[list(flagged)] = 1
    attr.data.foreach_set("value", vals)
    print("triangulos marcados", len(flagged))


def paso_meter_pestana(hondo=0.012, alcance=0.03):
    """Esconde la pestaña de la manga bajo el chaleco: los vértices que son solo de manga, cerca de
    la costura del hombro, se llevan hacia el eje del brazo. No toca vértices de otras partes."""
    import bmesh
    low = _low()
    me = low.data
    names = list(PARTS)
    parte = np.zeros(len(me.polygons), np.int32)
    me.attributes["parte"].data.foreach_get("value", parte)
    gi, mi = names.index("manga"), names.index("manto")
    mw = low.matrix_world
    inv = mw.inverted()
    bm = bmesh.new()
    bm.from_mesh(me)
    seam = []
    for e in bm.edges:
        if len(e.link_faces) == 2 and {parte[f.index] for f in e.link_faces} == {gi, mi}:
            c = mw @ ((e.verts[0].co + e.verts[1].co) / 2)
            if 0.9 < c.z < 1.12 and 0.17 < abs(c.x) < 0.32:
                seam.append(c)
    moved = 0
    for v in bm.verts:
        if not v.link_faces or any(parte[f.index] != gi for f in v.link_faces):
            continue
        w = mw @ v.co
        if not (0.95 < w.z < 1.13 and 0.17 < abs(w.x) < 0.34) or not seam:
            continue
        d = min((w - q).length for q in seam)
        if d > alcance:
            continue
        # Eje del brazo: del hombro (x≈±0.2, z≈1.05) hacia el codo; se mete en dirección horizontal
        # hacia ese eje y un poco hacia abajo.
        axis = Vector((math.copysign(0.24, w.x), 0.0, w.z))
        inward = (axis - w)
        inward.z = 0
        if inward.length < 1e-6:
            continue
        k = hondo * (1 - d / alcance)
        w = w + inward.normalized() * k + Vector((0, 0, -k * 0.6))
        v.co = inv @ w
        moved += 1
    bm.to_mesh(me)
    bm.free()
    me.update()
    print("vertices de manga metidos bajo el chaleco", moved, "costura", len(seam))


def paso_hornear():
    scene = bpy.context.scene
    high = bpy.data.objects["model"]
    low = _low()
    high.hide_viewport = False
    high.hide_render = False
    low.hide_render = False
    color = _new_image("NoeBaseColor")
    normal = _new_image("NoeNormalJuego", data=True)
    ao = _new_image("NoeAO", data=True)

    mat = low.data.materials[0]
    nt = mat.node_tree
    for n in list(nt.nodes):
        if n.type in ("TEX_IMAGE", "NORMAL_MAP", "UVMAP"):
            nt.nodes.remove(n)
    bsdf = nt.nodes["Principled BSDF"]
    uvn = nt.nodes.new("ShaderNodeUVMap")
    uvn.uv_map = "UVJuego"
    nodes = {}
    for key, img in (("color", color), ("normal", normal), ("ao", ao)):
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = img
        nt.links.new(uvn.outputs["UV"], t.inputs["Vector"])
        nodes[key] = t
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nm.uv_map = "UVJuego"
    nt.links.new(nodes["color"].outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(nodes["normal"].outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])

    scene.render.engine = "CYCLES"
    scene.cycles.samples = 16
    bake = scene.render.bake
    bake.margin = 16
    bake.cage_extrusion = 0.012
    bake.max_ray_distance = 0.03
    bake.use_pass_direct = False
    bake.use_pass_indirect = False
    bake.use_pass_color = True

    def run(kind, node, selected):
        bake.use_selected_to_active = selected
        bpy.ops.object.select_all(action="DESELECT")
        if selected:
            high.select_set(True)
        low.select_set(True)
        bpy.context.view_layer.objects.active = low
        nt.nodes.active = node
        bpy.ops.object.bake(type=kind)
        print("horneado", kind)

    run("NORMAL", nodes["normal"], True)
    run("DIFFUSE", nodes["color"], True)
    # Oclusión de la propia malla ligera (sombras suaves en pliegues, cuello, axilas…).
    high.hide_render = True
    scene.cycles.samples = 64
    scene.world.light_settings.distance = 0.035
    run("AO", nodes["ao"], False)
    for img, name in ((color, "noe_base_color.png"), (normal, "noe_normal_juego.png"), (ao, "noe_ao.png")):
        img.filepath_raw = os.path.join(OUT_DIR, name)
        img.file_format = "PNG"
        img.save()
    high.hide_viewport = True
    scene.render.engine = "BLENDER_EEVEE"


def _pixels(img):
    a = np.empty(SIZE * SIZE * 4, np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(SIZE, SIZE, 4)


def _position_map(obj):
    """Posición 3D (mundo) de cada texel del UV 'UVJuego'; NaN donde no hay malla."""
    me = obj.data
    me.calc_loop_triangles()
    uv = me.uv_layers["UVJuego"].data
    mw = obj.matrix_world
    pos = np.full((SIZE, SIZE, 3), np.nan, np.float32)
    face = np.full((SIZE, SIZE), -1, np.int32)
    tris = []
    for tri in me.loop_triangles:
        uvs = np.array([uv[i].uv[:] for i in tri.loops], np.float64) * SIZE
        ps = np.array([(mw @ me.vertices[v].co)[:] for v in tri.vertices], np.float32)
        tris.append((uvs, ps, tri.polygon_index))
    # Dos pasadas: primero los texeles cuyo centro cae dentro de cada triángulo; después, los que
    # solo lo tocan (hasta 0,8 px fuera del borde), sin pisar los ya asignados. Así ningún
    # triángulo estrecho se queda sin texeles (si no, el relleno de bordes le pondría el color
    # de la pieza vecina en la imagen).
    for tolerance in (0.0, 0.8):
        for uvs, ps, poly_index in tris:
            x0, y0 = np.floor(uvs.min(0) - 1).astype(int)
            x1, y1 = np.ceil(uvs.max(0) + 2).astype(int)
            x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, SIZE), min(y1, SIZE)
            if x1 <= x0 or y1 <= y0:
                continue
            xs, ys = np.meshgrid(np.arange(x0, x1) + 0.5, np.arange(y0, y1) + 0.5)
            (ax, ay), (bx, by), (cx, cy) = uvs
            den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
            if abs(den) < 1e-12:
                continue
            l1 = ((by - cy) * (xs - cx) + (cx - bx) * (ys - cy)) / den
            l2 = ((cy - ay) * (xs - cx) + (ax - cx) * (ys - cy)) / den
            l3 = 1 - l1 - l2
            # Distancia (en píxeles) a cada lado = coordenada baricéntrica × altura sobre ese lado.
            area2 = abs(den)
            h = [area2 / max(np.hypot(*(uvs[(k + 1) % 3] - uvs[(k + 2) % 3])), 1e-9) for k in range(3)]
            inside = (l1 * h[0] >= -tolerance) & (l2 * h[1] >= -tolerance) & (l3 * h[2] >= -tolerance)
            region_face = face[y0:y1, x0:x1]
            if tolerance > 0:
                inside &= region_face < 0
            if not inside.any():
                continue
            c1, c2 = np.clip(l1, 0, 1), np.clip(l2, 0, 1)
            c3 = np.clip(1 - c1 - c2, 0, 1)
            p = c1[..., None] * ps[0] + c2[..., None] * ps[1] + c3[..., None] * ps[2]
            pos[y0:y1, x0:x1][inside] = p[inside]
            region_face[inside] = poly_index
    return pos, face


def _box(a, r):
    """Media en una ventana (2r+1)² (con suma acumulada)."""
    pad = np.pad(a, ((r + 1, r), (r + 1, r)) + ((0, 0),) * (a.ndim - 2), mode="edge")
    c = pad.cumsum(0).cumsum(1)
    k = 2 * r + 1
    return (c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]) / (k * k)


def _noise(p, scale, seed):
    """Ruido suave en 3D (suma de senos con fases fijas, sin dependencias)."""
    rng = np.random.default_rng(seed)
    out = np.zeros(p.shape[:2], np.float32)
    for _ in range(6):
        d = rng.normal(size=3)
        d /= np.linalg.norm(d)
        out += np.sin((p @ d) * scale * rng.uniform(0.7, 1.4) + rng.uniform(0, 6.28))
    return out / 6


def paso_pintar(debug_face=None):
    low = _low()
    base = _pixels(bpy.data.images["NoeBaseColor"])[..., :3]
    ao = _pixels(bpy.data.images["NoeAO"])[..., 0]
    pos, face = _position_map(low)
    valid = ~np.isnan(pos[..., 0])
    p = np.nan_to_num(pos)
    names = list(PARTS)
    palette = np.stack([_hex(PARTS[n]) for n in names])

    # 1. Parte de cada texel: el color de la paleta más cercano, y luego mayoría en una ventana
    #    7×7 (quita las manchas sueltas de la pintura de Rodin).
    dist = ((base[..., None, :] - palette[None, None]) ** 2).sum(-1)
    # Dónde puede estar cada parte (posición en el cuerpo, en metros). El color solo no basta: el
    # blanco sombreado del pelo se parece al beige de la túnica.
    z, ax, back = p[..., 2], np.abs(p[..., 0]), p[..., 1] > 0.05     # Noé mira hacia -Y.
    allowed = {
        # Piel: solo cabeza (no en la nuca, que la tapa el pelo), manos y pies.
        "piel": (((z > 1.1) & ~(back & (z < 1.3) & (ax < 0.2))) | ((ax > 0.27) & (z < 0.8)) | (z < 0.2)),
        "nariz": (z > 1.2) & (z < 1.36) & (ax < 0.06),
        "canas": (z > 0.7) & ~((ax > BROW_ZONE[0]) & (ax < BROW_ZONE[1]) & (z > BROW_ZONE[2])
                                 & (z < BROW_ZONE[3]) & (p[..., 1] < -0.1)),
        # Por debajo del chaleco se ve en todo el contorno; por encima, solo en la abertura delantera.
        "tunica": ((z < 0.36) & (z > 0.14)) | ((z > 0.3) & (z < 1.16) & (ax < 0.13) & (p[..., 1] < -0.08)),
        "manto": (z < 1.18) & (z > 0.25) & ~((ax > 0.235) & (z > 0.55)),   # No en los brazos.
        "manga": (z < 1.15) & (z > 0.5) & (ax > 0.14),
        "cuerda": (z > 0.5) & (z < 0.8),
        "sandalia": z < 0.06,
    }
    for k, n in enumerate(names):
        dist[..., k] += np.where(allowed[n], 0.0, 10.0)
    label = dist.argmin(-1)

    # Primero se decide la parte de cada triángulo (mayoría de sus texeles) y se corrigen los
    # triángulos sueltos (ningún vecino comparte su parte). Luego cada texel solo puede elegir entre
    # la parte de su triángulo y la de los triángulos vecinos: así una manga es manga entera y solo
    # se mezclan partes en los bordes reales entre piezas.
    me = low.data
    nf = len(me.polygons)
    hist = np.zeros((nf, len(names)), np.float32)
    m = valid & (face >= 0)
    np.add.at(hist, (face[m], label[m]), 1.0)
    face_label = hist.argmax(1)
    neighbors = [set() for _ in range(nf)]
    edge_faces = {}
    for poly in me.polygons:
        for key in poly.edge_keys:
            edge_faces.setdefault(key, []).append(poly.index)
    for fs in edge_faces.values():
        for a in fs:
            for b in fs:
                if a != b:
                    neighbors[a].add(b)
    for _ in range(3):
        new_label = face_label.copy()
        for f in range(nf):
            nb = [face_label[n] for n in neighbors[f]]
            if nb and face_label[f] not in nb:
                new_label[f] = max(set(nb), key=nb.count)
        face_label = new_label
    allowed_face = np.zeros((nf, len(names)), bool)
    for f in range(nf):
        allowed_face[f, face_label[f]] = True
        for n in neighbors[f]:
            allowed_face[f, face_label[n]] = True
    # Permitido = lo que dejan los triángulos vecinos Y las reglas de posición en el cuerpo.
    ok = allowed_face[np.clip(face, 0, None)] & np.stack([allowed[n] for n in names], -1)
    dist = np.where(ok, dist, dist + 10.0)
    label = dist.argmin(-1)
    if debug_face is not None:
        mf = face == debug_face
        print("cara", debug_face, "texeles", int(mf.sum()), "parte cara", names[face_label[debug_face]],
              "permitidas", [names[k] for k in np.nonzero(allowed_face[debug_face])[0]],
              "vecinos", [names[face_label[n]] for n in neighbors[debug_face]],
              "hist", dict(zip(names, hist[debug_face].astype(int).tolist())),
              "texel labels", dict(zip(names, np.bincount(label[mf], minlength=len(names)).tolist())))
    for _ in range(3):
        # Mayoría local, pero solo entre las partes permitidas para el triángulo de cada texel:
        # en la imagen, junto al borde de una pieza puede haber otra pieza que en el cuerpo está lejos.
        votes = np.stack([_box(((label == k) & valid).astype(np.float32), 6) for k in range(len(names))], -1)
        votes = np.where(ok, votes, -1.0)
        label = votes.argmax(-1)
    if debug_face is not None:
        print("tras mayoria", dict(zip(names, np.bincount(label[face == debug_face], minlength=len(names)).tolist())))
    # Borde de la abertura delantera del chaleco: a cada altura (cada 1 cm) se busca el ancho que
    # mejor separa túnica (dentro) de chaleco (fuera) y se suaviza en una línea limpia.
    ti, mi = names.index("tunica"), names.index("manto")
    front = valid & (p[..., 1] < -0.08) & (z > 0.36) & (z < 1.12) & (ax < 0.2)
    zb = np.arange(0.36, 1.12, 0.01)
    cut = np.full(len(zb), np.nan)
    for i, z0 in enumerate(zb):
        band = front & (np.abs(z - z0) < 0.01) & np.isin(label, [ti, mi])
        if band.sum() < 20:
            continue
        a, lab = ax[band], label[band]
        best, best_err = np.nan, 1e9
        for t in np.arange(0.03, 0.15, 0.0025):
            err = np.sum((a < t) & (lab == mi)) + np.sum((a >= t) & (lab == ti))
            if err < best_err:
                best, best_err = t, err
        cut[i] = best
    ok_cut = ~np.isnan(cut)
    if ok_cut.sum() > 5:
        cut = np.interp(zb, zb[ok_cut], cut[ok_cut])
        k = np.exp(-np.arange(-6, 7) ** 2 / (2 * 3.0 ** 2))
        cut = np.convolve(np.pad(cut, 6, mode="edge"), k / k.sum(), mode="valid")
        line = np.interp(z, zb, cut)
        region = front & np.isin(label, [ti, mi])
        label = np.where(region & (ax < line), ti, np.where(region & (ax >= line), mi, label))
        print("abertura del chaleco (semiancho cm)", [round(float(c) * 100, 1) for c in cut[::10]])
    # Bordes que siguen la malla: si un triángulo es claramente de una sola parte (70 % o más de sus
    # píxeles), se pinta entero de esa parte. Así la costura manga/chaleco o cuerda/túnica sigue las
    # aristas de las piezas en vez de dibujar un zigzag de píxeles.
    m2 = valid & (face >= 0)
    hist2 = np.zeros((nf, len(names)), np.float32)
    np.add.at(hist2, (face[m2], label[m2]), 1.0)
    dom = hist2.argmax(1)
    frac = hist2.max(1) / np.maximum(hist2.sum(1), 1)
    solid = frac >= 0.7
    fl = np.clip(face, 0, None)
    take = m2 & solid[fl]
    label = np.where(take, dom[fl], label)
    print("triangulos de una sola parte", int(solid.sum()), "de", nf)
    attr = me.attributes.get("parte") or me.attributes.new("parte", "INT", "FACE")
    attr.data.foreach_set("value", dom.astype(np.int32))
    # Sandalias (según referencias/noe_giro.png): suela marrón oscuro y una tira ancha sobre la parte
    # delantera del pie, con los dedos asomando. Se colocan según la medida de cada pie.
    si, pi_ = names.index("sandalia"), names.index("piel")
    feet = valid & (z < 0.13) & (ax > 0.03) & (ax < 0.22)
    for sx in (1, -1):
        f = feet & (np.sign(p[..., 0]) == sx)
        if f.sum() < 50:
            continue
        ys = p[..., 1][f]
        toe, heel = np.percentile(ys, 1), np.percentile(ys, 99)     # Noé mira hacia -Y.
        t = (p[..., 1] - toe) / max(heel - toe, 1e-6)                # 0 punta, 1 talón.
        sole = f & (z < 0.022)
        top = f & (z >= 0.022)
        straps = top & (t > 0.17) & (t < 0.42) & (z < 0.075)         # Una tira ancha sobre el pie.
        label = np.where(sole | straps, si, np.where(top, pi_, label))
        print("pie", sx, "largo cm", round(float(heel - toe) * 100, 1))
    counts = {n: int(((label == k) & valid).sum()) for k, n in enumerate(names)}
    print("texeles por parte", counts)

    # 2. Color: plano por parte; la piel conserva su pintura suavizada.
    color = palette[label]
    skin = np.isin(label, [names.index(n) for n in SKIN_FAMILY]) & valid
    soft = _box(base * valid[..., None], 2) / np.maximum(_box(valid.astype(np.float32), 2), 1e-6)[..., None]
    # Solo la cara conserva la pintura de Rodin (rubor, nariz); manos, piernas y pies, color plano.
    head = skin & (z > 1.1)
    color[head] = soft[head]

    brow = (ax > BROW_ZONE[0] - 0.01) & (ax < BROW_ZONE[1] + 0.01) & (z > BROW_ZONE[2] - 0.01) \
        & (z < BROW_ZONE[3] + 0.01) & (p[..., 1] < -0.1) & valid
    ring = (ax > 0.02) & (ax < 0.15) & (((z > 1.30) & (z < 1.325)) | ((z > 1.42) & (z < 1.44))) \
        & (p[..., 1] < -0.1) & skin
    if ring.any():
        color[brow] = np.median(color[ring], axis=0)
    # 3. Tela: trama de lino (túnica y mangas) y tejido fino (chaleco), en coordenadas 3D para
    #    que no dependa de cómo esté desplegado el UV.
    around = np.arctan2(p[..., 0], -p[..., 1]) * 0.2
    weave = 0.5 * (np.sin(around / 0.006 * 2 * np.pi) + np.sin(p[..., 2] / 0.006 * 2 * np.pi))
    linen = 1 + 0.035 * weave + 0.03 * _noise(p, 900, 1)
    cloth = 1 + 0.025 * _noise(p, 400, 2) + 0.015 * _noise(p, 1500, 3)
    for name, pattern in (("tunica", linen), ("manga", linen), ("manto", cloth)):
        m = (label == names.index(name)) & valid
        color[m] *= pattern[m][:, None]
    # Pelo y barba: mechones muy suaves (el relieve ya lo dan las normales).
    hair = (label == names.index("canas")) & valid
    color[hair] *= (1 + 0.025 * _noise(p * np.array([4, 4, 0.6]), 300, 4))[hair][:, None]

    # 4. Sombreado suave de la oclusión.
    shade = 1 - 0.55 * (1 - np.clip(ao, 0, 1))
    # En la cara la oclusión marca pliegues de la malla ligera que no existen en el diseño.
    face_skin = skin & (z > 1.15) & (p[..., 1] < -0.05)
    shade = np.where(face_skin, 1 - 0.12 * (1 - np.clip(ao, 0, 1)), shade)
    color *= shade[..., None]

    # 5. Bordes: se extiende el color fuera de cada pieza para que no se vean costuras.
    filled = valid.copy()
    for _ in range(24):
        acc = _box(color * filled[..., None], 1)
        cnt = _box(filled.astype(np.float32), 1)
        grow = (~filled) & (cnt > 0)
        color[grow] = acc[grow] / cnt[grow][:, None]
        filled |= grow

    nimg = bpy.data.images["NoeNormalJuego"]
    nrm = _pixels(nimg)
    head_skin = skin & (z > 1.15) & ~((label == names.index("nariz")))
    flat_zone = head_skin | (valid & (z < 0.2) & (ax < 0.22) & np.isin(label, [names.index("piel"), names.index("sandalia")]))
    seam = me.attributes.get("costura_hombro")
    if seam is not None:
        flags = np.zeros(nf, np.int8)
        seam.data.foreach_get("value", flags)
        flat_zone |= valid & (face >= 0) & flags.astype(bool)[np.clip(face, 0, None)]
    soft_mask = np.clip(_box(flat_zone.astype(np.float32), 6) * 1.6, 0, 1)   # Borde difuminado.
    flat = np.array([0.5, 0.5, 1.0], np.float32)
    nrm[..., :3] = nrm[..., :3] * (1 - soft_mask[..., None]) + flat * soft_mask[..., None]
    nout = bpy.data.images.get("NoeNormalFinal") or bpy.data.images.new("NoeNormalFinal", SIZE, SIZE, is_data=True)
    nout.colorspace_settings.name = "Non-Color"
    nout.pixels.foreach_set(nrm.ravel())
    nout.filepath_raw = os.path.join(OUT_DIR, "noe_normal_juego_final.png")
    nout.file_format = "PNG"
    nout.save()
    for n in low.data.materials[0].node_tree.nodes:
        if n.type == "TEX_IMAGE" and n.image and n.image.name in ("NoeNormalJuego", "NoeNormalFinal"):
            n.image = nout

    out = bpy.data.images.get("NoeColorFinal") or bpy.data.images.new("NoeColorFinal", SIZE, SIZE)
    rgba = np.concatenate([np.clip(color, 0, 1), np.ones((SIZE, SIZE, 1), np.float32)], -1)
    out.pixels.foreach_set(rgba.ravel())
    out.filepath_raw = os.path.join(OUT_DIR, "noe_color_juego.png")
    out.file_format = "PNG"
    out.save()
    tex = next(n for n in low.data.materials[0].node_tree.nodes
               if n.type == "TEX_IMAGE" and n.image and n.image.name in ("NoeBaseColor", "NoeColorFinal"))
    tex.image = out
    print("pintada", "aprovechamiento", f"{valid.mean():.0%}")


def paso_exportar(path):
    low = _low()
    me = low.data
    # Solo el UV nuevo en el archivo del juego.
    for layer in [l for l in me.uv_layers if l.name != "UVJuego"]:
        me.uv_layers.remove(layer)
    bpy.ops.object.select_all(action="DESELECT")
    for o in bpy.context.scene.objects:
        if o.name == LOW or o.name.startswith(("OjoNoe", "BrilloOjo", "CejaNoe", "RodinGiro", "Rodin")):
            o.select_set(True)
    nodes = low.data.materials[0].node_tree.nodes
    for n in [n for n in nodes if n.type == "TEX_IMAGE" and n.image and n.image.name == "NoeAO"]:
        nodes.remove(n)     # La oclusión ya está pintada en el color; no se exporta aparte.
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_yup=True,
                              export_apply=True)
    total = 0
    for o in bpy.context.selected_objects:
        if o.type == "MESH":
            ev = o.evaluated_get(bpy.context.evaluated_depsgraph_get())
            total += sum(len(p.vertices) - 2 for p in ev.data.polygons)
    print("exportado", path, "triangulos", total)
    if total > 4000:
        print("AVISO: más triángulos de lo esperado; revisa modificadores (p. ej. suavizado añadido a mano)")
