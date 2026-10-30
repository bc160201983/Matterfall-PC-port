#!/usr/bin/env python3
"""Unreal Engine 4.13 graphics override for Matterfall (render scale, quality, frame rate).

UE4 games read their config only from their paks. A small pak whose name ends in _P mounts with
the patch priority, and of two paks with the same priority the one whose name sorts last is
mounted first and wins (FPakPlatformFile::MountAllPakFiles sorts the names in descending order).
This one, turrigun-ps4_zz_launcher_p.pak, therefore wins over the update's turrigun-ps4_p.pak. It holds:
  - Turrigun/Config/PS4/PS4Engine.ini (the update's own copy, else the game's) with the chosen
    console variables in [SystemSettings] and the frame-rate range in [/Script/Engine.Engine];
  - the two Blueprints that set the PS4 graphics at every level start (BP_EngineSettings: render
    scale 84%, shadows, post-process; BP_FunctionLibrary: screen-space reflections), with the
    commands for the variables chosen here changed. They run as console commands, which beat any
    ini value, so each one is either given the new value in place (same length: the package's
    sizes stay valid) or turned into an unknown command ("r.X" -> "#.X") so the ini value holds.

Matterfall 1.00/1.01 paks are version 3 (absolute compression-block offsets, a 44-byte footer, no
encrypted index); this pak is written in the same version, uncompressed.
It is written into the game's paks folder at every start and removed when nothing is changed.

Usage: python ue4_override.py <game dir> [--update DIR] [--render-scale 100] [--quality high] ...
       python ue4_override.py --check <pak>    (parses a pak back and lists its files)
"""
import argparse
import hashlib
import os
import re
import struct
import zlib
from pathlib import Path

PAK_MAGIC = 0x5A6F12E1
PAK_VERSION = 3
PAK_NAME = 'turrigun-ps4_zz_launcher_p.pak'
PROJECT = 'Turrigun'
CONFIG = 'Turrigun/Config/PS4/PS4Engine.ini'
ENGINE_SETTINGS = 'Turrigun/Content/Gameplay/Common/BP_EngineSettings.uasset'
FUNCTION_LIBRARY = 'Turrigun/Content/Gameplay/Common/BP_FunctionLibrary.uasset'
BLUEPRINTS = (ENGINE_SETTINGS, FUNCTION_LIBRARY)


def paks_dir(folder):
    return Path(folder) / 'turrigun' / 'content' / 'paks'


# -- pak files ----------------------------------------------------------------------------------

def _footer(path):
    """(version, index offset, index size) of a pak, versions 1 to 7, unencrypted index."""
    size = os.path.getsize(path)
    with open(path, 'rb') as f:
        for footer_size in (44, 45, 61):  # v1-3, v4-6 (bEncryptedIndex), v7 (+ key GUID)
            if size < footer_size:
                continue
            f.seek(size - footer_size + (footer_size - 44))
            magic, version, offset, index_size = struct.unpack('<IIQQ', f.read(24))
            if magic == PAK_MAGIC:
                if footer_size == 45:
                    f.seek(size - 45)
                    if f.read(1) != b'\0':
                        raise ValueError(f'{Path(path).name}: encrypted pak index')
                return version, offset, index_size
    raise ValueError(f'{Path(path).name}: not a pak file')


def read_index(path):
    """(version, mount point, {name: (offset, size, compression, blocks)}). Block offsets are
    absolute in the file (versions before 5 store them so; later ones are made absolute here)."""
    version, index_offset, index_size = _footer(path)
    with open(path, 'rb') as f:
        f.seek(index_offset)
        index = f.read(index_size)
    pos = 0

    def fstring():
        nonlocal pos
        n, = struct.unpack_from('<i', index, pos)
        pos += 4
        if n < 0:
            text = index[pos:pos - 2 * n].decode('utf-16le')[:-1]
            pos += -2 * n
        else:
            text = index[pos:pos + n].decode('latin1')[:-1]
            pos += n
        return text
    mount = fstring()
    count, = struct.unpack_from('<i', index, pos)
    pos += 4
    entries = {}
    for _ in range(count):
        name = fstring()
        offset, size, _uncompressed, compression = struct.unpack_from('<qqqi', index, pos)
        pos += 28
        if version == 1:
            pos += 8  # timestamp
        pos += 20  # SHA-1
        blocks = []
        if version >= 3:
            if compression:
                count_blocks, = struct.unpack_from('<i', index, pos)
                pos += 4
                for _ in range(count_blocks):
                    start, end = struct.unpack_from('<qq', index, pos)
                    if version >= 5:
                        start, end = start + offset, end + offset
                    blocks.append((start, end))
                    pos += 16
            pos += 5  # bEncrypted, CompressionBlockSize
        entries[name] = (offset, size, compression, blocks)
    if pos != len(index):
        raise ValueError(f'{Path(path).name}: index not fully read ({pos} of {len(index)} bytes)')
    return version, mount, entries


def _entry_header_size(version, compression, blocks):
    size = 8 + 8 + 8 + 4 + 20 + (8 if version == 1 else 0)
    if version >= 3:
        size += (4 + 16 * len(blocks) if compression else 0) + 5
    return size


def read_entry(path, entry, version):
    offset, size, compression, blocks = entry
    with open(path, 'rb') as f:
        if not compression:
            f.seek(offset + _entry_header_size(version, 0, []))
            return f.read(size)
        if compression != 1:
            raise ValueError(f'{Path(path).name}: compression {compression} is not zlib')
        data = bytearray()
        for start, end in blocks:
            f.seek(start)
            data += zlib.decompress(f.read(end - start))
        return bytes(data)


def game_paks(game, update=None):
    """The game's own paks, highest priority first: the update's _p paks, then the game's
    (this module's own pak left out)."""
    paks = []
    for folder in (update, game):
        if folder and paks_dir(folder).is_dir():
            found = [p for p in paks_dir(folder).glob('*.pak') if p.name.lower() != PAK_NAME]
            paks += sorted(found, key=lambda p: (not p.stem.lower().endswith('_p'), p.name.lower()))
    return paks


def read_file(paks, name, cache=None):
    """A file from the first pak that has it (paks from game_paks)."""
    for pak in paks:
        key = str(pak)
        if cache is not None and key in cache:
            version, entries = cache[key]
        else:
            version, _mount, entries = read_index(pak)
            if cache is not None:
                cache[key] = (version, entries)
        if name in entries:
            return read_entry(pak, entries[name], version)
    raise FileNotFoundError(name)


def _fstring(text):
    data = text.encode('latin1') + b'\0'
    return struct.pack('<i', len(data)) + data


def _entry(offset, data):
    """FPakEntry, version 3, uncompressed and unencrypted (as UnrealPak 4.13 writes it)."""
    return struct.pack('<qqqi', offset, len(data), len(data), 0) + hashlib.sha1(data).digest() + \
        b'\0' + struct.pack('<I', 0)


def write_pak(path, files, mount='../../../'):
    """An uncompressed version 3 pak of {name: bytes}."""
    body, records = b'', []
    for name, data in files.items():
        records.append((name, len(body)))
        body += _entry(0, data) + data  # the copy in front of the data has offset 0
    index = _fstring(mount) + struct.pack('<i', len(files))
    for (name, offset), data in zip(records, files.values()):
        index += _fstring(name) + _entry(offset, data)
    footer = struct.pack('<IIQQ', PAK_MAGIC, PAK_VERSION, len(body), len(index)) + hashlib.sha1(index).digest()
    path = Path(path)
    tmp = path.with_suffix('.tmp')
    tmp.write_bytes(body + index + footer)
    tmp.replace(path)


def check_pak(path):
    """Parses a pak back: (version, mount point, {name: size}); every file is read and hashed."""
    version, mount, entries = read_index(path)
    sizes = {}
    with open(path, 'rb') as f:
        raw = f.read()
    for name, entry in entries.items():
        offset, size, compression, _blocks = entry
        data = read_entry(path, entry, version)
        header = raw[offset:offset + 53]
        if not compression and (struct.unpack_from('<q', header, 8)[0] != size or
                                header[28:48] != hashlib.sha1(data).digest()):
            raise ValueError(f'{name}: entry header or hash does not match')
        sizes[name] = len(data)
    return version, mount, sizes


# -- config edits -------------------------------------------------------------------------------

def set_section(text, section, values):
    """Sets keys in the first [section] of an ini text, replacing existing lines there."""
    head, sep, rest = text.partition(f'[{section}]\n')
    if not sep:
        head, sep, rest = text.rstrip('\n') + '\n\n', f'[{section}]\n', ''
    lines = rest.split('\n')
    section_end = next((i for i, l in enumerate(lines) if l.startswith('[')), len(lines))
    body = [l for l in lines[:section_end] if l.strip() and l.split('=', 1)[0].strip() not in values]
    body += [f'{k}={v}' for k, v in values.items()] + ['']
    return head + sep + '\n'.join(body + lines[section_end:])


def set_values(ini, values, engine=None):
    """Sets keys in [SystemSettings] (console variables) and [/Script/Engine.Engine]."""
    text = ini.decode('utf-8-sig').replace('\r\n', '\n')
    if values:
        text = set_section(text, 'SystemSettings', values)
    if engine:
        text = set_section(text, '/Script/Engine.Engine', engine)
    return text.replace('\n', '\r\n').encode('utf-8')


# The game's own GPU heaps when its PS4Engine.ini does not set them (eboot 0x491d7c8, 0x491d7d0).
HEAP_DEFAULTS_MB = {'r.GarlicHeapSizeMB': 2600, 'r.OnionHeapSizeMB': 500}
# Of the extra heap memory (gpu_heap_extra_mb), this much goes to the onion heap (CPU-written GPU
# data; 300 MB, up to 228 MB used at 4K output), the rest to the garlic heap.
ONION_EXTRA_MB = 128


def heap_mb(ini, variable):
    """A heap size (r.GarlicHeapSizeMB, r.OnionHeapSizeMB) in the [SystemSettings] of a
    PS4Engine.ini (Matterfall: 2800 and 300)."""
    section = None
    for line in ini.decode('utf-8-sig', errors='replace').splitlines():
        line = line.strip()
        if line.startswith('['):
            section = line
        elif section == '[SystemSettings]' and '=' in line:
            key, value = (part.strip() for part in line.split('=', 1))
            if key.lower() == variable.lower() and value.isdigit():
                return int(value)
    return HEAP_DEFAULTS_MB[variable]


def frame_rate_range(fps):
    """UGameEngine::GetMaxTickRate on consoles: the game ticks at most at the upper bound of
    SmoothedFrameRateRange (Matterfall's DefaultEngine.ini: below 62, so 60 FPS) and t.MaxFPS.
    A higher bound lifts the 60 FPS cap."""
    return {'bSmoothFrameRate': 'False',
            'SmoothedFrameRateRange': '(LowerBound=(Type="ERangeBoundTypes::Inclusive",Value=22),'
                                      f'UpperBound=(Type="ERangeBoundTypes::Exclusive",Value={fps + 2}))'}


# Console commands in the Blueprints: "\x1f" (EX_StringConst) "<variable> <value>\0".
COMMAND = re.compile(rb'\x1f([A-Za-z]{1,6}\.[A-Za-z0-9_.]+) ([^\x00]*)\x00')


def edit_commands(data, values):
    """The Blueprint with its commands for `values` changed: the new value in place when it has
    the same length, else the command disabled ('r.' -> '#.'), so the ini value holds.
    Returns (data, [(variable, old, new)])."""
    out = bytearray(data)
    changes = []
    for match in COMMAND.finditer(data):
        name = match.group(1).decode('latin1')
        if name not in values:
            continue
        old = match.group(2).decode('latin1')
        new = str(values[name])
        if len(new.encode('latin1')) == len(old.encode('latin1')):
            out[match.start(2):match.end(2)] = new.encode('latin1')
            changes.append((name, old, new))
        else:
            out[match.start(1)] = ord('#')
            changes.append((name, old, '(ini)'))
    return bytes(out), changes


# -- the options ---------------------------------------------------------------------------------

# Render scale (matterfall.ini ue4_render_scale): r.ScreenPercentage of the game's 1920x1080 frame.
# 'console' keeps the PS4's own 84% (1613x907); above 100 the scene is drawn larger and scaled
# down to 1080p (supersampling: 200 = 3840x2160, 4K).
RENDER_SCALES = ('console', '50', '67', '75', '84', '100', '125', '133', '150', '167', '200')

# Matterfall's PS4 values (BP_EngineSettings on a base PS4 and the game's DefaultScalability):
# the Console preset changes nothing. Listed here for the other presets and the launcher.
CONSOLE = {
    'r.ScreenPercentage': '84', 'r.ShadowQuality': '3', 'r.AmbientOcclusionLevels': '0',
    'r.SSR.Quality': '1', 'r.MotionBlurQuality': '0', 'r.DepthOfFieldQuality': '1', 'r.BloomQuality': '4',
    'r.LensFlareQuality': '0', 'r.SceneColorFringeQuality': '0', 'r.EyeAdaptationQuality': '0',
    'r.PostProcessAAQuality': '4', 'r.LightShaftQuality': '1', 'r.Upscale.Quality': '2',
    'sg.TextureQuality': '3', 'sg.EffectsQuality': '1', 'sg.PostProcessQuality': '3',
}

# Individual settings: (matterfall.ini key, {level: console variables}). Levels 0 low, 1 medium,
# 2 console (the PS4: nothing written), 3 high, 4 ultra. Only variables UE 4.13 has (checked
# against the eboot's variable names; r.Shadow.MaxCSMResolution, r.VolumetricFog,
# grass.DensityScale and r.TemporalAA.Upsampling came later).
LEVELS = ('low', 'medium', 'console', 'high', 'ultra')
GROUPS = {
    'shadows': {
        'low': {'r.ShadowQuality': '1', 'r.Shadow.MaxResolution': '512', 'r.Shadow.CSM.MaxCascades': '1',
                'r.Shadow.DistanceScale': '0.6', 'r.Shadow.RadiusThreshold': '0.06'},
        'medium': {'r.ShadowQuality': '2', 'r.Shadow.MaxResolution': '1024', 'r.Shadow.CSM.MaxCascades': '2',
                   'r.Shadow.DistanceScale': '0.8', 'r.Shadow.RadiusThreshold': '0.05'},
        'high': {'r.ShadowQuality': '4', 'r.Shadow.MaxResolution': '2048', 'r.Shadow.CSM.MaxCascades': '4',
                 'r.Shadow.DistanceScale': '1.5', 'r.Shadow.RadiusThreshold': '0.02'},
        'ultra': {'r.ShadowQuality': '5', 'r.Shadow.MaxResolution': '4096', 'r.Shadow.CSM.MaxCascades': '4',
                  'r.Shadow.DistanceScale': '2', 'r.Shadow.RadiusThreshold': '0.01',
                  'r.Shadow.TexelsPerPixel': '2'},
    },
    'ambient_occlusion': {  # off on the PS4
        'low': {}, 'medium': {},
        'high': {'r.AmbientOcclusionLevels': '2', 'r.AmbientOcclusionMaxQuality': '100'},
        'ultra': {'r.AmbientOcclusionLevels': '3', 'r.AmbientOcclusionMaxQuality': '100'},
    },
    'reflections': {
        'low': {'r.SSR.Quality': '0'}, 'medium': {'r.SSR.Quality': '0'},
        'high': {'r.SSR.Quality': '3'}, 'ultra': {'r.SSR.Quality': '4', 'r.SSR.ResolutionScale': '1'},
    },
    'view_distance': {
        'low': {'r.ViewDistanceScale': '0.6', 'r.SkeletalMeshLODBias': '1'},
        'medium': {'r.ViewDistanceScale': '0.8'},
        'high': {'r.ViewDistanceScale': '1.5'},
        'ultra': {'r.ViewDistanceScale': '2', 'r.SkeletalMeshLODBias': '-1'},
    },
    'level_of_detail': {
        'low': {'r.StaticMeshLODDistanceScale': '1.5'}, 'medium': {'r.StaticMeshLODDistanceScale': '1.25'},
        'high': {'r.StaticMeshLODDistanceScale': '0.75', 'foliage.LODDistanceScale': '1.5'},
        'ultra': {'r.StaticMeshLODDistanceScale': '0.5', 'foliage.LODDistanceScale': '2',
                  'r.SkeletalMeshLODRadiusScale': '0.5'},
    },
    'foliage': {
        'low': {'foliage.DensityScale': '0.4'}, 'medium': {'foliage.DensityScale': '0.8'},
        'high': {}, 'ultra': {},
    },
    'effects': {  # particles, translucent lighting, refraction (the PS4: EffectsQuality 1)
        'low': {'r.EmitterSpawnRateScale': '0.25', 'r.RefractionQuality': '0', 'r.TranslucencyLightingVolumeDim': '24'},
        'medium': {'r.EmitterSpawnRateScale': '0.35', 'r.TranslucencyLightingVolumeDim': '32'},
        'high': {'r.TranslucencyLightingVolumeDim': '64', 'r.SSS.SampleSet': '2'},
        'ultra': {'r.EmitterSpawnRateScale': '1.0', 'r.TranslucencyLightingVolumeDim': '64', 'r.SSS.SampleSet': '2',
                  'r.ParticleLODBias': '-1'},
    },
    'post_process': {  # bloom, light shafts, lens flares (the game's look)
        'low': {'r.BloomQuality': '2', 'r.LightShaftQuality': '0', 'r.DepthOfFieldQuality': '0',
                'r.FastBlurThreshold': '0'},
        'medium': {'r.BloomQuality': '3'},
        'high': {'r.BloomQuality': '5', 'r.Upscale.Quality': '3'},
        'ultra': {'r.BloomQuality': '5', 'r.Upscale.Quality': '3', 'r.LensFlareQuality': '2',
                  'r.FastBlurThreshold': '100', 'r.Filter.SizeScale': '1'},
    },
    'detail': {  # r.DetailMode: small detail meshes and effects (the PS4: 1)
        'low': {'r.DetailMode': '0'}, 'medium': {}, 'high': {'r.DetailMode': '2'}, 'ultra': {'r.DetailMode': '2'},
    },
    'textures': {  # mip bias (lower = sharper); the PS4's streaming pool is kept (memory budget)
        'low': {'r.Streaming.MipBias': '1.5'}, 'medium': {'r.Streaming.MipBias': '1'},
        'high': {}, 'ultra': {'r.Streaming.MipBias': '-0.5', 'r.MipMapLODBias': '-0.5'},
    },
    'anisotropy': {  # also raised by the runtime's sampler override (GOW3_ANISOTROPY)
        'low': {'r.MaxAnisotropy': '2'}, 'medium': {'r.MaxAnisotropy': '4'},
        'high': {'r.MaxAnisotropy': '16'}, 'ultra': {'r.MaxAnisotropy': '16'},
    },
}
GROUP_NAMES = tuple(GROUPS)
# Quality presets: the level of every group ('console' = the PS4 for all).
PRESETS = ('low', 'medium', 'console', 'high', 'ultra')

# Effects with an on/off of their own: 'console' keeps the PS4's.
TOGGLES = {
    'motion_blur': ('r.MotionBlurQuality', {'off': '0', 'on': '3', 'high': '4'}),
    'depth_of_field': ('r.DepthOfFieldQuality', {'off': '0', 'on': '1', 'high': '2'}),
    'lens_flares': ('r.LensFlareQuality', {'off': '0', 'on': '2'}),
    'chromatic_aberration': ('r.SceneColorFringeQuality', {'off': '0', 'on': '1'}),
    'eye_adaptation': ('r.EyeAdaptationQuality', {'off': '0', 'on': '2'}),
}
# Anti-aliasing (r.PostProcessAAQuality): the PS4 runs temporal AA 4.
ANTI_ALIASING = {'console': None, 'taa_max': '6', 'taa_fast': '3', 'fxaa': '2', 'off': '0'}
# Sharpening in the game's tonemapper (r.Tonemapper.Sharpen, up to 10; off on the PS4).
SHARPEN = {'off': None, 'light': '0.5', 'medium': '1', 'strong': '2'}
# How a render scale below 100 is enlarged (r.Upscale.Quality): the PS4 uses 2 (4-tap bilinear).
UPSCALE_FILTER = {'console': None, 'sharp': '3', 'smooth': '1'}


def quality_values(options):
    """Console variables for the options (ini keys without the ue4_ prefix)."""
    values = {}
    preset = options.get('quality', 'console')
    if preset not in PRESETS:
        preset = 'console'
    for group, levels in GROUPS.items():
        level = options.get(group, 'preset')
        if level in ('preset', '', None):
            level = preset
        if level != 'console':
            values.update(levels.get(level, {}))
    for key, (variable, choices) in TOGGLES.items():
        value = choices.get(options.get(key, 'console'))
        if value is not None:
            values[variable] = value
    aa = ANTI_ALIASING.get(options.get('anti_aliasing', 'console'))
    if aa is not None:
        values['r.PostProcessAAQuality'] = aa
    sharpen = SHARPEN.get(options.get('sharpen', 'off'))
    if sharpen is not None:
        values['r.Tonemapper.Sharpen'] = sharpen
    upscale = UPSCALE_FILTER.get(options.get('upscale_filter', 'console'))
    if upscale is not None:
        values['r.Upscale.Quality'] = upscale
    scale = str(options.get('render_scale', 'console'))
    if scale != 'console' and scale in RENDER_SCALES:
        values['r.ScreenPercentage'] = scale
    return values


def apply(game, update=None, options=None, fps=60):
    """Writes or removes the override pak. Returns a short description of the active state."""
    options = options or {}
    pak = paks_dir(game) / PAK_NAME
    values = quality_values(options)
    engine = frame_rate_range(fps) if fps > 60 else {}
    if fps > 60:
        values['t.MaxFPS'] = str(fps)
    heap_extra = int(options.get('gpu_heap_extra_mb') or 0)
    if not values and not engine and not heap_extra:
        pak.unlink(missing_ok=True)
        return 'the game\'s own PS4 settings (render scale 84%, 60 FPS)'
    paks = game_paks(game, update)
    cache = {}
    config = read_file(paks, CONFIG, cache)
    if heap_extra:
        # The GPU heaps grow by the direct memory added above the PS4's (run_matterfall.py,
        # GOW3_DMEM_MB), so the CPU heap keeps its size. The game reads both at start from
        # [SystemSettings] (eboot 0x4cd480).
        onion = ONION_EXTRA_MB if heap_extra > ONION_EXTRA_MB else 0
        # One heap pool's free-list sizes are 32-bit (eboot 0x5e170): at most 4094 MB; the rest of a
        # larger GOW3_DMEM_MB then goes to the CPU heap.
        values['r.GarlicHeapSizeMB'] = str(min(heap_mb(config, 'r.GarlicHeapSizeMB') + heap_extra - onion, 4094))
        if onion:
            values['r.OnionHeapSizeMB'] = str(heap_mb(config, 'r.OnionHeapSizeMB') + onion)
    files = {CONFIG: set_values(config, values, engine)}
    edits = []
    for name in BLUEPRINTS:
        try:
            data, changes = edit_commands(read_file(paks, name, cache), values)
        except FileNotFoundError:
            continue
        if changes:
            files[name] = data
            edits += changes
    write_pak(pak, files)
    shown = ', '.join(f'{k}={v}' for k, v in values.items())
    blueprint = ', '.join(f'{n} {o}->{v}' for n, o, v in edits)
    return (f'{len(values)} settings ({shown})' + (f'; game commands changed: {blueprint}' if blueprint else '')
            + (f'; up to {fps} FPS' if fps > 60 else ''))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('game', type=Path, nargs='?')
    parser.add_argument('--update', type=Path)
    parser.add_argument('--check', type=Path, help='parse this pak back and list it')
    parser.add_argument('--render-scale', default='console', choices=RENDER_SCALES)
    parser.add_argument('--quality', default='console', choices=PRESETS)
    parser.add_argument('--fps', type=int, default=60, help='engine frame rate (60 = original)')
    args = parser.parse_args()
    if args.check:
        version, mount, sizes = check_pak(args.check)
        print(f'{args.check.name}: version {version}, mount {mount}, {len(sizes)} files')
        for name, size in sizes.items():
            print(f'  {name} ({size} bytes)')
        return
    if not args.game:
        parser.error('the game folder is needed')
    print('UE4 settings:', apply(args.game, args.update, {'render_scale': args.render_scale,
                                                          'quality': args.quality}, args.fps))


if __name__ == '__main__':
    main()
