"""Rig de Noé: adapta el esqueleto de la Universal Animation Library (Quaternius, CC0) a Noé,
le pone pesos automáticos y le pasa las animaciones.

Uso (en segundo plano, no toca ningún Blender abierto):
    blender --background --factory-startup --python herramientas/blender/rig_noe.py -- \\
        assets/personajes/rodin/noe_juego.glb assets/personajes/rodin/noe_rig.glb [carpeta_renders]

Entrada: el Noé exportado (cuerpo + ojos + cejas). Si se retoca en Blender, basta volver a exportarlo
y volver a ejecutar este script.

Otros personajes (la familia, los aldeanos): con un perfil que cambia las medidas y nombres de abajo,
    blender --background --factory-startup --python herramientas/blender/rig_noe.py -- \
        assets/personajes/familia/esposa.glb assets/personajes/familia/esposa_rig.glb --perfil herramientas/blender/perfiles/esposa.json

Cómo funciona:
1. El esqueleto (65 huesos, en T y de 1,83 m) se ajusta a las articulaciones de Noé, medidas en su
   malla: columna y cabeza por alturas, piernas por cadera-rodilla-tobillo, y cada brazo se gira desde
   la T hasta su dirección real (caído y algo abierto) y se escala a su largo.
2. El cuerpo recibe pesos automáticos (calor de huesos). La falda de la túnica mezcla pelvis y
   piernas, para que no se estire como un pantalón. Ojos y cejas van pegados al hueso de la cabeza.
3. Animaciones: cada hueso de Noé copia la orientación en el mundo del mismo hueso del esqueleto
   original mientras éste reproduce la animación, y se hornea. Así las animaciones funcionan aunque
   la postura de reposo de Noé (brazos caídos) no sea la T original.
"""

import math
import os
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

ROOT = os.getcwd()
UAL = os.path.join(ROOT, "assets/animaciones/UAL1_Standard.glb")
ANIMS = ["Idle", "Walk", "Jog_Fwd", "Sprint", "Interact", "Sword_Attack", "Fixing_Kneeling", "PickUp_Table", "Idle_Talking",
         "Trote"]
# Trote propio (trote_propio): el de la biblioteca es de atleta y deforma la túnica. Grados y metros; los
# ángulos van desde la postura de reposo (Idle).
TROTE_CUADROS = 18          # Un ciclo (dos pasos) a 30 cuadros/s.
TROTE = {"muslo": 32, "atras": 0.7, "rodilla": 38, "pie": 0.7, "brazo": 34, "codo": 80, "inclinacion": 10,
         "rebote": 0.07, "giro": 8}

# Articulaciones de Noé (metros; Z arriba, mira hacia -Y). Medidas en su malla con medir_noe.
SPINE_OLD = [0.0, 0.949, 1.072, 1.178, 1.311, 1.52, 1.6, 1.83]     # Suelo, pelvis…cabeza, coronilla.
SPINE_NEW = [0.0, 0.64, 0.74, 0.84, 0.95, 1.07, 1.14, 1.55]
BODY_XY = 0.85                     # Escala horizontal de la columna.
HIP = Vector((0.1, 0.0, 0.62))
KNEE = Vector((0.11, -0.01, 0.34))
ANKLE = Vector((0.12, -0.02, 0.075))
FOOT_SCALE = 0.72
SHOULDER = Vector((0.215, 0.03, 1.04))
HAND_TIP = Vector((0.381, -0.015, 0.538))
SKIRT = (0.15, 0.66)               # Alturas de la falda: pelvis y piernas se mezclan.
FALDA_BAJA = 0.06                  # Borde de abajo de la tela (lo de debajo es pie y sandalia).
# La túnica es una sola malla con las piernas dentro: va con dos huesos de falda (huesos_falda), no con
# las piernas. Su posición (y) y cuánto siguen al muslo más adelantado o más atrasado.
FALDA_HUESOS = {"falda_delante": -0.04, "falda_atras": 0.04}
FALDA_FONDO = 0.24                 # Ancho (de delante a atrás) en el que se mezclan los dos.
FALDA_SIGUE = 0.85
FALDA_MAX = 30                     # Lo más que se abre cada panel (grados): más, y la tela sale volando.
PIERNA_R = 0.09                    # Bajo la ropa, lo que está a menos de esto del hueso es pierna.
PIE_Z = 0.08                       # Por debajo, todo es pie y sandalia (va entero con la pierna).
CUERPO = "NoeLow"                  # Nombre (inicio) de la malla del cuerpo en el .glb.
PREFIJO = "Noe_"                   # Nombre de las animaciones en el juego.
ZONAS_ESCALA = 1.0                 # Alturas de las zonas rígidas de pesos, respecto a Noé.
CUERDA = True                      # Soga del cinto pintada en la textura (rígida con la pelvis).
ANCHO_CUERPO = 0.25                # Medio ancho de la ropa del tronco que no sigue a los brazos.


def _perfil():
    """Medidas y nombres de otro personaje (herramientas/blender/perfiles/<nombre>.json)."""
    argv = sys.argv[sys.argv.index("--") + 1:]
    if "--perfil" not in argv:
        return
    import json
    data = json.load(open(argv[argv.index("--perfil") + 1]))
    vec = {"HIP", "KNEE", "ANKLE", "SHOULDER", "HAND_TIP"}
    for k, v in data.items():
        if k.startswith("_"):
            continue
        globals()[k] = Vector(v) if k in vec else (tuple(v) if k == "SKIRT" else v)


_perfil()


def _interp(z, old, new):
    return float(np.interp(z, old, new))


def _spine_point(p):
    return Vector((p.x * BODY_XY, p.y * BODY_XY, _interp(p.z, SPINE_OLD, SPINE_NEW)))


def _leg_point(p, side, o_hip, o_knee, o_ankle):
    hip, knee, ankle = (Vector((v.x * side, v.y, v.z)) for v in (HIP, KNEE, ANKLE))
    if p.z <= o_ankle.z + 1e-4:
        return ankle + (p - o_ankle) * FOOT_SCALE
    if p.z >= o_knee.z:
        t = (o_hip.z - p.z) / (o_hip.z - o_knee.z)
        return hip.lerp(knee, t) + Vector((0, (p.y - o_hip.y) * 0.8, 0))
    t = (o_knee.z - p.z) / (o_knee.z - o_ankle.z)
    return knee.lerp(ankle, t) + Vector((0, (p.y - o_knee.y) * 0.8, 0))


def _chain(bone, names):
    """¿El hueso pertenece a una cadena que empieza en alguno de esos nombres?"""
    b = bone
    while b is not None:
        if b.name in names:
            return b.name
        b = b.parent
    return None


def ajustar_esqueleto(arm):
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.data.edit_bones
    old = {b.name: (b.head.copy(), b.tail.copy(), b.matrix.copy(), b.length, b.roll) for b in eb}
    o_sh = {s: old[f"upperarm_{s}"][0] for s in "lr"}
    o_hand_tip = {s: old[f"middle_04_leaf_{s}"][0] if f"middle_04_leaf_{s}" in old else old[f"hand_{s}"][0]
                  for s in "lr"}
    for b in eb:
        h, t, m, length, roll = old[b.name]
        arm_side = _chain(b, {"clavicle_l": 1, "clavicle_r": 1})
        leg_side = _chain(b, {"thigh_l": 1, "thigh_r": 1})
        if arm_side and b.name.startswith("clavicle"):
            s = arm_side[-1]
            sign = 1 if s == "l" else -1
            b.head = _spine_point(h)
            b.tail = Vector((SHOULDER.x * sign, SHOULDER.y, SHOULDER.z))
            b.roll = roll
        elif arm_side:
            s = arm_side[-1]
            sign = 1 if s == "l" else -1
            n_sh = Vector((SHOULDER.x * sign, SHOULDER.y, SHOULDER.z))
            n_tip = Vector((HAND_TIP.x * sign, HAND_TIP.y, HAND_TIP.z))
            d_old = (o_hand_tip[s] - o_sh[s])
            d_new = (n_tip - n_sh)
            rot = d_old.normalized().rotation_difference(d_new.normalized()).to_matrix().to_4x4()
            scale = d_new.length / d_old.length
            new_head = n_sh + (rot @ (h - o_sh[s]).to_4d()).to_3d() * scale
            mat = Matrix.Translation(new_head) @ rot @ Matrix.Translation(-h) @ m
            b.matrix = mat
            b.length = length * scale
        elif leg_side:
            s = leg_side[-1]
            sign = 1 if s == "l" else -1
            o_hip, o_knee, o_ankle = old[f"thigh_{s}"][0], old[f"calf_{s}"][0], old[f"foot_{s}"][0]
            b.head = _leg_point(h, sign, o_hip, o_knee, o_ankle)
            b.tail = _leg_point(t, sign, o_hip, o_knee, o_ankle)
            b.roll = roll
        else:
            b.head = _spine_point(h)
            b.tail = _spine_point(t)
            b.roll = roll
    bpy.ops.object.mode_set(mode="OBJECT")


def huesos_falda(arm):
    """Dos huesos que cuelgan de la pelvis por dentro de la falda: el de delante se adelanta con la pierna
    que va delante y el de atrás se va atrás con la que va atrás (animaciones). Así la túnica se abre como
    una campana al dar un paso largo, sin estirarse entre las piernas."""
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.data.edit_bones
    for name, y in FALDA_HUESOS.items():
        b = eb.new(name)
        b.head = Vector((0.0, y, SKIRT[1]))
        b.tail = Vector((0.0, y, FALDA_BAJA))
        b.parent = eb["pelvis"]
        b.use_deform = True
    bpy.ops.object.mode_set(mode="OBJECT")
    for name in FALDA_HUESOS:
        arm.pose.bones[name].rotation_mode = "QUATERNION"


def pesos(body, arm, extras):
    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    # Vértices sin peso (si el calor de huesos no llegó): al hueso más cercano.
    names = [b.name for b in arm.data.bones]
    groups = {g.index: g.name for g in body.vertex_groups}
    heads = {b.name: (arm.matrix_world @ b.head_local, arm.matrix_world @ b.tail_local) for b in arm.data.bones}
    unweighted = 0
    for v in body.data.vertices:
        if sum(g.weight for g in v.groups) < 1e-3:
            unweighted += 1
            p = body.matrix_world @ v.co
            best = min(names, key=lambda n: _seg_dist(p, *heads[n]))
            vg = body.vertex_groups.get(best) or body.vertex_groups.new(name=best)
            vg.add([v.index], 1.0, "REPLACE")
    print("vertices sin peso corregidos", unweighted)
    # Suavizar pesos entre vértices vecinos: las rasgaduras salen donde dos vecinos siguen a
    # huesos muy distintos.
    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.mode_set(mode="WEIGHT_PAINT")
    bpy.ops.object.vertex_group_smooth(group_select_mode="ALL", factor=0.5, repeat=2, expand=0.0)
    bpy.ops.object.vertex_group_normalize_all(lock_active=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    # Zonas que solo pueden seguir a ciertos huesos (si no, la barba sigue a los brazos y la ropa a
    # las manos, y se rasgan al moverse).
    spine = ["pelvis", "spine_01", "spine_02", "spine_03"]
    zonas = [
        # (condición, huesos permitidos, hueso si no queda ninguno)
        # Cabeza, barba y pelo: rígidos con la cabeza (si se reparten, la barba se rasga al girar).
        (lambda p: abs(p.x) < 0.2 and p.z > 1.0 * ZONAS_ESCALA, ["Head"], "Head"),
        (lambda p: abs(p.x) < 0.17 and p.z > 0.92 * ZONAS_ESCALA, ["spine_03", "neck_01", "Head"], "Head"),
        # Las piernas solo mueven la falda: del pecho para arriba, la ropa va con la columna (si no, el
        # calor de huesos le daba la espalda al muslo y al andar se atravesaba).
        (lambda p: abs(p.x) < ANCHO_CUERPO and SKIRT[1] < p.z <= 0.92 * ZONAS_ESCALA, spine, "spine_02"),
        (lambda p: abs(p.x) < ANCHO_CUERPO and 0.12 < p.z <= SKIRT[1],
         spine + [n for n in names if n.startswith(("thigh", "calf"))], "pelvis"),
    ]
    limited = 0
    for v in body.data.vertices:
        p = body.matrix_world @ v.co
        for cond, allowed, fallback in zonas:
            if not cond(p):
                continue
            gnames = {g.index: g.name for g in body.vertex_groups}
            # Primero se apuntan los grupos y luego se quitan: quitar mientras se recorre v.groups
            # se salta elementos (la lista se corre) y dejaba ropa siguiendo a los dedos.
            drop = [g.group for g in v.groups if gnames[g.group] not in allowed]
            for gi in drop:
                body.vertex_groups[gi].remove([v.index])
            total = sum(g.weight for g in v.groups)
            if total < 1e-4:
                vg = body.vertex_groups.get(fallback) or body.vertex_groups.new(name=fallback)
                vg.add([v.index], 1.0, "REPLACE")
            else:
                for g in v.groups:
                    g.weight /= total
            limited += 1
            break
    print("vertices con huesos limitados", limited)
    # Falda: de la cintura al borde, la tela pasa poco a poco de la pelvis a los huesos de falda; lo de
    # delante al de delante y lo de atrás al de atrás (mezclados por los costados). Las piernas no la tocan:
    # si cada pierna jala su lado, la tela de en medio se estira en picos.
    pelvis = body.vertex_groups.get("pelvis") or body.vertex_groups.new(name="pelvis")
    front_g = body.vertex_groups.get("falda_delante") or body.vertex_groups.new(name="falda_delante")
    back_g = body.vertex_groups.get("falda_atras") or body.vertex_groups.new(name="falda_atras")
    moved = 0
    for v in body.data.vertices:
        p = body.matrix_world @ v.co
        if not (FALDA_BAJA < p.z < SKIRT[1]) or abs(p.x) > 0.3:
            continue
        gn = {g.index: g.name for g in body.vertex_groups}
        if sum(g.weight for g in v.groups if gn[g.group].startswith(("upperarm", "lowerarm", "hand", "thumb",
               "index", "middle", "ring", "pinky"))) > 0.2:
            continue                            # Manga o mano que cuelga a la altura de la falda.
        w = min(1.0, (SKIRT[1] - p.z) / (SKIRT[1] - SKIRT[0])) ** 1.3
        front = min(1.0, max(0.0, 0.5 - p.y / FALDA_FONDO))
        for gi in [g.group for g in v.groups]:
            body.vertex_groups[gi].remove([v.index])
        pelvis.add([v.index], 1.0 - w, "REPLACE")
        if w * front > 1e-4:
            front_g.add([v.index], w * front, "REPLACE")
        if w * (1 - front) > 1e-4:
            back_g.add([v.index], w * (1 - front), "REPLACE")
        moved += 1
    print("vertices de la falda con sus huesos", moved)
    # La pierna que asoma bajo la ropa (espinilla, tobillo, pie) va entera con la pierna: si una parte se
    # quedaba con la túnica rígida, al echar el pie atrás la piel se estiraba como un calcetín. Por posición:
    # junto al hueso de la pantorrilla y por debajo del borde; hacia el borde se mezcla con la ropa.
    leg_bones = ("calf", "foot", "ball")
    gnames = {g.index: g.name for g in body.vertex_groups}
    calf = {s: (arm.matrix_world @ arm.data.bones[f"calf_{s}"].head_local,
                arm.matrix_world @ arm.data.bones[f"foot_{s}"].head_local) for s in "lr"}
    count = 0
    for v in body.data.vertices:
        p = body.matrix_world @ v.co
        if p.z >= SKIRT[0]:
            continue
        side = "l" if p.x > 0 else "r"
        if _seg_dist(p, *calf[side]) > PIERNA_R and p.z > PIE_Z:
            continue
        blend = min(1.0, (SKIRT[0] - p.z) / max(SKIRT[0] - PIE_Z, 1e-4))
        leg = {gnames[g.group]: g.weight for g in v.groups if g.weight > 1e-4
               and gnames[g.group].startswith(leg_bones) and gnames[g.group].endswith("_" + side)}
        if not leg:
            leg = {f"calf_{side}": 1.0}
        total = sum(leg.values())
        for g in v.groups:
            g.weight *= 1 - blend
        for name, w in leg.items():
            (body.vertex_groups.get(name) or body.vertex_groups.new(name=name)).add([v.index], w / total * blend, "ADD")
        count += 1
    print("vertices de la pierna bajo la ropa", count)
    # Cinto: la soga solo está pintada sobre la túnica, así que heredaba la mezcla de la falda y se
    # torcía con cada pierna. Va rígida con la pelvis; sus vecinos, a medias, para que no se rasgue.
    rope = _cuerda(body) if CUERDA else set()
    ring = set()
    for e in body.data.edges:
        a, b = e.vertices
        if (a in rope) != (b in rope):
            ring.add(b if a in rope else a)
    for idx, share in [(i, 1.0) for i in rope] + [(i, 0.5) for i in ring]:
        v = body.data.vertices[idx]
        for g in v.groups:
            body.vertex_groups[g.group].add([idx], g.weight * (1 - share), "REPLACE")
        pelvis.add([idx], share, "ADD")
    print("vertices del cinto rigidos", len(rope), "borde", len(ring))
    # Ojos, brillos y cejas: pegados a la cabeza.
    for o in extras:
        mw = o.matrix_world.copy()
        o.parent = arm
        o.parent_type = "BONE"
        o.parent_bone = "Head"
        o.matrix_world = mw


def _cuerda(body):
    """Vértices de la soga del cinto: triángulos con su color en la textura, a la altura de la cintura."""
    me = body.data
    img = next(n.image for n in me.materials[0].node_tree.nodes if n.type == "TEX_IMAGE" and n.image
               and "color" in n.image.name.lower())
    w, h = img.size
    px = np.array(img.pixels[:], np.float32).reshape(h, w, 4)[..., :3]
    target = np.array([0x5E, 0x39, 0x18]) / 255.0          # "cuerda" en la paleta de textura.py.
    uv = me.uv_layers.active.data
    rope = set()
    for poly in me.polygons:
        z = (body.matrix_world @ poly.center).z
        if not 0.4 < z < 0.85:
            continue
        cols = [px[int(np.clip(uv[li].uv[1], 0, 0.999) * h), int(np.clip(uv[li].uv[0], 0, 0.999) * w)]
                for li in poly.loop_indices]
        if np.abs(np.mean(cols, 0) - target).sum() < 0.25:
            rope.update(poly.vertices)
    return rope


def _seg_dist(p, a, b):
    ab = b - a
    t = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.length_squared, 1e-12)))
    return (p - (a + ab * t)).length


def trote_propio(src):
    """Trote para gente con túnica, hecho en el esqueleto original (luego se copia como las demás): pasos
    cortos desde la cadera, la rodilla solo se dobla al llevar el pie adelante (no se va atrás y no levanta
    la túnica), rebote suave, cadera y hombros que giran al compás y brazos que se mecen."""
    scene = bpy.context.scene
    idle = bpy.data.actions.get("Idle") or bpy.data.actions.get("Idle_Loop")
    src.animation_data.action = idle
    scene.frame_set(int(idle.frame_range[0]))
    # Postura de partida: piernas y columna rectas (reposo); los brazos, caídos como en Idle (el reposo es en
    # T). El Idle entero no sirve: tiene un pie más atrás que el otro y el trote salía cojo.
    base = {pb.name: (pb.matrix_basis.copy() if _chain(pb.bone, {"clavicle_l": 1, "clavicle_r": 1})
                      else Matrix.Identity(4)) for pb in src.pose.bones}
    act = bpy.data.actions.new("Trote")
    src.animation_data.action = act
    to_arm = src.matrix_world.inverted().to_3x3()
    x_axis = (to_arm @ Vector((1, 0, 0))).normalized()
    z_axis = (to_arm @ Vector((0, 0, 1))).normalized()

    def turn(name, deg, axis):
        # Gira el hueso en el espacio del mundo alrededor de su cabeza, sobre lo que ya tenga (y sus padres).
        bpy.context.view_layer.update()
        pb = src.pose.bones[name]
        m = pb.matrix.copy()
        h = m.translation.copy()
        pb.matrix = Matrix.Translation(h) @ Matrix.Rotation(math.radians(deg), 4, axis) @ Matrix.Translation(-h) @ m

    t = TROTE
    for f in range(TROTE_CUADROS + 1):
        ph = 2 * math.pi * f / TROTE_CUADROS
        s, c = math.sin(ph), math.cos(ph)
        scene.frame_set(f)
        for pb in src.pose.bones:
            pb.matrix_basis = base[pb.name]
        bpy.context.view_layer.update()
        pel = src.pose.bones["pelvis"]
        m = pel.matrix.copy()
        # Correr: arriba en el vuelo (piernas abiertas) y abajo al apoyar (al cruzar los pies).
        m.translation += to_arm @ Vector((0, 0, -t["rebote"] * math.cos(2 * ph)))
        pel.matrix = m
        turn("pelvis", t["giro"] * s, z_axis)
        turn("spine_01", t["inclinacion"], x_axis)
        turn("spine_02", -t["giro"] * 1.6 * s, z_axis)                  # Los hombros, al revés que la cadera.
        turn("Head", -t["inclinacion"] * 0.7, x_axis)
        # Ángulos sobre X: los huesos que cuelgan van adelante con ángulo negativo (Noé mira hacia -Y).
        for side, sign in (("l", 1), ("r", -1)):
            swing = -t["muslo"] * s * sign
            if swing > 0:                                                # Hacia atrás, menos.
                swing *= t["atras"]
            forward = max(0.0, c * sign)                                 # La pierna viene hacia delante.
            knee = 8 + t["rodilla"] * forward ** 1.5
            turn(f"thigh_{side}", swing, x_axis)
            turn(f"calf_{side}", knee, x_axis)
            turn(f"foot_{side}", -(swing + knee) * t["pie"], x_axis)
            turn(f"upperarm_{side}", t["brazo"] * s * sign, x_axis)       # Brazo contrario a la pierna.
            turn(f"lowerarm_{side}", -t["codo"], x_axis)
        bpy.context.view_layer.update()
        for pb in src.pose.bones:
            pb.keyframe_insert("rotation_quaternion" if pb.rotation_mode == "QUATERNION" else "rotation_euler", frame=f)
            if pb.name == "pelvis":
                pb.keyframe_insert("location", frame=f)
    act.use_fake_user = True
    print("trote propio", TROTE_CUADROS, "cuadros")


def animaciones(arm, src):
    scene = bpy.context.scene
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = arm
    for pb in arm.pose.bones:
        if pb.name in src.pose.bones and pb.name != "root":
            c = pb.constraints.new("COPY_ROTATION")
            c.target = src
            c.subtarget = pb.name
            c.target_space = "WORLD"
            c.owner_space = "WORLD"
    o_pelvis = src.matrix_world @ src.data.bones["pelvis"].head_local
    n_pelvis = arm.matrix_world @ arm.data.bones["pelvis"].head_local
    leg_ratio = (HIP.z - ANKLE.z) / (0.971 - 0.0865)
    baked = []
    for name in ANIMS:
        action = bpy.data.actions.get(name) or bpy.data.actions.get(name + "_Loop")
        if action is None:
            print("falta la animacion", name)
            continue
        src.animation_data.action = action
        f0, f1 = (int(round(x)) for x in action.frame_range)
        scene.frame_start, scene.frame_end = f0, f1
        bpy.ops.object.mode_set(mode="POSE")
        bpy.ops.pose.select_all(action="SELECT")
        bpy.ops.nla.bake(frame_start=f0, frame_end=f1, only_selected=False, visual_keying=True,
                         clear_constraints=False, use_current_action=False, bake_types={"POSE"})
        new = arm.animation_data.action
        new.name = PREFIJO + name
        # La pelvis también se mueve (rebote al andar, agacharse): desplazamiento del original,
        # escalado al largo de pierna de Noé. Sin el avance horizontal (lo pone el juego).
        pb = arm.pose.bones["pelvis"]
        stance = {"l": 0.0, "r": 0.0}
        for f in range(f0, f1 + 1):
            scene.frame_set(f)
            for side in "lr":
                stance[side] += _thigh_angle(arm, side) / (f1 - f0 + 1)
        for f in range(f0, f1 + 1):
            scene.frame_set(f)
            sp = src.matrix_world @ src.pose.bones["pelvis"].head
            delta = (sp - o_pelvis) * leg_ratio
            delta.y = 0.0
            mat = pb.matrix.copy()
            mat.translation = n_pelvis + delta
            pb.matrix = mat
            pb.keyframe_insert("location", frame=f)
            _falda(arm, f, stance)
        new.use_fake_user = True
        track = arm.animation_data.nla_tracks.new()
        track.name = new.name
        track.strips.new(new.name, f0, new)
        arm.animation_data.action = None
        baked.append(new.name)
        bpy.ops.object.mode_set(mode="OBJECT")
    for pb in arm.pose.bones:
        for c in list(pb.constraints):
            pb.constraints.remove(c)
    print("animaciones", baked)
    return baked


def _thigh_angle(arm, side, rest=False):
    """Ángulo hacia delante (negativo) o atrás (positivo) del muslo, visto de lado."""
    if rest:
        b = arm.data.bones[f"thigh_{side}"]
        d = b.tail_local - b.head_local
    else:
        pb = arm.pose.bones[f"thigh_{side}"]
        d = pb.tail - pb.head
    d = arm.matrix_world.to_3x3() @ d
    return math.atan2(d.y, -d.z)


def _falda(arm, frame, stance):
    """Pone los huesos de falda en este cuadro: el de delante sigue al muslo más adelantado y el de atrás
    al más atrasado, contados desde la postura media de la animación (stance): en reposo, los muslos algo
    adelantados no empujan la tela; si los dos van igual, cuelgan rectos."""
    bpy.context.view_layer.update()
    swing = [_thigh_angle(arm, s) - stance[s] for s in "lr"]
    lim = math.radians(FALDA_MAX)
    angles = {"falda_delante": max(min(min(swing), 0.0) * FALDA_SIGUE, -lim),
              "falda_atras": min(max(max(swing), 0.0) * FALDA_SIGUE, lim)}
    pel = arm.pose.bones["pelvis"]
    carry = pel.matrix @ arm.data.bones["pelvis"].matrix_local.inverted()
    x_axis = (arm.matrix_world.inverted().to_3x3() @ Vector((1, 0, 0))).normalized()
    for name, ang in angles.items():
        pb = arm.pose.bones[name]
        m = carry @ arm.data.bones[name].matrix_local
        h = m.translation.copy()
        pb.matrix = Matrix.Translation(h) @ Matrix.Rotation(ang, 4, x_axis) @ Matrix.Translation(-h) @ m
        bpy.context.view_layer.update()
        pb.keyframe_insert("rotation_quaternion", frame=frame)


def velocidad_natural(arm, action_name):
    """Velocidad (m/s) a la que hay que mover a Noé para que los pies no patinen."""
    scene = bpy.context.scene
    act = bpy.data.actions[action_name]
    arm.animation_data.action = act
    f0, f1 = (int(round(x)) for x in act.frame_range)
    ys = []
    for f in range(f0, f1 + 1):
        scene.frame_set(f)
        ball = arm.matrix_world @ arm.pose.bones["ball_l"].head
        pel = arm.matrix_world @ arm.pose.bones["pelvis"].head
        ys.append(ball.y - pel.y)
    arm.animation_data.action = None
    stride = max(ys) - min(ys)
    secs = (f1 - f0) / scene.render.fps
    return stride / (secs * 0.6)


def render(folder, arm):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x, scene.render.resolution_y = 500, 700
    w = bpy.data.worlds.new("w")
    w.color = (0.45, 0.45, 0.45)
    scene.world = w
    sun = bpy.data.objects.new("sol", bpy.data.lights.new("sol", "SUN"))
    sun.data.energy = 3
    sun.rotation_euler = (0.8, 0.2, -0.5)
    scene.collection.objects.link(sun)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 1.9
    cam.location = (2.6, -3.6, 0.85)
    cam.rotation_euler = (math.radians(90), 0, math.radians(36))
    scene.collection.objects.link(cam)
    scene.camera = cam
    shots = [("reposo", None, 0)] + [(a, PREFIJO + a, f) for a, f in (("Walk", 8), ("Jog_Fwd", 6),
                                                                   ("Sword_Attack", 12), ("Interact", 15))]
    for label, act, frame in shots:
        for tr in arm.animation_data.nla_tracks:
            tr.mute = True
        arm.animation_data.action = bpy.data.actions.get(act) if act else None
        if act is None:
            for pb in arm.pose.bones:
                pb.matrix_basis = Matrix.Identity(4)
        scene.frame_set(frame)
        scene.render.filepath = os.path.join(folder, f"rig_{label}.png")
        bpy.ops.render.render(write_still=True)
    arm.animation_data.action = None
    for tr in arm.animation_data.nla_tracks:
        tr.mute = False


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    if "--perfil" in argv:
        i = argv.index("--perfil")
        argv = argv[:i] + argv[i + 2:]
    src_path, out_path = argv[0], argv[1]
    renders = argv[2] if len(argv) > 2 else None
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.render.fps = 30

    bpy.ops.import_scene.gltf(filepath=src_path)
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    for o in meshes:
        mw = o.matrix_world.copy()
        o.parent = None
        o.matrix_world = mw
    for o in [o for o in bpy.data.objects if o.type == "EMPTY"]:
        bpy.data.objects.remove(o)
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    body = next(o for o in meshes if o.name.startswith(CUERPO))
    # glTF separa los vértices en las costuras de la textura; se vuelven a unir (las UV se conservan)
    # para que las piezas reciban los mismos pesos y no se abran al moverse.
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(body.data)
    n0 = len(bm.verts)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    print("vertices unidos en costuras", n0 - len(bm.verts))
    bm.to_mesh(body.data)
    bm.free()
    body.name = PREFIJO.rstrip("_")
    extras = [o for o in meshes if o is not body]

    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=UAL)
    new_objs = [o for o in bpy.data.objects if o not in before]
    src = next(o for o in new_objs if o.type == "ARMATURE")
    for o in new_objs:
        if o.type == "MESH":
            bpy.data.objects.remove(o)
    src.name = "UAL"
    if src.animation_data is None:
        src.animation_data_create()
    # El importador deja las animaciones en pistas NLA; se quitan para poder elegir cada acción.
    for tr in list(src.animation_data.nla_tracks):
        src.animation_data.nla_tracks.remove(tr)

    trote_propio(src)
    arm = src.copy()
    arm.data = src.data.copy()
    arm.animation_data_clear()
    arm.name = "Esqueleto"
    arm.data.name = "Esqueleto"
    bpy.context.scene.collection.objects.link(arm)
    arm.animation_data_create()

    ajustar_esqueleto(arm)
    huesos_falda(arm)
    pesos(body, arm, extras)
    baked = animaciones(arm, src)
    for name in (PREFIJO + "Walk", PREFIJO + "Jog_Fwd", PREFIJO + "Sprint", PREFIJO + "Trote"):
        if name in baked:
            print("VELOCIDAD", name, round(velocidad_natural(arm, name), 3))
    if renders:
        os.makedirs(renders, exist_ok=True)
        render(renders, arm)

    # Exportar solo Noé (esqueleto + mallas), sin el esqueleto original.
    for a in [a for a in bpy.data.actions if not a.name.startswith(PREFIJO)]:
        bpy.data.actions.remove(a)
    bpy.data.objects.remove(src)
    bpy.ops.object.select_all(action="DESELECT")
    for o in [arm, body] + extras:
        o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=out_path, export_format="GLB", use_selection=True, export_yup=True,
                              export_apply=False, export_skins=True, export_animations=True,
                              export_animation_mode="NLA_TRACKS", export_force_sampling=True,
                              export_anim_single_armature=True)
    print("RIG OK ->", out_path)


main()
