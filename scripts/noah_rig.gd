extends Node3D
## Noé del juego: con túnica corta y piernas (TRELLIS, referencias/noe_piernas_giro.webp), riggeado con
## herramientas/blender/rig_noe.py y su perfil (perfiles/noe_corta.json), con las animaciones de la
## Universal Animation Library adaptadas a su cuerpo. El Noé anterior (Rodin, túnica larga) sigue en
## assets/personajes/rodin/noe_rig.glb.
## Misma interfaz que el modelo anterior (noah_model.gd): update_locomotion() y action().

const LowPoly := preload("res://scripts/lowpoly.gd")
const FaldaResortes := preload("res://scripts/falda_resortes.gd")

const MODEL := "res://assets/personajes/noe_trellis/noe_corta_rig.glb"
const LOOPING := ["Noe_Idle", "Noe_Walk", "Noe_Jog_Fwd", "Noe_Sprint", "Noe_Idle_Talking", "Noe_Fixing_Kneeling",
		"Noe_Trote"]

## Velocidad natural (m/s) de cada ciclo, medida en el rig (recorrido del pie): la animación se
## escala por velocidad / natural para que los pies no patinen.
const WALK_SPEED := 0.455
const JOG_SPEED := 1.215
const SPRINT_SPEED := 1.567
## Trote propio (rig_noe.py, trote_propio): de reserva. Se usa el Jog_Fwd de la biblioteca, que tiene mejor
## zancada; la túnica ya no se deforma con él porque se abre con los huesos de falda de rig_noe.py.
const TROT_SPEED := 0.859

## Cuánto de la inclinación original de la espalda se conserva al correr (0 = recto).
const POSTURE_KEEP := 0.65
const POSTURE_BONES := ["pelvis", "spine_01", "spine_02", "spine_03", "neck_01", "Head"]
## Brazos al trotar: el original lleva los puños en alto como un boxeador; se acercan a la postura de
## reposo (brazos caídos) dejando un balanceo suave al compás de las piernas.
const ARM_KEEP := 0.65
const ARM_BONES := ["clavicle_l", "clavicle_r", "upperarm_l", "upperarm_r", "lowerarm_l", "lowerarm_r",
		"hand_l", "hand_r"]

## Material más mate y algo menos luminoso: con el sol, el resplandor y la saturación del juego,
## los colores claros de la paleta (pelo blanco, piel) se quemaban.
const ALBEDO_TINT := Color(1, 1, 1)     ## TRELLIS ya trae colores apagados (el de Rodin iba a 0,74).
const ROUGHNESS := 0.95
const SPECULAR := 0.2

## Herramientas en la mano derecha durante una acción (talar con hacha, picar con pico).
## El mango va a lo largo del eje Y de la herramienta; GRIP_* la colocan en el hueso de la mano.
const TOOL_HAND := "hand_r"
const GRIP_POS := Vector3(0, 0.07, 0)
const GRIP_ROT := Vector3(90, 0, 0)
## Giro sobre el mango: la hoja del hacha y las puntas del pico, de cara al golpe.
const TOOL_TWIST := 180.0
const WOOD := Color("6a4a2c")
const STONE := Color("6e6c67")
const ROPE := Color("5e3918")

## Modelo a cargar (se puede cambiar antes de añadirlo, para probar otro Noé) y su brillo (los de TRELLIS
## ya vienen con colores apagados: 1).
var model_path := MODEL
var albedo_tint := ALBEDO_TINT
var use_springs := true
var skeleton: Skeleton3D
var anim: AnimationPlayer
var tools: Dictionary = {}
var _action_left := 0.0


func _ready() -> void:
	var model: Node3D = load(model_path).instantiate()
	model.rotation.y = PI  # El modelo mira a +Z; en el juego "adelante" es -Z.
	add_child(model)
	skeleton = model.find_children("*", "Skeleton3D", true, false)[0]
	if use_springs:
		FaldaResortes.add(skeleton)    # Solo si el modelo trae cadenas de falda (túnica aparte).
	_soften_materials(model)
	anim = model.find_children("*", "AnimationPlayer", true, false)[0]
	# Correr y trotar vienen de un corredor atlético muy inclinado hacia delante: se endereza la
	# espalda, el cuello y la cabeza, dejando solo un poco de esa inclinación.
	for anim_name in ["Noe_Sprint", "Noe_Jog_Fwd"]:
		if anim.has_animation(anim_name):
			var a := anim.get_animation(anim_name)
			_straighten(a, POSTURE_BONES, POSTURE_KEEP)
			_straighten(a, ARM_BONES, ARM_KEEP)
			_no_sway(a)
	for anim_name in LOOPING:
		if anim.has_animation(anim_name):
			anim.get_animation(anim_name).loop_mode = Animation.LOOP_LINEAR
	anim.play("Noe_Idle")
	_build_tools()


func _process(delta: float) -> void:
	_action_left -= delta
	if _action_left <= 0.0:
		_show_tool("")


## Elige caminar, trotar, correr o reposo según la velocidad (salvo durante una acción).
func update_locomotion(speed: float) -> void:
	if _action_left > 0.0 and speed < 0.5:
		return
	if speed > 3.6:   # Correr solo por encima de la velocidad normal (reservado para más adelante).
		_play("Noe_Sprint", speed / SPRINT_SPEED)
	elif speed > 1.2:
		_play("Noe_Jog_Fwd", speed / JOG_SPEED)
	elif speed > 0.2:
		_play("Noe_Walk", speed / WALK_SPEED)
	else:
		_play("Noe_Idle", 1.0)


## Reproduce una animación puntual (talar, recoger, construir), con una herramienta en la mano si
## se indica ("hacha", "pico"). Devuelve su duración.
func action(anim_name: String, speed := 1.5, max_time := 0.9, tool := "") -> float:
	var full := "Noe_" + anim_name
	if not anim.has_animation(full):
		return 0.0
	anim.play(full, 0.12, speed)
	anim.seek(0.0, true)
	_action_left = minf(anim.get_animation(full).length / speed, max_time)
	_show_tool(tool)
	return _action_left


func _show_tool(tool: String) -> void:
	for t in tools:
		tools[t].visible = t == tool


func _build_tools() -> void:
	var hand := BoneAttachment3D.new()
	hand.bone_name = TOOL_HAND
	skeleton.add_child(hand)
	var grip := Node3D.new()
	grip.position = GRIP_POS
	grip.rotation_degrees = GRIP_ROT
	hand.add_child(grip)

	# Proporciones chibi, como Noé: mango corto y grueso, cabeza grande.
	var axe := Node3D.new()
	_handle(axe)
	LowPoly.box(axe, Vector3(0.09, 0.11, 0.08), STONE, Vector3(-0.01, 0.33, 0))           # Talón.
	var blade := PrismMesh.new()         # Cuña: estrecha junto al mango, ancha en el filo.
	blade.size = Vector3(0.24, 0.17, 0.05)
	LowPoly.part(axe, blade, STONE, Vector3(0.1, 0.33, 0), Vector3(0, 0, 90))
	LowPoly.box(axe, Vector3(0.03, 0.24, 0.056), STONE.lightened(0.25), Vector3(0.18, 0.33, 0))  # Filo.
	LowPoly.box(axe, Vector3(0.085, 0.05, 0.09), ROPE, Vector3(0, 0.25, 0))              # Atadura.
	tools["hacha"] = axe

	var pick := Node3D.new()
	_handle(pick)
	LowPoly.box(pick, Vector3(0.1, 0.1, 0.09), STONE, Vector3(0, 0.34, 0))
	for side in [-1, 1]:
		LowPoly.cylinder(pick, 0.0, 0.05, 0.2, 4, STONE, Vector3(0.13 * side, 0.32, 0),
				Vector3(0, 0, -100 * side))
	LowPoly.box(pick, Vector3(0.085, 0.05, 0.1), ROPE, Vector3(0, 0.26, 0))
	tools["pico"] = pick

	for t in tools:
		tools[t].visible = false
		tools[t].rotation_degrees.y = TOOL_TWIST
		grip.add_child(tools[t])


## Mango de madera a lo largo de Y, con un remate abajo para que no se escurra de la mano.
func _handle(parent: Node3D) -> void:
	LowPoly.cylinder(parent, 0.03, 0.035, 0.5, 6, WOOD, Vector3(0, 0.12, 0))
	LowPoly.cylinder(parent, 0.045, 0.045, 0.05, 6, WOOD.darkened(0.25), Vector3(0, -0.13, 0))


func _play(anim_name: String, speed: float) -> void:
	if anim.current_animation != anim_name:
		anim.play(anim_name, 0.2)
	anim.speed_scale = speed


## Acerca la rotación de la columna, el cuello y la cabeza a la de reposo.
func _straighten(a: Animation, bones: Array, keep: float) -> void:
	for t in a.get_track_count():
		if a.track_get_type(t) != Animation.TYPE_ROTATION_3D:
			continue
		var bone := String(a.track_get_path(t).get_concatenated_subnames())
		if bone not in bones:
			continue
		var rest := skeleton.get_bone_rest(skeleton.find_bone(bone)).basis.get_rotation_quaternion()
		for k in a.track_get_key_count(t):
			a.track_set_key_value(t, k, rest.slerp(a.track_get_key_value(t, k), keep))


## Sin vaivén lateral de la cadera (el tambaleo de lado a lado al trotar).
func _no_sway(a: Animation) -> void:
	for t in a.get_track_count():
		if a.track_get_type(t) != Animation.TYPE_POSITION_3D:
			continue
		var bone := String(a.track_get_path(t).get_concatenated_subnames())
		if bone != "pelvis":
			continue
		var rest_x := skeleton.get_bone_rest(skeleton.find_bone(bone)).origin.x
		for k in a.track_get_key_count(t):
			var v: Vector3 = a.track_get_key_value(t, k)
			a.track_set_key_value(t, k, Vector3(rest_x, v.y, v.z))


func _soften_materials(root: Node) -> void:
	for mi in root.find_children("*", "MeshInstance3D", true, false):
		var mesh: Mesh = (mi as MeshInstance3D).mesh
		for i in mesh.get_surface_count():
			var src := mesh.surface_get_material(i) as BaseMaterial3D
			if src == null:
				continue
			var m := src.duplicate() as BaseMaterial3D
			m.albedo_color = src.albedo_color * albedo_tint
			m.roughness = ROUGHNESS
			m.metallic = 0.0
			m.metallic_specular = SPECULAR
			(mi as MeshInstance3D).set_surface_override_material(i, m)
