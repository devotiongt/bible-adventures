extends Node3D
## A village character (Noah's family and the villagers): a model rigged with rig_noah.py and its
## profile (tools/blender/profiles/), who stays in one spot for a while (standing, talking or
## working) and then walks slowly to the next of their points, in order and unhurried.
## Data in data/village.json, "villagers".

## Color brightness: Noah uses 0.74 (noah_rig.gd) because his palette is very light; the ones made with
## TRELLIS already come with muted colors and use 1 (data/village.json, "shine").
const ROUGHNESS := 0.95
const SPECULAR := 0.2
const SPEED := 0.55                            ## Calm pace (m/s).
const TURN_SPEED := 4.0

var world  ## world.gd
var model_path := ""
var prefix := ""
var natural_walk := 0.63   ## Natural speed of the walk cycle (printed by rig_noah.py).
var points: Array[Vector3] = []
var stays: Array = ["Idle"]   ## What they do on reaching a point: looping animations.
var albedo_tint := 0.74
var rng := RandomNumberGenerator.new()

var anim: AnimationPlayer
var _target := 0
var _wait := 0.0


func _ready() -> void:
	var model: Node3D = load(model_path).instantiate()
	model.rotation.y = PI      # The model faces +Z; here "forward" is -Z, like Noah.
	add_child(model)
	_soften_materials(model)
	anim = model.find_children("*", "AnimationPlayer", true, false)[0]
	for a in ["Idle", "Walk", "Idle_Talking", "Fixing_Kneeling", "Interact"]:
		if anim.has_animation(prefix + a):
			anim.get_animation(prefix + a).loop_mode = Animation.LOOP_LINEAR
	_stay()


func _process(delta: float) -> void:
	if points.is_empty():
		return
	if _wait > 0.0:
		_wait -= delta
		if _wait <= 0.0:
			_target = (_target + 1) % points.size()
			_play("Walk", SPEED / natural_walk)
		return
	var to := points[_target] - position
	to.y = 0.0
	if to.length() < 0.15:
		_stay()
		return
	var step := to.normalized() * minf(SPEED * delta, to.length())
	position += step
	position.y = world.height_at(position.x, position.z)
	var facing := atan2(-to.x, -to.z)
	rotation.y = lerp_angle(rotation.y, facing, minf(1.0, TURN_SPEED * delta))


## Stays at the point doing one of their things for a while.
func _stay() -> void:
	_wait = rng.randf_range(5.0, 11.0)
	_play(stays[rng.randi() % stays.size()], 1.0)


func _play(anim_name: String, speed: float) -> void:
	var full := prefix + anim_name
	if not anim.has_animation(full):
		full = prefix + "Idle"
	if anim.current_animation != full:
		anim.play(full, 0.3)
	anim.speed_scale = speed


func _soften_materials(root: Node) -> void:
	for mi in root.find_children("*", "MeshInstance3D", true, false):
		var mesh: Mesh = (mi as MeshInstance3D).mesh
		for i in mesh.get_surface_count():
			var src := mesh.surface_get_material(i) as BaseMaterial3D
			if src == null:
				continue
			var m := src.duplicate() as BaseMaterial3D
			m.albedo_color = src.albedo_color * Color(albedo_tint, albedo_tint, albedo_tint)
			m.roughness = ROUGHNESS
			m.metallic = 0.0
			m.metallic_specular = SPECULAR
			(mi as MeshInstance3D).set_surface_override_material(i, m)
