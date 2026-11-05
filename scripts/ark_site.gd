extends Node3D
## Obra del arca. El modelo se hace en Blender (herramientas/blender/arca.py) y trae
## un nodo por etapa: Etapa1 … Etapa5. Cada etapa construida se hace visible y sólida;
## la siguiente se ve como un "fantasma" translúcido para que el jugador sepa qué viene.
## La etapa 3 (sellar con brea) no añade piezas: oscurece los tablones del casco.

const LowPoly := preload("res://scripts/lowpoly.gd")
const Models := preload("res://scripts/models.gd")
const Effects := preload("res://scripts/effects.gd")
const ARK_MODEL := preload("res://assets/arca/arca.glb")
const Piezas := preload("res://scripts/piezas.gd")

## Obra alrededor del arca (coordenadas locales: x a lo largo, +z el costado de la puerta, que mira
## al sur). El camino de la aldea llega por el oeste (-x): ahí está el toldo para descansar; el
## taller va junto a la puerta; el andamio, pegado al casco; la brea se calienta al este, cerca de
## los pozos. [pieza, posición, giro en grados]
const SITE := [
	["Toldo", Vector3(-14.5, 0, 4.5), 20.0],
	["Banco", Vector3(-14.8, 0, 4.0), 15.0],
	["Cantaro", Vector3(-13.4, 0, 3.6), 0.0],
	["Cantaro", Vector3(-13.0, 0, 4.1), 40.0],
	["Cesta", Vector3(-15.8, 0, 3.4), 0.0],
	["MesaTrabajo", Vector3(-4.5, 0, 6.0), -6.0],
	["Caballete", Vector3(-1.0, 0, 7.2), 12.0],
	["Caballete", Vector3(2.4, 0, 6.6), -8.0],
	["Tablones", Vector3(6.2, 0, 6.8), 4.0],
	["Tablones", Vector3(6.4, 0, 8.0), -3.0],
	["Andamio", Vector3(-6.5, 0, 4.4), 0.0],
	["Andamio", Vector3(4.0, 0, -4.4), 180.0],
	["OllaBrea", Vector3(13.5, 0, 5.2), 0.0],
	["Cantaro", Vector3(14.6, 0, 4.4), 0.0],
	["Saco", Vector3(-3.2, 0, 7.4), 30.0],
	["Saco", Vector3(-2.7, 0, 7.9), 80.0],
]

const L := 22.0   ## Largo del arca (eje X).
const W := 5.8    ## Ancho máximo (eje Z).

## Color de cada material del modelo de Blender.
const WOOD_COLORS := {
	"Casco": Color("a47148"),
	"Viga": Color("6e4628"),
	"Cubierta": Color("bf8a58"),
	"Pared": Color("a8774c"),
	"Techo": Color("7a4a2a"),
	"Puerta": Color("5e3b22"),
	"Ventana": Color("1a120c"),
}
const PITCH := Color("3a2a20")
const WOOD_DARK := Color("6e4628")
const WOOD_LIGHT := Color("bf8a58")
const WOOD := Color("a47148")
const STONE := Color("8e8d88")
const GHOST := Color(1.0, 0.97, 0.88, 0.2)

var _stages: Array[MeshInstance3D] = []
var _ghosts: Array[MeshInstance3D] = []
var _bodies: Array[CollisionShape3D] = []


func _ready() -> void:
	add_to_group("interactuable")
	_build_site_props()

	var model := ARK_MODEL.instantiate()
	add_child(model)
	var ghost_model := ARK_MODEL.instantiate()
	add_child(ghost_model)
	var ghost_mat := StandardMaterial3D.new()
	ghost_mat.albedo_color = GHOST
	ghost_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	ghost_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED

	for i in 5:
		var stage := model.find_child("Etapa%d" % (i + 1)) as MeshInstance3D
		var ghost := ghost_model.find_child("Etapa%d" % (i + 1)) as MeshInstance3D
		_stages.append(stage)
		_ghosts.append(ghost)
		if stage == null:
			_bodies.append(null)
			continue
		_apply_materials(stage, false)
		ghost.material_override = ghost_mat
		ghost.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		# Colisión con la forma real: se puede subir por la rampa hasta la puerta.
		var body := StaticBody3D.new()
		var col := CollisionShape3D.new()
		col.shape = stage.mesh.create_trimesh_shape()
		body.add_child(col)
		stage.add_child(body)
		_bodies.append(col)

	_refresh(false)
	Game.ark_stage_changed.connect(func(_stage: int) -> void: _refresh(true))


# --- Interacción --------------------------------------------------------------

func interact_distance(from: Vector3) -> float:
	var local := to_local(from)
	var dx := maxf(absf(local.x) - L * 0.5, 0.0)
	var dz := maxf(absf(local.z) - W * 0.5, 0.0)
	return Vector2(dx, dz).length()


func get_prompt() -> String:
	if Game.ark_complete():
		return "El arca está terminada"
	var stage := Game.next_ark_stage()
	var text := "Construir: %s (%s)" % [stage["nombre"], Game.requirements_text(stage["materiales"])]
	if not Game.has_item("martillo"):
		text += " · necesitas martillo"
	return text


func interact(_player: Node) -> void:
	if Game.ark_complete():
		Game.notify.emit("Ahora toca reunir a los animales... (próximamente)")
		return
	Game.build_ark_stage()


# --- Visuales -----------------------------------------------------------------

func _refresh(animate: bool) -> void:
	var built := Game.ark_stage
	for i in _stages.size():
		if _stages[i] == null:
			continue
		_stages[i].visible = i < built
		_ghosts[i].visible = i == built
		_bodies[i].disabled = i >= built
	# Etapa 3: el casco queda sellado con brea.
	if _stages[1]:
		_apply_materials(_stages[1], built >= 3)
	if animate and built > 0:
		Effects.dust(self, Vector3(0, 0.6, 0), L * 0.5, 40)
		var stage := _stages[built - 1]
		if stage:
			stage.scale = Vector3(1, 0.01, 1)
			create_tween().tween_property(stage, "scale", Vector3.ONE, 0.8) \
					.set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)


## Sustituye los materiales de Blender por la madera del juego (con la veta del shader
## y la variación de tono de cada tablón, que viene en el color de vértice).
func _apply_materials(mi: MeshInstance3D, sealed: bool) -> void:
	for s in mi.mesh.get_surface_count():
		var source := mi.mesh.surface_get_material(s)
		var mat_name := source.resource_name if source else ""
		if mat_name == "Piedra" or not WOOD_COLORS.has(mat_name):
			continue
		var color: Color = WOOD_COLORS[mat_name]
		if sealed and mat_name == "Casco":
			color = PITCH
		mi.set_surface_override_material(s, Models.wood(color, false))


func _build_site_props() -> void:
	for entry in SITE:
		var piece: Node3D = Piezas.make(entry[0])
		piece.position = entry[1]
		piece.rotation.y = deg_to_rad(entry[2])
		add_child(piece)
		if entry[0] in ["Saco", "Cesta", "Cantaro"]:
			piece.scale = Vector3.ONE * (1.0 if entry[0] == "Cantaro" else 0.6)   # A escala de la obra.
		if entry[0] in ["Toldo", "MesaTrabajo", "Caballete", "Tablones", "Andamio", "OllaBrea"]:
			var body := StaticBody3D.new()
			var col := CollisionShape3D.new()
			col.shape = (piece as MeshInstance3D).mesh.create_convex_shape()
			body.add_child(col)
			piece.add_child(body)
	# Cartel de la obra.
	var sign_pos := Vector3(-L * 0.5 - 4.0, 0, -0.8)        # Donde llega el camino de la aldea.
	_wood_part(LowPoly.box(self, Vector3(0.15, 1.6, 0.15), WOOD_DARK, sign_pos + Vector3(0, 0.8, 0)))
	_wood_part(LowPoly.box(self, Vector3(1.3, 0.7, 0.08), WOOD_LIGHT, sign_pos + Vector3(0, 1.4, 0)))
	# Pila de troncos.
	var logs := Vector3(-L * 0.5 - 1.5, 0, -W * 0.5 - 2.6)
	for i in 3:
		_wood_part(LowPoly.cylinder(self, 0.25, 0.25, 2.2, 6, WOOD, logs + Vector3(0, 0.25, i * 0.52), Vector3(0, 0, 90)))
	_wood_part(LowPoly.cylinder(self, 0.25, 0.25, 2.2, 6, WOOD_LIGHT, logs + Vector3(0, 0.68, 0.26), Vector3(0, 0, 90)))
	_wood_part(LowPoly.cylinder(self, 0.25, 0.25, 2.2, 6, WOOD_LIGHT, logs + Vector3(0, 0.68, 0.78), Vector3(0, 0, 90)))


func _wood_part(mi: MeshInstance3D) -> void:
	mi.material_override = Models.wood((mi.material_override as StandardMaterial3D).albedo_color)
