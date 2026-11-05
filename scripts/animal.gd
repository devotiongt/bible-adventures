extends Node3D
## Ambient animal: wanders, stops to eat and rests near its area.
## (In the animals chapter they will be the ones Noah guides to the ark.)

const Models := preload("res://scripts/models.gd")

## Model -> [scale, natural speed of the "Walk" cycle in model units].
## The natural speed was measured from the hooves' travel while planted,
## so the animal moves exactly as far as its legs carry it and doesn't "skate".
const SPECIES := {
	"Deer": [0.36, 2.49],
	"Stag": [0.38, 2.42],
	"Alpaca": [0.36, 2.25],
	"Horse": [0.4, 2.75],
	"Horse_White": [0.4, 2.75],
	"Donkey": [0.36, 2.67],
	"Cow": [0.36, 2.73],
	"Bull": [0.38, 2.73],
	"Fox": [0.26, 2.18],
	"ShibaInu": [0.26, 2.37],
}

var species := "Deer"
var world  ## world.gd
var home := Vector3.ZERO
var rng := RandomNumberGenerator.new()

var _anim: AnimationPlayer
var _target := Vector3.ZERO
var _speed := 1.0
var _wait := 0.0
var _walking := false


func _ready() -> void:
	# It moves every frame (not in physics): no physics interpolation.
	physics_interpolation_mode = Node.PHYSICS_INTERPOLATION_MODE_OFF
	var data: Array = SPECIES[species]
	var model: Node3D = Models.scene(Models.ANIMALS % species).instantiate()
	model.scale = Vector3.ONE * float(data[0])
	add_child(model)
	_speed = float(data[0]) * float(data[1])
	_anim = model.find_children("*", "AnimationPlayer", true, false)[0]
	for anim_name in ["Idle", "Walk", "Eating", "Idle_2", "Idle_Headlow"]:
		if _anim.has_animation(anim_name):
			_anim.get_animation(anim_name).loop_mode = Animation.LOOP_LINEAR
	_rest()


func _process(delta: float) -> void:
	if _walking:
		var to := _target - position
		to.y = 0.0
		if to.length() < 0.3:
			_rest()
			return
		var dir := to.normalized()
		position += dir * _speed * delta
		position.y = world.height_at(position.x, position.z)
		rotation.y = lerp_angle(rotation.y, atan2(dir.x, dir.z), 4.0 * delta)
	else:
		_wait -= delta
		if _wait <= 0.0:
			_wander()


func _rest() -> void:
	_walking = false
	_wait = rng.randf_range(3.0, 8.0)
	var options := ["Idle", "Eating"]
	if _anim.has_animation("Idle_Headlow"):
		options.append("Idle_Headlow")
	var choice: String = options[rng.randi() % options.size()]
	if _anim.has_animation(choice):
		_anim.play(choice, 0.4)


func _wander() -> void:
	# In a pen it only wanders inside the fence; outside, around its spot.
	var pen: float = world.corral_radius_at(home.x, home.z)
	var reach := pen - 1.2 if pen > 0.0 else 7.0
	for attempt in 10:
		var p := home + Vector3(rng.randf_range(-reach, reach), 0, rng.randf_range(-reach, reach))
		var h: float = world.height_at(p.x, p.z)
		var inside := pen > 0.0 and Vector2(p.x - home.x, p.z - home.z).length() < reach
		if inside or (pen == 0.0 and world.is_open_ground(p.x, p.z, 1.0)):
			_target = Vector3(p.x, h, p.z)
			_walking = true
			_anim.play("Walk", 0.3)
			return
	_wait = 2.0
