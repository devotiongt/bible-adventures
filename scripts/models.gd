extends RefCounted
## Carga de modelos de Quaternius (CC0) y materiales compartidos:
## viento en hojas y hierba, madera procedural para el arca.

const FOLIAGE_SHADER := preload("res://shaders/foliage.gdshader")
const WOOD_SHADER := preload("res://shaders/wood.gdshader")

const NATURE := "res://assets/naturaleza/%s.gltf"
const ANIMALS := "res://assets/animales/%s.gltf"

## Texturas de follaje: lo que use una de estas se balancea con el viento.
const FOLIAGE_TEXTURES := ["Leaves", "Leaf_", "Grass", "Flowers"]

static var _scenes: Dictionary = {}
static var _foliage: Dictionary = {}
static var _wood: Dictionary = {}


static func scene(path: String) -> PackedScene:
	if not _scenes.has(path):
		_scenes[path] = load(path)
	return _scenes[path]


## Instancia un modelo de naturaleza con el viento ya aplicado a sus hojas.
static func nature(model: String, sway_height := 4.0, wind := 0.06) -> Node3D:
	var node: Node3D = scene(NATURE % model).instantiate()
	apply_wind(node, sway_height, wind)
	return node


static func apply_wind(node: Node, sway_height: float, wind: float) -> void:
	for mi in node.find_children("*", "MeshInstance3D", true, false):
		var mesh: Mesh = (mi as MeshInstance3D).mesh
		for s in mesh.get_surface_count():
			var mat := mesh.surface_get_material(s) as BaseMaterial3D
			if mat and is_foliage(mat):
				(mi as MeshInstance3D).set_surface_override_material(s, foliage_material(mat, sway_height, wind))


static func is_foliage(mat: BaseMaterial3D) -> bool:
	if mat.albedo_texture == null:
		return false
	var file := mat.albedo_texture.resource_path.get_file()
	for prefix in FOLIAGE_TEXTURES:
		if file.begins_with(prefix):
			return true
	return false


static func foliage_material(source: BaseMaterial3D, sway_height: float, wind: float) -> ShaderMaterial:
	var key := "%s|%.2f|%.3f" % [source.albedo_texture.resource_path, sway_height, wind]
	if not _foliage.has(key):
		var m := ShaderMaterial.new()
		m.shader = FOLIAGE_SHADER
		m.set_shader_parameter("albedo_tex", source.albedo_texture)
		m.set_shader_parameter("albedo", source.albedo_color)
		m.set_shader_parameter("sway_height", sway_height)
		m.set_shader_parameter("wind_strength", wind)
		_foliage[key] = m
	return _foliage[key]


## Primer MeshInstance3D de un modelo (para MultiMesh de hierba, etc.).
static func first_mesh(model: String) -> MeshInstance3D:
	var node: Node3D = scene(NATURE % model).instantiate()
	var mi: MeshInstance3D = node.find_children("*", "MeshInstance3D", true, false)[0]
	mi.get_parent().remove_child(mi)
	node.free()
	return mi


static func wood(color: Color, seams := true) -> ShaderMaterial:
	var key := "%s|%s" % [color.to_html(), seams]
	if not _wood.has(key):
		var m := ShaderMaterial.new()
		m.shader = WOOD_SHADER
		m.set_shader_parameter("base_color", color)
		m.set_shader_parameter("seams", seams)
		_wood[key] = m
	return _wood[key]
