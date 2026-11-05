extends RefCounted
## Loading of Quaternius models (CC0) and shared materials:
## wind on leaves and grass, procedural wood for the ark.

const FOLIAGE_SHADER := preload("res://shaders/foliage.gdshader")
const WOOD_SHADER := preload("res://shaders/wood.gdshader")

const NATURE := "res://assets/nature/%s.gltf"
const ANIMALS := "res://assets/animals/%s.gltf"

## Foliage textures: anything using one of these sways in the wind.
const FOLIAGE_TEXTURES := ["Leaves", "Leaf_", "Grass", "Flowers"]

static var _scenes: Dictionary = {}
static var _foliage: Dictionary = {}
static var _wood: Dictionary = {}


static func scene(path: String) -> PackedScene:
	if not _scenes.has(path):
		_scenes[path] = load(path)
	return _scenes[path]


## Instances a nature model with the wind already applied to its leaves.
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


## First MeshInstance3D of a model (for grass MultiMesh, etc.).
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
