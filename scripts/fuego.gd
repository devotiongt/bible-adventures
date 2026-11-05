extends Node3D
## Fuego animado de la fogata: lenguas de fuego de juguete que se mecen (shaders/llama.gdshader), unas
## chispas que suben y una luz cálida que parpadea. Va encima de la pieza Fogata, que no trae llama.

const FLAME_SHADER := preload("res://shaders/llama.gdshader")
const BASE := 0.06                   # Las lenguas nacen entre los troncos, algo por encima de la ceniza.
const LIGHT_ENERGY := 1.3

## Lenguas: (alto, ancho, distancia al centro, ángulo, colores base → punta).
const TONGUES := [
	[0.64, 0.19, 0.0, 0.0, Color(1.0, 0.86, 0.38), Color(0.98, 0.45, 0.14)],
	[0.5, 0.11, 0.1, 0.3, Color(1.0, 0.93, 0.6), Color(1.0, 0.7, 0.2)],
	[0.42, 0.1, 0.12, 1.9, Color(1.0, 0.8, 0.3), Color(0.96, 0.42, 0.13)],
	[0.5, 0.11, 0.1, 3.4, Color(1.0, 0.93, 0.6), Color(1.0, 0.7, 0.2)],
	[0.4, 0.1, 0.12, 4.9, Color(1.0, 0.8, 0.3), Color(0.96, 0.42, 0.13)],
]

var _light: OmniLight3D
var _time := 0.0


func _ready() -> void:
	for i in TONGUES.size():
		var spec: Array = TONGUES[i]
		var tongue := MeshInstance3D.new()
		tongue.mesh = _tongue_mesh(spec[0], spec[1])
		var mat := ShaderMaterial.new()
		mat.shader = FLAME_SHADER
		mat.set_shader_parameter("height", spec[0])
		mat.set_shader_parameter("base_color", spec[4])
		mat.set_shader_parameter("tip_color", spec[5])
		mat.set_shader_parameter("speed", 0.9 + 0.08 * i)
		tongue.material_override = mat
		tongue.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		tongue.set_instance_shader_parameter("phase", i * 1.37)
		var dir := Vector2.from_angle(spec[3])
		tongue.position = Vector3(dir.x * spec[2], BASE, dir.y * spec[2])
		# Las de alrededor se abren un poco hacia fuera.
		if spec[2] > 0.0:
			tongue.rotate(Vector3(dir.y, 0, -dir.x).normalized(), -0.25)
		add_child(tongue)
	add_child(_sparks())
	_light = OmniLight3D.new()
	_light.light_color = Color(1.0, 0.68, 0.38)
	_light.light_energy = LIGHT_ENERGY
	_light.omni_range = 3.5
	_light.position = Vector3(0, 0.7, 0)
	add_child(_light)


func _process(delta: float) -> void:
	_time += delta
	_light.light_energy = LIGHT_ENERGY * (1.0 + 0.12 * sin(_time * 9.0) + 0.07 * sin(_time * 15.7))


## Gota: panzona y redonda abajo, con la punta corta (perfil de torno).
func _tongue_mesh(h: float, r: float) -> ArrayMesh:
	var profile := [Vector2(0.0, 0.0), Vector2(0.75, 0.04), Vector2(1.0, 0.16), Vector2(1.0, 0.3),
		Vector2(0.86, 0.47), Vector2(0.62, 0.64), Vector2(0.34, 0.81), Vector2(0.12, 0.94), Vector2(0.0, 1.0)]
	var segments := 12
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	for k in profile.size() - 1:
		var a: Vector2 = profile[k]
		var b: Vector2 = profile[k + 1]
		for s in segments:
			var u0 := TAU * s / segments
			var u1 := TAU * (s + 1) / segments
			var p00 := Vector3(cos(u0) * a.x * r, a.y * h, sin(u0) * a.x * r)
			var p01 := Vector3(cos(u1) * a.x * r, a.y * h, sin(u1) * a.x * r)
			var p10 := Vector3(cos(u0) * b.x * r, b.y * h, sin(u0) * b.x * r)
			var p11 := Vector3(cos(u1) * b.x * r, b.y * h, sin(u1) * b.x * r)
			for p in [p00, p10, p11, p00, p11, p01]:
				st.add_vertex(p)
	st.generate_normals()
	return st.commit()


## Chispas: pocas, pequeñas, que suben despacio y se apagan.
func _sparks() -> CPUParticles3D:
	var p := CPUParticles3D.new()
	var mesh := SphereMesh.new()
	mesh.radius = 0.018
	mesh.height = 0.036
	mesh.radial_segments = 6
	mesh.rings = 3
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.albedo_color = Color(1.0, 0.78, 0.3)
	mesh.material = mat
	p.mesh = mesh
	p.amount = 7
	p.lifetime = 1.6
	p.position = Vector3(0, 0.6, 0)
	p.emission_shape = CPUParticles3D.EMISSION_SHAPE_SPHERE
	p.emission_sphere_radius = 0.1
	p.direction = Vector3.UP
	p.spread = 20.0
	p.initial_velocity_min = 0.4
	p.initial_velocity_max = 0.8
	p.gravity = Vector3(0, 0.15, 0)
	var curve := Curve.new()
	curve.add_point(Vector2(0, 1))
	curve.add_point(Vector2(1, 0))
	p.scale_amount_curve = curve
	return p
