#!/usr/bin/env python3
"""Start Matterfall (PS4, CUSA02475, Unreal Engine 4.13) on this runtime.

The game folder is an unpacked PKG (eboot.bin, sce_module, sce_sys, turrigun/...). An update
folder beside it (<game>-patch, or --update) is laid over it: its executable and modules are the
ones prepared and run, and its files win over the game's when the game opens them.

Settings come from matterfall.ini (the launcher and the in-game menu write it; see
gow3_pc/scripts/matterfall_settings.py): the runtime reads its own keys, this script turns the
others into GOW3_* environment variables and an Unreal Engine config override pak (render scale,
quality, frame rate; gow3_pc/scripts/ue4_override.py). Your own GOW3_* environment still wins.
The saves are backed up before every start (user/savedata_backups, the last 10).

Usage:
  python tools/run_matterfall.py [--game DIR] [--update DIR|none] [--seconds N] [--check-imports]
                                 [--data DIR] [--no-overrides] [-- extra runtime arguments]
Output (log, prepared image) goes to <data>/analysis/matterfall; saves and caches to <data>/user;
the settings file is <data>/matterfall.ini (data: GOW3_DATA_DIR, else the port folder).
"""
import argparse
import ctypes
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / 'gow3_pc' / 'scripts'
RUNTIME = ROOT / 'gow3_pc' / 'out' / 'gow3-probe.exe'
TITLE_ID = 'CUSA02475'
sys.path.insert(0, str(SCRIPTS))

# Unreal Engine 4 needs none of the Uncharted/God of War hooks: their shader hashes and memory
# layouts belong to those games. Linear image readbacks keep UE4's CPU-read render targets
# (sky light SH map, exposure) correct.
DEFAULT_ENV = {
    'GOW3_GAMESETTINGS': '0',       # Uncharted draw-distance pokes off
    'GOW3_MOUSE_LOOK': '0',         # no known camera code: mouse acts as the right stick
    # The temporal upscalers (FSR 3.1/4, DLSS) need the game's motion vectors, which are only
    # worked out for Uncharted: off. FSR 1 and RCAS (fsr1, rcas in matterfall.ini) still work.
    'GOW3_UPSCALER': 'none',
    'GOW3_READBACK_LINEAR': '1',
    'GOW3_VBLANK_HZ': '60',
    'GOW3_NATIVE_TSC': '1',
    'GOW3_PIPELINE_CACHE': '1',
    # Shared GPU core switches that are off for the Uncharted games:
    'GOW3_MERGE_SUBIMAGES': '1',    # sky cube mips drawn before the cube exists are merged into it
    'GOW3_REPORT_120HZ': '1',       # above 60 FPS (GOW3_VBLANK_HZ=0) the display reads 119.88 Hz
    'GOW3_RED_ZONE_RBP': '1',       # red zone kept through rbp (RenderThread index buffer crash)
    # Threaded Vulkan recording and the draw pipe are on (the runtime's defaults) since 30 Oct 2026:
    # data larger than a recording chunk (UE4's cube array uploads) is now recorded directly
    # instead of asserting in vk_scheduler.h, and a 36-minute level 1-1 run was clean.
    # GOW3_VK_RECORD_THREAD=0 / GOW3_DRAW_PIPE=0 turn them off.
}


def find_update(game, choice):
    if choice and choice.lower() == 'none':
        return None
    if choice:
        return Path(choice)
    for suffix in ('-patch', '-update', '_patch', '_update'):
        candidate = game.with_name(game.name + suffix)
        if (candidate / 'eboot.bin').is_file():
            return candidate
    return None


def wait_for(pid):
    """The in-game "Apply and restart": the previous game process ends first (GPU, memory)."""
    if os.name != 'nt':
        return
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
    if handle:
        kernel32.WaitForSingleObject(handle, 30000)
        kernel32.CloseHandle(handle)


def window_icon(game, out):
    """The game's own icon (sce_sys/icon0.png) as a BMP for the window (SDL loads BMP)."""
    try:
        from PIL import Image
        with Image.open(game / 'sce_sys' / 'icon0.png') as icon:
            icon.convert('RGBA').resize((64, 64), Image.LANCZOS).save(out / 'window_icon.bmp')
        return out / 'window_icon.bmp'
    except (ImportError, OSError):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--game', type=Path, help='game folder (default: matterfall.ini game_dir, '
                                                  f'else ../game/{TITLE_ID})')
    parser.add_argument('--update', help='update folder, or "none" (default: matterfall.ini update_dir, '
                                         'else <game>-patch)')
    parser.add_argument('--data', type=Path, help='folder of matterfall.ini, user/ and analysis/ '
                                                  '(default: GOW3_DATA_DIR, else the port folder)')
    parser.add_argument('--out', type=Path)
    parser.add_argument('--user', type=Path)
    parser.add_argument('--seconds', type=int, default=0, help='stop after N seconds (0: never)')
    parser.add_argument('--check-imports', action='store_true', help='only list unsupported imports')
    parser.add_argument('--no-overrides', action='store_true',
                        help='leave the Unreal Engine override pak as it is (no settings applied to it)')
    parser.add_argument('--after', type=int, help=argparse.SUPPRESS)  # in-game restart
    parser.add_argument('extra', nargs='*', help='more runtime arguments (after --)')
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):  # the game's log may hold any character
        try:
            stream.reconfigure(errors='replace')
        except (AttributeError, ValueError):
            pass
    if args.after:
        wait_for(args.after)

    import matterfall_settings as settings
    data = (args.data or Path(os.environ.get('GOW3_DATA_DIR') or ROOT)).resolve()
    config = Path(os.environ.get('GOW3_CONFIG') or data / 'matterfall.ini')
    values = settings.settings(settings.read_ini(config))

    game = args.game or (Path(values['game_dir']) if values.get('game_dir') else ROOT.parent / 'game' / TITLE_ID)
    game = game.resolve()
    if not (game / 'eboot.bin').is_file():
        sys.exit(f'No eboot.bin in {game}: unpack the game PKG there (gow3_pc/scripts/pkg_extract.py), '
                 'or choose the game folder in the launcher.')
    update_choice = args.update or (values.get('update_dir') or None)
    update = find_update(game, update_choice)
    if update and not (update / 'eboot.bin').is_file():
        print(f'Update: {update} has no eboot.bin; starting without it', flush=True)
        update = None
    if update:
        update = update.resolve()
        print(f'Update: {update}', flush=True)
    # The executable and modules that run: the update's when there is one.
    code = update or game
    out = (args.out or data / 'analysis' / 'matterfall').resolve()
    out.mkdir(parents=True, exist_ok=True)
    user = (args.user or Path(os.environ.get('GOW3_USER_DIR') or data / 'user')).resolve()
    user.mkdir(parents=True, exist_ok=True)

    for script, extra in (('prepare.py', ['--executable', 'eboot.bin']),
                          ('link_modules.py', ['--executable', 'eboot.bin']),
                          ('content_profile.py', [])):
        subprocess.run([sys.executable, str(SCRIPTS / script), str(code), '--out', str(out), *extra], check=True,
                       stdin=subprocess.DEVNULL)

    env = dict(os.environ)
    # Values derived on the previous start ("Apply and restart" inherits them) are derived again.
    for key in env.pop('GOW3_DERIVED', '').split(','):
        env.pop(key, None)
    derived = []
    for key, value in settings.environment(values).items():
        if key not in env:
            env[key] = value
            derived.append(key)
    for key, value in DEFAULT_ENV.items():
        env.setdefault(key, value)
    env.setdefault('GOW3_CONFIG', str(config))
    env.setdefault('GOW3_GPU_USER_DIR', str(user))
    icon = window_icon(game, out)
    if icon:
        env.setdefault('GOW3_WINDOW_ICON', str(icon))
    env['GOW3_DERIVED'] = ','.join(derived)
    clang64 = Path(env.get('MSYS2_ROOT', r'C:\msys64')) / 'clang64' / 'bin'
    if os.name == 'nt' and clang64.is_dir() and not (RUNTIME.parent / 'SDL3.dll').is_file():
        env['PATH'] = f'{clang64}{os.pathsep}{env.get("PATH", "")}'
    print('Settings:', config, '-', settings.summary(values), flush=True)

    # Render scale, quality and frame rate: the Unreal Engine config override pak.
    if not args.no_overrides:
        import ue4_override
        try:
            print('Unreal Engine settings:', ue4_override.apply(game, update, settings.ue4_options(values),
                                                                settings.engine_fps(values)), flush=True)
        except (OSError, ValueError) as error:
            print(f'Unreal Engine settings: unchanged ({error})', flush=True)

    from save_backup import backup
    try:
        made = backup(user)
        if made:
            print(f'Saves backed up to {made}', flush=True)
    except OSError as error:
        print(f'Save backup failed, starting anyway: {error}', flush=True)

    runtime = Path(env.get('GOW3_PROBE', RUNTIME))
    if not runtime.is_file():
        sys.exit(f'{runtime} not found: build it with gow3_pc/build.sh.')
    # The in-game "Apply and restart" starts this script again once this process is gone.
    restart = [sys.executable, str(Path(__file__).resolve()), '--after', str(os.getpid()),
               '--game', str(game), '--update', str(update) if update else 'none', '--data', str(data)]
    if args.extra:
        restart += ['--', *args.extra]
    env['GOW3_RESTART_COMMAND'] = subprocess.list2cmdline(restart)
    command = [str(runtime), str(out / 'boot-linked.bin'), '--no-game-hooks',
               '--content-profile', str(out / 'content.bin'),
               '--app0', str(game), '--user', str(user), '--guest-path', '/app0/eboot.bin',
               '--timeout', str(args.seconds)]
    if update:
        command += ['--app0-overlay', str(update)]
    if args.check_imports:
        command.append('--check-imports')
    command += args.extra
    log = out / ('check-imports.log' if args.check_imports else 'boot.log')
    print('Log:', log, flush=True)
    with open(log, 'w', encoding='utf-8', errors='replace') as stream:
        process = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        for line in iter(process.stdout.readline, b''):
            text = line.decode('utf-8', errors='replace')
            stream.write(text)
            stream.flush()
            sys.stdout.write(text)
            sys.stdout.flush()
        process.wait()
    print(f'Runtime exited with {process.returncode}', flush=True)
    return process.returncode


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
