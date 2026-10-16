# -*- coding: utf-8 -*-
"""Пиксельные писки (генерируются в ~/.claude-pet/sounds) и голос Windows."""
import math
import os
import random
import re
import struct
import wave
import winsound

from settings import DATA_DIR

SOUND_DIR = os.path.join(DATA_DIR, "sounds")
RATE = 22050

# Каждый звук — список нот: (частота_начала, частота_конца, длительность_сек, форма)
SOUNDS = {
    "click": [(700, 1100, 0.06, "square")],
    "happy": [(660, 660, 0.07, "square"), (990, 990, 0.09, "square")],
    "land":  [(220, 120, 0.07, "triangle")],
    "drag":  [(500, 900, 0.12, "triangle")],
    "purr":  [(110, 130, 0.12, "triangle"), (130, 110, 0.12, "triangle")],
    "eat":   [(0, 0, 0.05, "noise"), (0, 0, 0.0, "rest"), (0, 0, 0.05, "noise"), (0, 0, 0.05, "rest"),
              (0, 0, 0.05, "noise")],
    "alert": [(880, 880, 0.08, "square"), (0, 0, 0.05, "rest")] * 3,
    "done":  [(523, 523, 0.07, "square"), (659, 659, 0.07, "square"), (784, 784, 0.12, "square")],
    "bye":   [(784, 392, 0.25, "triangle")],
    "pop":   [(300, 600, 0.05, "square")],
}


def _sample(form, phase):
    if form == "square":
        return 1.0 if (phase % 1.0) < 0.5 else -1.0
    if form == "triangle":
        p = phase % 1.0
        return 4 * p - 1 if p < 0.5 else 3 - 4 * p
    if form == "noise":
        return random.uniform(-1, 1)
    return 0.0


def _render(notes, path):
    frames = bytearray()
    for f0, f1, dur, form in notes:
        n = int(RATE * dur)
        phase = 0.0
        for i in range(n):
            t = i / max(1, n - 1)
            freq = f0 + (f1 - f0) * t
            phase += freq / RATE
            env = min(1.0, i / 200, (n - i) / 400)  # без щелчков на краях
            v = _sample(form, phase) * env * 0.22
            frames += struct.pack("<h", int(v * 32767))
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(frames))


def ensure_sounds():
    os.makedirs(SOUND_DIR, exist_ok=True)
    for name, notes in SOUNDS.items():
        path = os.path.join(SOUND_DIR, name + ".wav")
        if not os.path.exists(path):
            _render(notes, path)


def play(name):
    path = os.path.join(SOUND_DIR, name + ".wav")
    if os.path.exists(path):
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)


class Voice:
    """Голос Windows (SAPI). Русский — Irina, если установлена."""

    def __init__(self):
        self.sp = None
        try:
            import win32com.client
            self.sp = win32com.client.Dispatch("SAPI.SpVoice")
            ru = self.sp.GetVoices("Language=419")
            if ru.Count:
                self.sp.Voice = ru.Item(0)
            self.sp.Rate = 1
        except Exception:
            self.sp = None

    def say(self, text):
        if not self.sp or not text:
            return
        clean = re.sub(r"[*_`#>\[\]()]+", " ", text)
        clean = re.sub(r"https?://\S+", "ссылка", clean)
        try:
            self.sp.Speak(clean[:600], 1 | 2)  # асинхронно, перебивая прошлую фразу
        except Exception:
            pass

    def stop(self):
        if self.sp:
            try:
                self.sp.Speak("", 1 | 2)
            except Exception:
                pass
