extends RefCounted
## Helpers for building low poly pieces with flat shading (faceted faces).

static var _materials: Dictionary = {}


static func material(color: Color) -> StandardMaterial3D:
	var key := color.to_html()
	if not _materials.has(key):
		var m := StandardMaterial3D.new()
		m.albedo_color = color
		m.roughness = 0.95
		if color.a < 1.0:
			m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		_materials[key] = m
	return _materials[key]


## Turns a mesh into one with no shared vertices, with one normal per face.
static func flat(src: Mesh) -> ArrayMesh:
	var arrays := src.surface_get_arrays(0)
	var verts: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var indices := PackedInt32Array()
	if arrays[Mesh.ARRAY_INDEX] != null:
		indices = arrays[Mesh.ARRAY_INDEX]
	var indexed := indices.size() > 0
	var tri_count := int((indices.size() if indexed else verts.size()) / 3.0)

	var out_v := PackedVector3Array()
	var out_n := PackedVector3Array()
	for t in tri_count:
		var a := verts[indices[t * 3]] if indexed else verts[t * 3]
		var b := verts[indices[t * 3 + 1]] if indexed else verts[t * 3 + 1]
		var c := verts[indices[t * 3 + 2]] if indexed else verts[t * 3 + 2]
		var n := face_normal(a, b, c)
		if n == Vector3.ZERO:
			continue
		out_v.append(a)
		out_v.append(b)
		out_v.append(c)
		out_n.append(n)
		out_n.append(n)
		out_n.append(n)

	var out := []
	out.resize(Mesh.ARRAY_MAX)
	out[Mesh.ARRAY_VERTEX] = out_v
	out[Mesh.ARRAY_NORMAL] = out_n
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, out)
	return mesh


## Normal of a triangle with Godot's winding (front face clockwise).
static func face_normal(a: Vector3, b: Vector3, c: Vector3) -> Vector3:
	var n := (c - a).cross(b - a)
	if n.length_squared() < 1e-10:
		return Vector3.ZERO
	return n.normalized()


static func part(parent: Node3D, mesh: PrimitiveMesh, color: Color, pos := Vector3.ZERO,
		rot_deg := Vector3.ZERO) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	mi.mesh = flat(mesh)
	mi.material_override = material(color)
	mi.position = pos
	mi.rotation_degrees = rot_deg
	parent.add_child(mi)
	return mi


static func box(parent: Node3D, size: Vector3, color: Color, pos := Vector3.ZERO,
		rot_deg := Vector3.ZERO) -> MeshInstance3D:
	var m := BoxMesh.new()
	m.size = size
	return part(parent, m, color, pos, rot_deg)


static func cylinder(parent: Node3D, top: float, bottom: float, height: float, sides: int,
		color: Color, pos := Vector3.ZERO, rot_deg := Vector3.ZERO) -> MeshInstance3D:
	var m := CylinderMesh.new()
	m.top_radius = top
	m.bottom_radius = bottom
	m.height = height
	m.radial_segments = sides
	m.rings = 1
	return part(parent, m, color, pos, rot_deg)


static func sphere(parent: Node3D, radius: float, height: float, sides: int, rings: int,
		color: Color, pos := Vector3.ZERO) -> MeshInstance3D:
	var m := SphereMesh.new()
	m.radius = radius
	m.height = height
	m.radial_segments = sides
	m.rings = rings
	return part(parent, m, color, pos)


## Small tone variation so not everything looks identical.
static func vary(color: Color, rng: RandomNumberGenerator, amount := 0.06) -> Color:
	return Color(
		clampf(color.r + rng.randf_range(-amount, amount), 0.0, 1.0),
		clampf(color.g + rng.randf_range(-amount, amount), 0.0, 1.0),
		clampf(color.b + rng.randf_range(-amount, amount), 0.0, 1.0),
		color.a)
