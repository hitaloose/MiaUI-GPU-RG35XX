# MiaUI 2.0.1 – Collections + PCSX ReARMed fix

An update for a console already on **MiaUI 2.0.0**, installed through MiaUI's own Updater
app. Most of the earlier `perf-ps1` / `perf-audio` updates are already part of
2.0.0 (Lenient vsync, the UI layer on the GPU, audio paced by the measured screen rate,
PCSX ReARMed r26), so this one only adds what 2.0.0 doesn't have.

Do **not** install the old `miaui-v1.0.3-*` updates on 2.0: they were built for 1.0.3 and
would put older binaries over 2.0's.

## Installation

Requirement: MiaUI 2.0.0 already installed.

1. Download and extract `miaui-v2.0.1-update.zip`. It contains an `Updater.pak` folder.
2. Copy the `Updater.pak` folder into the `Tools` folder of the card (`/userdata/Tools`),
   for example with 2.0's web manager, or over ADB: `adb push Updater.pak /userdata/Tools/`
3. On the console, open **Tools → Updater** and install it.

Saves, states, settings and your collections are not touched. The update writes only:

- `/opt/minui/bin/minui.elf`
- `/userdata/Cores/pcsx_rearmed_libretro.so`
- `/userdata/Tools/Collections.pak/` (new)

## Collections from the game list

Collections are the lists in **Collections** at the top of the main menu: each one is a
`/userdata/Collections/<name>.txt` file with one path per line (`/Roms/<system>/<file>` for a
ROM, `/Ports/<name>.pak` for a port). In 2.0.0 they can only be edited by hand. Now the
work is split in two: the main menu puts games in lists, a tool manages the lists.

### In the main menu: Y puts a game in a list

- **Y on a game or a port** (in any system, in Ports, in Recently Played or inside a
  collection) opens the list of collections, with a box checked on the ones that already have
  it. **A** adds or removes it (saved right away), **B** closes. The `Y LISTS` hint shows at
  the bottom when a game is selected.
- A port opened from a collection brings you back to that collection when you quit it,
  like ROMs already did.
- The menu never creates or deletes a list: with none yet, Y points to the tool.
- Lists are written through a temporary file and renamed, so a power loss while saving
  can't leave a list half written. Order is kept, new games go to the end.
- **MENU + SELECT + START inside a collection removes the game from that list only.**
  Elsewhere this hidden shortcut still deletes the ROM file; inside a collection it used to
  delete the ROM too.
- English and Spanish texts, like the rest of 2.0's menu.

### Tools → Collections: create, rename and delete lists

- **+ New collection** opens an on-screen keyboard (the same layout and buttons as the
  RetroAchievements login: X changes keys, B deletes, START is done, MENU cancels).
- **A** on a list renames it, **X** deletes it after asking. Deleting removes only the
  list, never the games.
- With no list at all, it offers to create the usual ones: Backlog, Playing, Paused, Beaten
  and Abandoned.
- Names can't be empty, start with a dot, have `/` or `\`, or repeat another list's name.
  Every write goes through a temporary file and a rename.
- It shows how many games each list has, in English or Spanish like the system.

## PCSX ReARMed: NEON code keeps d8-d15

Three of its NEON routines (the SPU channel mixers `mix_chan`/`mix_chan_rvb` and the GTE
`gteRTPT_sf1lm0_neon`) wrote d8-d15, which the ARM calling convention says a function must
give back unchanged. 2.0's minarch already protects itself from this (`Core_callSavingVFP`),
so this is a fix in the core itself: the routines now use d16-d31, the same instructions with
no speed cost, and the core's own C code is safe too. Checked on the device by filling d8-d15
with a known pattern around every frame (Bloody Roar): before, 556 of 2700 frames came back
changed; after, 0 of 6000.

Credits: MiaUI by DSkywalk. PCSX ReARMed by its developers (GPLv2).

## Building

Needs Docker. From the repo root:

```
./perf-update/build.sh
```

Output in `perf-update/output/`: `minui.elf`, `pcsx_rearmed_libretro.so` and
`miaui-v2.0.1-update.zip`. The build uses Debian bookworm's `arm-linux-gnueabihf` gcc
(glibc 2.36), because MiaUI ships glibc 2.37 and can't load binaries built against a newer
one. The package uses 2.0's Updater (`perf-update/updater/local_updater.py`, from the 2.0.0
release) and a `plan.json` written by `perf-update/docker/make_plan.py`.
