# MiaUI v1.0.3 – Performance Update (PS1)

An update for an existing MiaUI v1.0.3 install. No new image needed: it replaces two files
through MiaUI's own Updater app.

## Installation

Requirement: MiaUI v1.0.3 already installed.

1. Download and extract `miaui-v1.0.3-perf-ps1.zip`. It contains an `Updater.pak` folder.
2. Copy the `Updater.pak` folder into the `Tools` folder of the card (ROMS partition, `/userdata/Tools`).
   - MiaUI's ROMS partition is ext4. On Windows, use a tool that can write ext4,
     or copy it over ADB (MiaUI's ADB app, in Tools):
     `adb push Updater.pak /userdata/Tools/`
3. On the console, open **Tools → Updater** and choose **Install Update**.
4. Wait for `UPDATE COMPLETED SUCCESSFULLY` and press A. The Updater disables itself afterwards.
5. In a game, open the menu (MENU) → Options and check that **Prevent Tearing** is set to
   **Lenient** (the PS1 default; if you had switched it to Off, set it back to Lenient).

Saves, states and settings are not touched. The update replaces only:

- `/opt/minui/bin/minarch.elf`
- `/userdata/Cores/pcsx_rearmed_libretro.so`

## What's new

PS1 on MiaUI was slow (dropping to ~30 FPS) even though the hardware can keep up.
The cause was in the frontend (minarch), not in the emulator. Fixes:

- **"Prevent Tearing: Lenient" now actually works.**
  It used to behave like "Strict": whenever a frame ran late, the game waited for the next
  vsync and dropped to 30 FPS. Now it only waits for vsync when the frame is on time.
- **The UI layer is no longer uploaded to the GPU on every frame during gameplay.**
  It is empty while you play, but the whole 640x480 layer was copied every frame, costing
  ~6 ms of the 16.6 ms budget. It is now drawn only in the menu or with the debug HUD on.
  This helps every system, not just PS1.
- **No more periodic hitch.**
  The RG35XX screen runs at 60.46 Hz and games at 60 Hz. The difference filled the audio
  buffer and made the game skip a frame every ~2 seconds. Audio now follows the screen's rate.
- **PCSX ReARMed updated (r23 from 2023 → r26 from 2026).**
  Adds threaded GPU rendering and the recent dynarec improvements.

Measured result (Tekken 3, Lenient): a steady 60.4 FPS, the screen's own rate, with ~4.7 ms
to spare per frame. Before: ~30 FPS. The other systems should benefit from the minarch fixes
too, but only PS1 was measured.

Credits: MiaUI by DSkywalk. PCSX ReARMed by its developers (GPLv2).

## Building

Needs Docker. From the repo root:

```
./perf-update/build.sh
```

Output in `perf-update/output/`: `minarch.elf`, `pcsx_rearmed_libretro.so` and the
`Updater.pak` zip. The build uses Debian bookworm's `arm-linux-gnueabihf` gcc (glibc 2.36),
because MiaUI ships glibc 2.37 and can't load binaries built against a newer glibc.
The PCSX ReARMed commit is pinned in `cores/makefile` (`pcsx_rearmed_HASH`).

## Measuring

Set `MINARCH_FPS_LOG=1` before starting `minarch.elf` (e.g. in an Emus pak's `launch.sh`,
with stdout sent to a file) and it prints one line per second:

```
PERF mode=1 fps_x10=604 game=61 slow=0 worst_ms=16 vsync_on=61 | avg_us emu=10521 (audio_wait=0) upload=1254 ui=9 swap=4753
```

`mode` is Prevent Tearing (0 Off, 1 Lenient, 2 Strict), `slow` counts frames over 17.5 ms,
`emu` is the time between flips (emulation plus audio wait), `upload` the game texture,
`ui` the UI layer, and `swap` eglSwapBuffers (which waits for vsync on this driver).
The counters use integer math only: the PCSX NEON code leaves the VFP registers dirty,
so doubles computed in minarch come out as nan/inf.
