# -*- coding: utf-8 -*-
"""Клод-питомец: живёт поверх всех окон, гуляет по панели задач и окнам, помогает.

Запуск: start-pet.bat (или `pythonw pet.pyw`, или ClaudePet.exe). Закрыть: крестик при наведении,
ПКМ → «Закрыть», значок в трее или stop-pet.bat.

Мышь: потащить — перенести, клик — порадовать, поводить туда-сюда — погладить,
двойной клик — «чем помочь?», ПКМ — меню.
Горячие клавиши:
  Ctrl+Alt+C — помочь с активным окном
  Ctrl+Alt+T — сделать что-то с выделенным текстом (перевести, исправить, ...)
  Ctrl+Alt+S — обвести область экрана и спросить про неё
  Ctrl+Alt+V — спросить голосом
Свои анимации, фразы и шапки — в animations.py.
"""
import collections
import ctypes
import importlib
import importlib.util
import json
import math
import os
import random
import sys
import time
import tkinter as tk
from tkinter import messagebox

FROZEN = getattr(sys, "frozen", False)
HERE = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(sys.executable) if FROZEN else HERE
sys.path.insert(0, HERE)

import helper  # noqa: E402
import sounds  # noqa: E402
import winsys  # noqa: E402
from critter import Critter  # noqa: E402
from settings import Settings  # noqa: E402
from ui import KEY, Bubble, HelpPanel, ReminderDialog, Snipper, overlay  # noqa: E402

TICK_MS = 33             # ~30 кадров физики в секунду
BEHAVIOR_ANIMS = {"idle", "walk", "sleep", "air", "crouch", "held", "happy", "purr", "sad", "eat"}
REQUIRED_ANIMS = BEHAVIOR_ANIMS | {"wave", "think", "sparkle", "dance"}
EYE_FRAMES = ("base", "look_left", "look_right")
PID_FILE = os.path.join(APP_DIR, "pet.pid")
CLAUDE_STATE = os.path.join(os.path.expanduser("~"), ".claude", "pet-state.json")
STARTUP_BAT = os.path.join(os.environ.get("APPDATA", ""),
                           r"Microsoft\Windows\Start Menu\Programs\Startup\claude-pet.bat")
HOTKEYS = {"help": "ctrl+alt+c", "text": "ctrl+alt+t", "snip": "ctrl+alt+s", "voice": "ctrl+alt+v"}
TOGGLES = [  # (ключ настройки, подпись в меню)
    ("auto", "Гулять самому"),
    ("perch", "Залезать на окна"),
    ("music_dance", "Танцевать под музыку"),
    ("talk", "Разговаривать"),
    ("voice", "Говорить вслух"),
    ("sounds", "Звуки"),
    ("claude_link", "Реагировать на Claude Code"),
    ("tips", "Подсказки по активному окну"),
    ("replace_selection", "Сразу вставлять обработанный текст"),
    ("topmost", "Всегда поверх окон"),
]
HAT_NAMES = {"auto": "Авто (по сезону)", "none": "Без шапки", "santa": "Санта", "witch": "Ведьма",
             "party": "Колпак", "crown": "Корона", "tophat": "Цилиндр"}
POMO_WORK, POMO_BREAK, POMO_LONG = 25 * 60, 5 * 60, 15 * 60


def load_animation_module():
    """animations.py рядом с программой (его можно править), иначе — встроенный."""
    path = os.path.join(APP_DIR, "animations.py")
    if os.path.exists(path):
        spec = importlib.util.spec_from_file_location("animations_live", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    import animations
    return importlib.reload(animations)


class Friend(Critter):
    """Друг Клода другого цвета: гуляет, танцует, прыгает по окнам."""

    def __init__(self, world, color):
        super().__init__(world, tk.Toplevel(world.root), color)
        self.resize()
        l, t, r, _ = winsys.work_area()
        self.x, self.y = random.uniform(l, r - self.w), float(t)
        self.set_state("fall")
        self.canvas.bind("<Button-3>", world.on_menu)

    def on_click(self):
        super().on_click()
        self.world.sound("happy")

    def on_drag_start(self):
        self.world.sound("drag")


class Pet(Critter):
    def __init__(self):
        self.root = root = tk.Tk()
        root.title("Claude Pet")
        self.settings = st = Settings()
        self.scale = tk.IntVar(value=st["scale"])
        self.clock = 0.0
        self.music = False
        self.windows = []
        self.frames_version = 0
        self.load_animations()
        super().__init__(None, root)
        root.protocol("WM_DELETE_WINDOW", self.goodbye)

        self.opt = {}
        for key, _ in TOGGLES:
            var = tk.BooleanVar(value=st[key])
            var.trace_add("write", lambda *a, k=key, v=var: self.settings.__setitem__(k, v.get()))
            self.opt[key] = var
        self.opt["topmost"].trace_add("write", lambda *a: self.apply_topmost())
        self.hat = tk.StringVar(value=st["hat"])
        self.hat.trace_add("write", lambda *a: self.settings.__setitem__("hat", self.hat.get()))
        self.autostart = tk.BooleanVar(value=os.path.exists(STARTUP_BAT))

        sounds.ensure_sounds()
        self.voice_out = sounds.Voice()
        self.bubble = Bubble(root)
        self.bubble.c.bind("<Button-1>", lambda e: self.open_help(self.bubble_tip))
        self.bubble.c.config(cursor="hand2")
        self.asker = helper.Asker()
        self.panel = HelpPanel(self)
        self.make_close_button()
        self.resize()

        l, t, r, b = winsys.work_area()
        x = st["x"]
        self.x = float(x if x is not None and l <= x <= r - self.w else random.randint(l + 50, max(l + 51, r - 200)))
        self.y = float(self.bounds()[2])
        self.idle_since = 0.0
        self.hover_until = 0.0
        self.pet_moves, self.pet_last = [], None
        self.purr_until = 0.0
        self.last_pet_line = -99.0
        self.next_chatter = random.uniform(60, 150)
        self.next_water = 45 * 60
        self.alert_kind, self.alert_until = None, 0.0
        self.claude, self.claude_mtime, self.next_claude_poll = "idle", None, 0.0
        self.last_win, self.win_key, self.win_since = None, None, 0.0
        self.next_win_poll, self.last_tip_key, self.next_tip = 0.0, None, 60.0
        self.bubble_tip = None
        self.hidden, self.dnd_until = False, None
        self.next_slow = 0.0
        self.next_meet = 30.0
        self.peaks = collections.deque(maxlen=30)
        self.quiet_until = 0.0
        self.tick_n = 0
        self.text_job = None
        self.read_claude_state(initial=True)
        self.apply_offline_decay()

        self.tray = None
        try:
            import tray
            tray.make_icon(self.frames["base"], self.palette)
            self.tray = tray.Tray("Клод", self.toggle_hidden, self.tray_menu)
        except Exception:
            self.tray = None
        self.hotkeys = winsys.Hotkeys(HOTKEYS)
        self.meter = winsys.AudioMeter()
        self.friends = []
        for _ in range(min(4, st["friends"])):
            self.add_friend(save=False)

        c = self.canvas
        c.bind("<Motion>", self.on_hover_motion)
        c.bind("<Enter>", lambda e: self.set_hover(True))
        c.bind("<Leave>", lambda e: self.set_hover(False))
        c.bind("<Button-3>", self.on_menu)
        c.bind("<Double-Button-1>", lambda e: self.open_help())

        self.set_state("idle")
        hour = time.localtime().tm_hour
        if self.hotkeys.failed:
            self.say("горячие клавиши заняты другой программой: " + ", ".join(self.hotkeys.failed), secs=8)
        else:
            self.say("morning" if 6 <= hour < 11 else "night" if hour < 5 else "click", secs=3)
        root.after(TICK_MS, self.tick)
        root.after(2000, self.keep_on_top)

    # ---------- данные для всех существ ----------
    def load_animations(self):
        a = load_animation_module()
        frames, anims = dict(a.FRAMES), dict(a.ANIMATIONS)
        for name in REQUIRED_ANIMS:
            if name not in anims:
                raise ValueError(f"В ANIMATIONS нет обязательной анимации «{name}»")
        for name, spec in anims.items():
            for f in spec["frames"]:
                if f.lstrip("~") not in frames:
                    raise ValueError(f"Анимация «{name}»: нет кадра «{f}»")
        hats = dict(getattr(a, "HATS", {}))
        for name, rows in list(frames.items()) + list(hats.items()):
            for ch in "".join(rows):
                if ch != "." and ch not in a.PALETTE:
                    raise ValueError(f"«{name}»: символа «{ch}» нет в PALETTE")
        self.palette, self.frames, self.anims, self.hats = a.PALETTE, frames, anims, hats
        self.phrases = getattr(a, "PHRASES", {})
        self.friend_colors = getattr(a, "FRIEND_COLORS", ["#4D96FF"])
        self.gw = max(len(row) for rows in frames.values() for row in rows)
        self.gh = max(len(rows) for rows in frames.values())
        self.frames_version += 1

    def current_hat(self):
        h = self.hat.get()
        if h == "none":
            return None
        if h != "auto":
            return h
        t = time.localtime()
        m, d = t.tm_mon, t.tm_mday
        if (m, d) in ((12, 31), (1, 1)):
            return "party"
        if (m == 12 and d >= 15) or (m == 1 and d <= 14):
            return "santa"
        if (m == 10 and d >= 24) or (m, d) == (11, 1):
            return "witch"
        return None

    def perch_enabled(self):
        return self.opt["perch"].get()

    def speed_factor(self):
        return 0.6 if self.settings["food"] < 20 else 1.0

    def all_critters(self):
        return [self] + self.friends

    # ---------- кадры Клода ----------
    def adjust_frame(self, frame):
        if self.state == "idle" and frame in EYE_FRAMES:
            return self.follow_cursor(frame)
        return frame

    def follow_cursor(self, frame):
        """Глаза смотрят на курсор, если он рядом."""
        mx, my = self.root.winfo_pointerxy()
        dx = mx - (self.x + self.w / 2)
        if math.hypot(dx, my - (self.y + self.h / 2)) > 600:
            return frame
        if abs(dx) < self.w * 0.35:
            return "base"
        return "look_left" if (dx < 0) != self.flip else "look_right"

    def idle_anim(self):
        st = self.settings
        return "sad" if st["mood"] < 30 or st["food"] < 15 else "idle"

    def resize(self):
        super().resize()
        self.settings["scale"] = self.scale.get()
        for f in getattr(self, "friends", []):
            f.resize()

    # ---------- речь и звук ----------
    def say(self, what, secs=3.5, force=False):
        """what — ключ из PHRASES или готовый текст."""
        if not (self.opt["talk"].get() or force) or (self.panel.visible and not force):
            return
        self.bubble_tip = None
        lines = self.phrases.get(what)
        text = random.choice(lines) if lines else what
        if text:
            self.bubble.show(text, self.clock + secs)
            if self.opt["voice"].get():
                self.voice_out.say(text)
                self.quiet_until = self.clock + 1 + len(text) * 0.08

    def sound(self, name):
        if self.opt["sounds"].get():
            sounds.play(name)
            self.quiet_until = max(self.quiet_until, self.clock + 1.0)

    def chatter(self):
        if self.clock >= self.next_water:
            self.next_water = self.clock + 45 * 60
            return self.say("water", secs=6)
        if self.clock < self.next_chatter or self.state not in ("idle", "walk"):
            return
        self.next_chatter = self.clock + random.uniform(120, 300)
        st, hour = self.settings, time.localtime().tm_hour
        if st["food"] < 25:
            self.say("hungry", secs=5)
        elif st["mood"] < 30:
            self.say("sad", secs=5)
        else:
            self.say("night" if hour < 5 else "bored", secs=4)

    # ---------- настроение и еда ----------
    def mood(self, delta):
        st = self.settings
        st["mood"] = max(0.0, min(100.0, st["mood"] + delta))

    def apply_offline_decay(self):
        last = self.settings["last_seen"]
        if last:
            away = max(0.0, time.time() - last) / 600  # по единице за 10 минут без Клода
            self.mood(-min(30, away))
            self.settings["food"] = max(0.0, self.settings["food"] - min(30, away))

    def feed(self):
        if self.busy():
            return
        if self.settings["food"] >= 90:
            return self.say("full", secs=3, force=True)
        self.settings["food"] = min(100.0, self.settings["food"] + 35)
        self.mood(5)
        self.set_state("oneshot", "eat")
        self.sound("eat")
        self.say("eat", secs=3, force=True)

    def status_line(self):
        st = self.settings
        s = f"Клод · настроение {int(st['mood'])}% · сытость {int(st['food'])}%"
        p = st["pomodoro"]
        if p:
            left = max(0, int((p["until"] - time.time()) / 60) + 1)
            s += f" · помодоро: {'работа' if p['phase'] == 'work' else 'перерыв'}, {left} мин"
        return s

    # ---------- поведение ----------
    def set_state(self, state, anim=None):
        if state == "purr":
            self.state = state
            self.play("purr")
        elif state in ("work", "ponder"):
            self.state = state
            self.play("think")
        elif state == "alert":
            self.state = state
            self.play("sparkle")
        elif state == "bye":
            self.state = state
            self.play("wave")
        else:
            super().set_state(state, anim)

    def pick_next(self):
        if self.state == "sleep":
            self.idle_since = self.clock
        if self.clock - self.idle_since > 120:  # давно скучает — засыпает
            return self.set_state("sleep")
        if not self.opt["auto"].get() or self.panel.visible:
            return self.set_state("idle")
        roll = random.random()
        if roll < 0.10 and self.hop_to_window():
            return
        if roll < 0.15 and self.perch:
            return self.drop_perch()
        if roll < 0.45:
            self.set_state("walk")
        elif roll < 0.58:
            self.set_state("idle")
        elif roll < 0.65:
            self.set_state("jump")
        elif roll < 0.70:
            self.set_state("sleep")
        else:
            extras = [n for n in self.anims if n not in BEHAVIOR_ANIMS]
            self.set_state("oneshot", random.choice(extras)) if extras else self.set_state("idle")

    def after_oneshot(self):
        self.after_claude_or_idle()

    def after_land(self):
        self.after_claude_or_idle()

    def after_claude_or_idle(self):
        if self.opt["claude_link"].get() and self.claude == "working":
            self.set_state("work")
        else:
            self.set_state("idle")

    def alert(self, text, secs=30, kind="other"):
        """Привлечь внимание: прыгает с искрами, в облачке — текст."""
        if self.hidden:
            self.show()
        if self.state in ("drag", "bye"):
            return
        self.alert_kind, self.alert_until = kind, self.clock + secs
        self.set_state("alert")
        self.say(text, secs=secs, force=True)
        self.sound("alert")

    # ---------- главный цикл ----------
    def tick(self):
        dt = TICK_MS / 1000
        self.clock += dt
        self.tick_n += 1
        if self.tray:
            try:
                self.tray.pump()
            except Exception:
                pass
        if self.clock >= self.next_claude_poll:
            self.next_claude_poll = self.clock + 0.7
            self.read_claude_state()
        if self.clock >= self.next_win_poll:
            self.next_win_poll = self.clock + 0.5
            self.watch_windows()
        if self.clock >= self.next_slow:
            self.next_slow = self.clock + 1.0
            self.slow_tick()
        result = self.asker.poll()
        if result:
            self.on_answer(*result)
        key = self.hotkeys.poll()
        if key:
            self.on_hotkey(key)
        if self.tick_n % 3 == 0:
            self.listen_music()

        self.bob = 0.0
        if self.state == "purr" and self.clock >= self.purr_until:
            self.after_claude_or_idle()
        elif self.state == "work" and self.claude != "working":
            self.set_state("idle")
        elif self.state == "ponder" and not self.asker.busy:
            self.after_claude_or_idle()
        elif self.state == "alert":
            self.bob = abs(math.sin(self.clock * 7)) * 6 * self.scale.get() / 4
            if self.clock >= self.alert_until or (self.alert_kind == "claude" and self.claude != "attention"):
                self.bubble.hide()
                self.after_claude_or_idle()

        was_perch = self.perch
        landed = self.step(dt)
        if landed:
            if self.y - self.fall_from > 150:
                self.say("land", secs=2)
                self.sound("land")
            if self.perch and self.perch != was_perch and random.random() < 0.3:
                self.say("perch", secs=2.5)
        if self.state not in ("idle", "sleep"):
            self.idle_since = self.clock
        if self.opt["auto"].get() and self.state != "bye":
            self.chatter()
        for f in self.friends:
            f.step(dt)

        if not self.hidden:
            self.render()
            for f in self.friends:
                f.render()
            self.place_overlays()
        self.root.after(TICK_MS, self.tick)

    def slow_tick(self):
        """Раз в секунду: окна, настроение, напоминания, помодоро, трей, сохранение."""
        st = self.settings
        try:
            self.windows = winsys.top_windows() if self.perch_enabled() else []
        except Exception:
            self.windows = []
        st["mood"] = max(0.0, st["mood"] - 1 / 240)
        st["food"] = max(0.0, st["food"] - 1 / 180)
        st["last_seen"] = time.time()
        now = time.time()
        due = [r for r in st["reminders"] if r["due"] <= now]
        if due:
            st["reminders"] = [r for r in st["reminders"] if r["due"] > now]
            self.alert("⏰ " + due[0]["text"], secs=60, kind="reminder")
        self.pomodoro_tick(now)
        if self.dnd_until and now >= self.dnd_until:
            self.dnd_until = None
            self.show()
        self.meet_friends()
        if self.tray:
            self.tray.set_tip(self.status_line())
        if int(self.clock) % 5 == 0:
            if not self.perch:
                st["x"] = int(self.x)
            st.save()

    def place_overlays(self):
        sc = self.scale.get()
        if self.bubble.visible:
            if self.clock >= self.bubble.until:
                self.bubble.hide()
            else:
                self.bubble.place(self.x + self.w / 2, self.y + 2 * sc)
        if self.panel.visible:
            self.panel.place()
        show_x = self.clock < self.hover_until and self.state != "bye"
        if show_x:
            self.close_win.geometry(f"20x20+{int(self.x + self.w - 2)}+{int(self.y + 2 * sc - 10)}")
            if not self.close_visible:
                self.close_win.deiconify()
                self.close_visible = True
        elif self.close_visible:
            self.close_win.withdraw()
            self.close_visible = False

    def apply_topmost(self):
        on = self.opt["topmost"].get()
        for w in [self.root, self.bubble.win, self.close_win, self.panel.win] + [f.win for f in self.friends]:
            w.attributes("-topmost", on)

    def keep_on_top(self):
        if self.opt["topmost"].get() and not self.hidden:
            self.apply_topmost()
            self.root.lift()
        self.root.after(2000, self.keep_on_top)

    # ---------- музыка ----------
    def listen_music(self):
        if not self.opt["music_dance"].get():
            self.music = False
            return
        loud = self.clock >= self.quiet_until and self.meter.peak() > 0.02
        self.peaks.append(loud)
        level = sum(self.peaks) / len(self.peaks)
        if not self.music and len(self.peaks) == self.peaks.maxlen and level >= 0.85:
            self.music = True
            if self.state in ("idle", "walk"):
                self.say("music", secs=2)
        elif self.music and level < 0.3:
            self.music = False

    # ---------- друзья ----------
    def add_friend(self, save=True):
        if len(self.friends) >= 4:
            return self.say("больше друзей не поместится!", secs=3, force=True)
        color = self.friend_colors[len(self.friends) % len(self.friend_colors)]
        self.friends.append(Friend(self, color))
        if save:
            self.settings["friends"] = len(self.friends)
            self.say("friend", secs=3)

    def remove_friends(self):
        for f in self.friends:
            f.win.destroy()
        self.friends = []
        self.settings["friends"] = 0

    def meet_friends(self):
        """Если друг рядом — машут друг другу."""
        if self.clock < self.next_meet or self.state not in ("idle", "walk"):
            return
        for f in self.friends:
            if f.state in ("idle", "walk") and abs(f.x - self.x) < 160 and abs(f.y - self.y) < 20:
                self.next_meet = self.clock + 60
                self.flip, f.flip = f.x < self.x, self.x < f.x
                self.set_state("oneshot", "wave")
                f.set_state("oneshot", random.choice(["wave", "dance"]))
                self.say("friend", secs=3)
                self.mood(3)
                return

    # ---------- помодоро и напоминания ----------
    def add_reminder(self, text, due):
        self.settings["reminders"] = self.settings["reminders"] + [{"text": text, "due": due}]
        when = time.strftime("%H:%M", time.localtime(due))
        self.say(f"напомню в {when}", secs=3, force=True)

    def remove_reminder(self, r):
        self.settings["reminders"] = [x for x in self.settings["reminders"] if x != r]

    def pomodoro_start(self):
        self.settings["pomodoro"] = {"phase": "work", "until": time.time() + POMO_WORK, "count": 0}
        self.say("work", secs=4, force=True)
        self.sound("done")

    def pomodoro_stop(self):
        self.settings["pomodoro"] = None
        self.say("помодоро выключен", secs=3, force=True)

    def pomodoro_tick(self, now):
        p = self.settings["pomodoro"]
        if not p or now < p["until"]:
            return
        p = dict(p)
        if p["phase"] == "work":
            p["count"] += 1
            p["phase"] = "break"
            p["until"] = now + (POMO_LONG if p["count"] % 4 == 0 else POMO_BREAK)
            self.mood(5)
            self.alert(random.choice(self.phrases.get("break", ["перерыв!"])), secs=20, kind="pomodoro")
        else:
            p["phase"] = "work"
            p["until"] = now + POMO_WORK
            self.alert(random.choice(self.phrases.get("work", ["за работу!"])), secs=15, kind="pomodoro")
        self.settings["pomodoro"] = p

    # ---------- спрятать / показать ----------
    def hide(self, minutes=None):
        self.say("hidden", secs=2, force=True)
        self.root.after(1200, self._withdraw_all)
        self.dnd_until = time.time() + minutes * 60 if minutes else None

    def _withdraw_all(self):
        self.hidden = True
        for w in [self.root, self.bubble.win, self.close_win, self.panel.win] + [f.win for f in self.friends]:
            w.withdraw()
        self.bubble.visible = self.panel.visible = self.close_visible = False

    def show(self):
        if not self.hidden:
            return
        self.hidden = False
        self.dnd_until = None
        self.root.deiconify()
        for f in self.friends:
            f.win.deiconify()
        self.drawn_key = None

    def toggle_hidden(self):
        self.show() if self.hidden else self.hide()

    # ---------- Claude Code ----------
    def read_claude_state(self, initial=False):
        """Хуки Claude Code пишут ~/.claude/pet-state.json — реагируем на изменения."""
        try:
            mtime = os.stat(CLAUDE_STATE).st_mtime
        except OSError:
            return
        if mtime == self.claude_mtime:
            if self.claude == "working" and time.time() - mtime > 15 * 60:
                self.claude = "idle"  # хук «готово» так и не пришёл
            return
        self.claude_mtime = mtime
        try:
            with open(CLAUDE_STATE, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        prev, state = self.claude, data.get("state", "idle")
        if time.time() - data.get("t", 0) > 15 * 60:
            state = "idle"
        self.claude = state
        if initial or not self.opt["claude_link"].get() or self.busy() or self.state == "alert":
            return
        if state == "working" and prev != "working":
            self.set_state("work")
            self.say("working", secs=2.5)
        elif state == "working" and self.state in ("idle", "walk", "sleep", "music"):
            self.set_state("work")
        elif state == "done":
            self.vx = 0.0
            self.set_state("jump", "happy")
            self.say("done", secs=5)
            self.sound("done")
            self.mood(1)
        elif state == "attention":
            msg = (data.get("message") or "").strip()
            if "waiting for your input" in msg.lower():
                return self.say("done", secs=5)  # просто ждёт следующий вопрос
            if len(msg) > 140:
                msg = msg[:137] + "..."
            self.alert(msg or random.choice(self.phrases.get("attention", ["эй!"])), kind="claude")

    # ---------- помощь по окнам ----------
    def watch_windows(self):
        """Запоминает активное окно (не наше) и как долго в нём сидят."""
        try:
            fg = winsys.foreground()
        except Exception:
            return
        if not fg or fg["pid"] == os.getpid() or not fg["title"]:
            return
        self.last_win = fg
        key = (fg["exe"], fg["title"])
        if key != self.win_key:
            self.win_key, self.win_since = key, self.clock
        self.maybe_tip(fg)

    def maybe_tip(self, fg):
        """Иногда сам подсказывает что-то по окну, в котором давно работают."""
        if not (self.opt["tips"].get() and self.opt["talk"].get()) or self.asker.busy:
            return
        if self.panel.visible or self.hidden or self.state not in ("idle", "walk"):
            return
        if self.clock < self.next_tip or self.clock - self.win_since < 25 or self.win_key == self.last_tip_key:
            return
        if helper.is_private(fg) or fg["exe"].lower() in ("explorer.exe", "lockapp.exe"):
            return
        self.last_tip_key = self.win_key
        self.next_tip = self.clock + 10 * 60
        prompt = (f"Пользователь уже какое-то время работает в окне «{fg['title']}» "
                  f"(программа {fg['exe']}). Дай ОДИН короткий полезный совет (до 20 слов) "
                  "по тому, чем он, судя по всему, занят: горячая клавиша, приём, напоминание. "
                  "Без вступлений. Если сказать нечего полезного — ответь ровно SKIP.")
        self.asker.start("tip", prompt, model="haiku")

    def on_answer(self, tag, ok, text, meta=None):
        if tag == "panel":
            self.panel.on_result(ok, text)
            if ok:
                self.mood(2)
                if self.opt["voice"].get():
                    self.voice_out.say(text)
            if not self.panel.visible:
                self.say("готово, ответ в окошке" if ok else "не получилось :(", secs=4, force=True)
        elif tag == "tip":
            if not ok:
                self.opt["tips"].set(False)  # не стучаться снова, пока не починят вход
                self.say(text, secs=10, force=True)
            elif "SKIP" not in text:
                self.say(text, secs=12)
                self.bubble_tip = text
        elif tag == "text":
            self.finish_text_action(ok, text, meta)

    def open_help(self, note=None, image=None):
        if self.state == "bye":
            return
        self.show()
        self.bubble.hide()
        if self.state not in ("drag", "jump", "fall", "ponder"):
            self.set_state("idle")
        self.panel.open(self.last_win, note, image)

    # ---------- горячие клавиши ----------
    def on_hotkey(self, name):
        if name == "help":
            self.watch_windows()
            self.open_help()
        elif name == "text":
            self.start_text_action()
        elif name == "snip":
            self.start_snip()
        elif name == "voice":
            self.watch_windows()
            self.open_help()
            self.panel.dictate()

    def start_snip(self):
        self.show()

        def done(bbox):
            if not bbox:
                return
            self.root.after(150, lambda: self.open_help(image=helper.capture_bbox(bbox)))
        Snipper(self.root, done)

    # ---------- действия с выделенным текстом ----------
    def start_text_action(self, waited=0):
        """Ждём, пока отпустят Ctrl+Alt, копируем выделение и показываем меню действий."""
        if waited == 0:
            fg = winsys.foreground()
            self.text_target = fg["hwnd"] if fg and fg["pid"] != os.getpid() else None
        if winsys.modifiers_down() and waited < 1500:
            return self.root.after(30, self.start_text_action, waited + 30)
        seq = winsys.clipboard_seq()
        winsys.press("ctrl", "c")
        self.root.after(250, self.show_text_menu, seq)

    def show_text_menu(self, seq):
        text = ""
        if winsys.clipboard_seq() != seq:
            try:
                text = self.root.clipboard_get().strip()
            except tk.TclError:
                text = ""
        if not text:
            self.show()
            return self.say("text_none", secs=3, force=True)
        m = tk.Menu(self.root, tearoff=0)
        m.add_command(label=f"«{text[:30]}{'…' if len(text) > 30 else ''}»", state="disabled")
        for label, task, replace in helper.TEXT_ACTIONS:
            m.add_command(label=label, command=lambda t=task, r=replace: self.run_text_action(text, t, r))
        m.add_command(label="Спросить своё…", command=lambda: self.open_help(
            "Выделенный текст у меня в буфере обмена — нажми «Из буфера» или напиши, что с ним сделать."))
        m.tk_popup(*self.root.winfo_pointerxy())

    def run_text_action(self, text, task, replace):
        if self.asker.busy:
            return self.say("подожди, я ещё думаю", secs=2, force=True)
        self.asker.start("text", f"{task}\n\nТекст:\n{text[:8000]}",
                         meta={"replace": replace, "hwnd": self.text_target})
        self.show()
        self.set_state("ponder")
        self.say("думаю...", secs=2, force=True)

    def finish_text_action(self, ok, text, meta):
        if not ok:
            return self.say(text, secs=8, force=True)
        if not meta.get("replace"):
            return self.open_help(text)
        result = text.strip().strip("«»\"'")
        self.root.clipboard_clear()
        self.root.clipboard_append(result)
        self.sound("done")
        hwnd = meta.get("hwnd")
        fg = winsys.foreground()
        ours = fg and fg["pid"] == os.getpid()
        if self.opt["replace_selection"].get() and hwnd and fg and (fg["hwnd"] == hwnd or ours):
            winsys.set_foreground(hwnd)

            def paste():
                if winsys.u32.GetForegroundWindow() == hwnd:
                    winsys.press("ctrl", "v")
                    self.say("готово! вставил", secs=3, force=True)
                else:
                    self.say("готово, текст в буфере — Ctrl+V", secs=4, force=True)
            return self.root.after(200, paste)
        self.say("готово, текст в буфере — Ctrl+V", secs=4, force=True)

    # ---------- мышь ----------
    def set_hover(self, inside):
        self.hover_until = float("inf") if inside else self.clock + 1.2

    def on_hover_motion(self, e):
        """Поводить мышкой туда-сюда над Клодом — погладить."""
        if self.busy():
            return
        x = e.x_root
        if self.pet_last is None:
            self.pet_last = (x, 0)
            return
        last_x, last_dir = self.pet_last
        if abs(x - last_x) < 3:
            return
        d = 1 if x > last_x else -1
        if d != last_dir and last_dir != 0:
            self.pet_moves.append(self.clock)
        self.pet_last = (x, d)
        self.pet_moves = [t for t in self.pet_moves if self.clock - t < 1.5]
        if len(self.pet_moves) >= 3:
            if self.state != "purr":
                self.set_state("purr")
                self.sound("purr")
            self.purr_until = self.clock + 1.5
            if self.clock - self.last_pet_line > 5:
                self.last_pet_line = self.clock
                self.mood(3)
                self.say("pet", secs=2)

    def on_drag_start(self):
        self.say("drag", secs=2)
        self.sound("drag")

    def on_click(self):
        if self.state == "alert":
            self.claude = "idle" if self.alert_kind == "claude" else self.claude
            self.bubble.hide()
            return self.set_state("idle")
        if self.state == "sleep":
            self.set_state("oneshot", "wave")
            return self.say("wake")
        if self.state in ("work", "ponder"):
            return self.say("working", secs=2)
        if self.state not in ("jump", "fall"):
            self.vx = 0.0
            self.set_state("jump", "happy")
            self.say("click", secs=2)
            self.sound("happy")
            self.mood(1)

    def make_close_button(self):
        self.close_win = overlay(self.root)
        c = tk.Canvas(self.close_win, width=20, height=20, bg=KEY, highlightthickness=0, bd=0, cursor="hand2")
        c.pack()
        c.create_oval(1, 1, 19, 19, fill="#1A1A1A", outline="#F5F0E8")
        c.create_line(6, 6, 14, 14, fill="#F5F0E8", width=2)
        c.create_line(14, 6, 6, 14, fill="#F5F0E8", width=2)
        c.bind("<Button-1>", lambda e: self.goodbye())
        c.bind("<Enter>", lambda e: self.set_hover(True))
        c.bind("<Leave>", lambda e: self.set_hover(False))
        self.close_visible = False

    # ---------- меню ----------
    def build_menu(self):
        r = self.root
        m = tk.Menu(r, tearoff=0)
        m.add_command(label=self.status_line(), state="disabled")
        m.add_separator()
        m.add_command(label="Помоги с этим окном…   Ctrl+Alt+C", command=self.open_help)
        m.add_command(label="Спросить про область экрана…   Ctrl+Alt+S", command=self.start_snip)
        m.add_command(label="Текст: выдели и нажми Ctrl+Alt+T", state="disabled")
        m.add_command(label="Спросить голосом   Ctrl+Alt+V", command=lambda: self.on_hotkey("voice"))
        m.add_separator()
        m.add_command(label="Напомнить…", command=lambda: ReminderDialog(self))
        if self.settings["pomodoro"]:
            m.add_command(label="Остановить помодоро", command=self.pomodoro_stop)
        else:
            m.add_command(label="Начать помодоро (25/5)", command=self.pomodoro_start)
        m.add_command(label="Покормить печенькой", command=self.feed)
        m.add_separator()

        anims = tk.Menu(m, tearoff=0)
        for name in self.anims:
            if name not in ("air", "crouch", "held"):
                anims.add_command(label=name, command=lambda n=name: self.menu_play(n))
        m.add_cascade(label="Анимации", menu=anims)
        hats = tk.Menu(m, tearoff=0)
        for key in ["auto", "none"] + list(self.hats):
            hats.add_radiobutton(label=HAT_NAMES.get(key, key), variable=self.hat, value=key)
        m.add_cascade(label="Шапка", menu=hats)
        sizes = tk.Menu(m, tearoff=0)
        for v in (2, 3, 4, 5, 6, 8, 10):
            sizes.add_radiobutton(label=f"{v}×", variable=self.scale, value=v, command=self.resize)
        m.add_cascade(label="Размер", menu=sizes)
        friends = tk.Menu(m, tearoff=0)
        friends.add_command(label="Позвать друга", command=self.add_friend)
        friends.add_command(label="Отпустить друзей", command=self.remove_friends,
                            state="normal" if self.friends else "disabled")
        m.add_cascade(label="Друзья", menu=friends)
        opts = tk.Menu(m, tearoff=0)
        for key, label in TOGGLES:
            opts.add_checkbutton(label=label, variable=self.opt[key])
        opts.add_checkbutton(label="Запускать вместе с Windows", variable=self.autostart,
                             command=self.toggle_autostart)
        opts.add_separator()
        opts.add_command(label="Перезагрузить анимации", command=self.reload)
        m.add_cascade(label="Настройки", menu=opts)
        m.add_separator()
        m.add_command(label="Показать" if self.hidden else "Спрятать в трей", command=self.toggle_hidden)
        m.add_command(label="Не мешать 1 час", command=lambda: self.hide(60))
        m.add_command(label="Закрыть", command=self.goodbye)
        return m

    def on_menu(self, e):
        self.build_menu().tk_popup(e.x_root, e.y_root)

    def tray_menu(self):
        self.build_menu().tk_popup(*self.root.winfo_pointerxy())

    def menu_play(self, name):
        if name in ("walk", "sleep", "idle", "purr"):
            self.purr_until = self.clock + 3
            self.set_state(name)
        elif name == "happy":
            self.set_state("jump", "happy")
        else:
            self.set_state("oneshot", name)

    def reload(self):
        try:
            self.load_animations()
        except Exception as ex:  # показать ошибку в кадрах, а не упасть
            messagebox.showerror("Ошибка в animations.py", str(ex))
            return
        self.resize()
        self.set_state("idle")

    def toggle_autostart(self):
        if self.autostart.get():
            if FROZEN:
                cmd = f'@start "" "{sys.executable}"\n'
            else:
                pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
                cmd = f'@start "" "{pyw}" "{os.path.abspath(__file__)}"\n'
            with open(STARTUP_BAT, "w", encoding="utf-8") as f:
                f.write(cmd)
        elif os.path.exists(STARTUP_BAT):
            os.remove(STARTUP_BAT)

    def goodbye(self):
        """Помахать на прощание и закрыться. Второй вызов закрывает сразу."""
        if self.state == "bye" or self.hidden:
            return self.quit()
        self.set_state("bye")
        self.say("bye", secs=2, force=True)
        self.sound("bye")
        self.root.after(1400, self.quit)

    def quit(self):
        st = self.settings
        if not self.perch:
            st["x"] = int(self.x)
        st["last_seen"] = time.time()
        st.save(force=True)
        self.hotkeys.stop()
        if self.tray:
            self.tray.close()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    # Только один Клод за раз
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "ClaudeDesktopPet")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        sys.exit(0)
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    try:
        Pet().run()
    finally:
        try:
            os.remove(PID_FILE)
        except OSError:
            pass
