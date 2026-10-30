Matterfall (PS4) - PC port (beta)
=================================
By BilalReloaded. Runs the PS4 game (CUSA02475, Unreal Engine 4.13) on Windows with a Vulkan
renderer. No game files are included: you need your own copy of the game.

Requirements
- Windows 10 or 11, 64-bit.
- A GPU with Vulkan 1.3 support and an up-to-date driver (NVIDIA, AMD or Intel).
- Your own Matterfall: the unpacked game folder CUSA02475 (eboot.bin, sce_sys, turrigun) and,
  recommended, its update 1.01 unpacked next to it as CUSA02475-patch. Fake PKGs of both can be
  unpacked by the launcher (ADVANCED -> Install from PKG).

How to play
1. Extract this whole folder anywhere (keep everything together), preferably on an internal SSD.
2. Start "Matterfall Launcher.exe".
3. Choose your game folder (click the game card, or ADVANCED -> Game folder). The update is found
   by itself when it sits next to the game as <game folder>-patch; else choose it there too.
4. Pick a quality preset (GRAPHICS) and press PLAY.
   In the game, Insert (keyboard) or R3 + L2 (controller) opens the port's menu: display mode,
   VSync, frame rate limit, overlay, controls.

What the settings do
- Render resolution: the size the 3D scene is drawn at (Unreal's r.ScreenPercentage of the
  game's 1920x1080 picture). The PS4 uses 84%. 100% is native 1080p; 133% renders 1440p, 200%
  renders 4K and scales it down (supersampling: much sharper, needs a strong GPU; an RTX 5080
  holds about 49 FPS in the title scene at 200% with the Ultra preset).
- Output size / display mode: the game always outputs a 1920x1080 picture, shown in a window
  of the size you choose, or on the whole screen (borderless or fullscreen). "Upscale with
  FSR 1" enlarges it to a 1440p or 4K screen more sharply than plain filtering.
- Quality presets: Console is exactly the PS4. High and Ultra go beyond it (bigger shadow maps,
  more shadow cascades, ambient occlusion, better reflections, longer view distance, full
  particles, 16x texture filtering). Low and Medium are for weaker GPUs. Every single setting
  can be changed on its own under GRAPHICS -> SINGLE SETTINGS.
- Engine frame rate: 60 is the PS4 original. 120 and 240 lift the engine's 60 FPS cap
  (experimental). Frame rate limit caps it again (Half refresh: e.g. 72 FPS on 144 Hz).
- These Unreal Engine settings are written into a small extra pak in the game's paks folder
  (turrigun\content\paks\turrigun-ps4_zz_launcher_p.pak) at every start, and removed when all
  settings are the PS4's. The game's own files are never changed.

Files
- matterfall.ini: every setting (the launcher and the in-game menu both use it).
- user\: saves (user\savedata), backups of them made before every start
  (user\savedata_backups, the last 10; ADVANCED -> Restore backup) and the shader cache.
- analysis\matterfall\boot.log: the log of the last start (ADVANCED -> Open log folder).

Not available for this game
- FSR 3.1, FSR 4 and DLSS: the runtime needs the game's motion vectors for them, which are only
  worked out for Uncharted. Unreal's own temporal upsampling came with a later engine (4.19).
- Native 1440p/4K output and other aspect ratios than 16:9: the PS4 renderer always outputs
  1920x1080 (use Render resolution for the detail of a higher resolution).

Troubleshooting
- The first start compiles shaders: expect stutter for a while; it goes away as the shader
  cache fills. ADVANCED -> Reset shader cache starts it again from nothing.
- If the game does not start, look at analysis\matterfall\boot.log and the launcher's own log,
  analysis\matterfall\launcher-last-run.log.
