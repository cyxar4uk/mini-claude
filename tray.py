# -*- coding: utf-8 -*-
"""Значок Клода в трее (у часов). Сообщения окна обрабатываются через pump() из цикла tkinter."""
import os

from settings import DATA_DIR

ICON_PATH = os.path.join(DATA_DIR, "icon.ico")
WM_TRAY = 0x0400 + 20  # WM_USER + 20


def make_icon(rows, palette, path=ICON_PATH):
    """Рисует .ico из кадра (того же пиксель-арта)."""
    from PIL import Image
    pts = [(c, r) for r, row in enumerate(rows) for c, ch in enumerate(row) if ch != "."]
    l = min(c for c, _ in pts); r = max(c for c, _ in pts)
    t = min(r_ for _, r_ in pts); b = max(r_ for _, r_ in pts)
    w, h = r - l + 1, b - t + 1
    side = max(w, h) + 2
    img = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    ox, oy = (side - w) // 2, (side - h) // 2
    for c, r_ in pts:
        col = palette[rows[r_][c]].lstrip("#")
        img.putpixel((c - l + ox, r_ - t + oy), tuple(int(col[i:i + 2], 16) for i in (0, 2, 4)) + (255,))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    big = img.resize((256, 256), Image.NEAREST)
    big.save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (256, 256)])
    return path


class Tray:
    def __init__(self, tip, on_left, on_right, icon_path=ICON_PATH):
        import win32api
        import win32con
        import win32gui
        self.g, self.con = win32gui, win32con
        self.on_left, self.on_right = on_left, on_right
        hinst = win32api.GetModuleHandle(None)
        wc = win32gui.WNDCLASS()
        wc.hInstance = hinst
        wc.lpszClassName = "ClaudePetTray"
        wc.lpfnWndProc = {WM_TRAY: self._on_tray}
        try:
            win32gui.RegisterClass(wc)
        except win32gui.error:
            pass  # уже зарегистрирован
        self.hwnd = win32gui.CreateWindow("ClaudePetTray", "ClaudePetTray", 0, 0, 0, 0, 0,
                                          0, 0, hinst, None)
        self.hicon = win32gui.LoadImage(hinst, icon_path, win32con.IMAGE_ICON, 0, 0,
                                        win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE)
        self.tip = tip
        win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, self._nid(tip))

    def _nid(self, tip):
        flags = self.g.NIF_ICON | self.g.NIF_MESSAGE | self.g.NIF_TIP
        return (self.hwnd, 0, flags, WM_TRAY, self.hicon, tip[:127])

    def _on_tray(self, hwnd, msg, wparam, lparam):
        if lparam == self.con.WM_LBUTTONUP:
            self.on_left()
        elif lparam == self.con.WM_RBUTTONUP:
            self.on_right()
        return 0

    def set_tip(self, tip):
        if tip != self.tip:
            self.tip = tip
            try:
                self.g.Shell_NotifyIcon(self.g.NIM_MODIFY, self._nid(tip))
            except self.g.error:
                pass

    def pump(self):
        self.g.PumpWaitingMessages()

    def close(self):
        try:
            self.g.Shell_NotifyIcon(self.g.NIM_DELETE, (self.hwnd, 0))
            self.g.DestroyWindow(self.hwnd)
        except self.g.error:
            pass
