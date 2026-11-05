extends RefCounted
## Village pieces by name. If there is a generated version (Hunyuan3D, processed with
## tools/blender/process_generated.py → assets/village/generated.glb) that one is used; if not, the
## one made by script (tools/blender/houses.py → assets/village/village.glb).

const VILLAGE := preload("res://assets/village/village.glb")
const GENERATED := preload("res://assets/village/generated.glb")
const PROPS_SHADER := preload("res://shaders/props.gdshader")
const WATER_SHADER := preload("res://shaders/still_water.gdshader")

## Generated pieces with no wood (clay, cloth, stone): no grain.
const NO_WOOD := ["oven", "jugs", "sacks", "baskets"]
## Materials of the scripted pieces that are wood (they get grain in the game).
const WOODS := ["Wood", "WoodDark", "Bark"]
## Water materials of the scripted pieces (trough, well): water with highlights and a light edge.
const WATERS := ["TroughWater", "WellWater"]

## Name of the scripted piece → name of the generated one that replaces it. Only single-material ones
## (wood, clay, cloth): the ones that mix materials (well, campfire, baskets, trough, loom) look better
## modeled by script, piece by piece.
const REPLACEMENTS := {
	"Oven": "oven", "Bench": "bench", "Table": "table", "Fence": "fence",
	"Clothesline": "clothesline", "Sack": "sacks", "Jug": "jugs", "Stall": "pottery_stall", "Campfire": "campfire",
}

static var _scripted: Dictionary = {}
static var _generated: Dictionary = {}
static var _wood_material: ShaderMaterial
static var _plain_material: ShaderMaterial
static var _textured: Dictionary = {}
static var _grain: Dictionary = {}


## New copy of a piece (by its script name or directly the generated one's).
static func make(piece: String) -> Node3D:
	if _scripted.is_empty():
		_load()
	var key: String = REPLACEMENTS.get(piece, piece)
	if _generated.has(key):
		var node: MeshInstance3D = _generated[key].duplicate()
		node.material_override = _material_for(key, node)
		return node
	var node: Node3D = _scripted[piece].duplicate()
	_scripted_materials(node)
	return node


## Scripted pieces: wood uses the same shader as the generated ones (grain and a shared brown), so it
## doesn't look smoother and lighter than the bench or table next to it; water uses the still-water one.
static func _scripted_materials(node: Node3D) -> void:
	var mi := node as MeshInstance3D
	if mi == null:
		return
	for i in mi.mesh.get_surface_count():
		var src := mi.mesh.surface_get_material(i) as BaseMaterial3D
		if src == null or src.resource_name not in WOODS + WATERS:
			continue
		if not _grain.has(src.resource_name) and src.resource_name in WATERS:
			var w := ShaderMaterial.new()
			w.shader = WATER_SHADER
			if src.resource_name == "WellWater":     # Deep, shaded well: darker.
				w.set_shader_parameter("deep_color", Color(0.10, 0.22, 0.30))
				w.set_shader_parameter("shallow_color", Color(0.26, 0.45, 0.52))
			_grain[src.resource_name] = w
		elif not _grain.has(src.resource_name):
			var m := ShaderMaterial.new()
			m.shader = PROPS_SHADER
			m.set_shader_parameter("use_flat_color", true)
			m.set_shader_parameter("flat_color", src.albedo_color)
			_grain[src.resource_name] = m
		mi.set_surface_override_material(i, _grain[src.resource_name])


## Material of a generated piece: textured if it has one (painted with a material map), otherwise the
## vertex-color one, with or without wood grain.
static func _material_for(key: String, node: MeshInstance3D) -> Material:
	var src := node.mesh.surface_get_material(0) as BaseMaterial3D
	if src and src.albedo_texture:
		if not _textured.has(key):
			var m := ShaderMaterial.new()
			m.shader = PROPS_SHADER
			m.set_shader_parameter("use_texture", true)
			m.set_shader_parameter("albedo_tex", src.albedo_texture)
			_textured[key] = m
		return _textured[key]
	return _plain_material if key in NO_WOOD else _wood_material


static func _load() -> void:
	var a := VILLAGE.instantiate()
	for child in a.get_children():
		a.remove_child(child)
		_scripted[String(child.name)] = child
	a.free()
	var g := GENERATED.instantiate()
	for child in g.get_children():
		g.remove_child(child)
		_generated[String(child.name)] = child
	g.free()
	# The generated ones have the color painted on the vertices; wood gets grain (shaders/props.gdshader).
	_wood_material = ShaderMaterial.new()
	_wood_material.shader = PROPS_SHADER
	_plain_material = ShaderMaterial.new()
	_plain_material.shader = PROPS_SHADER
	_plain_material.set_shader_parameter("wood", 0.0)
