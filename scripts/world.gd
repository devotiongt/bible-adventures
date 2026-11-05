extends Node3D
## The valley of Noah's village (docs/DESIGN_CHAPTER1.md, references/noah_village_sketch.jpg), placed
## by hand from data/village.json: almost flat ground with a gentle roll, the ark at the top of the
## northern hill, hills all around with the road's way out of the valley, a river to the west with a
## bridge, paths that join the doors with the plaza and the plaza with each work area. Vegetation and
## resources are grouped where they make sense (forest, quarry, banks, edges of paths and houses);
## randomness only varies size, rotation and tone a little.

const LowPoly := preload("res://scripts/lowpoly.gd")
const ResourceNode := preload("res://scripts/resource_node.gd")
const Stylized := preload("res://scripts/stylized.gd")
const Village := preload("res://scripts/village.gd")
const WATER_SHADER := preload("res://shaders/water.gdshader")
const TERRAIN_SHADER := preload("res://shaders/terrain.gdshader")

const DATA := "res://data/village.json"
## Terrain: the "area" rectangle from the data (valley and hills), with a cell of CELL meters.
const CELL := 0.75
const WATER_LEVEL := -0.55

const GRASS := Color("76a952")         ## A somewhat warm green (Mesopotamian valley), not garish.
const GRASS_SHADE := Color("65984a")
const GRASS_HILL := Color("6f9f50")
const BANK := Color("c9a77c")
const BANK_DARK := Color("a98760")
const PATH := Color("d6a76e")
const PLAZA := Color("e0c595")
const WORN := Color("a6b56b")       ## Trampled grass along the edges of the paths.
const PATH_KINDS := ["street", "alley", "trail"]
## Measurements of each house model (tools/blender/houses.py), in house coordinates: x across the
## width, y toward the facade. size: width and depth it takes up; center_x: offset of that
## rectangle; front: distance to the frontmost part (low wall or stone bench); door_x: where you go
## out (the door or the yard gate); door: the house door; roof: height of the low roof;
## rug: free spot on the roof (no stairs or awnings).
const HOUSE_MODELS := {
	"HouseA": {"size": [5.6, 3.8], "center_x": 0.45, "front": 2.3, "door_x": -0.5, "door": [-0.5, 1.9],
			"roof": 2.5, "rug": [0.9, 0.7]},
	"HouseB": {"size": [5.6, 4.2], "center_x": 0.0, "front": 4.7, "door_x": -0.2, "door": [-1.2, 2.1],
			"roof": 2.2, "rug": [1.6, 0.7]},
	"HouseC": {"size": [4.4, 8.0], "center_x": 0.0, "front": 2.4, "door_x": 0.0, "door": [0.0, 1.8],
			"roof": 2.4, "rug": [0.0, 0.3]},
	"NoahHouse": {"size": [8.8, 5.0], "center_x": 0.3, "front": 6.6, "door_x": 0.15, "door": [-1.6, 2.5],
			"roof": 2.4, "rug": [2.4, 1.2]},
}

var data: Dictionary
var rng := RandomNumberGenerator.new()
var undulation := FastNoiseLite.new()
var patches := FastNoiseLite.new()

var _w: int
var _h: int
var _heights := PackedFloat32Array()
var _river: PackedVector2Array
var _river_chunks: Array = []   # [{from, to, box}]: river stretches with their box, so we don't walk the whole thing.
var area_min: Vector2
var area_max: Vector2
var _paths: Array = []          # [{points: PackedVector2Array, width, box: Rect2}]
var _house_rects: Array = []    # [{pos, rotation, center, half}] for _house_distance
var _plaza_poly := PackedVector2Array()
var _plaza_box: Rect2
var _placed: Array[Vector3] = []
var _clouds: Array[Node3D] = []


func _ready() -> void:
	data = JSON.parse_string(FileAccess.get_file_as_string(DATA))
	undulation.seed = 11
	undulation.frequency = 0.03
	patches.seed = 5
	patches.frequency = 0.05
	rng.seed = 1234
	area_min = Vector2(data["area"][0], data["area"][1])
	area_max = Vector2(data["area"][2], data["area"][3])
	_river = _curve(data["river"]["points"], 4)
	var reach: float = float(data["river"]["width"]) * 0.5 + 8.0
	for i in range(0, _river.size() - 1, 8):
		var j := mini(i + 8, _river.size() - 1)
		_river_chunks.append({"from": i, "to": j, "box": _bounds(_river.slice(i, j + 1)).grow(reach)})
	for house in data["houses"]:
		house.merge(HOUSE_MODELS[house["model"]])     # Whatever the house doesn't say, its model fills in.
	for p in data["paths"]:
		var pts := _curve(p["points"], 6)
		_paths.append({"points": pts, "width": float(p["width"]), "type": p.get("type", "street"),
				"box": _bounds(pts).grow(p["width"] + 1.0)})
	# Smoothed plaza outline (closed curve through its vertices): no polygon corners.
	var outline: Array = data["plaza"]["outline"]
	var n := outline.size()
	for i in n:
		var pts := [outline[(i - 1 + n) % n], outline[i], outline[(i + 1) % n], outline[(i + 2) % n]]
		var seg := _curve(pts, 6)
		for k in range(6, 12):           # Only the stretch between the 2nd and 3rd points.
			_plaza_poly.append(seg[k])
	_plaza_box = _bounds(_plaza_poly)
	for house in data["houses"]:
		var back := -float(house["size"][1]) * 0.5
		var front := house_front(house) + float(house["yard"])
		_house_rects.append({"pos": Vector2(house["pos"][0], house["pos"][1]), "rotation": house_angle(house),
				"center": Vector2(float(house.get("center_x", 0.0)), (back + front) * 0.5),
				"half": Vector2(house["size"][0] * 0.5, (front - back) * 0.5)})
	_bake_heights()
	_build_terrain()
	_build_river()
	var village := Village.new()
	village.name = "Village"
	village.world = self
	add_child(village)
	_place_resources()
	_place_shade_trees()
	_build_hill_forest()
	_build_vegetation()
	_build_clouds(12)


func _process(delta: float) -> void:
	for cloud in _clouds:
		cloud.position.x += delta * 0.6
		if cloud.position.x > area_max.x + 60.0:
			cloud.position.x = area_min.x - 60.0


# --- Queries (used by Noah, the animals, the ark and placement) --------------

## Ground height: interpolated from the precomputed grid, same as the terrain mesh.
func height_at(x: float, z: float) -> float:
	var fx := clampf((x - area_min.x) / CELL, 0.0, _w - 1.001)
	var fz := clampf((z - area_min.y) / CELL, 0.0, _h - 1.001)
	var i := int(fx)
	var j := int(fz)
	var tx := fx - i
	var tz := fz - j
	var a := lerpf(_heights[j * _w + i], _heights[j * _w + i + 1], tx)
	var b := lerpf(_heights[(j + 1) * _w + i], _heights[(j + 1) * _w + i + 1], tx)
	return lerpf(a, b, tz)


func normal_at(x: float, z: float) -> Vector3:
	var e := 0.4
	return Vector3(height_at(x - e, z) - height_at(x + e, z), 2.0 * e,
			height_at(x, z - e) - height_at(x, z + e)).normalized()


func ark_position() -> Vector3:
	var c: Array = data["ark"]["center"]
	return Vector3(c[0], float(data["ark"]["height"]), c[1])


## 0 at the center of the ark clearing, 1 at its edge.
func clearing_distance(x: float, z: float) -> float:
	var c: Array = data["ark"]["center"]
	var s: Array = data["ark"]["semi_axes"]
	return Vector2((x - c[0]) / s[0], (z - c[1]) / s[1]).length()


## Noah starts in his house's yard.
func spawn_point() -> Vector3:
	var p := house_point(data["houses"][0], Vector2(1.5, 4.6))
	return Vector3(p.x, height_at(p.x, p.y) + 0.5, p.y)


## Rotation of a house: the facade faces the nearest street or alley (ends up parallel to it), with a
## small offset of its own ("rotation", in degrees).
func house_angle(house: Dictionary) -> float:
	var pos := Vector2(house["pos"][0], house["pos"][1])
	var nearest := pos + Vector2(0, 1)
	var best := INF
	for path in _paths:
		if path["type"] == "trail":
			continue
		var pts: PackedVector2Array = path["points"]
		for i in pts.size() - 1:
			var q := Geometry2D.get_closest_point_to_segment(pos, pts[i], pts[i + 1])
			if q.distance_to(pos) < best:
				best = q.distance_to(pos)
				nearest = q
	var to := nearest - pos
	return atan2(to.x, to.y) + deg_to_rad(float(house.get("rotation", 0.0)))


## World point from local house coordinates (x across the width, y toward the facade).
func house_point(house: Dictionary, local: Vector2) -> Vector2:
	return Vector2(house["pos"][0], house["pos"][1]) + _rotate_local(local, house_angle(house))


func house_front(house: Dictionary) -> float:
	return float(house.get("front", house["size"][1] * 0.5))


func _rotate_local(local: Vector2, angle: float) -> Vector2:
	# Rotation around Y like Godot's: the local +Z axis (the facade) points to (sin, cos).
	return Vector2(local.x * cos(angle) + local.y * sin(angle), -local.x * sin(angle) + local.y * cos(angle))


## Distance (m) to the edge of the valley: negative inside, positive in the hills. "shape" 2 is an
## ellipse; more, a rectangle with rounded corners.
func valley_distance(x: float, z: float) -> float:
	var v: Dictionary = data["valley"]
	var p := Vector2(x - v["center"][0], z - v["center"][1])
	var ang := p.angle()
	var k := 1.0
	for wave in v["waves"]:
		k += float(wave[1]) * sin(float(wave[0]) * ang + float(wave[2]))
	var n := float(v.get("shape", 2.0))
	var r := pow(pow(absf(p.x / v["semi_axes"][0]), n) + pow(absf(p.y / v["semi_axes"][1]), n), 1.0 / n) / k
	return (r - 1.0) * minf(v["semi_axes"][0], v["semi_axes"][1])


## Radius of the pen the point falls in (0 if it isn't in any).
func corral_radius_at(x: float, z: float) -> float:
	for c in data["pens"]:
		if Vector2(x - c["center"][0], z - c["center"][1]).length() < float(c["radius"]):
			return float(c["radius"])
	return 0.0


## Distance to the center of the riverbed. Far from it (outside the box of every stretch) the exact
## value isn't needed: a large one is returned.
func river_distance(x: float, z: float) -> float:
	var p := Vector2(x, z)
	var best := 99.0
	for chunk in _river_chunks:
		if chunk["box"].has_point(p):
			best = minf(best, _polyline_distance(p, _river.slice(chunk["from"], chunk["to"] + 1)))
	return best


## Distance to the edge of the nearest path (negative on the path). The width changes a bit along
## each path, like one worn by foot traffic.
func path_distance(x: float, z: float) -> float:
	return _path_query(x, z).x


## (distance to the edge, type: 0 street, 1 alley, 2 trail) of the nearest path.
func _path_query(x: float, z: float) -> Vector2:
	var p := Vector2(x, z)
	var best := Vector2(INF, 0)
	var vary := 1.0 + patches.get_noise_2d(x * 1.7 + 50.0, z * 1.7) * 0.22
	for path in _paths:
		if path["box"].has_point(p):
			var d: float = _polyline_distance(p, path["points"]) - path["width"] * 0.5 * vary
			if d < best.x:
				best = Vector2(d, PATH_KINDS.find(path["type"]))
	return best


func on_bridge(x: float, z: float) -> bool:
	for b in data["bridges"]:
		# Along the bridge: its local x axis, rotated "rotation" degrees in Y.
		var rel := Vector2(x - b["center"][0], z - b["center"][1])
		var turn := deg_to_rad(float(b["rotation"]))
		var along := rel.dot(Vector2(cos(turn), -sin(turn)))
		var across := rel.dot(Vector2(sin(turn), cos(turn)))
		if absf(along) < b["length"] * 0.5 and absf(across) < b["width"] * 0.5:
			return true
	return false


## Where you can walk: not inside the river (except the bridge) nor up the hills.
func is_walkable(x: float, z: float) -> bool:
	if valley_distance(x, z) > 4.0:
		return false
	return on_bridge(x, z) or river_distance(x, z) > data["river"]["width"] * 0.5 + 0.2


## A spot free of paths, plaza, yards, river and ark clearing (for plants and animals).
func is_open_ground(x: float, z: float, margin := 0.5) -> bool:
	if not is_walkable(x, z) or valley_distance(x, z) > 0.0:
		return false
	if path_distance(x, z) < margin or river_distance(x, z) < data["river"]["width"] * 0.5 + 1.0 + margin:
		return false
	if (_plaza_distance(x, z) < margin and island_distance(x, z) > -margin) or _house_distance(x, z) < margin \
			or clearing_distance(x, z) < 1.05:
		return false
	if field_distance(x, z) < margin:
		return false
	return true


# --- Terrain shape -------------------------------------------------------------

func _shape_height(x: float, z: float) -> float:
	var h := undulation.get_noise_2d(x, z) * 0.35
	# Hills around the valley, with some relief of their own.
	var v: Dictionary = data["valley"]
	var d := valley_distance(x, z)
	var hill := smoothstep(0.0, float(v["hill_width"]), d)
	# The road to the valley goes out through a pass between the hills.
	if v.has("exit"):
		var exit := Vector2(v["exit"][0], v["exit"][1])
		var exit_d := _polyline_distance(Vector2(x, z), PackedVector2Array([exit, exit + Vector2(2, 40)]))
		hill *= smoothstep(float(v["exit_width"]) * 0.5, float(v["exit_width"]) * 1.6, exit_d)
	h += hill * float(v["hill_height"]) * (1.0 + undulation.get_noise_2d(x * 2.0, z * 2.0) * 0.35)
	# Ark hill: rises gently to a flat landing at the top.
	var ark: Dictionary = data["ark"]
	var cd := clearing_distance(x, z)
	var reach := float(ark["hill"]) / float(ark["semi_axes"][0])
	h = lerpf(h, float(ark["height"]), 1.0 - smoothstep(1.0, 1.0 + reach, cd))
	# The plaza, the houses and their yards, packed and flat.
	h *= smoothstep(0.0, 4.0, minf(_plaza_distance(x, z), _house_distance(x, z)))
	# Riverbed, with gentle banks.
	var river: Dictionary = data["river"]
	var half := float(river["width"]) * 0.5
	var rd := river_distance(x, z)
	if rd < half + 3.0:
		h = lerpf(h, -float(river["depth"]), 1.0 - smoothstep(half - 0.6, half + 2.5, rd))
	return h


func _bake_heights() -> void:
	_w = int((area_max.x - area_min.x) / CELL) + 1
	_h = int((area_max.y - area_min.y) / CELL) + 1
	_heights.resize(_w * _h)
	for j in _h:
		for i in _w:
			_heights[j * _w + i] = _shape_height(area_min.x + i * CELL, area_min.y + j * CELL)


## Distance to the edge of the plaza (negative inside): an irregular polygon, the widening of the street.
func _plaza_distance(x: float, z: float) -> float:
	var p := Vector2(x, z)
	# Far from the plaza the distance to its box is enough (saves walking the whole outline).
	var gap := maxf(maxf(_plaza_box.position.x - x, x - _plaza_box.end.x), maxf(_plaza_box.position.y - z, z - _plaza_box.end.y))
	if gap > 8.0:
		return gap
	var d := INF
	for i in _plaza_poly.size():
		var a := _plaza_poly[i]
		var b := _plaza_poly[(i + 1) % _plaza_poly.size()]
		d = minf(d, p.distance_to(Geometry2D.get_closest_point_to_segment(p, a, b)))
	return -d if Geometry2D.is_point_in_polygon(p, _plaza_poly) else d


## Distance to the edge of the grass island in the middle of the plaza (negative inside).
func island_distance(x: float, z: float) -> float:
	var isle: Dictionary = data["plaza"].get("island", {})
	if isle.is_empty():
		return INF
	var rel := Vector2(x - isle["center"][0], z - isle["center"][1])
	# A wavy edge, not a compass-drawn circle.
	var wave := 0.35 * sin(3.0 * rel.angle() + 1.3) + 0.2 * sin(5.0 * rel.angle() + 0.4)
	return rel.length() - float(isle["radius"]) - wave


## Distance to the nearest yard (rectangle of the house plus its yard in front).
func _house_distance(x: float, z: float) -> float:
	var best := INF
	for r in _house_rects:
		# Rectangle of the house plus its yard in front, in house coordinates.
		var rel: Vector2 = Vector2(x, z) - r["pos"]
		if rel.length_squared() > 400.0:
			best = minf(best, rel.length() - 10.0)
			continue
		var d: Vector2 = (_rotate_local(rel, -r["rotation"]) - r["center"]).abs() - r["half"]
		best = minf(best, Vector2(maxf(d.x, 0.0), maxf(d.y, 0.0)).length() + minf(maxf(d.x, d.y), 0.0))
	return best


## Distance to the fields and gardens (rotated rectangles): negative inside.
func field_distance(x: float, z: float) -> float:
	var best := INF
	for f in data["fields"] + data["gardens"]:
		var local := Vector2(x - f["center"][0], z - f["center"][1]).rotated(-deg_to_rad(float(f["rotation"])))
		var d := local.abs() - Vector2(f["size"][0], f["size"][1]) * 0.5
		best = minf(best, Vector2(maxf(d.x, 0.0), maxf(d.y, 0.0)).length() + minf(maxf(d.x, d.y), 0.0))
	return best


# --- Terrain mesh --------------------------------------------------------------

func _build_terrain() -> void:
	var colors := PackedColorArray()
	var marks := PackedColorArray()     # Slope, path, packed ground, plaza.
	colors.resize(_w * _h)
	marks.resize(_w * _h)
	for j in _h:
		for i in _w:
			var x := area_min.x + i * CELL
			var z := area_min.y + j * CELL
			var y := _heights[j * _w + i]
			var hx := _heights[j * _w + mini(i + 1, _w - 1)] - _heights[j * _w + maxi(i - 1, 0)]
			var hz := _heights[mini(j + 1, _h - 1) * _w + i] - _heights[maxi(j - 1, 0) * _w + i]
			var n := Vector3(-hx, 2.0 * CELL, -hz).normalized()
			var q := _path_query(x, z)
			colors[j * _w + i] = _ground_color(x, y, z, q)
			marks[j * _w + i] = _ground_marks(x, y, z, n, q)

	var verts := PackedVector3Array()
	var normals := PackedVector3Array()
	var vcolors := PackedColorArray()
	var uv := PackedVector2Array()
	var uv2 := PackedVector2Array()
	for j in _h - 1:
		for i in _w - 1:
			var q := [j * _w + i, j * _w + i + 1, (j + 1) * _w + i + 1, (j + 1) * _w + i]
			for tri in [[0, 1, 2], [0, 2, 3]]:
				var p: Array[Vector3] = []
				for k in tri:
					var idx: int = q[k]
					p.append(Vector3(area_min.x + (idx % _w) * CELL, _heights[idx], area_min.y + (idx / _w) * CELL))
				var n := LowPoly.face_normal(p[0], p[1], p[2])
				# A very slight tone change per triangle: grass texture without loud noise.
				var center := (p[0] + p[1] + p[2]) / 3.0
				var fleck := (_hash(center.x, center.z) - 0.5) * 0.035
				for k in 3:
					var idx: int = q[tri[k]]
					var m := marks[idx]
					verts.append(p[k])
					normals.append(n)
					var col := (colors[idx] * (1.0 + fleck)).srgb_to_linear()
					col.a = 0.5 + fleck            # The shader uses the tone change on the dirt too.
					vcolors.append(col)
					uv.append(Vector2(m.r, m.g))
					uv2.append(Vector2(m.b, m.a))

	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = verts
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_COLOR] = vcolors
	arrays[Mesh.ARRAY_TEX_UV] = uv
	arrays[Mesh.ARRAY_TEX_UV2] = uv2
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	var mat := ShaderMaterial.new()
	mat.shader = TERRAIN_SHADER
	mat.set_shader_parameter("cliff_color", BANK)
	mat.set_shader_parameter("cliff_dark", BANK_DARK)
	mat.set_shader_parameter("path_color", PATH)
	mat.set_shader_parameter("dirt_color", PLAZA)

	var body := StaticBody3D.new()
	body.name = "Terrain"
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	mi.material_override = mat
	body.add_child(mi)
	var shape := ConcavePolygonShape3D.new()
	shape.set_faces(verts)
	var col := CollisionShape3D.new()
	col.shape = shape
	body.add_child(col)
	add_child(body)


## q: the point's _path_query (computed once for the color and the marks).
func _ground_color(x: float, y: float, z: float, q: Vector2) -> Color:
	# Large, soft patches of darker grass (not speckled).
	var patch := smoothstep(-0.1, 0.5, patches.get_noise_2d(x, z))
	var c := GRASS.lerp(GRASS_SHADE, patch * 0.6)
	c = c.lerp(GRASS_HILL, smoothstep(0.0, 8.0, valley_distance(x, z)))
	# Trampled, lighter grass next to the paths (wider next to a street than next to a trail).
	var fringe: float = [1.3, 0.9, 0.6][int(q.y)] if q.x < INF else 0.0
	c = c.lerp(WORN, (1.0 - smoothstep(0.0, fringe, q.x)) * 0.55)
	# Wet bank next to the river.
	var rd: float = river_distance(x, z) - data["river"]["width"] * 0.5
	return c.lerp(BANK, 1.0 - smoothstep(0.0, 1.2, rd)) if y < 0.3 else c


## How much of each ground type (0.5 = the edge): slope, path and packed ground (plaza, yards
## and ark clearing).
func _ground_marks(x: float, y: float, z: float, n: Vector3, q: Vector2) -> Color:
	# Values linear with distance: that way, when interpolated between vertices, the edge (0.5) comes
	# out straight and smooth instead of stair-stepped.
	var bank := smoothstep(0.86, 0.74, n.y) * (1.0 - smoothstep(0.0, 1.0, y))
	bank = maxf(bank, clampf(0.5 - field_distance(x, z) * 0.6, 0.0, 1.0))   # Plowed soil of the fields.
	var wobble := patches.get_noise_2d(x * 3.0, z * 3.0) * 0.35
	var d := q.x + wobble * 0.5
	if q.y == 2:
		# Trails fade into the grass here and there.
		d += maxf(0.0, patches.get_noise_2d(x * 2.5, z * 2.5)) * 1.6
	var path := clampf(0.5 - d * 0.5, 0.0, 1.0)
	# Yards with rounded corners (the ground wears in curves, not rectangles).
	var packed := clampf(0.5 - (_house_distance(x, z) + 0.8 + wobble) * 0.5, 0.0, 1.0)
	# The plaza: paved, with a crisp edge (it's built, not worn), or dirt, with a worn edge that fades
	# into the grass, and the olive tree's grass island in the middle.
	var plaza := clampf(0.5 - _plaza_distance(x, z) * 0.5, 0.0, 1.0)
	if data["plaza"].get("ground", "stone") == "dirt":
		# The same dirt as the paths, which reach it and join without a seam.
		var earth := clampf(0.5 - (_plaza_distance(x, z) + wobble * 3.0) * 0.4, 0.0, 1.0)
		earth = minf(earth, clampf(0.5 + (island_distance(x, z) + wobble) * 0.6, 0.0, 1.0))
		path = maxf(path, earth)
		plaza = 0.0
	# In the ark clearing only the work area, around the hull, is trampled.
	var c: Array = data["ark"]["center"]
	# It reaches the workshop, on the door side (+z).
	var work := Vector2(absf(x - c[0]), absf(z - c[1] - 2.0)) - Vector2(12.5, 5.2)
	var work_d := Vector2(maxf(work.x, 0.0), maxf(work.y, 0.0)).length() - 2.0
	packed = maxf(packed, clampf(0.5 - (work_d + wobble * 2.0) * 0.5, 0.0, 1.0))
	return Color(bank, path, packed, plaza)


func _hash(x: float, z: float) -> float:
	return fposmod(sin(x * 127.1 + z * 311.7) * 43758.5453, 1.0)


# --- River and bridge ----------------------------------------------------------

func _build_river() -> void:
	var box := _bounds(_river).grow(6.0)
	var water := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = box.size
	plane.subdivide_width = int(box.size.x)
	plane.subdivide_depth = int(box.size.y)
	water.mesh = plane
	var mat := ShaderMaterial.new()
	mat.shader = WATER_SHADER
	mat.set_shader_parameter("deep_color", Color("5f9fb5"))
	mat.set_shader_parameter("shallow_color", Color("9fd0d6"))
	mat.set_shader_parameter("depth_fade", 1.2)
	water.material_override = mat
	water.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	water.position = Vector3(box.get_center().x, WATER_LEVEL, box.get_center().y)
	water.name = "River"
	add_child(water)


# --- Resources (chopping, mining, reeds, pitch) --------------------------------

func _place_resources() -> void:
	for grove in data["forest"]:
		var c := Vector2(grove["center"][0], grove["center"][1])
		for p in _cluster(c, float(grove["radius"]), int(grove["trees"]), 2.8):
			_add_resource("tree", p)
	var q: Dictionary = data["quarry"]
	for p in _cluster(Vector2(q["center"][0], q["center"][1]), float(q["radius"]), int(q["rocks"]), 2.4):
		_add_resource("rock", p)
	# Reeds along both banks, here and there, leaving the bridge clear.
	var half := float(data["river"]["width"]) * 0.5 + 0.9
	var along := 0.0
	for i in _river.size() - 1:
		var a := _river[i]
		var b := _river[i + 1]
		var side := (b - a).normalized().orthogonal()
		along += a.distance_to(b)
		if along < 9.0:
			continue
		along = 0.0
		var s := 1.0 if (i / 3) % 2 == 0 else -1.0
		var p := a + side * s * (half + rng.randf_range(0.0, 0.6))
		var near_bridge := false
		for bridge in data["bridges"]:
			near_bridge = near_bridge or p.distance_to(Vector2(bridge["center"][0], bridge["center"][1])) \
					< bridge["length"] * 0.5 + 3.0
		if near_bridge or valley_distance(p.x, p.y) > -2.0:
			continue
		_add_resource("bush", p)
	for p in data["pitch"]:
		_add_resource("pitch", Vector2(p[0], p[1]))


func _add_resource(kind: String, p: Vector2) -> void:
	var node := ResourceNode.new()
	node.setup(kind, rng)
	node.position = Vector3(p.x, height_at(p.x, p.y), p.y)
	node.rotation.y = rng.randf() * TAU
	add_child(node)
	_placed.append(node.position)


## Points spread inside a circle without crowding (closer together toward the center).
func _cluster(center: Vector2, radius: float, count: int, spacing: float) -> Array[Vector2]:
	var out: Array[Vector2] = []
	for attempt in count * 30:
		if out.size() >= count:
			break
		var r := radius * sqrt(rng.randf()) * rng.randf_range(0.6, 1.0)
		var p := center + Vector2.from_angle(rng.randf() * TAU) * r
		if not is_open_ground(p.x, p.y, 0.6):
			continue
		var ok := true
		for o in out:
			if o.distance_to(p) < spacing:
				ok = false
				break
		if ok:
			out.append(p)
	return out


# --- Shade trees, hill forest and plants ---------------------------------------

func _place_shade_trees() -> void:
	var root := Node3D.new()
	root.name = "ShadeTrees"
	add_child(root)
	for t in data["shade_trees"]:
		var tree: Node3D
		match t["type"]:
			"olive":
				tree = Stylized.olive(rng)
			"pine":
				tree = Stylized.pine(rng)
			_:
				tree = Stylized.round_tree(rng)
		tree.position = Vector3(t["pos"][0], height_at(t["pos"][0], t["pos"][1]), t["pos"][1])
		tree.rotation.y = rng.randf() * TAU
		tree.scale = Vector3.ONE * float(t["scale"])
		root.add_child(tree)
		_placed.append(tree.position)
	# Lone trees and forest patches in the valley (decorative: they can't be chopped).
	for t in data.get("trees", []):
		var tree := Stylized.round_tree(rng) if _hash(t[0], t[1]) < 0.7 else Stylized.pine(rng)
		tree.position = Vector3(t[0], height_at(t[0], t[1]), t[1])
		tree.rotation.y = rng.randf() * TAU
		tree.scale = Vector3.ONE * rng.randf_range(0.85, 1.2)
		root.add_child(tree)


## The hills at the edge, covered in forest patches (not random lone trees).
func _build_hill_forest() -> void:
	var root := Node3D.new()
	root.name = "HillForest"
	add_child(root)
	var x := area_min.x
	while x < area_max.x:
		var z := area_min.y
		while z < area_max.y:
			var p := Vector2(x + rng.randf_range(-1.2, 1.2), z + rng.randf_range(-1.2, 1.2))
			var d := valley_distance(p.x, p.y)
			var forest := patches.get_noise_2d(p.x * 0.8, p.y * 0.8)
			if d > 2.0 and d < 30.0 and forest > -0.05 and river_distance(p.x, p.y) > 5.0:
				var tree := Stylized.pine(rng) if forest > 0.25 or rng.randf() < 0.3 else Stylized.round_tree(rng)
				tree.position = Vector3(p.x, height_at(p.x, p.y), p.y)
				tree.rotation.y = rng.randf() * TAU
				tree.scale = Vector3.ONE * rng.randf_range(0.85, 1.25)
				root.add_child(tree)
			z += 3.6
		x += 3.6
	# Dense forest on the east edge (decorative), behind the trees that can be chopped.
	if not data.has("dense_forest"):
		return
	var dense: Dictionary = data["dense_forest"]
	x = float(dense["x_from"])
	while x < area_max.x:
		var z := float(dense["z_from"])
		while z < float(dense["z_to"]):
			var p := Vector2(x + rng.randf_range(-1.0, 1.0), z + rng.randf_range(-1.0, 1.0))
			if valley_distance(p.x, p.y) <= 2.0 and path_distance(p.x, p.y) > 1.5 and rng.randf() < 0.85:
				var tree := Stylized.round_tree(rng) if rng.randf() < 0.6 else Stylized.pine(rng)
				tree.position = Vector3(p.x, height_at(p.x, p.y), p.y)
				tree.rotation.y = rng.randf() * TAU
				tree.scale = Vector3.ONE * rng.randf_range(0.9, 1.3)
				root.add_child(tree)
			z += 2.8
		x += 2.8


func _build_vegetation() -> void:
	var root := Node3D.new()
	root.name = "Plants"
	add_child(root)
	# Loose pebbles along the edges of streets and alleys, where foot traffic pushes them aside.
	for path in _paths:
		if path["type"] == "trail":
			continue
		var pts: PackedVector2Array = path["points"]
		for i in pts.size() - 1:
			if _hash(pts[i].x, pts[i].y * 1.3) < 0.45:
				continue
			var side := (pts[i + 1] - pts[i]).normalized().orthogonal() * (1.0 if _hash(pts[i].y, pts[i].x) < 0.5 else -1.0)
			var p: Vector2 = pts[i] + side * (float(path["width"]) * 0.5 + rng.randf_range(-0.1, 0.25))
			var pebble := Stylized.rock(rng)
			pebble.scale = Vector3.ONE * rng.randf_range(0.07, 0.14)
			pebble.position = Vector3(p.x, height_at(p.x, p.y) - 0.02, p.y)
			pebble.rotation.y = rng.randf() * TAU
			root.add_child(pebble)
	# Tufts along the edges of the paths, here and there (not a continuous row).
	for path in _paths:
		var pts: PackedVector2Array = path["points"]
		for i in pts.size() - 1:
			var a := pts[i]
			var b := pts[i + 1]
			var side := (b - a).normalized().orthogonal()
			for s in [-1.0, 1.0]:
				if _hash(a.x * s, a.y) < 0.55:
					continue
				var p: Vector2 = a + side * s * (float(path["width"]) * 0.5 + rng.randf_range(0.25, 0.6))
				_tuft_group(root, p, rng.randi_range(1, 3), 0.5)
	# At the foot of the trees and rocks.
	for p3 in _placed:
		_tuft_group(root, Vector2(p3.x, p3.z) + Vector2.from_angle(rng.randf() * TAU) * 1.0, rng.randi_range(2, 4), 0.7)
	# Next to the houses' yards: tufts, bushes and a flower bed of a single color.
	for house in data["houses"]:
		var c := Vector2(house["pos"][0], house["pos"][1])
		var half := Vector2(house["size"][0], house["size"][1]) * 0.5 + Vector2.ONE * float(house["yard"]) * 0.5
		for corner in [Vector2(-1, -1), Vector2(1, -1), Vector2(-1, 1), Vector2(1, 1)]:
			var p: Vector2 = c + corner * (half + Vector2(0.6, 0.6))
			if rng.randf() < 0.5:
				_add_plant(root, Stylized.bush(rng), p, 1.3)
			_flower_patch(root, p + Vector2(corner.x * 0.8, 0), rng.randi_range(3, 6))
	# Edge of the ark meadow: tufts and flowers here and there, where the grass isn't trampled anymore.
	var ark: Dictionary = data["ark"]
	for k in 44:
		var a := TAU * k / 44.0 + rng.randf_range(-0.05, 0.05)
		var p := Vector2(ark["center"][0], ark["center"][1]) + Vector2(cos(a) * ark["semi_axes"][0] * 1.1,
				sin(a) * ark["semi_axes"][1] * 1.18)
		if _hash(p.x, p.y) < 0.35:
			continue
		_tuft_group(root, p, rng.randi_range(2, 4), 0.6)
		if k % 5 == 0:
			_flower_patch(root, p + Vector2.from_angle(a) * 1.2, rng.randi_range(3, 6))
	# Meadows: some flower beds and tufts in the darker grass patches.
	var span: Array = data["valley"]["semi_axes"]
	for k in 26 * int(span[0] * span[1] / 2600.0):
		var p := Vector2(rng.randf_range(-span[0], span[0]), rng.randf_range(-span[1], span[1]))
		if patches.get_noise_2d(p.x, p.y) > 0.15 and is_open_ground(p.x, p.y, 1.5):
			_flower_patch(root, p, rng.randi_range(4, 8))
			_tuft_group(root, p + Vector2(1.2, 0.4), rng.randi_range(2, 4), 0.8)
	_build_grass()


func _tuft_group(root: Node3D, center: Vector2, count: int, spread: float) -> void:
	for i in count:
		var p := center + Vector2.from_angle(rng.randf() * TAU) * rng.randf_range(0.0, spread)
		if is_open_ground(p.x, p.y, 0.1):
			_add_plant(root, Stylized.tuft(rng), p, rng.randf_range(0.7, 1.1))


## A flower bed of one color, the way they really grow.
func _flower_patch(root: Node3D, center: Vector2, count: int) -> void:
	var color := rng.randi_range(0, Stylized.FLOWERS.size() - 1)
	for i in count:
		var p := center + Vector2.from_angle(rng.randf() * TAU) * rng.randf_range(0.0, 0.9)
		if is_open_ground(p.x, p.y, 0.1):
			_add_plant(root, Stylized.flower_of(color), p, rng.randf_range(1.6, 2.1))


func _add_plant(root: Node3D, plant: Node3D, p: Vector2, plant_scale: float) -> void:
	plant.position = Vector3(p.x, height_at(p.x, p.y) - 0.02, p.y)
	plant.rotation.y = rng.randf() * TAU
	plant.scale = Vector3.ONE * plant_scale
	root.add_child(plant)


## Short grass: only in the meadow patches and along the edges, never on paths, plaza or
## yards. In 12 × 12 m chunks that are drawn near the camera.
func _build_grass() -> void:
	var mesh := Stylized.mesh("grass_0", func(st: SurfaceTool, r: RandomNumberGenerator, _v: int) -> void:
		Stylized.tuft_blades(st, r, 5, 0.26))
	var mat := Stylized.material(0.05, 0.3)
	var root := Node3D.new()
	root.name = "Grass"
	add_child(root)
	var chunk := 12.0
	var span: Array = data["valley"]["semi_axes"]
	var cx := -float(span[0])
	while cx < float(span[0]):
		var cz := -float(span[1])
		while cz < float(span[1]):
			_grass_chunk(root, mesh, mat, Vector2(cx + chunk * 0.5, cz + chunk * 0.5), chunk)
			cz += chunk
		cx += chunk


func _grass_chunk(root: Node3D, mesh: Mesh, mat: Material, center: Vector2, size: float) -> void:
	var transforms: Array[Transform3D] = []
	var base := Vector3(center.x, height_at(center.x, center.y), center.y)
	for i in int(size * size * 1.6):
		var x := center.x + rng.randf_range(-size * 0.5, size * 0.5)
		var z := center.y + rng.randf_range(-size * 0.5, size * 0.5)
		# More grass in the dark patches and along the edges of paths and river.
		var density := smoothstep(0.0, 0.45, patches.get_noise_2d(x, z))
		density = maxf(density, 1.0 - smoothstep(0.3, 1.4, path_distance(x, z)))
		if rng.randf() > density or not is_open_ground(x, z, 0.15):
			continue
		var basis := Basis(Vector3.UP, rng.randf() * TAU).scaled(Vector3.ONE * rng.randf_range(0.9, 1.4))
		transforms.append(Transform3D(basis, Vector3(x, height_at(x, z) - 0.03, z) - base))
	if transforms.is_empty():
		return
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.mesh = mesh
	mm.instance_count = transforms.size()
	for i in transforms.size():
		mm.set_instance_transform(i, transforms[i])
	var mmi := MultiMeshInstance3D.new()
	mmi.multimesh = mm
	mmi.material_override = mat
	mmi.position = base
	mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	mmi.visibility_range_end = 48.0
	mmi.visibility_range_end_margin = 10.0
	mmi.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_SELF
	root.add_child(mmi)


func _build_clouds(amount: int) -> void:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(1, 1, 1)
	mat.roughness = 1.0
	mat.emission_enabled = true
	mat.emission = Color(0.6, 0.6, 0.65)
	for i in amount:
		var cloud := Node3D.new()
		cloud.position = Vector3(rng.randf_range(area_min.x - 60, area_max.x + 60), rng.randf_range(30, 42),
				rng.randf_range(area_min.y - 40, area_max.y))
		for j in rng.randi_range(4, 7):
			var puff := MeshInstance3D.new()
			var sphere := SphereMesh.new()
			var r := rng.randf_range(2.5, 5.0)
			sphere.radius = r
			sphere.height = r * 1.4
			sphere.radial_segments = 10
			sphere.rings = 5
			puff.mesh = sphere
			puff.material_override = mat
			puff.position = Vector3(j * 3.2 - 8.0 + rng.randf_range(-1, 1), rng.randf_range(0, 1.8), rng.randf_range(-2, 2))
			puff.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			cloud.add_child(puff)
		add_child(cloud)
		_clouds.append(cloud)


# --- Curves -------------------------------------------------------------------

## Smooth curve (Catmull-Rom) through the control points, with `steps` segments between each pair.
func _curve(points: Array, steps: int) -> PackedVector2Array:
	var pts: Array[Vector2] = []
	for p in points:
		pts.append(Vector2(p[0], p[1]))
	var out := PackedVector2Array()
	for i in pts.size() - 1:
		var p0 := pts[maxi(i - 1, 0)]
		var p1 := pts[i]
		var p2 := pts[i + 1]
		var p3 := pts[mini(i + 2, pts.size() - 1)]
		for s in steps:
			var t := float(s) / steps
			var t2 := t * t
			var t3 := t2 * t
			out.append(0.5 * ((2.0 * p1) + (p2 - p0) * t + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t2
					+ (3.0 * p1 - p0 - 3.0 * p2 + p3) * t3))
	out.append(pts[-1])
	return out


func _polyline_distance(p: Vector2, pts: PackedVector2Array) -> float:
	var best := INF
	for i in pts.size() - 1:
		var a := pts[i]
		var ab := pts[i + 1] - a
		var t := clampf((p - a).dot(ab) / ab.length_squared(), 0.0, 1.0)
		best = minf(best, p.distance_squared_to(a + ab * t))
	return sqrt(best)


func _bounds(pts: PackedVector2Array) -> Rect2:
	var r := Rect2(pts[0], Vector2.ZERO)
	for p in pts:
		r = r.expand(p)
	return r
