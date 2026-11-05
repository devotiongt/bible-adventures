extends Node3D
## Follow camera with an elevated view (Animal Crossing style).
## Q/R or the gamepad triggers rotate it in 45° steps, the wheel zooms in or out,
## and dragging with the right button rotates it freely.

const MIN_DISTANCE := 7.0
const MAX_DISTANCE := 24.0

var target: Node3D
var distance := 13.0
var pitch_deg := 42.0
var camera: Camera3D
var _yaw := 0.0


func _ready() -> void:
	# Moves every frame (not in physics): no physics interpolation.
	physics_interpolation_mode = Node.PHYSICS_INTERPOLATION_MODE_OFF
	camera = Camera3D.new()
	camera.fov = 45.0
	camera.far = 400.0
	add_child(camera)
	camera.make_current()
	if target:
		global_position = target.global_position


func set_yaw(yaw: float) -> void:
	_yaw = yaw
	rotation.y = yaw


func _process(delta: float) -> void:
	if target:
		# Smoothed position (physics interpolation): otherwise, at low frame rates the
		# character jitters relative to the camera.
		var target_pos := target.get_global_transform_interpolated().origin
		global_position = global_position.lerp(target_pos, 1.0 - exp(-8.0 * delta))
	if Input.is_action_just_pressed("camera_left"):
		_yaw += PI / 4.0
	if Input.is_action_just_pressed("camera_right"):
		_yaw -= PI / 4.0
	rotation.y = lerp_angle(rotation.y, _yaw, 1.0 - exp(-10.0 * delta))
	var pitch := deg_to_rad(pitch_deg)
	camera.position = Vector3(0, sin(pitch), cos(pitch)) * distance + Vector3(0, 1.0, 0)
	camera.look_at(global_position + Vector3(0, 1.0, 0))


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed:
		if event.button_index == MOUSE_BUTTON_WHEEL_UP:
			distance = maxf(MIN_DISTANCE, distance - 1.0)
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			distance = minf(MAX_DISTANCE, distance + 1.0)
	elif event is InputEventMouseMotion and event.button_mask & MOUSE_BUTTON_MASK_RIGHT:
		_yaw -= event.relative.x * 0.006
		rotation.y = _yaw
		pitch_deg = clampf(pitch_deg + event.relative.y * 0.2, 20.0, 70.0)
