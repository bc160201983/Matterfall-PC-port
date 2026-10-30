# Matterfall — PC port

Run the PS4 game **Matterfall** (Housemarque, 2017; CUSA02475) natively on Windows. The game's
own x86-64 code runs directly on the PC; a runtime supplies the PS4 system libraries, and a Vulkan
renderer executes the PS4 GPU work. There is no emulator in between.

By **BilalReloaded** ([YouTube](https://www.youtube.com/@BilalReloaded/videos),
[GitHub](https://github.com/bc160201983)), October 2026. Built on the
[Uncharted: The Nathan Drake Collection PC port](https://github.com/bc160201983/Uncharted-The-Nathan-Drake-Collection-PC-port)
and the [MediEvil PC port](https://github.com/bc160201983/medievil_2019_pc_port) (both on the
gow3_pc runtime and shadPS4's video core). What changed and when: [CHANGELOG.md](CHANGELOG.md).

> **No game files are in this repository or its builds.** You need your own copy of Matterfall
> (an unpacked CUSA02475 folder, or a fake package `.pkg` the launcher unpacks for you; update
> 1.01 is recommended). This project is not affiliated with Sony Interactive Entertainment or
> Housemarque. Matterfall is a trademark of its owners.

## What works

- Boot, intro movies, menus, saving and gameplay, tested on an RTX 5080 (level 1-1 and a
  30-minute session with no crash and no memory growth).
- Audio (Wwise through AudioOut), controller (DualSense, DualShock 4, Xbox and others through
  SDL3) and keyboard and mouse, all remappable.
- Correct sky lighting: the game reads a small sky-light table back from the GPU on the CPU; other
  PS4 emulators show wrong lighting there.
- Offline: PSN features (leaderboards, friends, store) answer as "signed out".

## System requirements

- Windows 10 or 11 (64-bit).
- A CPU from Intel's 4th-generation Core (Haswell) or newer, or any AMD Ryzen.
- A graphics card or integrated GPU with **Vulkan 1.3** and a current driver.
- About 6 GB of free RAM (16 GB in the PC recommended).

## Install and play

1. Download `Matterfall-windows.zip` from the [Releases](../../releases) page and extract it.
2. Start **Matterfall Launcher.exe**.
3. Choose your game folder (or **Install from PKG**). An update folder next to it
   (`CUSA02475-patch`) is found automatically.
4. Pick your settings and press **PLAY**.

## Settings (launcher)

- **Graphics:** presets Low, Medium, Console (the PS4's own settings), High and Ultra; render
  scale from 50% to 200% (the PS4 draws at 84%); shadows (maps up to 4096), ambient occlusion,
  reflections, view distance, level of detail, foliage, effects, post-processing, detail,
  textures, anisotropic filtering, motion blur, depth of field, lens flares, chromatic
  aberration, eye adaptation, anti-aliasing and sharpening.
- **Display:** windowed, borderless or fullscreen; window size; VSync; FPS counter; FSR 1 and
  sharpening.
- **Performance:** engine frame rate above 60 (experimental) and frame limits; background shader
  compilation and pipeline warm-up (shader cache kept between runs).
- **Controls:** keyboard, mouse and controller remapping.
- **Advanced:** install from PKG, save backups (made before every start), log and save folders,
  shader cache reset, desktop shortcut.

The game itself forces its render scale and some quality settings at every level load. The
launcher's settings therefore go into a small override package next to the game's own (named
`turrigun-ps4_zz_launcher_p.pak`), which holds edited copies of those two game settings files. It
is only written when a setting differs from the console default, and removed otherwise.

## Building from source

The runtime builds with MSYS2's CLANG64 toolchain (packages listed in
[gow3_pc/packaging/windows/README.md](gow3_pc/packaging/windows/README.md)):

```bash
git clone --recursive https://github.com/bc160201983/Matterfall-PC-port
cd Matterfall-PC-port
CXXFLAGS="-include cstdlib -include cstdio -include cwchar -include cmath -include new" gow3_pc/build.sh
python tools/run_matterfall.py --game <path to CUSA02475>
tools/package_matterfall.sh   # dist/Matterfall-windows.zip
```

Keep the repository's LF line endings (`git config core.autocrlf false`); the FSR patches do not
apply to CRLF files.

## Credits and licenses

- The runtime and renderer: gow3_pc (GPL-2.0), shadPS4's video core and shader recompiler
  (GPL-2.0), the Uncharted and MediEvil ports' fixes.
- Sky-light readback fix after bahamutfan64's shadPS4 Matterfall branch.
- Third-party licenses are in the package's `licenses` folder.
