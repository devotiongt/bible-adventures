"""Pule el Noé generado por Rodin (abierto en Blender, ver rodin.py):

    paso_cara        rellena las cuencas de los ojos que pinta Rodin (geometría y textura) y
                     pinta el rubor directamente en la textura
    paso_ojos        ojos nuevos, hundidos en la cara (no encima)
    paso_optimizar   reduce los polígonos y hornea el detalle de la malla original en un mapa
                     de normales y el color en una textura nueva
    paso_exportar    guarda .blend y .glb

En vivo:
    python3 herramientas/blender/en_vivo.py pulir_rodin paso_cara paso_ojos paso_optimizar "paso_exportar('...')"
"""

import math
import os

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = globals().get("PROJECT_ROOT", os.getcwd())
OUT_DIR = os.path.join(ROOT, "assets/personajes/rodin")

EYE = (0.074, 1.315)            # Centro de cada ojo (x, z) en metros, medido sobre el modelo.
EYE_SOCKET = (0.032, 0.03)     # Semiejes (x, z) de la zona pintada a rellenar.
CHEEK = (0.1, 1.287)
CHEEK_SIZE = (0.032, 0.021)
SKIN = np.array([252, 212, 183]) / 255
BLUSH = np.array([242, 168, 152]) / 255
TARGET_TRIS = 15000


def _model():
    return bpy.data.objects["model"]


def _image():
    for n in _model().data.materials[0].node_tree.nodes:
        if n.type == "TEX_IMAGE" and n.image and ("paleta" in n.image.name or "diffuse" in n.image.name):
            return n.image
    raise RuntimeError("sin textura de color")


def _ellipse(p, cx, cz, rx, rz):
    return ((p.x - cx) / rx) ** 2 + ((p.z - cz) / rz) ** 2


def _front_faces(obj, test):
    """Caras de delante (normal hacia -Y) cuyo centro cumple test(punto mundial)."""
    mw = obj.matrix_world
    out = []
    for poly in obj.data.polygons:
        c = mw @ poly.center
        n = (mw.to_3x3() @ poly.normal).normalized()
        if n.y < -0.2 and test(c):
            out.append(poly.index)
    return out


def _paint(obj, img, faces, color_at):
    """Pinta en la textura los texeles de esas caras. color_at(punto 3D, color actual) -> color."""
    me = obj.data
    mw = obj.matrix_world
    uv = me.uv_layers.active.data
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)
    me.calc_loop_triangles()
    face_set = set(faces)
    for tri in me.loop_triangles:
        if tri.polygon_index not in face_set:
            continue
        uvs = [Vector(uv[li].uv) for li in tri.loops]
        pos = [mw @ me.vertices[vi].co for vi in tri.vertices]
        xs = [u.x * w for u in uvs]
        ys = [u.y * h for u in uvs]
        x0, x1 = max(int(min(xs)) - 1, 0), min(int(max(xs)) + 2, w)
        y0, y1 = max(int(min(ys)) - 1, 0), min(int(max(ys)) + 2, h)
        (ax, ay), (bx, by), (cx, cy) = zip(xs, ys)
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-9:
            continue
        for y in range(y0, y1):
            for x in range(x0, x1):
                px_x, px_y = x + 0.5, y + 0.5
                l1 = ((by - cy) * (px_x - cx) + (cx - bx) * (px_y - cy)) / den
                l2 = ((cy - ay) * (px_x - cx) + (ax - cx) * (px_y - cy)) / den
                l3 = 1 - l1 - l2
                if min(l1, l2, l3) < -0.02:
                    continue
                p = pos[0] * l1 + pos[1] * l2 + pos[2] * l3
                px[y, x, :3] = color_at(p, px[y, x, :3])
    img.pixels.foreach_set(px.ravel())
    img.update()


def paso_recargar():
    """Vuelve a la malla original de Rodin (conservando la textura ya pintada) y une las costuras:
    el glTF separa los vértices en las costuras de UV y, si no se unen, al alisar se abren grietas."""
    old = _model()
    img = _image()
    parent = old.parent
    mat = old.data.materials[0]
    bpy.data.objects.remove(old)
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(OUT_DIR, "noe_rodin_original.glb"))
    new_objs = [o for o in bpy.data.objects if o not in before]
    obj = next(o for o in new_objs if o.type == "MESH")
    for o in new_objs:
        if o is not obj:
            bpy.data.objects.remove(o)
    obj.name = "model"
    obj.parent = parent
    obj.matrix_parent_inverse.identity()
    obj.location = (0, 0, 0)
    obj.rotation_euler = (0, 0, 0)
    obj.scale = (1, 1, 1)
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    n0 = len(bm.verts)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    print("vertices", n0, "->", len(bm.verts), "bordes abiertos", sum(1 for e in bm.edges if e.is_boundary))
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def paso_cara(rubor=True):
    obj = _model()
    img = _image()
    mw = obj.matrix_world
    inv = mw.inverted()
    # 1. Geometría: alisar los vértices de las cuencas hasta dejar la cara lisa.
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    for sx in (1, -1):
        zone = [v for v in bm.verts
                if _ellipse(mw @ v.co, sx * EYE[0], EYE[1], EYE_SOCKET[0], EYE_SOCKET[1]) < 1
                and (mw.to_3x3() @ v.normal).y < 0]
        for _ in range(120):
            bmesh.ops.smooth_vert(bm, verts=zone, factor=0.7, use_axis_x=True, use_axis_y=True, use_axis_z=True)
        print("cuenca", sx, "vertices alisados", len(zone))
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()

    # 2. Textura: la zona de los ojos pintados pasa a piel (con borde difuminado).
    # El color de relleno es el de la piel de alrededor (anillo justo fuera de la zona), no el de la paleta.
    ring = {1: [], -1: []}

    def collect(p, cur):
        for sx in (1, -1):
            if 2.6 < _ellipse(p, sx * EYE[0], EYE[1], *EYE_SOCKET) < 4.0 and p.z < EYE[1] + 0.02:
                ring[sx].append(cur.copy())
        return cur

    around = _front_faces(obj, lambda c: min(_ellipse(c, sx * EYE[0], EYE[1], *EYE_SOCKET) for sx in (1, -1)) < 4.2)
    _paint(obj, img, around, collect)
    fill = {sx: np.median(np.array(ring[sx]), axis=0) if ring[sx] else SKIN for sx in (1, -1)}
    print("piel de alrededor", {sx: (fill[sx] * 255).astype(int).tolist() for sx in fill})

    def skin_over_eye(p, cur):
        for sx in (1, -1):
            e = _ellipse(p, sx * EYE[0], EYE[1], *EYE_SOCKET)
            if e < 2.4:
                t = min(1.0, max(0.0, (2.4 - e) / 0.8))     # Lleno hasta 1.6, se difumina hasta 2.4.
                return cur * (1 - t) + fill[sx] * t
        return cur

    faces = _front_faces(obj, lambda c: min(_ellipse(c, sx * EYE[0], EYE[1], *EYE_SOCKET) for sx in (1, -1)) < 2.6)
    _paint(obj, img, faces, skin_over_eye)

    # 2b. Mapa de normales: Rodin hornea ahí la cuenca y seguiría sombreando un hueco.
    #     En esa zona se deja plano (0.5, 0.5, 1 = "sin relieve").
    flat = np.array([0.5, 0.5, 1.0])

    def flat_normal(p, cur):
        for sx in (1, -1):
            e = _ellipse(p, sx * EYE[0], EYE[1], *EYE_SOCKET)
            if e < 1.6:
                t = min(1.0, max(0.0, (1.6 - e) / 0.6))
                return cur * (1 - t) + flat * t
        return cur

    normal_img = next(n.image for n in obj.data.materials[0].node_tree.nodes
                      if n.type == "TEX_IMAGE" and n.image and "normal" in n.image.name)
    _paint(obj, normal_img, faces, flat_normal)

    if not rubor:
        print("cara lista (sin rubor)")
        return
    # 3. Rubor pintado (sustituye a las piezas transparentes).
    for o in [o for o in bpy.data.objects if o.name.startswith("RuborNoe")]:
        bpy.data.objects.remove(o)

    def blush(p, cur):
        for sx in (1, -1):
            e = _ellipse(p, sx * CHEEK[0], CHEEK[1], *CHEEK_SIZE)
            if e < 1:
                t = 0.55 * (1 - e) ** 1.5
                return cur * (1 - t) + BLUSH * t
        return cur

    faces = _front_faces(obj, lambda c: min(_ellipse(c, sx * CHEEK[0], CHEEK[1], *CHEEK_SIZE) for sx in (1, -1)) < 1.2)
    _paint(obj, img, faces, blush)
    print("cara lista")


def paso_ojos():
    """Ojos hundidos en la cara: la mitad de la bolita queda dentro, así parecen parte de ella."""
    obj = _model()
    root = bpy.data.objects["RodinGiro"]
    for o in [o for o in bpy.data.objects if o.name.startswith(("OjoNoe", "BrilloOjo"))]:
        bpy.data.objects.remove(o)
    bvh = BVHTree.FromObject(obj, bpy.context.evaluated_depsgraph_get())
    mw = obj.matrix_world
    inv = mw.inverted()
    d = (inv.to_3x3() @ Vector((0, 1, 0))).normalized()

    def mat(name, rgb, rough):
        m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        m.use_nodes = True
        b = m.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (*[c ** 2.2 for c in rgb], 1)
        b.inputs["Roughness"].default_value = rough
        b.inputs["Metallic"].default_value = 0.0
        return m

    iris = mat("OjoNoe", (0.2, 0.13, 0.09), 0.3)
    glint = mat("BrilloOjo", (1, 1, 1), 0.3)
    for sx, side in ((1, "I"), (-1, "D")):
        hit, n, _i, _d = bvh.ray_cast(inv @ Vector((sx * EYE[0], -2.0, EYE[1])), d)
        surf = mw @ hit
        normal = (mw.to_3x3() @ n).normalized()
        rot = normal.to_track_quat("-Y", "Z").to_euler()
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=1.0, location=surf - normal * 0.002)
        eye = bpy.context.active_object
        eye.name = f"OjoNoe{side}"
        eye.scale = (0.0145, 0.007, 0.0205)
        eye.rotation_euler = rot
        eye.data.materials.append(iris)
        bpy.ops.mesh.primitive_uv_sphere_add(segments=6, ring_count=4, radius=1.0,
                                             location=surf + normal * 0.0042 + Vector((-sx * 0.005, 0, 0.0075)))
        g = bpy.context.active_object
        g.name = f"BrilloOjo{side}"
        g.scale = (0.0038, 0.0015, 0.0044)
        g.rotation_euler = rot
        g.data.materials.append(glint)
        for o in (eye, g):
            for p in o.data.polygons:
                p.use_smooth = True
            bpy.context.view_layer.update()
            wm = o.matrix_world.copy()
            o.parent = root
            o.matrix_world = wm
    print("ojos listos")


def _detail_weight(w):
    """Cuánto detalle conservar en cada zona (0 = reducir normal; con peso 1 no se reduciría nada)."""
    hands = abs(w.x) > 0.29 and w.z < 0.78
    wrists = abs(w.x) > 0.26 and 0.55 < w.z < 0.82
    face = w.z > 1.15 and w.y < -0.06 and abs(w.x) < 0.17
    feet = w.z < 0.1
    if hands:
        return HAND_W
    if wrists or face:
        return FACE_W
    if feet:
        return FEET_W
    return 0.0


HAND_W, FACE_W, FEET_W = 0.85, 0.6, 0.4


def _curvature_weights(obj, max_weight=0.85):
    """Importancia automática de cada vértice según cuánto se dobla la superficie a su alrededor.
    El reductor mide el error en distancia absoluta, así que sacrifica detalles pequeños pero
    muy curvos (dedos, muñecas, bordes de manga, nariz); este peso los protege sin decirle dónde
    están."""
    me = obj.data
    n = len(me.vertices)
    normals = np.array([v.normal[:] for v in me.vertices], np.float32)
    edges = np.array([e.vertices[:] for e in me.edges], np.int64)
    dot = np.clip((normals[edges[:, 0]] * normals[edges[:, 1]]).sum(1), -1, 1)
    ang = np.arccos(dot)                                   # Ángulo entre normales vecinas.
    co = np.array([v.co[:] for v in me.vertices], np.float32)
    length = np.linalg.norm(co[edges[:, 0]] - co[edges[:, 1]], axis=1) + 1e-6
    bend = ang / length                                    # Curvatura (radianes por metro).
    curv = np.zeros(n, np.float32)
    np.maximum.at(curv, edges[:, 0], bend)
    np.maximum.at(curv, edges[:, 1], bend)
    # Suavizado en la malla: la importancia se extiende un poco a los vecinos.
    for _ in range(3):
        acc = np.zeros(n, np.float32)
        cnt = np.zeros(n, np.float32)
        np.add.at(acc, edges[:, 0], curv[edges[:, 1]])
        np.add.at(acc, edges[:, 1], curv[edges[:, 0]])
        np.add.at(cnt, edges[:, 0], 1)
        np.add.at(cnt, edges[:, 1], 1)
        curv = 0.5 * curv + 0.5 * acc / np.maximum(cnt, 1)
    lo, hi = np.percentile(curv, 50), np.percentile(curv, 97)
    return np.clip((curv - lo) / (hi - lo), 0, 1) * max_weight


def _thickness_weights(obj, thin=0.02, thick=0.12, max_weight=0.85):
    """Importancia automática según el grosor de cada zona (rayo hacia dentro del cuerpo hasta la
    superficie opuesta). Lo delgado (dedos, muñecas, nariz, borde de mangas) se protege; lo grueso
    (torso, espalda) cede triángulos. El reductor, si no, destruye primero lo pequeño."""
    from mathutils.bvhtree import BVHTree
    me = obj.data
    bvh = BVHTree.FromPolygons([v.co for v in me.vertices], [p.vertices[:] for p in me.polygons])
    t = np.full(len(me.vertices), thick, np.float32)
    for v in me.vertices:
        n = v.normal
        hit, _n, _i, dist = bvh.ray_cast(v.co - n * 0.001, -n, thick)
        if hit is not None:
            t[v.index] = dist
    # Suavizado: un dedo entero es "delgado", no solo algunos puntos.
    edges = np.array([e.vertices[:] for e in me.edges], np.int64)
    for _ in range(4):
        acc = np.zeros_like(t)
        cnt = np.zeros_like(t)
        np.add.at(acc, edges[:, 0], t[edges[:, 1]])
        np.add.at(acc, edges[:, 1], t[edges[:, 0]])
        np.add.at(cnt, edges[:, 0], 1)
        np.add.at(cnt, edges[:, 1], 1)
        t = 0.5 * t + 0.5 * acc / np.maximum(cnt, 1)
    return np.clip((thick - t) / (thick - thin), 0, 1) * max_weight


def paso_optimizar(target=TARGET_TRIS, prioridad="grosor", hornear=True, factor=1.0, hombros=0.0):
    """Malla ligera con el detalle de la original horneado (normales) y su color (textura)."""
    scene = bpy.context.scene
    high = _model()
    high.hide_viewport = False
    high.hide_render = False
    bpy.ops.object.select_all(action="DESELECT")
    stale = bpy.data.objects.get(f"NoeLow{target}")
    if stale is not None:
        bpy.data.objects.remove(stale)
    for o in [o for o in bpy.data.objects if o.name.startswith(f"NoeLow{target}.")]:
        bpy.data.objects.remove(o)
    low = high.copy()
    low.data = high.data.copy()
    low.name = f"NoeLow{target}"
    assert low.name == f"NoeLow{target}", low.name
    high.users_collection[0].objects.link(low)
    tris = sum(len(p.vertices) - 2 for p in high.data.polygons)
    mod = low.modifiers.new("Reducir", "DECIMATE")
    mod.ratio = target / tris
    if prioridad:
        # Reparte los triángulos: más donde la superficie se dobla mucho (o en las zonas fijas).
        vg = low.vertex_groups.new(name="Detalle")
        mwl = low.matrix_world
        if prioridad == "grosor":
            weights = _thickness_weights(low)
            if hombros:
                # Prioridad extra en la costura manga/chaleco de los hombros.
                for v in low.data.vertices:
                    w = mwl @ v.co
                    if 0.15 < abs(w.x) < 0.34 and 0.9 < w.z < 1.15:
                        weights[v.index] = max(weights[v.index], hombros)
        elif prioridad == "curvatura":
            weights = _curvature_weights(low)
        else:
            weights = [_detail_weight(mwl @ v.co) for v in low.data.vertices]
        for v, wgt in zip(low.data.vertices, weights):
            if wgt > 0:
                vg.add([v.index], float(wgt), "REPLACE")
        mod.vertex_group = vg.name
        mod.vertex_group_factor = factor
        mod.invert_vertex_group = True
    bpy.context.view_layer.objects.active = low
    with bpy.context.temp_override(object=low, active_object=low):
        bpy.ops.object.modifier_apply(modifier=mod.name)
    print("triangulos", tris, "->", sum(len(p.vertices) - 2 for p in low.data.polygons))
    mwl = low.matrix_world
    hand_tris = sum(1 for p in low.data.polygons if _detail_weight(mwl @ p.center) == HAND_W)
    print("triangulos en las manos", hand_tris)
    print("triangulos en los hombros", sum(1 for p in low.data.polygons
                                           if 0.15 < abs((mwl @ p.center).x) < 0.34 and 0.9 < (mwl @ p.center).z < 1.15))
    if low.vertex_groups.get("Detalle"):
        low.vertex_groups.remove(low.vertex_groups["Detalle"])
    if not hornear:
        # Material propio (si no, compartiría el de la malla original y se estropearía al hornear).
        low.data.materials[0] = high.data.materials[0].copy()
        print("sin hornear")
        return

    size = 2048
    color = bpy.data.images.new(f"NoeColor{target}", size, size)
    normal = bpy.data.images.new(f"NoeNormal{target}", size, size, is_data=True)
    normal.colorspace_settings.name = "Non-Color"
    # Material nuevo para la malla ligera: color + normal.
    mat = bpy.data.materials.new(f"NoeLow{target}")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.72
    bsdf.inputs["Metallic"].default_value = 0.0
    bsdf.inputs["Specular IOR Level"].default_value = 0.35
    tc = nt.nodes.new("ShaderNodeTexImage")
    tc.image = color
    tn = nt.nodes.new("ShaderNodeTexImage")
    tn.image = normal
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(tc.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    low.data.materials.clear()
    low.data.materials.append(mat)

    scene.render.engine = "CYCLES"
    scene.cycles.samples = 8
    scene.cycles.device = "CPU"
    bake = scene.render.bake
    bake.use_selected_to_active = True
    bake.cage_extrusion = 0.012
    bake.max_ray_distance = 0.03
    bake.margin = 8
    bpy.ops.object.select_all(action="DESELECT")
    high.select_set(True)
    low.select_set(True)
    bpy.context.view_layer.objects.active = low
    for image, kind in ((normal, "NORMAL"), (color, "DIFFUSE")):
        nt.nodes.active = tn if image is normal else tc
        bake.use_pass_direct = False
        bake.use_pass_indirect = False
        bake.use_pass_color = True
        bpy.ops.object.bake(type=kind)
        print("horneado", kind)
    color.filepath_raw = os.path.join(OUT_DIR, f"noe_color_{target}.png")
    color.file_format = "PNG"
    color.save()
    normal.filepath_raw = os.path.join(OUT_DIR, f"noe_normal_{target}.png")
    normal.file_format = "PNG"
    normal.save()
    high.hide_render = True
    high.hide_viewport = True
    scene.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in [e.identifier for e in
                                                                 bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else "BLENDER_EEVEE_NEXT"
    print("optimizado")


def paso_mostrar(target):
    """Deja visible solo la versión indicada (y los ojos)."""
    for o in bpy.data.objects:
        if o.type == "MESH" and (o.name == "model" or o.name.startswith("NoeLow")):
            show = o.name == f"NoeLow{target}"
            o.hide_viewport = not show
            o.hide_render = not show


def paso_exportar(path):
    bpy.ops.object.select_all(action="DESELECT")
    for o in bpy.data.objects:
        if o.name != "model" and not o.hide_viewport:
            o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_yup=True,
                              export_apply=True)
    bpy.ops.wm.save_as_mainfile(filepath=path.replace(".glb", ".blend"), copy=True)
    print("exportado", path)
