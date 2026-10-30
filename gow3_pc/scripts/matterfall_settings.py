#!/usr/bin/env python3
"""Matterfall settings: matterfall.ini, shared by the launcher, tools/run_matterfall.py and the
runtime.

One file holds three kinds of keys:
  - the runtime's own (gow3_pc/gpu/shim/gow3_settings.cpp; the in-game menu, Insert / R3+L2,
    changes the same): display_mode, vsync, fps_limit, show_fps, async_shaders, fsr1, rcas,
    rcas_strength, frames_queued, mouse, mouse_sens, key_map, pad_map, mouse_map, ...;
  - Unreal Engine settings that tools/run_matterfall.py writes into a config override pak at
    every start (scripts/ue4_override.py): ue4_render_scale, ue4_quality, ue4_<group>, engine_fps;
  - start options that become GOW3_* environment variables: window_size, frame_limit,
    anisotropy, language, speakers, shader options, game_dir, update_dir.
The runtime keeps keys it does not know when it saves the file.
"""
import ctypes
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ue4_override  # noqa: E402

DEFAULTS = {
    # runtime (gow3_settings.cpp)
    'display_mode': 'windowed', 'vsync': '1', 'fps_limit': '60', 'show_fps': '0', 'async_shaders': '1',
    'fsr1': '0', 'rcas': '0', 'rcas_strength': '75', 'frames_queued': '1',
    'mouse': '1', 'mouse_sens': '1.00', 'mouse_invert': '0', 'vibration': '1', 'prompts': 'auto',
    # Unreal Engine (ue4_override.py)
    'ue4_render_scale': 'console', 'ue4_quality': 'console', 'engine_fps': '60',
    **{f'ue4_{group}': 'preset' for group in ue4_override.GROUP_NAMES},
    **{f'ue4_{toggle}': 'console' for toggle in ue4_override.TOGGLES},
    'ue4_anti_aliasing': 'console', 'ue4_sharpen': 'off', 'ue4_upscale_filter': 'console',
    # start options (environment)
    'window_size': 'auto', 'frame_limit': '60', 'anisotropy': '0', 'language': '1', 'speakers': 'auto',
    # The runtime's own defaults: only a changed value becomes an environment variable.
    'background_warmup': '1', 'parallel_warmup': '0', 'pipeline_binaries': '0', 'perf_log': '0',
    'game_dir': '', 'update_dir': '',
}

ENGINE_FPS = ('60', '120', '240')
# Frame limits the runtime's own list has (gow3_graphics.h FpsLimits): written as fps_limit, so
# the in-game menu shows and changes them. Others (above 120, unlimited, half the display's
# refresh) are fixed for the session with GOW3_FPS_LIMIT.
RUNTIME_LIMITS = ('30', '40', '45', '50', '55', '60', '75', '90', '100', '120')
FRAME_LIMITS = ('30', '60', '120', '144', '165', '240', '0', 'half')
WINDOW_SIZES = ('auto', '1280x720', '1600x900', '1920x1080', '2560x1440', '3840x2160')


def read_ini(path):
    values = {}
    try:
        lines = Path(path).read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        return values
    for line in lines:
        if '=' in line and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            values[key.strip()] = value.strip()
    return values


def write_keys(path, updates):
    """Rewrites `updates` in place and appends missing keys, keeping every other line (LF)."""
    path = Path(path)
    try:
        lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        lines = ['# Matterfall settings (launcher and in-game menu: Insert / R3+L2)']
    done, out = set(), []
    for line in lines:
        key = line.split('=', 1)[0].strip() if '=' in line and not line.lstrip().startswith('#') else None
        if key in updates:
            if key not in done:
                out.append(f'{key}={updates[key]}')
                done.add(key)
        else:
            out.append(line)
    out += [f'{k}={v}' for k, v in updates.items() if k not in done]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(out) + '\n')
    tmp.replace(path)


def settings(ini):
    """Every key with its default filled in."""
    return {**DEFAULTS, **{k: v for k, v in ini.items() if v != '' or k in ('game_dir', 'update_dir')}}


def engine_fps(values):
    fps = values.get('engine_fps', '60')
    return int(fps) if fps in ENGINE_FPS else 60


def ue4_options(values):
    """ue4_override.apply options from the ini (the ue4_ prefix dropped)."""
    return {key[4:]: value for key, value in values.items() if key.startswith('ue4_')}


def display_refresh_hz():
    """The primary display's refresh rate, 60 when unknown."""
    if os.name != 'nt':
        return 60
    try:
        class DEVMODE(ctypes.Structure):
            _fields_ = [('name', ctypes.c_wchar * 32), ('spec', ctypes.c_ushort), ('driver', ctypes.c_ushort),
                        ('size', ctypes.c_ushort), ('extra', ctypes.c_ushort), ('fields', ctypes.c_ulong),
                        ('pos', ctypes.c_long * 2), ('orientation', ctypes.c_ulong), ('fixed', ctypes.c_ulong),
                        ('color', ctypes.c_short), ('duplex', ctypes.c_short), ('yres', ctypes.c_short),
                        ('tt', ctypes.c_short), ('collate', ctypes.c_short), ('form', ctypes.c_wchar * 32),
                        ('logpixels', ctypes.c_ushort), ('bits', ctypes.c_ulong), ('width', ctypes.c_ulong),
                        ('height', ctypes.c_ulong), ('flags', ctypes.c_ulong), ('frequency', ctypes.c_ulong)]
        mode = DEVMODE()
        mode.size = ctypes.sizeof(DEVMODE)
        if ctypes.windll.user32.EnumDisplaySettingsW(None, -1, ctypes.byref(mode)) and mode.frequency > 1:
            return int(mode.frequency)
    except (AttributeError, OSError):
        pass
    return 60


def screen_size():
    if os.name != 'nt':
        return 1920, 1080
    try:
        user32 = ctypes.windll.user32
        # Physical pixels, as the game window (SDL) counts them: a DPI-unaware process is told
        # the scaled size (2048x1152 for a 2560x1440 screen at 125%).
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            user32.SetProcessDPIAware()
        return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    except (AttributeError, OSError):
        return 1920, 1080


def window_rect(size):
    """GOW3_WINDOW_RECT for a windowed size, centred on the primary display (at most its size)."""
    try:
        width, height = (int(n) for n in size.split('x'))
    except ValueError:
        return None
    screen_w, screen_h = screen_size()
    if width > screen_w * 0.95 or height > screen_h * 0.9:  # room for the border and the taskbar
        scale = min(screen_w * 0.95 / width, screen_h * 0.9 / height)
        width, height = int(width * scale) // 2 * 2, int(height * scale) // 2 * 2
    return f'{(screen_w - width) // 2},{max(0, (screen_h - height) // 2 - 16)},{width},{height}'


def frame_limit(values):
    """(fps_limit for the ini or None, GOW3_FPS_LIMIT or None, description)."""
    choice = values.get('frame_limit', '60')
    fps = engine_fps(values)
    if choice in RUNTIME_LIMITS:
        return choice, None, f'{choice} FPS'
    if choice == 'half':
        half = max(30, round(display_refresh_hz() / 2))
        return None, str(half), f'{half} FPS (half the display refresh)'
    if choice == '0':
        # No "unlimited" in 1.0: without a limit the game twice asked for 22-28 GB at the intro
        # and closed (not understood yet). Settings from before keep the engine frame rate.
        return None, str(fps), f'{fps} FPS'
    if choice.isdigit():
        return None, choice, f'{choice} FPS'
    return '60', None, '60 FPS'


def environment(values):
    """GOW3_* variables for the start options (the user's own environment still wins)."""
    env = {}
    fps = engine_fps(values)
    if fps > 60:
        # Unreal Engine 4 flips at every vblank: a 480 Hz vblank (reported to the game as a
        # 119.88 Hz display, video_out driver) with a frame limit shows each frame when it is ready.
        env['GOW3_VBLANK_HZ'] = '0'
    _ini_limit, fixed, _text = frame_limit(values)
    if fixed is not None:
        env['GOW3_FPS_LIMIT'] = fixed
    if values.get('display_mode', 'windowed') == 'windowed' and values.get('window_size', 'auto') != 'auto':
        rect = window_rect(values['window_size'])
        if rect:
            env['GOW3_WINDOW_RECT'] = rect
    if values.get('anisotropy', '0') in ('2', '4', '8', '16'):
        env['GOW3_ANISOTROPY'] = values['anisotropy']
    if values.get('language', '1').isdigit() and values.get('language', '1') != '1':
        env['GOW3_LANGUAGE'] = values['language']  # PS4 language code; the runtime's default is 1
    if values.get('speakers', 'auto') in ('2', '6', '8'):
        env['GOW3_AUDIO_SPEAKERS'] = values['speakers']
    # Above the PS4's settings the game's render targets outgrow the PS4's 5056 MB of direct
    # memory: at 200% render scale it stopped with "Failed to allocate direct memory ... Size =
    # 67108864, MemoryType = Garlic" (PS4Memory.cpp line 265) on entering a level. A larger
    # reported pool does not work: the game hands its CPU heap all the free memory as a 32-bit size
    # (8192 MB shrank the heap to 728 MB, 9152 MB made later free-memory checks wrap and fail).
    # Spare memory the game is not told about takes the graphics allocations that no longer fit
    # (runtime_memory.c). Only the memory the game really allocates is committed.
    scale = values.get('ue4_render_scale', 'console')
    if (scale.isdigit() and int(scale) > 100) or values.get('ue4_quality') in ('high', 'ultra'):
        env['GOW3_DMEM_SPARE_MB'] = '4096'
    if values.get('background_warmup', '1') == '0':
        env['GOW3_BACKGROUND_WARMUP'] = '0'
    for key, name in (('parallel_warmup', 'GOW3_PARALLEL_WARMUP'), ('pipeline_binaries', 'GOW3_PIPELINE_BINARIES'),
                      ('perf_log', 'GOW3_FRAME_STATS')):
        if values.get(key, '0') == '1':
            env[name] = '1'
    return env


def summary(values):
    """One line for the log: what the start options do."""
    _ini, _fixed, limit = frame_limit(values)
    scale = values.get('ue4_render_scale', 'console')
    scale_text = 'PS4 84%' if scale == 'console' else f'{scale}%'
    return (f'render scale {scale_text}, quality {values.get("ue4_quality", "console")}, engine up to '
            f'{engine_fps(values)} FPS, frame limit {limit}, {values.get("display_mode", "windowed")}'
            + (f' {values["window_size"]}' if values.get('window_size', 'auto') != 'auto' else ''))
