# -*- coding: utf-8 -*-
"""Всё, что Клоду нужно от Windows: окна, горячие клавиши, нажатия, громкость звука."""
import ctypes
import os
import queue
import threading
from ctypes import POINTER, WINFUNCTYPE, byref, c_float, c_int, c_ulong, c_ushort, c_ubyte, c_void_p
from ctypes import wintypes as wt

u32 = ctypes.windll.user32
k32 = ctypes.windll.kernel32
dwm = ctypes.windll.dwmapi
ole32 = ctypes.windll.ole32

for name, args in {
    "IsWindowVisible": [wt.HWND], "IsIconic": [wt.HWND], "IsZoomed": [wt.HWND], "IsWindow": [wt.HWND],
    "GetWindowLongW": [wt.HWND, c_int], "GetWindowTextLengthW": [wt.HWND],
    "GetWindowTextW": [wt.HWND, wt.LPWSTR, c_int],
    "GetWindowThreadProcessId": [wt.HWND, POINTER(wt.DWORD)],
    "GetWindowRect": [wt.HWND, POINTER(wt.RECT)], "GetAncestor": [wt.HWND, wt.UINT],
    "SetForegroundWindow": [wt.HWND], "WindowFromPoint": [wt.POINT],
}.items():
    getattr(u32, name).argtypes = args
u32.GetForegroundWindow.restype = wt.HWND
u32.WindowFromPoint.restype = wt.HWND
u32.GetAncestor.restype = wt.HWND
dwm.DwmGetWindowAttribute.argtypes = [wt.HWND, wt.DWORD, c_void_p, wt.DWORD]

OWN_PID = os.getpid()


# ---------- экран и окна ----------
def work_area():
    """Прямоугольник основного экрана без панели задач."""
    r = wt.RECT()
    u32.SystemParametersInfoW(0x0030, 0, byref(r), 0)  # SPI_GETWORKAREA
    return r.left, r.top, r.right, r.bottom


def virtual_screen():
    """Все мониторы вместе: (x, y, ширина, высота)."""
    return tuple(u32.GetSystemMetrics(i) for i in (76, 77, 78, 79))


def window_info(hwnd):
    """(заголовок, имя exe, pid) окна."""
    n = u32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    u32.GetWindowTextW(hwnd, buf, n + 1)
    pid = wt.DWORD()
    u32.GetWindowThreadProcessId(hwnd, byref(pid))
    exe = ""
    h = k32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if h:
        size = wt.DWORD(1024)
        path = ctypes.create_unicode_buffer(1024)
        if k32.QueryFullProcessImageNameW(h, 0, path, byref(size)):
            exe = os.path.basename(path.value)
        k32.CloseHandle(h)
    return buf.value, exe, pid.value


def foreground():
    hwnd = u32.GetForegroundWindow()
    if not hwnd:
        return None
    title, exe, pid = window_info(hwnd)
    return {"hwnd": hwnd, "title": title, "exe": exe, "pid": pid}


def window_rect(hwnd):
    r = wt.RECT()
    # Точные границы без невидимой рамки (DWMWA_EXTENDED_FRAME_BOUNDS)
    if dwm.DwmGetWindowAttribute(hwnd, 9, byref(r), ctypes.sizeof(r)) != 0:
        u32.GetWindowRect(hwnd, byref(r))
    return r.left, r.top, r.right, r.bottom


def _cloaked(hwnd):
    v = c_int(0)
    dwm.DwmGetWindowAttribute(hwnd, 14, byref(v), 4)  # DWMWA_CLOAKED: окно на другом рабочем столе
    return v.value != 0


def perchable(hwnd):
    """На это окно можно залезть: видно, не свёрнуто и не развёрнуто на весь экран."""
    return bool(hwnd) and u32.IsWindow(hwnd) and u32.IsWindowVisible(hwnd) \
        and not u32.IsIconic(hwnd) and not u32.IsZoomed(hwnd) and not _cloaked(hwnd)


_ENUM = WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def top_windows():
    """Обычные окна других программ сверху вниз: [(hwnd, (l, t, r, b))]."""
    out = []

    def cb(hwnd, _):
        if not perchable(hwnd) or u32.GetWindowLongW(hwnd, -20) & 0x80:  # WS_EX_TOOLWINDOW
            return True
        if not u32.GetWindowTextLengthW(hwnd):
            return True
        pid = wt.DWORD()
        u32.GetWindowThreadProcessId(hwnd, byref(pid))
        if pid.value == OWN_PID:
            return True
        rect = window_rect(hwnd)
        if rect[2] - rect[0] >= 200 and rect[3] - rect[1] >= 120:
            out.append((hwnd, rect))
        return True

    u32.EnumWindows(_ENUM(cb), 0)
    return out


def edge_visible(hwnd, x, y):
    """Точка (x, y) на окне hwnd не закрыта другими окнами."""
    h = u32.WindowFromPoint(wt.POINT(int(x), int(y)))
    return bool(h) and u32.GetAncestor(h, 2) == hwnd  # GA_ROOT


def set_foreground(hwnd):
    return bool(u32.SetForegroundWindow(hwnd))


# ---------- клавиатура и буфер обмена ----------
VK = {"ctrl": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B, "c": 0x43, "v": 0x56, "h": 0x48}


def press(*keys):
    """Нажать сочетание, например press("ctrl", "c")."""
    codes = [VK[k] for k in keys]
    for c in codes:
        u32.keybd_event(c, 0, 0, 0)
    for c in reversed(codes):
        u32.keybd_event(c, 0, 2, 0)  # KEYEVENTF_KEYUP


def modifiers_down():
    return any(u32.GetAsyncKeyState(vk) & 0x8000 for vk in (0x10, 0x11, 0x12, 0x5B, 0x5C))


def clipboard_seq():
    return u32.GetClipboardSequenceNumber()


# ---------- глобальные горячие клавиши ----------
MOD = {"alt": 1, "ctrl": 2, "shift": 4, "win": 8}


class Hotkeys:
    """RegisterHotKey в отдельном потоке; нажатия забираются через poll()."""

    def __init__(self, bindings):
        """bindings: {имя: "ctrl+alt+c"}."""
        self.q = queue.Queue()
        self.failed = []
        self.tid = None
        self.names = {}
        self._bindings = {}
        for i, (name, combo) in enumerate(bindings.items(), start=1):
            *mods, key = combo.lower().split("+")
            self._bindings[i] = (sum(MOD[m] for m in mods), ord(key.upper()), combo)
            self.names[i] = name
        ready = threading.Event()
        threading.Thread(target=self._run, args=(ready,), daemon=True).start()
        ready.wait(2)

    def _run(self, ready):
        self.tid = k32.GetCurrentThreadId()
        for i, (mods, vk, combo) in self._bindings.items():
            if not u32.RegisterHotKey(None, i, mods | 0x4000, vk):  # MOD_NOREPEAT
                self.failed.append(combo)
        ready.set()
        msg = wt.MSG()
        while u32.GetMessageW(byref(msg), None, 0, 0) > 0:
            if msg.message == 0x0312:  # WM_HOTKEY
                self.q.put(self.names.get(msg.wParam))
        for i in self._bindings:
            u32.UnregisterHotKey(None, i)

    def poll(self):
        try:
            return self.q.get_nowait()
        except queue.Empty:
            return None

    def stop(self):
        if self.tid:
            u32.PostThreadMessageW(self.tid, 0x0012, 0, 0)  # WM_QUIT


# ---------- громкость того, что играет (Core Audio через COM) ----------
class _GUID(ctypes.Structure):
    _fields_ = [("Data1", c_ulong), ("Data2", c_ushort), ("Data3", c_ushort), ("Data4", c_ubyte * 8)]


def _guid(s):
    g = _GUID()
    ole32.CLSIDFromString(ctypes.c_wchar_p(s), byref(g))
    return g


def _method(ptr, index, *argtypes):
    vtbl = ctypes.cast(ptr, POINTER(POINTER(c_void_p)))[0]
    fn = WINFUNCTYPE(ctypes.HRESULT, c_void_p, *argtypes)(vtbl[index])
    return lambda *a: fn(ptr, *a)


_CLSID_ENUM = _guid("{BCDE0395-E52F-467C-8E3D-C4579291692E}")
_IID_ENUM = _guid("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
_IID_METER = _guid("{C02216F6-8C67-4B5B-9D00-D008E73E0064}")


class AudioMeter:
    """peak() — насколько громко сейчас звучит динамик (0..1)."""

    def __init__(self):
        self.meter = None
        self.age = 0

    def _release(self, p):
        if p:
            try:
                _method(p, 2)()
            except OSError:
                pass

    def _make(self):
        ole32.CoInitialize(None)
        enum, dev, meter = c_void_p(), c_void_p(), c_void_p()
        hr = ole32.CoCreateInstance(byref(_CLSID_ENUM), None, 23, byref(_IID_ENUM), byref(enum))
        if hr != 0:
            return None
        try:
            _method(enum, 4, c_int, c_int, POINTER(c_void_p))(0, 1, byref(dev))  # eRender, eMultimedia
            _method(dev, 3, POINTER(_GUID), wt.DWORD, c_void_p, POINTER(c_void_p))(
                byref(_IID_METER), 23, None, byref(meter))
            return meter
        except OSError:
            return None
        finally:
            self._release(dev)
            self._release(enum)

    def peak(self):
        self.age += 1
        if self.meter is None or self.age > 300:  # иногда пересоздаём: могли сменить наушники
            self._release(self.meter)
            self.meter, self.age = self._make(), 0
            if self.meter is None:
                return 0.0
        v = c_float()
        try:
            _method(self.meter, 3, POINTER(c_float))(byref(v))
        except OSError:
            self.meter = None
            return 0.0
        return v.value
