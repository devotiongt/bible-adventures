"""Noah's rig: fits the skeleton of the Universal Animation Library (Quaternius, CC0) to Noah,
gives it automatic weights and passes the animations over.

Usage (in the background, it doesn't touch any open Blender):
    blender --background --factory-startup --python tools/blender/rig_noah.py -- \\
        assets/characters/rodin/noah_game.glb assets/characters/rodin/noah_rig.glb [renders_folder]

Input: the exported Noah (body + eyes + brows). If he is retouched in Blender, just export him again
and run this script again.

Other characters (the family, the villagers): with a profile that changes the measurements and names below,
    blender --background --factory-startup --python tools/blender/rig_noah.py -- \
        assets/characters/family/wife.glb assets/characters/family/wife_rig.glb --profile tools/blender/profiles/wife.json

How it works:
1. The skeleton (65 bones, in T pose and 1.83 m tall) is fitted to Noah's joints, measured on his
   mesh: spine and head by heights, legs by hip-knee-ankle, and each arm is turned from the T
   to its real direction (hanging and a bit open) and scaled to its length.
2. The body gets automatic weights (bone heat). The tunic's skirt blends pelvis and
   legs, so it doesn't stretch like trousers. Eyes and brows are stuck to the head bone.
3. Animations: each bone of Noah copies the world orientation of the same bone of the original
   skeleton while it plays the animation, and it gets baked. That way the animations work even though
   Noah's rest pose (arms down) is not the original T.
"""

import math
import os
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

ROOT = os.getcwd()
UAL = os.path.join(ROOT, "assets/animations/UAL1_Standard.glb")
ANIMS = ["Idle", "Walk", "Jog_Fwd", "Sprint", "Interact", "Sword_Attack", "Fixing_Kneeling", "PickUp_Table", "Idle_Talking",
         "Trot"]
# Our own trot (own_trot): the library's one is an athlete's and deforms the tunic. Degrees and meters; the
# angles are measured from the rest pose (Idle).
TROT_FRAMES = 18            # One cycle (two steps) at 30 frames/s.
TROT = {"thigh": 32, "back": 0.7, "knee": 38, "foot": 0.7, "arm": 34, "elbow": 80, "lean": 10,
        "bounce": 0.07, "twist": 8}

# Noah's joints (meters; Z up, facing -Y). Measured on his mesh with measure_noah.
SPINE_OLD = [0.0, 0.949, 1.072, 1.178, 1.311, 1.52, 1.6, 1.83]     # Ground, pelvis…head, crown.
SPINE_NEW = [0.0, 0.64, 0.74, 0.84, 0.95, 1.07, 1.14, 1.55]
BODY_XY = 0.85                     # Horizontal scale of the spine.
HIP = Vector((0.1, 0.0, 0.62))
KNEE = Vector((0.11, -0.01, 0.34))
ANKLE = Vector((0.12, -0.02, 0.075))
FOOT_SCALE = 0.72
SHOULDER = Vector((0.215, 0.03, 1.04))
HAND_TIP = Vector((0.381, -0.015, 0.538))
SKIRT = (0.15, 0.66)               # Skirt heights: pelvis and legs are blended.
SKIRT_LOW = 0.06                   # Bottom edge of the cloth (what's below is foot and sandal).
# The tunic is a single mesh with the legs inside: it goes with two skirt bones (skirt_bones), not with
# the legs. Their position (y) and how much they follow the most forward or most backward thigh.
SKIRT_BONES = {"skirt_front": -0.04, "skirt_back": 0.04}
SKIRT_DEPTH = 0.24                 # Width (front to back) over which the two are blended.
SKIRT_FOLLOW = 0.85
SKIRT_MAX = 30                     # The most each panel opens (degrees): more, and the cloth flies off.
LEG_R = 0.09                       # Under the clothes, whatever is closer than this to the bone is leg.
FOOT_Z = 0.08                      # Below this, everything is foot and sandal (goes whole with the leg).
BODY = "NoahLow"                   # Name (start) of the body mesh in the .glb.
PREFIX = "Noah_"                   # Name of the animations in the game.
ZONE_SCALE = 1.0                   # Heights of the rigid weight zones, relative to Noah.
ROPE = True                        # Belt rope painted in the texture (rigid with the pelvis).
BODY_WIDTH = 0.25                  # Half width of the torso clothes that don't follow the arms.


def _profile():
    """Measurements and names of another character (tools/blender/profiles/<name>.json)."""
    argv = sys.argv[sys.argv.index("--") + 1:]
    if "--profile" not in argv:
        return
    import json
    data = json.load(open(argv[argv.index("--profile") + 1]))
    vec = {"HIP", "KNEE", "ANKLE", "SHOULDER", "HAND_TIP"}
    for k, v in data.items():
        if k.startswith("_"):
            continue
        globals()[k] = Vector(v) if k in vec else (tuple(v) if k == "SKIRT" else v)


_profile()


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
    """Does the bone belong to a chain that starts at one of those names?"""
    b = bone
    while b is not None:
        if b.name in names:
            return b.name
        b = b.parent
    return None


def fit_skeleton(arm):
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


def skirt_bones(arm):
    """Two bones hanging from the pelvis inside the skirt: the front one moves forward with the leg
    that goes in front and the back one moves back with the one that goes behind (animations). That way
    the tunic opens like a bell on a long step, without stretching between the legs."""
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.data.edit_bones
    for name, y in SKIRT_BONES.items():
        b = eb.new(name)
        b.head = Vector((0.0, y, SKIRT[1]))
        b.tail = Vector((0.0, y, SKIRT_LOW))
        b.parent = eb["pelvis"]
        b.use_deform = True
    bpy.ops.object.mode_set(mode="OBJECT")
    for name in SKIRT_BONES:
        arm.pose.bones[name].rotation_mode = "QUATERNION"


def weights(body, arm, extras):
    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    # Vertices without weight (if bone heat didn't reach them): to the nearest bone.
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
    print("unweighted vertices fixed", unweighted)
    # Smooth weights between neighboring vertices: tears appear where two neighbors follow
    # very different bones.
    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.mode_set(mode="WEIGHT_PAINT")
    bpy.ops.object.vertex_group_smooth(group_select_mode="ALL", factor=0.5, repeat=2, expand=0.0)
    bpy.ops.object.vertex_group_normalize_all(lock_active=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    # Zones that can only follow certain bones (otherwise the beard follows the arms and the clothes
    # the hands, and they tear when moving).
    spine = ["pelvis", "spine_01", "spine_02", "spine_03"]
    zones = [
        # (condition, allowed bones, bone if none is left)
        # Head, beard and hair: rigid with the head (if they are shared, the beard tears when turning).
        (lambda p: abs(p.x) < 0.2 and p.z > 1.0 * ZONE_SCALE, ["Head"], "Head"),
        (lambda p: abs(p.x) < 0.17 and p.z > 0.92 * ZONE_SCALE, ["spine_03", "neck_01", "Head"], "Head"),
        # The legs only move the skirt: from the chest up, the clothes go with the spine (otherwise
        # bone heat gave the back to the thigh and it poked through when walking).
        (lambda p: abs(p.x) < BODY_WIDTH and SKIRT[1] < p.z <= 0.92 * ZONE_SCALE, spine, "spine_02"),
        (lambda p: abs(p.x) < BODY_WIDTH and 0.12 < p.z <= SKIRT[1],
         spine + [n for n in names if n.startswith(("thigh", "calf"))], "pelvis"),
    ]
    limited = 0
    for v in body.data.vertices:
        p = body.matrix_world @ v.co
        for cond, allowed, fallback in zones:
            if not cond(p):
                continue
            gnames = {g.index: g.name for g in body.vertex_groups}
            # First note the groups and then remove them: removing while walking v.groups
            # skips elements (the list shifts) and left clothes following the fingers.
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
    print("vertices with limited bones", limited)
    # Skirt: from the waist to the hem, the cloth goes little by little from the pelvis to the skirt bones; the
    # front to the front one and the back to the back one (blended at the sides). The legs don't touch it:
    # if each leg pulls its side, the cloth in the middle stretches into spikes.
    pelvis = body.vertex_groups.get("pelvis") or body.vertex_groups.new(name="pelvis")
    front_g = body.vertex_groups.get("skirt_front") or body.vertex_groups.new(name="skirt_front")
    back_g = body.vertex_groups.get("skirt_back") or body.vertex_groups.new(name="skirt_back")
    moved = 0
    for v in body.data.vertices:
        p = body.matrix_world @ v.co
        if not (SKIRT_LOW < p.z < SKIRT[1]) or abs(p.x) > 0.3:
            continue
        gn = {g.index: g.name for g in body.vertex_groups}
        if sum(g.weight for g in v.groups if gn[g.group].startswith(("upperarm", "lowerarm", "hand", "thumb",
               "index", "middle", "ring", "pinky"))) > 0.2:
            continue                            # Sleeve or hand hanging at skirt height.
        w = min(1.0, (SKIRT[1] - p.z) / (SKIRT[1] - SKIRT[0])) ** 1.3
        front = min(1.0, max(0.0, 0.5 - p.y / SKIRT_DEPTH))
        for gi in [g.group for g in v.groups]:
            body.vertex_groups[gi].remove([v.index])
        pelvis.add([v.index], 1.0 - w, "REPLACE")
        if w * front > 1e-4:
            front_g.add([v.index], w * front, "REPLACE")
        if w * (1 - front) > 1e-4:
            back_g.add([v.index], w * (1 - front), "REPLACE")
        moved += 1
    print("skirt vertices with their bones", moved)
    # The leg peeking out under the clothes (shin, ankle, foot) goes whole with the leg: if a part
    # stayed with the rigid tunic, when the foot went back the skin stretched like a sock. By position:
    # next to the calf bone and below the hem; toward the hem it blends with the clothes.
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
        if _seg_dist(p, *calf[side]) > LEG_R and p.z > FOOT_Z:
            continue
        blend = min(1.0, (SKIRT[0] - p.z) / max(SKIRT[0] - FOOT_Z, 1e-4))
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
    print("leg vertices under the clothes", count)
    # Belt: the rope is only painted on the tunic, so it inherited the skirt blend and
    # twisted with each leg. It goes rigid with the pelvis; its neighbors, halfway, so it doesn't tear.
    rope = _rope(body) if ROPE else set()
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
    print("rigid belt vertices", len(rope), "edge", len(ring))
    # Eyes, glints and brows: stuck to the head.
    for o in extras:
        mw = o.matrix_world.copy()
        o.parent = arm
        o.parent_type = "BONE"
        o.parent_bone = "Head"
        o.matrix_world = mw


def _rope(body):
    """Vertices of the belt rope: triangles with its color in the texture, at waist height."""
    me = body.data
    img = next(n.image for n in me.materials[0].node_tree.nodes if n.type == "TEX_IMAGE" and n.image
               and "color" in n.image.name.lower())
    w, h = img.size
    px = np.array(img.pixels[:], np.float32).reshape(h, w, 4)[..., :3]
    target = np.array([0x5E, 0x39, 0x18]) / 255.0          # "rope" in the palette of texture.py.
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


def own_trot(src):
    """Trot for people in tunics, made on the original skeleton (then copied like the others): short
    steps from the hip, the knee only bends when bringing the foot forward (it doesn't go back and doesn't lift
    the tunic), soft bounce, hip and shoulders turning in time and swinging arms."""
    scene = bpy.context.scene
    idle = bpy.data.actions.get("Idle") or bpy.data.actions.get("Idle_Loop")
    src.animation_data.action = idle
    scene.frame_set(int(idle.frame_range[0]))
    # Starting pose: straight legs and spine (rest); the arms, down as in Idle (the rest pose is a
    # T). The whole Idle doesn't work: it has one foot further back than the other and the trot came out limping.
    base = {pb.name: (pb.matrix_basis.copy() if _chain(pb.bone, {"clavicle_l": 1, "clavicle_r": 1})
                      else Matrix.Identity(4)) for pb in src.pose.bones}
    act = bpy.data.actions.new("Trot")
    src.animation_data.action = act
    to_arm = src.matrix_world.inverted().to_3x3()
    x_axis = (to_arm @ Vector((1, 0, 0))).normalized()
    z_axis = (to_arm @ Vector((0, 0, 1))).normalized()

    def turn(name, deg, axis):
        # Turns the bone in world space around its head, on top of what it already has (and its parents).
        bpy.context.view_layer.update()
        pb = src.pose.bones[name]
        m = pb.matrix.copy()
        h = m.translation.copy()
        pb.matrix = Matrix.Translation(h) @ Matrix.Rotation(math.radians(deg), 4, axis) @ Matrix.Translation(-h) @ m

    t = TROT
    for f in range(TROT_FRAMES + 1):
        ph = 2 * math.pi * f / TROT_FRAMES
        s, c = math.sin(ph), math.cos(ph)
        scene.frame_set(f)
        for pb in src.pose.bones:
            pb.matrix_basis = base[pb.name]
        bpy.context.view_layer.update()
        pel = src.pose.bones["pelvis"]
        m = pel.matrix.copy()
        # Running: up in the flight (legs apart) and down on contact (when the feet cross).
        m.translation += to_arm @ Vector((0, 0, -t["bounce"] * math.cos(2 * ph)))
        pel.matrix = m
        turn("pelvis", t["twist"] * s, z_axis)
        turn("spine_01", t["lean"], x_axis)
        turn("spine_02", -t["twist"] * 1.6 * s, z_axis)                 # The shoulders, opposite to the hip.
        turn("Head", -t["lean"] * 0.7, x_axis)
        # Angles about X: the hanging bones go forward with a negative angle (Noah faces -Y).
        for side, sign in (("l", 1), ("r", -1)):
            swing = -t["thigh"] * s * sign
            if swing > 0:                                                # Backward, less.
                swing *= t["back"]
            forward = max(0.0, c * sign)                                 # The leg is coming forward.
            knee = 8 + t["knee"] * forward ** 1.5
            turn(f"thigh_{side}", swing, x_axis)
            turn(f"calf_{side}", knee, x_axis)
            turn(f"foot_{side}", -(swing + knee) * t["foot"], x_axis)
            turn(f"upperarm_{side}", t["arm"] * s * sign, x_axis)         # Arm opposite to the leg.
            turn(f"lowerarm_{side}", -t["elbow"], x_axis)
        bpy.context.view_layer.update()
        for pb in src.pose.bones:
            pb.keyframe_insert("rotation_quaternion" if pb.rotation_mode == "QUATERNION" else "rotation_euler", frame=f)
            if pb.name == "pelvis":
                pb.keyframe_insert("location", frame=f)
    act.use_fake_user = True
    print("own trot", TROT_FRAMES, "frames")


def animations(arm, src):
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
            print("missing animation", name)
            continue
        src.animation_data.action = action
        f0, f1 = (int(round(x)) for x in action.frame_range)
        scene.frame_start, scene.frame_end = f0, f1
        bpy.ops.object.mode_set(mode="POSE")
        bpy.ops.pose.select_all(action="SELECT")
        bpy.ops.nla.bake(frame_start=f0, frame_end=f1, only_selected=False, visual_keying=True,
                         clear_constraints=False, use_current_action=False, bake_types={"POSE"})
        new = arm.animation_data.action
        new.name = PREFIX + name
        # The pelvis moves too (bounce when walking, crouching): offset from the original,
        # scaled to Noah's leg length. Without the horizontal advance (the game does that).
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
            _skirt(arm, f, stance)
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
    print("animations", baked)
    return baked


def _thigh_angle(arm, side, rest=False):
    """Forward (negative) or backward (positive) angle of the thigh, seen from the side."""
    if rest:
        b = arm.data.bones[f"thigh_{side}"]
        d = b.tail_local - b.head_local
    else:
        pb = arm.pose.bones[f"thigh_{side}"]
        d = pb.tail - pb.head
    d = arm.matrix_world.to_3x3() @ d
    return math.atan2(d.y, -d.z)


def _skirt(arm, frame, stance):
    """Sets the skirt bones in this frame: the front one follows the most forward thigh and the back one
    the most backward, counted from the average pose of the animation (stance): at rest, slightly forward
    thighs don't push the cloth; if both go the same, they hang straight."""
    bpy.context.view_layer.update()
    swing = [_thigh_angle(arm, s) - stance[s] for s in "lr"]
    lim = math.radians(SKIRT_MAX)
    angles = {"skirt_front": max(min(min(swing), 0.0) * SKIRT_FOLLOW, -lim),
              "skirt_back": min(max(max(swing), 0.0) * SKIRT_FOLLOW, lim)}
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


def natural_speed(arm, action_name):
    """Speed (m/s) at which Noah has to be moved so the feet don't slide."""
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
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
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
    shots = [("rest", None, 0)] + [(a, PREFIX + a, f) for a, f in (("Walk", 8), ("Jog_Fwd", 6),
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
    if "--profile" in argv:
        i = argv.index("--profile")
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
    body = next(o for o in meshes if o.name.startswith(BODY))
    # glTF splits the vertices at the texture seams; they are joined again (the UVs are kept)
    # so the pieces get the same weights and don't open up when moving.
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(body.data)
    n0 = len(bm.verts)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    print("vertices joined at seams", n0 - len(bm.verts))
    bm.to_mesh(body.data)
    bm.free()
    body.name = PREFIX.rstrip("_")
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
    # The importer leaves the animations in NLA tracks; they are removed so each action can be picked.
    for tr in list(src.animation_data.nla_tracks):
        src.animation_data.nla_tracks.remove(tr)

    own_trot(src)
    arm = src.copy()
    arm.data = src.data.copy()
    arm.animation_data_clear()
    arm.name = "Skeleton"
    arm.data.name = "Skeleton"
    bpy.context.scene.collection.objects.link(arm)
    arm.animation_data_create()

    fit_skeleton(arm)
    skirt_bones(arm)
    weights(body, arm, extras)
    baked = animations(arm, src)
    for name in (PREFIX + "Walk", PREFIX + "Jog_Fwd", PREFIX + "Sprint", PREFIX + "Trot"):
        if name in baked:
            print("SPEED", name, round(natural_speed(arm, name), 3))
    if renders:
        os.makedirs(renders, exist_ok=True)
        render(renders, arm)

    # Export only Noah (skeleton + meshes), without the original skeleton.
    for a in [a for a in bpy.data.actions if not a.name.startswith(PREFIX)]:
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
