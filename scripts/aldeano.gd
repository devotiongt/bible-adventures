extends Node3D
## Personaje de la aldea (la familia de Noé y los aldeanos): un modelo riggeado con rig_noe.py y su
## perfil (herramientas/blender/perfiles/), que se queda un rato en un sitio (de pie, hablando o
## trabajando) y luego camina despacio hasta el siguiente de sus puntos, en orden y sin prisa.
## Datos en data/aldea.json, "aldeanos".

## Brillo del color: Noé lleva 0,74 (noah_rig.gd) porque su paleta es muy clara; los hechos con TRELLIS ya
## vienen con colores apagados y van a 1 (data/aldea.json, "brillo").
const ROUGHNESS := 0.95
const SPECULAR := 0.2
const SPEED := 0.55                            ## Paso tranquilo (m/s).
const TURN_SPEED := 4.0

var world  ## world.gd
var model_path := ""
var prefix := ""
var natural_walk := 0.63   ## Velocidad natural del ciclo de caminar (la imprime rig_noe.py).
var points: Array[Vector3] = []
var stays: Array = ["Idle"]   ## Lo que hace al llegar a un punto: animaciones en bucle.
var albedo_tint := 0.74
var rng := RandomNumberGenerator.new()

var anim: AnimationPlayer
var _target := 0
var _wait := 0.0


func _ready() -> void:
	var model: Node3D = load(model_path).instantiate()
	model.rotation.y = PI      # El modelo mira a +Z; aquí "adelante" es -Z, como Noé.
	add_child(model)
	_soften_materials(model)
	anim = model.find_children("*", "AnimationPlayer", true, false)[0]
	for a in ["Idle", "Walk", "Idle_Talking", "Fixing_Kneeling", "Interact"]:
		if anim.has_animation(prefix + a):
			anim.get_animation(prefix + a).loop_mode = Animation.LOOP_LINEAR
	_stay()


func _process(delta: float) -> void:
	if points.is_empty():
		return
	if _wait > 0.0:
		_wait -= delta
		if _wait <= 0.0:
			_target = (_target + 1) % points.size()
			_play("Walk", SPEED / natural_walk)
		return
	var to := points[_target] - position
	to.y = 0.0
	if to.length() < 0.15:
		_stay()
		return
	var step := to.normalized() * minf(SPEED * delta, to.length())
	position += step
	position.y = world.height_at(position.x, position.z)
	var facing := atan2(-to.x, -to.z)
	rotation.y = lerp_angle(rotation.y, facing, minf(1.0, TURN_SPEED * delta))


## Se queda en el punto haciendo algo de los suyos un rato.
func _stay() -> void:
	_wait = rng.randf_range(5.0, 11.0)
	_play(stays[rng.randi() % stays.size()], 1.0)


func _play(anim_name: String, speed: float) -> void:
	var full := prefix + anim_name
	if not anim.has_animation(full):
		full = prefix + "Idle"
	if anim.current_animation != full:
		anim.play(full, 0.3)
	anim.speed_scale = speed


func _soften_materials(root: Node) -> void:
	for mi in root.find_children("*", "MeshInstance3D", true, false):
		var mesh: Mesh = (mi as MeshInstance3D).mesh
		for i in mesh.get_surface_count():
			var src := mesh.surface_get_material(i) as BaseMaterial3D
			if src == null:
				continue
			var m := src.duplicate() as BaseMaterial3D
			m.albedo_color = src.albedo_color * Color(albedo_tint, albedo_tint, albedo_tint)
			m.roughness = ROUGHNESS
			m.metallic = 0.0
			m.metallic_specular = SPECULAR
			(mi as MeshInstance3D).set_surface_override_material(i, m)
