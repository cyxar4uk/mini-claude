# -*- coding: utf-8 -*-
"""Вопросы к Claude: скриншоты окон и областей, действия с текстом.

Claude вызывается через CLI (`claude -p`) в пустой временной папке:
без пользовательских настроек и хуков, из инструментов доступен только Read,
чтобы посмотреть картинку. Ничего на компьютере он не меняет.
"""
import os
import queue
import shutil
import subprocess
import tempfile
import threading

import winsys

WORK_DIR = os.path.join(tempfile.gettempdir(), "claude-pet")
SHOT = os.path.join(WORK_DIR, "window.png")
SNIP = os.path.join(WORK_DIR, "snip.png")
MAX_SHOT_W = 1400
# Окна, заголовки которых Клод не отправляет никуда — даже для подсказок
PRIVATE_WORDS = ("password", "пароль", "bank", "банк", "keepass", "1password", "bitwarden",
                 "private", "инкогнито", "incognito", "сбер", "тинькофф", "т-банк")

SYSTEM = (
    "Ты — Клод, маленький пиксельный краб-помощник, который живёт на рабочем столе "
    "пользователя Windows. Ты видишь, какое окно сейчас открыто (заголовок, программа, "
    "иногда скриншот), и помогаешь с тем, что там происходит. Отвечай по-русски, коротко "
    "и по делу — обычно до 120 слов, простым текстом, без markdown-заголовков и таблиц. "
    "Если видишь ошибку — объясни причину и как исправить. Ты ничего не выполняешь на "
    "компьютере и не меняешь файлы — только советуешь."
)

_ONLY_TEXT = " Верни ТОЛЬКО готовый текст — без пояснений, кавычек и вступлений."
# Действия с выделенным текстом: (подпись, задание, заменяет ли текст)
TEXT_ACTIONS = [
    ("Перевести", "Переведи текст: если он на русском — на английский, иначе на русский. "
                  "Сохрани смысл, тон и форматирование." + _ONLY_TEXT, True),
    ("Исправить ошибки", "Исправь орфографию, пунктуацию и грамматику, ничего больше не меняя."
     + _ONLY_TEXT, True),
    ("Сделать вежливее", "Перепиши текст вежливее и дружелюбнее, сохранив смысл и язык." + _ONLY_TEXT, True),
    ("Сделать короче", "Сократи текст примерно вдвое, сохранив главное и язык." + _ONLY_TEXT, True),
    ("Объяснить", "Объясни простыми словами, что значит этот текст и что с ним можно сделать.", False),
]

foreground = winsys.foreground


def is_private(win):
    text = f"{win.get('title', '')} {win.get('exe', '')}".lower()
    return any(w in text for w in PRIVATE_WORDS)


def _save(img, path):
    os.makedirs(WORK_DIR, exist_ok=True)
    if img.width > MAX_SHOT_W:
        img = img.resize((MAX_SHOT_W, int(img.height * MAX_SHOT_W / img.width)))
    img.save(path)
    return path


def capture_bbox(bbox, path=SNIP):
    """Скриншот прямоугольника экрана (l, t, r, b)."""
    try:
        from PIL import ImageGrab
    except ImportError:
        return None
    l, t, r, b = bbox
    if r - l < 8 or b - t < 8:
        return None
    return _save(ImageGrab.grab(bbox=bbox, all_screens=True), path)


def capture(hwnd):
    """Скриншот окна. Возвращает путь или None."""
    if not hwnd or winsys.u32.IsIconic(hwnd):
        return None
    l, t, r, b = winsys.window_rect(hwnd)
    if r - l < 50 or b - t < 50:
        return None
    return capture_bbox((l, t, r, b), SHOT)


def claude_exe():
    return shutil.which("claude") or "claude"


def ask(prompt, image=None, model=None, timeout=180, image_note="Скриншот этого окна"):
    """Один вопрос к Claude. Возвращает (ok, текст)."""
    os.makedirs(WORK_DIR, exist_ok=True)
    if image:
        prompt = f"{image_note}: {image}\nСначала посмотри его через Read.\n\n" + prompt
    cmd = [claude_exe(), "-p", "--output-format", "text",
           "--tools", "Read" if image else "",
           "--setting-sources", "project", "--strict-mcp-config",
           "--no-session-persistence", "--append-system-prompt", SYSTEM]
    if model:
        cmd += ["--model", model]
    env = dict(os.environ, CLAUDE_PET_INTERNAL="1")
    try:
        p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
                           cwd=WORK_DIR, env=env, timeout=timeout,
                           creationflags=0x08000000)  # CREATE_NO_WINDOW
    except FileNotFoundError:
        return False, "Не нашёл Claude Code (команду claude). Установи его, и я смогу помогать."
    except subprocess.TimeoutExpired:
        return False, "Claude слишком долго думал, попробуй ещё раз."
    out = (p.stdout or "").strip()
    err = (p.stderr or "").strip()
    if p.returncode != 0:
        both = f"{out}\n{err}".lower()
        if "authenticat" in both or "login" in both:
            return False, ("Мне нужен вход в Claude: открой терминал, набери claude "
                           "и выполни /login. Потом спроси меня ещё раз.")
        return False, "Не получилось спросить Claude: " + (err or out or "неизвестная ошибка")[:200]
    return True, out or "(пустой ответ)"


class Asker:
    """Запускает вопросы в фоне; результаты забираются через poll() из цикла tkinter."""

    def __init__(self):
        self.results = queue.Queue()
        self.busy = False

    def start(self, tag, prompt, image=None, model=None, meta=None, image_note="Скриншот этого окна"):
        if self.busy:
            return False
        self.busy = True

        def work():
            try:
                ok, text = ask(prompt, image, model, image_note=image_note)
            except Exception as ex:  # не уронить питомца
                ok, text = False, f"Ошибка: {ex}"
            self.results.put((tag, ok, text, meta))
            self.busy = False

        threading.Thread(target=work, daemon=True).start()
        return True

    def poll(self):
        try:
            return self.results.get_nowait()
        except queue.Empty:
            return None
