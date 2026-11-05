extends Node3D
## Main scene of chapter 1: sets up the environment, the island, the ark, Noah,
## the camera and the interface.

const World := preload("res://scripts/world.gd")
const ArkSite := preload("res://scripts/ark_site.gd")
const Player := preload("res://scripts/player.gd")
const CameraRig := preload("res://scripts/camera_rig.gd")
const Hud := preload("res://scripts/hud.gd")
const Debug := preload("res://scripts/debug.gd")
const Animal := preload("res://scripts/animal.gd")
const Villager := preload("res://scripts/villager.gd")


func _ready() -> void:
	_setup_environment()

	var world := World.new()
	world.name = "Island"
	add_child(world)

	var ark := ArkSite.new()
	ark.name = "Ark"
	ark.position = world.ark_position()
	add_child(ark)

	_spawn_animals(world)
	_spawn_villagers(world)

	var player := Player.new()
	player.name = "Noah"
	player.world = world
	player.position = world.spawn_point()
	if Game.args.has("pos"):
		var xz: PackedStringArray = Game.args["pos"].split(",")
		player.position = Vector3(float(xz[0]), 0, float(xz[1]))
		player.position.y = world.height_at(player.position.x, player.position.z) + 0.5
	add_child(player)
	player.add_child(_floating_motes())

	var rig := CameraRig.new()
	rig.name = "Camera"
	rig.target = player
	if Game.args.has("camera"):
		rig.set_yaw(deg_to_rad(float(Game.args["camera"])))
	if Game.args.has("zoom"):
		rig.distance = float(Game.args["zoom"])
	rig.position = player.position
	add_child(rig)
	player.camera_rig = rig

	var hud := Hud.new()
	hud.layer = 5
	hud.player = player
	hud.visible = not Game.args.has("no_hud")      # --no_hud: clean screenshots, for references.
	add_child(hud)

	add_child(Debug.new())


func _setup_environment() -> void:
	var sky_mat := ProceduralSkyMaterial.new()
	sky_mat.sky_top_color = Color("8fc3e6")
	sky_mat.sky_horizon_color = Color("f1e6d2")
	sky_mat.ground_horizon_color = Color("f1e6d2")
	sky_mat.ground_bottom_color = Color("b9c9a4")
	sky_mat.sun_angle_max = 20.0
	var sky := Sky.new()
	sky.sky_material = sky_mat

	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	# Warm mid-morning light: the ambient a little golden and the shadows with a touch of sky blue.
	env.ambient_light_color = Color("f6e3c8")
	env.ambient_light_sky_contribution = 0.5
	env.ambient_light_energy = 0.8
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	env.tonemap_exposure = 0.8
	env.ssao_enabled = true
	env.ssao_radius = 1.4
	env.ssao_intensity = 1.3
	env.glow_enabled = true
	env.glow_intensity = 0.15
	env.glow_bloom = 0.06
	env.glow_hdr_threshold = 1.4
	# Distance haze: what's near stays sharp, and the hills and forest in the back fade toward the sky.
	env.fog_enabled = true
	env.fog_light_color = Color("efe2cc")
	env.fog_sun_scatter = 0.25
	env.fog_density = 0.0035
	env.fog_aerial_perspective = 0.45
	env.fog_sky_affect = 0.3
	env.fog_depth_curve = 2.2
	env.fog_depth_begin = 25.0
	env.fog_depth_end = 140.0
	env.fog_mode = Environment.FOG_MODE_DEPTH
	# Soft colors (not garish): less saturation than before and mild contrast.
	env.adjustment_enabled = true
	env.adjustment_saturation = 1.04
	env.adjustment_contrast = 1.06
	env.adjustment_brightness = 1.02

	if Game.args.has("no_glow"):
		env.glow_enabled = false
	if Game.args.has("no_ssao"):
		env.ssao_enabled = false

	var world_env := WorldEnvironment.new()
	world_env.environment = env
	add_child(world_env)

	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-36, -50, 0)      # Lower: somewhat longer shadows.
	sun.light_color = Color("ffdcae")
	sun.light_energy = 1.35
	sun.shadow_enabled = true
	sun.shadow_blur = 1.5
	sun.directional_shadow_max_distance = 70.0
	sun.directional_shadow_blend_splits = true
	add_child(sun)

	# Diorama effect above the 3D and below the interface: just a vignette and a slight blur at
	# the edges (the style reference is sharp).
	if not Game.args.has("no_diorama"):
		var post := CanvasLayer.new()
		post.layer = 0
		var rect := ColorRect.new()
		rect.set_anchors_preset(Control.PRESET_FULL_RECT)
		rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
		var mat := ShaderMaterial.new()
		mat.shader = preload("res://shaders/tilt_shift.gdshader")
		rect.material = mat
		post.add_child(rect)
		add_child(post)


## Pollen and dust motes that float slowly around Noah, backlit: they add air and depth.
func _floating_motes() -> CPUParticles3D:
	var p := CPUParticles3D.new()
	var mesh := QuadMesh.new()
	mesh.size = Vector2(0.05, 0.05)
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.billboard_mode = BaseMaterial3D.BILLBOARD_ENABLED
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.albedo_color = Color(1.0, 0.95, 0.8, 0.7)
	mat.vertex_color_use_as_albedo = true
	mesh.material = mat
	p.mesh = mesh
	p.amount = 40
	p.lifetime = 9.0
	p.preprocess = 9.0
	p.local_coords = false
	p.emission_shape = CPUParticles3D.EMISSION_SHAPE_BOX
	p.emission_box_extents = Vector3(12, 2.5, 12)
	p.position = Vector3(0, 2.5, 0)
	p.direction = Vector3(1, 0.3, 0.4)
	p.spread = 60.0
	p.gravity = Vector3.ZERO
	p.initial_velocity_min = 0.1
	p.initial_velocity_max = 0.35
	var fade := Gradient.new()
	fade.set_color(0, Color(1, 1, 1, 0))
	fade.set_color(1, Color(1, 1, 1, 0))
	fade.add_point(0.3, Color(1, 1, 1, 1))
	fade.add_point(0.7, Color(1, 1, 1, 1))
	p.color_ramp = fade
	return p


## Village animals, each pair in its place (data/village.json, "animals"): in the pens, in
## the meadows and in the forest.
func _spawn_animals(world: Node3D) -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = 99
	for entry in world.data["animals"]:
		var pair := [entry[0], Vector3(entry[1], 0, entry[2])]
		for i in 2:
			var animal := Animal.new()
			animal.species = pair[0]
			animal.world = world
			var p: Vector3 = pair[1] + Vector3(i * 2.0, 0, rng.randf_range(-1, 1))
			p.y = world.height_at(p.x, p.z)
			animal.position = p
			animal.home = p
			animal.rotation.y = rng.randf() * TAU
			animal.rng.seed = rng.randi()
			add_child(animal)


## Noah's family and the villagers (data/village.json, "villagers"): each with their points, in
## coordinates of their house's yard (x across the width, y toward the facade).
func _spawn_villagers(world: Node3D) -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = 21
	for v in world.data.get("villagers", []):
		var house: Dictionary = {}
		for h in world.data["houses"]:
			if h["id"] == v["house"]:
				house = h
		var npc := Villager.new()
		npc.name = v["id"]
		npc.world = world
		npc.model_path = v["model"]
		npc.prefix = v["prefix"]
		npc.natural_walk = float(v["speed"])
		npc.stays = v["actions"]
		npc.albedo_tint = float(v.get("shine", 0.74))
		npc.rng.seed = rng.randi()
		for local in v["points"]:
			var p: Vector2 = world.house_point(house, Vector2(local[0], local[1]))
			npc.points.append(Vector3(p.x, world.height_at(p.x, p.y), p.y))
		npc.position = npc.points[0]
		add_child(npc)
