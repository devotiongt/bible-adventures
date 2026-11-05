extends Node3D
## Modelo de Noé: personaje base de Quaternius (CC0) con pelo largo y barba canosos,
## el cuerpo adelgazado y la túnica hechos en Blender (herramientas/blender/tunica.py),
## la falda como tela simulada, sandalias y las animaciones de la Universal Animation Library.

const CHARACTER := "res://assets/personajes/Superhero_Male_FullBody.gltf"
const HAIR := ["res://assets/personajes/Hair_Long.gltf", "res://assets/personajes/Hair_Beard.gltf"]
const ANIMATIONS := "res://assets/animaciones/UAL1_Standard.glb"
const HAIR_SHADER := preload("res://shaders/hair.gdshader")
const RobeCloth := preload("res://scripts/robe_cloth.gd")
const CLOTHES := "res://assets/personajes/tunica.glb"

const LOOPING := ["Idle", "Walk", "Jog_Fwd", "Sprint", "Fixing_Kneeling", "Idle_Talking"]

## Color de cada material de la ropa hecha en Blender.
const CLOTH_COLORS := {
	"Lino": Color("d8c6a2"),
	"Manto": Color("7d5b3b"),
	"Faja": Color("94402c"),
	"Borde": Color("8c6a46"),
}
const LEATHER := Color("6e4526")
const SOLE := Color("3f2716")

## Perfil de la túnica en reposo: [altura, semieje x, semieje z, centro z].
const ROBE_PROFILE := [
	[0.05, 0.29, 0.26, -0.02],
	[0.45, 0.26, 0.23, -0.02],
	[0.9, 0.2, 0.16, -0.03],
	[1.04, 0.16, 0.125, -0.025],
]

const HEM_HEIGHT := 0.32  ## La túnica llega a media pantorrilla.
const SKIRT_TOP := 1.04  ## Altura (en reposo) donde empieza la falda (bajo la faja); igual que en tunica.py.

var skeleton: Skeleton3D
var anim: AnimationPlayer
var _action_left := 0.0


func _ready() -> void:
	var character: Node3D = load(CHARACTER).instantiate()
	character.rotation.y = PI  # El modelo mira a +Z; en el juego "adelante" es -Z.
	add_child(character)
	skeleton = character.get_node("Armature/Skeleton3D")
	for path in HAIR:
		_attach_skinned(path)
	_tint_hair(skeleton.get_node("Eyebrows"))
	_build_clothes()
	_build_sandals()
	_setup_animations(character)


func _process(delta: float) -> void:
	_action_left -= delta


## Velocidad natural (m/s) de cada ciclo, medida con el recorrido del pie: al
## escalar la animación por velocidad / natural, los pies no patinan.
const WALK_SPEED := 1.01
const JOG_SPEED := 1.885  ## Del trote "con túnica" (piernas al 65 %).
const JOG_LEG_SWING := 0.65


## Elige caminar, trotar o reposo según la velocidad (salvo durante una acción).
func update_locomotion(speed: float) -> void:
	if _action_left > 0.0 and speed < 0.5:
		return
	if speed > 1.6:
		_play("Trote", speed / JOG_SPEED)
	elif speed > 0.3:
		_play("Walk", speed / WALK_SPEED)
	else:
		_play("Idle", 1.0)


## Reproduce una animación puntual (talar, recoger, construir). Devuelve su duración.
func action(anim_name: String, speed := 1.5, max_time := 0.9) -> float:
	anim.play(anim_name, 0.12, speed)
	anim.seek(0.0, true)
	_action_left = minf(anim.get_animation(anim_name).length / speed, max_time)
	return _action_left


func _play(anim_name: String, speed: float) -> void:
	if anim.current_animation != anim_name:
		anim.play(anim_name, 0.2)
	anim.speed_scale = speed


func _setup_animations(character: Node3D) -> void:
	var source: Node = load(ANIMATIONS).instantiate()
	var library: AnimationLibrary = (source.get_node("AnimationPlayer") as AnimationPlayer).get_animation_library("")
	source.free()
	for anim_name in library.get_animation_list():
		var a := library.get_animation(anim_name)
		# Sin desplazamiento del hueso raíz: el movimiento lo pone el CharacterBody.
		var root_track := a.find_track(NodePath("Armature/Skeleton3D:root"), Animation.TYPE_POSITION_3D)
		if root_track != -1:
			a.remove_track(root_track)
		if anim_name in LOOPING:
			a.loop_mode = Animation.LOOP_LINEAR
	library.add_animation("Trote", _robe_jog(library.get_animation("Jog_Fwd")))
	anim = AnimationPlayer.new()
	character.add_child(anim)
	anim.add_animation_library("", library)
	anim.play("Idle")


## El trote original abre mucho las piernas (está pensado para pantalones).
## Esta copia acerca la rotación de muslos, pantorrillas y pies a la de reposo,
## dando pasos más cortos que una túnica larga sí puede cubrir.
func _robe_jog(source: Animation) -> Animation:
	var a: Animation = source.duplicate(true)
	for t in a.get_track_count():
		var bone := String(a.track_get_path(t).get_concatenated_subnames())
		if a.track_get_type(t) != Animation.TYPE_ROTATION_3D:
			continue
		if not (bone.begins_with("thigh") or bone.begins_with("calf") or bone.begins_with("foot")):
			continue
		var rest := skeleton.get_bone_rest(skeleton.find_bone(bone)).basis.get_rotation_quaternion()
		for k in a.track_get_key_count(t):
			a.track_set_key_value(t, k, rest.slerp(a.track_get_key_value(t, k), JOG_LEG_SWING))
	a.loop_mode = Animation.LOOP_LINEAR
	return a


# --- Pelo ---------------------------------------------------------------------

func _attach_skinned(path: String) -> void:
	var source: Node = load(path).instantiate()
	var mi: MeshInstance3D = source.find_children("*", "MeshInstance3D", true, false)[0]
	mi.get_parent().remove_child(mi)
	source.free()
	skeleton.add_child(mi)
	mi.skeleton = NodePath("..")
	_tint_hair(mi)


func _tint_hair(mi: MeshInstance3D) -> void:
	for s in mi.mesh.get_surface_count():
		var original := mi.mesh.surface_get_material(s) as BaseMaterial3D
		var m := ShaderMaterial.new()
		m.shader = HAIR_SHADER
		if original and original.albedo_texture:
			m.set_shader_parameter("albedo_tex", original.albedo_texture)
		mi.set_surface_override_material(s, m)


# --- Ropa ---------------------------------------------------------------------

func _build_clothes() -> void:
	var source: Node = load(CLOTHES).instantiate()
	var source_skeleton: Skeleton3D = source.find_children("*", "Skeleton3D", true, false)[0]
	var skirt_template: Mesh = (source.find_child("Falda", true, false) as MeshInstance3D).mesh
	# El cuerpo adelgazado en Blender sustituye al original (que es de "superhéroe").
	(skeleton.get_node("SuperHero_Male") as MeshInstance3D).visible = false
	for part in ["Cuerpo", "Tunica"]:
		var mi := source.find_child(part, true, false) as MeshInstance3D
		mi.get_parent().remove_child(mi)
		mi.owner = null
		mi.skin = _rebind_skin(mi.skin, source_skeleton)
		skeleton.add_child(mi)
		mi.skeleton = NodePath("..")
		if part == "Tunica":
			_apply_cloth_materials(mi)
	source.free()

	var skirt := RobeCloth.new()
	skirt.name = "FaldaTela"
	var rings := _resample(ROBE_PROFILE, HEM_HEIGHT, SKIRT_TOP, 8)
	rings.reverse()
	skirt.setup(skeleton, rings, CLOTH_COLORS["Lino"], CLOTH_COLORS["Borde"], skirt_template, CLOTH_COLORS)
	add_child(skirt)


## Blender exporta los huesos con su propia orientación. La malla está en la misma
## posición de reposo que el cuerpo, así que basta con enlazar cada hueso (por nombre)
## al reposo del esqueleto de Noé.
func _rebind_skin(source_skin: Skin, source_skeleton: Skeleton3D) -> Skin:
	var skin := Skin.new()
	for i in source_skin.get_bind_count():
		var bone_name := String(source_skin.get_bind_name(i))
		if bone_name.is_empty():
			bone_name = source_skeleton.get_bone_name(source_skin.get_bind_bone(i))
		var bone := skeleton.find_bone(bone_name)
		skin.add_named_bind(bone_name, skeleton.get_bone_global_rest(bone).affine_inverse())
	return skin


func _apply_cloth_materials(mi: MeshInstance3D) -> void:
	for s in mi.mesh.get_surface_count():
		var source := mi.mesh.surface_get_material(s)
		var mat_name := source.resource_name if source else "Lino"
		mi.set_surface_override_material(s, cloth_material(CLOTH_COLORS.get(mat_name, CLOTH_COLORS["Lino"])))


static var _cloth_materials := {}


static func cloth_material(color: Color) -> StandardMaterial3D:
	if not _cloth_materials.has(color):
		var m := StandardMaterial3D.new()
		m.albedo_color = color
		m.roughness = 0.95
		m.cull_mode = BaseMaterial3D.CULL_DISABLED
		_cloth_materials[color] = m
	return _cloth_materials[color]


# --- Sandalias -----------------------------------------------------------------

## Suela y tres tiras de cuero (dedos, empeine y tobillo) para cada pie. Se ajustan a
## la forma real del pie leyendo los vértices del cuerpo, y van pegadas a los huesos
## del pie (la suela y la tira de los dedos al hueso de los dedos).
func _build_sandals() -> void:
	var body: MeshInstance3D = skeleton.get_node("SuperHero_Male")
	var verts: PackedVector3Array = body.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	var skin := Skin.new()
	for i in skeleton.get_bone_count():
		skin.add_named_bind(skeleton.get_bone_name(i), skeleton.get_bone_global_rest(i).affine_inverse())
	var st := SurfaceTool.new()
	st.set_skin_weight_count(SurfaceTool.SKIN_4_WEIGHTS)
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	_vertex_count = 0
	for side in ["l", "r"]:
		var sx := 1.0 if side == "l" else -1.0
		var foot := skeleton.find_bone("foot_" + side)
		var ball := skeleton.find_bone("ball_" + side)
		var ball_z := skeleton.get_bone_global_rest(ball).origin.z
		var sole := _bounds(verts, func(v: Vector3) -> bool: return v.x * sx > 0.02 and v.y < 0.04)
		var sole_lo: Vector3 = sole[0]
		var sole_hi: Vector3 = sole[1]
		# Suela.
		var sole_center := (sole_lo + sole_hi) * 0.5
		var sole_size := sole_hi - sole_lo + Vector3(0.02, 0.0, 0.025)
		_sandal_box(st, Vector3(sole_center.x, 0.0, sole_center.z), Vector3(sole_size.x, 0.024, sole_size.z), foot, ball, ball_z - 0.02)
		# Tiras por encima del pie.
		for strap in [[ball_z - 0.035, ball], [lerpf(sole_lo.z, ball_z, 0.5), foot]]:
			var z0: float = strap[0]
			var slice := _bounds(verts, func(v: Vector3) -> bool: return v.x * sx > 0.02 and absf(v.z - z0) < 0.012 and v.y < 0.16)
			_sandal_arc(st, slice, z0, strap[1])
		# Tira del tobillo.
		var ankle := _bounds(verts, func(v: Vector3) -> bool: return v.x * sx > 0.02 and v.y > 0.085 and v.y < 0.115 and v.z < 0.05)
		_sandal_ring(st, ankle, 0.1, foot)
	var mat := StandardMaterial3D.new()
	mat.vertex_color_use_as_albedo = true
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	mat.roughness = 0.7
	var mi := MeshInstance3D.new()
	mi.name = "Sandalias"
	mi.mesh = st.commit()
	mi.material_override = mat
	mi.skin = skin
	skeleton.add_child(mi)
	mi.skeleton = NodePath("..")


## [mínimo, máximo] de los vértices que cumplen la condición.
func _bounds(verts: PackedVector3Array, keep: Callable) -> Array:
	var lo := Vector3.ONE * 99.0
	var hi := -Vector3.ONE * 99.0
	for v in verts:
		if keep.call(v):
			lo = lo.min(v)
			hi = hi.max(v)
	return [lo, hi]


func _sandal_vertex(st: SurfaceTool, p: Vector3, n: Vector3, color: Color, bone: int) -> void:
	st.set_color(color.srgb_to_linear())
	st.set_normal(n)
	st.set_bones(PackedInt32Array([bone, 0, 0, 0]))
	st.set_weights(PackedFloat32Array([1.0, 0.0, 0.0, 0.0]))
	st.add_vertex(p)
	_vertex_count += 1


func _sandal_box(st: SurfaceTool, center: Vector3, size: Vector3, foot: int, ball: int, split_z: float) -> void:
	var box := BoxMesh.new()
	box.size = size
	box.subdivide_depth = 3
	var arrays := box.surface_get_arrays(0)
	var bv: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var bn: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
	var bi: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	var base := _vertex_count
	for i in bv.size():
		var p := bv[i] + center
		_sandal_vertex(st, p, bn[i], SOLE, ball if p.z > split_z else foot)
	for i in bi:
		st.add_index(base + i)


## Tira en arco por encima del pie, de un lado de la suela al otro.
func _sandal_arc(st: SurfaceTool, slice: Array, z0: float, bone: int) -> void:
	var lo: Vector3 = slice[0]
	var hi: Vector3 = slice[1]
	var cx := (lo.x + hi.x) * 0.5
	var hx := (hi.x - lo.x) * 0.5 + 0.007
	var top := hi.y + 0.006
	var points := []
	var normals := []
	for k in 13:
		var a := PI * k / 12.0
		points.append(Vector3(cx + cos(a) * hx, sin(a) * top, z0))
		normals.append(Vector3(cos(a), sin(a), 0.0))
	_sandal_strip(st, points, normals, Vector3(0, 0, 0.022), bone)


## Tira horizontal alrededor del tobillo.
func _sandal_ring(st: SurfaceTool, slice: Array, y0: float, bone: int) -> void:
	var lo: Vector3 = slice[0]
	var hi: Vector3 = slice[1]
	var center := (lo + hi) * 0.5
	var half := (hi - lo) * 0.5 + Vector3(0.008, 0, 0.008)
	var points := []
	var normals := []
	for k in 21:
		var a := TAU * k / 20.0
		points.append(Vector3(center.x + cos(a) * half.x, y0, center.z + sin(a) * half.z))
		normals.append(Vector3(cos(a), 0.0, sin(a)))
	_sandal_strip(st, points, normals, Vector3(0, 0.02, 0), bone)


func _sandal_strip(st: SurfaceTool, points: Array, normals: Array, width: Vector3, bone: int) -> void:
	var base := _vertex_count
	for k in points.size():
		_sandal_vertex(st, points[k] - width * 0.5, normals[k], LEATHER, bone)
		_sandal_vertex(st, points[k] + width * 0.5, normals[k], LEATHER, bone)
	for k in points.size() - 1:
		var i := base + k * 2
		st.add_index(i)
		st.add_index(i + 2)
		st.add_index(i + 1)
		st.add_index(i + 1)
		st.add_index(i + 2)
		st.add_index(i + 3)


## Interpola el perfil para tener anillos regulares entre y0 e y1.
func _resample(profile: Array, y0: float, y1: float, rings: int, grow := 0.0) -> Array:
	var out := []
	for r in rings + 1:
		var y := lerpf(y0, y1, float(r) / rings)
		var k := 0
		while k < profile.size() - 2 and profile[k + 1][0] < y:
			k += 1
		var a: Array = profile[k]
		var b: Array = profile[k + 1]
		var t := clampf((y - a[0]) / (b[0] - a[0]), 0.0, 1.0)
		out.append([y, lerpf(a[1], b[1], t) + grow, lerpf(a[2], b[2], t) + grow, lerpf(a[3], b[3], t)])
	return out


var _vertex_count := 0
