#!/usr/bin/env python3
"""Matterfall - launcher (Windows, Tkinter + Pillow).

Choose the game folder (and its update), set display, graphics, performance, controls and audio
options, and play. Every option is kept in matterfall.ini in the data folder (the port folder, or
GOW3_DATA_DIR): the runtime and its in-game menu (Insert / R3+L2) read and write the same file,
and tools/run_matterfall.py turns the rest into environment variables and an Unreal Engine config
override pak at every start (gow3_pc/scripts/matterfall_settings.py, ue4_override.py).
No game files ship with the port: the art shown here comes from the player's own game folder.
"""
import ctypes
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import urllib.request
import webbrowser
from tkinter import filedialog, messagebox

try:
    from PIL import Image, ImageDraw, ImageTk
except ImportError:  # the launcher still opens, without pictures
    Image = ImageDraw = ImageTk = None

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "gow3_pc" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import matterfall_settings as ms  # noqa: E402
import ue4_override  # noqa: E402
import save_backup  # noqa: E402

TITLE_ID = "CUSA02475"
APP_TITLE = "Matterfall"
DATA_DIR = Path(os.environ.get("GOW3_DATA_DIR") or ROOT)
INI_FILE = Path(os.environ.get("GOW3_CONFIG") or DATA_DIR / "matterfall.ini")
USER_DIR = Path(os.environ.get("GOW3_USER_DIR") or DATA_DIR / "user")
OUT_DIR = DATA_DIR / "analysis" / "matterfall"
RUN_SCRIPT = ROOT / "tools" / "run_matterfall.py"
STARTER_EXE = ROOT / "Matterfall Launcher.exe"  # the packaged build's starter (tools/package_matterfall.sh)
DEFAULT_GAME_DIR = ROOT.parent / "game" / TITLE_ID  # the development tree's layout
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
# Update notice: the newest GitHub release of this repository is compared with the package's
# VERSION file (nothing is installed; the release page opens). Empty: no check.
UPDATE_REPOSITORY = os.environ.get("MATTERFALL_UPDATE_REPO", "bc160201983/Matterfall-PC-port")
LINKS = (("Patreon", "https://www.patreon.com/c/bilalreloaded", "#f96854", "#ff7f6e"),
         ("YouTube", "https://www.youtube.com/@BilalReloaded", "#e62117", "#ff3b30"))

# -- colours (Matterfall: deep blue, cyan matter, magenta accents) ------------------------------
BG = "#0a0d16"
PANEL = "#111725"
PANEL_HI = "#182136"
LINE = "#26324d"
TEXT = "#e6efff"
MUTED = "#8fa0c2"
DIM = "#5b6886"
ACCENT = "#36d6ff"
ACCENT_HI = "#7ae6ff"
INK = "#04121c"
MAGENTA = "#ff3fa4"
STOP_RED = "#d0455f"

# -- option lists (value, label) ----------------------------------------------------------------
DISPLAY_MODES = [("windowed", "Windowed"), ("borderless", "Borderless"), ("fullscreen", "Fullscreen")]
OUTPUT_RESOLUTIONS = [("1080", "1080p (PS4)"), ("1440", "1440p"), ("2160", "4K (2160p)")]
WINDOW_SIZES = [("auto", "Auto"), ("1280x720", "720p"), ("1600x900", "900p"), ("1920x1080", "1080p"),
                ("2560x1440", "1440p"), ("3840x2160", "4K")]
# Percent of the output resolution (Display tab); the pixel sizes shown are for 1080p output.
RENDER_SCALES = [("console", "PS4 (84%)"), ("50", "50% (fastest)"), ("67", "67%"), ("75", "75%"),
                 ("84", "84%"), ("100", "100% (native)"), ("125", "125%"), ("133", "133%"), ("150", "150%"),
                 ("167", "167%"), ("200", "200% (4K at 1080p output)")]
PRESETS = [("low", "LOW", "Fewer shadows, no reflections, shorter view distance. For integrated graphics."),
           ("medium", "MEDIUM", "A little below the PS4: lighter shadows and effects."),
           ("console", "CONSOLE", "Exactly the PS4 settings (the game's own Blueprint values)."),
           ("high", "HIGH", "Beyond the PS4: sharper, longer shadows, ambient occlusion, better reflections."),
           ("ultra", "ULTRA", "Everything at its highest: 4K shadow maps, full particles, 16x filtering.")]
LEVEL_CHOICES = [("preset", "Preset"), ("low", "Low"), ("medium", "Medium"), ("console", "PS4"),
                 ("high", "High"), ("ultra", "Ultra")]
TOGGLE_CHOICES = {
    "motion_blur": [("console", "PS4 (off)"), ("off", "Off"), ("on", "On"), ("high", "High")],
    "depth_of_field": [("console", "PS4"), ("off", "Off"), ("on", "On"), ("high", "High")],
    "lens_flares": [("console", "PS4 (off)"), ("off", "Off"), ("on", "On")],
    "chromatic_aberration": [("console", "PS4 (off)"), ("off", "Off"), ("on", "On")],
    "eye_adaptation": [("console", "PS4 (off)"), ("off", "Off"), ("on", "On")],
}
GROUP_TEXT = {
    "shadows": ("Shadows", "Shadow quality, shadow map size (up to 4096), cascades and distance."),
    "ambient_occlusion": ("Ambient occlusion", "Soft contact shadows in corners. Off on the PS4; High and Ultra add it."),
    "reflections": ("Screen-space reflections", "Reflections on shiny floors and walls."),
    "view_distance": ("View distance", "How far objects and characters stay drawn."),
    "level_of_detail": ("Level of detail", "How long detailed models are kept as they get farther away."),
    "foliage": ("Foliage", "Density of plants and small scattered meshes."),
    "effects": ("Effects", "Particles (spawn rate), translucent lighting and refraction."),
    "post_process": ("Post-processing", "Bloom, light shafts, upscaling filter and lens effects."),
    "detail": ("Detail", "Small detail meshes and effects (r.DetailMode)."),
    "textures": ("Texture detail", "Mip level of textures; Ultra is sharper than the PS4. The memory budget stays."),
    "anisotropy": ("Texture filtering (engine)", "The engine's anisotropic filtering of textures at an angle."),
}
TOGGLE_TEXT = {
    "motion_blur": ("Motion blur", "Off in the PS4 game."),
    "depth_of_field": ("Depth of field", "Background blur in close-ups and menus."),
    "lens_flares": ("Lens flares", "Off in the PS4 game."),
    "chromatic_aberration": ("Chromatic aberration", "Colour fringes at the screen edges. Off in the PS4 game."),
    "eye_adaptation": ("Eye adaptation", "Automatic exposure. Off in the PS4 game (changes its look)."),
}
ANTI_ALIASING = [("console", "Temporal (PS4)"), ("taa_max", "Temporal, max"), ("taa_fast", "Temporal, fast"),
                 ("fxaa", "FXAA"), ("off", "Off")]
SHARPEN = [("off", "Off"), ("light", "Light"), ("medium", "Medium"), ("strong", "Strong")]
UPSCALE_FILTER = [("console", "PS4 (4-tap)"), ("sharp", "Sharp"), ("smooth", "Smooth")]
ANISOTROPY = [("0", "Game"), ("4", "4x"), ("8", "8x"), ("16", "16x")]
ENGINE_FPS = [("60", "60"), ("120", "120"), ("240", "240")]
FRAME_LIMITS = [("30", "30"), ("60", "60"), ("120", "120"), ("144", "144"), ("165", "165"), ("240", "240"),
                ("half", "Half refresh")]
FRAMES_QUEUED = [("1", "1 (lowest latency)"), ("2", "2"), ("0", "Unlimited")]
PAD_SPEAKER = [("0", "Off"), ("20", "20%"), ("35", "35% (default)"), ("50", "50%"), ("75", "75%"),
               ("100", "100% (full)")]
SPEAKERS = [("auto", "Auto"), ("2", "Stereo"), ("6", "5.1"), ("8", "7.1")]
# PS4 system language codes (sceSystemServiceParamGetInt LANG): the game's text and voices follow it.
LANGUAGES = [("1", "English (US)"), ("18", "English (UK)"), ("2", "Français"), ("4", "Deutsch"),
             ("5", "Italiano"), ("3", "Español"), ("20", "Español (Latinoamérica)"), ("7", "Português"),
             ("17", "Português (Brasil)"), ("6", "Nederlands"), ("16", "Polski"), ("8", "Русский"),
             ("12", "Suomi"), ("13", "Svenska"), ("14", "Dansk"), ("15", "Norsk"), ("19", "Türkçe"),
             ("0", "日本語"), ("9", "한국어"), ("10", "繁體中文"), ("11", "简体中文")]
# As the runtime writes them (mouse_sens=%.2f).
MOUSE_SENSITIVITIES = [("0.50", "0.5x"), ("0.75", "0.75x"), ("1.00", "1x"), ("1.50", "1.5x"), ("2.00", "2x"),
                       ("3.00", "3x")]

# -- controls (runtime_pad.c) -------------------------------------------------------------------
# Action -> up to two bindings "key:<SDL key name>" / "mouse:<left|middle|right|x1|x2|wheel_up|
# wheel_down>". Stick directions take keys only. These are the runtime's own defaults.
CONTROL_GROUPS = (
    ("MOVE (LEFT STICK)", (("ls_up", "Up"), ("ls_down", "Down"), ("ls_left", "Left"), ("ls_right", "Right"))),
    ("AIM AND SHOOT (RIGHT STICK; THE MOUSE MOVES IT TOO)",
     (("rs_up", "Aim up"), ("rs_down", "Aim down"), ("rs_left", "Aim left"), ("rs_right", "Aim right"))),
    ("BUTTONS", (("cross", "Cross"), ("circle", "Circle"), ("square", "Square"), ("triangle", "Triangle"),
                 ("l1", "L1"), ("r1", "R1"), ("l2", "L2"), ("r2", "R2"), ("l3", "L3 (left stick press)"),
                 ("r3", "R3 (right stick press)"), ("options", "Options (pause)"),
                 ("touchpad_left", "Touchpad"), ("up", "D-pad up"), ("down", "D-pad down"),
                 ("left", "D-pad left"), ("right", "D-pad right"))),
)
STICK_ACTIONS = {"ls_up", "ls_down", "ls_left", "ls_right", "rs_up", "rs_down", "rs_left", "rs_right"}
DEFAULT_CONTROLS = {
    "ls_up": ["key:W"], "ls_down": ["key:S"], "ls_left": ["key:A"], "ls_right": ["key:D"],
    "rs_up": ["key:Up"], "rs_down": ["key:Down"], "rs_left": ["key:Left"], "rs_right": ["key:Right"],
    "cross": ["key:Space"], "circle": ["key:Left Ctrl"], "square": ["key:F"], "triangle": ["key:R"],
    "l1": ["key:Q", "mouse:x1"], "r1": ["key:E", "mouse:x2"], "l2": ["mouse:right"], "r2": ["mouse:left"],
    "l3": ["key:Left Shift"], "r3": ["key:V", "mouse:middle"], "options": ["key:Escape", "key:Return"],
    "touchpad_left": ["key:Tab"], "up": ["key:3"], "down": ["key:4"], "left": ["key:1", "mouse:wheel_down"],
    "right": ["key:2", "mouse:wheel_up"],
}
# Controller: the SDL button of each remappable PS4 button (the sticks and triggers are fixed).
PAD_DEFAULTS = {"cross": "a", "circle": "b", "square": "x", "triangle": "y", "l1": "leftshoulder",
                "r1": "rightshoulder", "l3": "leftstick", "r3": "rightstick", "options": "start",
                "up": "dpup", "down": "dpdown", "left": "dpleft", "right": "dpright"}
PAD_BUTTONS = [("a", "Cross / A"), ("b", "Circle / B"), ("x", "Square / X"), ("y", "Triangle / Y"),
               ("leftshoulder", "L1 / LB"), ("rightshoulder", "R1 / RB"), ("leftstick", "L3 / LS"),
               ("rightstick", "R3 / RS"), ("start", "Options / Menu"), ("back", "Share / View"),
               ("dpup", "D-pad up"), ("dpdown", "D-pad down"), ("dpleft", "D-pad left"),
               ("dpright", "D-pad right"), ("misc1", "Mute / Share"), ("paddle1", "Paddle 1"),
               ("paddle2", "Paddle 2"), ("paddle3", "Paddle 3"), ("paddle4", "Paddle 4"), ("", "None")]
MOUSE_LABELS = {"left": "Left mouse", "middle": "Middle mouse", "right": "Right mouse", "x1": "Mouse back",
                "x2": "Mouse forward", "wheel_up": "Wheel up", "wheel_down": "Wheel down"}
TK_TO_SDL = {
    "space": "Space", "Return": "Return", "Escape": "Escape", "Tab": "Tab", "BackSpace": "Backspace",
    "Shift_L": "Left Shift", "Shift_R": "Right Shift", "Control_L": "Left Ctrl", "Control_R": "Right Ctrl",
    "Alt_L": "Left Alt", "Alt_R": "Right Alt", "Caps_Lock": "CapsLock", "Up": "Up", "Down": "Down",
    "Left": "Left", "Right": "Right", "Delete": "Delete", "Home": "Home", "End": "End", "Prior": "PageUp",
    "Next": "PageDown", "minus": "-", "equal": "=", "bracketleft": "[", "bracketright": "]",
    "backslash": "\\", "semicolon": ";", "apostrophe": "'", "grave": "`", "period": ".", "slash": "/",
    "KP_Divide": "Keypad /", "KP_Multiply": "Keypad *", "KP_Subtract": "Keypad -", "KP_Add": "Keypad +",
    "KP_Enter": "Keypad Enter", "KP_Decimal": "Keypad .",
}
TK_TO_SDL.update({f"F{n}": f"F{n}" for n in range(1, 13)})
TK_TO_SDL.update({f"KP_{n}": f"Keypad {n}" for n in range(10)})
RESERVED_KEYS = {"Insert", "F9", "F12"}  # in-game menu, pad recording, screenshot


def parse_map(spec):
    entries = []
    for entry in (spec or "").split(","):
        action, eq, name = entry.partition("=")
        if eq:
            entries.append((action.strip(), name.strip()))
    return entries


def apply_map(bindings, spec, prefix):
    """A runtime map on top of the bindings: an action's first entry replaces its sources of this
    kind, further ones add, "action=" leaves none."""
    replaced = set()
    for action, name in parse_map(spec):
        if action == "touchpad":
            action = "touchpad_left"
        if action not in bindings:
            continue
        if action not in replaced:
            replaced.add(action)
            bindings[action] = [b for b in bindings[action] if not b.startswith(prefix)]
        if name:
            bindings[action].append(prefix + name)


def controls_from_ini(values):
    controls = {action: list(bindings) for action, bindings in DEFAULT_CONTROLS.items()}
    apply_map(controls, values.get("key_map"), "key:")
    apply_map(controls, values.get("mouse_map"), "mouse:")
    pad = dict(PAD_DEFAULTS)
    replaced = set()
    for action, name in parse_map(values.get("pad_map")):
        if action in pad and action not in replaced:
            replaced.add(action)
            pad[action] = name
    return {a: b[:2] for a, b in controls.items()}, pad


def control_maps(controls, pad):
    """key_map, mouse_map and pad_map for the ini (every action listed, so an unbound one loses
    the runtime's default)."""
    keys, mouse = [], []
    for action in DEFAULT_CONTROLS:
        bindings = controls.get(action, [])
        names = [b[4:] for b in bindings if b.startswith("key:")]
        keys += [f"{action}={name}" for name in names] or [f"{action}="]
        if action not in STICK_ACTIONS:
            buttons = [b[6:] for b in bindings if b.startswith("mouse:")]
            mouse += [f"{action}={name}" for name in buttons] or [f"{action}="]
    pads = "" if pad == PAD_DEFAULTS else ",".join(f"{a}={b}" for a, b in pad.items())
    return ",".join(keys), ",".join(mouse), pads


def binding_label(binding):
    if not binding:
        return "—"
    kind, _, name = binding.partition(":")
    return MOUSE_LABELS.get(name, name) if kind == "mouse" else name


# -- game folders -------------------------------------------------------------------------------

def read_sfo(folder):
    try:
        from prepare import sfo
        return sfo((Path(folder) / "sce_sys" / "param.sfo").read_bytes())
    except (OSError, ValueError, ImportError, KeyError):
        return {}


def is_game_dir(folder):
    return bool(folder) and (Path(folder) / "eboot.bin").is_file() and \
        (Path(folder) / "sce_sys" / "param.sfo").is_file()


def find_update(game, chosen):
    if chosen and is_game_dir(chosen):
        return Path(chosen)
    if chosen:
        return None
    for suffix in ("-patch", "-update", "_patch", "_update"):
        candidate = Path(game).with_name(Path(game).name + suffix)
        if is_game_dir(candidate):
            return candidate
    return None


def dark_title_bar(window):
    try:
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        value = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
    except (AttributeError, OSError):
        pass


def desktop_folder():
    try:
        buffer = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buffer) == 0:  # CSIDL_DESKTOPDIRECTORY
            return Path(buffer.value)
    except (AttributeError, OSError):
        pass
    return Path.home() / "Desktop"


def round_rect(canvas, x1, y1, x2, y2, r, **kw):
    points = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2,
              x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(points, smooth=True, **kw)


# -- widgets (the Uncharted launcher's, in Matterfall's colours) --------------------------------

class Toggle(tk.Canvas):
    def __init__(self, parent, scale, value, command):
        self.s = scale
        w, h = int(46 * scale), int(24 * scale)
        super().__init__(parent, width=w, height=h, bg=parent["bg"], highlightthickness=0, cursor="hand2")
        self.w, self.h, self.value, self.command = w, h, bool(value), command
        self.bind("<Button-1>", lambda e: self.set(not self.value, notify=True))
        self.draw()

    def set(self, value, notify=False):
        self.value = bool(value) if not isinstance(value, str) else value == "1"
        self.draw()
        if notify:
            self.command(self.value)

    def draw(self):
        self.delete("all")
        pad = max(1, int(2 * self.s))
        track = ACCENT if self.value else LINE
        round_rect(self, 1, 1, self.w - 1, self.h - 1, self.h // 2, fill=track, outline=track)
        d = self.h - 2 * pad - 2
        x = self.w - pad - d - 1 if self.value else pad + 1
        self.create_oval(x, pad + 1, x + d, pad + 1 + d, fill=INK if self.value else MUTED, outline="")


class Segmented(tk.Frame):
    """A row of choices; the selected one is lit."""

    def __init__(self, parent, options, value, command, font):
        super().__init__(parent, bg=LINE, padx=1, pady=1)
        self.command, self.labels, self.value = command, {}, value
        for i, (option, label) in enumerate(options):
            item = tk.Label(self, text=label, font=font, padx=11, pady=5, cursor="hand2", bd=0)
            item.bind("<Button-1>", lambda e, v=option: self.set(v, notify=True))
            item.bind("<Enter>", lambda e, w=item, v=option: v != self.value and w.config(bg=PANEL_HI))
            item.bind("<Leave>", lambda e: self.restyle())
            item.grid(row=0, column=i, padx=(0 if i == 0 else 1, 0))
            self.labels[option] = item
        self.restyle()

    def set(self, value, notify=False):
        self.value = value
        self.restyle()
        if notify:
            self.command(value)

    def restyle(self):
        for option, item in self.labels.items():
            selected = option == self.value
            item.config(bg=ACCENT if selected else PANEL, fg=INK if selected else TEXT)


class Dropdown(tk.Label):
    """A choice from a longer list: the current one, and a menu of all on click."""

    def __init__(self, parent, options, value, command, font, width=None):
        super().__init__(parent, font=font, bg=PANEL, fg=TEXT, padx=12, pady=5, cursor="hand2", anchor="w",
                         highlightthickness=1, highlightbackground=LINE, width=width or 0)
        self.options, self.command, self.font = options, command, font
        self.set(value)
        self.bind("<Button-1>", lambda e: self.open())
        self.bind("<Enter>", lambda e: self.config(bg=PANEL_HI))
        self.bind("<Leave>", lambda e: self.config(bg=PANEL))

    def set(self, value, notify=False):
        self.value = value
        label = next((label for option, label in self.options if option == value), value)
        self.config(text=f"{label}   ▾")
        if notify:
            self.command(value)

    def open(self):
        menu = tk.Menu(self, tearoff=0, bg=PANEL, fg=TEXT, activebackground=ACCENT, activeforeground=INK,
                       font=self.font, bd=0)
        for option, label in self.options:
            menu.add_command(label=("✓  " if option == self.value else "     ") + label,
                             command=lambda v=option: self.set(v, notify=True))
        menu.tk_popup(self.winfo_rootx(), self.winfo_rooty() + self.winfo_height())


class ScrollBar(tk.Canvas):
    def __init__(self, parent, scale, target):
        super().__init__(parent, width=max(6, int(10 * scale)), bg=parent["bg"], highlightthickness=0)
        self.target, self.first, self.last, self.hover, self.grab = target, 0.0, 1.0, False, None
        self.bind("<Configure>", lambda e: self.draw())
        self.bind("<Enter>", lambda e: self.highlight(True))
        self.bind("<Leave>", lambda e: self.highlight(False))
        self.bind("<Button-1>", self.press)
        self.bind("<B1-Motion>", self.drag)
        self.bind("<ButtonRelease-1>", self.release)

    def set(self, first, last):
        self.first, self.last = float(first), float(last)
        self.draw()

    def highlight(self, hover):
        self.hover = hover
        self.draw()

    def draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if h <= 1 or self.last - self.first >= 1:
            return
        x1, x2, r = 2, w - 2, max(1, (w - 4) // 2)
        round_rect(self, x1, 1, x2, h - 1, r, fill=PANEL, outline=PANEL)
        top = min(int(self.first * h), h - 24)
        bottom = min(h, max(int(self.last * h), top + 24))
        color = MUTED if self.hover or self.grab is not None else DIM
        round_rect(self, x1, top + 1, x2, bottom - 1, r, fill=color, outline=color)

    def press(self, event):
        position = event.y / max(1, self.winfo_height())
        if self.first <= position <= self.last:
            self.grab = position - self.first
        else:
            self.grab = (self.last - self.first) / 2
            self.target.yview_moveto(position - self.grab)

    def drag(self, event):
        if self.grab is not None:
            self.target.yview_moveto(event.y / max(1, self.winfo_height()) - self.grab)

    def release(self, event):
        self.grab = None
        self.draw()


# -- the launcher -------------------------------------------------------------------------------

class Launcher:
    def __init__(self, root, direct=False):
        self.root = root
        self.direct = direct
        self.s = max(1.0, root.winfo_fpixels("1i") / 96.0)
        self.ini = ms.settings(ms.read_ini(INI_FILE))
        self.controls, self.pad = controls_from_ini(self.ini)
        self.process = None
        self.output = queue.Queue()
        self.last_output = 0.0
        self.game_started = False
        self.widgets = {}
        self.images = []
        self.capturing = None
        self.busy = None  # a PKG unpack in progress
        self.fonts()
        root.title(f"{APP_TITLE} - Launcher by BilalReloaded")
        root.configure(bg=BG)
        root.resizable(True, True)
        self.width = self.px(1120)
        self.set_icon()
        self.build()
        root.update_idletasks()
        dark_title_bar(root)
        root.minsize(root.winfo_reqwidth(), min(root.winfo_reqheight(), self.px(640)))
        self.fit_to_screen()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<FocusIn>", lambda e: e.widget is root and self.follow_ini())
        root.after(150, self.poll)
        if UPDATE_REPOSITORY and self.ini.get("check_updates", "1") == "1" and not direct:
            root.after(1500, self.check_updates)
        if direct:
            root.after(100, self.play_direct)

    # -- basics -----------------------------------------------------------------------------

    def px(self, value):
        return int(value * self.s)

    def fonts(self):
        self.f_title = ("Bahnschrift SemiBold", 40)
        self.f_subtitle = ("Bahnschrift", 11)
        self.f_card_title = ("Bahnschrift SemiBold", 15)
        self.f_body = ("Segoe UI", 10)
        self.f_body_bold = ("Segoe UI Semibold", 10)
        self.f_small = ("Segoe UI", 9)
        self.f_tab = ("Segoe UI Semibold", 10)
        self.f_play = ("Bahnschrift SemiBold", 18)

    def game_dir(self):
        folder = self.ini.get("game_dir") or ""
        return Path(folder) if folder else DEFAULT_GAME_DIR

    def update_dir(self):
        return find_update(self.game_dir(), self.ini.get("update_dir") or "")

    def art(self, name):
        """A picture from the player's own game (the update's first): never shipped with the port."""
        if Image is None:
            return None
        for folder in (self.update_dir(), self.game_dir()):
            if folder and (Path(folder) / "sce_sys" / name).is_file():
                try:
                    return Image.open(Path(folder) / "sce_sys" / name).convert("RGBA")
                except OSError:
                    pass
        return None

    def set_icon(self):
        icon = self.art("icon0.png")
        if icon is not None:
            photo = ImageTk.PhotoImage(icon.resize((64, 64), Image.LANCZOS))
            self.images.append(photo)
            self.root.iconphoto(True, photo)

    def fit_to_screen(self):
        spare = self.root.winfo_screenheight() - self.px(110) - self.root.winfo_reqheight()
        if spare > 0:
            self.body.config(height=self.body.winfo_reqheight() + min(spare, self.px(220)))
            self.root.update_idletasks()

    def save(self, updates):
        self.ini.update(updates)
        try:
            ms.write_keys(INI_FILE, updates)
        except OSError as error:
            messagebox.showerror(APP_TITLE, f"Could not save the settings to {INI_FILE}:\n{error}")

    def change(self, key, value):
        if isinstance(value, bool):
            value = "1" if value else "0"
        self.save({key: value})
        if key == "frame_limit":
            # Limits in the runtime's own list are its fps_limit (the in-game menu changes it).
            self.save({"fps_limit": value if value in ms.RUNTIME_LIMITS else "120"})
        if key in ("ue4_render_scale", "fsr1", "window_size", "display_mode", "output_resolution", "ue4_quality",
                   "ue4_shadows"):
            self.refresh_resolution_note()
        if key in ("engine_fps", "frame_limit"):
            self.refresh_fps_note()
        if key.startswith("ue4_") and key != "ue4_quality":
            self.redraw_presets()

    def follow_ini(self):
        """The in-game menu's changes (the runtime saves the same file) shown here too."""
        fresh = ms.settings(ms.read_ini(INI_FILE))
        if fresh == self.ini:
            return
        self.ini = fresh
        for key, widget in self.widgets.items():
            if key in self.ini and hasattr(widget, "set"):
                widget.set(self.ini[key])
        self.controls, self.pad = controls_from_ini(self.ini)
        self.refresh_bindings()
        self.redraw_presets()

    # -- layout -----------------------------------------------------------------------------

    def build(self):
        self.build_hero()
        self.build_card()
        self.build_footer()
        self.build_tabs()
        tab = self.ini.get("launcher_tab", "graphics")
        self.show_tab(tab if tab in self.pages else "graphics", save=False)

    def build_hero(self):
        w, h = self.width, self.px(160)
        canvas = tk.Canvas(self.root, width=w, height=h, bg=BG, highlightthickness=0)
        canvas.pack(side="top")
        art = self.art("pic1.png") or self.art("pic0.png")
        if art is not None:
            art = art.convert("RGB")
            scale = w / art.width
            art = art.resize((w, int(art.height * scale)), Image.LANCZOS)
            top = max(0, int(art.height * 0.30) - h // 2)
            art = art.crop((0, top, w, top + h))
            fade = Image.new("L", (w, h), 0)
            draw = ImageDraw.Draw(fade)
            for x in range(w):  # dark on the left for the title, the art on the right
                draw.line([(x, 0), (x, h)], fill=int(235 * max(0.0, 1 - x / (w * 0.62)) ** 1.2))
            start = int(h * 0.55)
            for y in range(start, h):
                draw.line([(0, y), (w, y)], fill=max(int(255 * ((y - start) / (h - start)) ** 1.6),
                                                     0))
            dark = Image.new("RGB", (w, h), BG)
            art = Image.composite(dark, art, fade)
            photo = ImageTk.PhotoImage(art)
            self.images.append(photo)
            canvas.create_image(0, 0, image=photo, anchor="nw")
            self.hero_photo = photo
        x, y = self.px(44), self.px(58)
        for dx, dy in ((2, 2), (1, 1)):  # a shadow keeps the title readable over the art
            canvas.create_text(x + dx, y + dy, text="MATTERFALL", font=self.f_title, fill="#000000", anchor="w")
            canvas.create_text(x + self.px(3) + dx, y + self.px(40) + dy, text="P C   P O R T   ·   L A U N C H E R",
                               font=self.f_subtitle, fill="#000000", anchor="w")
        canvas.create_text(x, y, text="MATTERFALL", font=self.f_title, fill=TEXT, anchor="w")
        canvas.create_text(x + self.px(3), y + self.px(40), text="P C   P O R T   ·   L A U N C H E R",
                           font=self.f_subtitle, fill=ACCENT, anchor="w")
        canvas.create_line(x + self.px(3), y + self.px(60), x + self.px(300), y + self.px(60), fill=MAGENTA, width=2)
        self.draw_links(canvas, w)

    def draw_links(self, canvas, width):
        right, top, height = width - self.px(22), self.px(18), self.px(30)
        for label, url, color, hover in reversed(LINKS):
            tag = f"link-{label}"
            text = canvas.create_text(0, 0, text=label, font=self.f_body_bold, fill="white", anchor="w", tags=tag)
            x1, _, x2, _ = canvas.bbox(text)
            left = right - (x2 - x1) - self.px(28)
            mid = top + height // 2
            canvas.coords(text, left + self.px(14), mid)
            badge = round_rect(canvas, left, top, right, top + height, height // 2, fill=color, outline=color, tags=tag)
            canvas.tag_lower(badge, text)
            canvas.tag_bind(tag, "<Button-1>", lambda e, u=url: webbrowser.open(u))
            canvas.tag_bind(tag, "<Enter>", lambda e, b=badge, c=hover: (canvas.itemconfig(b, fill=c, outline=c),
                                                                       canvas.config(cursor="hand2")))
            canvas.tag_bind(tag, "<Leave>", lambda e, b=badge, c=color: (canvas.itemconfig(b, fill=c, outline=c),
                                                                       canvas.config(cursor="")))
            right = left - self.px(10)

    def build_card(self):
        """The game: its icon, version and folders. Double-click plays."""
        frame = tk.Frame(self.root, bg=BG)
        frame.pack(side="top", fill="x", padx=self.px(40), pady=(0, self.px(12)))
        self.card = tk.Canvas(frame, width=self.width - 2 * self.px(40), height=self.px(84), bg=BG,
                              highlightthickness=0, cursor="hand2")
        self.card.pack(side="left")
        self.card.bind("<Double-Button-1>", lambda e: self.play_or_stop())
        self.card.bind("<Button-1>", lambda e: None if is_game_dir(self.game_dir()) else self.choose_game_dir())
        self.draw_card()

    def draw_card(self):
        c = self.card
        w, h = int(c["width"]), int(c["height"])
        c.delete("all")
        round_rect(c, 2, 2, w - 2, h - 2, self.px(10), fill=PANEL_HI, outline=ACCENT, width=2)
        icon = self.art("icon0.png")
        x = self.px(18)
        if icon is not None:
            size = h - self.px(18)
            photo = ImageTk.PhotoImage(icon.resize((size, size), Image.LANCZOS))
            self.card_photo = photo
            c.create_image(x, h // 2, image=photo, anchor="w")
            x += size + self.px(16)
        game = self.game_dir()
        update = self.update_dir()
        c.create_text(x, h // 2 - self.px(14), text="Matterfall", font=self.f_card_title, fill=TEXT, anchor="w")
        if is_game_dir(game):
            base = read_sfo(game)
            version = read_sfo(update).get("APP_VER") if update else base.get("APP_VER", base.get("VERSION"))
            line = (f"{base.get('TITLE_ID', '?')}  ·  version {(version or '?').lstrip('0')}"
                    f"{'  ·  update ' + str(update) if update else '  ·  no update found (1.01 recommended)'}")
            if base.get("TITLE_ID") not in (None, TITLE_ID):
                line = f"This folder holds {base.get('TITLE_ID')}, not Matterfall ({TITLE_ID})."
        else:
            line = "No game folder yet: click here (or Advanced → Game folder) to choose it, or install from a PKG."
        c.create_text(x + self.px(1), h // 2 + self.px(12), text=line, font=self.f_small, fill=MUTED, anchor="w")
        c.create_text(w - self.px(18), self.px(16), text="PS4 · UNREAL ENGINE 4.13", font=("Segoe UI Semibold", 7),
                      fill=ACCENT, anchor="e")

    def build_tabs(self):
        outer = tk.Frame(self.root, bg=BG)
        outer.pack(side="top", fill="both", expand=True, padx=self.px(40))
        strip = tk.Frame(outer, bg=BG)
        strip.pack(side="top", fill="x")
        self.tab_buttons = {}
        tabs = [("graphics", "GRAPHICS"), ("display", "DISPLAY"), ("performance", "PERFORMANCE"),
                ("controls", "CONTROLS"), ("audio", "AUDIO"), ("advanced", "ADVANCED")]
        for name, label in tabs:
            cell = tk.Frame(strip, bg=BG)
            cell.pack(side="left", padx=(0, self.px(26)))
            text = tk.Label(cell, text=label, font=self.f_tab, bg=BG, fg=MUTED, cursor="hand2")
            text.pack(side="top", pady=(0, self.px(6)))
            bar = tk.Frame(cell, bg=BG, height=max(2, self.px(2)))
            bar.pack(side="top", fill="x")
            for widget in (cell, text):
                widget.bind("<Button-1>", lambda e, n=name: self.show_tab(n))
            self.tab_buttons[name] = (text, bar)
        tk.Frame(outer, bg=LINE, height=1).pack(side="top", fill="x")
        self.body = tk.Frame(outer, bg=BG, height=self.px(330))
        self.body.pack(side="top", fill="both", expand=True, pady=(self.px(14), 0))
        self.body.pack_propagate(False)
        self.scroll_canvases = set()
        self.root.bind_all("<MouseWheel>", self.wheel)
        self.pages = {"graphics": self.page_graphics(), "display": self.page_display(),
                      "performance": self.page_performance(), "controls": self.page_controls(),
                      "audio": self.page_audio(), "advanced": self.page_advanced()}

    def show_tab(self, name, save=True):
        self.current_tab = name
        if save:
            self.save({"launcher_tab": name})
        for tab, (text, bar) in self.tab_buttons.items():
            text.config(fg=TEXT if tab == name else MUTED)
            bar.config(bg=ACCENT if tab == name else BG)
        for tab, page in self.pages.items():
            if tab == name:
                page.holder.pack(fill="both", expand=True)
            else:
                page.holder.pack_forget()

    def wheel(self, event):
        if self.capturing is not None:
            return
        try:
            widget = self.root.winfo_containing(event.x_root, event.y_root)
        except (KeyError, tk.TclError):
            return
        while widget is not None:
            if str(widget) in self.scroll_canvases:
                if tuple(widget.yview()) != (0.0, 1.0):
                    step = int(-event.delta / 120) or (-1 if event.delta > 0 else 1)
                    widget.yview_scroll(step, "units")
                return
            widget = widget.master

    def page(self):
        holder = tk.Frame(self.body, bg=BG)
        canvas = tk.Canvas(holder, bg=BG, highlightthickness=0)
        bar = ScrollBar(holder, self.s, canvas)
        inner = tk.Frame(canvas, bg=BG)
        window = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side="left", fill="both", expand=True)

        def layout(event=None):
            width, height, need = canvas.winfo_width(), canvas.winfo_height(), inner.winfo_reqheight()
            if height <= 1:
                return
            canvas.itemconfigure(window, width=width)
            canvas.configure(scrollregion=(0, 0, width, max(need, height)))
            if need > height and not bar.winfo_manager():
                bar.pack(side="right", fill="y", padx=(self.px(8), 0), before=canvas)
            elif need <= height and bar.winfo_manager():
                bar.pack_forget()
                canvas.yview_moveto(0)
        inner.bind("<Configure>", layout)
        canvas.bind("<Configure>", layout)
        self.scroll_canvases.add(str(canvas))
        inner.holder = holder
        return inner

    def section(self, page, title, note=None):
        tk.Label(page, text=title, font=self.f_small, bg=BG, fg=ACCENT, anchor="w").pack(
            side="top", fill="x", pady=(self.px(10), self.px(4)))
        if note:
            tk.Label(page, text=note, font=self.f_small, bg=BG, fg=DIM, anchor="w", justify="left",
                     wraplength=self.width - self.px(120)).pack(side="top", fill="x", pady=(0, self.px(6)))

    def row(self, page, title, hint, factory):
        row = tk.Frame(page, bg=BG)
        row.pack(side="top", fill="x", pady=(0, self.px(10)))
        text = tk.Frame(row, bg=BG)
        text.pack(side="left", fill="x", expand=True)
        tk.Label(text, text=title, font=self.f_body_bold, bg=BG, fg=TEXT, anchor="w").pack(side="top", fill="x")
        hint_label = None
        if hint is not None:
            hint_label = tk.Label(text, text=hint, font=self.f_small, bg=BG, fg=MUTED, anchor="w", justify="left",
                                  wraplength=self.px(520))
            hint_label.pack(side="top", fill="x")
        control = factory(row)
        control.pack(side="right", padx=(self.px(20), 0))
        control.hint = hint_label
        return control

    def toggle(self, page, key, title, hint):
        self.widgets[key] = self.row(page, title, hint, lambda p: Toggle(
            p, self.s, self.ini.get(key, "0") == "1", lambda v, k=key: self.change(k, v)))
        return self.widgets[key]

    def choice(self, page, key, title, hint, options, dropdown=False):
        def factory(parent):
            cls = Dropdown if dropdown else Segmented
            return cls(parent, options, self.ini.get(key, ms.DEFAULTS.get(key)), lambda v, k=key: self.change(k, v),
                       self.f_small)
        self.widgets[key] = self.row(page, title, hint, factory)
        return self.widgets[key]

    def flat_button(self, parent, label, action):
        button = tk.Label(parent, text=label, font=self.f_small, bg=PANEL, fg=TEXT, padx=self.px(12), pady=self.px(6),
                          cursor="hand2", highlightthickness=1, highlightbackground=LINE)
        button.bind("<Button-1>", lambda e: action())
        button.bind("<Enter>", lambda e: button.config(bg=PANEL_HI))
        button.bind("<Leave>", lambda e: button.config(bg=PANEL))
        return button

    def buttons(self, page, title, actions, note=""):
        self.section(page, title)
        line = tk.Frame(page, bg=BG)
        line.pack(side="top", fill="x")
        for label, action in actions:
            self.flat_button(line, label, action).pack(side="left", padx=(0, self.px(10)))
        if note:
            tk.Label(line, text=note, font=self.f_small, bg=BG, fg=MUTED, anchor="w").pack(side="left", padx=(self.px(6), 0))
        return line

    # -- graphics ---------------------------------------------------------------------------

    def page_graphics(self):
        page = self.page()
        self.section(page, "QUALITY PRESET", "Unreal Engine settings, written into a small config pak at every "
                     "start (the game's own files are not changed). Single settings below override the preset.")
        grid = tk.Frame(page, bg=BG)
        grid.pack(side="top", fill="x")
        self.preset_cards = {}
        gap = self.px(12)
        card_w = (self.width - 2 * self.px(40) - self.px(24) - 4 * gap) // 5
        card_h = self.px(118)
        for i, (name, title, text) in enumerate(PRESETS):
            canvas = tk.Canvas(grid, width=card_w, height=card_h, bg=BG, highlightthickness=0, cursor="hand2")
            canvas.grid(row=0, column=i, padx=(0 if i == 0 else gap, 0))
            canvas.bind("<Button-1>", lambda e, n=name: self.apply_preset(n))
            canvas.bind("<Enter>", lambda e, n=name: self.draw_preset(n, hover=True))
            canvas.bind("<Leave>", lambda e, n=name: self.draw_preset(n))
            self.preset_cards[name] = (canvas, card_w, card_h, title, text)
        self.custom_note = tk.Label(page, text="", font=self.f_small, bg=BG, fg=MUTED, anchor="w")
        self.custom_note.pack(side="top", fill="x", pady=(self.px(6), 0))
        self.root.after_idle(self.redraw_presets)

        self.section(page, "RESOLUTION")
        self.choice(page, "ue4_render_scale", "Render resolution",
                    "The 3D scene's size as a percentage of the output resolution (Display tab). The PS4 draws "
                    "84%. Above 100% the scene is drawn larger and scaled down (supersampling: 200% of 1080p "
                    "renders 4K). For a 4K screen, 4K output at 100% is sharper than 1080p at 200%.", RENDER_SCALES, dropdown=True)
        self.choice(page, "ue4_anti_aliasing", "Anti-aliasing",
                    "The game's temporal AA smooths edges but softens a little in motion. Max is steadier; FXAA "
                    "is sharper; Off shows raw pixels (best with a high render resolution).", ANTI_ALIASING)
        self.choice(page, "ue4_upscale_filter", "Upscaling filter",
                    "How a render resolution below 100% is enlarged to 1080p (r.Upscale.Quality).", UPSCALE_FILTER)
        self.choice(page, "ue4_sharpen", "Sharpening (tonemapper)",
                    "The engine's own sharpening of the final picture (r.Tonemapper.Sharpen; off on the PS4).", SHARPEN)
        self.section(page, "SINGLE SETTINGS", "Preset = the level of the quality preset above. PS4 = exactly as "
                     "on the console.")
        for group, (title, hint) in GROUP_TEXT.items():
            self.choice(page, f"ue4_{group}", title, hint, LEVEL_CHOICES, dropdown=True)
        for toggle, (title, hint) in TOGGLE_TEXT.items():
            self.choice(page, f"ue4_{toggle}", title, hint, TOGGLE_CHOICES[toggle], dropdown=True)
        self.section(page, "NOT AVAILABLE FOR THIS GAME",
                     "FSR 3.1, FSR 4 and DLSS upscaling need the game's motion vectors, which the runtime only "
                     "knows for Uncharted; Unreal's own temporal upsampling arrived in a later engine (4.19). "
                     "Material quality stays at the PS4's (the game ships shaders for that level only). Other "
                     "aspect ratios than 16:9: the game's camera and HUD are made for 16:9.")
        return page

    def draw_preset(self, name, hover=False):
        canvas, w, h, title, text = self.preset_cards[name]
        selected = self.ini.get("ue4_quality", "console") == name
        canvas.delete("all")
        fill = PANEL_HI if selected or hover else PANEL
        outline = ACCENT if selected else ("#3b4a6e" if hover else LINE)
        round_rect(canvas, 2, 2, w - 2, h - 2, self.px(10), fill=fill, outline=outline, width=2 if selected else 1)
        canvas.create_text(self.px(14), self.px(22), text=title, font=self.f_card_title,
                           fill=ACCENT if selected else TEXT, anchor="w")
        canvas.create_text(self.px(14), self.px(44), text=text, font=self.f_small, fill=MUTED, anchor="nw",
                           width=w - self.px(26))
        if name == "console":
            canvas.create_text(w - self.px(12), self.px(22), text="PS4", font=("Segoe UI Semibold", 7),
                               fill=MAGENTA, anchor="e")

    def redraw_presets(self):
        if not getattr(self, "preset_cards", None):
            return
        for name in self.preset_cards:
            self.draw_preset(name)
        custom = [GROUP_TEXT[g][0] for g in ue4_override.GROUP_NAMES if self.ini.get(f"ue4_{g}", "preset") != "preset"]
        custom += [TOGGLE_TEXT[t][0] for t in ue4_override.TOGGLES if self.ini.get(f"ue4_{t}", "console") != "console"]
        self.custom_note.config(text=("Changed from the preset: " + ", ".join(custom)) if custom else
                                "All single settings follow the preset.")

    def apply_preset(self, name):
        updates = {"ue4_quality": name}
        updates.update({f"ue4_{g}": "preset" for g in ue4_override.GROUP_NAMES})
        updates.update({f"ue4_{t}": "console" for t in ue4_override.TOGGLES})
        self.save(updates)
        for key, value in updates.items():
            if key in self.widgets:
                self.widgets[key].set(value)
        self.redraw_presets()
        self.refresh_resolution_note()

    # -- display ----------------------------------------------------------------------------

    def page_display(self):
        page = self.page()
        self.section(page, "WINDOW")
        self.choice(page, "display_mode", "Display mode",
                    "Borderless covers the screen at the desktop resolution without changing the display mode. "
                    "Alt+Enter and the in-game menu (Insert) switch it too.", DISPLAY_MODES)
        self.choice(page, "output_resolution", "Output resolution",
                    "The size the game itself outputs: menus, HUD and the 3D scene at that resolution (the PS4 "
                    "Pro's own 4K mode, unlocked). Render resolution (Graphics) scales the 3D scene within it. "
                    "1440p and 4K need more graphics memory and GPU power.", OUTPUT_RESOLUTIONS)
        self.choice(page, "window_size", "Window size (windowed)",
                    "The window's size and place (centred). The game's output is scaled to the window or screen.",
                    WINDOW_SIZES)
        self.resolution_note = tk.Label(page, text="", font=self.f_small, bg=BG, fg=ACCENT, anchor="w",
                                        justify="left", wraplength=self.width - self.px(120))
        self.resolution_note.pack(side="top", fill="x", pady=(0, self.px(8)))
        self.toggle(page, "vsync", "VSync", "Waits for the monitor: no tearing. Off allows tearing for the lowest latency.")
        self.section(page, "SCALING TO THE SCREEN")
        self.toggle(page, "fsr1", "Upscale with FSR 1",
                    "Enlarges the game's output to a larger window or screen with AMD FSR 1 instead of plain "
                    "filtering (for example 1080p output on a 4K screen).")
        self.toggle(page, "rcas", "Sharpening (RCAS)", "AMD's contrast-adaptive sharpening of the shown picture.")
        self.choice(page, "rcas_strength", "Sharpening strength", None,
                    [("25", "25%"), ("50", "50%"), ("75", "75%"), ("100", "100%")])
        self.section(page, "OVERLAY")
        self.toggle(page, "show_fps", "FPS counter",
                    "The performance overlay in a corner (items, size and corner: in-game menu, Insert or R3 + L2).")
        self.refresh_resolution_note()
        return page

    def refresh_resolution_note(self):
        if not hasattr(self, "resolution_note"):
            return
        scale = self.ini.get("ue4_render_scale", "console")
        label = dict(RENDER_SCALES).get(scale, scale)
        mode = self.ini.get("display_mode", "windowed")
        size = self.ini.get("window_size", "auto")
        shown = {"windowed": f"a {dict(WINDOW_SIZES).get(size, size)} window" if size != "auto" else "a window",
                 "borderless": "the whole screen (borderless)", "fullscreen": "the whole screen (fullscreen)"}[
            mode if mode in ("windowed", "borderless", "fullscreen") else "windowed"]
        fsr = " with FSR 1" if self.ini.get("fsr1") == "1" else ""
        output = dict(OUTPUT_RESOLUTIONS).get(self.ini.get("output_resolution", "1080"), "1080p")
        used = ms.render_scale(ms.settings(self.ini))
        if used != scale:
            # The scene would not fit the game's graphics memory (matterfall_settings.render_scale).
            label = (f"{dict(RENDER_SCALES).get(used, used)} (limited: {dict(RENDER_SCALES).get(scale, scale)} "
                     f"does not fit the game's graphics memory at this output and quality)")
        self.resolution_note.config(text=f"Now: the 3D scene at {label} of {output}, shown on {shown}{fsr}.")

    # -- performance ------------------------------------------------------------------------

    def page_performance(self):
        page = self.page()
        self.section(page, "FRAME RATE")
        self.choice(page, "engine_fps", "Engine frame rate",
                    "The highest frame rate the game runs at. 60 is the PS4 original and recommended. 120 and "
                    "240 are experimental: they lift the engine's 60 FPS cap, but game speed, physics or "
                    "cutscenes may misbehave. Applied at start.", ENGINE_FPS)
        self.choice(page, "frame_limit", "Frame rate limit",
                    "Caps the frame rate below the engine frame rate. \"Half refresh\" shows every frame for "
                    "exactly two refreshes of your screen (72 FPS on 144 Hz): smooth, with engine 120.", FRAME_LIMITS)
        self.fps_note = tk.Label(page, text="", font=self.f_small, bg=BG, fg=ACCENT, anchor="w", justify="left",
                                 wraplength=self.width - self.px(120))
        self.fps_note.pack(side="top", fill="x", pady=(0, self.px(8)))
        self.choice(page, "frames_queued", "Frames queued",
                    "1 is the lowest input latency; more can raise the frame rate when the graphics card is the limit.",
                    FRAMES_QUEUED)
        self.section(page, "SHADERS")
        self.toggle(page, "async_shaders", "Compile new shaders in the background",
                    "Fewer stutters in new areas: the game keeps running while shaders compile, an effect may "
                    "appear a moment later. Switch it off if something stays missing.")
        self.toggle(page, "warmup_while_playing", "Load the shader cache while the game starts",
                    "Off (default): saved shaders load before the game starts (a few seconds of loading "
                    "screen). On: the game starts at once and they load in the background, which crashed "
                    "on some PCs.")
        self.toggle(page, "parallel_warmup", "Fast shader cache loading", "Builds cached pipelines on several CPU threads.")
        self.toggle(page, "pipeline_binaries", "Pipeline binary cache",
                    "Reuses compiled Vulkan pipelines between sessions: faster loading, but each kept "
                    "pipeline holds about 2 MB of memory (Uncharted 2 used twice the RAM). Off by default.")
        self.section(page, "DIAGNOSTICS")
        self.toggle(page, "perf_log", "Performance log", "Frame rate and frame time statistics in the log every 5 "
                                                        "seconds; helps when you report a problem.")
        self.refresh_fps_note()
        return page

    def refresh_fps_note(self):
        if not hasattr(self, "fps_note"):
            return
        fps = ms.engine_fps(self.ini)
        _ini, _fixed, limit = ms.frame_limit(self.ini)
        refresh = ms.display_refresh_hz()
        if fps == 60:
            text = f"Now: at most 60 FPS (the PS4's), limit {limit}. Your display: {refresh} Hz."
        else:
            text = (f"Now: up to {fps} FPS (experimental), limit {limit}. Your display: {refresh} Hz; with VSync "
                    f"on, frames beyond {refresh} FPS are not shown.")
        self.fps_note.config(text=text)

    # -- controls ---------------------------------------------------------------------------

    def page_controls(self):
        page = self.page()
        self.section(page, "MOUSE AND CONTROLLER")
        self.toggle(page, "mouse", "Mouse aims", "The mouse moves the right stick (aim and shoot).")
        self.choice(page, "mouse_sens", "Mouse sensitivity", None, MOUSE_SENSITIVITIES)
        self.toggle(page, "mouse_invert", "Invert mouse up/down", None)
        self.toggle(page, "vibration", "Controller vibration", None)
        self.section(page, "KEYBOARD AND MOUSE",
                     "Click a slot, then press a key or mouse button. Right-click a slot to clear it. Insert opens "
                     "the in-game menu, F12 takes a screenshot (both fixed). Stick directions take keys only.")
        self.binding_slots = {}
        self.pad_widgets = {}
        table = tk.Frame(page, bg=BG)
        table.pack(side="top", fill="x")
        row = 0
        for title, actions in CONTROL_GROUPS:
            tk.Label(table, text=title, font=("Segoe UI Semibold", 8), bg=BG, fg=DIM, anchor="w").grid(
                row=row, column=0, columnspan=4, sticky="w", pady=(self.px(8), self.px(2)))
            row += 1
            for action, label in actions:
                tk.Label(table, text=label, font=self.f_body, bg=BG, fg=TEXT, anchor="w", width=24).grid(
                    row=row, column=0, sticky="w")
                for slot in (0, 1):
                    cell = tk.Label(table, text="", font=self.f_small, bg=PANEL, fg=TEXT, width=16, pady=self.px(3),
                                    cursor="hand2", highlightthickness=1, highlightbackground=LINE)
                    cell.grid(row=row, column=1 + slot, padx=(self.px(8), 0), pady=1, sticky="w")
                    cell.bind("<Button-1>", lambda e, a=action, s=slot: self.start_capture(a, s))
                    cell.bind("<Button-3>", lambda e, a=action, s=slot: self.set_binding(a, s, None))
                    self.binding_slots[(action, slot)] = cell
                if action in PAD_DEFAULTS:
                    pad = Dropdown(table, PAD_BUTTONS, self.pad.get(action, ""),
                                   lambda v, a=action: self.set_pad(a, v), self.f_small, width=16)
                    pad.grid(row=row, column=3, padx=(self.px(16), 0), pady=1, sticky="w")
                    self.pad_widgets[action] = pad
                elif action in ("l2", "r2") or action in STICK_ACTIONS:
                    tk.Label(table, text="controller: fixed", font=self.f_small, bg=BG, fg=DIM).grid(
                        row=row, column=3, padx=(self.px(16), 0), sticky="w")
                row += 1
        tk.Label(table, text="KEYBOARD / MOUSE", font=("Segoe UI Semibold", 7), bg=BG, fg=DIM).grid(
            row=0, column=1, columnspan=2)
        tk.Label(table, text="CONTROLLER", font=("Segoe UI Semibold", 7), bg=BG, fg=DIM).grid(
            row=0, column=3, padx=(self.px(16), 0))
        self.buttons(page, "", (("Reset controls", self.reset_controls),))
        self.refresh_bindings()
        return page

    def refresh_bindings(self):
        if not getattr(self, "binding_slots", None):
            return
        for (action, slot), cell in self.binding_slots.items():
            bindings = self.controls.get(action, [])
            cell.config(text=binding_label(bindings[slot] if slot < len(bindings) else None), bg=PANEL)
        for action, widget in self.pad_widgets.items():
            widget.set(self.pad.get(action, ""))

    def save_controls(self):
        keys, mouse, pads = control_maps(self.controls, self.pad)
        self.save({"key_map": keys, "mouse_map": mouse, "pad_map": pads})

    def start_capture(self, action, slot):
        self.stop_capture()
        self.capturing = (action, slot)
        self.binding_slots[(action, slot)].config(text="press a key…", bg=PANEL_HI)
        self.root.bind_all("<KeyPress>", self.capture_key)
        # The click that armed the capture is not the binding.
        self.root.after(250, lambda: self.capturing == (action, slot) and (
            self.root.bind_all("<ButtonPress>", self.capture_button),
            self.root.bind_all("<MouseWheel>", self.capture_wheel)))

    def stop_capture(self):
        self.capturing = None
        self.root.unbind_all("<KeyPress>")
        self.root.unbind_all("<ButtonPress>")
        self.root.bind_all("<MouseWheel>", self.wheel)
        self.refresh_bindings()

    def capture_key(self, event):
        if not self.capturing:
            return
        name = TK_TO_SDL.get(event.keysym)
        if name is None and len(event.keysym) == 1 and event.keysym.isalnum():
            name = event.keysym.upper()
        if name is None or event.keysym in RESERVED_KEYS:
            return "break"
        action, slot = self.capturing
        self.set_binding(action, slot, f"key:{name}")
        return "break"

    def capture_button(self, event):
        if not self.capturing:
            return
        action, slot = self.capturing
        if action in STICK_ACTIONS:
            return "break"
        name = {1: "left", 2: "middle", 3: "right", 4: "x1", 5: "x2"}.get(event.num)
        if name:
            self.set_binding(action, slot, f"mouse:{name}")
        return "break"

    def capture_wheel(self, event):
        if not self.capturing:
            return
        action, slot = self.capturing
        if action not in STICK_ACTIONS:
            self.set_binding(action, slot, "mouse:wheel_up" if event.delta > 0 else "mouse:wheel_down")
        return "break"

    def set_binding(self, action, slot, binding):
        bindings = list(self.controls.get(action, []))
        while len(bindings) <= slot:
            bindings.append(None)
        bindings[slot] = binding
        # The same input is not bound twice.
        if binding:
            for other, others in self.controls.items():
                if other != action and binding in others:
                    self.controls[other] = [b for b in others if b != binding]
        self.controls[action] = [b for b in bindings if b][:2]
        self.stop_capture()
        self.save_controls()

    def set_pad(self, action, button):
        self.pad[action] = button
        self.save_controls()

    def reset_controls(self):
        if not messagebox.askyesno(APP_TITLE, "Set all keyboard, mouse and controller bindings back to the defaults?"):
            return
        self.controls = {a: list(b) for a, b in DEFAULT_CONTROLS.items()}
        self.pad = dict(PAD_DEFAULTS)
        self.save({"key_map": "", "mouse_map": "", "pad_map": ""})
        self.refresh_bindings()

    # -- audio ------------------------------------------------------------------------------

    def page_audio(self):
        page = self.page()
        self.section(page, "SOUND")
        self.choice(page, "speakers", "Speakers",
                    "The game's own stereo, 5.1 or 7.1 mix. Auto matches your Windows sound output.", SPEAKERS)
        self.choice(page, "pad_speaker_volume", "Controller speaker sounds",
                    "Short voice lines the PS4 plays on the controller's own speaker (multiplier up/lost, "
                    "health low). Here they play on your speakers; this sets their volume.", PAD_SPEAKER)
        self.section(page, "LANGUAGE")
        self.choice(page, "language", "Game language",
                    "The console language the game sees: its menus, subtitles and voices follow it (when the "
                    "game has that language).", LANGUAGES, dropdown=True)
        return page

    # -- advanced ---------------------------------------------------------------------------

    def page_advanced(self):
        page = self.page()
        self.section(page, "TEXTURES")
        self.choice(page, "anisotropy", "Texture filtering (forced)",
                    "Forces anisotropic filtering on the game's textures in the graphics driver layer (sharper "
                    "floors and walls at an angle; costs almost nothing). Game = as on the PS4.", ANISOTROPY)
        self.buttons(page, "GAME", (("Game folder", self.choose_game_dir), ("Update folder", self.choose_update_dir),
                                    ("Install from PKG", self.install_pkg)),
                     "The game is never copied: the port reads it where it is.")
        self.folder_label = tk.Label(page, text="", font=self.f_small, bg=BG, fg=DIM, anchor="w", justify="left")
        self.folder_label.pack(side="top", fill="x", pady=(self.px(6), 0))
        self.buttons(page, "FOLDERS", (("Open log folder", lambda: self.open_path(OUT_DIR)),
                                       ("Open saves folder", lambda: self.open_path(USER_DIR / "savedata")),
                                       ("Open settings file", lambda: self.open_path(INI_FILE))))
        line = self.buttons(page, "SAVE BACKUPS", (("Restore backup", self.restore_backup),),
                            "A backup of your saves is made before every start (the last 10 are kept).")
        self.backup_choice = Dropdown(line, [("", "No backups yet")], "", lambda v: None, self.f_small)
        self.backup_choice.pack(side="left", padx=(self.px(10), 0), before=line.winfo_children()[0])
        self.refresh_backups()
        self.buttons(page, "SHORTCUTS AND CACHES", (("Desktop shortcut", self.desktop_shortcut),
                                                    ("Reset shader cache", self.clear_cache),
                                                    ("Reset all settings", self.reset_settings)))
        version = (ROOT / "VERSION").read_text(encoding="ascii", errors="replace").strip() \
            if (ROOT / "VERSION").is_file() else "source tree"
        self.section(page, "VERSION", f"Port version: {version}. Settings: {INI_FILE}. Runtime: "
                     f"{ROOT / 'gow3_pc' / 'out' / 'gow3-probe.exe'}.")
        self.refresh_folders()
        return page

    def refresh_folders(self):
        game, update = self.game_dir(), self.update_dir()
        text = f"Game: {game if is_game_dir(game) else '(not chosen)'}\nUpdate: {update or '(none found)'}"
        if hasattr(self, "folder_label"):
            self.folder_label.config(text=text)
        self.draw_card()

    def choose_game_dir(self):
        folder = filedialog.askdirectory(title="Select the Matterfall game folder (CUSA02475, with eboot.bin)",
                                         initialdir=str(self.game_dir() if self.game_dir().exists() else ROOT))
        if not folder:
            return False
        if not is_game_dir(folder):
            messagebox.showerror(APP_TITLE, "That folder has no eboot.bin and sce_sys\\param.sfo.\n\nChoose the "
                                            "unpacked game folder (CUSA02475), or use Install from PKG.")
            return False
        title = read_sfo(folder).get("TITLE_ID")
        if title and title != TITLE_ID and not messagebox.askyesno(
                APP_TITLE, f"This is {title}, not Matterfall ({TITLE_ID}). Use it anyway?"):
            return False
        if read_sfo(folder).get("CATEGORY") == "gp":
            messagebox.showinfo(APP_TITLE, "That is the game update, not the game. It is used as the update folder; "
                                           "choose the game folder too.")
            self.save({"update_dir": folder})
            self.refresh_folders()
            return False
        self.save({"game_dir": folder})
        self.refresh_folders()
        return True

    def choose_update_dir(self):
        folder = filedialog.askdirectory(title="Select the Matterfall update folder (1.01, with eboot.bin)",
                                         initialdir=str(self.game_dir().parent if self.game_dir().exists() else ROOT))
        if not folder:
            return
        if not is_game_dir(folder):
            if messagebox.askyesno(APP_TITLE, "That folder has no eboot.bin. Use no fixed update folder (the "
                                              "launcher then looks for <game folder>-patch)?"):
                self.save({"update_dir": ""})
                self.refresh_folders()
            return
        self.save({"update_dir": folder})
        self.refresh_folders()

    def install_pkg(self):
        if self.busy or self.process:
            messagebox.showinfo(APP_TITLE, "Wait until the game or the current unpack has finished.")
            return
        try:
            import pkg_extract
        except ImportError as error:
            messagebox.showerror(APP_TITLE, "Unpacking a PKG needs the Python package 'cryptography', which is "
                                            f"not available here ({error}).\n\nUnpack the PKG with another tool, "
                                            "or install it: python -m pip install cryptography")
            return
        path = filedialog.askopenfilename(title="Select the Matterfall game or update PKG (fake PKG)",
                                          filetypes=[("PS4 package", "*.pkg"), ("All files", "*.*")])
        if not path:
            return
        try:
            pkg = pkg_extract.Pkg(path)
            sfo = {}
            for entry in pkg.entries:
                if entry["id"] == 0x1000:
                    sfo = pkg_extract.parse_sfo(pkg.entry_data(entry))
        except (OSError, ValueError, KeyError) as error:
            messagebox.showerror(APP_TITLE, f"Not a PKG this launcher can read:\n{error}")
            return
        title = sfo.get("TITLE_ID") or (pkg.content_id.split("-")[1].split("_")[0] if "-" in pkg.content_id else "game")
        update = sfo.get("CATEGORY") == "gp"
        if update and is_game_dir(self.game_dir()):
            target = self.game_dir().with_name(self.game_dir().name + "-patch")
        else:
            target = Path(path).resolve().parent / (title + ("-patch" if update else ""))
        if title != TITLE_ID and not messagebox.askyesno(APP_TITLE, f"This PKG is {title}, not Matterfall. Unpack anyway?"):
            return
        if not messagebox.askokcancel(APP_TITLE, f"Unpack the {'update ' + str(sfo.get('APP_VER', '')) if update else 'game'} "
                                                 f"into:\n{target}\n\nIt needs about {pkg.pfs_size / 1e9:.1f} GB of free "
                                                 "space and takes a few minutes. It can be resumed if stopped."):
            return
        self.busy = {"done": 0, "total": 1, "error": None, "finished": False}

        def report(done, total, rate):
            self.busy.update(done=done, total=total, rate=rate)

        def work():
            try:
                pkg_extract.extract(path, str(target), report)
            except Exception as error:  # shown to the player
                self.busy["error"] = str(error) or error.__class__.__name__
            self.busy["finished"] = True
        threading.Thread(target=work, daemon=True).start()
        self.root.after(300, lambda: self.pkg_tick(target, update))

    def pkg_tick(self, target, update):
        state = self.busy
        if not state["finished"]:
            percent = 100 * state["done"] / max(1, state["total"])
            self.set_status(f"Unpacking the PKG… {percent:.0f}%",
                            f"{state['done'] >> 20} of {state['total'] >> 20} MB, {state.get('rate', 0):.0f} MB/s")
            self.root.after(300, lambda: self.pkg_tick(target, update))
            return
        self.busy = None
        if state["error"]:
            self.set_status("The PKG could not be unpacked.", state["error"])
            messagebox.showerror(APP_TITLE, f"The PKG could not be unpacked:\n{state['error']}")
            return
        self.save({"update_dir" if update else "game_dir": str(target)})
        self.refresh_folders()
        self.set_status("PKG unpacked.", str(target))

    def refresh_backups(self):
        names = save_backup.list_backups(USER_DIR)
        options = [(n, n) for n in names] or [("", "No backups yet")]
        self.backup_choice.options = options
        self.backup_choice.set(options[0][0])

    def restore_backup(self):
        name = self.backup_choice.value
        if not name:
            messagebox.showinfo(APP_TITLE, "There is no save backup yet (one is made before every start).")
            return
        if self.process:
            messagebox.showinfo(APP_TITLE, "Close the game first.")
            return
        if not messagebox.askyesno(APP_TITLE, f"Replace your saves with the backup from {name}?\n\nYour current "
                                              "saves are backed up first, so this can be undone."):
            return
        try:
            save_backup.restore(USER_DIR, name)
        except (OSError, ValueError) as error:
            messagebox.showerror(APP_TITLE, f"The backup could not be restored:\n{error}")
            return
        self.refresh_backups()
        messagebox.showinfo(APP_TITLE, f"Saves restored from {name}.")

    def open_path(self, path):
        path = Path(path)
        target = path if path.exists() else next((p for p in path.parents if p.exists()), ROOT)
        try:
            os.startfile(target)
        except OSError as error:
            messagebox.showerror(APP_TITLE, f"Could not open {target}:\n{error}")

    def clear_cache(self):
        cache = USER_DIR / "cache"
        if not cache.exists():
            messagebox.showinfo(APP_TITLE, "There is no shader cache yet.")
            return
        if self.process:
            messagebox.showwarning(APP_TITLE, "Close the game first.")
            return
        if not messagebox.askyesno(APP_TITLE, "Delete the shader cache?\n\nShaders are compiled again the next time "
                                              "you play, which brings back stutters for a while."):
            return
        shutil.rmtree(cache, ignore_errors=True)
        messagebox.showinfo(APP_TITLE, "Shader cache cleared.")

    def shortcut_icon(self):
        """An .ico of the game's own icon (made on this PC, never shipped), else the starter's."""
        icon = self.art("icon0.png")
        if icon is not None:
            try:
                OUT_DIR.mkdir(parents=True, exist_ok=True)
                path = OUT_DIR / "matterfall.ico"
                icon.save(path, sizes=[(256, 256), (64, 64), (48, 48), (32, 32), (16, 16)])
                return path
            except OSError:
                pass
        return STARTER_EXE if STARTER_EXE.exists() else None

    def desktop_shortcut(self):
        link = desktop_folder() / "Matterfall.lnk"
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        target = pythonw if pythonw.exists() else Path(sys.executable)
        arguments = f"\"{Path(__file__).resolve()}\""
        if STARTER_EXE.exists():
            target, arguments = STARTER_EXE, ""
        icon = self.shortcut_icon()

        def ps(value):
            return "'" + str(value).replace("'", "''") + "'"
        script = ("[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
                  f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut({ps(link)});"
                  f"$s.TargetPath={ps(target)};$s.Arguments={ps(arguments)};$s.WorkingDirectory={ps(ROOT)};"
                  + (f"$s.IconLocation={ps(icon)};" if icon else "") +
                  "$s.Description='Matterfall (PS4) PC port launcher';$s.Save()")
        result = subprocess.run(["powershell", "-NoProfile", "-Command", script], creationflags=NO_WINDOW,
                                capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode == 0 and link.exists():
            messagebox.showinfo(APP_TITLE, f"Shortcut created:\n{link}")
        else:
            messagebox.showerror(APP_TITLE, f"The shortcut could not be created:\n{result.stderr.strip()[-600:]}")

    def reset_settings(self):
        if not messagebox.askyesno(APP_TITLE, "Set every setting back to its default (the PS4's graphics, 60 FPS, "
                                              "default controls)? The game folders are kept."):
            return
        keep = {k: self.ini.get(k, "") for k in ("game_dir", "update_dir")}
        defaults = {k: v for k, v in ms.DEFAULTS.items() if k not in keep}
        self.save({**defaults, "key_map": "", "mouse_map": "", "pad_map": ""})
        self.follow_ini()
        for key, widget in self.widgets.items():
            if key in self.ini:
                widget.set(self.ini[key])
        self.controls, self.pad = controls_from_ini(self.ini)
        self.refresh_bindings()
        self.redraw_presets()

    # -- footer, play -----------------------------------------------------------------------

    def build_footer(self):
        footer = tk.Frame(self.root, bg=PANEL)
        footer.pack(side="bottom", fill="x")
        tk.Frame(self.root, bg=LINE, height=1).pack(side="bottom", fill="x")
        inner = tk.Frame(footer, bg=PANEL)
        inner.pack(fill="x", padx=self.px(40), pady=self.px(14))
        left = tk.Frame(inner, bg=PANEL)
        left.pack(side="left", fill="x", expand=True)
        self.status = tk.Label(left, text="Ready to play Matterfall.", font=self.f_body_bold, bg=PANEL, fg=TEXT, anchor="w")
        self.status.pack(side="top", fill="x")
        self.substatus = tk.Label(left, text="Insert or R3 + L2 in the game opens the menu.", font=self.f_small,
                                  bg=PANEL, fg=MUTED, anchor="w")
        self.substatus.pack(side="top", fill="x")
        w, h = self.px(200), self.px(52)
        self.play_button = tk.Canvas(inner, width=w, height=h, bg=PANEL, highlightthickness=0, cursor="hand2")
        self.play_button.pack(side="right")
        self.play_button.bind("<Button-1>", lambda e: self.play_or_stop())
        self.play_button.bind("<Enter>", lambda e: self.draw_play(hover=True))
        self.play_button.bind("<Leave>", lambda e: self.draw_play())
        self.draw_play()
        self.update_button = tk.Label(inner, text="UPDATE", font=self.f_body_bold, bg=PANEL_HI, fg=ACCENT,
                                      padx=self.px(16), pady=self.px(10), cursor="hand2", highlightthickness=1,
                                      highlightbackground=ACCENT)

    def draw_play(self, hover=False):
        canvas = self.play_button
        w, h = int(canvas["width"]), int(canvas["height"])
        canvas.delete("all")
        running = self.process is not None
        fill = STOP_RED if running else (ACCENT_HI if hover else ACCENT)
        round_rect(canvas, 2, 2, w - 2, h - 2, self.px(8), fill=fill, outline=fill)
        canvas.create_text(w // 2, h // 2, text="STOP" if running else "PLAY", font=self.f_play,
                           fill=TEXT if running else INK)

    def set_status(self, text, detail=None):
        self.status.config(text=text)
        if detail is not None:
            self.substatus.config(text=detail)

    def check_updates(self):
        """The newest release on GitHub against this package's VERSION: a notice, nothing installed."""
        current = (ROOT / "VERSION").read_text(encoding="ascii", errors="replace").strip() \
            if (ROOT / "VERSION").is_file() else None
        if not current:
            return
        result = []

        def work():
            try:
                request = urllib.request.Request(f"https://api.github.com/repos/{UPDATE_REPOSITORY}/releases/latest",
                                                 headers={"Accept": "application/vnd.github+json"})
                with urllib.request.urlopen(request, timeout=10) as response:
                    result.append(json.load(response))
            except (OSError, ValueError):
                result.append(None)
        threading.Thread(target=work, daemon=True).start()

        def done():
            if not result:
                self.root.after(300, done)
                return
            release = result[0]
            if not release:
                return
            tag = str(release.get("tag_name", "")).lstrip("v")

            def numbers(text):
                return tuple(int(p) for p in text.split(".") if p.isdigit())
            if numbers(tag) > numbers(current.lstrip("v")):
                url = release.get("html_url") or f"https://github.com/{UPDATE_REPOSITORY}/releases"
                self.update_button.config(text=f"VERSION {tag} AVAILABLE")
                self.update_button.bind("<Button-1>", lambda e: webbrowser.open(url))
                self.update_button.pack(side="right", padx=(0, self.px(14)))
        self.root.after(300, done)

    def play_or_stop(self):
        if self.process:
            self.stop()
        else:
            self.play()

    def play(self):
        if self.busy:
            messagebox.showinfo(APP_TITLE, "Wait until the PKG is unpacked.")
            return
        if not RUN_SCRIPT.exists():
            messagebox.showerror(APP_TITLE, f"Start script missing:\n{RUN_SCRIPT}")
            return
        if not is_game_dir(self.game_dir()):
            messagebox.showinfo(APP_TITLE, "Select your Matterfall game folder (CUSA02475, the unpacked game with "
                                           "eboot.bin and sce_sys), or install it from its PKG (Advanced).")
            if not self.choose_game_dir():
                return
        self.follow_ini()
        if not self.update_dir() and self.ini.get("warned_no_update") != str(self.game_dir()):
            if not messagebox.askokcancel(APP_TITLE, "No update found for this game. The port is tested with "
                                                     "update 1.01: unpack it next to the game folder as "
                                                     f"{self.game_dir().name}-patch, or choose it under Advanced.\n\n"
                                                     "Play anyway?"):
                return
            self.save({"warned_no_update": str(self.game_dir())})
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        env["GOW3_CONFIG"] = str(INI_FILE)
        env.setdefault("GOW3_DATA_DIR", str(DATA_DIR))
        python = Path(sys.executable)
        if python.name.lower() == "pythonw.exe" and python.with_name("python.exe").exists():
            python = python.with_name("python.exe")
        command = [str(python), "-u", str(RUN_SCRIPT), "--game", str(self.game_dir()),
                   "--update", str(self.update_dir()) if self.update_dir() else "none"]
        try:
            ctypes.windll.user32.AllowSetForegroundWindow(-1)  # the game window may take the focus
        except (AttributeError, OSError):
            pass
        try:
            self.process = subprocess.Popen(command, cwd=str(ROOT), env=env, stdout=subprocess.PIPE,
                                            stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                            creationflags=NO_WINDOW, text=True, encoding="utf-8", errors="replace")
        except OSError as error:
            messagebox.showerror(APP_TITLE, f"Could not start the game:\n{error}")
            self.process = None
            return
        self.started_at = time.time()
        self.last_output = time.time()
        self.game_started = False
        try:
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            self.run_log = open(OUT_DIR / "launcher-last-run.log", "w", encoding="utf-8")
            self.run_log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {subprocess.list2cmdline(command)}\n")
        except OSError:
            self.run_log = None
        threading.Thread(target=self.read_output, args=(self.process,), daemon=True).start()
        self.set_status("Starting Matterfall…", "Preparing the game files and settings.")
        self.draw_play()

    def read_output(self, process):
        log = self.run_log
        for line in process.stdout:
            self.output.put(line.rstrip())
            if log:
                try:
                    log.write(line)
                    log.flush()
                except (OSError, ValueError):
                    log = None
        if log:
            try:
                log.close()
            except OSError:
                pass

    def poll(self):
        while True:
            try:
                line = self.output.get_nowait()
            except queue.Empty:
                break
            self.last_output = time.time()
            if line.startswith(("Unreal Engine settings:", "Saves backed up", "Settings:")):
                self.set_status("Starting Matterfall…", line[:160])
        if self.process:
            if self.process.poll() is not None:
                self.finished(self.process.returncode)
            elif not self.game_started and time.time() - self.last_output > 2.5:
                self.game_started = True
                self.set_status("Playing Matterfall", "Insert or R3 + L2 opens the in-game menu. STOP closes the game.")
        self.root.after(150, self.poll)

    def crash_reason(self):
        log = OUT_DIR / "boot.log"
        try:
            if log.stat().st_mtime < self.started_at:
                return None
            tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-80:]
        except OSError:
            return None
        for i, line in enumerate(tail):
            if line.startswith("Fault:") or line.startswith("STOP:") or "Assertion" in line:
                return "\n".join(l for l in tail[i:i + 4] if l.strip())[-600:]
        return None

    def finished(self, code):
        self.process = None
        self.draw_play()
        self.refresh_backups()
        if code in (0, None) or getattr(self, "stopping", False):
            self.stopping = False
            self.set_status("Game closed.", "Ready to play again.")
        else:
            reason = self.crash_reason()
            self.set_status("The game stopped unexpectedly.", f"Exit code {code}. See the log folder.")
            if messagebox.askyesno(APP_TITLE, "The game stopped with an error" + (f":\n\n{reason}" if reason else ".")
                                   + "\n\nOpen the log folder?"):
                self.open_path(OUT_DIR)
        if self.direct:
            self.root.after(200, self.root.destroy)

    def stop(self):
        if not self.process:
            return
        self.stopping = True
        subprocess.run(["taskkill", "/PID", str(self.process.pid), "/T", "/F"], creationflags=NO_WINDOW,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.set_status("Stopping the game…")

    def play_direct(self):
        self.play()
        if not self.process:
            self.root.destroy()

    def close(self):
        if self.process and not messagebox.askyesno(
                APP_TITLE, "The game is still running. Close the launcher anyway? (The game keeps running.)"):
            return
        self.root.destroy()


def log_launcher_error(kind, value, trace):
    """Errors go to <data>/analysis/matterfall/launcher-error.log (pythonw has no console)."""
    import traceback
    text = "".join(traceback.format_exception(kind, value, trace))
    path = OUT_DIR / "launcher-error.log"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as log:
            log.write(time.strftime("%Y-%m-%d %H:%M:%S ") + "\n" + text + "\n")
    except OSError:
        pass
    return text, path


def main():
    if "--version" in sys.argv[1:]:
        print("Matterfall launcher;", "settings", INI_FILE)
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("BilalReloaded.Matterfall.Launcher")
    except Exception:
        pass
    direct = "--play" in sys.argv[1:]  # desktop "play" shortcuts: start at once, close with the game
    root = tk.Tk()
    if direct:
        root.withdraw()
    root.report_callback_exception = lambda kind, value, trace: log_launcher_error(kind, value, trace)
    launcher = Launcher(root, direct)
    if "--smoke-test" in sys.argv[1:]:  # packaging check: build every page, then close
        root.update()
        for name in launcher.pages:
            launcher.show_tab(name, save=False)
            root.update()
        print("Launcher smoke test: OK,", len(launcher.pages), "pages,", len(launcher.widgets), "settings")
        root.destroy()
        return
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        text, path = log_launcher_error(*sys.exc_info())
        try:
            fallback = tk.Tk()
            fallback.withdraw()
            messagebox.showerror(APP_TITLE, f"The launcher could not start:\n\n{text[-1500:]}\nThis was saved to:\n{path}")
            fallback.destroy()
        except Exception:
            pass
        raise
