extends CharacterBody3D
## Noah: third-person movement relative to the camera and interaction with the world.

signal target_changed(target: Node)

const NoahModel := preload("res://scripts/noah_rig.gd")

## Noah's animation depending on what he is doing.
const ACTION_ANIMS := {"tree": "Sword_Attack", "rock": "Sword_Attack", "bush": "Interact", "pitch": "Interact"}
## Tool he holds in his hand while doing it.
const ACTION_TOOLS := {"tree": "axe", "rock": "pickaxe"}

const SPEED := 2.3
const ACCEL := 40.0
const GRAVITY := 22.0
const REACH := 1.6
const ACTION_COOLDOWN := 0.38

var world  ## world.gd, to query the terrain height.
var camera_rig: Node3D
var target: Node = null

var visual: Node3D
var noah: Node3D
var _cooldown := 0.0
var _needs_release := false


func _ready() -> void:
	var shape := CapsuleShape3D.new()
	shape.radius = 0.35
	shape.height = 1.7
	var col := CollisionShape3D.new()
	col.shape = shape
	col.position.y = 0.85
	add_child(col)
	floor_max_angle = deg_to_rad(75)   # Climbs the ramps of the terrain steps.
	_build_model()


func _build_model() -> void:
	visual = Node3D.new()
	add_child(visual)
	noah = NoahModel.new()
	visual.add_child(noah)


func _physics_process(delta: float) -> void:
	if Game.ui_blocked:
		_needs_release = true
	elif _needs_release and not Input.is_action_pressed("interact"):
		_needs_release = false

	var input := Vector2.ZERO
	if not Game.ui_blocked:
		input = Input.get_vector("move_left", "move_right", "move_up", "move_down")
	var dir := Vector3(input.x, 0, input.y)
	if camera_rig:
		dir = dir.rotated(Vector3.UP, camera_rig.rotation.y)

	var desired := dir * SPEED
	if world and not world.is_walkable(position.x + desired.x * 0.15, position.z + desired.z * 0.15):
		desired = Vector3.ZERO
	velocity.x = move_toward(velocity.x, desired.x, ACCEL * delta)
	velocity.z = move_toward(velocity.z, desired.z, ACCEL * delta)
	velocity.y = velocity.y - GRAVITY * delta if not is_on_floor() else -0.5
	move_and_slide()

	if dir.length() > 0.1:
		visual.rotation.y = lerp_angle(visual.rotation.y, atan2(-dir.x, -dir.z), 12.0 * delta)
	_animate_walk(delta)
	_update_target()

	_cooldown -= delta
	if target and _cooldown <= 0.0 and not Game.ui_blocked and not _needs_release \
			and Input.is_action_pressed("interact"):
		_interact()


func _animate_walk(_delta: float) -> void:
	noah.update_locomotion(Vector2(velocity.x, velocity.z).length())


func _update_target() -> void:
	var best: Node = null
	var best_d := REACH
	for node in get_tree().get_nodes_in_group("interactable"):
		var d: float = node.interact_distance(global_position)
		if d < best_d:
			best_d = d
			best = node
	if best != target:
		target = best
		target_changed.emit(target)


func _interact() -> void:
	_cooldown = ACTION_COOLDOWN
	var to := (target as Node3D).global_position - global_position
	if Vector2(to.x, to.z).length() > 0.2:
		visual.rotation.y = atan2(-to.x, -to.z)
	var anim_name: String = ACTION_ANIMS.get(target.get("kind"), "Fixing_Kneeling")
	_cooldown = maxf(noah.action(anim_name, 1.6, 0.75, ACTION_TOOLS.get(target.get("kind"), "")),
			ACTION_COOLDOWN)
	target.interact(self)
