extends StaticBody3D
## Gatherable resource: tree, rock, reeds (fiber) or pitch pit.
## It is struck several times with "interact", drops materials and respawns over time.

const LowPoly := preload("res://scripts/lowpoly.gd")
const Effects := preload("res://scripts/effects.gd")
const Stylized := preload("res://scripts/stylized.gd")

## Color and height of the particles when striking each resource.
const PARTICLES := {
	"tree": [Color("c99a62"), 1.0],
	"rock": [Color("9a9a95"), 0.5],
	"bush": [Color("9db55a"), 0.6],
	"pitch": [Color("1a1310"), 0.2],
}

const KINDS := {
	"tree": {"action": "Chop tree", "hits": 4, "tool": "axe", "tool_hits": 2,
		"drops": "wood", "amount": 3, "respawn": 45.0, "radius": 0.4},
	"rock": {"action": "Break rock", "hits": 3, "drops": "stone", "amount": 2,
		"respawn": 60.0, "radius": 0.8},
	"bush": {"action": "Gather reed fiber", "hits": 1, "drops": "fiber", "amount": 2,
		"respawn": 25.0, "radius": 0.5},
	"pitch": {"action": "Draw pitch", "hits": 2, "requires": "bucket", "drops": "pitch", "amount": 2,
		"respawn": 35.0, "radius": 1.1},
}

var kind := "tree"
var config: Dictionary
var hits := 0
var depleted := false
var visual: Node3D
var _collision: CollisionShape3D


func setup(p_kind: String, rng: RandomNumberGenerator) -> void:
	kind = p_kind
	config = KINDS[kind]
	name = kind.capitalize()
	add_to_group("interactable")
	visual = Node3D.new()
	add_child(visual)
	match kind:
		"tree":
			_build_tree(rng)
		"rock":
			_build_rock(rng)
		"bush":
			_build_reeds(rng)
		"pitch":
			_build_pitch(rng)


# --- Interaction (used by the player) -----------------------------------------

func interact_distance(from: Vector3) -> float:
	if depleted:
		return INF
	var d := Vector2(from.x - global_position.x, from.z - global_position.z).length()
	return d - float(config["radius"]) * scale.x


func get_prompt() -> String:
	if config.has("requires") and not Game.has_item(config["requires"]):
		return "You need a %s" % Game.item_name(config["requires"]).to_lower()
	return config["action"]


func interact(_player: Node) -> void:
	if depleted:
		return
	if config.has("requires") and not Game.has_item(config["requires"]):
		Game.notify.emit("You need a %s for this. Craft it with C." % Game.item_name(config["requires"]).to_lower())
		return
	hits += 1
	var fx: Array = PARTICLES[kind]
	Effects.burst(get_parent(), global_position + Vector3(0, fx[1], 0), fx[0], 10, 0.08, 3.2)
	var needed := int(config["hits"])
	if config.has("tool") and Game.has_item(config["tool"]):
		needed = int(config["tool_hits"])
	if hits >= needed:
		hits = 0
		_harvest()
	else:
		_shake()


func _harvest() -> void:
	depleted = true
	var amount := int(config["amount"])
	Game.add(config["drops"], amount)
	Game.notify.emit("+%d %s" % [amount, Game.item_name(config["drops"])])
	if _collision:
		_collision.set_deferred("disabled", true)
	var t := create_tween()
	if kind == "tree":
		Effects.burst(get_parent(), global_position + Vector3(0, 3.0, 0), Color("6e9e3e"), 24, 0.14, 2.0, 2.5, 1.8)
		# The tree falls to one side before disappearing.
		t.tween_property(visual, "rotation:z", deg_to_rad(85), 0.6).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_IN)
	t.tween_property(visual, "scale", Vector3.ONE * 0.01, 0.3).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_IN)
	t.tween_callback(func() -> void: visual.visible = false)
	get_tree().create_timer(float(config["respawn"])).timeout.connect(_respawn)


func _respawn() -> void:
	depleted = false
	visual.rotation = Vector3.ZERO
	visual.visible = true
	if _collision:
		_collision.disabled = false
	var t := create_tween()
	t.tween_property(visual, "scale", Vector3.ONE, 0.5).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)


func _shake() -> void:
	var t := create_tween()
	t.tween_property(visual, "rotation:z", 0.12, 0.05)
	t.tween_property(visual, "rotation:z", -0.08, 0.08)
	t.tween_property(visual, "rotation:z", 0.0, 0.08)


# --- Models -------------------------------------------------------------------

func _add_collision(shape: Shape3D, offset: Vector3) -> void:
	_collision = CollisionShape3D.new()
	_collision.shape = shape
	_collision.position = offset
	add_child(_collision)


func _build_tree(rng: RandomNumberGenerator) -> void:
	# Pines (the "gopher wood") and round trees, as in the reference.
	var tree := Stylized.pine(rng) if rng.randf() < 0.45 else Stylized.round_tree(rng)
	tree.scale = Vector3.ONE * rng.randf_range(0.9, 1.15)
	visual.add_child(tree)
	# The stump always stays; the rest falls when chopped.
	LowPoly.cylinder(self, 0.2, 0.26, 0.28, 8, Color("6b4a33"), Vector3(0, 0.12, 0))
	LowPoly.cylinder(self, 0.19, 0.19, 0.02, 8, Color("c9a77c"), Vector3(0, 0.27, 0))
	var shape := CylinderShape3D.new()
	shape.radius = 0.35
	shape.height = 3.0
	_add_collision(shape, Vector3(0, 1.5, 0))


func _build_rock(rng: RandomNumberGenerator) -> void:
	var rock := Stylized.rock(rng)
	rock.scale = Vector3.ONE * rng.randf_range(0.95, 1.2)
	visual.add_child(rock)
	var shape := SphereShape3D.new()
	shape.radius = 0.75
	_add_collision(shape, Vector3(0, 0.3, 0))


func _build_reeds(rng: RandomNumberGenerator) -> void:
	for i in 3:
		var reed := Stylized.tuft(rng)
		reed.scale = Vector3.ONE * rng.randf_range(1.4, 1.9)
		reed.position = Vector3(rng.randf_range(-0.35, 0.35), 0, rng.randf_range(-0.35, 0.35)) if i > 0 else Vector3.ZERO
		visual.add_child(reed)


func _build_pitch(rng: RandomNumberGenerator) -> void:
	var pitch := StandardMaterial3D.new()
	pitch.albedo_color = Color("1a1310")
	pitch.roughness = 0.12
	pitch.metallic_specular = 0.9
	var pool := LowPoly.cylinder(visual, 1.1, 1.15, 0.12, 16, Color("1a1310"), Vector3(0, 0.03, 0))
	pool.material_override = pitch
	var bubble := LowPoly.sphere(visual, 0.18, 0.2, 10, 5, Color("1a1310"), Vector3(0.3, 0.1, -0.2))
	bubble.material_override = pitch
	for i in 10:
		var angle := TAU * i / 10.0 + rng.randf_range(-0.1, 0.1)
		var pebble := Stylized.rock(rng)
		pebble.scale = Vector3.ONE * rng.randf_range(0.14, 0.22)
		pebble.position = Vector3(cos(angle) * 1.25, 0.0, sin(angle) * 1.25)
		pebble.rotation.y = rng.randf() * TAU
		visual.add_child(pebble)
