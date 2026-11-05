extends Node
## Herramientas para probar el juego desde la línea de comandos, por ejemplo:
##   godot --path . -- --sin_guardar --demo --etapas=5 --captura=/tmp/arca.png
## --sin_hud oculta la interfaz (capturas limpias).
## --captura guarda una imagen de la pantalla tras unos segundos y cierra el juego.


func _ready() -> void:
	if Game.args.has("autotest"):
		_autotest()
	if Game.args.has("captura"):
		_capture(Game.args["captura"], float(Game.args.get("espera", "2.5")))


## --autotest: recorre el bucle principal (talar, fabricar, construir) y lo comprueba.
func _autotest() -> void:
	await get_tree().process_frame
	var fails: PackedStringArray = []
	var player = get_parent().get_node("Noe")
	var tree: Node = null
	for node in get_tree().get_nodes_in_group("interactuable"):
		if node.get("kind") == "arbol":
			tree = node
			break
	for anim_name in ["Sword_Attack", "Interact", "Fixing_Kneeling", "Idle", "Walk", "Jog_Fwd"]:
		if not player.noah.anim.has_animation("Noe_" + anim_name):
			fails.append("falta la animación " + anim_name)
	player.target = tree
	player._interact()
	for i in 3:
		tree.interact(player)
	if Game.count("madera") != 3:
		fails.append("talar 4 veces debería dar 3 maderas, hay %d" % Game.count("madera"))
	if not tree.depleted:
		fails.append("el árbol debería quedar talado")

	Game.add("piedra", 2)
	Game.add("fibra", 3)
	Game.craft(Game.recipes[3])  # cuerda
	Game.craft(Game.recipes[4])  # martillo
	if not Game.has_item("martillo"):
		fails.append("no se pudo fabricar el martillo")
	if Game.craft(Game.recipes[4]):
		fails.append("no debería poder fabricar un segundo martillo")

	if Game.build_ark_stage():
		fails.append("construyó sin materiales")
	Game.add("madera", 10)
	for i in 3:
		Game.craft(Game.recipes[1])  # viga
	Game.craft(Game.recipes[2])  # clavijas
	Game.craft(Game.recipes[2])
	if not Game.build_ark_stage() or Game.ark_stage != 1:
		fails.append("no construyó la etapa 1 con los materiales justos")

	print("AUTOTEST ", "OK" if fails.is_empty() else "FALLÓ:\n- " + "\n- ".join(fails))
	print("Inventario final: ", Game.inventory)
	get_tree().quit(0 if fails.is_empty() else 1)


func _capture(path: String, wait: float) -> void:
	if Game.args.has("sin_dialogo"):
		Game.ui_blocked = false
	if Game.args.has("fabricar"):
		Input.action_press("craftear")
		await get_tree().process_frame
		Input.action_release("craftear")
	if Game.args.has("caminar"):
		var action: String = Game.args.get("dir", "mover_arriba")
		Input.action_press(action, float(Game.args["caminar"]))
		if Game.args.has("giro"):
			# Cambia de dirección a mitad de camino, para ver cómo se balancea la tela.
			get_tree().create_timer(float(Game.args["giro"])).timeout.connect(func() -> void:
				Input.action_release(action)
				Input.action_press(Game.args.get("dir2", "mover_der"), float(Game.args["caminar"])))
	await get_tree().create_timer(wait).timeout
	await RenderingServer.frame_post_draw
	var image := get_viewport().get_texture().get_image()
	image.save_png(path)
	print("Captura guardada en ", path)
	get_tree().quit()
