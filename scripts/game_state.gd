extends Node
## Estado global del juego (autoload "Game"): inventario, recetas, etapas del arca,
## controles y guardado. Los datos se leen de res://data/*.json para que sea fácil
## añadir objetos, recetas o capítulos sin tocar código.

signal inventory_changed
signal ark_stage_changed(stage: int)
signal notify(text: String)

const SAVE_PATH := "user://partida.json"

var items: Dictionary = {}
var recipes: Array = []
var ark_stages: Array = []

var inventory: Dictionary = {}
var ark_stage: int = 0  ## Número de etapas del arca ya construidas.
var intro_seen := false

## Mientras hay un panel o diálogo abierto, Noé no se mueve ni interactúa.
var ui_blocked := false

## Argumentos de línea de comandos tras "--" (p. ej. --nuevo, --captura=ruta.png).
var args: Dictionary = {}
var _saving_enabled := true


func _ready() -> void:
	_parse_args()
	_setup_input()
	items = _load_json("res://data/items.json")
	recipes = _load_json("res://data/recetas.json")
	ark_stages = _load_json("res://data/arca.json")

	_saving_enabled = not args.has("sin_guardar")
	if not args.has("nuevo"):
		load_game()
	if args.has("demo"):
		for id in items:
			inventory[id] = 40
	if args.has("etapas"):
		ark_stage = clampi(int(args["etapas"]), 0, ark_stages.size())
	if args.has("sin_intro"):
		intro_seen = true


# --- Inventario ---------------------------------------------------------------

func count(id: String) -> int:
	return int(inventory.get(id, 0))


func has_item(id: String) -> bool:
	return count(id) > 0


func has_all(requirements: Dictionary) -> bool:
	for id in requirements:
		if count(id) < int(requirements[id]):
			return false
	return true


func add(id: String, amount: int = 1) -> void:
	inventory[id] = count(id) + amount
	inventory_changed.emit()
	save_game()


func consume(requirements: Dictionary) -> void:
	for id in requirements:
		inventory[id] = count(id) - int(requirements[id])
		if inventory[id] <= 0:
			inventory.erase(id)


func item_name(id: String) -> String:
	return items.get(id, {}).get("nombre", id)


func item_color(id: String) -> Color:
	return Color(items.get(id, {}).get("color", "#ffffff"))


func is_tool(id: String) -> bool:
	return items.get(id, {}).get("herramienta", false)


## Texto tipo "tablón 4/12 · clavija 0/8".
func requirements_text(requirements: Dictionary) -> String:
	var parts: PackedStringArray = []
	for id in requirements:
		parts.append("%s %d/%d" % [item_name(id).to_lower(), count(id), int(requirements[id])])
	return " · ".join(parts)


# --- Fabricación --------------------------------------------------------------

func can_craft(recipe: Dictionary) -> bool:
	var result: String = recipe["resultado"]
	if is_tool(result) and has_item(result):
		return false
	return has_all(recipe["ingredientes"])


func craft(recipe: Dictionary) -> bool:
	var result: String = recipe["resultado"]
	if is_tool(result) and has_item(result):
		notify.emit("Ya tienes un %s." % item_name(result).to_lower())
		return false
	if not has_all(recipe["ingredientes"]):
		notify.emit("Te faltan materiales para %s." % item_name(result).to_lower())
		return false
	consume(recipe["ingredientes"])
	var amount := int(recipe["cantidad"])
	add(result, amount)
	notify.emit("Fabricaste %d × %s" % [amount, item_name(result)])
	return true


# --- Arca ---------------------------------------------------------------------

func ark_complete() -> bool:
	return ark_stage >= ark_stages.size()


func next_ark_stage() -> Dictionary:
	if ark_complete():
		return {}
	return ark_stages[ark_stage]


func build_ark_stage() -> bool:
	var stage := next_ark_stage()
	if stage.is_empty():
		return false
	if not has_item("martillo"):
		notify.emit("Necesitas un martillo para construir. Fabrícalo con C.")
		return false
	if not has_all(stage["materiales"]):
		notify.emit("Faltan materiales: " + requirements_text(stage["materiales"]))
		return false
	consume(stage["materiales"])
	ark_stage += 1
	inventory_changed.emit()
	save_game()
	ark_stage_changed.emit(ark_stage)
	return true


# --- Guardado -----------------------------------------------------------------

func save_game() -> void:
	if not _saving_enabled:
		return
	var file := FileAccess.open(SAVE_PATH, FileAccess.WRITE)
	if file == null:
		return
	file.store_string(JSON.stringify({
		"inventario": inventory,
		"etapa_arca": ark_stage,
		"intro_vista": intro_seen,
	}, "\t"))


func load_game() -> void:
	if not FileAccess.file_exists(SAVE_PATH):
		return
	var data = JSON.parse_string(FileAccess.get_file_as_string(SAVE_PATH))
	if typeof(data) != TYPE_DICTIONARY:
		return
	inventory.clear()
	var saved: Dictionary = data.get("inventario", {})
	for id in saved:
		inventory[id] = int(saved[id])
	ark_stage = int(data.get("etapa_arca", 0))
	intro_seen = bool(data.get("intro_vista", false))


func reset_game() -> void:
	inventory.clear()
	ark_stage = 0
	intro_seen = false
	save_game()
	get_tree().reload_current_scene()


# --- Utilidades ---------------------------------------------------------------

func _load_json(path: String) -> Variant:
	var data = JSON.parse_string(FileAccess.get_file_as_string(path))
	if data == null:
		push_error("No se pudo leer " + path)
	return data


func _parse_args() -> void:
	for arg in OS.get_cmdline_user_args():
		var kv := arg.trim_prefix("--").split("=", true, 1)
		args[kv[0]] = kv[1] if kv.size() > 1 else "1"


## Teclado y mando. El control táctil para móvil se añadirá encima de estas acciones.
func _setup_input() -> void:
	var keys := {
		"mover_izq": [KEY_A, KEY_LEFT],
		"mover_der": [KEY_D, KEY_RIGHT],
		"mover_arriba": [KEY_W, KEY_UP],
		"mover_abajo": [KEY_S, KEY_DOWN],
		"interactuar": [KEY_E, KEY_SPACE],
		"craftear": [KEY_C, KEY_TAB],
		"camara_izq": [KEY_Q],
		"camara_der": [KEY_R],
		"reiniciar": [KEY_F9],
	}
	var buttons := {
		"interactuar": JOY_BUTTON_A,
		"craftear": JOY_BUTTON_Y,
		"camara_izq": JOY_BUTTON_LEFT_SHOULDER,
		"camara_der": JOY_BUTTON_RIGHT_SHOULDER,
	}
	var axes := {
		"mover_izq": [JOY_AXIS_LEFT_X, -1.0],
		"mover_der": [JOY_AXIS_LEFT_X, 1.0],
		"mover_arriba": [JOY_AXIS_LEFT_Y, -1.0],
		"mover_abajo": [JOY_AXIS_LEFT_Y, 1.0],
	}
	for action in keys:
		if not InputMap.has_action(action):
			InputMap.add_action(action)
		for key in keys[action]:
			var ev := InputEventKey.new()
			ev.physical_keycode = key
			InputMap.action_add_event(action, ev)
	for action in buttons:
		var ev := InputEventJoypadButton.new()
		ev.button_index = buttons[action]
		InputMap.action_add_event(action, ev)
	for action in axes:
		var ev := InputEventJoypadMotion.new()
		ev.axis = axes[action][0]
		ev.axis_value = axes[action][1]
		InputMap.action_add_event(action, ev)
