extends Node
## Tools to test the game from the command line, for example:
##   godot --path . -- --no_save --demo --stages=5 --screenshot=/tmp/ark.png
## --no_hud hides the interface (clean screenshots).
## --screenshot saves an image of the screen after a few seconds and quits the game.


func _ready() -> void:
	if Game.args.has("autotest"):
		_autotest()
	if Game.args.has("screenshot"):
		_capture(Game.args["screenshot"], float(Game.args.get("wait", "2.5")))


## --autotest: runs through the main loop (chop, craft, build) and checks it.
func _autotest() -> void:
	await get_tree().process_frame
	var fails: PackedStringArray = []
	var player = get_parent().get_node("Noah")
	var tree: Node = null
	for node in get_tree().get_nodes_in_group("interactable"):
		if node.get("kind") == "tree":
			tree = node
			break
	for anim_name in ["Sword_Attack", "Interact", "Fixing_Kneeling", "Idle", "Walk", "Jog_Fwd"]:
		if not player.noah.anim.has_animation("Noah_" + anim_name):
			fails.append("missing animation " + anim_name)
	player.target = tree
	player._interact()
	for i in 3:
		tree.interact(player)
	if Game.count("wood") != 3:
		fails.append("chopping 4 times should give 3 wood, got %d" % Game.count("wood"))
	if not tree.depleted:
		fails.append("the tree should be felled")

	Game.add("stone", 2)
	Game.add("fiber", 3)
	Game.craft(Game.recipes[3])  # rope
	Game.craft(Game.recipes[4])  # hammer
	if not Game.has_item("hammer"):
		fails.append("could not craft the hammer")
	if Game.craft(Game.recipes[4]):
		fails.append("should not be able to craft a second hammer")

	if Game.build_ark_stage():
		fails.append("built without materials")
	Game.add("wood", 10)
	for i in 3:
		Game.craft(Game.recipes[1])  # beam
	Game.craft(Game.recipes[2])  # pegs
	Game.craft(Game.recipes[2])
	if not Game.build_ark_stage() or Game.ark_stage != 1:
		fails.append("did not build stage 1 with the exact materials")

	print("AUTOTEST ", "OK" if fails.is_empty() else "FAILED:\n- " + "\n- ".join(fails))
	print("Final inventory: ", Game.inventory)
	get_tree().quit(0 if fails.is_empty() else 1)


func _capture(path: String, wait: float) -> void:
	if Game.args.has("no_dialog"):
		Game.ui_blocked = false
	if Game.args.has("craft"):
		Input.action_press("craft")
		await get_tree().process_frame
		Input.action_release("craft")
	if Game.args.has("walk"):
		var action: String = Game.args.get("dir", "move_up")
		Input.action_press(action, float(Game.args["walk"]))
		if Game.args.has("turn"):
			# Changes direction halfway, to see how the cloth sways.
			get_tree().create_timer(float(Game.args["turn"])).timeout.connect(func() -> void:
				Input.action_release(action)
				Input.action_press(Game.args.get("dir2", "move_right"), float(Game.args["walk"])))
	await get_tree().create_timer(wait).timeout
	await RenderingServer.frame_post_draw
	var image := get_viewport().get_texture().get_image()
	image.save_png(path)
	print("Screenshot saved to ", path)
	get_tree().quit()
