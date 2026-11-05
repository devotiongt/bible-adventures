extends CanvasLayer
## Interface: objective, inventory, action prompt, notices, crafting
## panel and dialogs with the Bible texts.

const PARCHMENT := Color(0.96, 0.91, 0.8, 0.94)
const PARCHMENT_DARK := Color(0.88, 0.8, 0.64, 0.95)
const INK := Color("4a3424")
const ACCENT := Color("b5652b")
const OK := Color("3f7d3a")
const MISSING := Color("b0413e")

var player: Node

var _objective: Label
var _prompt_panel: PanelContainer
var _prompt: Label
var _inventory: HBoxContainer
var _toasts: VBoxContainer
var _craft_root: Control
var _craft_list: VBoxContainer
var _dialog_root: Control
var _dialog_text: Label
var _dialog_queue: Array[String] = []


func _ready() -> void:
	var root := Control.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.theme = _make_theme()
	add_child(root)

	var margin := MarginContainer.new()
	margin.set_anchors_preset(Control.PRESET_FULL_RECT)
	for side in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 16)
	root.add_child(margin)
	var column := VBoxContainer.new()
	margin.add_child(column)

	var top := HBoxContainer.new()
	column.add_child(top)
	top.add_child(_build_objective_panel())
	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	top.add_child(spacer)
	_toasts = VBoxContainer.new()
	_toasts.custom_minimum_size.x = 320
	_toasts.alignment = BoxContainer.ALIGNMENT_BEGIN
	top.add_child(_toasts)

	var fill := Control.new()
	fill.size_flags_vertical = Control.SIZE_EXPAND_FILL
	column.add_child(fill)

	_prompt_panel = PanelContainer.new()
	_prompt = Label.new()
	_prompt_panel.add_child(_prompt)
	column.add_child(_centered(_prompt_panel))
	var gap := Control.new()
	gap.custom_minimum_size.y = 8
	column.add_child(gap)

	var inv_panel := PanelContainer.new()
	_inventory = HBoxContainer.new()
	_inventory.add_theme_constant_override("separation", 10)
	inv_panel.add_child(_inventory)
	column.add_child(_centered(inv_panel))

	_build_craft_panel(root)
	_build_dialog(root)
	_ignore_mouse(margin)

	Game.inventory_changed.connect(_on_inventory_changed)
	Game.ark_stage_changed.connect(_on_ark_stage_changed)
	Game.notify.connect(toast)
	_on_inventory_changed()

	if not Game.intro_seen:
		show_dialog([
			"The earth was filled with violence, but Noah found grace in the eyes of the Lord. (Genesis 6:8)",
			"God said to Noah: “Make thee an ark of gopher wood; rooms shalt thou make in the ark, and shalt pitch it within and without with pitch.” (Genesis 6:14)",
			"Your mission: gather materials on the island, craft tools and build the ark stage by stage.",
			"Tip: chop trees with E to get wood, gather fiber from the reeds and stone from the rocks. Press C to open the crafting panel: start with a hammer.",
		])
		Game.intro_seen = true
		Game.save_game()


func _process(_delta: float) -> void:
	_update_objective()
	if not _dialog_queue.is_empty() or _dialog_root.visible:
		if Input.is_action_just_pressed("interact") or Input.is_action_just_pressed("ui_accept"):
			_next_dialog()
		return
	if Input.is_action_just_pressed("craft"):
		_toggle_craft()
	elif _craft_root.visible and Input.is_action_just_pressed("ui_cancel"):
		_toggle_craft()
	if Input.is_action_just_pressed("restart"):
		Game.reset_game()
		return

	var target: Node = player.target if player else null
	_prompt_panel.visible = target != null and not Game.ui_blocked
	if _prompt_panel.visible:
		_prompt.text = "[E]  " + target.get_prompt()


func _input(event: InputEvent) -> void:
	if _dialog_root.visible and event is InputEventMouseButton and event.pressed:
		_next_dialog()
		get_viewport().set_input_as_handled()


func _unhandled_input(event: InputEvent) -> void:
	if _craft_root.visible and event is InputEventKey and event.pressed and not event.echo:
		var index: int = event.keycode - KEY_1
		if index >= 0 and index < Game.recipes.size():
			Game.craft(Game.recipes[index])


# --- Objective and inventory --------------------------------------------------

func _build_objective_panel() -> PanelContainer:
	var panel := PanelContainer.new()
	var box := VBoxContainer.new()
	panel.add_child(box)
	var title := Label.new()
	title.text = "Chapter 1 · Noah's Ark"
	title.add_theme_font_size_override("font_size", 22)
	title.add_theme_color_override("font_color", ACCENT)
	box.add_child(title)
	_objective = Label.new()
	_objective.custom_minimum_size.x = 380
	_objective.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	box.add_child(_objective)
	var help := Label.new()
	help.text = "WASD move · E action · C craft · Q/R rotate camera"
	help.add_theme_font_size_override("font_size", 13)
	help.modulate.a = 0.7
	box.add_child(help)
	return panel


func _update_objective() -> void:
	if Game.ark_complete():
		_objective.text = "The ark is finished! Soon the animals will arrive, two by two."
		return
	var stage := Game.next_ark_stage()
	var text := "Stage %d of %d: %s\n%s" % [Game.ark_stage + 1, Game.ark_stages.size(),
			stage["name"], Game.requirements_text(stage["materials"])]
	if not Game.has_item("hammer"):
		text += "\nFirst craft a hammer (C)."
	_objective.text = text


func _on_inventory_changed() -> void:
	for child in _inventory.get_children():
		child.queue_free()
	var any := false
	for id in Game.items:
		if not Game.has_item(id):
			continue
		any = true
		_inventory.add_child(_make_slot(id))
	if not any:
		var empty := Label.new()
		empty.text = "Inventory empty: walk up to a tree and press E"
		_inventory.add_child(empty)
	if _craft_root and _craft_root.visible:
		_rebuild_craft_list()


func _make_slot(id: String) -> Control:
	var box := VBoxContainer.new()
	box.alignment = BoxContainer.ALIGNMENT_CENTER
	var swatch := Panel.new()
	swatch.custom_minimum_size = Vector2(34, 34)
	var sb := StyleBoxFlat.new()
	sb.bg_color = Game.item_color(id)
	sb.set_corner_radius_all(8)
	sb.set_border_width_all(2)
	sb.border_color = INK.lightened(0.3)
	swatch.add_theme_stylebox_override("panel", sb)
	var center := CenterContainer.new()
	center.add_child(swatch)
	box.add_child(center)
	var count := Label.new()
	count.text = "%s ×%d" % [Game.item_name(id), Game.count(id)] if not Game.is_tool(id) else Game.item_name(id)
	count.add_theme_font_size_override("font_size", 14)
	count.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	box.add_child(count)
	box.tooltip_text = Game.items[id].get("description", "")
	return box


# --- Notices ------------------------------------------------------------------

func toast(text: String) -> void:
	var panel := PanelContainer.new()
	var label := Label.new()
	label.text = text
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.custom_minimum_size.x = 290
	panel.add_child(label)
	panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_toasts.add_child(panel)
	while _toasts.get_child_count() > 5:
		_toasts.get_child(0).free()
	var t := panel.create_tween()
	t.tween_interval(2.6)
	t.tween_property(panel, "modulate:a", 0.0, 0.5)
	t.tween_callback(panel.queue_free)


func _on_ark_stage_changed(stage: int) -> void:
	var data: Dictionary = Game.ark_stages[stage - 1]
	var lines: Array[String] = ["Stage finished: %s!" % data["name"], data["on_complete"]]
	if Game.ark_complete():
		lines.append("“Thus did Noah; according to all that God commanded him, so did he.” (Genesis 6:22)")
		lines.append("Chapter 1 complete! Coming soon: the animals come to the ark two by two.")
	show_dialog(lines)


# --- Crafting -----------------------------------------------------------------

func _build_craft_panel(root: Control) -> void:
	_craft_root = CenterContainer.new()
	_craft_root.set_anchors_preset(Control.PRESET_FULL_RECT)
	_craft_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_craft_root.visible = false
	root.add_child(_craft_root)
	var panel := PanelContainer.new()
	_craft_root.add_child(panel)
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 10)
	panel.add_child(box)
	var title := Label.new()
	title.text = "Craft"
	title.add_theme_font_size_override("font_size", 24)
	title.add_theme_color_override("font_color", ACCENT)
	box.add_child(title)
	_craft_list = VBoxContainer.new()
	_craft_list.add_theme_constant_override("separation", 8)
	box.add_child(_craft_list)
	var hint := Label.new()
	hint.text = "Press the number or the button · C to close"
	hint.add_theme_font_size_override("font_size", 13)
	hint.modulate.a = 0.7
	box.add_child(hint)


func _toggle_craft() -> void:
	_craft_root.visible = not _craft_root.visible
	Game.ui_blocked = _craft_root.visible
	if _craft_root.visible:
		_rebuild_craft_list()


func _rebuild_craft_list() -> void:
	for child in _craft_list.get_children():
		child.queue_free()
	for i in Game.recipes.size():
		var recipe: Dictionary = Game.recipes[i]
		var result: String = recipe["result"]
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 12)
		var swatch := ColorRect.new()
		swatch.color = Game.item_color(result)
		swatch.custom_minimum_size = Vector2(22, 22)
		row.add_child(_centered(swatch))
		var name_label := Label.new()
		name_label.text = "%d. %s ×%d" % [i + 1, Game.item_name(result), int(recipe["amount"])]
		name_label.custom_minimum_size.x = 170
		row.add_child(name_label)
		var ingredients := RichTextLabel.new()
		ingredients.bbcode_enabled = true
		ingredients.fit_content = true
		ingredients.scroll_active = false
		ingredients.custom_minimum_size.x = 300
		ingredients.text = _ingredients_bbcode(recipe["ingredients"])
		ingredients.add_theme_color_override("default_color", INK)
		row.add_child(ingredients)
		var button := Button.new()
		var owned := Game.is_tool(result) and Game.has_item(result)
		button.text = "Already owned" if owned else "Craft"
		button.disabled = not Game.can_craft(recipe)
		button.custom_minimum_size.x = 120
		button.pressed.connect(Game.craft.bind(recipe))
		row.add_child(button)
		_craft_list.add_child(row)


func _ingredients_bbcode(requirements: Dictionary) -> String:
	var parts: PackedStringArray = []
	for id in requirements:
		var need := int(requirements[id])
		var color := OK if Game.count(id) >= need else MISSING
		parts.append("[color=#%s]%s %d/%d[/color]" % [color.to_html(false), Game.item_name(id).to_lower(), Game.count(id), need])
	return ", ".join(parts)


# --- Dialogs ------------------------------------------------------------------

func _build_dialog(root: Control) -> void:
	_dialog_root = MarginContainer.new()
	_dialog_root.set_anchors_preset(Control.PRESET_FULL_RECT)
	_dialog_root.add_theme_constant_override("margin_bottom", 40)
	_dialog_root.visible = false
	root.add_child(_dialog_root)
	var align := VBoxContainer.new()
	align.alignment = BoxContainer.ALIGNMENT_END
	_dialog_root.add_child(align)
	var panel := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = PARCHMENT
	sb.set_corner_radius_all(16)
	sb.set_border_width_all(3)
	sb.border_color = ACCENT
	sb.set_content_margin_all(24)
	panel.add_theme_stylebox_override("panel", sb)
	var box := VBoxContainer.new()
	panel.add_child(box)
	_dialog_text = Label.new()
	_dialog_text.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_dialog_text.custom_minimum_size.x = 680
	_dialog_text.add_theme_font_size_override("font_size", 22)
	box.add_child(_dialog_text)
	var hint := Label.new()
	hint.text = "E / Enter / click to continue"
	hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	hint.add_theme_font_size_override("font_size", 13)
	hint.modulate.a = 0.6
	box.add_child(hint)
	align.add_child(_centered(panel))


func show_dialog(lines: Array[String]) -> void:
	_dialog_queue.append_array(lines)
	if not _dialog_root.visible:
		_craft_root.visible = false
		_next_dialog()


func _next_dialog() -> void:
	if _dialog_queue.is_empty():
		_dialog_root.visible = false
		Game.ui_blocked = false
		return
	_dialog_root.visible = true
	Game.ui_blocked = true
	_dialog_text.text = _dialog_queue.pop_front()


# --- Utilities ----------------------------------------------------------------

func _centered(control: Control) -> CenterContainer:
	var center := CenterContainer.new()
	center.mouse_filter = Control.MOUSE_FILTER_IGNORE
	center.add_child(control)
	return center


func _ignore_mouse(node: Node) -> void:
	if node is Container and not node is PanelContainer:
		(node as Control).mouse_filter = Control.MOUSE_FILTER_IGNORE
	elif node is Control and not node is BaseButton:
		(node as Control).mouse_filter = Control.MOUSE_FILTER_IGNORE
	for child in node.get_children():
		_ignore_mouse(child)


func _make_theme() -> Theme:
	var theme := Theme.new()
	theme.default_font_size = 17
	var panel := StyleBoxFlat.new()
	panel.bg_color = PARCHMENT
	panel.set_corner_radius_all(12)
	panel.set_border_width_all(2)
	panel.border_color = INK.lightened(0.45)
	panel.set_content_margin_all(12)
	theme.set_stylebox("panel", "PanelContainer", panel)
	theme.set_color("font_color", "Label", INK)

	var normal := StyleBoxFlat.new()
	normal.bg_color = ACCENT
	normal.set_corner_radius_all(8)
	normal.set_content_margin_all(6)
	var hover := normal.duplicate() as StyleBoxFlat
	hover.bg_color = ACCENT.lightened(0.15)
	var pressed := normal.duplicate() as StyleBoxFlat
	pressed.bg_color = ACCENT.darkened(0.15)
	var disabled := normal.duplicate() as StyleBoxFlat
	disabled.bg_color = PARCHMENT_DARK
	theme.set_stylebox("normal", "Button", normal)
	theme.set_stylebox("hover", "Button", hover)
	theme.set_stylebox("pressed", "Button", pressed)
	theme.set_stylebox("disabled", "Button", disabled)
	theme.set_stylebox("focus", "Button", StyleBoxEmpty.new())
	for state in ["font_color", "font_hover_color", "font_pressed_color", "font_focus_color"]:
		theme.set_color(state, "Button", Color.WHITE)
	theme.set_color("font_disabled_color", "Button", INK.lightened(0.4))
	return theme
