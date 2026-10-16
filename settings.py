# -*- coding: utf-8 -*-
"""Настройки и состояние Клода между запусками: ~/.claude-pet/settings.json."""
import json
import os

DATA_DIR = os.path.join(os.path.expanduser("~"), ".claude-pet")
PATH = os.path.join(DATA_DIR, "settings.json")

DEFAULTS = {
    "scale": 4,
    "x": None,                 # где стоял в прошлый раз
    "auto": True,              # гулять самому
    "talk": True,              # облачка с репликами
    "claude_link": True,       # реагировать на Claude Code
    "tips": True,              # подсказки по активному окну
    "topmost": True,
    "sounds": True,
    "voice": False,            # читать реплики вслух
    "music_dance": True,       # танцевать, когда играет звук
    "perch": True,             # залезать на окна
    "replace_selection": True, # сразу вставлять результат вместо выделенного текста
    "hat": "auto",
    "mood": 80,                # настроение 0..100
    "food": 80,                # сытость 0..100
    "last_seen": None,
    "reminders": [],           # [{"text": ..., "due": epoch}]
    "pomodoro": None,          # {"phase": "work"|"break", "until": epoch, "count": n}
    "friends": 0,
}


class Settings:
    def __init__(self):
        self.data = dict(DEFAULTS)
        self.dirty = False
        try:
            with open(PATH, encoding="utf-8") as f:
                saved = json.load(f)
            self.data.update({k: v for k, v in saved.items() if k in DEFAULTS})
        except (OSError, ValueError):
            pass

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        if self.data.get(key) != value:
            self.data[key] = value
            self.dirty = True

    def save(self, force=False):
        if not (self.dirty or force):
            return
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = PATH + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, PATH)
            self.dirty = False
        except OSError:
            pass
