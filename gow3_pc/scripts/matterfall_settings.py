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
    anisotropy, language, speakers, shader options, game_dir, update_dir; gpu_heap_extra_mb (hidden:
    the garlic heap's extra MB instead of the estimate, gpu_heap_extra_mb()).
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
    'output_resolution': '1080', 'pad_speaker_volume': '35', 'window_size': 'auto', 'frame_limit': '60', 'anisotropy': '0', 'language': '1', 'speakers': 'auto',
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


# Native output (1440p, 4K). The game picks its display size once at start (eboot 0x4c3170): it
# reads the display mode from VideoOut and switches to 3840x2160 when the display has more than
# 1080 lines, but its shipped [HMQ] ProMode=1 forces 1920x1080 again. Its back buffers are made
# once at that size and never resized, so a live r.SetRes cannot change the output. The runtime
# reports the chosen display (GOW3_INTERNAL_WIDTH/HEIGHT) and two eboot patches let the game use
# it: the ProMode clamp is skipped, and the reported size is used instead of a fixed 3840x2160.
# Patterns checked unique in the 1.00 and 1.01 eboots (both at the same addresses).
OUTPUT_SIZES = {'1080': (1920, 1080), '1440': (2560, 1440), '2160': (3840, 2160)}
OUTPUT_PATCHES = (
    # ProMode == 1 -> 1920x1080 (0x4c344b): jne -> jmp, the clamp is skipped.
    ('ProMode 1080p clamp', '83 7D 9C 01 75 15 48 8D 0D ?? ?? ?? ?? 48 B8 80 07 00 00 38 04 00 00 48 89 41 08',
     4, '75', 'EB'),
    # height > 1080 -> fixed 3840x2160 (0x4c31f1): mov rax,[rbp-0x60] (the reported size) + nop.
    ('reported display size', '81 7D A4 39 04 00 00 0F 82 ?? ?? ?? ?? 48 B8 00 0F 00 00 70 08 00 00 48 89 43 08',
     13, '48 B8 00 0F 00 00 70 08 00 00', '48 8B 45 A0 66 0F 1F 44 00 00'),
)


def output_size(values):
    """(width, height) of the game's native output."""
    return OUTPUT_SIZES.get(values.get('output_resolution', '1080'), (1920, 1080))


def _find(data, pattern):
    import re
    regex = b''.join(b'.' if byte == '??' else re.escape(bytes.fromhex(byte)) for byte in pattern.split())
    return [match.start() for match in re.finditer(regex, data, re.S)]


def apply_output_patches(image):
    """Patches the linked image for native output above 1080p. Returns None when done, else why not
    (nothing is changed then: every patch must match exactly once with its original bytes)."""
    path = Path(image)
    data = bytearray(path.read_bytes())
    edits = []
    for name, pattern, offset, original, replacement in OUTPUT_PATCHES:
        hits = _find(data, pattern)
        if len(hits) != 1:
            return f'{name}: pattern found {len(hits)} times'
        at = hits[0] + offset
        old, new = bytes.fromhex(original), bytes.fromhex(replacement)
        if data[at:at + len(old)] != old:
            return f'{name}: unexpected bytes'
        edits.append((at, new))
    for at, new in edits:
        data[at:at + len(new)] = new
    path.write_bytes(bytes(data))
    return None


# Graphics memory above the PS4's settings. Unreal Engine's PS4 code splits the direct memory at
# start (eboot 0x4cd480): the CPU heap gets "direct memory - 33 MB - reserved - onion - garlic"
# and later uses that as a 32-bit size, the garlic (GPU) heap gets r.GarlicHeapSizeMB from
# PS4Engine.ini [SystemSettings] (Matterfall: 2800, onion 300). Larger render targets (render
# scale above 100%, 1440p/4K output, Ultra shadows) outgrow the 2800 MB: the heap then adds pools
# of the failed allocation's size, printing "Failed to allocate GPU memory" for every pool it
# tries first (slow, and it crashed after some hundred pools). Raising the reported direct memory
# alone breaks the CPU heap (8192 MB wrapped it to 728 MB). Raising both by the same amount keeps
# the CPU heap at its PS4 size and gives the garlic heap the room. One garlic pool's free-list
# sizes are 32-bit (eboot 0x5e170), so the heap stays below 4 GiB: GPU_HEAP_MAX_MB.
DMEM_PS4_MB = 5056
GPU_HEAP_PS4_MB = 2800
GPU_HEAP_MAX_MB = 4094


# Peak garlic use measured in level 1-1 (the game's own heap counters, 1 s samples, Ultra unless
# noted): PS4 settings (1613x907) 1984 MB; 1613x907 2207 MB (4096 shadow maps); 4275x2405 3714 MB;
# 5120x2880 3795 and 3832 MB, and in a third run more than the 4094 MB heap for a moment at the
# level start. Unreal's render target pool keeps released targets for a while
# (r.RenderTargetPoolMin=500), so the level start peaks above the frame's own needs. Estimate:
# 2000 MB, plus the quality's fixed part, plus 170 MB per million pixels above the PS4's, plus a
# margin. Heap that is not used costs commit charge only (the pages are never touched).
GPU_HEAP_BASE_MB = 2000
GPU_HEAP_MB_PER_MPIXEL = 170
GPU_HEAP_QUALITY_MB = {'high': 128, 'ultra': 256}  # by the shadows level
GPU_HEAP_MARGIN_MB = 512  # fragmentation and short peaks between the samples
PS4_RENDER_PIXELS = 1613 * 907
# The largest scene that fits the 4094 MB heap (4275x2405, 1440p at 167%). Larger ones make the
# heap add pools in memory the game is not told about once it is full, and the game crashed soon
# after that (0xC0000005: the owner's 1440p at 200% with the PS4's heap; 5760x3240 with 4094 MB)
# or, without that memory, at once. 2160p at 200% also ran at 13 FPS (GPU-bound, RTX 5080).
MAX_RENDER_PIXELS = 10500000


def _shadows(values):
    level = values.get('ue4_shadows', 'preset')
    return values.get('ue4_quality', 'console') if level in ('preset', '', None) else level


def _scene_pixels(values, scale):
    width, height = output_size(values)
    percent = int(scale) if str(scale).isdigit() else 84
    return width * height * percent * percent // 10000


def render_scale(values):
    """The render scale that is used: the chosen one, or the largest listed scale below it whose
    scene has at most MAX_RENDER_PIXELS."""
    scale = values.get('ue4_render_scale', 'console')
    if _scene_pixels(values, scale) <= MAX_RENDER_PIXELS:
        return scale
    chosen = int(scale) if scale.isdigit() else 84
    fitting = [s for s in ue4_override.RENDER_SCALES if s.isdigit() and int(s) <= chosen
               and _scene_pixels(values, s) <= MAX_RENDER_PIXELS]
    return max(fitting, key=int) if fitting else 'console'


def render_pixels(values):
    """Pixels of the scene the game draws: the output size times the used render scale squared."""
    return _scene_pixels(values, render_scale(values))


def gpu_heap_extra_mb(values):
    """GPU heap memory above the PS4's for these settings (0: the PS4's heaps): the garlic heap's
    extra (64 MB steps, matterfall.ini gpu_heap_extra_mb overrides it) plus, with any, 128 MB for
    the onion heap (ue4_override.ONION_EXTRA_MB)."""
    override = values.get('gpu_heap_extra_mb', 'auto')
    if override.isdigit():
        garlic = int(override)
    else:
        need = (GPU_HEAP_BASE_MB + GPU_HEAP_QUALITY_MB.get(_shadows(values), 0) + GPU_HEAP_MARGIN_MB
                + GPU_HEAP_MB_PER_MPIXEL * max(0, render_pixels(values) - PS4_RENDER_PIXELS) // 1000000)
        garlic = -(-max(0, need - GPU_HEAP_PS4_MB) // 64) * 64
    garlic = min(garlic, GPU_HEAP_MAX_MB - GPU_HEAP_PS4_MB)
    return garlic + ue4_override.ONION_EXTRA_MB if garlic else 0


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
    if values.get('pad_speaker_volume', '35').isdigit():
        env['GOW3_PAD_SPEAKER_VOLUME'] = values['pad_speaker_volume']
    if values.get('speakers', 'auto') in ('2', '6', '8'):
        env['GOW3_AUDIO_SPEAKERS'] = values['speakers']
    width, height = output_size(values)
    if height > 1080:
        env['GOW3_INTERNAL_WIDTH'], env['GOW3_INTERNAL_HEIGHT'] = str(width), str(height)
    # The larger graphics heap is reported as more direct memory. tools/run_matterfall.py raises
    # r.GarlicHeapSizeMB in the override pak by the same amount (GOW3_DMEM_MB - DMEM_PS4_MB) and
    # drops this variable when the pak cannot be written: alone it would break the CPU heap.
    extra = gpu_heap_extra_mb(values)
    if extra:
        env['GOW3_DMEM_MB'] = str(DMEM_PS4_MB + extra)
    # Above the PS4's settings, direct memory the game is not told about (runtime_memory.c) is a
    # last resort for a heap that is still full for a moment: its extra pools go there instead of
    # failing at once (without it a full heap stopped the game at once). Only the memory really
    # allocated is committed.
    if (extra or height > 1080 or render_pixels(values) > 1920 * 1080
            or values.get('ue4_quality') in ('high', 'ultra')):
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
    width, height = output_size(values)
    return (f'output {width}x{height}, render scale {scale_text}, quality {values.get("ue4_quality", "console")}, engine up to '
            f'{engine_fps(values)} FPS, frame limit {limit}, {values.get("display_mode", "windowed")}'
            + (f' {values["window_size"]}' if values.get('window_size', 'auto') != 'auto' else ''))
