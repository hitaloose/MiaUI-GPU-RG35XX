# MiaUI v1.0.3 – Performance Update (PS1, audio) + Collections

An update for an existing MiaUI v1.0.3 install. No new image needed: it replaces three files
through MiaUI's own Updater app. It includes everything from the earlier `perf-ps1` and `perf-collections` updates.

## Installation

Requirement: MiaUI v1.0.3 already installed (with or without the earlier updates).

1. Download and extract `miaui-v1.0.3-perf-audio.zip`. It contains an `Updater.pak` folder.
2. Copy the `Updater.pak` folder into the `Tools` folder of the card (ROMS partition, `/userdata/Tools`).
   - MiaUI's ROMS partition is ext4. On Windows, use a tool that can write ext4,
     or copy it over ADB (MiaUI's ADB app, in Tools):
     `adb push Updater.pak /userdata/Tools/`
3. On the console, open **Tools → Updater** and choose **Install Update**.
4. Wait for `UPDATE COMPLETED SUCCESSFULLY` and press A. The Updater disables itself afterwards
   (it now replaces the disabled copy a previous update left in Tools, which used to fail with
   "Failed to rename Updater.pak folder").
5. In a game, open the menu (MENU) → Options and check that **Prevent Tearing** is set to
   **Lenient** (the PS1 default; if you had switched it to Off, set it back to Lenient).

Saves, states, settings and your collections are not touched. The update replaces only:

- `/opt/minui/bin/minarch.elf`
- `/opt/minui/bin/minui.elf`
- `/userdata/Cores/pcsx_rearmed_libretro.so`

## Collections from the game list

Collections are the lists in **Collections** at the top of the main menu: each one is a
`/userdata/Collections/<name>.txt` file with one path per line (`/Roms/<system>/<file>` for a
ROM, `/Ports/<name>.pak` for a port). Until now they could only be edited by hand. Now:

- **Y on a game or a port** (in any system, in Ports, in Recently Played or inside a collection) opens the list
  of collections, with a box checked on the ones that already have the game.
  **A** adds or removes it (saved right away), **B** closes. A game can be in any number of
  collections. The `Y LISTS` hint shows at the bottom when a game is selected.
- A port opened from a collection brings you back to that collection when you quit it,
  like ROMs already did.
- **Default collections**: Backlog, Playing, Beaten and Abandoned are created (empty) when the
  Collections folder has no list at all. Lists you already have are never changed.
  Any `.txt` you add to the folder shows up in the Y list too.
- Lists are written through a temporary file and renamed, so a power loss while saving
  can't leave a list half written. Order is kept, new games go to the end.
- **MENU + SELECT + START inside a collection now removes the game from that list only.**
  This is MiaUI's hidden delete shortcut: elsewhere it still deletes the ROM file, but inside a
  collection it used to delete the ROM too.

This `minui.elf` is built from the current source, so it also brings the upstream minui changes
made after the v1.0.3 image: the hidden delete shortcut above, a fix for MAME clone names and a
small render optimization.

## Performance (PS1)

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
  The RG35XX screen runs at 60.46 Hz, not 60, while games run at their own ~60 Hz. The
  difference filled the audio buffer and made the game skip a frame every ~2 seconds. The
  screen's rate is now measured while you play (vsync periods over ~2 s windows, integer
  math only) and the audio input rate follows it, instead of a rate fixed in the code.
- **PCSX ReARMed updated (r23 from 2023 → r26 from 2026).**
  Adds threaded GPU rendering and the recent dynarec improvements.
- **PCSX ReARMed no longer corrupts the frontend's floating point registers.**
  Three of its NEON routines (the SPU channel mixers `mix_chan`/`mix_chan_rvb` and the GTE
  `gteRTPT_sf1lm0_neon`) wrote d8-d15, which the ARM calling convention says a function
  must give back unchanged, so any `double` minarch held across a frame came back as garbage
  (nan). They now use d16-d31 instead: same instructions, no speed cost. Checked on the
  device by filling d8-d15 with a known pattern around every frame (Bloody Roar): before,
  556 of 2700 frames came back changed; after, 0 of 6000.

Measured result (Tekken 3, Lenient): a steady 60.4 FPS, the screen's own rate, with ~4.7 ms
to spare per frame. Before: ~30 FPS. The other systems should benefit from the minarch fixes
too, but only PS1 was measured.

Credits: MiaUI by DSkywalk. PCSX ReARMed by its developers (GPLv2).

## Building

Needs Docker. From the repo root:

```
./perf-update/build.sh
```

Output in `perf-update/output/`: `minarch.elf`, `minui.elf`, `pcsx_rearmed_libretro.so` and the
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
The counters use integer math only: with an unpatched PCSX ReARMed, its NEON code clobbers
d8-d15, so doubles held in minarch come out as nan/inf (fixed in this update's core, see above).
