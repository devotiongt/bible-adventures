extends RefCounted
## La túnica como tela: las cadenas de huesos de la falda (herramientas/blender/rig_noe.py, huesos_falda) las
## mueve un simulador de resortes de Godot. Pensado para una túnica aparte sobre un cuerpo con piernas: con
## la túnica pegada al cuerpo sin piernas debajo (el Noé de Rodin), las piernas la atraviesan; por eso solo
## se activa si el modelo trae las cadenas (rig_noe_cadenas.py). Se retrasan al arrancar y frenar, se mecen y las piernas (unas
## cápsulas en los muslos y pantorrillas) las empujan al dar el paso.

const STIFFNESS := 1.8     ## Cuánto vuelven a colgar rectas (más: tela más tiesa).
const DRAG := 0.6         ## Cuánto frena el vaivén (más: menos rebote).
const GRAVITY := 0.8
const JOINT_RADIUS := 0.05
const LEG_RADIUS := 0.085  ## Grosor de las piernas para empujar la tela (en metros del personaje).


## Pone el simulador en el esqueleto, si el modelo trae cadenas de falda.
static func add(skeleton: Skeleton3D) -> SpringBoneSimulator3D:
	var chains: Array[int] = []
	var i := 0
	while skeleton.find_bone("falda_%d_1" % i) >= 0:
		chains.append(i)
		i += 1
	if chains.is_empty():
		return null
	var sim := SpringBoneSimulator3D.new()
	sim.name = "Falda"
	skeleton.add_child(sim)
	sim.setting_count = chains.size()
	for k in chains.size():
		var c := chains[k]
		sim.set_root_bone_name(k, "falda_%d_1" % c)
		sim.set_end_bone_name(k, "falda_%d_2" % c)
		sim.set_extend_end_bone(k, true)
		sim.set_end_bone_direction(k, SpringBoneSimulator3D.BONE_DIRECTION_FROM_PARENT)
		sim.set_end_bone_length(k, 0.04)
		sim.set_stiffness(k, STIFFNESS)
		sim.set_drag(k, DRAG)
		sim.set_gravity(k, GRAVITY)
		sim.set_radius(k, JOINT_RADIUS)
		sim.set_enable_all_child_collisions(k, true)
		# El movimiento se mide desde la cadera: al correr, la tela no se queda atrás como con viento;
		# solo la mueven las piernas y el vaivén del cuerpo.
		sim.set_center_from(k, SpringBoneSimulator3D.CENTER_FROM_BONE)
		sim.set_center_bone_name(k, "pelvis")
	for side in ["l", "r"]:
		for bone in ["thigh_", "calf_"]:
			var b := skeleton.find_bone(bone + side)
			var child := skeleton.find_bone(("calf_" if bone == "thigh_" else "foot_") + side)
			if b < 0 or child < 0:
				continue
			var length := skeleton.get_bone_rest(child).origin.length()
			var cap := SpringBoneCollisionCapsule3D.new()
			cap.bone_name = bone + side
			cap.radius = LEG_RADIUS
			cap.height = length + LEG_RADIUS * 2.0
			cap.position_offset = Vector3(0, length * 0.5, 0)    # El hueso va a lo largo de su eje Y.
			sim.add_child(cap)
	return sim
