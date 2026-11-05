extends Node3D
## Casas y objetos de la aldea (modelos de herramientas/blender/casas.py), colocados según
## data/aldea.json: cada casa mira a la plaza y tiene en su patio lo de una casa de verdad (horno de
## pan, cántaros, cesta, leña, macetas) y en el techo lo que se pone a secar (alfombras, sacos); cada
## familia tiene algo propio (el telar de la tejedora, el puesto del alfarero, ropa tendida); en la
## plaza-mercado, toldos, fogata, mesas, el pozo y bancos donde no pisa ningún camino; los corrales con
## su bebedero y la cerca abierta hacia la aldea; huertos y campos en surcos; el puente de piedra.

const Piezas := preload("res://scripts/piezas.gd")
const Stylized := preload("res://scripts/stylized.gd")
const Fuego := preload("res://scripts/fuego.gd")

var world  ## world.gd
var rng := RandomNumberGenerator.new()


func _ready() -> void:
	rng.seed = 77
	_build_houses()
	_build_plaza()
	_build_corrals()
	_build_walls()
	_build_bridge()
	_build_fields()


# --- Casas --------------------------------------------------------------------

func _build_houses() -> void:
	for house in world.data["casas"]:
		var angle: float = world.house_angle(house)
		var c := Vector2(house["pos"][0], house["pos"][1])
		_piece(house["modelo"], c, angle, "casa")
		var front: float = world.house_front(house)
		var cx := float(house["centro_x"])
		var half_w := float(house["tam"][0]) * 0.5
		var depth := float(house["tam"][1]) * 0.5
		var door := Vector2(house["puerta"][0], house["puerta"][1])
		var local := func(x: float, y: float) -> Vector2: return world.house_point(house, Vector2(x, y))
		match house["modelo"]:
			"CasaNoe":
				# Patio de Noé, dentro del murete (referencias/casa_noe.jpg): horno, leña, banco,
				# cántaros, cesta y el telar.
				_piece("Horno", local.call(-2.9, 5.5), angle + 0.4)
				_piece("Lena", local.call(3.8, 4.1), angle + PI * 0.5)
				_piece("Banco", local.call(0.1, 3.3), angle)
				_jars(local.call(-3.1, 3.1), angle, 3)
				_small_group("Cesta", local.call(2.6, 3.2), angle)
				_piece("Telar", local.call(2.9, 5.9), angle + PI)
			"CasaB":
				# Patio delante, dentro del murete.
				_piece("Horno", local.call(-1.9, 3.6), angle + rng.randf_range(-0.5, 0.5))
				_jars(local.call(door.x + 1.1, door.y + 0.4), angle, rng.randi_range(1, 3))
				_piece("Lena", local.call(cx, -depth - 0.7), angle)
			"CasaC":
				# Patio detrás: el horno y la leña quedan ahí; delante, el poyo con cántaros.
				_piece("Horno", local.call(-1.2, -3.0), angle + rng.randf_range(-0.5, 0.5))
				_piece("Lena", local.call(1.2, -3.1), angle)
				_jars(local.call(door.x + 1.2, front + 0.3), angle, rng.randi_range(1, 3))
			_:
				_piece("Horno", local.call(cx - half_w + 0.8, front + 1.1), angle + rng.randf_range(-0.5, 0.5))
				_jars(local.call(door.x + 1.0, front + 0.4), angle, rng.randi_range(1, 3))
				_piece("Lena", local.call(cx, -depth - 0.7), angle)
		_small_group("Cesta", local.call(door.x - 1.0, door.y + 0.45), angle)
		if house.get("puesto", false):
			_piece("Puesto", local.call(1.8, front + 2.4), angle)
		_house_details(house, angle, local)


## Lo que hace que cada casa parezca habitada: macetas junto a la puerta, sacos, cosas secándose en
## el techo (en el sitio libre de escaleras y toldos) y, según la familia, ropa tendida o el telar.
func _house_details(house: Dictionary, angle: float, local: Callable) -> void:
	var front: float = world.house_front(house)
	var half_w := float(house["tam"][0]) * 0.5
	var door := Vector2(house["puerta"][0], house["puerta"][1])
	var rug := Vector2(house["alfombra"][0], house["alfombra"][1])
	# Macetas a los lados de la puerta (en la de Noé, sobre el murete del patio).
	if house["modelo"] == "CasaNoe":
		for x in [-2.6, 2.4, 3.8]:
			_potted_plant(local.call(x, front - 0.1), 0.95)
	else:
		for side in [-1.0, 1.0]:
			if rng.randf() < 0.75:
				_potted_plant(local.call(door.x + side * 0.95, door.y + 0.35), 0.0)
	# Sacos de grano junto a la casa.
	_small_group("Saco", local.call(-half_w + 0.6, door.y + 0.35), angle + rng.randf_range(-1, 1))
	# En el techo: una alfombra secándose y algún cántaro, saco o cesta al lado.
	_on_roof(_piece("Alfombra", local.call(rug.x, rug.y), angle + rng.randf_range(-0.3, 0.3), ""),
			float(house["techo"]))
	_on_roof(_small_group(["Cantaro", "Saco", "Cesta"][rng.randi() % 3], local.call(rug.x - 0.5, rug.y - 1.0),
			rng.randf() * TAU, 0.5), float(house["techo"]))
	match house["id"]:
		"jafet":
			_piece("Tendedero", local.call(half_w + 1.6, 0.6), angle + PI * 0.5, "")
		"vecina_tejedora":
			_piece("Telar", local.call(-1.6, front + 1.2), angle + 0.3)
			_piece("Tendedero", local.call(-half_w - 1.6, -0.4), angle + PI * 0.5, "")
		"noe":
			_piece("Tendedero", local.call(-5.6, -0.8), angle + PI * 0.5, "")


func _on_roof(node: Node3D, roof_height: float) -> void:
	node.position.y = world.height_at(node.position.x, node.position.z) + roof_height


## Maceta de barro con un arbusto o flores. raise: altura de lo que tiene debajo (un murete).
func _potted_plant(p: Vector2, raise: float) -> void:
	var pot := _piece("Maceta", p, rng.randf() * TAU, "")
	pot.position.y += raise
	var bushy := rng.randf() < 0.5
	var plant: Node3D = Stylized.bush(rng) if bushy else Stylized.flower_of(rng.randi_range(0, 4))
	plant.scale = Vector3.ONE * (0.45 if bushy else 1.6)
	plant.position = pot.position + Vector3(0, 0.28, 0)
	add_child(plant)


## Cántaros junto a una pared: el grupo generado, más grande cuantos más cántaros se quieren.
func _jars(center: Vector2, angle: float, count: int) -> void:
	var jars := _piece("Cantaro", center, angle + rng.randf_range(-0.6, 0.6), "")
	jars.scale = Vector3.ONE * (0.85 + 0.15 * count)    # El cántaro grande, a la altura de la rodilla o más.


## Cestas o sacos: los grupos generados, algo más chicos.
func _small_group(piece: String, p: Vector2, angle: float, size := 0.7) -> Node3D:
	var node := _piece(piece, p, angle, "")
	node.scale = Vector3.ONE * size
	return node


# --- Plaza --------------------------------------------------------------------

func _build_plaza() -> void:
	var plaza: Dictionary = world.data["plaza"]
	var c := Vector2(plaza["centro"][0], plaza["centro"][1])
	var well := Vector2(plaza["pozo"][0], plaza["pozo"][1])
	_piece("Pozo", well, 0.3)
	_jars(well + Vector2(1.1, 0.5), 0.0, 2)
	# Mercado alrededor del borde, cada puesto con el mostrador hacia el centro; la fogata y mesas largas
	# con sus bancos. Los puestos de lona traen su mercancía; a los de madera se les pone un cántaro.
	for t in plaza["tiendas"]:
		var p := Vector2(t[0], t[1])
		var to := c - p
		var facing := atan2(to.x, to.y)
		var stall := _piece(t[2], p, facing)
		stall.rotation.y += rng.randf_range(-0.08, 0.08)
		if not String(t[2]).begins_with("Lona"):
			_jars(p + to.normalized().orthogonal() * 1.9, 0.0, 1)
	# Bultos del mercado entre los puestos: sacos, cestas y cántaros.
	for g in plaza.get("bultos", []):
		var p := Vector2(g[0], g[1])
		if g[2] == "Cantaro":
			_jars(p, rng.randf() * TAU, rng.randi_range(2, 3))
		else:
			_small_group(g[2], p, rng.randf() * TAU, rng.randf_range(0.95, 1.15))
	# Ambulantes por dentro del mercado, mirando al centro: carretas, mantas en el suelo, cajas y barriles.
	for t in plaza.get("ambulantes", []):
		var p := Vector2(t[0], t[1])
		var to := c - p
		_piece(t[2], p, atan2(to.x, to.y) + rng.randf_range(-0.3, 0.3), "" if t[2].begins_with("Manta") else "objeto")
	# Fogatas con asientos alrededor, todos mirando al fuego y del lado que da al centro de la plaza:
	# dos troncos tumbados y dos tocones juntos; la leña, detrás.
	for f in plaza["fogatas"]:
		var fire := Vector2(f[0], f[1])
		var campfire := _piece("Fogata", fire, 0.0, "")
		campfire.add_child(Fuego.new())
		var to_plaza := (c - fire).angle()
		for seat in [["TroncoAsiento", -0.15, 1.45], ["TroncoAsiento", 0.95, 1.45], ["Tocon", -1.0, 1.3],
				["Tocon", -1.55, 1.35], ["Lena", 3.55, 1.4]]:
			var offset: Vector2 = Vector2.from_angle(to_plaza + seat[1]) * seat[2]
			_piece(seat[0], fire + offset, atan2(-offset.x, -offset.y), "")
	for m in plaza["mesas"]:
		var p := Vector2(m[0], m[1])
		var turn := (p - c).angle() + PI * 0.5
		_piece("Mesa", p, -turn)
		for side in [-1.0, 1.0]:
			# El respaldo del banco va hacia fuera: el asiento mira a la mesa.
			var offset: Vector2 = Vector2.from_angle(turn + PI * 0.5) * 0.85 * side
			_piece("Banco", p + offset, atan2(-offset.x, -offset.y))
	# En medio, la isla de pasto con el olivo (lo pone world.gd, en arboles_de_sombra): bancos alrededor
	# con el respaldo hacia el árbol, y matas, arbustos y flores en su borde.
	var isle: Dictionary = plaza["isla"]
	var ic := Vector2(isle["centro"][0], isle["centro"][1])
	var ir := float(isle["radio"])
	for k in int(isle["bancos"]):
		var dir := Vector2.from_angle(TAU * k / float(isle["bancos"]) + 0.6)
		_piece("Banco", ic + dir * (ir + 0.5), atan2(dir.x, dir.y))
	for k in 14:
		var a := TAU * k / 14.0 + rng.randf_range(-0.12, 0.12)
		var p := ic + Vector2.from_angle(a) * ir * rng.randf_range(0.6, 0.85)
		var plant: Node3D = Stylized.bush(rng) if k % 3 == 0 else (Stylized.tuft(rng) if k % 3 == 1
				else Stylized.flower_of(k % Stylized.FLOWERS.size()))
		plant.scale = Vector3.ONE * (0.7 if k % 3 == 0 else 1.6)
		plant.position = Vector3(p.x, world.height_at(p.x, p.y), p.y)
		plant.rotation.y = rng.randf() * TAU
		add_child(plant)

## Muretes de adobe que cierran los patios que comparten las casas de un mismo grupo.
func _build_walls() -> void:
	for wall in world.data["muros"]:
		for i in wall.size() - 1:
			var a := Vector2(wall[i][0], wall[i][1])
			var b := Vector2(wall[i + 1][0], wall[i + 1][1])
			var n := maxi(1, int(round(a.distance_to(b) / 2.0)))
			var dir := (b - a).normalized()
			for k in n:
				var p := a.lerp(b, (k + 0.5) / n)
				_piece("Murete", p, -dir.angle()).scale.x = a.distance_to(b) / n / 2.0


# --- Corral y campos ----------------------------------------------------------

func _build_corrals() -> void:
	for corral in world.data["corrales"]:
		_build_corral(corral)


func _build_corral(corral: Dictionary) -> void:
	var c := Vector2(corral["centro"][0], corral["centro"][1])
	var r := float(corral["radio"])
	var plaza := Vector2(world.data["plaza"]["centro"][0], world.data["plaza"]["centro"][1])
	var gate := (plaza - c).angle()            # La entrada mira hacia la aldea.
	var count := int(ceil(TAU * r / 2.0))
	for i in count:
		var a := TAU * (i + 0.5) / count
		if absf(angle_difference(a, gate)) < PI / count:
			continue
		var p := c + Vector2.from_angle(a) * r
		_piece("Cerca", p, -a - PI * 0.5)    # El tramo, tangente al círculo.
	_piece("Abrevadero", c + Vector2.from_angle(gate + PI) * (r - 1.4), -(gate + PI) - PI * 0.5)
	_small_group("Saco", c + Vector2.from_angle(gate + 2.2) * (r - 1.0), rng.randf() * TAU)


func _build_fields() -> void:
	var wheat := Stylized.mesh("trigo_0", Callable(Stylized, "build_wheat"))
	for f in world.data["campos"]:
		var rows := int(f["surcos"])
		for row in rows:
			_row(f, row, rows, wheat, 0.42)
		_fence_side(f, true)
	# Huertos: cada fila de una hortaliza (lechugas, cebollas, calabazas), cercados por los cuatro
	# lados con la entrada hacia la aldea.
	var crops := [Stylized.mesh("lechuga_0", Callable(Stylized, "build_lettuce")),
			Stylized.mesh("cebolla_0", Callable(Stylized, "build_onion")),
			Stylized.mesh("calabaza_0", Callable(Stylized, "build_squash"))]
	for f in world.data["huertos"]:
		var rows := int(f["filas"])
		for row in rows:
			_row(f, row, rows, crops[row % crops.size()], 0.55)
		_fence_side(f, true)
		_fence_side(f, false)
		_fence_ends(f)


## Una fila de plantas a lo largo de un campo o huerto (un MultiMesh por fila).
func _row(f: Dictionary, row: int, rows: int, mesh: Mesh, spacing: float) -> void:
	var c := Vector2(f["centro"][0], f["centro"][1])
	var size := Vector2(f["tam"][0], f["tam"][1])
	var turn := deg_to_rad(float(f["giro"]))
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


## Cerca en un lado largo: el que da a la plaza (con un paso en medio) o el de enfrente.
func _fence_side(f: Dictionary, toward_plaza: bool) -> void:
	var c := Vector2(f["centro"][0], f["centro"][1])
	var size := Vector2(f["tam"][0], f["tam"][1])
	var turn := deg_to_rad(float(f["giro"]))
	var plaza := Vector2(world.data["plaza"]["centro"][0], world.data["plaza"]["centro"][1])
	var side := Vector2(0, size.y * 0.5 + 0.6)
	if (c + side.rotated(turn)).distance_to(plaza) > (c - side.rotated(turn)).distance_to(plaza):
		side = -side
	if not toward_plaza:
		side = -side
	var x := -size.x * 0.5 + 1.0
	while x < size.x * 0.5 - 0.9:
		if absf(x) > 1.5 or not toward_plaza:
			_piece("Cerca", c + (side + Vector2(x, 0)).rotated(turn), -turn)
		x += 2.05


## Cerca en los dos lados cortos.
func _fence_ends(f: Dictionary) -> void:
	var c := Vector2(f["centro"][0], f["centro"][1])
	var size := Vector2(f["tam"][0], f["tam"][1])
	var turn := deg_to_rad(float(f["giro"]))
	for sx in [-1.0, 1.0]:
		var y := -size.y * 0.5 + 0.4
		while y < size.y * 0.5 - 0.3:
			_piece("Cerca", c + Vector2(sx * (size.x * 0.5 + 0.6), y).rotated(turn), -turn - PI * 0.5)
			y += 2.05


## Puentes de piedra y madera sobre el río, a lo largo de la calle que cruza; se sube por su tablero
## (colisión con su forma). El modelo mide 9 m: se estira hasta el largo de cada puente.
func _build_bridge() -> void:
	for b in world.data["puentes"]:
		var bridge := _piece("PuentePiedra", Vector2(b["centro"][0], b["centro"][1]), deg_to_rad(float(b["giro"])), "")
		bridge.position.y = 0.0
		bridge.scale.x = float(b["largo"]) / 9.0
		var mi := bridge as MeshInstance3D
		var body := StaticBody3D.new()
		var col := CollisionShape3D.new()
		col.shape = mi.mesh.create_trimesh_shape()
		body.add_child(col)
		mi.add_child(body)


# --- Piezas -------------------------------------------------------------------

## Pone una copia de una pieza en el suelo. collision: "casa" (forma exacta), "" (sin colisión) o
## cualquier otra cosa (forma convexa).
func _piece(piece: String, p: Vector2, angle: float, collision := "objeto") -> Node3D:
	var node: Node3D = Piezas.make(piece)
	node.position = Vector3(p.x, world.height_at(p.x, p.y), p.y)
	node.rotation = Vector3(0, angle, 0)
	add_child(node)
	if collision != "":
		var mi := node as MeshInstance3D
		if mi == null:
			mi = node.find_children("*", "MeshInstance3D", true, false)[0]
		var body := StaticBody3D.new()
		var col := CollisionShape3D.new()
		col.shape = mi.mesh.create_trimesh_shape() if collision == "casa" else mi.mesh.create_convex_shape()
		body.add_child(col)
		mi.add_child(body)
	return node
