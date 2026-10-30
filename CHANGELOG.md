# Changelog

## 1.0.0 — 30 October 2026

First release.

- Matterfall (CUSA02475, 1.00 and update 1.01) boots, plays its movies, saves and plays through
  the tested levels at 60 FPS.
- Runtime: the Unreal Engine 4 system functions from the MediEvil port; offline PSN (NpToolkit2,
  NpManager, Matching2, Score, Tus, WebApi, WordFilter), Json2, keyboard IME, content export and
  DLC answers; `sceKernelAvailableDirectMemorySize`; working `sceHttpUriParse`/`Build`/`Escape`
  (fixes the 32 GB allocation crash); spare direct memory for render scales above 100%; Windows
  red-zone protection for functions that address locals through rbp.
- Renderer: the MediEvil UE4 fixes (CMask fill, 3D volume textures as 2D-array views, image
  suballocation, barrier batches of at most 128); the sky-light readback (small tiled render
  targets written back to guest memory, orphaned sky-cube sub-images merged); oversized recording
  data recorded directly, so threaded Vulkan recording and the draw pipe stay on.
- Fixed: a race when two threads join the same media thread; log spam from virtual memory
  reservations; `--timeout` on Windows.
- Launcher with quality presets and every UE4 quality and resolution setting, controls remapping,
  PKG install, save backups; packaged Windows build.
