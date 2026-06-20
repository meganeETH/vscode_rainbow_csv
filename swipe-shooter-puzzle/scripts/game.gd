extends Node2D
## Swipe Shooter Puzzle
##
## A swipe-to-aim brick-breaker / "ballz" style puzzle game.
## Swipe upward to aim, release to launch your stream of balls. Hit the numbered
## bricks to break them before the stack reaches the bottom danger line. Collect
## the "+1" orbs to grow your barrage.
##
## Everything is drawn procedurally (no external art assets) and the ball physics
## are handled manually with sub-stepped circle-vs-AABB collisions, so the game
## is fully deterministic and dependency-free.

const COLS := 7
const FIELD_TOP := 175.0
const MAX_ROWS := 10
const BALL_RADIUS := 11.0
const BALL_SPEED := 1150.0
const SHOOT_INTERVAL := 0.05
const STEP_LEN := 6.0
# Minimum steepness of the aim direction; prevents flat / downward shots.
const MIN_AIM_STEEPNESS := 0.18

const DESIGN_W := 720.0
const DESIGN_H := 1280.0

enum State { AIM, SHOOT, OVER }

var cell := 0.0
var field_left := 0.0
var field_right := DESIGN_W
var danger_y := 0.0
var launch_y := 0.0
var launch_x := DESIGN_W * 0.5

# Vector2i(col, row) -> { "hp": int, "type": int }  (type 0 = brick, 1 = +1 orb)
var bricks := {}
# Each ball is { "pos": Vector2, "vel": Vector2 }
var balls := []

var ball_count := 1
var balls_to_spawn := 0
var fire_timer := 0.0
var first_return_x := -1.0

var aim_dir := Vector2(0, -1)
var aiming := false

var state := State.AIM
var level := 1
var score := 0

var rng := RandomNumberGenerator.new()
var font: Font


func _ready() -> void:
	rng.randomize()
	font = ThemeDB.fallback_font
	cell = (field_right - field_left) / float(COLS)
	danger_y = FIELD_TOP + MAX_ROWS * cell
	launch_y = danger_y + 34.0
	new_game()


func new_game() -> void:
	bricks.clear()
	balls.clear()
	score = 0
	level = 1
	ball_count = 1
	balls_to_spawn = 0
	launch_x = (field_left + field_right) * 0.5
	aim_dir = Vector2(0, -1)
	aiming = false
	for i in range(3):
		_shift_down()
		_spawn_top_row()
	state = State.AIM
	queue_redraw()


# ---------------------------------------------------------------- board

func _shift_down() -> void:
	var moved := {}
	for key in bricks:
		moved[Vector2i(key.x, key.y + 1)] = bricks[key]
	bricks = moved


func _base_hp() -> int:
	return max(1, level + rng.randi_range(-1, 2))


func _spawn_top_row() -> void:
	var placed := 0
	var empties := []
	for c in range(COLS):
		if rng.randf() < 0.6:
			bricks[Vector2i(c, 0)] = {"hp": _base_hp(), "type": 0}
			placed += 1
		else:
			empties.append(c)
	if placed == 0:
		var c := rng.randi_range(0, COLS - 1)
		bricks[Vector2i(c, 0)] = {"hp": _base_hp(), "type": 0}
		empties.erase(c)
	if empties.size() > 0 and rng.randf() < 0.8:
		var oc: int = empties[rng.randi_range(0, empties.size() - 1)]
		bricks[Vector2i(oc, 0)] = {"hp": 1, "type": 1}


func _brick_rect(key: Vector2i) -> Rect2:
	var pad := 3.0
	var x := field_left + key.x * cell + pad
	var y := FIELD_TOP + key.y * cell + pad
	var s := cell - pad * 2.0
	return Rect2(x, y, s, s)


# ---------------------------------------------------------------- input

# Touch only: on desktop, emulate_touch_from_mouse turns mouse input into the
# same screen-touch / screen-drag events, so a single code path covers both.
func _input(event: InputEvent) -> void:
	if state == State.OVER:
		if event is InputEventScreenTouch and event.pressed:
			new_game()
		return
	if state != State.AIM:
		return

	if event is InputEventScreenTouch:
		if event.pressed:
			aiming = true
			_update_aim(event.position)
		elif aiming:
			aiming = false
			_fire()
		queue_redraw()
	elif event is InputEventScreenDrag and aiming:
		_update_aim(event.position)
		queue_redraw()


func _update_aim(pointer: Vector2) -> void:
	var origin := Vector2(launch_x, launch_y - BALL_RADIUS)
	var d := pointer - origin
	if d.length() < 1.0:
		return
	d = d.normalized()
	if d.y > -MIN_AIM_STEEPNESS:
		d.y = -MIN_AIM_STEEPNESS
		d = d.normalized()
	aim_dir = d


func _fire() -> void:
	if aim_dir.y >= 0.0:
		return
	state = State.SHOOT
	balls_to_spawn = ball_count
	fire_timer = 0.0
	first_return_x = -1.0
	balls.clear()


# ---------------------------------------------------------------- sim

func _physics_process(delta: float) -> void:
	if state != State.SHOOT:
		return

	if balls_to_spawn > 0:
		fire_timer -= delta
		if fire_timer <= 0.0:
			balls.append({
				"pos": Vector2(launch_x, launch_y - BALL_RADIUS - 1.0),
				"vel": aim_dir * BALL_SPEED,
			})
			balls_to_spawn -= 1
			fire_timer = SHOOT_INTERVAL

	var still_active := []
	for b in balls:
		if _advance_ball(b, delta):
			still_active.append(b)
		elif first_return_x < 0.0:
			first_return_x = b.pos.x
	balls = still_active

	if balls_to_spawn == 0 and balls.is_empty():
		_end_turn()
	queue_redraw()


# Moves a single ball for one frame; returns false once it has fallen back to
# the launch line (and is therefore out of play).
func _advance_ball(b: Dictionary, delta: float) -> bool:
	var pos: Vector2 = b.pos
	var vel: Vector2 = b.vel
	var remaining := vel.length() * delta
	var alive := true

	while remaining > 0.0:
		var step: float = min(STEP_LEN, remaining)
		remaining -= step
		pos += vel.normalized() * step

		if pos.x - BALL_RADIUS < field_left:
			pos.x = field_left + BALL_RADIUS
			vel.x = abs(vel.x)
		elif pos.x + BALL_RADIUS > field_right:
			pos.x = field_right - BALL_RADIUS
			vel.x = -abs(vel.x)
		if pos.y - BALL_RADIUS < FIELD_TOP:
			pos.y = FIELD_TOP + BALL_RADIUS
			vel.y = abs(vel.y)
		if pos.y + BALL_RADIUS >= launch_y:
			alive = false
			break

		var res := _resolve_bricks(pos, vel)
		pos = res[0]
		vel = res[1]

		# Keep a constant speed and never let a ball travel (near-)horizontally,
		# otherwise it could bounce between the side walls forever and the turn
		# would never end.
		var sp := vel.length()
		if sp > 0.0:
			var d := vel / sp
			if absf(d.y) < 0.12:
				d.y = 0.12 if d.y >= 0.0 else -0.12
				d = d.normalized()
			vel = d * BALL_SPEED

	b.pos = pos
	b.vel = vel
	return alive


# Resolves the deepest brick collision for this sub-step and collects any orbs
# the ball is overlapping. Returns [pos, vel] after the bounce.
func _resolve_bricks(pos: Vector2, vel: Vector2) -> Array:
	var hit_key = null
	var hit_normal := Vector2.ZERO
	var deepest := -1.0
	var orb_keys := []

	for key in bricks:
		var r := _brick_rect(key)
		var closest := Vector2(
			clampf(pos.x, r.position.x, r.position.x + r.size.x),
			clampf(pos.y, r.position.y, r.position.y + r.size.y))
		var diff := pos - closest
		var dist := diff.length()
		if dist >= BALL_RADIUS:
			continue
		if bricks[key].type == 1:
			orb_keys.append(key)
			continue
		var pen := BALL_RADIUS - dist
		if pen > deepest:
			deepest = pen
			hit_key = key
			hit_normal = (diff / dist) if dist > 0.001 else -vel.normalized()

	for key in orb_keys:
		bricks.erase(key)
		ball_count += 1

	if hit_key != null:
		var b = bricks[hit_key]
		b.hp -= 1
		if b.hp <= 0:
			bricks.erase(hit_key)
			score += 1
		vel = vel - 2.0 * vel.dot(hit_normal) * hit_normal
		pos += hit_normal * (deepest + 0.5)

	return [pos, vel]


func _end_turn() -> void:
	if first_return_x >= 0.0:
		launch_x = clampf(first_return_x, field_left + BALL_RADIUS, field_right - BALL_RADIUS)
	_shift_down()
	for key in bricks:
		if key.y >= MAX_ROWS:
			state = State.OVER
			queue_redraw()
			return
	_spawn_top_row()
	level += 1
	state = State.AIM


# ---------------------------------------------------------------- draw

func _draw() -> void:
	draw_rect(Rect2(field_left, FIELD_TOP, field_right - field_left, launch_y - FIELD_TOP),
			Color(0.07, 0.08, 0.12))
	draw_line(Vector2(field_left, danger_y), Vector2(field_right, danger_y),
			Color(0.9, 0.2, 0.3, 0.7), 3.0)

	for key in bricks:
		var b = bricks[key]
		var r := _brick_rect(key)
		var center := r.get_center()
		if b.type == 1:
			draw_circle(center, r.size.x * 0.42, Color(0.2, 0.8, 1.0))
			draw_circle(center, r.size.x * 0.30, Color(0.05, 0.2, 0.3))
			_text_centered("+1", center, r.size.x, 28, Color.WHITE)
		else:
			var t := clampf(float(b.hp) / float(level + 4), 0.0, 1.0)
			var col := Color(0.25, 0.75, 0.45).lerp(Color(0.9, 0.35, 0.25), t)
			draw_rect(r, col)
			draw_rect(r, col.darkened(0.4), false, 2.0)
			_text_centered(str(b.hp), center, r.size.x, 34, Color.WHITE)

	if state == State.AIM and aiming:
		_draw_aim()

	var lp := Vector2(launch_x, launch_y - BALL_RADIUS)
	draw_circle(lp, BALL_RADIUS, Color(0.95, 0.95, 1.0))
	for ball in balls:
		draw_circle(ball.pos, BALL_RADIUS, Color(0.95, 0.95, 1.0))

	_text_left("Score: %d" % score, Vector2(20, 64), 40, Color.WHITE)
	_text_centered("Lv %d" % level, Vector2(DESIGN_W * 0.5, 48), 240, 40, Color(0.8, 0.85, 1.0))
	_text_centered("x%d" % ball_count, Vector2(launch_x, launch_y + 24), 140, 30, Color(0.8, 0.9, 1.0))

	if state == State.AIM and not aiming:
		_text_centered("Swipe up to aim & shoot", Vector2(DESIGN_W * 0.5, launch_y - 44),
				DESIGN_W, 28, Color(1, 1, 1, 0.5))

	if state == State.OVER:
		_draw_game_over()


func _draw_aim() -> void:
	var p := Vector2(launch_x, launch_y - BALL_RADIUS)
	var dir := aim_dir
	var col := Color(1, 1, 1, 0.55)
	var budget := 1500.0
	var bounces := 0
	while budget > 0.0 and bounces < 3:
		var tx := INF
		if dir.x > 0.001:
			tx = (field_right - BALL_RADIUS - p.x) / dir.x
		elif dir.x < -0.001:
			tx = (field_left + BALL_RADIUS - p.x) / dir.x
		var ty := INF
		if dir.y < -0.001:
			ty = (FIELD_TOP + BALL_RADIUS - p.y) / dir.y
		var seg: float = min(min(tx, ty), budget)
		if seg <= 0.0:
			break
		var np := p + dir * seg
		draw_dashed_line(p, np, col, 2.0, 12.0)
		budget -= seg
		p = np
		if seg < ty:
			dir.x = -dir.x  # reflected off a side wall
		else:
			break  # reached the top, stop the preview
		bounces += 1


func _draw_game_over() -> void:
	draw_rect(Rect2(0, 0, DESIGN_W, DESIGN_H), Color(0, 0, 0, 0.65))
	_text_centered("GAME OVER", Vector2(DESIGN_W * 0.5, 520), DESIGN_W, 72, Color(1, 0.5, 0.4))
	_text_centered("Score: %d" % score, Vector2(DESIGN_W * 0.5, 620), DESIGN_W, 48, Color.WHITE)
	_text_centered("Reached level %d" % level, Vector2(DESIGN_W * 0.5, 678), DESIGN_W, 34,
			Color(0.8, 0.85, 1.0))
	_text_centered("Tap to play again", Vector2(DESIGN_W * 0.5, 800), DESIGN_W, 40,
			Color(1, 1, 1, 0.85))


func _text_centered(text: String, center: Vector2, width: float, size: int, color: Color) -> void:
	var pos := Vector2(center.x - width * 0.5, center.y + size * 0.35)
	draw_string(font, pos, text, HORIZONTAL_ALIGNMENT_CENTER, width, size, color)


func _text_left(text: String, pos: Vector2, size: int, color: Color) -> void:
	draw_string(font, pos, text, HORIZONTAL_ALIGNMENT_LEFT, -1, size, color)
