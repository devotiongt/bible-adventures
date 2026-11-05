extends Node
## Global game state (autoload "Game"): inventory, recipes, ark stages,
## controls and saving. Data is read from res://data/*.json so it is easy
## to add items, recipes or chapters without touching code.

signal inventory_changed
signal ark_stage_changed(stage: int)
signal notify(text: String)

const SAVE_PATH := "user://savegame.json"

var items: Dictionary = {}
var recipes: Array = []
var ark_stages: Array = []

var inventory: Dictionary = {}
var ark_stage: int = 0  ## Number of ark stages already built.
var intro_seen := false

## While a panel or dialog is open, Noah doesn't move or interact.
var ui_blocked := false

## Command-line arguments after "--" (e.g. --new, --screenshot=path.png).
var args: Dictionary = {}
var _saving_enabled := true


func _ready() -> void:
	_parse_args()
	_setup_input()
	items = _load_json("res://data/items.json")
	recipes = _load_json("res://data/recipes.json")
	ark_stages = _load_json("res://data/ark.json")

	_saving_enabled = not args.has("no_save")
	if not args.has("new"):
		load_game()
	if args.has("demo"):
		for id in items:
			inventory[id] = 40
	if args.has("stages"):
		ark_stage = clampi(int(args["stages"]), 0, ark_stages.size())
	if args.has("no_intro"):
		intro_seen = true


# --- Inventory ----------------------------------------------------------------

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
	return items.get(id, {}).get("name", id)


func item_color(id: String) -> Color:
	return Color(items.get(id, {}).get("color", "#ffffff"))


func is_tool(id: String) -> bool:
	return items.get(id, {}).get("tool", false)


## Text like "plank 4/12 · peg 0/8".
func requirements_text(requirements: Dictionary) -> String:
	var parts: PackedStringArray = []
	for id in requirements:
		parts.append("%s %d/%d" % [item_name(id).to_lower(), count(id), int(requirements[id])])
	return " · ".join(parts)


# --- Crafting -----------------------------------------------------------------

func can_craft(recipe: Dictionary) -> bool:
	var result: String = recipe["result"]
	if is_tool(result) and has_item(result):
		return false
	return has_all(recipe["ingredients"])


func craft(recipe: Dictionary) -> bool:
	var result: String = recipe["result"]
	if is_tool(result) and has_item(result):
		notify.emit("You already have a %s." % item_name(result).to_lower())
		return false
	if not has_all(recipe["ingredients"]):
		notify.emit("You are missing materials for %s." % item_name(result).to_lower())
		return false
	consume(recipe["ingredients"])
	var amount := int(recipe["amount"])
	add(result, amount)
	notify.emit("You crafted %d × %s" % [amount, item_name(result)])
	return true


# --- Ark ----------------------------------------------------------------------

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
	if not has_item("hammer"):
		notify.emit("You need a hammer to build. Craft it with C.")
		return false
	if not has_all(stage["materials"]):
		notify.emit("Missing materials: " + requirements_text(stage["materials"]))
		return false
	consume(stage["materials"])
	ark_stage += 1
	inventory_changed.emit()
	save_game()
	ark_stage_changed.emit(ark_stage)
	return true


# --- Saving -------------------------------------------------------------------

func save_game() -> void:
	if not _saving_enabled:
		return
	var file := FileAccess.open(SAVE_PATH, FileAccess.WRITE)
	if file == null:
		return
	file.store_string(JSON.stringify({
		"inventory": inventory,
		"ark_stage": ark_stage,
		"intro_seen": intro_seen,
	}, "\t"))


func load_game() -> void:
	if not FileAccess.file_exists(SAVE_PATH):
		return
	var data = JSON.parse_string(FileAccess.get_file_as_string(SAVE_PATH))
	if typeof(data) != TYPE_DICTIONARY:
		return
	inventory.clear()
	var saved: Dictionary = data.get("inventory", {})
	for id in saved:
		inventory[id] = int(saved[id])
	ark_stage = int(data.get("ark_stage", 0))
	intro_seen = bool(data.get("intro_seen", false))


func reset_game() -> void:
	inventory.clear()
	ark_stage = 0
	intro_seen = false
	save_game()
	get_tree().reload_current_scene()


# --- Utilities ----------------------------------------------------------------

func _load_json(path: String) -> Variant:
	var data = JSON.parse_string(FileAccess.get_file_as_string(path))
	if data == null:
		push_error("Could not read " + path)
	return data


func _parse_args() -> void:
	for arg in OS.get_cmdline_user_args():
		var kv := arg.trim_prefix("--").split("=", true, 1)
		args[kv[0]] = kv[1] if kv.size() > 1 else "1"


## Keyboard and gamepad. Touch controls for mobile will be added on top of these actions.
func _setup_input() -> void:
	var keys := {
		"move_left": [KEY_A, KEY_LEFT],
		"move_right": [KEY_D, KEY_RIGHT],
		"move_up": [KEY_W, KEY_UP],
		"move_down": [KEY_S, KEY_DOWN],
		"interact": [KEY_E, KEY_SPACE],
		"craft": [KEY_C, KEY_TAB],
		"camera_left": [KEY_Q],
		"camera_right": [KEY_R],
		"restart": [KEY_F9],
	}
	var buttons := {
		"interact": JOY_BUTTON_A,
		"craft": JOY_BUTTON_Y,
		"camera_left": JOY_BUTTON_LEFT_SHOULDER,
		"camera_right": JOY_BUTTON_RIGHT_SHOULDER,
	}
	var axes := {
		"move_left": [JOY_AXIS_LEFT_X, -1.0],
		"move_right": [JOY_AXIS_LEFT_X, 1.0],
		"move_up": [JOY_AXIS_LEFT_Y, -1.0],
		"move_down": [JOY_AXIS_LEFT_Y, 1.0],
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
