"""Noé en estilo chibi (cabeza grande, formas redondas, colores planos), hecho en Blender.

Uso (sin abrir Blender):
    blender --background --factory-startup --python herramientas/blender/noe_chibi.py -- assets/personajes/noe_chibi.glb [carpeta_renders]
En vivo, con Blender abierto:
    python3 herramientas/blender/en_vivo.py noe_chibi paso_limpiar paso_cuerpo paso_cabeza paso_brazos paso_pies

El personaje no lleva huesos: es una jerarquía de piezas con su pivote, pensada para animarse
por código en Godot (rebote al andar, balanceo de brazos, pasitos, parpadeo):
    Noe
    ├─ Cuerpo          túnica, manto, faja y nudo   (pivote en la cadera)
    │  ├─ Cabeza       cara, pelo, barba, cejas     (pivote en el cuello)
    │  │  ├─ OjoI / OjoD                            (para parpadear)
    │  ├─ BrazoI / BrazoD  manga y mano             (pivote en el hombro)
    ├─ PieI / PieD     pie con sandalia             (pivote en el tobillo)
Ejes de Blender: Z arriba, Noé mira hacia -Y (en Godot, hacia +Z del modelo).
"""

import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

ROOT = globals().get("PROJECT_ROOT", os.getcwd())

COLORS = {
    "Piel": (0.91, 0.70, 0.56),
    "Tunica": (0.93, 0.87, 0.74),
    "Manto": (0.55, 0.36, 0.22),
    "Faja": (0.73, 0.26, 0.19),
    "Canas": (0.97, 0.96, 0.93),
    "Cuero": (0.45, 0.28, 0.16),
    "Ojo": (0.16, 0.11, 0.08),
    "Brillo": (1.0, 1.0, 1.0),
    "Rubor": (0.95, 0.6, 0.52),
    "Borde": (0.62, 0.43, 0.27),
}

HEAD_CENTER = Vector((0, 0, 0.93))
HEAD_R = 0.27


# --- Utilidades -----------------------------------------------------------------

def material(name):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes["Principled BSDF"]
        rgb = tuple(c ** 2.2 for c in COLORS[name])  # Colores pensados en sRGB.
        bsdf.inputs["Base Color"].default_value = (*rgb, 1)
        bsdf.inputs["Roughness"].default_value = 0.35 if name in ("Ojo", "Brillo") else 0.75
        mat.diffuse_color = (*rgb, 1)
    return mat


def finish(obj, mat_name, subdiv=1, smooth=True):
    obj.data.materials.clear()
    obj.data.materials.append(material(mat_name))
    if smooth:
        for p in obj.data.polygons:
            p.use_smooth = True
    if subdiv:
        mod = obj.modifiers.new("Suave", "SUBSURF")
        mod.levels = subdiv
        mod.render_levels = subdiv
    return obj


def sphere(name, center, scale, mat_name, segments=24, rings=12, subdiv=1):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, radius=1.0, location=center)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return finish(obj, mat_name, subdiv)


def lathe(name, profile, mat_name, segments=40, wave=None, cap_top=True, cap_bottom=True, subdiv=1):
    """Superficie de revolución. profile: [(z, radio), ...] de abajo arriba.
    wave(a, t) devuelve un factor que multiplica el radio (pliegues)."""
    bm = bmesh.new()
    rings = []
    for i, (z, r) in enumerate(profile):
        t = i / (len(profile) - 1)
        ring = []
        for s in range(segments):
            a = math.tau * s / segments
            k = wave(a, t) if wave else 1.0
            ring.append(bm.verts.new((math.cos(a) * r * k, math.sin(a) * r * k, z)))
        rings.append(ring)
    for i in range(len(rings) - 1):
        for s in range(segments):
            s2 = (s + 1) % segments
            bm.faces.new((rings[i][s], rings[i][s2], rings[i + 1][s2], rings[i + 1][s]))
    if cap_bottom:
        bm.faces.new(list(reversed(rings[0])))
    if cap_top:
        bm.faces.new(rings[-1])
    bm.normal_update()
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return finish(obj, mat_name, subdiv)


def on_head(x, z, out=0.0):
    """Punto de la superficie frontal de la cabeza a esa x, z (más 'out' hacia fuera)."""
    d = Vector((x, 0, z)) - HEAD_CENTER
    y = -math.sqrt(max(HEAD_R ** 2 - d.x ** 2 - d.z ** 2, 0.0))
    p = HEAD_CENTER + Vector((d.x, y, d.z))
    return p + (p - HEAD_CENTER).normalized() * out


def pivot(name, location, parent=None):
    empty = bpy.data.objects.new(name, None)
    empty.empty_display_size = 0.08
    empty.location = location
    bpy.context.scene.collection.objects.link(empty)
    if parent:
        attach(empty, parent)
    return empty


def attach(child, parent):
    bpy.context.view_layer.update()
    world = child.matrix_world.copy()
    child.parent = parent
    child.matrix_world = world


def obj(name):
    return bpy.data.objects[name]


# --- Pasos ----------------------------------------------------------------------

def paso_limpiar():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.armatures, bpy.data.images, bpy.data.lights,
                 bpy.data.cameras):
        for block in list(coll):
            if block.users == 0:
                coll.remove(block)
    root = pivot("Noe", (0, 0, 0))
    pivot("Cuerpo", (0, 0, 0.32), root)
    _view()


def paso_cuerpo():
    body = obj("Cuerpo")

    def folds(a, t):
        # Pliegues suaves que se pierden hacia arriba.
        return 1.0 + 0.045 * (1 - t) ** 2 * math.sin(9 * a + 0.6)

    robe = lathe("Tunica", [(0.09, 0.27), (0.14, 0.265), (0.28, 0.225), (0.42, 0.2), (0.53, 0.185),
                            (0.6, 0.16), (0.65, 0.115), (0.68, 0.05)], "Tunica", wave=folds)
    hem = lathe("Borde", [(0.085, 0.276), (0.13, 0.272)], "Borde", wave=folds, cap_top=False, cap_bottom=False)
    mantle = lathe("Manto", [(0.47, 0.215), (0.53, 0.212), (0.6, 0.19), (0.655, 0.14), (0.69, 0.07)], "Manto",
                   wave=lambda a, t: 1.0 + 0.03 * (1 - t) * math.sin(7 * a), cap_bottom=False)
    sash = lathe("Faja", [(0.29, 0.222), (0.3, 0.232), (0.35, 0.226), (0.36, 0.214)], "Faja",
                 cap_top=False, cap_bottom=False)
    knot = sphere("Nudo", (0.05, -0.225, 0.325), (0.045, 0.03, 0.04), "Faja")
    tails = []
    for i, (dx, length, tilt) in enumerate(((0.035, 0.14, 0.15), (0.07, 0.11, -0.1))):
        bpy.ops.mesh.primitive_cube_add(size=1, location=(dx, -0.228, 0.305 - length * 0.5))
        tail = bpy.context.active_object
        tail.name = f"Cinta{i}"
        tail.scale = (0.035, 0.012, length)
        tail.rotation_euler = (0.12, tilt, 0)
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        finish(tail, "Faja", subdiv=1)
        tails.append(tail)
    for part in [robe, hem, mantle, sash, knot] + tails:
        attach(part, body)


def paso_cabeza():
    head = pivot("Cabeza", (0, 0, 0.68), obj("Cuerpo"))
    parts = [sphere("Cara", HEAD_CENTER, (HEAD_R, HEAD_R * 0.97, HEAD_R * 0.95), "Piel", 32, 16)]
    # Orejas y nariz.
    for sx in (1, -1):
        parts.append(sphere(f"Oreja{'I' if sx > 0 else 'D'}", HEAD_CENTER + Vector((sx * 0.262, 0.01, -0.01)),
                            (0.04, 0.03, 0.055), "Piel"))
    parts.append(sphere("Nariz", on_head(0, 0.885, 0.012), (0.04, 0.035, 0.035), "Piel"))
    # Rubor en las mejillas.
    for sx in (1, -1):
        p = on_head(sx * 0.14, 0.87, -0.004)
        parts.append(sphere(f"Rubor{'I' if sx > 0 else 'D'}", p, (0.045, 0.012, 0.03), "Rubor", subdiv=0))
    # Pelo canoso: herradura de mechones esponjosos de oreja a oreja por la nuca, pegada
    # al cráneo (calvo por arriba, como un abuelo). Tres filas de bolitas que se solapan.
    for row, (dz, count, size) in enumerate(((-0.02, 12, 0.05), (-0.08, 12, 0.056), (-0.14, 10, 0.05))):
        ring_r = math.sqrt(HEAD_R ** 2 - dz ** 2)
        for i in range(count):
            ang = -0.12 + (math.pi + 0.24) * i / (count - 1)   # Lado izquierdo -> nuca -> derecho.
            wobble = 1.0 + 0.15 * math.sin(i * 2.3 + row * 1.7)
            out = ring_r + size * 0.05
            pos = HEAD_CENTER + Vector((math.cos(ang) * out, math.sin(ang) * out + 0.005, dz))
            parts.append(sphere(f"Pelo{row}_{i}", pos, (size * wobble, size * wobble, size * 0.85 * wobble),
                                "Canas", 16, 8))
    # Barba grande y redondeada, en forma de gota.
    beard = sphere("Barba", on_head(0, 0.78, -0.05) + Vector((0, -0.02, -0.06)), (0.2, 0.13, 0.2), "Canas", 32, 16)
    for v in beard.data.vertices:
        if v.co.z < 0:
            v.co.x *= 1.0 + v.co.z * 2.2   # Se estrecha hacia la punta.
        v.co.z *= 1.15 if v.co.z < 0 else 0.8
    parts.append(beard)
    # Bigote y cejas pobladas.
    for sx in (1, -1):
        m = sphere(f"Bigote{'I' if sx > 0 else 'D'}", on_head(sx * 0.055, 0.845, 0.01), (0.07, 0.035, 0.03), "Canas")
        m.rotation_euler = (0, sx * -0.35, 0)
        parts.append(m)
        b = sphere(f"Ceja{'I' if sx > 0 else 'D'}", on_head(sx * 0.1, 1.005, 0.008), (0.055, 0.025, 0.022), "Canas")
        b.rotation_euler = (0, sx * 0.2, 0)
        parts.append(b)
    for part in parts:
        attach(part, head)
    # Ojos (piezas propias para poder parpadear).
    for sx, side in ((1, "I"), (-1, "D")):
        center = on_head(sx * 0.095, 0.935, 0.0)
        eye = pivot(f"Ojo{side}", center, head)
        e = sphere(f"Pupila{side}", center, (0.03, 0.015, 0.045), "Ojo", subdiv=0)
        g = sphere(f"Brillo{side}", center + Vector((sx * -0.008, -0.012, 0.016)), (0.009, 0.005, 0.011), "Brillo",
                   12, 6, subdiv=0)
        attach(e, eye)
        attach(g, eye)


def paso_brazos():
    body = obj("Cuerpo")
    for sx, side in ((1, "I"), (-1, "D")):
        shoulder = Vector((sx * 0.15, 0, 0.6))
        arm = pivot(f"Brazo{side}", shoulder, body)
        # Manga acampanada hacia abajo y un poco hacia fuera.
        sleeve = lathe(f"Manga{side}", [(-0.25, 0.085), (-0.2, 0.08), (-0.1, 0.07), (0.0, 0.06), (0.04, 0.03)],
                       "Tunica", segments=24, cap_bottom=False,
                       wave=lambda a, t: 1.0 + 0.06 * (1 - t) * math.sin(6 * a))
        sleeve.location = shoulder
        sleeve.rotation_euler = (0, -sx * 0.32, 0)
        hand_pos = shoulder + Vector((sx * math.sin(0.32) * 0.28, -0.01, -math.cos(0.32) * 0.28))
        hand = sphere(f"Mano{side}", hand_pos, (0.055, 0.05, 0.06), "Piel")
        for part in (sleeve, hand):
            attach(part, arm)


def paso_pies():
    root = obj("Noe")
    for sx, side in ((1, "I"), (-1, "D")):
        ankle = Vector((sx * 0.09, -0.11, 0.07))
        foot = pivot(f"Pie{side}", ankle, root)
        skin = sphere(f"Dedos{side}", ankle + Vector((0, -0.045, -0.025)), (0.06, 0.09, 0.045), "Piel")
        sole = sphere(f"Suela{side}", ankle + Vector((0, -0.04, -0.06)), (0.07, 0.105, 0.016), "Cuero", subdiv=1)
        strap = lathe(f"Tira{side}", [(-0.01, 0.062), (0.012, 0.064)], "Cuero", segments=20,
                      cap_top=False, cap_bottom=False)
        strap.location = ankle + Vector((0, -0.06, -0.035))
        strap.scale = (1.0, 0.8, 1.0)
        strap.rotation_euler = (1.25, 0, 0)
        for part in (skin, sole, strap):
            attach(part, foot)
    _view()


def _view():
    wm = bpy.context.window_manager
    if not wm or not wm.windows:
        return
    from mathutils import Euler
    for area in wm.windows[0].screen.areas:
        if area.type == "VIEW_3D":
            space = area.spaces.active
            space.shading.type = "MATERIAL"
            space.overlay.show_relationship_lines = False
            r3d = space.region_3d
            r3d.view_location = Vector((0, 0, 0.6))
            r3d.view_distance = 2.4
            r3d.view_rotation = Euler((math.radians(78), 0, math.radians(-28))).to_quaternion()


def paso_render(folder):
    scene = bpy.context.scene
    for engine in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
        try:
            scene.render.engine = engine
            break
        except TypeError:
            continue
    scene.render.resolution_x = 900
    scene.render.resolution_y = 900
    scene.render.film_transparent = False
    try:
        scene.view_settings.view_transform = "AgX"
    except TypeError:
        scene.view_settings.view_transform = "Filmic"
    world = bpy.data.worlds.get("Cielo") or bpy.data.worlds.new("Cielo")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.62, 0.78, 0.9, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.9
    scene.world = world
    added = []
    key = bpy.data.objects.new("Sol", bpy.data.lights.new("Sol", "SUN"))
    key.data.energy = 3.2
    key.data.angle = math.radians(8)
    key.rotation_euler = (math.radians(50), math.radians(10), math.radians(-35))
    fill = bpy.data.objects.new("Relleno", bpy.data.lights.new("Relleno", "AREA"))
    fill.data.energy = 120
    fill.data.size = 2
    fill.location = (-1.5, -1.5, 1.5)
    fill.rotation_euler = (math.radians(55), 0, math.radians(-135))
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=0.8, depth=0.08, location=(0, 0, -0.04))
    ground = bpy.context.active_object
    ground.name = "Cesped"
    gmat = bpy.data.materials.new("Cesped")
    gmat.use_nodes = True
    gmat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.24, 0.45, 0.12, 1)
    ground.data.materials.append(gmat)
    cam = bpy.data.objects.new("Camara", bpy.data.cameras.new("Camara"))
    cam.data.lens = 70
    added += [key, fill, cam]
    for o in (key, fill, cam):
        scene.collection.objects.link(o)
    added.append(ground)
    scene.camera = cam
    shots = (("frente", (1.3, -2.9, 1.25)), ("lado", (2.9, -0.7, 1.1)), ("espalda", (-1.2, 2.9, 1.3)))
    for label, pos in shots:
        cam.location = pos
        cam.rotation_euler = (Vector((0, 0, 0.6)) - Vector(pos)).to_track_quat("-Z", "Y").to_euler()
        scene.render.filepath = os.path.join(folder, f"noe_chibi_{label}.png")
        bpy.ops.render.render(write_still=True)
    for o in added:
        bpy.data.objects.remove(o)


def paso_exportar(out_path):
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.gltf(filepath=out_path, export_format="GLB", use_selection=True, export_yup=True,
                              export_apply=True, export_animations=False)
    print(f"NOE OK -> {out_path}")


PASOS = [paso_limpiar, paso_cuerpo, paso_cabeza, paso_brazos, paso_pies]


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out_path = argv[0] if argv else "noe_chibi.glb"
    renders = argv[1] if len(argv) > 1 else None
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for paso in PASOS:
        paso()
    if renders:
        paso_render(renders)
    paso_exportar(out_path)


if not globals().get("EN_VIVO"):
    main()
