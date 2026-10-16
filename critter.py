# -*- coding: utf-8 -*-
"""Пиксельное существо: окно-спрайт, анимации, физика, прыжки по окнам, перетаскивание.

Клод и его друзья — наследники Critter. Общие данные (кадры, масштаб, список окон, время)
берутся из world — главного Клода.
"""
import math
import random
import tkinter as tk

import winsys
from ui import KEY

GRAVITY = 0.7


def body_top(rows):
    """Строка и центр «макушки»: первая строка с непрерывным куском тела ≥ 8 пикселей."""
    for r, row in enumerate(rows):
        best, start, run = (0, 0), None, 0
        for c, ch in enumerate(row + "."):
            if ch == "o":
                start = c if run == 0 else start
                run += 1
            else:
                if run > best[0]:
                    best = (run, start)
                run = 0
        if best[0] >= 8:
            return r, best[1] + best[0] / 2
    return None, None


class Critter:
    WALK_SPEED = 1.6

    def __init__(self, world, win, color=None):
        self.world = world if world is not None else self
        self.win = win
        self.color = color
        win.overrideredirect(True)
        win.configure(bg=KEY)
        win.attributes("-transparentcolor", KEY)
        win.attributes("-topmost", True)
        self.canvas = tk.Canvas(win, bg=KEY, highlightthickness=0, bd=0)
        self.canvas.pack()
        self.x = self.y = 0.0
        self.vx = self.vy = 0.0
        self.flip = False
        self.anim = None
        self.anim_time = 0.0
        self.loops_left = 0
        self.state = "idle"
        self.state_until = 0.0
        self.perch = None          # окно, на котором стоим
        self.perch_rect = None
        self.next_edge_check = 0.0
        self.fall_from = 0.0
        self.target_x = 0.0
        self.drawn_key = None
        self.drag = None
        self.bob = 0.0
        self.w = self.h = 0

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag_motion)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

    # ---------- общие данные ----------
    @property
    def now(self):
        return self.world.clock

    def scale_px(self):
        return self.world.scale.get()

    def resize(self):
        s = self.scale_px()
        self.w, self.h = self.world.gw * s, self.world.gh * s
        self.canvas.config(width=self.w, height=self.h)
        self.drawn_key = None

    # ---------- анимации ----------
    def play(self, name, loops=None):
        if name not in self.world.anims:
            name = "idle"
        if name != self.anim:
            self.anim_time = 0.0
        self.anim = name
        self.loops_left = loops if loops is not None else self.world.anims[name].get("loops", 1)

    def current_frame(self):
        spec = self.world.anims[self.anim]
        seq = spec["frames"]
        idx = int(self.anim_time * spec.get("fps", 4))
        if idx >= len(seq):
            if self.state == "oneshot":
                self.loops_left -= 1
                if self.loops_left <= 0:
                    self.after_oneshot()
                    return self.current_frame()
            self.anim_time = 0.0
            idx = 0
        return self.adjust_frame(seq[idx])

    def adjust_frame(self, frame):
        return frame

    def after_oneshot(self):
        self.set_state("idle")

    # ---------- отрисовка ----------
    def draw(self, frame_name):
        w = self.world
        mirrored = frame_name.startswith("~") ^ self.flip
        hat = w.current_hat()
        key = (frame_name, mirrored, self.scale_px(), hat, w.frames_version)
        if key == self.drawn_key:
            return
        self.drawn_key = key
        rows = [row.ljust(w.gw, ".") for row in w.frames[frame_name.lstrip("~")]]
        rows = ["." * w.gw] * (w.gh - len(rows)) + rows  # кадры пониже прижимаются к полу
        if mirrored:
            rows = [row[::-1] for row in rows]
        if hat and hat in w.hats:
            rows = self.put_hat(rows, w.hats[hat])
        palette = dict(w.palette)
        if self.color:
            palette["o"] = self.color
        s = self.scale_px()
        self.canvas.delete("all")
        for r, row in enumerate(rows):
            for c, ch in enumerate(row):
                if ch != "." and ch in palette:
                    x0, y0 = c * s, r * s
                    self.canvas.create_rectangle(x0, y0, x0 + s, y0 + s, fill=palette[ch], width=0)

    @staticmethod
    def put_hat(rows, hat):
        top, center = body_top(rows)
        if top is None:
            return rows
        grid = [list(row) for row in rows]
        hw = max(len(r) for r in hat)
        left = int(round(center - hw / 2))
        for i, hrow in enumerate(reversed(hat)):
            r = top - 1 - i
            if r < 0:
                break
            for j, ch in enumerate(hrow):
                c = left + j
                if ch != "." and 0 <= c < len(grid[r]):
                    grid[r][c] = ch
        return ["".join(g) for g in grid]

    def show_at(self):
        self.win.geometry(f"{self.w}x{self.h}+{int(self.x)}+{int(self.y)}")

    # ---------- пол, стены и окна ----------
    def bounds(self):
        """(левый край, правый край, пол) с учётом окна, на котором стоим."""
        if self.perch and self.perch_rect:
            l, t, r, _ = self.perch_rect
            return l, max(l, r - self.w), t - self.h
        l, _, r, b = winsys.work_area()
        return l, r - self.w, b - self.h

    def drop_perch(self):
        self.perch = self.perch_rect = None
        if self.state not in ("drag", "jump", "fall"):
            self.vx = self.vy = 0.0
            self.set_state("fall")

    def update_perch(self):
        if not self.perch:
            return
        if not winsys.perchable(self.perch):
            return self.drop_perch()
        rect = winsys.window_rect(self.perch)
        old = self.perch_rect
        if old and rect != old and self.state not in ("drag", "jump", "fall"):
            self.x += rect[0] - old[0]  # окно поехало — едем вместе с ним
        self.perch_rect = rect
        wa = winsys.work_area()
        if rect[1] - self.h < wa[1]:
            return self.drop_perch()
        if self.now >= self.next_edge_check:
            self.next_edge_check = self.now + 1.0
            cx = min(max(self.x + self.w / 2, rect[0] + 4), rect[2] - 4)
            if not winsys.edge_visible(self.perch, cx, rect[1] + 3):
                self.drop_perch()

    def try_land(self, prev_y):
        """Падаем: не встали ли ногами на верх какого-нибудь окна."""
        if self.vy <= 0 or not self.world.perch_enabled():
            return False
        cx = self.x + self.w / 2
        prev_b, new_b = prev_y + self.h, self.y + self.h
        top_limit = winsys.work_area()[1] + self.h
        for hwnd, rect in self.world.windows:
            l, t, r, _ = rect
            if l + 4 <= cx <= r - 4 and prev_b <= t <= new_b and t > top_limit \
                    and winsys.edge_visible(hwnd, cx, t + 3):
                self.perch, self.perch_rect = hwnd, rect
                self.y = t - self.h
                return True
        return False

    def hop_to_window(self):
        """Запрыгнуть на окно повыше, если такое есть рядом."""
        if not self.world.perch_enabled():
            return False
        s = self.scale_px() / 4
        g = GRAVITY * s
        floor_y = self.bounds()[2]
        top_limit = winsys.work_area()[1] + self.h
        options = []
        for hwnd, (l, t, r, b) in self.world.windows:
            if hwnd == self.perch or r - l < self.w + 20:
                continue
            ty = t - self.h
            rise = self.y - ty
            if t <= top_limit or rise < 40 * s or rise > 520 * s:
                continue
            tx = random.uniform(l + 4, r - self.w - 4)
            if abs(tx - self.x) > 900 or not winsys.edge_visible(hwnd, tx + self.w / 2, t + 3):
                continue
            options.append((tx, ty, rise))
        if not options:
            return False
        tx, ty, rise = random.choice(options)
        margin = 24 * s
        vy0 = -math.sqrt(2 * g * (rise + margin))
        ticks = (-vy0 + math.sqrt(2 * g * margin)) / g  # время до высоты окна на спуске
        self.perch = self.perch_rect = None
        self.state = "jump"
        self.play("air")
        self.vy = vy0
        self.vx = (tx - self.x) / max(ticks, 1)
        self.flip = self.vx < 0
        self.fall_from = floor_y
        return True

    # ---------- поведение ----------
    def set_state(self, state, anim=None):
        self.state = state
        s = self.scale_px() / 4
        if state == "idle":
            self.play(self.idle_anim())
            self.state_until = self.now + random.uniform(3, 9)
        elif state == "walk":
            l, r, _ = self.bounds()
            self.target_x = random.uniform(l, r)
            self.flip = self.target_x < self.x
            self.play("walk")
        elif state == "sleep":
            self.play("sleep")
            self.state_until = self.now + random.uniform(15, 45)
        elif state == "jump":
            self.perch = self.perch_rect = None
            self.vy = -random.uniform(9, 13) * s
            self.vx = random.choice([-1, 1]) * random.uniform(0, 3) * s
            self.play(anim or "air")
        elif state == "fall":
            self.fall_from = self.y
            self.play("air")
        elif state == "land":
            self.play("crouch")
            self.state_until = self.now + 0.15
        elif state == "oneshot":
            self.play(anim)
        elif state == "music":
            self.play("dance")
        elif state == "drag":
            self.play("held")

    def idle_anim(self):
        return "idle"

    def pick_next(self):
        roll = random.random()
        if roll < 0.12 and self.hop_to_window():
            return
        if roll < 0.18 and self.perch:
            return self.drop_perch()
        if roll < 0.50:
            self.set_state("walk")
        elif roll < 0.65:
            self.set_state("idle")
        elif roll < 0.72:
            self.set_state("jump")
        elif roll < 0.77:
            self.set_state("sleep")
        else:
            extras = [n for n in ("wave", "dance") if n in self.world.anims]
            self.set_state("oneshot", random.choice(extras)) if extras else self.set_state("idle")

    def after_land(self):
        self.set_state("idle")

    def busy(self):
        return self.state in ("drag", "jump", "fall", "bye")

    def step(self, dt):
        """Один кадр физики и поведения. Возвращает True, если только что приземлились."""
        self.anim_time += dt
        s = self.scale_px() / 4
        self.update_perch()
        l, r, floor = self.bounds()
        landed = False

        if self.world.music and self.state in ("idle", "walk") and "dance" in self.world.anims:
            self.set_state("music")
        elif self.state == "music" and not self.world.music:
            self.set_state("idle")

        if self.state == "walk":
            step = self.WALK_SPEED * s * self.world.speed_factor() * (-1 if self.flip else 1)
            if abs(self.target_x - self.x) <= abs(step):
                self.x = self.target_x
                self.set_state("idle")
            else:
                self.x += step
        elif self.state in ("jump", "fall"):
            prev_y = self.y
            self.vy += GRAVITY * s
            self.x += self.vx
            self.y += self.vy
            if self.try_land(prev_y):
                landed = True
            else:
                sl, sr, sfloor = self.bounds()
                if self.x < sl or self.x > sr:
                    self.vx = -self.vx * 0.5
                if self.y >= sfloor:
                    self.y = sfloor
                    landed = True
            if landed:
                self.vx = self.vy = 0.0
                self.set_state("land")
        elif self.state == "oneshot":
            move = self.world.anims[self.anim].get("move")
            if move:
                self.x += move * (-1 if self.flip else 1) * s
                if self.x <= l or self.x >= r:
                    self.flip = not self.flip
        elif self.state == "land" and self.now >= self.state_until:
            self.after_land()
        elif self.state in ("idle", "sleep") and self.now >= self.state_until:
            self.pick_next()

        if self.state != "drag":
            l, r, floor = self.bounds()
            self.x = max(l, min(self.x, r))
            if self.state not in ("jump", "fall"):
                self.y = floor - self.bob
        return landed

    def render(self):
        self.draw(self.current_frame())
        self.show_at()

    # ---------- мышь ----------
    def on_press(self, e):
        self.drag = {"dx": e.x_root - self.x, "dy": e.y_root - self.y,
                     "x0": e.x_root, "y0": e.y_root, "moved": False}

    def on_drag_motion(self, e):
        d = self.drag
        if not d or self.state == "bye":
            return
        if not d["moved"] and abs(e.x_root - d["x0"]) + abs(e.y_root - d["y0"]) > 4:
            d["moved"] = True
            self.perch = self.perch_rect = None
            self.set_state("drag")
            self.on_drag_start()
        if d["moved"]:
            self.x, self.y = e.x_root - d["dx"], e.y_root - d["dy"]

    def on_release(self, e):
        d, self.drag = self.drag, None
        if self.state == "bye":
            return
        if d and d["moved"]:
            self.vx = self.vy = 0.0
            self.set_state("fall")
        else:
            self.on_click()

    def on_drag_start(self):
        pass

    def on_click(self):
        if self.state not in ("jump", "fall"):
            self.set_state("jump", "happy")
