extends RefCounted
## Vegetación y rocas con el estilo de la referencia (referencias/arboles.webp y rocas_terreno.png):
## árboles redondos con espiral, pinos por capas, arbustos de bolitas, flores de cinco pétalos, matas
## de hierba y rocas facetadas lilas. Cada pieza se junta en una sola malla con color por vértice
## (una llamada de dibujo) y se guarda por variante para reutilizarla.

const PLANT_SHADER := preload("res://shaders/toon_plant.gdshader")
const LowPoly := preload("res://scripts/lowpoly.gd")

const TRUNK := Color("8f6a4a")
const LEAF := [Color("6aa847"), Color("76b04f"), Color("5f9a3f")]
const LEAF_SWIRL := Color("4b7f33")
const PINE := [Color("4b8a48"), Color("427d40")]
const BUSH := [Color("67a044"), Color("58903c")]
const BLADE := Color("64a442")
const BLADE_TIP := Color("98cb63")
const FLOWERS := [Color("b9a3d9"), Color("f2b8c6"), Color("e98f80"), Color("f3c27a"), Color("f7f1e3")]
const FLOWER_CENTER := Color("f2cf5b")
const ROCK := Color("aaa2b6")
const OLIVE_TRUNK := Color("8a7660")
const WHEAT_STEM := Color("c9b16a")
const LETTUCE := Color("8cc45a")
const ONION := Color("efe4cf")
const SQUASH := Color("e8a046")
const WHEAT_HEAD := Color("e6cf86")
const OLIVE_LEAF := Color("88a66a")

const VARIANTS := 4

static var _meshes: Dictionary = {}
static var _materials: Dictionary = {}


## Árbol redondo: copa de capas como un helado, con una bola lateral con espiral.
static func round_tree(rng: RandomNumberGenerator) -> Node3D:
	return _instance("arbol_%d" % rng.randi_range(0, VARIANTS - 1), _build_round_tree, 3.2, 0.03)


static func pine(rng: RandomNumberGenerator) -> Node3D:
	return _instance("pino_%d" % rng.randi_range(0, VARIANTS - 1), _build_pine, 4.0, 0.03)


static func bush(rng: RandomNumberGenerator) -> Node3D:
	return _instance("arbusto_%d" % rng.randi_range(0, VARIANTS - 1), _build_bush, 0.8, 0.03)


static func flower(rng: RandomNumberGenerator) -> Node3D:
	return flower_of(rng.randi_range(0, FLOWERS.size() - 1))


## Flor de un color concreto de FLOWERS (para macizos de un solo color).
static func flower_of(color: int) -> Node3D:
	return _instance("flor_%d" % color, _build_flower, 0.3, 0.05)


## Olivo: tronco retorcido y copa ancha de bolas aplanadas verde salvia (el árbol de la plaza).
static func olive(rng: RandomNumberGenerator) -> Node3D:
	return _instance("olivo_%d" % rng.randi_range(0, VARIANTS - 1), _build_olive, 3.0, 0.025)


## Mata de hierba alta (decoración y juncos).
static func tuft(rng: RandomNumberGenerator) -> Node3D:
	return _instance("mata_%d" % rng.randi_range(0, VARIANTS - 1), _build_tuft, 0.6, 0.08)


static func rock(rng: RandomNumberGenerator) -> Node3D:
	var node := MeshInstance3D.new()
	node.mesh = mesh("roca_%d" % rng.randi_range(0, VARIANTS - 1), _build_rock)
	node.material_override = material(0.0, 1.0, 0.95)
	return node


## Malla de una variante (la crea la primera vez). El número final del nombre es la semilla.
static func mesh(key: String, builder: Callable) -> ArrayMesh:
	if not _meshes.has(key):
		var rng := RandomNumberGenerator.new()
		var variant := int(key.get_slice("_", 1))
		rng.seed = hash(key)
		var st := SurfaceTool.new()
		st.begin(Mesh.PRIMITIVE_TRIANGLES)
		builder.call(st, rng, variant)
		_meshes[key] = st.commit()
	return _meshes[key]


static func material(wind: float, sway_height: float, roughness := 0.9) -> ShaderMaterial:
	var key := "%.3f|%.2f|%.2f" % [wind, sway_height, roughness]
	if not _materials.has(key):
		var m := ShaderMaterial.new()
		m.shader = PLANT_SHADER
		m.set_shader_parameter("wind_strength", wind)
		m.set_shader_parameter("sway_height", sway_height)
		m.set_shader_parameter("roughness", roughness)
		_materials[key] = m
	return _materials[key]


static func _instance(key: String, builder: Callable, sway_height: float, wind: float) -> Node3D:
	var node := MeshInstance3D.new()
	node.mesh = mesh(key, builder)
	node.material_override = material(wind, sway_height)
	return node


# --- Piezas -------------------------------------------------------------------

## Añade una malla primitiva a la malla final, transformada y de un color. flat = caras facetadas.
static func add(st: SurfaceTool, prim: PrimitiveMesh, xform: Transform3D, color: Color, flat := false,
		jitter := 0.0, rng: RandomNumberGenerator = null) -> void:
	var arrays := prim.get_mesh_arrays()
	var verts: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	var lin := color.srgb_to_linear()
	var nb := xform.basis.inverse().transposed()
	if jitter > 0.0:
		# Mismo desplazamiento para vértices en la misma posición (las costuras no se abren).
		var offsets := {}
		for i in verts.size():
			var k := verts[i].snapped(Vector3.ONE * 0.001)
			if not offsets.has(k):
				offsets[k] = Vector3(rng.randf_range(-1, 1), rng.randf_range(-1, 1), rng.randf_range(-1, 1)) * jitter
			verts[i] += offsets[k]
	for t in indices.size() / 3:
		var a := xform * verts[indices[t * 3]]
		var b := xform * verts[indices[t * 3 + 1]]
		var c := xform * verts[indices[t * 3 + 2]]
		var fn := LowPoly.face_normal(a, b, c)
		if flat and fn == Vector3.ZERO:
			continue
		for k in 3:
			var idx := indices[t * 3 + k]
			st.set_color(lin)
			st.set_normal(fn if flat else (nb * normals[idx]).normalized())
			st.add_vertex([a, b, c][k])


static func sphere(radius: float, segments := 14, rings := 8) -> SphereMesh:
	var m := SphereMesh.new()
	m.radius = radius
	m.height = radius * 2.0
	m.radial_segments = segments
	m.rings = rings
	return m


static func cone(bottom: float, top: float, height: float, sides: int) -> CylinderMesh:
	var m := CylinderMesh.new()
	m.bottom_radius = bottom
	m.top_radius = top
	m.height = height
	m.radial_segments = sides
	m.rings = 1
	return m


static func _at(pos: Vector3, scale := Vector3.ONE, rot := Vector3.ZERO) -> Transform3D:
	return Transform3D(Basis.from_euler(rot).scaled(scale), pos)


static func _build_round_tree(st: SurfaceTool, rng: RandomNumberGenerator, _variant: int) -> void:
	var height := rng.randf_range(1.6, 2.1)
	var leaf: Color = LEAF[rng.randi_range(0, LEAF.size() - 1)]
	add(st, cone(0.17, 0.11, height + 0.4, 8), _at(Vector3(0, (height + 0.4) * 0.5, 0)), TRUNK)
	var side := -1.0 if rng.randf() < 0.5 else 1.0
	# Rama hacia la bola lateral.
	add(st, cone(0.08, 0.06, 0.7, 6), _at(Vector3(0.25 * side, height - 0.15, 0), Vector3.ONE,
			Vector3(0, 0, -0.9 * side)), TRUNK)
	# Copa en capas, cada una algo menor y más arriba (el "helado" de la referencia).
	var r := rng.randf_range(1.0, 1.15)
	var y := height + 0.55
	for i in 4:
		var ri: float = r * [1.0, 0.86, 0.66, 0.4][i]
		add(st, sphere(ri), _at(Vector3(0.05 * i * side, y, 0), Vector3(1, 0.62, 1)),
				leaf.lightened(0.03 * i))
		y += ri * 0.5
	# Bola lateral con espiral mirando hacia afuera.
	var ball := Vector3(0.75 * side, height + 0.15, 0.15)
	var br := r * 0.68
	add(st, sphere(br), _at(ball), leaf.darkened(0.04))
	var out := Vector3(side, 0.05, 0.55).normalized()
	var basis := Basis(Quaternion(Vector3.UP, out))
	for ring in [[0.5, 0.66], [0.2, 0.34]]:
		var torus := TorusMesh.new()
		torus.inner_radius = br * ring[0]
		torus.outer_radius = br * ring[1]
		torus.rings = 16
		torus.ring_segments = 8
		var depth: float = sqrt(maxf(0.0, 1.0 - pow((ring[0] + ring[1]) * 0.5, 2.0))) * br
		add(st, torus, Transform3D(basis.scaled(Vector3(1, 0.6, 1)), ball + out * (depth + br * 0.02)), LEAF_SWIRL)


static func _build_olive(st: SurfaceTool, rng: RandomNumberGenerator, _variant: int) -> void:
	var lean := rng.randf_range(0.15, 0.3)
	add(st, cone(0.26, 0.2, 1.1, 8), _at(Vector3(0.1, 0.5, 0), Vector3.ONE, Vector3(0, 0, -lean)), OLIVE_TRUNK)
	add(st, cone(0.2, 0.14, 1.2, 8), _at(Vector3(0.05, 1.45, 0), Vector3.ONE, Vector3(0.1, 0, lean * 1.4)), OLIVE_TRUNK)
	add(st, cone(0.12, 0.08, 1.0, 6), _at(Vector3(0.45, 1.6, 0.1), Vector3.ONE, Vector3(0, 0, -0.9)), OLIVE_TRUNK)
	for i in 6:
		var a := TAU * i / 6.0 + rng.randf_range(-0.3, 0.3)
		var d := rng.randf_range(0.5, 1.0)
		var r := rng.randf_range(0.65, 0.85)
		add(st, sphere(r), _at(Vector3(cos(a) * d, 2.3 + rng.randf_range(-0.15, 0.3), sin(a) * d), Vector3(1, 0.55, 1)),
				OLIVE_LEAF.lightened(rng.randf_range(-0.04, 0.06)))
	add(st, sphere(0.8), _at(Vector3(0, 2.65, 0), Vector3(1, 0.6, 1)), OLIVE_LEAF.lightened(0.05))


static func _build_pine(st: SurfaceTool, rng: RandomNumberGenerator, _variant: int) -> void:
	var green: Color = PINE[rng.randi_range(0, PINE.size() - 1)]
	var s := rng.randf_range(0.9, 1.1)
	add(st, cone(0.2, 0.16, 0.9, 8), _at(Vector3(0, 0.45, 0)), TRUNK.darkened(0.1))
	var y := 0.65
	var tiers := [[1.25, 1.2], [1.0, 1.1], [0.75, 1.0], [0.48, 0.95]]
	for i in tiers.size():
		var t: Array = tiers[i]
		var h: float = t[1] * s
		add(st, cone(t[0] * s, 0.0, h, 10), _at(Vector3(0, y + h * 0.5, 0), Vector3.ONE,
				Vector3(0, rng.randf() * TAU, 0)), green.lightened(0.04 * i), true)
		y += h * 0.55
	# Remate en punta.
	add(st, cone(0.22 * s, 0.0, 0.6 * s, 8), _at(Vector3(0, y + 0.3 * s, 0)), green.lightened(0.18), true)


static func _build_bush(st: SurfaceTool, rng: RandomNumberGenerator, _variant: int) -> void:
	var green: Color = BUSH[rng.randi_range(0, BUSH.size() - 1)]
	for i in 11:
		var a := rng.randf() * TAU
		var d := rng.randf_range(0.0, 0.42)
		var r := rng.randf_range(0.2, 0.3)
		var p := Vector3(cos(a) * d, r * 0.7 + (0.42 - d) * 0.55, sin(a) * d)
		add(st, sphere(r, 10, 6), _at(p), green.lightened(rng.randf_range(-0.04, 0.08)))


static func _build_flower(st: SurfaceTool, _rng: RandomNumberGenerator, variant: int) -> void:
	var color: Color = FLOWERS[variant]
	add(st, cone(0.015, 0.012, 0.22, 5), _at(Vector3(0, 0.11, 0)), BLADE)
	for i in 5:
		var a := TAU * i / 5.0
		add(st, sphere(0.065, 8, 4), _at(Vector3(cos(a) * 0.07, 0.23, sin(a) * 0.07), Vector3(1, 0.35, 0.75),
				Vector3(0, -a, 0)), color)
	add(st, sphere(0.04, 8, 4), _at(Vector3(0, 0.245, 0), Vector3(1, 0.6, 1)), FLOWER_CENTER)


## Espiga de trigo: tallos dorados con su espiga (los campos de village.gd).
static func build_wheat(st: SurfaceTool, rng: RandomNumberGenerator, _variant: int) -> void:
	for i in 5:
		var a := TAU * i / 5.0 + rng.randf_range(-0.4, 0.4)
		var h := rng.randf_range(0.55, 0.75)
		var lean := rng.randf_range(0.05, 0.2)
		var dir := Vector3(cos(a), 0, sin(a))
		var rot := Basis(dir.cross(Vector3.UP).normalized(), -lean)
		add(st, cone(0.012, 0.008, h, 3), Transform3D(rot, dir * 0.03 + rot * Vector3(0, h * 0.5, 0)), WHEAT_STEM, true)
		add(st, sphere(0.035, 6, 4), Transform3D(rot.scaled(Vector3(1, 2.6, 1)), dir * 0.03 + rot * Vector3(0, h + 0.05, 0)),
				WHEAT_HEAD)


## Hortalizas del huerto (village.gd): lechuga, cebolla y calabaza.
static func build_lettuce(st: SurfaceTool, rng: RandomNumberGenerator, _variant: int) -> void:
	for i in 6:
		var a := TAU * i / 6.0
		add(st, sphere(0.09, 8, 5), _at(Vector3(cos(a) * 0.07, 0.07, sin(a) * 0.07), Vector3(1, 0.7, 1)),
				LETTUCE.lightened(rng.randf_range(-0.03, 0.06)))
	add(st, sphere(0.08, 8, 5), _at(Vector3(0, 0.12, 0)), LETTUCE.lightened(0.12))


static func build_onion(st: SurfaceTool, rng: RandomNumberGenerator, _variant: int) -> void:
	add(st, sphere(0.07, 8, 5), _at(Vector3(0, 0.05, 0), Vector3(1, 0.85, 1)), ONION)
	for i in 3:
		var lean := Basis(Vector3.RIGHT.rotated(Vector3.UP, TAU * i / 3.0), 0.25)
		add(st, cone(0.015, 0.0, 0.32, 3), Transform3D(lean, Vector3(0, 0.08, 0) + lean * Vector3(0, 0.16, 0)),
				BLADE.lerp(BLADE_TIP, rng.randf() * 0.4), true)


static func build_squash(st: SurfaceTool, rng: RandomNumberGenerator, _variant: int) -> void:
	add(st, sphere(0.13, 10, 6), _at(Vector3(0, 0.09, 0), Vector3(1.1, 0.7, 1)), SQUASH)
	add(st, cone(0.02, 0.015, 0.06, 5), _at(Vector3(0, 0.18, 0)), TRUNK)
	for i in 3:
		var a := TAU * i / 3.0 + rng.randf()
		add(st, sphere(0.1, 8, 4), _at(Vector3(cos(a) * 0.18, 0.03, sin(a) * 0.18), Vector3(1, 0.25, 0.8),
				Vector3(0, -a, 0)), BUSH[0])


static func _build_tuft(st: SurfaceTool, rng: RandomNumberGenerator, _variant: int) -> void:
	tuft_blades(st, rng, 7, 0.55)


## Hojas de una mata: conos finos de 3 lados, inclinados hacia afuera, con la punta más clara.
static func tuft_blades(st: SurfaceTool, rng: RandomNumberGenerator, count: int, height: float) -> void:
	for i in count:
		var a := TAU * i / count + rng.randf_range(-0.3, 0.3)
		var h := height * rng.randf_range(0.6, 1.0)
		var lean := rng.randf_range(0.15, 0.45)
		var dir := Vector3(cos(a), 0, sin(a))
		var rot := Basis(dir.cross(Vector3.UP).normalized(), -lean)
		var base := dir * 0.04
		add(st, cone(0.035, 0.0, h, 3), Transform3D(rot, base + rot * Vector3(0, h * 0.5, 0)),
				BLADE.lerp(BLADE_TIP, rng.randf() * 0.5), true)


static func _build_rock(st: SurfaceTool, rng: RandomNumberGenerator, _variant: int) -> void:
	var s := sphere(0.75, 9, 5)
	var tmp := SurfaceTool.new()
	tmp.begin(Mesh.PRIMITIVE_TRIANGLES)
	add(tmp, s, _at(Vector3(0, 0.3, 0), Vector3(rng.randf_range(1.0, 1.3), 0.8, rng.randf_range(0.85, 1.1))),
			ROCK, true, 0.12, rng)
	# Cada cara con un tono algo distinto (lila, gris, verdoso), como en la referencia.
	var built := tmp.commit_to_arrays()
	var verts: PackedVector3Array = built[Mesh.ARRAY_VERTEX]
	var normals: PackedVector3Array = built[Mesh.ARRAY_NORMAL]
	for t in verts.size() / 3:
		var tint: Color = ROCK.lerp([Color("b8aec6"), Color("9c97aa"), Color("a8b0a6")][rng.randi_range(0, 2)], 0.5)
		tint = tint.lightened(rng.randf_range(-0.05, 0.08))
		for k in 3:
			var v := verts[t * 3 + k]
			st.set_color(tint.srgb_to_linear())
			st.set_normal(normals[t * 3 + k])
			st.add_vertex(Vector3(v.x, maxf(v.y, 0.0), v.z))   # Base plana, apoyada en el suelo.
