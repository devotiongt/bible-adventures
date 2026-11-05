extends MeshInstance3D
## Tunic skirt simulated as cloth (Verlet / position-based dynamics).
## - The waist row is stuck to the pelvis.
## - Each particle gently tends toward its "ideal" position (the animated pose), so the
##   tunic keeps its shape, but lags and swings with inertia when walking or turning.
## - The legs and hips are capsules that push the cloth outward.
## The simulation runs in world space so the inertia is real.
## If given a template mesh (the Blender skirt, with folds), it draws that mesh
## deformed by the cloth: each vertex follows the patch of cloth it belongs to (by its UV) and
## keeps its fold relative to it. Otherwise it draws the simulation grid itself.

const SEGMENTS := 28
const MIN_STEP := 1.0 / 240.0
const MAX_STEP := 1.0 / 30.0
const ITERATIONS := 4
const GRAVITY := Vector3(0, -9.8, 0)
const DAMPING := 0.97          ## Fraction of the velocity kept every 1/60 s.
const THICKNESS := 0.035       ## Gap between the cloth and the body.
const MAX_DRIFT := 0.3         ## The farthest the cloth strays from its ideal pose.
const AROUND_SLACK := 1.25     ## The cloth can stretch a little sideways if a leg pushes it.
const STIFF_TOP := 0.18        ## Pull toward the ideal pose near the waist...
const STIFF_HEM := 0.025       ## ...and at the bottom hem (looser).

## Collision capsules: [start bone, end bone, radius].
const CAPSULES := [
	["thigh_l", "calf_l", 0.1], ["calf_l", "foot_l", 0.075],
	["thigh_r", "calf_r", 0.1], ["calf_r", "foot_r", 0.075],
	["thigh_l", "thigh_r", 0.115], ["pelvis", "spine_02", 0.14],
]
const BONES := ["pelvis", "thigh_l", "calf_l", "thigh_r", "calf_r", "spine_02", "foot_l", "foot_r"]

var body_skeleton: Skeleton3D  ## Noah's skeleton (MeshInstance3D already has "skeleton").

var _rings := 0
var _rest := PackedVector3Array()     ## Rest position (skeleton space).
var _pos := PackedVector3Array()      ## Simulated position (world).
var _prev := PackedVector3Array()
var _target := PackedVector3Array()   ## Ideal pose for this step (world).
var _weights: Array[Dictionary] = []  ## bone -> weight, per particle.
var _stiff := PackedFloat32Array()
var _edges := PackedInt32Array()      ## Pairs (a, b) of linked particles.
var _edge_len := PackedFloat32Array()
var _edge_slack := PackedFloat32Array()  ## How much each link can stretch without being corrected.
var _colors := PackedColorArray()
var _indices := PackedInt32Array()
var _bone_id := {}
var _skin := {}                       ## bone -> Transform3D from rest to current pose (world).
var _template := []                   ## Surfaces of the template mesh (see _prepare_template).
var _last_dt := 1.0 / 60.0
var _started := false


## rings: [[height, semi-axis x, semi-axis z, center z], ...] from the waist down.
## band_rows: how many bottom rows get the hem color.
func setup(p_skeleton: Skeleton3D, rings: Array, color: Color, hem_color: Color, template: Mesh = null,
		colors := {}, band_rows := 2) -> void:
	body_skeleton = p_skeleton
	_rings = rings.size()
	for bone in BONES:
		_bone_id[bone] = body_skeleton.find_bone(bone)
	for r in _rings:
		var ring: Array = rings[r]
		var t := float(r) / (_rings - 1)
		for s in SEGMENTS:
			var a := TAU * s / SEGMENTS
			var p := Vector3(cos(a) * ring[1], ring[0], ring[3] + sin(a) * ring[2])
			_rest.append(p)
			_weights.append(_skirt_weights(p, t))
			_stiff.append(lerpf(STIFF_TOP, STIFF_HEM, t))
			_colors.append((hem_color if r >= _rings - band_rows else color).srgb_to_linear())
	for r in _rings:
		for s in SEGMENTS:
			var i := r * SEGMENTS + s
			_add_edge(i, r * SEGMENTS + (s + 1) % SEGMENTS, AROUND_SLACK)  # around
			if r + 1 < _rings:
				_add_edge(i, i + SEGMENTS)                     # downward
			if r + 2 < _rings:
				_add_edge(i, i + 2 * SEGMENTS)                 # bending stiffness
			if r + 1 < _rings:
				_add_edge(i, (r + 1) * SEGMENTS + (s + 1) % SEGMENTS)  # diagonal
	for r in _rings - 1:
		for s in SEGMENTS:
			var i0 := r * SEGMENTS + s
			var i1 := r * SEGMENTS + (s + 1) % SEGMENTS
			_indices.append_array([i0, i0 + SEGMENTS, i1, i1, i0 + SEGMENTS, i1 + SEGMENTS])
	_pos.resize(_rest.size())
	_prev.resize(_rest.size())
	_target.resize(_rest.size())

	top_level = true
	process_priority = 100  # After the animation moves the skeleton.
	var mat := StandardMaterial3D.new()
	mat.vertex_color_use_as_albedo = true
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	mat.roughness = 0.95
	material_override = mat
	mesh = ArrayMesh.new()
	if template:
		material_override = null
		_prepare_template(template, colors)


## For each vertex of the template mesh: which cloth particles it falls between (by its UV)
## and its offset and normal measured in the local frame of the cloth at rest.
func _prepare_template(template: Mesh, colors: Dictionary) -> void:
	var frames := _grid_frames(_rest)
	# The UV height must go from the waist (0) to the hem (1); if it comes reversed, it's flipped.
	# The whole skirt is checked at once: a single surface (e.g. the trim) is not enough.
	var top_y := -INF
	var flip := false
	for surface in template.get_surface_count():
		var arrays := template.surface_get_arrays(surface)
		var verts: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var uvs: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV]
		for i in verts.size():
			if verts[i].y > top_y:
				top_y = verts[i].y
				flip = uvs[i].y > 0.5
	for surface in template.get_surface_count():
		var arrays := template.surface_get_arrays(surface)
		var verts: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
		var uvs: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV]
		var corners := PackedInt32Array()
		var blend := PackedFloat32Array()
		var offsets := PackedVector3Array()
		var normal_coefs := PackedVector3Array()
		for i in verts.size():
			var uv := uvs[i]
			var cell := _cell(uv.x, 1.0 - uv.y if flip else uv.y)
			for k in 4:
				corners.append(cell[0][k])
				blend.append(cell[1][k])
			var frame := _blend_frame(_rest, frames, cell[0], cell[1])
			var d: Vector3 = verts[i] - frame[0]
			offsets.append(Vector3(d.dot(frame[1]), d.dot(frame[2]), d.dot(frame[3])))
			var n := normals[i]
			normal_coefs.append(Vector3(n.dot(frame[1]), n.dot(frame[2]), n.dot(frame[3])))
		var source_mat := template.surface_get_material(surface)
		var mat_name := source_mat.resource_name if source_mat else ""
		var mat := StandardMaterial3D.new()
		mat.albedo_color = colors.get(mat_name, Color.WHITE)
		mat.roughness = 0.95
		mat.cull_mode = BaseMaterial3D.CULL_DISABLED
		_template.append({
			"corners": corners, "blend": blend, "offsets": offsets, "normal_coefs": normal_coefs,
			"indices": arrays[Mesh.ARRAY_INDEX], "uv": uvs, "material": mat, "count": verts.size(),
		})


## The 4 particles around the point (u around 0..1, v waist 0 .. hem 1) and their weights.
func _cell(u: float, v: float) -> Array:
	var gu := fposmod(u, 1.0) * SEGMENTS
	var gv := clampf(v, 0.0, 1.0) * (_rings - 1)
	var s0 := int(floor(gu)) % SEGMENTS
	var s1 := (s0 + 1) % SEGMENTS
	var r0 := mini(int(floor(gv)), _rings - 2)
	var r1 := r0 + 1
	var fu: float = gu - floor(gu)
	var fv: float = gv - r0
	return [
		PackedInt32Array([r0 * SEGMENTS + s0, r0 * SEGMENTS + s1, r1 * SEGMENTS + s0, r1 * SEGMENTS + s1]),
		PackedFloat32Array([(1 - fu) * (1 - fv), fu * (1 - fv), (1 - fu) * fv, fu * fv]),
	]


## Local frame of each particle: outward normal, tangent around and tangent downward.
func _grid_frames(points: PackedVector3Array) -> Array:
	var normals := PackedVector3Array()
	var arounds := PackedVector3Array()
	var downs := PackedVector3Array()
	normals.resize(points.size())
	arounds.resize(points.size())
	downs.resize(points.size())
	for r in _rings:
		var center := Vector3.ZERO
		for s in SEGMENTS:
			center += points[r * SEGMENTS + s]
		center /= SEGMENTS
		for s in SEGMENTS:
			var i := r * SEGMENTS + s
			var around := points[r * SEGMENTS + (s + 1) % SEGMENTS] - points[r * SEGMENTS + (s - 1 + SEGMENTS) % SEGMENTS]
			var down := points[mini(r + 1, _rings - 1) * SEGMENTS + s] - points[maxi(r - 1, 0) * SEGMENTS + s]
			var n := around.cross(down).normalized()
			if n.dot(points[i] - center) < 0.0:
				n = -n
			normals[i] = n
			arounds[i] = around
			downs[i] = down
	return [normals, arounds, downs]


## Point and orthonormal frame (point, normal, around, down) blending 4 particles.
func _blend_frame(points: PackedVector3Array, frames: Array, corners: PackedInt32Array,
		weights: PackedFloat32Array, offset := 0) -> Array:
	var p := Vector3.ZERO
	var n := Vector3.ZERO
	var t := Vector3.ZERO
	var d := Vector3.ZERO
	var normals: PackedVector3Array = frames[0]
	var arounds: PackedVector3Array = frames[1]
	var downs: PackedVector3Array = frames[2]
	for k in 4:
		var c := corners[offset + k]
		var w := weights[offset + k]
		p += points[c] * w
		n += normals[c] * w
		t += arounds[c] * w
		d += downs[c] * w
	n = n.normalized()
	t = (t - n * t.dot(n)).normalized()
	var d2 := n.cross(t)
	if d2.dot(d) < 0.0:
		d2 = -d2
	return [p, n, t, d2]


func _add_edge(a: int, b: int, slack := 1.0) -> void:
	_edges.append(a)
	_edges.append(b)
	_edge_len.append(_rest[a].distance_to(_rest[b]))
	_edge_slack.append(slack)


## Ideal pose: mostly the pelvis; the legs only drag it a little
## (the collisions do the rest), like a hanging tunic.
func _skirt_weights(p: Vector3, t: float) -> Dictionary:
	var left := smoothstep(-0.1, 0.1, p.x)
	var legs := 0.7 * smoothstep(0.0, 0.5, t)
	var calf := smoothstep(0.45, 1.0, t)
	return {
		"pelvis": 1.0 - legs,
		"thigh_l": legs * left * (1.0 - calf), "calf_l": legs * left * calf,
		"thigh_r": legs * (1.0 - left) * (1.0 - calf), "calf_r": legs * (1.0 - left) * calf,
	}


func _process(delta: float) -> void:
	if body_skeleton == null:
		return
	global_transform = Transform3D.IDENTITY
	_update_skin()
	_update_targets()
	if not _started or _pos[0].distance_to(_target[0]) > 1.0:
		_reset()
	# One step per frame, with the frame's real time: if the screen runs at
	# 120 Hz the cloth moves on each one and not in jumps.
	_simulate(clampf(delta, MIN_STEP, MAX_STEP))
	_rebuild_mesh()


func _update_skin() -> void:
	var to_world := body_skeleton.global_transform
	for bone in BONES:
		var i: int = _bone_id[bone]
		_skin[bone] = to_world * body_skeleton.get_bone_global_pose(i) * body_skeleton.get_bone_global_rest(i).affine_inverse()


func _update_targets() -> void:
	for i in _rest.size():
		var p := Vector3.ZERO
		var w: Dictionary = _weights[i]
		for bone in w:
			if w[bone] > 0.0:
				p += (_skin[bone] as Transform3D) * _rest[i] * w[bone]
		_target[i] = p


func _reset() -> void:
	for i in _rest.size():
		_pos[i] = _target[i]
		_prev[i] = _target[i]
	_started = true


func _simulate(dt: float) -> void:
	var count := _pos.size()
	var gravity_step := GRAVITY * dt * dt
	# Verlet with a variable step: the velocity is rescaled by dt / previous dt.
	var carry := pow(DAMPING, dt * 60.0) * (dt / _last_dt)
	_last_dt = dt
	for i in count:
		var p := _pos[i]
		_pos[i] = p + (p - _prev[i]) * carry + gravity_step
		_prev[i] = p
	var rate := dt * 60.0  # The pull toward the ideal pose doesn't depend on fps.

	var capsules := []
	for c in CAPSULES:
		capsules.append([(_skin[c[0]] as Transform3D) * body_skeleton.get_bone_global_rest(_bone_id[c[0]]).origin,
				(_skin[c[1]] as Transform3D) * body_skeleton.get_bone_global_rest(_bone_id[c[1]]).origin,
				float(c[2]) + THICKNESS])

	for iteration in ITERATIONS:
		# The waist is stuck to the body.
		for s in SEGMENTS:
			_pos[s] = _target[s]
		# Keep the tunic's shape.
		for i in range(SEGMENTS, count):
			_pos[i] += (_target[i] - _pos[i]) * (1.0 - pow(1.0 - _stiff[i], rate))
		# Distances between particles (the cloth doesn't stretch).
		for e in _edge_len.size():
			var a := _edges[e * 2]
			var b := _edges[e * 2 + 1]
			var d := _pos[b] - _pos[a]
			var length := d.length()
			if length < 1e-6:
				continue
			var rest_len := _edge_len[e]
			if length > rest_len and length < rest_len * _edge_slack[e]:
				continue
			if length > rest_len:
				rest_len *= _edge_slack[e]
			var fix := d * ((length - rest_len) / length)
			if a < SEGMENTS:
				_pos[b] -= fix
			else:
				_pos[a] += fix * 0.5
				_pos[b] -= fix * 0.5
		# Don't stray too far from the ideal pose and, at the end (overrides everything else),
		# push out of the legs and hips.
		for i in range(SEGMENTS, count):
			var p := _pos[i]
			var drift := p - _target[i]
			if drift.length() > MAX_DRIFT:
				p = _target[i] + drift.normalized() * MAX_DRIFT
			for c in capsules:
				p = _push_out(p, c[0], c[1], c[2])
			_pos[i] = p


func _push_out(p: Vector3, a: Vector3, b: Vector3, radius: float) -> Vector3:
	var ab := b - a
	var t := clampf((p - a).dot(ab) / ab.length_squared(), 0.0, 1.0)
	var closest := a + ab * t
	var d := p - closest
	var dist := d.length()
	if dist >= radius or dist < 1e-6:
		return p
	return closest + d / dist * radius


func _rebuild_mesh() -> void:
	if not _template.is_empty():
		_rebuild_template()
		return
	_rebuild_grid()


func _rebuild_template() -> void:
	var frames := _grid_frames(_pos)
	var m := mesh as ArrayMesh
	m.clear_surfaces()
	for surface in _template:
		var count: int = surface["count"]
		var corners: PackedInt32Array = surface["corners"]
		var blend: PackedFloat32Array = surface["blend"]
		var offsets: PackedVector3Array = surface["offsets"]
		var coefs: PackedVector3Array = surface["normal_coefs"]
		var verts := PackedVector3Array()
		var normals := PackedVector3Array()
		verts.resize(count)
		normals.resize(count)
		for i in count:
			var f := _blend_frame(_pos, frames, corners, blend, i * 4)
			var o := offsets[i]
			var c := coefs[i]
			var n: Vector3 = f[1]
			var t: Vector3 = f[2]
			var d: Vector3 = f[3]
			verts[i] = (f[0] as Vector3) + n * o.x + t * o.y + d * o.z
			normals[i] = (n * c.x + t * c.y + d * c.z).normalized()
		var arrays := []
		arrays.resize(Mesh.ARRAY_MAX)
		arrays[Mesh.ARRAY_VERTEX] = verts
		arrays[Mesh.ARRAY_NORMAL] = normals
		arrays[Mesh.ARRAY_TEX_UV] = surface["uv"]
		arrays[Mesh.ARRAY_INDEX] = surface["indices"]
		m.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
		m.surface_set_material(m.get_surface_count() - 1, surface["material"])


func _rebuild_grid() -> void:
	var normals := PackedVector3Array()
	normals.resize(_pos.size())
	for r in _rings:
		var center := Vector3.ZERO
		for s in SEGMENTS:
			center += _pos[r * SEGMENTS + s]
		center /= SEGMENTS
		for s in SEGMENTS:
			var i := r * SEGMENTS + s
			var around := _pos[r * SEGMENTS + (s + 1) % SEGMENTS] - _pos[r * SEGMENTS + (s - 1 + SEGMENTS) % SEGMENTS]
			var down := _pos[mini(r + 1, _rings - 1) * SEGMENTS + s] - _pos[maxi(r - 1, 0) * SEGMENTS + s]
			var n := around.cross(down).normalized()
			if n.dot(_pos[i] - center) < 0.0:
				n = -n
			normals[i] = n
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = _pos
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_COLOR] = _colors
	arrays[Mesh.ARRAY_INDEX] = _indices
	var m := mesh as ArrayMesh
	m.clear_surfaces()
	m.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
