#!/usr/bin/env python3
"""plan.json for MiaUI 2.0's Updater (schema miaui-update-plan/1): every file under
<stage>/rootfs goes to /, under <stage>/userdata to /userdata. Owner and mode are the
ones MiaUI 2.0.0 gives these files (see its own update's plan.json)."""
import hashlib, json, os, sys, time

stage = sys.argv[1]
# path on the console -> (mode, uid, gid), as in 2.0.0's plan
OWNERS = {
    "/opt/minui/bin/minui.elf": (0o777, 1000, 100),
    "/userdata/Cores/pcsx_rearmed_libretro.so": (0o666, 1000, 100),
    "/userdata/Tools/Collections.pak/launch.sh": (0o777, 1000, 100),
    "/userdata/Tools/Collections.pak/collections.py": (0o755, 1000, 100),
}
DIRS = [{"p": "/userdata/Tools/Collections.pak", "m": 0o777, "u": 1000, "g": 100}]
files, total = [], 0
for area, prefix in (("rootfs", ""), ("userdata", "/userdata")):
    base = os.path.join(stage, area)
    for root, _, names in os.walk(base):
        for n in sorted(names):
            src = os.path.join(root, n)
            rel = os.path.relpath(src, base)
            dest = prefix + "/" + rel
            data = open(src, "rb").read()
            mode, uid, gid = OWNERS[dest]
            files.append({"p": dest, "n": area + "/" + rel, "s": len(data),
                          "h": hashlib.md5(data).hexdigest(), "m": mode, "u": uid, "g": gid})
            total += len(data)
print(json.dumps({
    "schema": "miaui-update-plan/1",
    "version": "2.0.1",
    "from": ["2.0.0"],
    "created": time.strftime("%Y-%m-%d %H:%M:%S"),
    "image": "",
    "boot": False,
    "rootfs": any(f["n"].startswith("rootfs/") for f in files),
    "bytes": total,
    "files": files, "dirs": DIRS, "links": [], "meta": [], "delete": [], "rmdir": [],
}, indent=1))
