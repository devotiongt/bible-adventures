extends RefCounted
## The tunic as cloth: the skirt bone chains (tools/blender/rig_noah.py, skirt_bones) are
## moved by a Godot spring simulator. Meant for a separate tunic over a body with legs: with
## the tunic stuck to a body with no legs under it (the Rodin Noah), the legs poke through it; so it only
## turns on if the model has the chains (rig_noah_chains.py). They lag behind when starting and stopping, they sway and the legs (some
## capsules on the thighs and calves) push them when taking a step.

const STIFFNESS := 1.8     ## How much they go back to hanging straight (more: stiffer cloth).
const DRAG := 0.6         ## How much the sway is damped (more: less bounce).
const GRAVITY := 0.8
const JOINT_RADIUS := 0.05
const LEG_RADIUS := 0.085  ## Thickness of the legs for pushing the cloth (in character meters).


## Puts the simulator on the skeleton, if the model has skirt chains.
static func add(skeleton: Skeleton3D) -> SpringBoneSimulator3D:
	var chains: Array[int] = []
	var i := 0
	while skeleton.find_bone("skirt_%d_1" % i) >= 0:
		chains.append(i)
		i += 1
	if chains.is_empty():
		return null
	var sim := SpringBoneSimulator3D.new()
	sim.name = "Skirt"
	skeleton.add_child(sim)
	sim.setting_count = chains.size()
	for k in chains.size():
		var c := chains[k]
		sim.set_root_bone_name(k, "skirt_%d_1" % c)
		sim.set_end_bone_name(k, "skirt_%d_2" % c)
		sim.set_extend_end_bone(k, true)
		sim.set_end_bone_direction(k, SpringBoneSimulator3D.BONE_DIRECTION_FROM_PARENT)
		sim.set_end_bone_length(k, 0.04)
		sim.set_stiffness(k, STIFFNESS)
		sim.set_drag(k, DRAG)
		sim.set_gravity(k, GRAVITY)
		sim.set_radius(k, JOINT_RADIUS)
		sim.set_enable_all_child_collisions(k, true)
		# Movement is measured from the hips: when running, the cloth doesn't trail behind as if in wind;
		# only the legs and the body's sway move it.
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
			cap.position_offset = Vector3(0, length * 0.5, 0)    # The bone runs along its Y axis.
			sim.add_child(cap)
	return sim
