# -*- coding: utf-8 -*-
import ctypes
from ctypes import wintypes
import json
import logging
import os
import sys
import threading
import time
import traceback
import tkinter as tk
from tkinter import messagebox

try:
    import keyboard
except Exception:
    keyboard = None


APP_TITLE = "悬浮剪贴板"
CONFIG_FILE = "keyboard_config.json"
AUTO_ENTER_AFTER_TEXT = True

COLOR_BG = "#F5F7FB"
COLOR_PANEL = "#FFFFFF"
COLOR_ACCENT = "#EAF2FF"
COLOR_ACCENT_DARK = "#2563EB"
COLOR_PINK = "#FEE2E2"
COLOR_GREEN = "#E7F8EE"
COLOR_HOLD = "#FFF4CC"
COLOR_BLACK = "#1F2937"
COLOR_BORDER = "#E5E7EB"
COLOR_WHITE = "#FFFFFF"
COLOR_MUTED = "#6B7280"
COLOR_HOVER = "#F1F5F9"


user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
gdi32 = ctypes.windll.gdi32
GetWindowLong = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
SetWindowLong = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)


GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
WM_NCLBUTTONDOWN = 0x00A1
HTCAPTION = 2

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
KEYEVENTF_KEYUP = 0x0002
VK_LBUTTON = 0x01
WM_MOUSEACTIVATE = 0x0021
MA_NOACTIVATE = 3


def configure_logging(base_dir):
    logging.basicConfig(
        filename=os.path.join(base_dir, "floating_clipboard.log"),
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        encoding="utf-8",
    )


def configure_win32_signatures():
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, wintypes.ULONG]
    user32.keybd_event.restype = None
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.BringWindowToTop.argtypes = [wintypes.HWND]
    user32.BringWindowToTop.restype = wintypes.BOOL
    user32.SetFocus.argtypes = [wintypes.HWND]
    user32.SetFocus.restype = wintypes.HWND
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    user32.AttachThreadInput.restype = wintypes.BOOL
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.restype = ctypes.c_int
    kernel32.GetCurrentThreadId.argtypes = []
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD


configure_win32_signatures()


def enable_dpi_awareness():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def get_scale_factor():
    hdc = user32.GetDC(0)
    try:
        dpi_x = gdi32.GetDeviceCaps(hdc, 88)
        return max(1.0, dpi_x / 96.0)
    finally:
        user32.ReleaseDC(0, hdc)


enable_dpi_awareness()
SCALE_FACTOR = get_scale_factor()
UI_SCALE = 1.0
FONT_SCALE = 2.3
TEXT_SEND_INTERVAL_MS = 820
APP_PID = os.getpid()


def spx(value):
    return int(round(value * UI_SCALE))


def font_size(value):
    return max(8, int(round(value * FONT_SCALE)))


def configure_tk_scaling(root):
    try:
        root.tk.call("tk", "scaling", 1.0)
    except Exception:
        pass


def hwnd_of(window):
    window.update_idletasks()
    return wintypes.HWND(window.winfo_id()).value


def apply_noactivate_topmost(window):
    try:
        hwnd = hwnd_of(window)
        ex_style = GetWindowLong(hwnd, GWL_EXSTYLE)
        SetWindowLong(hwnd, GWL_EXSTYLE, ex_style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
        user32.SetWindowPos(
            hwnd,
            HWND_TOPMOST,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )
    except Exception:
        pass


def keep_topmost(window):
    try:
        hwnd = hwnd_of(window)
        user32.SetWindowPos(
            hwnd,
            HWND_TOPMOST,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )
    except Exception:
        pass


def get_foreground_hwnd():
    try:
        return user32.GetForegroundWindow()
    except Exception:
        return None


def describe_window(hwnd):
    if not hwnd:
        return "None"
    try:
        title = ctypes.create_unicode_buffer(160)
        klass = ctypes.create_unicode_buffer(120)
        user32.GetWindowTextW(hwnd, title, len(title))
        user32.GetClassNameW(hwnd, klass, len(klass))
        return f"hwnd={hwnd} class={klass.value!r} title={title.value!r}"
    except Exception:
        return f"hwnd={hwnd}"


def get_window_pid(hwnd):
    if not hwnd:
        return None
    try:
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value
    except Exception:
        return None


def activate_window(hwnd):
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    try:
        current_thread = kernel32.GetCurrentThreadId()
        target_thread = user32.GetWindowThreadProcessId(hwnd, None)
        if target_thread and target_thread != current_thread:
            user32.AttachThreadInput(current_thread, target_thread, True)
        try:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            user32.SetFocus(hwnd)
        finally:
            if target_thread and target_thread != current_thread:
                user32.AttachThreadInput(current_thread, target_thread, False)
        return True
    except Exception:
        logging.error("activate_window failed hwnd=%s\n%s", hwnd, traceback.format_exc())
        return False


def begin_system_drag(window):
    try:
        hwnd = hwnd_of(window)
        user32.ReleaseCapture()
        user32.PostMessageW(hwnd, WM_NCLBUTTONDOWN, HTCAPTION, 0)
    except Exception:
        pass


def write_clipboard_text(text):
    data = (text + "\0").encode("utf-16le")
    if not user32.OpenClipboard(None):
        raise RuntimeError("无法打开系统剪贴板")
    try:
        user32.EmptyClipboard()
        h_global = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not h_global:
            raise RuntimeError("剪贴板内存分配失败")
        locked = kernel32.GlobalLock(h_global)
        if not locked:
            raise RuntimeError("剪贴板内存锁定失败")
        ctypes.memmove(locked, data, len(data))
        kernel32.GlobalUnlock(h_global)
        if not user32.SetClipboardData(CF_UNICODETEXT, h_global):
            raise RuntimeError("写入剪贴板失败")
    finally:
        user32.CloseClipboard()


VK_MAP = {
    "ctrl": 0x11,
    "control": 0x11,
    "shift": 0x10,
    "alt": 0x12,
    "win": 0x5B,
    "windows": 0x5B,
    "cmd": 0x5B,
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "esc": 0x1B,
    "escape": 0x1B,
    "space": 0x20,
    "backspace": 0x08,
    "delete": 0x2E,
    "del": 0x2E,
    "insert": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "page up": 0x21,
    "pageup": 0x21,
    "page down": 0x22,
    "pagedown": 0x22,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "caps lock": 0x14,
    "capslock": 0x14,
}

for i in range(10):
    VK_MAP[str(i)] = ord(str(i))
for ch in "abcdefghijklmnopqrstuvwxyz":
    VK_MAP[ch] = ord(ch.upper())
for i in range(1, 25):
    VK_MAP[f"f{i}"] = 0x70 + i - 1


def parse_hotkey(content):
    parts = [p.strip().lower() for p in content.replace("＋", "+").split("+") if p.strip()]
    if not parts:
        raise ValueError("快捷键内容为空")
    vks = []
    for part in parts:
        vk = VK_MAP.get(part)
        if vk is None:
            raise ValueError(f"暂不支持的按键: {part}")
        vks.append(vk)
    return vks


def key_down(vk):
    user32.keybd_event(vk, 0, 0, 0)


def key_up(vk):
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


def tap_hotkey(content):
    vks = parse_hotkey(content)
    for vk in vks:
        key_down(vk)
        time.sleep(0.018)
    for vk in reversed(vks):
        key_up(vk)
        time.sleep(0.018)


def item_key(item):
    return f"{item.get('name', '')}::{item.get('type', '')}::{item.get('content', '')}"


def display_type(kind):
    return {"text": "发送文本", "shortcut": "模拟快捷键", "hold": "按键长按"}.get(kind, kind)


DEFAULT_ITEMS = [
    {"name": "您好", "type": "text", "content": "您好，请问有什么可以帮您？"},
    {"name": "收到", "type": "text", "content": "收到，我稍后处理。"},
    {"name": "谢谢", "type": "text", "content": "谢谢，辛苦了。"},
    {"name": "截图", "type": "shortcut", "content": "ctrl+alt+a"},
]


class ConfigStore:
    def __init__(self, base_dir):
        self.path = os.path.join(base_dir, CONFIG_FILE)
        self.items = []

    def load(self):
        if not os.path.exists(self.path):
            self.items = [dict(item) for item in DEFAULT_ITEMS]
            self.save()
            logging.info("config created path=%s items=%s", self.path, len(self.items))
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.items = [
                {
                    "name": str(item.get("name", "")).strip(),
                    "type": item.get("type", "text"),
                    "content": str(item.get("content", "")),
                }
                for item in data
                if isinstance(item, dict)
            ]
            logging.info("config loaded path=%s items=%s", self.path, len(self.items))
        except Exception:
            logging.error("config load failed path=%s\n%s", self.path, traceback.format_exc())
            self.items = [dict(item) for item in DEFAULT_ITEMS]
            self.save()

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.items, f, ensure_ascii=False, indent=2)
        logging.info("config saved path=%s items=%s", self.path, len(self.items))


class ActionEngine:
    def __init__(self, app):
        self.app = app
        self.hold_states = {}
        self.active_count = 0

    def execute(self, item):
        target = self.app.choose_target_window()
        logging.info("execute requested name=%r target=%s", item.get("name", ""), describe_window(target))
        self.app.set_status(f"正在执行: {item.get('name', '')}")
        threading.Thread(target=self.execute_now, args=(dict(item), target), daemon=True).start()

    def execute_now(self, item, locked_target=None):
        self.active_count += 1
        kind = item.get("type", "text")
        content = item.get("content", "")
        logging.info("execute start name=%r type=%s content_len=%s", item.get("name", ""), kind, len(content))
        try:
            if kind == "text":
                target = self.app.prepare_target_window(locked_target)
                if not target:
                    raise RuntimeError("未找到目标输入框，请先点击一次目标输入框")
                write_clipboard_text(content)
                logging.info("text target prepared hwnd=%s", target)
                time.sleep(0.12)
                tap_hotkey("ctrl+v")
                time.sleep(0.16)
                if AUTO_ENTER_AFTER_TEXT:
                    tap_hotkey("enter")
                    time.sleep(0.12)
            elif kind == "shortcut":
                target = self.app.prepare_target_window(locked_target)
                if not target:
                    raise RuntimeError("未找到目标窗口，请先点击一次目标窗口")
                logging.info("shortcut target prepared hwnd=%s", target)
                time.sleep(0.04)
                tap_hotkey(content)
            elif kind == "hold":
                self.toggle_hold(item)
            logging.info("execute success name=%r type=%s", item.get("name", ""), kind)
            self.app.set_status_async(f"已执行: {item.get('name', '')}")
        except Exception as exc:
            logging.error(
                "execute failed name=%r type=%s error=%s\n%s",
                item.get("name", ""),
                kind,
                exc,
                traceback.format_exc(),
            )
            short = str(exc)
            if len(short) > 34:
                short = short[:34] + "..."
            self.app.set_status_async(f"执行失败: {short}")
        finally:
            self.active_count = max(0, self.active_count - 1)

    def toggle_hold(self, item):
        key = item_key(item)
        content = item.get("content", "")
        vks = parse_hotkey(content)
        if self.hold_states.get(key):
            for vk in reversed(vks):
                key_up(vk)
            self.hold_states.pop(key, None)
        else:
            for vk in vks:
                key_down(vk)
            self.hold_states[key] = vks
        logging.info("hold toggled name=%r active=%s", item.get("name", ""), bool(self.hold_states.get(key)))
        self.app.root.after(0, self.app.refresh_hold_states)

    def release_all(self):
        for vks in list(self.hold_states.values()):
            for vk in reversed(vks):
                try:
                    key_up(vk)
                except Exception:
                    pass
        self.hold_states.clear()

    def is_holding(self, item):
        return item_key(item) in self.hold_states


class EditDialog(tk.Toplevel):
    def __init__(self, app, item=None, index=None):
        super().__init__(app.root)
        self.app = app
        self.item = item
        self.index = index
        self.var_name = tk.StringVar(value=item.get("name", "") if item else "")
        self.var_type = tk.StringVar(value=item.get("type", "text") if item else "text")
        self.var_key = tk.StringVar(value=item.get("content", "") if item and item.get("type") != "text" else "")
        self.captured_value = self.var_key.get()
        self.type_buttons = {}

        self.title("编辑快捷项" if item else "新增快捷项")
        self.configure(bg=COLOR_BG)
        self.geometry(f"{spx(760)}x{spx(680)}")
        self.resizable(False, False)
        self.transient(app.root)
        self.grab_set()
        self.focus_force()
        self.build()

    def build(self):
        pad = spx(16)
        outer = tk.Frame(self, bg=COLOR_BG)
        outer.pack(fill="both", expand=True, padx=pad, pady=pad)

        title = tk.Label(
            outer,
            text="编辑快捷项" if self.item else "新增快捷项",
            bg=COLOR_BG,
            fg=COLOR_BLACK,
            font=("Microsoft YaHei UI", font_size(15), "bold"),
        )
        title.pack(anchor="w", pady=(0, spx(12)))

        tk.Label(
            outer,
            text="按钮名称",
            bg=COLOR_BG,
            fg=COLOR_BLACK,
            font=("Microsoft YaHei UI", font_size(11), "bold"),
        ).pack(anchor="w")
        name_entry = tk.Entry(
            outer,
            textvariable=self.var_name,
            font=("Microsoft YaHei UI", font_size(13)),
            relief="solid",
            bd=spx(1),
        )
        name_entry.pack(fill="x", ipady=spx(7), pady=(spx(4), spx(14)))

        type_row = tk.Frame(outer, bg=COLOR_BG)
        type_row.pack(fill="x", pady=(0, spx(12)))
        for text, value in [("文本", "text"), ("快捷键", "shortcut"), ("长按", "hold")]:
            btn = tk.Button(
                type_row,
                text=text,
                command=lambda v=value: self.set_type(v),
                bg=COLOR_PANEL,
                fg=COLOR_BLACK,
                activebackground=COLOR_ACCENT,
                relief="solid",
                bd=spx(1),
                padx=spx(12),
                pady=spx(8),
                font=("Microsoft YaHei UI", font_size(11), "bold"),
            )
            btn.pack(side="left", expand=True, fill="x", padx=spx(4))
            self.type_buttons[value] = btn

        self.content_holder = tk.Frame(outer, bg=COLOR_BG)
        self.content_holder.pack(fill="both", expand=True, pady=(0, spx(12)))

        self.text_box = tk.Text(
            self.content_holder,
            wrap="word",
            height=8,
            font=("Microsoft YaHei UI", font_size(13)),
            relief="solid",
            bd=spx(1),
            padx=spx(8),
            pady=spx(8),
        )
        if self.item and self.item.get("type") == "text":
            self.text_box.insert("1.0", self.item.get("content", ""))

        self.key_panel = tk.Frame(self.content_holder, bg=COLOR_PANEL, highlightthickness=spx(1), highlightbackground=COLOR_BORDER)
        self.key_label = tk.Label(
            self.key_panel,
            text=self.key_label_text(),
            bg=COLOR_PANEL,
            fg=COLOR_BLACK,
            justify="center",
            font=("Microsoft YaHei UI", font_size(13), "bold"),
        )
        self.key_label.pack(expand=True, fill="both", padx=spx(14), pady=spx(14))
        self.key_panel.bind("<Button-1>", lambda _e: self.capture_hotkey())
        self.key_label.bind("<Button-1>", lambda _e: self.capture_hotkey())

        manual = tk.Entry(
            self.key_panel,
            textvariable=self.var_key,
            font=("Consolas", font_size(11)),
            relief="solid",
            bd=spx(1),
        )
        manual.pack(fill="x", padx=spx(20), pady=(0, spx(20)), ipady=spx(5))
        manual.bind("<KeyRelease>", lambda _e: self.update_key_label())

        button_row = tk.Frame(outer, bg=COLOR_BG)
        button_row.pack(fill="x", side="bottom", pady=(spx(8), 0))
        self.make_dialog_button(button_row, "取消", COLOR_WHITE, self.destroy).pack(side="right", padx=(spx(8), 0))
        self.make_dialog_button(button_row, "确定保存", COLOR_ACCENT, self.save).pack(side="right")

        self.sync_content_area()

    def make_dialog_button(self, parent, text, bg, command):
        primary = bg == COLOR_ACCENT
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=COLOR_ACCENT_DARK if primary else COLOR_PANEL,
            fg=COLOR_WHITE if primary else COLOR_BLACK,
            activebackground=COLOR_GREEN,
            relief="flat",
            bd=0,
            padx=spx(18),
            pady=spx(8),
            font=("Microsoft YaHei UI", font_size(11), "bold"),
            cursor="hand2",
        )

    def set_type(self, value):
        self.var_type.set(value)
        self.sync_content_area()

    def key_label_text(self):
        value = self.var_key.get().strip()
        if value:
            return f"已录制: {value}\n点击此处重新录制，或在下方手动输入"
        if keyboard:
            return "点击此处录制组合键\n例如 Ctrl+Shift+Z"
        return "未安装 keyboard 库\n请在下方手动输入，例如 ctrl+shift+z"

    def update_key_label(self):
        self.captured_value = self.var_key.get().strip()
        self.key_label.configure(text=self.key_label_text())

    def sync_content_area(self):
        for child in self.content_holder.winfo_children():
            child.pack_forget()
        for value, button in self.type_buttons.items():
            selected = value == self.var_type.get()
            button.configure(
                bg=COLOR_ACCENT_DARK if selected else COLOR_PANEL,
                fg=COLOR_WHITE if selected else COLOR_BLACK,
                relief="sunken" if selected else "solid",
            )
        if self.var_type.get() == "text":
            self.text_box.pack(fill="both", expand=True)
        else:
            self.key_panel.pack(fill="both", expand=True)
            self.update_key_label()

    def capture_hotkey(self):
        if self.var_type.get() == "text":
            return
        if keyboard is None:
            self.update_key_label()
            return
        self.key_label.configure(text="正在录制...请按下目标按键组合")

        def worker():
            try:
                value = keyboard.read_hotkey(suppress=False)
            except Exception as exc:
                value = ""
                error = str(exc)
            else:
                error = ""

            def done():
                if value:
                    self.var_key.set(value)
                    self.captured_value = value
                    self.key_label.configure(text=f"录制成功: {value}\n点击此处重新录制")
                else:
                    self.key_label.configure(text=f"录制失败: {error}\n可在下方手动输入")

            self.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def save(self):
        name = self.var_name.get().strip()
        kind = self.var_type.get()
        if not name:
            messagebox.showwarning("缺少名称", "请填写按钮名称。", parent=self)
            return
        if kind == "text":
            content = self.text_box.get("1.0", "end-1c")
        else:
            content = self.var_key.get().strip()
        if not content:
            messagebox.showwarning("缺少内容", "请填写或录制执行内容。", parent=self)
            return
        if kind != "text":
            try:
                parse_hotkey(content)
            except Exception as exc:
                messagebox.showwarning("按键不支持", str(exc), parent=self)
                return
        self.app.upsert_item({"name": name, "type": kind, "content": content}, self.index, self.item)
        self.destroy()


class FloatingButtonWindow(tk.Toplevel):
    def __init__(self, app, item, x, y, width=220):
        super().__init__(app.root)
        self.app = app
        self.item = dict(item)
        self.width = width
        self.drag_start = None
        self.has_moved = False
        self.overrideredirect(True)
        self.configure(bg=COLOR_BLACK)
        self.build()
        self.geometry(f"+{x}+{y}")
        self.after(0, lambda: apply_noactivate_topmost(self))
        self.after(1500, self.topmost_tick)

    def build(self):
        self.frame = tk.Frame(self, bg=COLOR_PANEL, highlightthickness=spx(1), highlightbackground=COLOR_BORDER)
        self.frame.pack(fill="both", expand=True)
        self.label = tk.Label(
            self.frame,
            text=self.item.get("name", ""),
            bg=COLOR_HOLD if self.app.engine.is_holding(self.item) else COLOR_PANEL,
            fg=COLOR_BLACK,
            wraplength=spx(max(60, self.width - 24)),
            justify="center",
            padx=spx(10),
            pady=spx(16),
            font=("Microsoft YaHei UI", font_size(13), "bold"),
        )
        self.label.pack(fill="both", expand=True)
        self.close_label = tk.Label(
            self.frame,
            text="×",
            bg=COLOR_PINK,
            fg=COLOR_BLACK,
            width=2,
            height=1,
            relief="solid",
            bd=spx(1),
            font=("Arial", font_size(10), "bold"),
        )
        self.close_label.place(relx=1.0, x=-spx(31), y=spx(5))
        self.close_label.bind("<Button-1>", lambda _e: self.destroy())
        self.close_label.bind("<Enter>", lambda _e: self.close_label.configure(bg="#FF3B30"))
        self.close_label.bind("<Leave>", lambda _e: self.close_label.configure(bg=COLOR_PINK))

        for widget in (self.frame, self.label):
            widget.bind("<Button-1>", self.on_press)
            widget.bind("<B1-Motion>", self.on_motion)
            widget.bind("<ButtonRelease-1>", self.on_release)
            widget.bind("<Button-3>", self.show_menu)
            widget.bind("<MouseWheel>", self.on_wheel)

        self.apply_width(self.width)

    def topmost_tick(self):
        if self.winfo_exists():
            keep_topmost(self)
            self.after(1500, self.topmost_tick)

    def apply_width(self, width):
        self.width = max(80, min(500, int(width)))
        self.label.configure(wraplength=spx(max(60, self.width - 24)))
        self.update_idletasks()
        height = max(spx(64), self.label.winfo_reqheight() + spx(14))
        self.geometry(f"{spx(self.width)}x{height}")

    def on_wheel(self, event):
        step = 14 if event.delta > 0 else -14
        self.apply_width(self.width + step)

    def on_press(self, event):
        self.drag_start = (event.x_root, event.y_root, self.winfo_x(), self.winfo_y())
        self.has_moved = False

    def on_motion(self, event):
        if not self.drag_start:
            return
        sx, sy, wx, wy = self.drag_start
        dx = event.x_root - sx
        dy = event.y_root - sy
        if abs(dx) + abs(dy) > spx(5):
            self.has_moved = True
            self.geometry(f"+{wx + dx}+{wy + dy}")

    def on_release(self, _event):
        if not self.has_moved:
            self.app.engine.execute(self.item)
            self.refresh_visual()
        self.drag_start = None
        self.has_moved = False

    def refresh_visual(self):
        self.label.configure(bg=COLOR_HOLD if self.app.engine.is_holding(self.item) else COLOR_PANEL)

    def show_menu(self, event):
        PopupMenu(
            self,
            [
                ("小尺寸 150px", lambda: self.apply_width(150)),
                ("中尺寸 220px", lambda: self.apply_width(220)),
                ("大尺寸 320px", lambda: self.apply_width(320)),
                ("收回悬浮按钮", self.destroy),
            ],
            event.x_root,
            event.y_root,
        )

    def destroy(self):
        self.app.unregister_floating(self.item, self)
        super().destroy()


class ShortcutCell(tk.Label):
    def __init__(self, app, parent, item, index):
        self.app = app
        self.item = item
        self.index = index
        super().__init__(
            parent,
            text=self.text_for_item(),
            bg=self.bg_for_item(),
            fg=COLOR_BLACK,
            relief="flat",
            bd=0,
            highlightthickness=spx(1),
            highlightbackground=COLOR_BORDER,
            highlightcolor=COLOR_ACCENT_DARK,
            anchor="center",
            justify="center",
            padx=spx(10),
            pady=spx(6),
            wraplength=spx(300),
            font=("Microsoft YaHei UI", font_size(14), "bold"),
            cursor="hand2",
        )
        self.start = None
        self.dragging = False
        self.long_press_ready = False
        self.long_press_timer = None
        self.released = False
        self.bind("<Button-1>", self.on_press)
        self.bind("<B1-Motion>", self.on_motion)
        self.bind("<ButtonRelease-1>", self.on_release)
        self.bind("<Button-3>", self.show_menu)
        self.bind("<Enter>", self.on_enter)
        self.bind("<Leave>", self.on_leave)

    def text_for_item(self):
        if self.app.engine.is_holding(self.item):
            prefix = "●"
        else:
            prefix = {"text": "T", "shortcut": "⌘", "hold": "⏺"}.get(self.item.get("type"), "•")
        return f"{prefix}  {self.item.get('name', '')}"

    def bg_for_item(self):
        if self.app.engine.is_holding(self.item):
            return COLOR_HOLD
        return COLOR_ACCENT if self.item.get("type") == "text" else COLOR_PANEL

    def refresh_visual(self):
        self.configure(text=self.text_for_item(), bg=self.bg_for_item())

    def on_enter(self, _event):
        self.configure(bg=COLOR_HOVER if self.item.get("type") != "text" else "#DDEBFF")
        content = self.item.get("content", "")
        if len(content) > 60:
            content = content[:60] + "..."
        self.app.set_status(f"绑定类型: {display_type(self.item.get('type'))} | 内容: {content}", temporary=False)

    def on_leave(self, _event):
        self.refresh_visual()
        self.app.schedule_default_status()

    def on_press(self, event):
        self.start = (event.x_root, event.y_root)
        self.dragging = False
        self.long_press_ready = False
        self.released = False
        if self.long_press_timer:
            self.after_cancel(self.long_press_timer)
        self.long_press_timer = self.after(450, self.enable_move_mode)

    def enable_move_mode(self):
        self.long_press_ready = True
        self.configure(bg=COLOR_HOLD, highlightbackground=COLOR_ACCENT_DARK)

    def on_motion(self, event):
        if not self.start or self.released:
            return
        dx = event.x_root - self.start[0]
        dy = event.y_root - self.start[1]
        if self.long_press_ready and not self.dragging and (abs(dx) + abs(dy)) > spx(6):
            self.dragging = True
            self.app.active_drag_cell = self
            self.app.poll_drag_release()
            self.configure(bg=COLOR_HOLD)
            self.app.preview_reorder(self.index, event.x_root, event.y_root)
        elif self.dragging:
            self.app.preview_reorder(self.index, event.x_root, event.y_root)

    def on_release(self, event):
        if self.long_press_timer:
            self.after_cancel(self.long_press_timer)
            self.long_press_timer = None
        if self.released:
            return
        self.released = True
        if self.dragging:
            self.finish_drag(event.x_root, event.y_root)
        elif not self.long_press_ready:
            self.app.engine.execute(self.item)
            self.app.refresh_hold_states()
        else:
            self.refresh_visual()
        self.start = None
        self.dragging = False
        self.long_press_ready = False

    def finish_drag(self, x, y):
        if self.app.active_drag_cell is self:
            self.app.active_drag_cell = None
        self.refresh_visual()
        if not self.app.point_inside_main_window(x, y):
            self.app.create_floating(self.item, x, y)
        else:
            self.app.reorder_item(self.index, x, y)

    def force_release_if_mouse_up(self):
        if not self.dragging or self.released:
            return
        if user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000:
            return
        pos = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pos))
        self.on_release(type("Event", (), {"x_root": pos.x, "y_root": pos.y})())

    def show_menu(self, event):
        PopupMenu(
            self,
            [
                ("编辑快捷项", lambda: self.app.open_edit(self.index)),
                ("删除快捷项", lambda: self.app.delete_item(self.index)),
            ],
            event.x_root,
            event.y_root,
        )


class PopupMenu(tk.Toplevel):
    def __init__(self, parent, items, x, y):
        super().__init__(parent)
        self.overrideredirect(True)
        self.configure(bg=COLOR_BORDER)
        self.transient(parent)
        frame = tk.Frame(self, bg=COLOR_PANEL, padx=spx(4), pady=spx(4))
        frame.pack(fill="both", expand=True, padx=spx(1), pady=spx(1))
        for label, command in items:
            row = tk.Label(
                frame,
                text=label,
                bg=COLOR_PANEL,
                fg=COLOR_BLACK,
                anchor="w",
                padx=spx(18),
                pady=spx(10),
                font=("Microsoft YaHei UI", font_size(11), "bold"),
                cursor="hand2",
            )
            row.pack(fill="x")
            row.bind("<Enter>", lambda _e, w=row: w.configure(bg=COLOR_ACCENT))
            row.bind("<Leave>", lambda _e, w=row: w.configure(bg=COLOR_PANEL))
            row.bind("<Button-1>", lambda _e, c=command: self.select(c))
        self.geometry(f"+{x}+{y}")
        self.after(0, lambda: apply_noactivate_topmost(self))
        self.after(50, self.grab_set_global_safe)
        self.bind("<FocusOut>", lambda _e: self.destroy())

    def grab_set_global_safe(self):
        try:
            self.grab_set_global()
            self.bind("<ButtonRelease-1>", lambda _e: None)
        except Exception:
            pass

    def select(self, command):
        self.destroy()
        command()


class FloatingClipboardApp:
    def __init__(self, root, base_dir):
        self.root = root
        self.base_dir = base_dir
        self.store = ConfigStore(base_dir)
        self.store.load()
        self.active_floating_windows = {}
        self.active_drag_cell = None
        self.title_drag = None
        self.last_target_hwnd = None
        self.own_hwnds_cache = set()
        self.cells = []
        self.normal_geometry = f"{spx(760)}x{spx(520)}+{spx(120)}+{spx(120)}"
        self.collapsed = False
        self.circle_mode = False
        self.circle_window = None
        self.engine = ActionEngine(self)
        self.build()
        self.refresh_grid()
        self.root.after(0, lambda: apply_noactivate_topmost(self.root))
        self.root.after(1500, self.topmost_tick)
        self.root.after(80, self.update_own_hwnds_cache)
        self.root.after(120, self.track_foreground_window)

    def build(self):
        self.root.title(APP_TITLE)
        self.root.overrideredirect(True)
        self.root.configure(bg=COLOR_BLACK)
        self.root.geometry(self.normal_geometry)
        self.root.resizable(False, False)

        self.shell = tk.Frame(self.root, bg=COLOR_PANEL, highlightthickness=spx(1), highlightbackground=COLOR_BORDER)
        self.shell.pack(fill="both", expand=True)

        self.title_bar = tk.Frame(self.shell, bg=COLOR_PANEL, height=spx(86), highlightthickness=0)
        self.title_bar.pack(fill="x")
        self.title_bar.pack_propagate(False)
        self.title_bar.bind("<Button-1>", self.start_title_drag)
        self.title_bar.bind("<B1-Motion>", self.move_title_drag)

        title_icon = tk.Canvas(self.title_bar, width=spx(34), height=spx(34), bg=COLOR_PANEL, highlightthickness=0)
        title_icon.pack(side="left", padx=(spx(18), spx(8)))
        title_icon.create_rectangle(spx(9), spx(8), spx(27), spx(29), fill=COLOR_ACCENT, outline=COLOR_ACCENT_DARK, width=spx(2))
        title_icon.create_rectangle(spx(13), spx(4), spx(23), spx(11), fill=COLOR_PANEL, outline=COLOR_ACCENT_DARK, width=spx(2))
        title_icon.create_line(spx(13), spx(17), spx(23), spx(17), fill=COLOR_BLACK, width=spx(2))
        title_icon.create_line(spx(13), spx(23), spx(21), spx(23), fill=COLOR_BLACK, width=spx(2))
        title_icon.bind("<Button-1>", self.start_title_drag)
        title_icon.bind("<B1-Motion>", self.move_title_drag)

        title = tk.Label(
            self.title_bar,
            text=APP_TITLE,
            bg=COLOR_PANEL,
            fg=COLOR_BLACK,
            font=("Microsoft YaHei UI", font_size(13), "bold"),
        )
        title.pack(side="left")
        title.bind("<Button-1>", self.start_title_drag)
        title.bind("<B1-Motion>", self.move_title_drag)

        self.make_title_button(self.title_bar, "◉", COLOR_ACCENT, self.minimize_to_circle).pack(side="right", padx=(spx(6), spx(18)), pady=spx(14))
        self.make_title_button(self.title_bar, "×", COLOR_PINK, self.close).pack(side="right", padx=spx(6), pady=spx(14))
        self.make_title_button(self.title_bar, "▴", COLOR_WHITE, self.toggle_collapse).pack(side="right", padx=spx(6), pady=spx(14))
        self.make_title_button(self.title_bar, "−", COLOR_WHITE, self.hide_window).pack(side="right", padx=spx(6), pady=spx(14))
        self.make_title_button(self.title_bar, "+", COLOR_ACCENT, lambda: self.open_edit(None)).pack(side="right", padx=spx(6), pady=spx(14))

        self.divider = tk.Frame(self.shell, height=spx(1), bg=COLOR_BORDER)
        self.divider.pack(fill="x")

        self.body = tk.Frame(self.shell, bg=COLOR_BG)
        self.body.pack(fill="both", expand=True, padx=spx(12), pady=(spx(12), spx(8)))

        self.canvas = tk.Canvas(self.body, bg=COLOR_BG, highlightthickness=0)
        self.scrollbar = tk.Scrollbar(self.body, orient="vertical", command=self.canvas.yview)
        self.grid_frame = tk.Frame(self.canvas, bg=COLOR_BG)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.grid_frame.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self.on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self.on_mousewheel)

    def make_title_button(self, parent, text, bg, command):
        button = tk.Label(
            parent,
            text=text,
            bg=bg,
            fg=COLOR_BLACK,
            relief="flat",
            bd=0,
            width=3,
            font=("Arial", font_size(14), "bold"),
            cursor="hand2",
        )
        button.bind("<Button-1>", lambda _e: command())
        button.bind("<Enter>", lambda _e: button.configure(bg=COLOR_HOVER if bg == COLOR_WHITE else bg))
        button.bind("<Leave>", lambda _e: button.configure(bg=bg))
        return button

    def hide_window(self):
        logging.info("main window hidden")
        self.root.withdraw()
        self.show_restore_circle()

    def toggle_collapse(self):
        if self.circle_mode:
            return
        if self.collapsed:
            self.body.pack(fill="both", expand=True, padx=spx(12), pady=(spx(12), spx(8)))
            self.divider.pack(fill="x", after=self.title_bar)
            self.root.geometry(self.normal_geometry)
            self.collapsed = False
            self.set_status("已展开")
        else:
            self.normal_geometry = self.root.winfo_geometry()
            self.body.pack_forget()
            self.divider.pack_forget()
            self.root.geometry(f"{spx(760)}x{spx(88)}+{self.root.winfo_x()}+{self.root.winfo_y()}")
            self.collapsed = True
            self.set_status("已折叠")

    def minimize_to_circle(self):
        logging.info("main window minimized to circle")
        self.circle_mode = True
        self.root.withdraw()
        self.show_restore_circle()

    def show_restore_circle(self):
        if self.circle_window and self.circle_window.winfo_exists():
            self.circle_window.deiconify()
            return
        self.circle_window = tk.Toplevel(self.root)
        self.circle_window.overrideredirect(True)
        self.circle_window.configure(bg=COLOR_BG)
        try:
            self.circle_window.wm_attributes("-transparentcolor", COLOR_BG)
        except Exception:
            pass
        size = spx(78)
        x = self.root.winfo_x() + spx(18)
        y = self.root.winfo_y() + spx(18)
        self.circle_window.geometry(f"{size}x{size}+{x}+{y}")
        canvas = tk.Canvas(self.circle_window, width=size, height=size, highlightthickness=0, bg=COLOR_BG)
        canvas.pack(fill="both", expand=True)
        canvas.create_oval(spx(4), spx(6), size - spx(4), size - spx(2), fill="#C7D2FE", outline="", width=0)
        canvas.create_oval(spx(4), spx(3), size - spx(4), size - spx(5), fill="#F8FAFC", outline="#60A5FA", width=spx(3))
        canvas.create_rectangle(spx(22), spx(25), spx(56), spx(57), fill="#DBEAFE", outline="#2563EB", width=spx(2))
        canvas.create_rectangle(spx(30), spx(18), spx(48), spx(29), fill="#2563EB", outline="#2563EB", width=spx(2))
        canvas.create_line(spx(30), spx(38), spx(48), spx(38), fill="#1D4ED8", width=spx(2))
        canvas.create_line(spx(30), spx(47), spx(43), spx(47), fill="#1D4ED8", width=spx(2))
        canvas.create_oval(spx(34), spx(8), spx(44), spx(18), fill="#93C5FD", outline="", width=0)
        self.circle_drag = None
        for widget in (self.circle_window, canvas):
            widget.bind("<Button-1>", self.start_circle_drag)
            widget.bind("<B1-Motion>", self.move_circle_drag)
            widget.bind("<ButtonRelease-1>", self.restore_from_circle)
            widget.bind("<Double-Button-1>", self.restore_from_circle)
            widget.bind("<Button-3>", self.restore_from_circle)
        self.circle_window.after(0, lambda: apply_noactivate_topmost(self.circle_window))

    def start_circle_drag(self, event):
        if not self.circle_window:
            return
        self.circle_drag = (event.x_root, event.y_root, self.circle_window.winfo_x(), self.circle_window.winfo_y(), False, time.time())

    def move_circle_drag(self, event):
        if not self.circle_drag or not self.circle_window:
            return
        sx, sy, wx, wy, _moved, started_at = self.circle_drag
        dx = event.x_root - sx
        dy = event.y_root - sy
        moved = abs(dx) + abs(dy) > spx(5)
        self.circle_drag = (sx, sy, wx, wy, moved, started_at)
        self.circle_window.geometry(f"+{wx + dx}+{wy + dy}")

    def restore_from_circle(self, _event=None):
        moved = self.circle_drag[4] if self.circle_drag else False
        held_too_long = (time.time() - self.circle_drag[5]) > 0.35 if self.circle_drag else False
        self.circle_drag = None
        if moved or held_too_long:
            return
        if self.circle_window and self.circle_window.winfo_exists():
            self.circle_window.withdraw()
        self.root.deiconify()
        self.root.lift()
        self.circle_mode = False
        apply_noactivate_topmost(self.root)

    def start_title_drag(self, event):
        self.title_drag = (event.x_root, event.y_root, self.root.winfo_x(), self.root.winfo_y())

    def move_title_drag(self, event):
        if not self.title_drag:
            return
        sx, sy, wx, wy = self.title_drag
        self.root.geometry(f"+{wx + event.x_root - sx}+{wy + event.y_root - sy}")

    def on_canvas_configure(self, event):
        self.canvas.itemconfigure(self.canvas_window, width=event.width)

    def on_mousewheel(self, event):
        try:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass

    def refresh_grid(self):
        for child in self.grid_frame.winfo_children():
            child.destroy()
        self.cells = []
        for i, item in enumerate(self.store.items):
            cell = ShortcutCell(self, self.grid_frame, item, i)
            row, col = divmod(i, 2)
            cell.grid(row=row, column=col, sticky="ew", padx=spx(8), pady=spx(8), ipady=spx(14))
            self.cells.append(cell)
        for col in range(2):
            self.grid_frame.grid_columnconfigure(col, weight=1, uniform="shortcut")

    def index_from_point(self, x_root, y_root):
        if not self.cells:
            return 0
        best_index = 0
        best_distance = None
        for i, cell in enumerate(self.cells):
            cx = cell.winfo_rootx() + cell.winfo_width() / 2
            cy = cell.winfo_rooty() + cell.winfo_height() / 2
            distance = abs(x_root - cx) + abs(y_root - cy)
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_index = i
        return best_index

    def preview_reorder(self, from_index, x_root, y_root):
        target = self.index_from_point(x_root, y_root)
        for i, cell in enumerate(self.cells):
            if i == from_index:
                cell.configure(bg=COLOR_HOLD, highlightbackground=COLOR_ACCENT_DARK)
            elif i == target:
                cell.configure(bg=COLOR_GREEN, highlightbackground=COLOR_ACCENT_DARK)
            else:
                cell.refresh_visual()

    def reorder_item(self, from_index, x_root, y_root):
        if not (0 <= from_index < len(self.store.items)):
            return
        to_index = self.index_from_point(x_root, y_root)
        if to_index == from_index:
            self.refresh_hold_states()
            return
        item = self.store.items.pop(from_index)
        self.store.items.insert(to_index, item)
        self.store.save()
        self.refresh_grid()
        self.set_status(f"已移动到第 {to_index + 1} 位")

    def collect_own_hwnds(self):
        hwnds = set()

        def visit(widget):
            try:
                if isinstance(widget, (tk.Tk, tk.Toplevel)) and widget.winfo_exists():
                    hwnds.add(hwnd_of(widget))
            except Exception:
                pass
            try:
                for child in widget.winfo_children():
                    visit(child)
            except Exception:
                pass

        visit(self.root)
        for windows in self.active_floating_windows.values():
            for window in list(windows):
                try:
                    if window.winfo_exists():
                        hwnds.add(hwnd_of(window))
                except Exception:
                    pass
        return hwnds

    def update_own_hwnds_cache(self):
        self.own_hwnds_cache = self.collect_own_hwnds()
        self.root.after(500, self.update_own_hwnds_cache)

    def is_own_foreground(self, hwnd):
        if not hwnd:
            return False
        pid = get_window_pid(hwnd)
        if pid == APP_PID:
            return True
        return hwnd in self.own_hwnds_cache

    def track_foreground_window(self):
        hwnd = get_foreground_hwnd()
        if hwnd and not self.is_own_foreground(hwnd):
            self.last_target_hwnd = hwnd
        self.root.after(120, self.track_foreground_window)

    def choose_target_window(self):
        current = get_foreground_hwnd()
        if current and not self.is_own_foreground(current):
            self.last_target_hwnd = current
            logging.info("choose target from current %s", describe_window(current))
            return current
        if self.last_target_hwnd and user32.IsWindow(self.last_target_hwnd):
            logging.info("choose target from last %s current=%s", describe_window(self.last_target_hwnd), describe_window(current))
            return self.last_target_hwnd
        logging.info("choose target failed current=%s last=%s own_current=%s", describe_window(current), describe_window(self.last_target_hwnd), self.is_own_foreground(current))
        return None

    def prepare_target_window(self, locked_target=None):
        current = get_foreground_hwnd()
        target = locked_target or self.last_target_hwnd
        if not target or not user32.IsWindow(target):
            target = self.choose_target_window()
        if target and self.is_own_foreground(target):
            logging.info("prepare target rejected own window %s", describe_window(target))
            target = None
        logging.info(
            "prepare target current=%s target=%s locked=%s own_current=%s",
            describe_window(current),
            describe_window(target),
            describe_window(locked_target),
            self.is_own_foreground(current),
        )
        if target:
            activate_window(target)
        return target

    def set_status_async(self, text, temporary=True):
        try:
            self.root.after(0, lambda: self.set_status(text, temporary=temporary))
        except Exception:
            pass

    def refresh_hold_states(self):
        for cell in self.cells:
            cell.refresh_visual()
        for windows in self.active_floating_windows.values():
            for window in list(windows):
                if window.winfo_exists():
                    window.refresh_visual()

    def set_status(self, text, temporary=True):
        logging.info("status: %s", text)

    def schedule_default_status(self):
        pass

    def open_edit(self, index):
        item = None if index is None else dict(self.store.items[index])
        EditDialog(self, item=item, index=index)

    def upsert_item(self, new_item, index=None, old_item=None):
        if old_item:
            self.destroy_floating_by_item(old_item)
        if index is None:
            self.store.items.append(new_item)
        else:
            self.store.items[index] = new_item
        self.store.save()
        self.refresh_grid()
        self.set_status(f"已保存: {new_item['name']}")

    def delete_item(self, index):
        item = self.store.items[index]
        if not messagebox.askyesno("确认删除", f"确定删除“{item.get('name', '')}”吗？", parent=self.root):
            return
        self.destroy_floating_by_item(item)
        del self.store.items[index]
        self.store.save()
        self.refresh_grid()
        self.set_status("已删除快捷项")

    def create_floating(self, item, x, y):
        window = FloatingButtonWindow(self, item, x, y)
        key = item_key(item)
        self.active_floating_windows.setdefault(key, []).append(window)
        self.set_status(f"已创建悬浮按钮: {item.get('name', '')}")

    def unregister_floating(self, item, window):
        key = item_key(item)
        windows = self.active_floating_windows.get(key)
        if not windows:
            return
        if window in windows:
            windows.remove(window)
        if not windows:
            self.active_floating_windows.pop(key, None)

    def destroy_floating_by_item(self, item):
        key = item_key(item)
        windows = list(self.active_floating_windows.get(key, []))
        for window in windows:
            if window.winfo_exists():
                window.destroy()
        self.active_floating_windows.pop(key, None)

    def point_inside_main_window(self, x, y):
        wx, wy = self.root.winfo_rootx(), self.root.winfo_rooty()
        ww, wh = self.root.winfo_width(), self.root.winfo_height()
        return wx <= x <= wx + ww and wy <= y <= wy + wh

    def poll_drag_release(self):
        cell = self.active_drag_cell
        if cell:
            cell.force_release_if_mouse_up()
            if self.active_drag_cell:
                self.root.after(25, self.poll_drag_release)

    def topmost_tick(self):
        keep_topmost(self.root)
        self.root.after(1500, self.topmost_tick)

    def close(self):
        logging.info("app closing")
        self.engine.release_all()
        if self.circle_window and self.circle_window.winfo_exists():
            try:
                self.circle_window.destroy()
            except Exception:
                pass
        for windows in list(self.active_floating_windows.values()):
            for window in list(windows):
                try:
                    window.destroy()
                except Exception:
                    pass
        self.root.destroy()


def main():
    base_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    configure_logging(base_dir)
    logging.info("app starting base_dir=%s scale=%s ui_scale=%s font_scale=%s", base_dir, SCALE_FACTOR, UI_SCALE, FONT_SCALE)
    root = tk.Tk()
    configure_tk_scaling(root)
    app = FloatingClipboardApp(root, base_dir)
    root.protocol("WM_DELETE_WINDOW", app.close)
    root.mainloop()


if __name__ == "__main__":
    main()
