extends Node3D
## Houses and objects of the village (models from tools/blender/houses.py), placed according to
## data/village.json: each house faces the plaza and has in its yard what a real house has (bread
## oven, jugs, basket, firewood, flower pots) and on the roof what is put out to dry (rugs, sacks); each
## family has something of its own (the weaver's loom, the potter's stall, laundry hung out); in the
## market plaza, awnings, campfire, tables, the well and benches where no path runs; the pens with
## their trough and the fence open toward the village; gardens and fields in furrows; the stone bridge.

const Pieces := preload("res://scripts/pieces.gd")
const Stylized := preload("res://scripts/stylized.gd")
const Fire := preload("res://scripts/fire.gd")

var world  ## world.gd
var rng := RandomNumberGenerator.new()


func _ready() -> void:
	rng.seed = 77
	_build_houses()
	_build_plaza()
	_build_pens()
	_build_walls()
	_build_bridge()
	_build_fields()


# --- Houses -------------------------------------------------------------------

func _build_houses() -> void:
	for house in world.data["houses"]:
		var angle: float = world.house_angle(house)
		var c := Vector2(house["pos"][0], house["pos"][1])
		_piece(house["model"], c, angle, "house")
		var front: float = world.house_front(house)
		var cx := float(house["center_x"])
		var half_w := float(house["size"][0]) * 0.5
		var depth := float(house["size"][1]) * 0.5
		var door := Vector2(house["door"][0], house["door"][1])
		var local := func(x: float, y: float) -> Vector2: return world.house_point(house, Vector2(x, y))
		match house["model"]:
			"NoahHouse":
				# Noah's yard, inside the low wall (references/noah_house.jpg): oven, firewood, bench,
				# jugs, basket and the loom.
				_piece("Oven", local.call(-2.9, 5.5), angle + 0.4)
				_piece("Firewood", local.call(3.8, 4.1), angle + PI * 0.5)
				_piece("Bench", local.call(0.1, 3.3), angle)
				_jars(local.call(-3.1, 3.1), angle, 3)
				_small_group("Basket", local.call(2.6, 3.2), angle)
				_piece("Loom", local.call(2.9, 5.9), angle + PI)
			"HouseB":
				# Yard in front, inside the low wall.
				_piece("Oven", local.call(-1.9, 3.6), angle + rng.randf_range(-0.5, 0.5))
				_jars(local.call(door.x + 1.1, door.y + 0.4), angle, rng.randi_range(1, 3))
				_piece("Firewood", local.call(cx, -depth - 0.7), angle)
			"HouseC":
				# Yard behind: the oven and the firewood go there; in front, the stone bench with jugs.
				_piece("Oven", local.call(-1.2, -3.0), angle + rng.randf_range(-0.5, 0.5))
				_piece("Firewood", local.call(1.2, -3.1), angle)
				_jars(local.call(door.x + 1.2, front + 0.3), angle, rng.randi_range(1, 3))
			_:
				_piece("Oven", local.call(cx - half_w + 0.8, front + 1.1), angle + rng.randf_range(-0.5, 0.5))
				_jars(local.call(door.x + 1.0, front + 0.4), angle, rng.randi_range(1, 3))
				_piece("Firewood", local.call(cx, -depth - 0.7), angle)
		_small_group("Basket", local.call(door.x - 1.0, door.y + 0.45), angle)
		if house.get("stall", false):
			_piece("Stall", local.call(1.8, front + 2.4), angle)
		_house_details(house, angle, local)


## What makes each house look lived in: flower pots by the door, sacks, things drying on the roof
## (in the spot free of stairs and awnings) and, depending on the family, laundry hung out or the loom.
func _house_details(house: Dictionary, angle: float, local: Callable) -> void:
	var front: float = world.house_front(house)
	var half_w := float(house["size"][0]) * 0.5
	var door := Vector2(house["door"][0], house["door"][1])
	var rug := Vector2(house["rug"][0], house["rug"][1])
	# Flower pots on either side of the door (at Noah's, on the yard's low wall).
	if house["model"] == "NoahHouse":
		for x in [-2.6, 2.4, 3.8]:
			_potted_plant(local.call(x, front - 0.1), 0.95)
	else:
		for side in [-1.0, 1.0]:
			if rng.randf() < 0.75:
				_potted_plant(local.call(door.x + side * 0.95, door.y + 0.35), 0.0)
	# Grain sacks next to the house.
	_small_group("Sack", local.call(-half_w + 0.6, door.y + 0.35), angle + rng.randf_range(-1, 1))
	# On the roof: a rug drying and a jug, sack or basket beside it.
	_on_roof(_piece("Rug", local.call(rug.x, rug.y), angle + rng.randf_range(-0.3, 0.3), ""),
			float(house["roof"]))
	_on_roof(_small_group(["Jug", "Sack", "Basket"][rng.randi() % 3], local.call(rug.x - 0.5, rug.y - 1.0),
			rng.randf() * TAU, 0.5), float(house["roof"]))
	match house["id"]:
		"japheth":
			_piece("Clothesline", local.call(half_w + 1.6, 0.6), angle + PI * 0.5, "")
		"weaver_neighbor":
			_piece("Loom", local.call(-1.6, front + 1.2), angle + 0.3)
			_piece("Clothesline", local.call(-half_w - 1.6, -0.4), angle + PI * 0.5, "")
		"noah":
			_piece("Clothesline", local.call(-5.6, -0.8), angle + PI * 0.5, "")


func _on_roof(node: Node3D, roof_height: float) -> void:
	node.position.y = world.height_at(node.position.x, node.position.z) + roof_height


## Clay flower pot with a bush or flowers. raise: height of what's under it (a low wall).
func _potted_plant(p: Vector2, raise: float) -> void:
	var pot := _piece("FlowerPot", p, rng.randf() * TAU, "")
	pot.position.y += raise
	var bushy := rng.randf() < 0.5
	var plant: Node3D = Stylized.bush(rng) if bushy else Stylized.flower_of(rng.randi_range(0, 4))
	plant.scale = Vector3.ONE * (0.45 if bushy else 1.6)
	plant.position = pot.position + Vector3(0, 0.28, 0)
	add_child(plant)


## Jugs against a wall: the generated group, bigger the more jugs are wanted.
func _jars(center: Vector2, angle: float, count: int) -> void:
	var jars := _piece("Jug", center, angle + rng.randf_range(-0.6, 0.6), "")
	jars.scale = Vector3.ONE * (0.85 + 0.15 * count)    # The big jug, knee-high or more.


## Baskets or sacks: the generated groups, a bit smaller.
func _small_group(piece: String, p: Vector2, angle: float, size := 0.7) -> Node3D:
	var node := _piece(piece, p, angle, "")
	node.scale = Vector3.ONE * size
	return node


# --- Plaza --------------------------------------------------------------------

func _build_plaza() -> void:
	var plaza: Dictionary = world.data["plaza"]
	var c := Vector2(plaza["center"][0], plaza["center"][1])
	var well := Vector2(plaza["well"][0], plaza["well"][1])
	_piece("Well", well, 0.3)
	_jars(well + Vector2(1.1, 0.5), 0.0, 2)
	# Market around the edge, each stall with its counter toward the center; the campfire and long tables
	# with their benches. The tarp stalls bring their own goods; the wooden ones get a jug.
	for t in plaza["tents"]:
		var p := Vector2(t[0], t[1])
		var to := c - p
		var facing := atan2(to.x, to.y)
		var stall := _piece(t[2], p, facing)
		stall.rotation.y += rng.randf_range(-0.08, 0.08)
		if not String(t[2]).begins_with("Tarp"):
			_jars(p + to.normalized().orthogonal() * 1.9, 0.0, 1)
	# Market bundles between the stalls: sacks, baskets and jugs.
	for g in plaza.get("bundles", []):
		var p := Vector2(g[0], g[1])
		if g[2] == "Jug":
			_jars(p, rng.randf() * TAU, rng.randi_range(2, 3))
		else:
			_small_group(g[2], p, rng.randf() * TAU, rng.randf_range(0.95, 1.15))
	# Wanderers inside the market, facing the center: carts, blankets on the ground, crates and barrels.
	for t in plaza.get("wanderers", []):
		var p := Vector2(t[0], t[1])
		var to := c - p
		_piece(t[2], p, atan2(to.x, to.y) + rng.randf_range(-0.3, 0.3), "" if t[2].begins_with("Blanket") else "object")
	# Campfires with seats around them, all facing the fire and on the side toward the center of the plaza:
	# two logs lying down and two stumps together; the firewood, behind.
	for f in plaza["campfires"]:
		var fire := Vector2(f[0], f[1])
		var campfire := _piece("Campfire", fire, 0.0, "")
		campfire.add_child(Fire.new())
		var to_plaza := (c - fire).angle()
		for seat in [["LogSeat", -0.15, 1.45], ["LogSeat", 0.95, 1.45], ["Stump", -1.0, 1.3],
				["Stump", -1.55, 1.35], ["Firewood", 3.55, 1.4]]:
			var offset: Vector2 = Vector2.from_angle(to_plaza + seat[1]) * seat[2]
			_piece(seat[0], fire + offset, atan2(-offset.x, -offset.y), "")
	for m in plaza["tables"]:
		var p := Vector2(m[0], m[1])
		var turn := (p - c).angle() + PI * 0.5
		_piece("Table", p, -turn)
		for side in [-1.0, 1.0]:
			# The bench's backrest faces out: the seat faces the table.
			var offset: Vector2 = Vector2.from_angle(turn + PI * 0.5) * 0.85 * side
			_piece("Bench", p + offset, atan2(-offset.x, -offset.y))
	# In the middle, the grass island with the olive tree (world.gd places it, in shade_trees): benches
	# around it with the backrest toward the tree, and tufts, bushes and flowers on its edge.
	var isle: Dictionary = plaza["island"]
	var ic := Vector2(isle["center"][0], isle["center"][1])
	var ir := float(isle["radius"])
	for k in int(isle["benches"]):
		var dir := Vector2.from_angle(TAU * k / float(isle["benches"]) + 0.6)
		_piece("Bench", ic + dir * (ir + 0.5), atan2(dir.x, dir.y))
	for k in 14:
		var a := TAU * k / 14.0 + rng.randf_range(-0.12, 0.12)
		var p := ic + Vector2.from_angle(a) * ir * rng.randf_range(0.6, 0.85)
		var plant: Node3D = Stylized.bush(rng) if k % 3 == 0 else (Stylized.tuft(rng) if k % 3 == 1
				else Stylized.flower_of(k % Stylized.FLOWERS.size()))
		plant.scale = Vector3.ONE * (0.7 if k % 3 == 0 else 1.6)
		plant.position = Vector3(p.x, world.height_at(p.x, p.y), p.y)
		plant.rotation.y = rng.randf() * TAU
		add_child(plant)

## Low adobe walls that close off the yards shared by the houses of one group.
func _build_walls() -> void:
	for wall in world.data["walls"]:
		for i in wall.size() - 1:
			var a := Vector2(wall[i][0], wall[i][1])
			var b := Vector2(wall[i + 1][0], wall[i + 1][1])
			var n := maxi(1, int(round(a.distance_to(b) / 2.0)))
			var dir := (b - a).normalized()
			for k in n:
				var p := a.lerp(b, (k + 0.5) / n)
				_piece("LowWall", p, -dir.angle()).scale.x = a.distance_to(b) / n / 2.0


# --- Pens and fields -----------------------------------------------------------

func _build_pens() -> void:
	for pen in world.data["pens"]:
		_build_pen(pen)


func _build_pen(pen: Dictionary) -> void:
	var c := Vector2(pen["center"][0], pen["center"][1])
	var r := float(pen["radius"])
	var plaza := Vector2(world.data["plaza"]["center"][0], world.data["plaza"]["center"][1])
	var gate := (plaza - c).angle()            # The gate faces the village.
	var count := int(ceil(TAU * r / 2.0))
	for i in count:
		var a := TAU * (i + 0.5) / count
		if absf(angle_difference(a, gate)) < PI / count:
			continue
		var p := c + Vector2.from_angle(a) * r
		_piece("Fence", p, -a - PI * 0.5)    # The section, tangent to the circle.
	_piece("Trough", c + Vector2.from_angle(gate + PI) * (r - 1.4), -(gate + PI) - PI * 0.5)
	_small_group("Sack", c + Vector2.from_angle(gate + 2.2) * (r - 1.0), rng.randf() * TAU)


func _build_fields() -> void:
	var wheat := Stylized.mesh("wheat_0", Callable(Stylized, "build_wheat"))
	for f in world.data["fields"]:
		var rows := int(f["furrows"])
		for row in rows:
			_row(f, row, rows, wheat, 0.42)
		_fence_side(f, true)
	# Gardens: each row of one vegetable (lettuces, onions, squashes), fenced on all four
	# sides with the gate toward the village.
	var crops := [Stylized.mesh("lettuce_0", Callable(Stylized, "build_lettuce")),
			Stylized.mesh("onion_0", Callable(Stylized, "build_onion")),
			Stylized.mesh("squash_0", Callable(Stylized, "build_squash"))]
	for f in world.data["gardens"]:
		var rows := int(f["rows"])
		for row in rows:
			_row(f, row, rows, crops[row % crops.size()], 0.55)
		_fence_side(f, true)
		_fence_side(f, false)
		_fence_ends(f)


## A row of plants along a field or garden (one MultiMesh per row).
func _row(f: Dictionary, row: int, rows: int, mesh: Mesh, spacing: float) -> void:
	var c := Vector2(f["center"][0], f["center"][1])
	var size := Vector2(f["size"][0], f["size"][1])
	var turn := deg_to_rad(float(f["rotation"]))
	var transforms: Array[Transform3D] = []
	var y := -size.y * 0.5 + (row + 0.5) * size.y / rows
	var x := -size.x * 0.5 + 0.4
	while x < size.x * 0.5 - 0.4:
		var p := c + Vector2(x, y + rng.randf_range(-0.08, 0.08)).rotated(turn)
		var basis := Basis(Vector3.UP, rng.randf() * TAU).scaled(Vector3.ONE * rng.randf_range(0.85, 1.15))
		transforms.append(Transform3D(basis, Vector3(p.x, world.height_at(p.x, p.y) - 0.02, p.y)))
		x += spacing * rng.randf_range(0.85, 1.15)
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.mesh = mesh
	mm.instance_count = transforms.size()
	for i in transforms.size():
		mm.set_instance_transform(i, transforms[i])
	var mmi := MultiMeshInstance3D.new()
	mmi.multimesh = mm
	mmi.material_override = Stylized.material(0.05, 0.7)
	add_child(mmi)


## Fence on a long side: the one facing the plaza (with a gap in the middle) or the opposite one.
func _fence_side(f: Dictionary, toward_plaza: bool) -> void:
	var c := Vector2(f["center"][0], f["center"][1])
	var size := Vector2(f["size"][0], f["size"][1])
	var turn := deg_to_rad(float(f["rotation"]))
	var plaza := Vector2(world.data["plaza"]["center"][0], world.data["plaza"]["center"][1])
	var side := Vector2(0, size.y * 0.5 + 0.6)
	if (c + side.rotated(turn)).distance_to(plaza) > (c - side.rotated(turn)).distance_to(plaza):
		side = -side
	if not toward_plaza:
		side = -side
	var x := -size.x * 0.5 + 1.0
	while x < size.x * 0.5 - 0.9:
		if absf(x) > 1.5 or not toward_plaza:
			_piece("Fence", c + (side + Vector2(x, 0)).rotated(turn), -turn)
		x += 2.05


## Fence on both short sides.
func _fence_ends(f: Dictionary) -> void:
	var c := Vector2(f["center"][0], f["center"][1])
	var size := Vector2(f["size"][0], f["size"][1])
	var turn := deg_to_rad(float(f["rotation"]))
	for sx in [-1.0, 1.0]:
		var y := -size.y * 0.5 + 0.4
		while y < size.y * 0.5 - 0.3:
			_piece("Fence", c + Vector2(sx * (size.x * 0.5 + 0.6), y).rotated(turn), -turn - PI * 0.5)
			y += 2.05


## Stone and wood bridges over the river, along the street that crosses it; you walk up onto its deck
## (collision with its shape). The model is 9 m long: it is stretched to each bridge's length.
func _build_bridge() -> void:
	for b in world.data["bridges"]:
		var bridge := _piece("StoneBridge", Vector2(b["center"][0], b["center"][1]), deg_to_rad(float(b["rotation"])), "")
		bridge.position.y = 0.0
		bridge.scale.x = float(b["length"]) / 9.0
		var mi := bridge as MeshInstance3D
		var body := StaticBody3D.new()
		var col := CollisionShape3D.new()
		col.shape = mi.mesh.create_trimesh_shape()
		body.add_child(col)
		mi.add_child(body)


# --- Pieces -------------------------------------------------------------------

## Puts a copy of a piece on the ground. collision: "house" (exact shape), "" (no collision) or
## anything else (convex shape).
func _piece(piece: String, p: Vector2, angle: float, collision := "object") -> Node3D:
	var node: Node3D = Pieces.make(piece)
	node.position = Vector3(p.x, world.height_at(p.x, p.y), p.y)
	node.rotation = Vector3(0, angle, 0)
	add_child(node)
	if collision != "":
		var mi := node as MeshInstance3D
		if mi == null:
			mi = node.find_children("*", "MeshInstance3D", true, false)[0]
		var body := StaticBody3D.new()
		var col := CollisionShape3D.new()
		col.shape = mi.mesh.create_trimesh_shape() if collision == "house" else mi.mesh.create_convex_shape()
		body.add_child(col)
		mi.add_child(body)
	return node
