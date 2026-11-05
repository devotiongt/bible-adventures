extends Node3D
## The in-game Noah: with a short tunic and legs (TRELLIS, references/noah_legs_turnaround.webp), rigged with
## tools/blender/rig_noah.py and its profile (profiles/noah_short.json), with the animations from the
## Universal Animation Library adapted to his body. The previous Noah (Rodin, long tunic) is still in
## assets/characters/rodin/noah_rig.glb.
## Same interface as the previous model (noah_model.gd): update_locomotion() and action().

const LowPoly := preload("res://scripts/lowpoly.gd")
const SkirtSprings := preload("res://scripts/skirt_springs.gd")

const MODEL := "res://assets/characters/noah_trellis/noah_short_rig.glb"
const LOOPING := ["Noah_Idle", "Noah_Walk", "Noah_Jog_Fwd", "Noah_Sprint", "Noah_Idle_Talking", "Noah_Fixing_Kneeling",
		"Noah_Trot"]

## Natural speed (m/s) of each cycle, measured on the rig (foot travel): the animation is
## scaled by speed / natural so the feet don't slide.
const WALK_SPEED := 0.455
const JOG_SPEED := 1.215
const SPRINT_SPEED := 1.567
## Our own trot (rig_noah.py, own_trot): kept in reserve. The library's Jog_Fwd is used, which has a better
## stride; the tunic no longer deforms with it because it opens with the skirt bones from rig_noah.py.
const TROT_SPEED := 0.859

## How much of the back's original lean is kept when running (0 = straight).
const POSTURE_KEEP := 0.65
const POSTURE_BONES := ["pelvis", "spine_01", "spine_02", "spine_03", "neck_01", "Head"]
## Arms when jogging: the original holds the fists up like a boxer; they are brought closer to the rest
## pose (arms down), leaving a gentle swing in time with the legs.
const ARM_KEEP := 0.65
const ARM_BONES := ["clavicle_l", "clavicle_r", "upperarm_l", "upperarm_r", "lowerarm_l", "lowerarm_r",
		"hand_l", "hand_r"]

## A more matte and slightly less bright material: with the game's sun, glow and saturation,
## the light colors of the palette (white hair, skin) were blowing out.
const ALBEDO_TINT := Color(1, 1, 1)     ## TRELLIS already comes with muted colors (Rodin's was at 0.74).
const ROUGHNESS := 0.95
const SPECULAR := 0.2

## Tools in the right hand during an action (chopping with an axe, breaking with a pickaxe).
## The handle runs along the tool's Y axis; GRIP_* place it on the hand bone.
const TOOL_HAND := "hand_r"
const GRIP_POS := Vector3(0, 0.07, 0)
const GRIP_ROT := Vector3(90, 0, 0)
## Twist around the handle: the axe blade and the pickaxe points facing the strike.
const TOOL_TWIST := 180.0
const WOOD := Color("6a4a2c")
const STONE := Color("6e6c67")
const ROPE := Color("5e3918")

## Model to load (can be changed before adding it, to try another Noah) and its brightness (the TRELLIS ones
## already come with muted colors: 1).
var model_path := MODEL
var albedo_tint := ALBEDO_TINT
var use_springs := true
var skeleton: Skeleton3D
var anim: AnimationPlayer
var tools: Dictionary = {}
var _action_left := 0.0


func _ready() -> void:
	var model: Node3D = load(model_path).instantiate()
	model.rotation.y = PI  # The model faces +Z; in the game "forward" is -Z.
	add_child(model)
	skeleton = model.find_children("*", "Skeleton3D", true, false)[0]
	if use_springs:
		SkirtSprings.add(skeleton)    # Only if the model has skirt chains (separate tunic).
	_soften_materials(model)
	anim = model.find_children("*", "AnimationPlayer", true, false)[0]
	# Running and jogging come from an athletic runner leaning far forward: the back, neck and
	# head are straightened, leaving only a little of that lean.
	for anim_name in ["Noah_Sprint", "Noah_Jog_Fwd"]:
		if anim.has_animation(anim_name):
			var a := anim.get_animation(anim_name)
			_straighten(a, POSTURE_BONES, POSTURE_KEEP)
			_straighten(a, ARM_BONES, ARM_KEEP)
			_no_sway(a)
	for anim_name in LOOPING:
		if anim.has_animation(anim_name):
			anim.get_animation(anim_name).loop_mode = Animation.LOOP_LINEAR
	anim.play("Noah_Idle")
	_build_tools()


func _process(delta: float) -> void:
	_action_left -= delta
	if _action_left <= 0.0:
		_show_tool("")


## Picks walk, jog, run or idle based on speed (except during an action).
func update_locomotion(speed: float) -> void:
	if _action_left > 0.0 and speed < 0.5:
		return
	if speed > 3.6:   # Run only above normal speed (reserved for later).
		_play("Noah_Sprint", speed / SPRINT_SPEED)
	elif speed > 1.2:
		_play("Noah_Jog_Fwd", speed / JOG_SPEED)
	elif speed > 0.2:
		_play("Noah_Walk", speed / WALK_SPEED)
	else:
		_play("Noah_Idle", 1.0)


## Plays a one-off animation (chop, gather, build), with a tool in the hand if
## given ("axe", "pickaxe"). Returns its duration.
func action(anim_name: String, speed := 1.5, max_time := 0.9, tool := "") -> float:
	var full := "Noah_" + anim_name
	if not anim.has_animation(full):
		return 0.0
	anim.play(full, 0.12, speed)
	anim.seek(0.0, true)
	_action_left = minf(anim.get_animation(full).length / speed, max_time)
	_show_tool(tool)
	return _action_left


func _show_tool(tool: String) -> void:
	for t in tools:
		tools[t].visible = t == tool


func _build_tools() -> void:
	var hand := BoneAttachment3D.new()
	hand.bone_name = TOOL_HAND
	skeleton.add_child(hand)
	var grip := Node3D.new()
	grip.position = GRIP_POS
	grip.rotation_degrees = GRIP_ROT
	hand.add_child(grip)

	# Chibi proportions, like Noah: short thick handle, big head.
	var axe := Node3D.new()
	_handle(axe)
	LowPoly.box(axe, Vector3(0.09, 0.11, 0.08), STONE, Vector3(-0.01, 0.33, 0))           # Butt.
	var blade := PrismMesh.new()         # Wedge: narrow by the handle, wide at the edge.
	blade.size = Vector3(0.24, 0.17, 0.05)
	LowPoly.part(axe, blade, STONE, Vector3(0.1, 0.33, 0), Vector3(0, 0, 90))
	LowPoly.box(axe, Vector3(0.03, 0.24, 0.056), STONE.lightened(0.25), Vector3(0.18, 0.33, 0))  # Edge.
	LowPoly.box(axe, Vector3(0.085, 0.05, 0.09), ROPE, Vector3(0, 0.25, 0))              # Binding.
	tools["axe"] = axe

	var pick := Node3D.new()
	_handle(pick)
	LowPoly.box(pick, Vector3(0.1, 0.1, 0.09), STONE, Vector3(0, 0.34, 0))
	for side in [-1, 1]:
		LowPoly.cylinder(pick, 0.0, 0.05, 0.2, 4, STONE, Vector3(0.13 * side, 0.32, 0),
				Vector3(0, 0, -100 * side))
	LowPoly.box(pick, Vector3(0.085, 0.05, 0.1), ROPE, Vector3(0, 0.26, 0))
	tools["pickaxe"] = pick

	for t in tools:
		tools[t].visible = false
		tools[t].rotation_degrees.y = TOOL_TWIST
		grip.add_child(tools[t])


## Wooden handle along Y, with a knob at the bottom so it doesn't slip out of the hand.
func _handle(parent: Node3D) -> void:
	LowPoly.cylinder(parent, 0.03, 0.035, 0.5, 6, WOOD, Vector3(0, 0.12, 0))
	LowPoly.cylinder(parent, 0.045, 0.045, 0.05, 6, WOOD.darkened(0.25), Vector3(0, -0.13, 0))


func _play(anim_name: String, speed: float) -> void:
	if anim.current_animation != anim_name:
		anim.play(anim_name, 0.2)
	anim.speed_scale = speed


## Brings the rotation of the spine, neck and head closer to the rest pose.
func _straighten(a: Animation, bones: Array, keep: float) -> void:
	for t in a.get_track_count():
		if a.track_get_type(t) != Animation.TYPE_ROTATION_3D:
			continue
		var bone := String(a.track_get_path(t).get_concatenated_subnames())
		if bone not in bones:
			continue
		var rest := skeleton.get_bone_rest(skeleton.find_bone(bone)).basis.get_rotation_quaternion()
		for k in a.track_get_key_count(t):
			a.track_set_key_value(t, k, rest.slerp(a.track_get_key_value(t, k), keep))


## No sideways sway of the hips (the side-to-side wobble when jogging).
func _no_sway(a: Animation) -> void:
	for t in a.get_track_count():
		if a.track_get_type(t) != Animation.TYPE_POSITION_3D:
			continue
		var bone := String(a.track_get_path(t).get_concatenated_subnames())
		if bone != "pelvis":
			continue
		var rest_x := skeleton.get_bone_rest(skeleton.find_bone(bone)).origin.x
		for k in a.track_get_key_count(t):
			var v: Vector3 = a.track_get_key_value(t, k)
			a.track_set_key_value(t, k, Vector3(rest_x, v.y, v.z))


func _soften_materials(root: Node) -> void:
	for mi in root.find_children("*", "MeshInstance3D", true, false):
		var mesh: Mesh = (mi as MeshInstance3D).mesh
		for i in mesh.get_surface_count():
			var src := mesh.surface_get_material(i) as BaseMaterial3D
			if src == null:
				continue
			var m := src.duplicate() as BaseMaterial3D
			m.albedo_color = src.albedo_color * albedo_tint
			m.roughness = ROUGHNESS
			m.metallic = 0.0
			m.metallic_specular = SPECULAR
			(mi as MeshInstance3D).set_surface_override_material(i, m)
