# -*- coding: utf-8 -*-
"""Окошки Клода: облачко, панель помощи, выделение области экрана, напоминания."""
import time
import tkinter as tk
import tkinter.font as tkfont

import helper
import winsys

KEY = "#FF00FE"          # цвет, который Windows делает прозрачным
BG, PAPER, INK, MUTED, ORANGE = "#F5F0E8", "#FFFDF8", "#1A1A1A", "#7A6F66", "#D97757"


def overlay(root):
    """Окно без рамки, поверх всех, с прозрачным фоном."""
    w = tk.Toplevel(root)
    w.overrideredirect(True)
    w.configure(bg=KEY)
    w.attributes("-transparentcolor", KEY)
    w.attributes("-topmost", True)
    w.withdraw()
    return w


def flat_button(parent, text, command, primary=False, **kw):
    return tk.Button(parent, text=text, command=command, relief="flat", cursor="hand2",
                     bg=ORANGE if primary else "#E8DFD3", fg="white" if primary else INK,
                     activebackground="#C4654A" if primary else "#DCCFBF",
                     font=("Segoe UI", 9, "bold" if primary else "normal"), padx=8, **kw)


class Bubble:
    """Облачко с репликой над Клодом."""
    PAD, TAIL, WRAP = 8, 8, 230

    def __init__(self, root):
        self.win = overlay(root)
        self.c = tk.Canvas(self.win, bg=KEY, highlightthickness=0, bd=0)
        self.c.pack()
        self.font = tkfont.Font(family="Segoe UI", size=10)
        self.until = 0.0
        self.visible = False
        self.size = (0, 0)
        self.pos = None
        self.text = ""

    def show(self, text, until):
        c, p = self.c, self.PAD
        self.text = text
        c.delete("all")
        t = c.create_text(p + 2, p, text=text, anchor="nw", width=self.WRAP,
                          font=self.font, fill=INK)
        _, _, x1, y1 = c.bbox(t)
        w, h = x1 + p + 2, y1 + p
        r, fill = 8, PAPER
        c.create_polygon([1 + r, 1, w - r, 1, w, 1, w, 1 + r, w, h - r, w, h, w - r, h,
                          1 + r, h, 1, h, 1, h - r, 1, 1 + r, 1, 1],
                         smooth=True, fill=fill, outline=INK)
        m = w // 2
        c.create_polygon(m - 6, h - 1, m + 6, h - 1, m, h + self.TAIL, fill=fill, outline=INK)
        c.create_line(m - 5, h - 1, m + 6, h - 1, fill=fill, width=2)
        c.tag_raise(t)
        self.size = (w + 2, h + self.TAIL + 2)
        c.config(width=self.size[0], height=self.size[1])
        self.until = until
        self.pos = None
        if not self.visible:
            self.win.deiconify()
            self.visible = True

    def place(self, cx, bottom):
        l, t, r, _ = winsys.work_area()
        w, h = self.size
        x = int(max(l, min(cx - w / 2, r - w)))
        y = int(max(t, bottom - h))
        if (x, y) != self.pos:
            self.pos = (x, y)
            self.win.geometry(f"{w}x{h}+{x}+{y}")

    def hide(self):
        if self.visible:
            self.win.withdraw()
            self.visible = False


class HelpPanel:
    """Окошко «чем помочь?»: видит активное окно (или выделенную область) и спрашивает Claude."""
    W = 380
    QUICK = [
        ("Что тут?", "Что сейчас происходит на картинке/в окне? Чем ты можешь помочь?", False),
        ("Найди проблему", "Есть ли тут ошибка или проблема? Если да — в чём причина и как исправить?", False),
        ("Из буфера", "Вот текст из буфера обмена. Объясни его и подскажи, что с ним сделать.", True),
    ]

    def __init__(self, pet):
        self.pet = pet
        self.target = None
        self.image = None          # выделенная область экрана вместо окна
        self.history = []          # [(вопрос, ответ)] для продолжения разговора
        self.pending_q = None
        self.last_answer = ""
        self.visible = False
        self.pos = None
        self.win = w = tk.Toplevel(pet.root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.withdraw()
        outer = tk.Frame(w, bg=INK, padx=1, pady=1)
        outer.pack(fill="both", expand=True)
        body = tk.Frame(outer, bg=BG, padx=10, pady=8)
        body.pack(fill="both", expand=True)

        head = tk.Frame(body, bg=BG)
        head.pack(fill="x")
        self.ctx = tk.Label(head, bg=BG, fg=MUTED, font=("Segoe UI", 8),
                            anchor="w", justify="left", wraplength=self.W - 50)
        self.ctx.pack(side="left", fill="x", expand=True)
        x = tk.Label(head, text="×", bg=BG, fg=INK, font=("Segoe UI", 12), cursor="hand2")
        x.pack(side="right")
        x.bind("<Button-1>", lambda e: self.hide())

        box = tk.Frame(body, bg=BG)
        box.pack(fill="both", expand=True, pady=(4, 6))
        self.text = tk.Text(box, width=46, height=12, wrap="word", bg=PAPER, fg=INK,
                            relief="flat", font=("Segoe UI", 10), padx=6, pady=4,
                            state="disabled", cursor="arrow")
        sb = tk.Scrollbar(box, command=self.text.yview)
        self.text.config(yscrollcommand=sb.set)
        self.text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.text.tag_config("me", foreground=ORANGE, font=("Segoe UI", 10, "bold"))
        self.text.tag_config("err", foreground="#B3261E")
        self.text.tag_config("muted", foreground=MUTED)

        quick = tk.Frame(body, bg=BG)
        quick.pack(fill="x")
        for label, q, clip in self.QUICK:
            flat_button(quick, label, lambda q=q, clip=clip: self.ask(q, clip)).pack(side="left", padx=(0, 6))
        flat_button(quick, "Копировать", self.copy_answer).pack(side="right")

        self.shot = tk.BooleanVar(value=True)
        self.shot_box = tk.Checkbutton(body, text="Показывать Claude скриншот окна", variable=self.shot,
                                       bg=BG, activebackground=BG, font=("Segoe UI", 8), fg=MUTED)
        self.shot_box.pack(anchor="w", pady=(4, 2))

        row = tk.Frame(body, bg=BG)
        row.pack(fill="x")
        self.entry = tk.Entry(row, font=("Segoe UI", 10), relief="flat", bg=PAPER)
        self.entry.pack(side="left", fill="x", expand=True, ipady=4)
        self.entry.bind("<Return>", lambda e: self.ask_typed())
        self.entry.bind("<Escape>", lambda e: self.hide())
        flat_button(row, "Голосом", self.dictate).pack(side="left", padx=(6, 0))
        flat_button(row, "→", self.ask_typed, primary=True, width=3).pack(side="left", padx=(6, 0))

    # --- показ ---
    def open(self, target, note=None, image=None):
        new_ctx = image or self.image or self.target is None or not target \
            or target["hwnd"] != self.target["hwnd"]
        if new_ctx:
            self.history = []
            self.clear()
        self.target, self.image = target, image
        if image:
            self.ctx.config(text="Вижу: выделенную область экрана")
            self.shot_box.config(text="Показывать Claude выделенную область")
        elif target and target["title"]:
            self.ctx.config(text=f"Вижу: {target['title']} — {target['exe']}")
            self.shot_box.config(text="Показывать Claude скриншот окна")
        else:
            self.ctx.config(text="Не вижу активного окна — спрашивай о чём угодно")
        if note:
            self.write("Клод: ", "me")
            self.write(note + "\n\n")
        elif not self.text.get("1.0", "end").strip():
            self.write("Чем помочь? Выбери кнопку или напиши вопрос.\n\n", "muted")
        self.win.deiconify()
        self.visible = True
        self.pos = None
        self.place()
        self.win.after(50, self.entry.focus_force)

    def hide(self):
        self.win.withdraw()
        self.visible = False

    def place(self):
        p = self.pet
        self.win.update_idletasks()
        w, h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        l, t, r, _ = winsys.work_area()
        x = int(max(l, min(p.x + p.w / 2 - w / 2, r - w)))
        y = int(max(t, p.y + 2 * p.scale.get() - h - 6))
        if (x, y) != self.pos:
            self.pos = (x, y)
            self.win.geometry(f"+{x}+{y}")

    def clear(self):
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.config(state="disabled")

    def write(self, s, tag=None):
        self.text.config(state="normal")
        self.text.insert("end", s, tag)
        self.text.config(state="disabled")
        self.text.see("end")

    def copy_answer(self):
        if self.last_answer:
            self.pet.root.clipboard_clear()
            self.pet.root.clipboard_append(self.last_answer)
            self.pet.say("скопировал!", secs=2, force=True)
            self.pet.sound("pop")

    def dictate(self):
        """Голосовой ввод Windows (Win+H) прямо в поле вопроса."""
        self.entry.focus_force()
        self.win.after(150, lambda: winsys.press("win", "h"))

    # --- вопросы ---
    def ask_typed(self):
        q = self.entry.get().strip()
        if q:
            self.entry.delete(0, "end")
            self.ask(q)

    def ask(self, q, clipboard=False):
        p = self.pet
        if p.asker.busy:
            return self.write("Подожди, я ещё думаю над прошлым вопросом.\n\n", "muted")
        clip = ""
        if clipboard:
            try:
                clip = p.root.clipboard_get()
            except tk.TclError:
                return self.write("В буфере обмена нет текста.\n\n", "muted")
        self.write("Ты: ", "me")
        self.write(q + "\n")
        self.write("думаю...\n", "muted")
        self.pending_q = q

        t = self.target or {}
        parts = []
        if t.get("title") and not self.image:
            parts.append(f"Активное окно: «{t['title']}», программа {t['exe']}.")
        for old_q, old_a in self.history[-3:]:
            parts.append(f"Раньше пользователь спросил: {old_q}\nТы ответил: {old_a}")
        if clip:
            parts.append("Текст из буфера обмена:\n" + clip[:6000])
        parts.append("Вопрос: " + q)
        prompt = "\n\n".join(parts)

        if self.image:
            note = "Пользователь выделил этот фрагмент экрана"
            return self.start(prompt, self.image if self.shot.get() else None, note)
        want_shot = self.shot.get() and t.get("hwnd") and not helper.is_private(t)
        if not want_shot:
            return self.start(prompt, None)
        # Спрятать свои окна, чтобы не попасть на скриншот
        self.win.withdraw()
        p.bubble.hide()

        def grab():
            try:
                image = helper.capture(t["hwnd"])
            except Exception:
                image = None
            self.win.deiconify()
            self.start(prompt, image)
        self.win.after(150, grab)

    def start(self, prompt, image, note="Скриншот этого окна"):
        self.pet.asker.start("panel", prompt, image, image_note=note)
        self.pet.set_state("ponder")

    def on_result(self, ok, text):
        self.text.config(state="normal")
        last = self.text.search("думаю...", "end", backwards=True)
        if last:
            self.text.delete(last, f"{last} lineend +1c")
        self.text.config(state="disabled")
        self.write("Клод: ", "me")
        self.write(text + "\n\n", None if ok else "err")
        if ok:
            self.last_answer = text
            if self.pending_q:
                self.history.append((self.pending_q, text[:1500]))
        self.pending_q = None


class Snipper:
    """Затемняет экран; пользователь обводит мышкой область. callback((l, t, r, b)) или None."""

    def __init__(self, root, callback):
        self.callback = callback
        vx, vy, vw, vh = winsys.virtual_screen()
        self.origin = (vx, vy)
        self.w = w = tk.Toplevel(root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.attributes("-alpha", 0.3)
        w.geometry(f"{vw}x{vh}+{vx}+{vy}")
        self.c = tk.Canvas(w, bg="black", highlightthickness=0, cursor="crosshair")
        self.c.pack(fill="both", expand=True)
        self.c.create_text(vw // 2 - vx, 60, text="Обведи область мышкой · Esc — отмена",
                           fill="white", font=("Segoe UI", 16))
        self.start = None
        self.rect = None
        self.c.bind("<ButtonPress-1>", self.on_press)
        self.c.bind("<B1-Motion>", self.on_move)
        self.c.bind("<ButtonRelease-1>", self.on_release)
        w.bind("<Escape>", lambda e: self.finish(None))
        w.after(50, w.focus_force)

    def on_press(self, e):
        self.start = (e.x, e.y)
        self.rect = self.c.create_rectangle(e.x, e.y, e.x, e.y, outline=ORANGE, width=3)

    def on_move(self, e):
        if self.rect:
            self.c.coords(self.rect, *self.start, e.x, e.y)

    def on_release(self, e):
        if not self.start:
            return self.finish(None)
        (x0, y0), (x1, y1) = self.start, (e.x, e.y)
        ox, oy = self.origin
        bbox = (min(x0, x1) + ox, min(y0, y1) + oy, max(x0, x1) + ox, max(y0, y1) + oy)
        self.finish(bbox if bbox[2] - bbox[0] > 8 and bbox[3] - bbox[1] > 8 else None)

    def finish(self, bbox):
        self.w.destroy()
        self.callback(bbox)


class ReminderDialog:
    """«Напомни мне…»: текст + через сколько минут или во сколько."""

    def __init__(self, pet):
        self.pet = pet
        self.w = w = tk.Toplevel(pet.root)
        w.title("Напоминание — Клод")
        w.configure(bg=BG, padx=14, pady=12)
        w.attributes("-topmost", True)
        w.resizable(False, False)
        tk.Label(w, text="О чём напомнить?", bg=BG, fg=INK, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.text = tk.Entry(w, font=("Segoe UI", 10), relief="flat", bg=PAPER, width=38)
        self.text.pack(fill="x", ipady=4, pady=(4, 10))
        tk.Label(w, text="Через сколько минут:", bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w")
        row = tk.Frame(w, bg=BG)
        row.pack(fill="x", pady=(4, 8))
        for m in (5, 10, 15, 30, 60):
            flat_button(row, str(m), lambda m=m: self.add_in(m)).pack(side="left", padx=(0, 6))
        self.minutes = tk.Entry(row, font=("Segoe UI", 10), relief="flat", bg=PAPER, width=5)
        self.minutes.pack(side="left", ipady=3)
        flat_button(row, "мин", self.add_custom).pack(side="left", padx=(4, 0))
        row2 = tk.Frame(w, bg=BG)
        row2.pack(fill="x", pady=(0, 8))
        tk.Label(row2, text="или во сколько (ЧЧ:ММ):", bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(side="left")
        self.at = tk.Entry(row2, font=("Segoe UI", 10), relief="flat", bg=PAPER, width=7)
        self.at.pack(side="left", padx=6, ipady=3)
        flat_button(row2, "Поставить", self.add_at, primary=True).pack(side="left")
        self.err = tk.Label(w, text="", bg=BG, fg="#B3261E", font=("Segoe UI", 9))
        self.err.pack(anchor="w")
        tk.Label(w, text="Уже стоят:", bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(6, 0))
        self.list = tk.Frame(w, bg=BG)
        self.list.pack(fill="x")
        self.refresh()
        self.text.focus_force()

    def _add(self, due):
        text = self.text.get().strip() or "ты просил напомнить!"
        self.pet.add_reminder(text, due)
        self.text.delete(0, "end")
        self.err.config(text="")
        self.refresh()

    def add_in(self, minutes):
        self._add(time.time() + minutes * 60)

    def add_custom(self):
        try:
            m = float(self.minutes.get().replace(",", "."))
            assert m > 0
        except (ValueError, AssertionError):
            return self.err.config(text="Минуты — это число, например 25")
        self.add_in(m)

    def add_at(self):
        try:
            h, m = (int(x) for x in self.at.get().strip().split(":"))
            now = time.localtime()
            due = time.mktime((now.tm_year, now.tm_mon, now.tm_mday, h, m, 0, 0, 0, -1))
            if due <= time.time():
                due += 24 * 3600
        except (ValueError, OverflowError):
            return self.err.config(text="Время в виде 14:30")
        self._add(due)

    def refresh(self):
        for child in self.list.winfo_children():
            child.destroy()
        items = self.pet.settings["reminders"]
        if not items:
            tk.Label(self.list, text="ничего", bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w")
        for i, r in enumerate(sorted(items, key=lambda r: r["due"])):
            row = tk.Frame(self.list, bg=BG)
            row.pack(fill="x")
            when = time.strftime("%H:%M", time.localtime(r["due"]))
            tk.Label(row, text=f"{when} — {r['text']}", bg=BG, fg=INK, font=("Segoe UI", 9),
                     anchor="w").pack(side="left", fill="x", expand=True)
            x = tk.Label(row, text="×", bg=BG, fg=MUTED, cursor="hand2", font=("Segoe UI", 11))
            x.pack(side="right")
            x.bind("<Button-1>", lambda e, r=r: (self.pet.remove_reminder(r), self.refresh()))
