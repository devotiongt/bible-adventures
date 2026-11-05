"""Genera el cuerpo y la ropa de Noé en Blender y los exporta a glTF para Godot.

Uso (sin abrir Blender):
    blender --background --factory-startup --python herramientas/blender/tunica.py -- assets/personajes/tunica.glb [carpeta_renders]
En vivo, con Blender abierto (ver en_vivo.py):
    python3 herramientas/blender/en_vivo.py tunica paso_importar paso_adelgazar paso_tunica paso_nudo paso_falda

Produce tres mallas con el esqueleto del personaje base de Quaternius:
    Cuerpo  el cuerpo base adelgazado (el original es de "superhéroe").
    Tunica  sale del propio cuerpo: una copia de la piel separada 1,5 cm y alisada, así que
            se ajusta sin capas y hereda los pesos exactos del cuerpo (nunca lo atraviesa).
            El manto y la faja son zonas de color de la misma prenda, más el nudo de la faja.
    Falda   la falda con pliegues verticales. No lleva huesos: en Godot la mueve la simulación
            de tela (scripts/robe_cloth.gd). UV = (vuelta 0..1, altura 0 cintura .. 1 borde).

Las medidas están en el espacio del personaje en glTF (Y arriba, mira hacia +Z) y se pasan a
Blender con g(): Blender = (x, -z, y).
"""

import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = globals().get("PROJECT_ROOT", os.getcwd())
CHARACTER = os.path.join(ROOT, "assets/personajes/Superhero_Male_FullBody.gltf")

# Perfil de la falda: [altura, semieje x, semieje z, centro z]. Igual que ROBE_PROFILE en noah_model.gd.
SKIRT_PROFILE = [
    [0.05, 0.29, 0.26, -0.02],
    [0.45, 0.26, 0.23, -0.02],
    [0.9, 0.2, 0.16, -0.03],
    [1.04, 0.16, 0.125, -0.025],   # Justo por dentro de la faja (medida en Blender).
]
SKIRT_TOP = 1.04       # Debe coincidir con SKIRT_TOP en noah_model.gd (queda bajo la faja).
HEM_HEIGHT = 0.32      # Debe coincidir con HEM_HEIGHT en noah_model.gd.

## Cuánto se estrecha cada zona del cuerpo (1 = igual). La cabeza, manos y pies no cambian.
SLIM = {
    "pelvis": 0.92, "spine_01": 0.88, "spine_02": 0.84, "spine_03": 0.84, "neck_01": 0.95,
    "clavicle_l": 0.86, "clavicle_r": 0.86, "upperarm_l": 0.8, "upperarm_r": 0.8,
    "lowerarm_l": 0.88, "lowerarm_r": 0.88, "thigh_l": 0.88, "thigh_r": 0.88, "calf_l": 0.94, "calf_r": 0.94,
}

COLORS = {
    "Lino": (0.69, 0.56, 0.37),
    "Manto": (0.2, 0.11, 0.05),
    "Faja": (0.3, 0.05, 0.03),
    "Borde": (0.27, 0.15, 0.07),
}


def g(x, y, z):
    return Vector((x, -z, y))


def to_gltf(v):
    return Vector((v.x, v.z, -v.y))


def profile_at(profile, y):
    k = 0
    while k < len(profile) - 2 and profile[k + 1][0] < y:
        k += 1
    a, b = profile[k], profile[k + 1]
    t = max(0.0, min(1.0, (y - a[0]) / (b[0] - a[0])))
    return (a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t)


def material(name):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes["Principled BSDF"]
        bsdf.inputs["Base Color"].default_value = (*COLORS[name], 1)
        bsdf.inputs["Roughness"].default_value = 0.95
        mat.use_backface_culling = False
    return mat


def folds(a, v, count=11.0, sharp=1.6):
    """Pliegues verticales: crestas suaves alrededor del cuerpo."""
    wave = 0.5 + 0.5 * math.sin(count * a + 0.7 * math.sin(3 * a + 1.3) + v * 1.2)
    return wave ** sharp


def _armature():
    return next(o for o in bpy.data.objects if o.type == "ARMATURE")


def _segment_point(p, a, b):
    ab = b - a
    t = max(0.0, min(1.0, (p - a).dot(ab) / ab.length_squared))
    return a + ab * t


# --- Pasos (se pueden ejecutar uno a uno en un Blender abierto) -----------------

def _context():
    """Contexto de la vista 3D, para que los operadores funcionen desde el add-on."""
    wm = bpy.context.window_manager
    win = wm.windows[0] if wm and wm.windows else None
    if win is None:
        return {}
    for area in win.screen.areas:
        if area.type == "VIEW_3D":
            region = next(r for r in area.regions if r.type == "WINDOW")
            return {"window": win, "screen": win.screen, "area": area, "region": region}
    return {"window": win, "screen": win.screen}


def _run(fn, *args):
    with bpy.context.temp_override(**_context()):
        return fn(*args)


def _frame_character():
    ctx = _context()
    if "area" not in ctx:
        return
    from mathutils import Euler
    space = ctx["area"].spaces.active
    space.shading.type = "MATERIAL"
    space.overlay.show_bones = False
    r3d = space.region_3d
    r3d.view_location = Vector((0, 0, 0.95))
    r3d.view_distance = 3.6
    r3d.view_rotation = Euler((math.radians(80), 0, math.radians(25))).to_quaternion()


def paso_importar():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.armatures, bpy.data.images):
        for block in list(coll):
            if block.users == 0:
                coll.remove(block)
    bpy.ops.import_scene.gltf(filepath=CHARACTER)
    for o in [o for o in bpy.data.objects if o.type == "MESH" and o.parent is None]:
        bpy.data.objects.remove(o)  # Icosfera suelta que trae el glTF.
    bpy.data.objects["SuperHero_Male"].name = "Cuerpo"
    _frame_character()


def paso_adelgazar():
    """Acerca cada vértice al eje de sus huesos según SLIM, mezclando por sus pesos."""
    body = bpy.data.objects["Cuerpo"]
    arm = _armature()
    segments = {}
    for bone in arm.data.bones:
        if bone.name in SLIM:
            segments[bone.name] = (arm.matrix_world @ bone.head_local, arm.matrix_world @ bone.tail_local)
    names = {vg.index: vg.name for vg in body.vertex_groups}
    for v in body.data.vertices:
        p = body.matrix_world @ v.co
        new = Vector((0, 0, 0))
        total = 0.0
        for gr in v.groups:
            name = names.get(gr.group)
            if gr.weight <= 0.0:
                continue
            if name in segments:
                axis = _segment_point(p, *segments[name])
                new += (axis + (p - axis) * SLIM[name]) * gr.weight
            else:
                new += p * gr.weight
            total += gr.weight
        if total > 0:
            v.co = body.matrix_world.inverted() @ (new / total)
    body.data.update()


def _keep_for_tunic(p):
    """Zona del cuerpo que cubre la túnica (en coordenadas glTF): torso y brazo hasta el codo."""
    x, y = abs(p.x), p.y
    if 0.9 <= y <= 1.5 and x <= SLEEVE_END + 0.04:
        return True
    return 1.5 < y <= 1.58 and 0.1 < x <= SLEEVE_END + 0.04  # Hombros, sin el cuello.


SLEEVE_END = 0.6        # Mangas tres cuartos: pasan el codo (0,46).
SASH = (0.98, 1.1)      # Altura de la faja.
MANTLE_FRONT = 1.36     # El manto llega hasta aquí por delante...
MANTLE_BACK = 1.18      # ...y más abajo por la espalda.


def _cut(bm, co, no, clear_outer=False, clear_inner=False):
    """Corta la malla con un plano (para bordes de color rectos, o para recortarla)."""
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    bmesh.ops.bisect_plane(bm, geom=geom, plane_co=co, plane_no=no, clear_outer=clear_outer, clear_inner=clear_inner)


def paso_tunica():
    body = bpy.data.objects["Cuerpo"]
    tunic = body.copy()
    tunic.data = body.data.copy()
    tunic.name = "Tunica"
    tunic.data.name = "Tunica"
    bpy.context.scene.collection.objects.link(tunic)
    tunic.data.materials.clear()
    for name in ("Lino", "Manto", "Faja", "Borde"):
        tunic.data.materials.append(material(name))

    bm = bmesh.new()
    bm.from_mesh(tunic.data)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not _keep_for_tunic(to_gltf(v.co))], context="VERTS")
    # Alisar: la tela no marca músculos.
    for _ in range(6):
        bmesh.ops.smooth_vert(bm, verts=bm.verts, factor=0.5, use_axis_x=True, use_axis_y=True, use_axis_z=True)
    bm.normal_update()
    for v in bm.verts:
        p = to_gltf(v.co)
        offset = 0.016
        # Faja: un poco más gruesa, por encima de la tela.
        if 0.98 <= p.y <= 1.1 and abs(p.x) < 0.3:
            offset += 0.012
        # Pliegues suaves en el pecho y la espalda.
        a = math.atan2(p.z + 0.02, p.x)
        offset += 0.006 * folds(a, p.y * 4, 9, 2.0)
        v.co += v.normal * offset
        # Mangas algo holgadas al final (en reposo los brazos están en cruz).
        if abs(p.x) > 0.26:
            t = min(1.0, (abs(p.x) - 0.26) / (SLEEVE_END - 0.26))
            center = g(p.x, 1.4555 - 0.02 * t, -0.0654)
            radial = v.co - center
            radial.x = 0.0
            v.co = center + Vector((v.co.x - center.x, 0, 0)) + radial * (1.0 + 0.35 * t * t)
    # Recortes limpios: bajo de la túnica (queda dentro de la falda) y final de las mangas.
    _cut(bm, (0, 0, 0.95), (0, 0, 1), clear_inner=True)
    _cut(bm, (SLEEVE_END, 0, 0), (1, 0, 0), clear_outer=True)
    _cut(bm, (-SLEEVE_END, 0, 0), (-1, 0, 0), clear_outer=True)
    # Cortes por donde cambia el color, para que los bordes salgan rectos.
    for h in (SASH[0], SASH[1], MANTLE_BACK, MANTLE_FRONT):
        _cut(bm, (0, 0, h), (0, 0, 1))
    _cut(bm, (0, 0.03, 0), (0, 1, 0))   # Separación delante / espalda (glTF z = -0,03).
    for sx in (1, -1):
        _cut(bm, (sx * (SLEEVE_END - 0.04), 0, 0), (1, 0, 0))
        _cut(bm, (sx * 0.28, 0, 0), (1, 0, 0))   # Hombro: hasta aquí llega el manto.
    # Zonas de color: manto sobre hombros y espalda, faja en la cintura, borde de las mangas.
    for f in bm.faces:
        c = to_gltf(f.calc_center_median())
        if SASH[0] <= c.y <= SASH[1] and abs(c.x) < 0.3:
            f.material_index = 2
        elif abs(c.x) > SLEEVE_END - 0.04:
            f.material_index = 3
        elif abs(c.x) < 0.28 and (c.y > MANTLE_FRONT or (c.y > MANTLE_BACK and c.z < -0.03)):
            f.material_index = 1
        else:
            f.material_index = 0
        f.smooth = True
    bm.to_mesh(tunic.data)
    bm.free()
    tunic.data.update()
    # Por si el alisado metió algún punto dentro del cuerpo.
    push_out(tunic, BVHTree.FromObject(body, bpy.context.evaluated_depsgraph_get()), 0.012)


def paso_nudo():
    """Nudo de la faja y dos tiras colgando, pegados a la pelvis."""
    tunic = bpy.data.objects["Tunica"]
    front = max(to_gltf(tunic.matrix_world @ v.co).z for v in tunic.data.vertices
                if 1.0 < to_gltf(tunic.matrix_world @ v.co).y < 1.08)
    parts = []
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=0.04, location=g(0.06, 1.045, front + 0.01))
    knot = bpy.context.active_object
    knot.scale = (1.3, 0.8, 1.0)
    parts.append(knot)
    for dx, length, tilt in ((0.045, 0.26, 8), (0.085, 0.2, -5)):
        bpy.ops.mesh.primitive_cube_add(size=1, location=g(dx, 1.02 - length * 0.5, front + 0.012))
        strip = bpy.context.active_object
        strip.scale = (0.045, 0.012, length)
        strip.rotation_euler = (math.radians(-4), math.radians(tilt), 0)
        parts.append(strip)
    for p in parts:
        p.data.materials.clear()
        p.data.materials.append(material("Faja"))
        bpy.ops.object.select_all(action="DESELECT")
        p.select_set(True)
        bpy.context.view_layer.objects.active = p
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        p.vertex_groups.new(name="pelvis").add(list(range(len(p.data.vertices))), 1.0, "REPLACE")
    bpy.ops.object.select_all(action="DESELECT")
    for p in parts:
        p.select_set(True)
    tunic.select_set(True)
    bpy.context.view_layer.objects.active = tunic
    bpy.ops.object.join()


def paso_falda():
    seg = 64
    ring_count = 24
    bm = bmesh.new()
    uv_layer = bm.loops.layers.uv.new("UVMap")
    rows = []
    uv = {}
    for r in range(ring_count + 1):
        v = r / ring_count
        y = SKIRT_TOP + (HEM_HEIGHT - SKIRT_TOP) * v
        rx, rz, cz = profile_at(SKIRT_PROFILE, y)
        ring = []
        for s in range(seg + 1):  # Se repite la costura para que la UV no salte.
            a = math.tau * s / seg
            depth = 0.03 * v ** 0.9 * folds(a, v, 12, 1.0) + 0.006 * math.sin(a * 3 + 0.5) * v
            vert = bm.verts.new(g(math.cos(a) * (rx + depth), y, cz + math.sin(a) * (rz + depth)))
            uv[vert] = (s / seg, 1.0 - v)   # glTF invierte la V al exportar.
            ring.append(vert)
        rows.append(ring)
    hem_rows = 3
    for r in range(ring_count):
        for s in range(seg):
            f = bm.faces.new((rows[r][s], rows[r][s + 1], rows[r + 1][s + 1], rows[r + 1][s]))
            f.material_index = 1 if r >= ring_count - hem_rows else 0
            f.smooth = True
            for loop in f.loops:
                loop[uv_layer].uv = uv[loop.vert]
    mesh = bpy.data.meshes.new("Falda")
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(material("Lino"))
    mesh.materials.append(material("Borde"))
    skirt = bpy.data.objects.new("Falda", mesh)
    bpy.context.scene.collection.objects.link(skirt)


def push_out(obj, body_bvh, margin):
    """Saca de dentro del cuerpo cualquier vértice que lo atraviese en reposo."""
    for v in obj.data.vertices:
        co = obj.matrix_world @ v.co
        loc, normal, _i, _dist = body_bvh.find_nearest(co)
        if loc is None:
            continue
        if (co - loc).dot(normal) < margin:
            v.co = obj.matrix_world.inverted() @ (loc + normal * margin)


def paso_exportar(out_path):
    bpy.ops.object.select_all(action="DESELECT")
    for o in (_armature(), bpy.data.objects["Cuerpo"], bpy.data.objects["Tunica"], bpy.data.objects["Falda"]):
        o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=out_path, export_format="GLB", use_selection=True, export_yup=True,
                              export_apply=True, export_skins=True, export_animations=False,
                              export_texcoords=True, export_normals=True)
    print(f"TUNICA OK -> {out_path}")


def render(folder):
    scene = bpy.context.scene
    for engine in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
        try:
            scene.render.engine = engine
            break
        except TypeError:
            continue
    scene.render.resolution_x = 700
    scene.render.resolution_y = 900
    world = bpy.data.worlds.new("Cielo")
    world.color = (0.6, 0.66, 0.72)
    scene.world = world
    sun = bpy.data.objects.new("Sol", bpy.data.lights.new("Sol", "SUN"))
    sun.data.energy = 3.5
    sun.rotation_euler = (math.radians(55), 0, math.radians(-30))
    scene.collection.objects.link(sun)
    cam = bpy.data.objects.new("Camara", bpy.data.cameras.new("Camara"))
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 2.25
    scene.collection.objects.link(cam)
    scene.camera = cam
    for label, pos in (("frente", (0.9, -3.2, 1.05)), ("espalda", (-0.9, 3.2, 1.05))):
        cam.location = pos
        cam.rotation_euler = (Vector((0, 0, 0.95)) - Vector(pos)).to_track_quat("-Z", "Y").to_euler()
        scene.render.filepath = f"{folder}/tunica_{label}.png"
        bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(sun)
    bpy.data.objects.remove(cam)


PASOS = [paso_importar, paso_adelgazar, paso_tunica, paso_nudo, paso_falda]


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out_path = argv[0] if argv else "tunica.glb"
    renders = argv[1] if len(argv) > 1 else None
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for paso in PASOS:
        paso()
    if renders:
        render(renders)
    paso_exportar(out_path)


if not globals().get("EN_VIVO"):
    main()
