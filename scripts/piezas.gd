extends RefCounted
## Piezas de la aldea por su nombre. Si hay versión generada (Hunyuan3D, procesada con
## herramientas/blender/procesar_generados.py → assets/aldea/generados.glb) se usa esa; si no, la
## hecha por script (herramientas/blender/casas.py → assets/aldea/aldea.glb).

const ALDEA := preload("res://assets/aldea/aldea.glb")
const GENERADOS := preload("res://assets/aldea/generados.glb")
const PROPS_SHADER := preload("res://shaders/props.gdshader")
const AGUA_SHADER := preload("res://shaders/agua_quieta.gdshader")

## Piezas generadas sin madera (barro, tela, piedra): no llevan veta.
const SIN_MADERA := ["horno", "cantaros", "sacos", "cestas"]
## Materiales de las piezas por script que son madera (llevan veta en el juego).
const MADERAS := ["Madera", "MaderaOscura", "Corteza"]
## Materiales de agua de las piezas por script (abrevadero, pozo): agua con brillos y borde claro.
const AGUAS := ["AguaBebedero", "AguaPozo"]

## Nombre de la pieza por script → nombre de la generada que la sustituye. Solo los de un solo material
## (madera, barro, tela): los que mezclan materiales (pozo, fogata, cestas, bebedero, telar) se ven mejor
## modelados por script, pieza a pieza.
const REEMPLAZOS := {
	"Horno": "horno", "Banco": "banco", "Mesa": "mesa", "Cerca": "cerca",
	"Tendedero": "tendedero", "Saco": "sacos", "Cantaro": "cantaros", "Puesto": "puesto_ceramica", "Fogata": "fogata",
}

static var _scripted: Dictionary = {}
static var _generated: Dictionary = {}
static var _wood_material: ShaderMaterial
static var _plain_material: ShaderMaterial
static var _textured: Dictionary = {}
static var _grain: Dictionary = {}


## Copia nueva de una pieza (por su nombre de script o directamente el de la generada).
static func make(piece: String) -> Node3D:
	if _scripted.is_empty():
		_load()
	var key: String = REEMPLAZOS.get(piece, piece)
	if _generated.has(key):
		var node: MeshInstance3D = _generated[key].duplicate()
		node.material_override = _material_for(key, node)
		return node
	var node: Node3D = _scripted[piece].duplicate()
	_scripted_materials(node)
	return node


## Piezas por script: la madera usa el mismo shader que los generados (veta y café común), para que no
## se vea más lisa y clara que el banco o la mesa de al lado; el agua, el de agua quieta.
static func _scripted_materials(node: Node3D) -> void:
	var mi := node as MeshInstance3D
	if mi == null:
		return
	for i in mi.mesh.get_surface_count():
		var src := mi.mesh.surface_get_material(i) as BaseMaterial3D
		if src == null or src.resource_name not in MADERAS + AGUAS:
			continue
		if not _grain.has(src.resource_name) and src.resource_name in AGUAS:
			var w := ShaderMaterial.new()
			w.shader = AGUA_SHADER
			if src.resource_name == "AguaPozo":     # Pozo hondo y en sombra: más oscuro.
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


## Material de una pieza generada: con textura si la trae (pintada con mapa de materiales), si no el
## de color por vértice, con o sin veta de madera.
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
	return _plain_material if key in SIN_MADERA else _wood_material


static func _load() -> void:
	var a := ALDEA.instantiate()
	for child in a.get_children():
		a.remove_child(child)
		_scripted[String(child.name)] = child
	a.free()
	var g := GENERADOS.instantiate()
	for child in g.get_children():
		g.remove_child(child)
		_generated[String(child.name)] = child
	g.free()
	# Los generados traen el color pintado en los vértices; la madera lleva veta (shaders/props.gdshader).
	_wood_material = ShaderMaterial.new()
	_wood_material.shader = PROPS_SHADER
	_plain_material = ShaderMaterial.new()
	_plain_material.shader = PROPS_SHADER
	_plain_material.set_shader_parameter("wood", 0.0)
