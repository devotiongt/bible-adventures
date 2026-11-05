"""Noé según la hoja de giro de referencia (referencias/noe_giro.png), hecho en Blender.

Uso (sin abrir Blender):
    blender --background --factory-startup --python herramientas/blender/noe.py -- assets/personajes/noe.glb [carpeta_renders]
En vivo, con Blender abierto:
    python3 herramientas/blender/en_vivo.py noe paso_limpiar paso_referencias paso_cuerpo paso_cabeza paso_brazos paso_pies

Las medidas salen de la hoja de giro: la figura mide 478 px y se escala a 1,55 m (3,24 mm por px).
Los perfiles (ancho visto de frente y fondo visto de lado, altura por altura) están en las tablas
de abajo. Los colores son los de referencias/paleta.png.

Sin huesos: jerarquía de piezas con su pivote, para animarlas por código en Godot:
    Noe
    ├─ Cuerpo                túnica, sobretúnica, cinturón de cuerda (pivote en la cadera)
    │  ├─ Cabeza             cara, pelo, barba, cejas               (pivote en el cuello)
    │  │  ├─ OjoI / OjoD                                            (para parpadear)
    │  ├─ BrazoI / BrazoD    manga y mano                           (pivote en el hombro)
    ├─ PieI / PieD           pie, pierna y sandalia                 (pivote en el tobillo)
Ejes de Blender: Z arriba, Noé mira hacia -Y. El centro del cuerpo está en el origen.
"""

import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

ROOT = globals().get("PROJECT_ROOT", os.getcwd())
REF_SHEET = os.path.join(ROOT, "referencias/noe_giro.png")

PX = 1.55 / 478                  # Metros por píxel en la hoja de giro.
REF_BASE_Y = 532                 # Fila de la base de los pies en la imagen.
REF_FRONT_X = 165.5              # Centro de la figura de frente.
REF_SIDE_X = 403.5               # Centro del cuerpo en la figura de lado.

# Paleta (referencias/paleta.png) y tonos derivados.
COLORS = {
    "Piel": "FCD4B7",
    "Nariz": "EDA88A",
    "Rubor": "F2A898",
    "Canas": "EFEFEF",
    "Tunica": "DDD3C0",
    "Manga": "C8AE86",
    "Manto": "A55B2E",
    "Cinturon": "5E3918",
    "Sandalia": "3F2A1D",
    "Ojo": "3A2418",
    "Brillo": "FFFFFF",
}

# Perfiles medidos: (z, semiancho de frente, semifondo de lado, centro en Y).
TUNIC = [(0.175, 0.24, 0.19, 0.0), (0.24, 0.237, 0.188, 0.0), (0.32, 0.23, 0.18, 0.0), (0.5, 0.2, 0.16, 0.0),
         (0.7, 0.19, 0.155, 0.0), (0.9, 0.19, 0.155, 0.0), (1.02, 0.195, 0.152, 0.0), (1.09, 0.17, 0.135, 0.0),
         (1.14, 0.11, 0.1, 0.005), (1.17, 0.06, 0.06, 0.01)]
VEST = [(0.32, 0.253, 0.197, 0.0), (0.45, 0.232, 0.19, 0.0), (0.6, 0.212, 0.176, 0.0), (0.75, 0.206, 0.168, 0.0),
        (0.9, 0.206, 0.166, 0.0), (1.0, 0.222, 0.17, 0.0), (1.07, 0.228, 0.162, 0.0), (1.12, 0.17, 0.135, 0.005),
        (1.155, 0.105, 0.095, 0.01)]
BELT_Z = 0.70
HEAD_CENTER = Vector((0, -0.03, 1.335))
SKULL = Vector((0.15, 0.155, 0.19))    # Semiejes del cráneo.
NECK_Z = 1.14
SHOULDER = Vector((0.18, 0.0, 1.035))
HAND = Vector((0.36, -0.01, 0.6))


# --- Utilidades -----------------------------------------------------------------

def srgb(hex_color):
    return tuple(int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4))


def material(name):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes["Principled BSDF"]
        rgb = tuple(c ** 2.2 for c in srgb(COLORS[name]))
        bsdf.inputs["Base Color"].default_value = (*rgb, 1)
        bsdf.inputs["Roughness"].default_value = 0.3 if name in ("Ojo", "Brillo") else 0.65
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


def lathe(name, profile, mat_name, segments=48, wave=None, cap_top=True, cap_bottom=True, subdiv=1, skip=None):
    """Superficie de revolución elíptica. profile: [(z, semiancho x, semifondo y, centro y), ...].
    wave(a, t) multiplica el radio (pliegues); skip(a, t) quita esas caras (aberturas)."""
    bm = bmesh.new()
    rings = []
    for i, (z, rx, ry, cy) in enumerate(profile):
        t = i / (len(profile) - 1)
        ring = []
        for s in range(segments):
            a = math.tau * s / segments
            k = wave(a, t) if wave else 1.0
            ring.append(bm.verts.new((math.cos(a) * rx * k, cy + math.sin(a) * ry * k, z)))
        rings.append(ring)
    for i in range(len(rings) - 1):
        for s in range(segments):
            s2 = (s + 1) % segments
            a = math.tau * (s + 0.5) / segments
            if skip and skip(a, (i + 0.5) / (len(rings) - 1)):
                continue
            bm.faces.new((rings[i][s], rings[i][s2], rings[i + 1][s2], rings[i + 1][s]))
    if cap_bottom:
        bm.faces.new(list(reversed(rings[0])))
    if cap_top:
        bm.faces.new(rings[-1])
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bm.normal_update()
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return finish(obj, mat_name, subdiv)


def tube(name, points, radii, mat_name, segments=16, subdiv=1, twist=None):
    """Tubo que sigue una lista de puntos (cuerda, mangas, piernas)."""
    bm = bmesh.new()
    rings = []
    for i, p in enumerate(points):
        a = points[max(i - 1, 0)]
        b = points[min(i + 1, len(points) - 1)]
        t = (b - a).normalized()
        side = t.cross(Vector((0, 0, 1))) if abs(t.z) < 0.95 else t.cross(Vector((1, 0, 0)))
        side.normalize()
        up = side.cross(t).normalized()
        ring = []
        for s in range(segments):
            ang = math.tau * s / segments
            r = radii[i] * (twist(i, ang) if twist else 1.0)
            ring.append(bm.verts.new(p + (side * math.cos(ang) + up * math.sin(ang)) * r))
        rings.append(ring)
    for i in range(len(rings) - 1):
        for s in range(segments):
            s2 = (s + 1) % segments
            bm.faces.new((rings[i][s], rings[i][s2], rings[i + 1][s2], rings[i + 1][s]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])
    bm.normal_update()
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return finish(obj, mat_name, subdiv)


def solidify(obj, thickness, offset=-1):
    mod = obj.modifiers.new("Grosor", "SOLIDIFY")
    mod.thickness = thickness
    mod.offset = offset
    obj.modifiers.move(len(obj.modifiers) - 1, 0)


def on_head(x, z, out=0.0):
    """Punto de la cara (parte delantera del cráneo) a esa x, z, más 'out' hacia fuera."""
    d = Vector((x, 0, z)) - HEAD_CENTER
    k = 1.0 - (d.x / SKULL.x) ** 2 - (d.z / SKULL.z) ** 2
    y = -SKULL.y * math.sqrt(max(k, 0.0))
    p = HEAD_CENTER + Vector((d.x, y, d.z))
    normal = Vector((d.x / SKULL.x ** 2, y / SKULL.y ** 2, d.z / SKULL.z ** 2)).normalized()
    return p + normal * out


def pivot(name, location, parent=None):
    empty = bpy.data.objects.new(name, None)
    empty.empty_display_size = 0.05
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


def front_angle(a):
    """Distancia angular al frente (-Y), en radianes."""
    return abs(math.atan2(math.sin(a + math.pi / 2), math.cos(a + math.pi / 2)))


# --- Pasos ----------------------------------------------------------------------

def paso_limpiar():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.lights, bpy.data.cameras):
        for block in list(coll):
            if block.users == 0:
                coll.remove(block)
    root = pivot("Noe", (0, 0, 0))
    pivot("Cuerpo", (0, 0, BELT_Z), root)
    _view()


def paso_referencias():
    """La hoja de giro detrás del modelo, a escala: vista de frente y vista de lado."""
    img = bpy.data.images.load(REF_SHEET, check_existing=True)
    w, h = img.size
    for label, rot, loc_x, loc_y, ref_x in (
            ("RefFrente", (math.pi / 2, 0, 0), None, 0.9, REF_FRONT_X),
            ("RefLado", (math.pi / 2, 0, -math.pi / 2), 0.9, None, REF_SIDE_X)):
        ref = bpy.data.objects.new(label, None)
        ref.empty_display_type = "IMAGE"
        ref.data = img
        ref.empty_display_size = w * PX
        ref.empty_image_offset = (0, 0)
        ref.rotation_euler = rot
        # La imagen se coloca para que la figura de referencia quede justo detrás de Noé.
        offset_x = -ref_x * PX
        offset_z = -(h - REF_BASE_Y) * PX
        if label == "RefFrente":
            ref.location = (offset_x, loc_y, offset_z)
        else:
            ref.location = (loc_x, -offset_x, offset_z)
        ref.color[3] = 0.55
        ref.use_empty_image_alpha = True
        ref.show_empty_image_perspective = False
        bpy.context.scene.collection.objects.link(ref)


def paso_cuerpo():
    body = obj("Cuerpo")
    folds = lambda a, t: 1.0 + 0.035 * (1 - t) ** 3 * math.sin(11 * a + 0.4)
    tunic = lathe("Tunica", TUNIC, "Tunica", wave=folds)

    # Sobretúnica sin mangas, abierta por delante con los bordes rectos y sisas para los brazos.
    def openings(a, t):
        z = VEST[0][0] + (VEST[-1][0] - VEST[0][0]) * t
        front = front_angle(a) < (0.42 if z < 1.0 else 0.42 + (z - 1.0) * 4.0)
        side = abs(math.cos(a)) > 0.8 and 0.88 < z < 1.11 and abs(math.sin(a)) < 0.55
        return front or side

    vest = lathe("Sobretunica", VEST, "Manto", segments=64, cap_top=False, cap_bottom=False, skip=openings,
                 wave=lambda a, t: 1.0 + 0.025 * (1 - t) ** 2 * math.sin(7 * a + 1.0))
    solidify(vest, 0.022)

    # Cinturón de cuerda trenzada con nudo y dos cabos colgando.
    rope_pts = []
    for i in range(65):
        a = math.tau * i / 64
        rope_pts.append(Vector((math.cos(a) * 0.218, math.sin(a) * 0.182, BELT_Z + 0.004 * math.sin(a * 3))))
    rope = tube("Cuerda", rope_pts, [0.016] * len(rope_pts), "Cinturon", segments=10,
                twist=lambda i, ang: 1.0 + 0.25 * math.sin(ang * 2 + i * 1.7))
    knot = sphere("Nudo", (-0.03, -0.19, BELT_Z - 0.005), (0.032, 0.024, 0.03), "Cinturon")
    ends = []
    for j, (dx, length) in enumerate(((-0.045, 0.15), (-0.012, 0.13))):
        pts = [Vector((dx, -0.195 - 0.004 * k, BELT_Z - 0.02 - length * k / 6)) for k in range(7)]
        ends.append(tube(f"Cabo{j}", pts, [0.014] * 6 + [0.018], "Cinturon", segments=8,
                         twist=lambda i, ang: 1.0 + 0.2 * math.sin(ang * 2 + i * 2.1)))
    for part in [tunic, vest, rope, knot] + ends:
        attach(part, body)


def paso_cabeza():
    head = pivot("Cabeza", (0, -0.01, NECK_Z), obj("Cuerpo"))
    parts = [sphere("Cara", HEAD_CENTER, SKULL, "Piel", 32, 16)]
    for sx in (1, -1):
        side = "I" if sx > 0 else "D"
        parts.append(sphere(f"Oreja{side}", HEAD_CENTER + Vector((sx * 0.148, 0.005, -0.035)), (0.022, 0.03, 0.045),
                            "Piel"))
        parts.append(sphere(f"Rubor{side}", on_head(sx * 0.085, 1.275, -0.004), (0.035, 0.012, 0.022), "Rubor",
                            subdiv=0))
    parts.append(sphere("Nariz", on_head(0, 1.275, 0.03), (0.046, 0.042, 0.042), "Nariz"))

    # Pelo: casquete sobre el cráneo con la frente despejada.
    cap = sphere("Pelo", HEAD_CENTER + Vector((0, 0.008, 0.012)), SKULL + Vector((0.018, 0.02, 0.018)), "Canas",
                 40, 20)
    bm = bmesh.new()
    bm.from_mesh(cap.data)
    gone = [v for v in bm.verts if v.co.y < -0.035 and v.co.z > -0.07 - 0.25 * max(0.0, abs(v.co.x) - 0.08)]
    bmesh.ops.delete(bm, geom=gone, context="VERTS")
    bm.to_mesh(cap.data)
    bm.free()
    solidify(cap, 0.025)
    parts.append(cap)
    # Calva en la coronilla (se ve desde atrás).
    crown = HEAD_CENTER + Vector((0, 0.07, SKULL.z * 0.93))
    parts.append(sphere("Calva", crown, (0.06, 0.05, 0.03), "Piel"))
    # Melena: mechones largos que salen de la cabeza y caen por la espalda, terminados en punta.
    # Base de pelo bajo los mechones, para que se lean como una sola masa con surcos.
    base = lathe("MelenaBase", [(1.06, 0.15, 0.085, 0.09), (1.15, 0.172, 0.12, 0.065), (1.26, 0.18, 0.15, 0.035),
                                (1.36, 0.175, 0.168, 0.005), (1.45, 0.155, 0.158, -0.01)],
                 "Canas", segments=40, cap_top=False, cap_bottom=False,
                 skip=lambda a, t: front_angle(a) < 0.8 + 0.4 * t)
    base.location = (0, -0.03, 0)
    solidify(base, 0.03)
    parts.append(base)
    for i in range(21):
        u = i / 20
        ang = math.radians(-20 + 220 * u)      # De un lado a otro pasando por la nuca (+Y).
        side_k = abs(math.cos(ang))            # 1 en los lados, 0 en la nuca.
        top = 1.47 - 0.05 * side_k
        length = 0.42 + 0.06 * math.sin(i * 1.9) - 0.12 * side_k
        pts, radii = [], []
        for k in range(9):
            t = k / 8
            z = top - length * t
            # Pegado a la cabeza arriba; abajo cae un poco hacia atrás, por fuera de la sobretúnica.
            r = 0.175 + 0.02 * t + 0.015 * math.sin(t * math.pi)
            back = 0.05 * t * (1 - side_k)
            p = Vector((math.cos(ang) * r, HEAD_CENTER.y + 0.02 + math.sin(ang) * r * 0.95 + back, z))
            p.x += 0.012 * math.sin(t * 5 + i)  # Ondulado.
            pts.append(p)
            radii.append((0.05 - 0.036 * t ** 1.6) * (1.0 + 0.15 * math.sin(i * 2.7)))
        parts.append(tube(f"Mechon{i}", pts, radii, "Canas", segments=10))
    # Barba grande desde las mejillas hasta el pecho, terminada en punta.
    beard = sphere("Barba", (0, -0.15, 1.115), (0.165, 0.11, 0.2), "Canas", 40, 20)
    for v in beard.data.vertices:
        c = v.co
        if c.z < 0:
            k = -c.z / 0.2
            c.x *= 1.0 - 0.75 * k ** 1.3        # Se estrecha hasta la punta.
            c.y = c.y * (1.0 - 0.35 * k) - 0.06 * k ** 1.5
            c.z *= 1.0 + 0.05 * k
        # Mechones verticales.
        ang = math.atan2(c.y, c.x)
        r = Vector((c.x, c.y, 0))
        if r.length > 1e-4:
            bump = 0.006 * math.sin(ang * 14) * min(1.0, max(0.0, -c.z / 0.1 + 0.3))
            c.x += r.normalized().x * bump
            c.y += r.normalized().y * bump
    parts.append(beard)
    for sx in (1, -1):
        side = "I" if sx > 0 else "D"
        # Patillas: unen la melena con la barba por delante de las orejas.
        parts.append(sphere(f"Patilla{side}", HEAD_CENTER + Vector((sx * 0.128, -0.06, -0.09)),
                            (0.045, 0.06, 0.09), "Canas"))
        # Bigote ancho que cae hacia los lados.
        m = sphere(f"Bigote{side}", on_head(sx * 0.05, 1.225, 0.03), (0.06, 0.03, 0.026), "Canas")
        m.rotation_euler = (0, sx * -0.45, 0)
        parts.append(m)
        # Cejas pobladas, más altas por dentro.
        b = sphere(f"Ceja{side}", on_head(sx * 0.064, 1.365, 0.012), (0.052, 0.024, 0.026), "Canas")
        b.rotation_euler = (0, sx * 0.1, 0)
        parts.append(b)
    for part in parts:
        attach(part, head)
    # Ojos pequeños oscuros con brillo (piezas propias para parpadear).
    for sx, side in ((1, "I"), (-1, "D")):
        center = on_head(sx * 0.055, 1.312, 0.002)
        eye = pivot(f"Ojo{side}", center, head)
        iris = sphere(f"Iris{side}", center, (0.016, 0.009, 0.022), "Ojo", subdiv=0)
        glint = sphere(f"Brillo{side}", center + Vector((sx * -0.005, -0.008, 0.008)), (0.005, 0.003, 0.006),
                       "Brillo", 12, 6, subdiv=0)
        for part in (iris, glint):
            attach(part, eye)


def paso_brazos():
    body = obj("Cuerpo")
    for sx, side in ((1, "I"), (-1, "D")):
        shoulder = SHOULDER * Vector((sx, 1, 1))
        hand = HAND * Vector((sx, 1, 1))
        arm = pivot(f"Brazo{side}", shoulder, body)
        direction = (hand - shoulder).normalized()
        wrist = hand - direction * 0.04
        pts = [shoulder + (wrist - shoulder) * (k / 8) for k in range(9)]
        radii = [0.062, 0.06, 0.057, 0.055, 0.054, 0.053, 0.053, 0.054, 0.056]
        sleeve = tube(f"Manga{side}", pts, radii, "Manga", segments=20)
        shoulder_cap = sphere(f"Hombro{side}", shoulder + Vector((-sx * 0.01, 0, -0.005)), (0.06, 0.062, 0.058),
                              "Manga")
        # Mano grande y relajada: una sola pieza suave con el pulgar.
        palm = sphere(f"Mano{side}", hand + direction * 0.01, (0.04, 0.028, 0.068), "Piel")
        palm.rotation_euler = (0.1, -sx * 0.3, 0)
        thumb = sphere(f"Pulgar{side}", hand + Vector((-sx * 0.014, -0.026, 0.018)), (0.015, 0.015, 0.03), "Piel")
        thumb.rotation_euler = (0, sx * 0.4, 0)
        for part in (sleeve, shoulder_cap, palm, thumb):
            attach(part, arm)


def paso_pies():
    root = obj("Noe")
    for sx, side in ((1, "I"), (-1, "D")):
        ankle = Vector((sx * 0.11, 0.035, 0.065))
        foot = pivot(f"Pie{side}", ankle, root)
        leg = tube(f"Pie{side}Piel", [ankle + Vector((0, 0, 0.14)), ankle + Vector((0, 0, 0.02)),
                                      ankle + Vector((0, -0.04, -0.02)), ankle + Vector((0, -0.11, -0.03)),
                                      ankle + Vector((0, -0.15, -0.032))],
                   [0.05, 0.05, 0.05, 0.046, 0.032], "Piel", segments=16)
        sole = sphere(f"Suela{side}", ankle + Vector((0, -0.07, -0.05)), (0.068, 0.13, 0.022), "Sandalia")
        strap = lathe(f"Tira{side}", [(-0.016, 0.054, 0.036, 0.0), (0.016, 0.056, 0.038, 0.0)], "Sandalia",
                      segments=24, cap_top=False, cap_bottom=False)
        strap.location = ankle + Vector((0, -0.09, -0.04))
        strap.rotation_euler = (1.35, 0, 0)
        for part in (leg, sole, strap):
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
            r3d.view_location = Vector((0, 0, 0.8))
            r3d.view_distance = 3.2
            r3d.view_rotation = Euler((math.radians(82), 0, math.radians(-30))).to_quaternion()


def _lights(scene):
    world = bpy.data.worlds.get("Cielo") or bpy.data.worlds.new("Cielo")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (1, 1, 1, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.4
    scene.world = world
    key = bpy.data.objects.new("Sol", bpy.data.lights.new("Sol", "SUN"))
    key.data.energy = 2.0
    key.data.color = (1.0, 0.96, 0.9)
    key.data.angle = math.radians(25)
    key.rotation_euler = (math.radians(45), math.radians(8), math.radians(-30))
    scene.collection.objects.link(key)
    rim = bpy.data.objects.new("Contraluz", bpy.data.lights.new("Contraluz", "SUN"))
    rim.data.energy = 1.2
    rim.rotation_euler = (math.radians(60), 0, math.radians(160))
    scene.collection.objects.link(rim)
    return [key, rim]


def _engine(scene):
    for engine in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
        try:
            scene.render.engine = engine
            return
        except TypeError:
            continue


def paso_comparar(folder):
    """Renders ortográficos a la misma escala y encuadre que la hoja de giro (de frente y de lado),
    con fondo transparente, para superponerlos a la referencia."""
    scene = bpy.context.scene
    _engine(scene)
    scene.render.resolution_x = 1024
    scene.render.resolution_y = 572
    scene.render.film_transparent = True
    scene.view_settings.view_transform = "Standard"
    added = _lights(scene)
    for o in bpy.data.objects:
        if o.name.startswith("Ref"):
            o.hide_render = True
    cam = bpy.data.objects.new("CamaraOrto", bpy.data.cameras.new("CamaraOrto"))
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 1024 * PX
    scene.collection.objects.link(cam)
    scene.camera = cam
    added.append(cam)
    cz = (REF_BASE_Y - 286) * PX
    # Frente: cámara en -Y mirando +Y (la derecha de la imagen es +X).
    cam.location = ((512 - REF_FRONT_X) * PX, -5, cz)
    cam.rotation_euler = (math.pi / 2, 0, 0)
    scene.render.filepath = os.path.join(folder, "comparar_frente.png")
    bpy.ops.render.render(write_still=True)
    # Lado: cámara en -X mirando +X (la derecha de la imagen es -Y, hacia donde mira Noé).
    cam.location = (-5, -(512 - REF_SIDE_X) * PX, cz)
    cam.rotation_euler = (math.pi / 2, 0, -math.pi / 2)
    scene.render.filepath = os.path.join(folder, "comparar_lado.png")
    bpy.ops.render.render(write_still=True)
    for o in added:
        bpy.data.objects.remove(o)


def paso_render(folder):
    scene = bpy.context.scene
    _engine(scene)
    # Misma escala que la hoja de giro (para ponerlas una junto a otra).
    scene.render.resolution_x = 320
    scene.render.resolution_y = 572
    scene.render.film_transparent = True
    scene.view_settings.view_transform = "Standard"
    added = _lights(scene)
    for o in bpy.data.objects:
        if o.name.startswith("Ref"):
            o.hide_render = True
    cam = bpy.data.objects.new("CamaraOrto", bpy.data.cameras.new("CamaraOrto"))
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 572 * PX
    scene.collection.objects.link(cam)
    scene.camera = cam
    added.append(cam)
    cz = (REF_BASE_Y - 286) * PX
    views = (("frente", (0, -5, cz), (math.pi / 2, 0, 0)),
             ("lado", (-5, 0, cz), (math.pi / 2, 0, -math.pi / 2)),
             ("espalda", (0, 5, cz), (math.pi / 2, 0, math.pi)),
             ("tres_cuartos", (3.2, -3.8, cz), (math.pi / 2, 0, math.radians(40))))
    for label, loc, rot in views:
        cam.location = loc
        cam.rotation_euler = rot
        scene.render.filepath = os.path.join(folder, f"noe_{label}.png")
        bpy.ops.render.render(write_still=True)
    for o in added:
        bpy.data.objects.remove(o)


def paso_exportar(out_path):
    bpy.ops.object.select_all(action="DESELECT")
    for o in bpy.data.objects:
        if not o.name.startswith("Ref"):
            o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=out_path, export_format="GLB", use_selection=True, export_yup=True,
                              export_apply=True, export_animations=False)
    print(f"NOE OK -> {out_path}")


PASOS = [paso_limpiar, paso_referencias, paso_cuerpo, paso_cabeza, paso_brazos, paso_pies]


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out_path = argv[0] if argv else "noe.glb"
    renders = argv[1] if len(argv) > 1 else None
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for paso in PASOS:
        paso()
    if renders:
        paso_comparar(renders)
        paso_render(renders)
    paso_exportar(out_path)


if not globals().get("EN_VIVO"):
    main()
