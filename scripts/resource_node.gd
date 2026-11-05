extends StaticBody3D
## Recurso recolectable: árbol, roca, juncos (fibra) o pozo de brea.
## Se golpea varias veces con "interactuar", suelta materiales y reaparece con el tiempo.

const LowPoly := preload("res://scripts/lowpoly.gd")
const Effects := preload("res://scripts/effects.gd")
const Stylized := preload("res://scripts/stylized.gd")

## Color y altura de las partículas al golpear cada recurso.
const PARTICLES := {
	"arbol": [Color("c99a62"), 1.0],
	"roca": [Color("9a9a95"), 0.5],
	"arbusto": [Color("9db55a"), 0.6],
	"brea": [Color("1a1310"), 0.2],
}

const KINDS := {
	"arbol": {"accion": "Talar árbol", "golpes": 4, "herramienta": "hacha", "golpes_herramienta": 2,
		"suelta": "madera", "cantidad": 3, "reaparece": 45.0, "radio": 0.4},
	"roca": {"accion": "Picar roca", "golpes": 3, "suelta": "piedra", "cantidad": 2,
		"reaparece": 60.0, "radio": 0.8},
	"arbusto": {"accion": "Recoger fibra de juncos", "golpes": 1, "suelta": "fibra", "cantidad": 2,
		"reaparece": 25.0, "radio": 0.5},
	"brea": {"accion": "Sacar brea", "golpes": 2, "requiere": "cubo", "suelta": "brea", "cantidad": 2,
		"reaparece": 35.0, "radio": 1.1},
}

var kind := "arbol"
var config: Dictionary
var hits := 0
var depleted := false
var visual: Node3D
var _collision: CollisionShape3D


func setup(p_kind: String, rng: RandomNumberGenerator) -> void:
	kind = p_kind
	config = KINDS[kind]
	name = kind.capitalize()
	add_to_group("interactuable")
	visual = Node3D.new()
	add_child(visual)
	match kind:
		"arbol":
			_build_tree(rng)
		"roca":
			_build_rock(rng)
		"arbusto":
			_build_reeds(rng)
		"brea":
			_build_pitch(rng)


# --- Interacción (la usa el jugador) ------------------------------------------

func interact_distance(from: Vector3) -> float:
	if depleted:
		return INF
	var d := Vector2(from.x - global_position.x, from.z - global_position.z).length()
	return d - float(config["radio"]) * scale.x


func get_prompt() -> String:
	if config.has("requiere") and not Game.has_item(config["requiere"]):
		return "Necesitas un %s" % Game.item_name(config["requiere"]).to_lower()
	return config["accion"]


func interact(_player: Node) -> void:
	if depleted:
		return
	if config.has("requiere") and not Game.has_item(config["requiere"]):
		Game.notify.emit("Necesitas un %s para esto. Fabrícalo con C." % Game.item_name(config["requiere"]).to_lower())
		return
	hits += 1
	var fx: Array = PARTICLES[kind]
	Effects.burst(get_parent(), global_position + Vector3(0, fx[1], 0), fx[0], 10, 0.08, 3.2)
	var needed := int(config["golpes"])
	if config.has("herramienta") and Game.has_item(config["herramienta"]):
		needed = int(config["golpes_herramienta"])
	if hits >= needed:
		hits = 0
		_harvest()
	else:
		_shake()


func _harvest() -> void:
	depleted = true
	var amount := int(config["cantidad"])
	Game.add(config["suelta"], amount)
	Game.notify.emit("+%d %s" % [amount, Game.item_name(config["suelta"])])
	if _collision:
		_collision.set_deferred("disabled", true)
	var t := create_tween()
	if kind == "arbol":
		Effects.burst(get_parent(), global_position + Vector3(0, 3.0, 0), Color("6e9e3e"), 24, 0.14, 2.0, 2.5, 1.8)
		# El árbol cae hacia un lado antes de desaparecer.
		t.tween_property(visual, "rotation:z", deg_to_rad(85), 0.6).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_IN)
	t.tween_property(visual, "scale", Vector3.ONE * 0.01, 0.3).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_IN)
	t.tween_callback(func() -> void: visual.visible = false)
	get_tree().create_timer(float(config["reaparece"])).timeout.connect(_respawn)


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


# --- Modelos ------------------------------------------------------------------

func _add_collision(shape: Shape3D, offset: Vector3) -> void:
	_collision = CollisionShape3D.new()
	_collision.shape = shape
	_collision.position = offset
	add_child(_collision)


func _build_tree(rng: RandomNumberGenerator) -> void:
	# Pinos (la "madera de gofer") y árboles redondos, como en la referencia.
	var tree := Stylized.pine(rng) if rng.randf() < 0.45 else Stylized.round_tree(rng)
	tree.scale = Vector3.ONE * rng.randf_range(0.9, 1.15)
	visual.add_child(tree)
	# El tocón queda siempre, el resto cae al talarlo.
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
