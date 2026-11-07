#!/usr/bin/env python3
"""MiaUI updater, on the console itself.

Installs the update_<crc32>.tar.gz beside this script, made by
00_RELEASE/release-diff-manager/release_diff_manager.py. The tarball starts
with plan.json, which says what to do:

    files    written under / (rootfs/...), /userdata (userdata/...) or the
             boot partition (boot/...); each to a temporary name first and
             then renamed over the old one, so a file is either old or new,
             never half written. "k" (files and links): only if the card
             doesn't have that path yet - a user's saves are never replaced.
    dirs, links, meta   new folders and links, and owner/mode fixes
    delete, rmdir       files that went away; a folder only if it's empty
                        afterwards (a user's own files keep it)
    boot     the boot partition (p1, not mounted while the console runs) has
             changes: it's mounted for the update and unmounted after

Logs go to /tmp only (RAM). If something fails, the update file stays and the
update can simply be run again.

Testing on a PC: UPDATER_ROOT (a folder standing for /), UPDATER_BOOT (one
standing for the boot partition) and --headless (no screen, progress on the
terminal, installs without asking).
"""
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tarfile
import textwrap
import threading
import time
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))

# --- Rutas ---
UPDATE_DIR = os.environ.get("UPDATER_DIR", HERE)
ROOT = os.environ.get("UPDATER_ROOT", "/")
TEST_BOOT = os.environ.get("UPDATER_BOOT")
REAL = ROOT == "/"
BOOT_MNT = "/tmp/miaui-boot"
LOG_FILE = "/tmp/miaui-update.log"
LANG_CONF = "/userdata/Profile/language.conf"
FONT = "/opt/minui/res/BPreplayBold-unhinted.otf"
BATTERY = "/sys/class/power_supply/battery"
PLAN_SCHEMA = "miaui-update-plan/1"
MIN_BATTERY = 20   # % below which, without the charger, it won't start

# --- Mapeo de botones ---
BTN_A = 0
BTN_B = 1
BTN_MENU = 10
BTN_UP = 13
BTN_DOWN = 14
BTN_LEFT = 15
BTN_RIGHT = 16

# --- Colores (los de sdtool / scrapper / RetroAchievements) ---
BG = (30, 30, 30)
WHITE = (255, 255, 255)
GREY = (200, 200, 200)
DIM = (150, 150, 150)
GREEN = (50, 255, 50)
SOFT_GREEN = (150, 255, 150)
YELLOW = (255, 200, 50)
RED = (255, 100, 100)


def get_language():
    if os.path.exists(LANG_CONF):
        try:
            with open(LANG_CONF, "r", encoding="utf-8") as f:
                if "es" in f.read().strip().lower():
                    return "es"
        except Exception:
            pass
    return "en"


def load_texts(lang):
    texts = {
        "en": {
            "title": "MiaUI Updater",
            "opt_install": "Install update",
            "opt_details": "What does it change?",
            "opt_exit": "Exit",
            "inst_a": "Button A: Select",
            "inst_nav": "D-Pad Up/Down: Navigate",
            "inst_menu": "MENU Button: Exit",
            "checking": "Checking the update file...",
            "checked": "Checked: {}%",
            "hdr_version": "Update to: MiaUI {}",
            "hdr_from": "For: MiaUI {}",
            "st_ready": "[OK] Update checked. Ready to install.",
            "st_missing": "No update file found.",
            "st_multiple": "More than one update file found.",
            "st_format": "The update file's name is not valid.",
            "st_corrupt": "The update file is damaged (bad CRC).",
            "st_plan": "This update file can't be read.",
            "st_help": "'update_XXXXXXXX.tar.gz' must be inside 'Updater.pak'.",
            "sum_files": "Files to copy: {} ({})",
            "sum_delete": "Files to remove: {}",
            "sum_boot": "The boot partition is updated too.",
            "details_title": "What the update does",
            "d_rootfs": "System files: {}",
            "d_userdata": "Card files (Emus, Cores, Tools...): {}",
            "d_boot": "Boot partition files: {}",
            "d_delete": "Files removed: {}   Folders removed: {}",
            "d_links": "Links: {}   Folders: {}   Permissions: {}",
            "d_keep": "Kept if you already have them: {}",
            "d_size": "Total to copy: {}",
            "confirm_q": "Install MiaUI {}?",
            "confirm_1": "Keep the console on until it finishes.",
            "confirm_2": "It takes a few minutes.",
            "confirm_inst": "Press A to INSTALL  |  Press B to CANCEL",
            "battery_title": "The battery is too low ({}%).",
            "battery_1": "Connect the charger and try again.",
            "press_a": "Press A to continue.",
            "installing": "Installing update",
            "ph_prepare": "Getting ready...",
            "ph_boot_mount": "Opening the boot partition...",
            "ph_dirs": "Creating folders...",
            "ph_files": "Copying files",
            "ph_boot": "Updating the boot partition",
            "ph_links": "Creating links...",
            "ph_meta": "Setting permissions...",
            "ph_delete": "Removing old files...",
            "ph_finish": "Saving everything to the card...",
            "progress": "Progress: {}%   ({} / {})",
            "file_n": "File {} / {}",
            "do_not_off": "Do not turn the console off.",
            "done_title": "Update completed!",
            "done_files": "Files copied: {}",
            "done_kept": "Already yours, kept: {}",
            "done_deleted": "Files removed: {}",
            "done_dirs_kept": "Folders kept (they have your files): {}",
            "done_restart": "The console must restart to finish.",
            "press_a_reboot": "Press A to restart now.",
            "rebooting": "Restarting...",
            "fail_title": "The update could not finish:",
            "fail_1": "The update file is kept: you can run it again.",
            "fail_2": "Press A to see the log.",
            "log_title": "Log",
            "log_inst": "D-Pad Up/Down: Scroll   |   Button A: Continue",
            "err_space": "Not enough free space in {}: needs {}, has {}.",
            "space_title": "Not enough free space",
            "space_row": "Needs {}, only {} free.",
            "space_more": "{} more is needed there.",
            "space_more_user": "Free {} (delete some ROMs or files).",
            "space_inodes": "Room for {} more files, needs {}.",
            "space_none": "Nothing was changed.",
            "area_rootfs": "System (/)",
            "area_userdata": "User data (/userdata)",
            "area_boot": "Boot partition",
            "err_boot": "The boot partition could not be opened.",
            "err_rw": "The system could not be unlocked for writing.",
            "err_md5": "A file was damaged while copying: {}",
            "err_folder": "There is a folder where a file should go: {}",
        },
        "es": {
            "title": "Actualizador de MiaUI",
            "opt_install": "Instalar actualización",
            "opt_details": "¿Qué cambia?",
            "opt_exit": "Salir",
            "inst_a": "Botón A: Seleccionar",
            "inst_nav": "D-Pad Arriba/Abajo: Navegar",
            "inst_menu": "Botón MENU: Salir",
            "checking": "Comprobando el archivo de actualización...",
            "checked": "Comprobado: {}%",
            "hdr_version": "Actualiza a: MiaUI {}",
            "hdr_from": "Para: MiaUI {}",
            "st_ready": "[OK] Actualización comprobada. Lista para instalar.",
            "st_missing": "No se ha encontrado ningún archivo de actualización.",
            "st_multiple": "Hay más de un archivo de actualización.",
            "st_format": "El nombre del archivo de actualización no es válido.",
            "st_corrupt": "El archivo de actualización está dañado (mal CRC).",
            "st_plan": "Este archivo de actualización no se puede leer.",
            "st_help": "'update_XXXXXXXX.tar.gz' debe estar dentro de 'Updater.pak'.",
            "sum_files": "Archivos a copiar: {} ({})",
            "sum_delete": "Archivos a borrar: {}",
            "sum_boot": "También se actualiza la partición de arranque.",
            "details_title": "Qué hace la actualización",
            "d_rootfs": "Archivos del sistema: {}",
            "d_userdata": "Archivos de la tarjeta (Emus, Cores, Tools...): {}",
            "d_boot": "Archivos de arranque: {}",
            "d_delete": "Archivos borrados: {}   Carpetas borradas: {}",
            "d_links": "Enlaces: {}   Carpetas: {}   Permisos: {}",
            "d_keep": "Se respetan si ya los tienes: {}",
            "d_size": "Total a copiar: {}",
            "confirm_q": "¿Instalar MiaUI {}?",
            "confirm_1": "No apagues la consola hasta que termine.",
            "confirm_2": "Tarda unos minutos.",
            "confirm_inst": "Pulsa A para INSTALAR  |  Pulsa B para CANCELAR",
            "battery_title": "Queda poca batería ({}%).",
            "battery_1": "Conecta el cargador y vuelve a intentarlo.",
            "press_a": "Pulsa A para continuar.",
            "installing": "Instalando la actualización",
            "ph_prepare": "Preparando...",
            "ph_boot_mount": "Abriendo la partición de arranque...",
            "ph_dirs": "Creando carpetas...",
            "ph_files": "Copiando archivos",
            "ph_boot": "Actualizando la partición de arranque",
            "ph_links": "Creando enlaces...",
            "ph_meta": "Poniendo permisos...",
            "ph_delete": "Borrando archivos antiguos...",
            "ph_finish": "Guardando todo en la tarjeta...",
            "progress": "Progreso: {}%   ({} / {})",
            "file_n": "Archivo {} / {}",
            "do_not_off": "No apagues la consola.",
            "done_title": "¡Actualización completada!",
            "done_files": "Archivos copiados: {}",
            "done_kept": "Ya eran tuyos, respetados: {}",
            "done_deleted": "Archivos borrados: {}",
            "done_dirs_kept": "Carpetas respetadas (tienen archivos tuyos): {}",
            "done_restart": "La consola debe reiniciarse para terminar.",
            "press_a_reboot": "Pulsa A para reiniciar ahora.",
            "rebooting": "Reiniciando...",
            "fail_title": "La actualización no ha podido terminar:",
            "fail_1": "El archivo se conserva: puedes volver a lanzarla.",
            "fail_2": "Pulsa A para ver el registro.",
            "log_title": "Registro",
            "log_inst": "D-Pad Arriba/Abajo: Mover   |   Botón A: Continuar",
            "err_space": "No hay espacio libre en {}: necesita {}, hay {}.",
            "space_title": "No hay espacio libre suficiente",
            "space_row": "Necesita {}, solo hay {} libres.",
            "space_more": "Faltan {} en esa partición.",
            "space_more_user": "Libera {} (borra algunas ROMs o archivos).",
            "space_inodes": "Caben {} archivos más, necesita {}.",
            "space_none": "No se ha cambiado nada.",
            "area_rootfs": "Sistema (/)",
            "area_userdata": "Datos (/userdata)",
            "area_boot": "Partición de arranque",
            "err_boot": "No se ha podido abrir la partición de arranque.",
            "err_rw": "No se ha podido desbloquear el sistema para escribir.",
            "err_md5": "Un archivo se ha dañado al copiarlo: {}",
            "err_folder": "Hay una carpeta donde debería ir un archivo: {}",
        },
    }
    return texts.get(lang, texts["en"])


def human(n):
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%d %s" % (n, unit)) if unit == "B" else ("%.1f %s" % (n, unit))
        n /= 1024


# --- REGISTRO (sólo en /tmp) ---

class Log:
    def __init__(self):
        self.lines = []
        try:
            self.f = open(LOG_FILE, "a", encoding="utf-8")
        except OSError:
            self.f = None

    def __call__(self, msg):
        line = "%s %s" % (time.strftime("%H:%M:%S"), msg)
        self.lines.append(line)
        if self.f:
            self.f.write(line + "\n")
            self.f.flush()
        if HEADLESS:
            print(line, flush=True)


HEADLESS = "--headless" in sys.argv


# --- COMPROBACIÓN DEL ARCHIVO ---

class Checker(threading.Thread):
    """Finds the update file, checks its CRC (the one in its name) and reads
    its plan, off the screen's thread so the bar moves."""

    def __init__(self):
        super().__init__(daemon=True)
        self.status, self.path, self.plan = "CHECKING", None, None
        self.done, self.total = 0, 1

    def run(self):
        try:
            self.status = self.check()
        except Exception:  # noqa: BLE001 - a bad file is a status, not a crash
            self.status = "PLAN"

    def check(self):
        # listdir, not glob: a folder like "1) System [DRK]" holds glob
        # wildcards ([DRK] is a character class) and glob finds nothing there
        try:
            names = os.listdir(UPDATE_DIR)
        except OSError:
            names = []
        found = sorted(os.path.join(UPDATE_DIR, n) for n in names
                       if n.startswith("update_") and n.endswith(".tar.gz")
                       and os.path.isfile(os.path.join(UPDATE_DIR, n)))
        if not found:
            return "MISSING"
        if len(found) > 1:
            return "MULTIPLE"
        path = found[0]
        m = re.match(r"update_([0-9a-fA-F]{8})\.tar\.gz$", os.path.basename(path))
        if not m:
            return "FORMAT"
        self.total = os.path.getsize(path) or 1
        crc = 0
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                crc = zlib.crc32(chunk, crc)
                self.done += len(chunk)
        if "%08x" % (crc & 0xFFFFFFFF) != m.group(1).lower():
            return "CORRUPT"
        self.plan = read_plan(path)
        self.path = path
        return "READY"


def read_plan(path):
    with tarfile.open(path, "r|gz") as tar:
        first = tar.next()
        if first is None or first.name != "plan.json":
            raise ValueError("no plan.json")
        plan = json.loads(tar.extractfile(first).read().decode("utf-8"))
    if plan.get("schema") != PLAN_SCHEMA:
        raise ValueError("unknown plan")
    return plan


# --- INSTALACIÓN ---

class UpdateError(Exception):
    pass


class SpaceError(UpdateError):
    """Not enough room: rows are the partitions that fall short (see space_rows)."""

    def __init__(self, msg, rows):
        super().__init__(msg)
        self.rows = rows


def busy_files():
    """Files running programs have open as code (their binary, their .so).
    Replacing one doesn't free its old blocks until that program exits."""
    out = set()
    if not REAL:
        return out
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            out.add(os.readlink("/proc/%s/exe" % pid))
        except OSError:
            pass
        try:
            with open("/proc/%s/maps" % pid) as f:
                for line in f:
                    i = line.find("/")
                    if i >= 0:
                        out.add(line[i:].rstrip("\n").replace(" (deleted)", ""))
        except OSError:
            pass
    return out


def area_of(path):
    if path.startswith("boot:/"):
        return "boot"
    return "userdata" if path == "/userdata" or path.startswith("/userdata/") else "rootfs"


def proc_mounts():
    out = []
    try:
        with open("/proc/mounts") as f:
            for line in f:
                p = line.split()
                if len(p) >= 4:
                    out.append((p[0], p[1].replace("\\040", " "), p[2], p[3]))
    except OSError:
        pass
    return out


def boot_device():
    """p1 of the card /userdata is on (mmcblk0 normally)."""
    for src, mnt, _fs, _opt in proc_mounts():
        if mnt == "/userdata":
            m = re.match(r"(/dev/mmcblk\d+)p\d+$", src)
            if m:
                return m.group(1) + "p1"
    return "/dev/mmcblk0p1"


def battery():
    """(percent, charging) or None where there's no battery to read."""
    try:
        with open(os.path.join(BATTERY, "capacity")) as f:
            cap = int(f.read().strip())
        with open(os.path.join(BATTERY, "charger_online")) as f:
            charging = f.read().strip() == "1"
        return cap, charging
    except (OSError, ValueError):
        return None


class Installer(threading.Thread):
    def __init__(self, plan, path, t):
        super().__init__(daemon=True)
        self.plan, self.path, self.t = plan, path, t
        self.log = Log()
        self.lock = threading.Lock()
        self.s = {"phase": "ph_prepare", "file": "", "done": 0, "total": 1, "n": 0,
                  "files": len(plan["files"]), "copied": 0, "kept": 0, "deleted": 0,
                  "dirs_kept": 0, "error": None, "space": None, "finished": False}
        self.boot_dir = None
        self.boot_mounted = False     # we mounted it: we unmount it
        self.boot_remounted = False   # it was mounted read-only: back to ro
        self.root_rw = False
        self.is_root = hasattr(os, "geteuid") and os.geteuid() == 0
        small = len(plan["dirs"]) + len(plan["links"]) + len(plan["meta"]) + \
            len(plan["delete"]) + len(plan["rmdir"])
        self.unit = 4096   # what a folder, link or deletion weighs on the bar
        self.set(total=max(1, plan["bytes"] + small * self.unit))

    # the state the screen reads
    def set(self, **kw):
        with self.lock:
            self.s.update(kw)

    def add(self, key, n=1):
        with self.lock:
            self.s[key] += n

    def state(self):
        with self.lock:
            return dict(self.s)

    def run(self):
        self.log("update %s -> MiaUI %s (%s)" % (os.path.basename(self.path), self.plan.get("version"),
                                                 ", ".join(self.plan.get("from") or [])))
        try:
            self.install()
            self.log("done")
        except SpaceError as e:
            self.log("ERROR: %s" % e)
            self.set(error=str(e), space=e.rows)
        except UpdateError as e:
            self.log("ERROR: %s" % e)
            self.set(error=str(e))
        except Exception as e:  # noqa: BLE001 - shown on screen, not a crash
            self.log("ERROR: %s: %s" % (type(e).__name__, e))
            self.set(error="%s: %s" % (type(e).__name__, e))
        finally:
            self.cleanup()
            self.set(finished=True)

    # where a plan path lands
    def target(self, path):
        if path.startswith("boot:/"):
            base, rel = self.boot_dir, path[len("boot:/"):]
        else:
            base, rel = ROOT, path.lstrip("/")
        parts = rel.split("/")
        if not rel or any(p in ("", ".", "..") for p in parts):
            raise UpdateError("bad path in the update: %s" % path)
        return os.path.join(base, *parts)

    def install(self):
        plan, t = self.plan, self.t
        if plan.get("boot"):
            self.set(phase="ph_boot_mount")
            self.open_boot()
        self.check_space()   # every partition, before anything is written
        if plan.get("rootfs") and REAL:
            if os.system("mount -o remount,rw /") != 0:
                raise UpdateError(t["err_rw"])
            self.root_rw = True
            self.log("rootfs remounted rw")

        self.set(phase="ph_dirs")
        for d in plan["dirs"]:
            p = self.target(d["p"])
            if not os.path.isdir(p):
                os.makedirs(p)
            self.own(p, d)
            self.add("done", self.unit)

        self.set(phase="ph_files")
        files = {f["n"]: f for f in plan["files"]}
        with tarfile.open(self.path, "r|gz") as tar:
            for m in tar:
                if m.name == "plan.json":
                    continue
                f = files.get(m.name)
                if f is None or not m.isfile():
                    raise UpdateError("unexpected file in the update: %s" % m.name)
                boot = f["p"].startswith("boot:/")
                self.set(phase="ph_boot" if boot else "ph_files", file=f["p"].replace("boot:/", "/"))
                self.add("n")
                self.write(f, tar.extractfile(m), boot)

        self.set(phase="ph_links", file="")
        for ln in plan["links"]:
            p = self.target(ln["p"])
            if ln.get("k") and os.path.lexists(p):
                self.add("kept")
                self.log("kept yours: %s" % ln["p"])
            elif os.path.isdir(p) and not os.path.islink(p):
                self.log("kept: a folder where a link goes: %s" % ln["p"])
            else:
                if os.path.lexists(p):
                    os.unlink(p)
                os.makedirs(os.path.dirname(p), exist_ok=True)
                os.symlink(ln["l"], p)
                if self.is_root and "u" in ln:
                    os.lchown(p, ln["u"], ln["g"])
            self.add("done", self.unit)

        self.set(phase="ph_meta")
        for e in plan["meta"]:
            p = self.target(e["p"])
            if os.path.lexists(p) and not os.path.islink(p):
                self.own(p, e)
            self.add("done", self.unit)

        self.set(phase="ph_delete")
        for path in plan["delete"]:
            p = self.target(path)
            if os.path.islink(p) or os.path.isfile(p):
                os.unlink(p)
                self.add("deleted")
                self.log("removed %s" % path)
            elif os.path.isdir(p):
                self.log("kept: a folder where a file was: %s" % path)
            self.add("done", self.unit)
        for path in plan["rmdir"]:   # deepest first
            p = self.target(path)
            if os.path.isdir(p) and not os.path.islink(p):
                try:
                    os.rmdir(p)
                    self.log("removed folder %s" % path)
                except OSError:
                    self.add("dirs_kept")
                    self.log("kept folder (not empty) %s" % path)
            self.add("done", self.unit)

        self.set(phase="ph_finish", file="")
        os.sync()

    def own(self, p, e):
        """Owner and mode as in the image (ext4 only: FAT has neither)."""
        if "m" not in e:
            return
        if self.is_root:
            os.chown(p, e["u"], e["g"])
        os.chmod(p, e["m"])   # after chown, which clears setuid bits

    def write(self, f, src, boot):
        p = self.target(f["p"])
        if f.get("k") and os.path.lexists(p):
            self.add("kept")
            self.log("kept yours: %s" % f["p"])
            self.add("done", f["s"])
            return
        if os.path.isdir(p) and not os.path.islink(p):
            raise UpdateError(self.t["err_folder"].format(f["p"]))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".miaui-new"
        h = hashlib.md5()
        try:
            with open(tmp, "wb") as out:
                for chunk in iter(lambda: src.read(1 << 18), b""):
                    out.write(chunk)
                    h.update(chunk)
                    self.add("done", len(chunk))
                if boot:
                    out.flush()
                    os.fsync(out.fileno())
            if h.hexdigest() != f["h"]:
                raise UpdateError(self.t["err_md5"].format(f["p"]))
            self.own(tmp, f)
            if os.path.islink(p):
                os.unlink(p)
            os.replace(tmp, p)
        except BaseException:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
        self.add("copied")

    def space_rows(self, with_boot):
        """What the plan needs on each partition it writes to, against what is
        free there: [{area, where, need, free, inodes, ifree, ok}].

        Worst case, so the install never runs out half way:
        - every file counts in whole blocks of its partition (4 KB on ext4, a
          cluster on FAT), a folder or a long link one block each;
        - a file replaced in place gives back its old blocks, except when a
          running program has it open (a binary or a library: those blocks stay
          in use until it exits) or it has other hard links; a smaller new file
          gives nothing back (deletions happen at the end and count for nothing);
        - while a file is written its new copy and the old one both exist
          (.miaui-new, then rename), so the biggest new file counts once more;
        - a margin for the filesystem's own blocks: 2%, at least 4 MB.
        The payload is streamed from the .tar.gz, never unpacked anywhere first,
        so the update file itself needs nothing more.
        Without with_boot the boot partition is left out (it isn't mounted yet)."""
        busy = busy_files()
        devs = {}

        def part(p, area):
            d = os.path.dirname(p)
            while not os.path.isdir(d):
                d = os.path.dirname(d)
            dev = os.stat(d).st_dev
            e = devs.get(dev)
            if e is None:
                vfs = os.statvfs(d)
                e = devs[dev] = {"area": area, "where": d, "bs": vfs.f_bsize or 4096, "bytes": 0, "temp": 0,
                                 "inodes": 0, "free": vfs.f_bavail * vfs.f_frsize,
                                 "ifree": vfs.f_favail if vfs.f_files else None}   # FAT has no inodes
            return e

        def blocks(n, e):
            return -(-n // e["bs"]) * e["bs"]

        for f in self.plan["files"]:
            area = area_of(f["p"])
            if area == "boot" and not with_boot:
                continue
            p = self.target(f["p"])
            e = part(p, area)
            old = 0
            if os.path.lexists(p):
                if f.get("k"):
                    continue   # the card's own copy is kept: nothing is written
                st = os.lstat(p)
                if stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and os.path.realpath(p) not in busy:
                    old = st.st_blocks * 512 if hasattr(st, "st_blocks") else blocks(st.st_size, e)
            else:
                e["inodes"] += 1
            new = blocks(f["s"], e)
            e["bytes"] += max(0, new - old)
            e["temp"] = max(e["temp"], new)
        for d in self.plan["dirs"]:
            area = area_of(d["p"])
            if area == "boot" and not with_boot:
                continue
            p = self.target(d["p"])
            if not os.path.isdir(p):
                e = part(p, area)
                e["bytes"] += e["bs"]
                e["inodes"] += 1
        for ln in self.plan["links"]:
            if area_of(ln["p"]) == "boot" and not with_boot:
                continue
            p = self.target(ln["p"])
            if not os.path.lexists(p):
                e = part(p, area_of(ln["p"]))
                e["inodes"] += 1
                if len(ln["l"].encode("utf-8")) >= 60:   # a long target takes a block of its own
                    e["bytes"] += e["bs"]
        rows = []
        for e in devs.values():
            need = e["bytes"] + e["temp"]
            need += max(4 << 20, need // 50)
            ok = e["free"] >= need and (e["ifree"] is None or e["ifree"] >= e["inodes"] + 64)
            rows.append(dict(e, need=need, ok=ok))
        return rows

    def check_space(self, with_boot=True):
        rows = self.space_rows(with_boot)
        for r in rows:
            self.log("space on %s (%s): needs %s, free %s; files %d, inodes free %s -> %s" % (
                r["where"], r["area"], human(r["need"]), human(r["free"]), r["inodes"],
                "n/a" if r["ifree"] is None else r["ifree"], "ok" if r["ok"] else "NOT ENOUGH"))
        short = [r for r in rows if not r["ok"]]
        if short:
            r = short[0]
            raise SpaceError(self.t["err_space"].format(r["where"], human(r["need"]), human(r["free"])), short)

    def open_boot(self):
        if TEST_BOOT or not REAL:
            self.boot_dir = TEST_BOOT or os.path.join(ROOT, "boot-partition")
            os.makedirs(self.boot_dir, exist_ok=True)
            return
        dev = boot_device()
        for src, mnt, _fs, opts in proc_mounts():
            if src == dev:   # already mounted (by hand): use it where it is
                self.boot_dir = mnt
                if "ro" in opts.split(","):
                    if os.system("mount -o remount,rw '%s'" % mnt) != 0:
                        raise UpdateError(self.t["err_boot"])
                    self.boot_remounted = True
                self.log("boot partition %s already mounted at %s" % (dev, mnt))
                break
        else:
            if not os.path.exists(dev):
                raise UpdateError(self.t["err_boot"] + " (%s)" % dev)
            os.makedirs(BOOT_MNT, exist_ok=True)
            r = subprocess.run(["mount", "-t", "vfat", "-o", "rw,noatime", dev, BOOT_MNT],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            if r.returncode != 0 or not any(s == dev and m == BOOT_MNT for s, m, _f, _o in proc_mounts()):
                raise UpdateError(self.t["err_boot"] + " " + r.stdout.decode("utf-8", "replace").strip())
            self.boot_dir, self.boot_mounted = BOOT_MNT, True
            self.log("boot partition %s mounted at %s" % (dev, BOOT_MNT))
        # MiaUI's boot partition has these; anything else is not ours to write
        if not any(os.path.exists(os.path.join(self.boot_dir, n)) for n in ("uImage", "kernel.dtb", "uEnv.txt")):
            raise UpdateError(self.t["err_boot"] + " (no uImage in %s)" % self.boot_dir)

    def cleanup(self):
        """Whatever happened: everything on the card, boot unmounted, / read-only."""
        try:
            os.sync()
        except OSError:
            pass
        if self.boot_mounted:
            r = os.system("umount '%s'" % BOOT_MNT)
            self.log("boot partition unmounted" if r == 0 else "WARNING: umount %s failed" % BOOT_MNT)
            if r == 0:
                try:
                    os.rmdir(BOOT_MNT)
                except OSError:
                    pass
            self.boot_mounted = False
        elif self.boot_remounted:
            os.system("mount -o remount,ro '%s'" % self.boot_dir)
        if self.root_rw:
            os.system("mount -o remount,ro /")
            self.log("rootfs back to read-only")
            self.root_rw = False

    def retire(self):
        """After a good update: the update file goes, and the app hides itself
        (.off.Updater.pak) so it isn't run twice."""
        try:
            os.remove(self.path)
        except OSError:
            pass
        if os.environ.get("UPDATER_KEEP"):
            return
        if HERE.endswith("Updater.pak"):
            try:
                os.rename(HERE, os.path.join(os.path.dirname(HERE), ".off." + os.path.basename(HERE)))
            except OSError:
                self.log("WARNING: could not rename Updater.pak")


def plan_counts(plan):
    c = {"rootfs": 0, "userdata": 0, "boot": 0, "keep": 0}
    for f in plan["files"]:
        p = f["p"]
        c["boot" if p.startswith("boot:/") else "userdata" if p.startswith("/userdata/") else "rootfs"] += 1
        c["keep"] += 1 if f.get("k") else 0
    return c


# --- SIN PANTALLA (pruebas / SSH) ---

def run_headless(t):
    chk = Checker()
    chk.run()
    print("update file: %s" % chk.status)
    if chk.status != "READY":
        sys.exit(1)
    plan = chk.plan
    print("MiaUI %s, %d files (%s), %d deletions, boot: %s" % (
        plan.get("version"), len(plan["files"]), human(plan["bytes"]),
        len(plan["delete"]) + len(plan["rmdir"]), "yes" if plan.get("boot") else "no"))
    try:
        Installer(plan, chk.path, t).check_space(with_boot=False)
    except SpaceError as e:
        lines, _ = space_lines(t, e.rows)
        print("FAILED: " + " / ".join(lines[:-1]))
        sys.exit(3)
    job = Installer(plan, chk.path, t)
    job.start()
    last = None
    while job.is_alive():
        st = job.state()
        pct = st["done"] * 100 // st["total"]
        if (pct, st["phase"]) != last:
            last = (pct, st["phase"])
            print("%3d%%  %s %s" % (pct, t[st["phase"]], st["file"]), flush=True)
        time.sleep(0.2)
    st = job.state()
    if st["error"]:
        print("FAILED: %s" % st["error"])
        sys.exit(2)
    job.retire()
    print("OK: copied %d, kept %d, deleted %d, folders kept %d" % (st["copied"], st["kept"], st["deleted"], st["dirs_kept"]))


# --- INTERFAZ PYGAME ---

def init_pygame():
    import pygame
    pygame.display.init()
    pygame.font.init()
    pygame.joystick.init()
    for i in range(pygame.joystick.get_count()):
        pygame.joystick.Joystick(i).init()

    screen = pygame.display.set_mode((640, 480))
    try:
        font_title = pygame.font.Font(FONT, 29, bold=True)   # as sdtool, on the console's pygame
    except TypeError:                                         # a newer pygame (a PC) takes two
        font_title = pygame.font.Font(FONT, 29)
    font_list = pygame.font.Font(FONT, 25)
    if pygame.font.match_font("arial"):
        font_info = pygame.font.SysFont("Arial", 24)
    else:
        # the console has no Arial, and SysFont's fallback comes out much
        # smaller than 24: the menu's own font keeps these lines readable
        font_info = pygame.font.Font(FONT, 23)
    return pygame, screen, (font_title, font_list, font_info)


class UI:
    def __init__(self, t):
        self.t = t
        self.pg, self.screen, self.fonts = init_pygame()

    def buttons(self):
        """Buttons pressed since the last call (a keyboard too, for a PC)."""
        pg = self.pg
        keys = {pg.K_RETURN: BTN_A, pg.K_BACKSPACE: BTN_B, pg.K_ESCAPE: BTN_MENU,
                pg.K_UP: BTN_UP, pg.K_DOWN: BTN_DOWN, pg.K_LEFT: BTN_LEFT, pg.K_RIGHT: BTN_RIGHT}
        out = []
        for event in pg.event.get():
            if event.type == pg.QUIT:
                out.append(BTN_MENU)
            elif event.type == pg.JOYBUTTONDOWN:
                out.append(event.button)
            elif event.type == pg.KEYDOWN and event.key in keys:
                out.append(keys[event.key])
        return out

    def settle(self):
        self.pg.time.delay(200)
        self.pg.event.clear()

    @staticmethod
    def fit(font, text, width):
        """The text, cut with "..." to fit in `width` pixels."""
        if font.size(text)[0] <= width:
            return text
        while text and font.size(text + "...")[0] > width:
            text = text[:-1]
        return text + "..."

    def text(self, font, line, color, pos, width=600):
        self.screen.blit(font.render(self.fit(font, line, width), True, color), pos)

    def box(self, lines, top=330):
        """The info box at the bottom: [(text, color)]."""
        pg, font = self.pg, self.fonts[2]
        rect = pg.Rect(10, top, 620, 470 - top)
        pg.draw.rect(self.screen, (45, 45, 50), rect)
        pg.draw.rect(self.screen, (80, 80, 90), rect, 2)
        y = top + 12
        for line, color in lines:
            self.text(font, line, color, (25, y), 590)
            y += 26

    def bar(self, y, done, total):
        pg = self.pg
        width = 600
        fill = int(done / total * width) if total else 0
        pg.draw.rect(self.screen, (100, 100, 100), (20, y, width, 40))
        pg.draw.rect(self.screen, (50, 200, 50), (20, y, min(width, fill), 40))

    def notice(self, lines):
        """Lines of text, drawn once (no waiting): a "please wait" screen."""
        self.screen.fill(BG)
        y = 80
        for line in lines:
            self.text(self.fonts[1], line, WHITE, (30, y), 590)
            y += 35
        self.pg.display.flip()

    def message(self, lines, colors=None, keys=(BTN_A, BTN_B, BTN_MENU)):
        """Lines of text until one of `keys` (A, B or MENU)."""
        clock = self.pg.time.Clock()
        font = self.fonts[1]
        while True:
            self.screen.fill(BG)
            y = 80
            for i, line in enumerate(lines):
                self.text(font, line, (colors or {}).get(i, WHITE), (30, y), 590)
                y += 35
            self.pg.display.flip()
            if any(b in keys for b in self.buttons()):
                self.settle()
                return
            clock.tick(30)

    def confirm(self, lines):
        """A yes/no screen: True for A, False for B or MENU."""
        font_title, font_list, _ = self.fonts
        clock = self.pg.time.Clock()
        while True:
            self.screen.fill((50, 10, 10))
            y = 100
            for i, line in enumerate(lines):
                font = font_title if i == 0 else font_list
                self.text(font, line, YELLOW if i == 0 else SOFT_GREEN, (30, y), 580)
                y += 50 if i == 0 else 35
            self.pg.display.flip()
            for b in self.buttons():
                if b == BTN_A:
                    self.settle()
                    return True
                if b in (BTN_B, BTN_MENU):
                    self.settle()
                    return False
            clock.tick(30)

    def menu(self, items, header, info):
        """The main list: its index, or None for B / MENU."""
        font_title, font_list, font_info = self.fonts
        clock = self.pg.time.Clock()
        selected = 0
        while True:
            self.screen.fill(BG)
            self.text(font_title, self.t["title"], WHITE, (20, 20))
            y = 70
            for line in header:
                self.text(font_info, line, DIM, (20, y))
                y += 26
            y += 6
            for i, item in enumerate(items):
                on = i == selected
                self.text(font_list, ("> " if on else "  ") + item, GREEN if on else GREY, (20, y))
                y += 45
            self.box(info)
            self.pg.display.flip()
            for b in self.buttons():
                if b == BTN_A:
                    self.settle()
                    return selected
                if b in (BTN_B, BTN_MENU):
                    self.settle()
                    return None
                if b == BTN_UP:
                    selected = (selected - 1) % len(items)
                elif b == BTN_DOWN:
                    selected = (selected + 1) % len(items)
            clock.tick(30)

    def checking(self, chk):
        """The CRC check, with its bar, until it's done."""
        clock = self.pg.time.Clock()
        font_title, font_list, font_info = self.fonts
        while chk.is_alive():
            self.screen.fill(BG)
            self.text(font_title, self.t["title"], WHITE, (20, 20))
            self.text(font_list, self.t["checking"], YELLOW, (20, 150))
            pct = chk.done * 100 // chk.total
            self.text(font_info, self.t["checked"].format(pct), WHITE, (20, 195))
            self.bar(235, chk.done, chk.total)
            self.pg.display.flip()
            self.buttons()
            clock.tick(10)

    def progress(self, job):
        """The install, until it ends: no way out, it must not be stopped."""
        t = self.t
        font_title, font_list, font_info = self.fonts
        clock = self.pg.time.Clock()
        while True:
            st = job.state()
            if st["finished"]:
                return st
            self.screen.fill(BG)
            self.text(font_title, t["installing"], WHITE, (20, 20))
            self.text(font_list, t[st["phase"]], YELLOW, (20, 75))
            if st["file"]:
                self.text(font_info, st["file"], SOFT_GREEN, (20, 120))
            pct = min(100, st["done"] * 100 // st["total"])
            self.text(font_info, t["progress"].format(pct, human(min(st["done"], job.plan["bytes"])),
                                                      human(job.plan["bytes"])), WHITE, (20, 165))
            self.bar(205, st["done"], st["total"])
            if st["files"]:
                self.text(font_info, t["file_n"].format(st["n"], st["files"]), GREY, (20, 265))
            self.box([(t["do_not_off"], RED)], top=400)
            self.pg.display.flip()
            self.buttons()   # read and dropped: nothing stops it
            clock.tick(10)

    def log_viewer(self, lines):
        t = self.t
        font_title, _, font_info = self.fonts
        wrapped = []
        for line in lines:
            wrapped.extend(textwrap.wrap(line, width=52) or [""])
        rows, top = 12, max(0, len(wrapped) - 12)
        clock = self.pg.time.Clock()
        while True:
            self.screen.fill((20, 20, 25))
            self.text(font_title, t["log_title"], WHITE, (20, 20))
            y = 70
            for line in wrapped[top:top + rows]:
                self.text(font_info, line, SOFT_GREEN, (20, y))
                y += 26
            self.box([(t["log_inst"], YELLOW)], top=420)
            self.pg.display.flip()
            for b in self.buttons():
                if b in (BTN_A, BTN_B, BTN_MENU):
                    self.settle()
                    return
                if b == BTN_UP:
                    top = max(0, top - 1)
                elif b == BTN_DOWN:
                    top = min(max(0, len(wrapped) - rows), top + 1)
                elif b == BTN_LEFT:
                    top = max(0, top - rows)
                elif b == BTN_RIGHT:
                    top = min(max(0, len(wrapped) - rows), top + rows)
            clock.tick(30)

    def quit(self):
        """Cierra la aplicación limpiamente y limpia la pantalla."""
        for _ in range(0, 10):
            self.screen.fill(BG)
            self.pg.display.flip()
        self.pg.quit()
        if REAL:
            os.system("cat /dev/zero > /dev/fb0 2>/dev/null")


def series(versions):
    """The release series an update is for: updates are cumulative over a
    whole major version, so ["1.0.1", "1.0.3"] is "1.x.x", whichever of them
    the console has. Versions it can't read are shown as they are."""
    out = []
    for v in versions or []:
        m = re.match(r"v?(\d+)\.", v)
        name = m.group(1) + ".x.x" if m else v
        if name not in out:
            out.append(name)
    return ", ".join(out) or "?"


def flush_nekobit():
    """What minui's power-off does for NekoBit (NB_flushToCard in
    common/nekobit_store.h): if its RAM state changed since the last save,
    onto the card, the old copy kept as the backup. A plain reboot skips
    minui's power-off, so without this the play since the last save is lost.
    (The Updater's own NekoBit session isn't stamped: it isn't play time.)"""
    tmp, card = "/tmp/nekobit", "/userdata/Profile/shared/NekoBit"
    if not os.path.exists(os.path.join(tmp, "dirty")):
        return
    try:
        with open(os.path.join(tmp, "state.bin"), "rb") as f:
            data = f.read()
        if not data:
            return
        os.makedirs(card, exist_ok=True)
        state = os.path.join(card, "nekobit.bin")
        if os.path.exists(state):
            os.replace(state, os.path.join(card, "nekobit.bak"))   # the loader falls back to it
        with open(state + ".tmp", "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(state + ".tmp", state)
        fd = os.open(card, os.O_RDONLY)
        os.fsync(fd)
        os.close(fd)
        os.remove(os.path.join(tmp, "dirty"))
    except OSError:
        pass   # NekoBit's state is never worth blocking the restart


def reboot(ui=None, t=None):
    """A real restart, the way the rest of MiaUI's tools do it (sdtool.py)."""
    if ui:
        ui.notice([t["rebooting"]])
    if not REAL:   # a PC test: never restart the machine running it
        print("REBOOT (not on a console: skipped)", flush=True)
        return
    flush_nekobit()
    os.sync()
    if ui:
        ui.quit()
    os.system("reboot")
    sys.exit(0)


def status_lines(t, status, plan):
    if status != "READY":
        return [(t["st_" + status.lower()], RED), ("", GREY), (t["st_help"], GREY)]
    lines = [(t["st_ready"], GREEN),
             (t["sum_files"].format(len(plan["files"]), human(plan["bytes"])), GREY)]
    deletions = len(plan["delete"]) + len(plan["rmdir"])
    if deletions:
        lines.append((t["sum_delete"].format(deletions), GREY))
    if plan.get("boot"):
        lines.append((t["sum_boot"], YELLOW))
    return lines


def space_lines(t, rows):
    """The "not enough space" screen: per partition, what is missing."""
    lines, colors = [t["space_title"], ""], {0: RED}
    for r in rows:
        lines.append(t["area_" + r["area"]])
        if r["free"] < r["need"]:
            lines.append(t["space_row"].format(human(r["need"]), human(r["free"])))
            miss = human(r["need"] - r["free"])
            colors[len(lines)] = YELLOW
            lines.append(t["space_more_user" if r["area"] == "userdata" else "space_more"].format(miss))
        else:
            colors[len(lines)] = YELLOW
            lines.append(t["space_inodes"].format(r["ifree"], r["inodes"]))
    lines += ["", t["space_none"], t["press_a"]]
    return lines, colors


def details(ui, t, plan):
    c = plan_counts(plan)
    lines = [t["details_title"], ""]
    if c["rootfs"]:
        lines.append(t["d_rootfs"].format(c["rootfs"]))
    if c["userdata"]:
        lines.append(t["d_userdata"].format(c["userdata"]))
    if c["boot"]:
        lines.append(t["d_boot"].format(c["boot"]))
    lines.append(t["d_delete"].format(len(plan["delete"]), len(plan["rmdir"])))
    lines.append(t["d_links"].format(len(plan["links"]), len(plan["dirs"]), len(plan["meta"])))
    if c["keep"]:
        lines.append(t["d_keep"].format(c["keep"]))
    lines += [t["d_size"].format(human(plan["bytes"])), "", t["press_a"]]
    ui.message(lines, {0: GREEN})


def main():
    t = load_texts(get_language())
    if HEADLESS:
        run_headless(t)
        return
    ui = UI(t)
    chk = Checker()
    chk.start()
    ui.checking(chk)
    chk.join()
    plan = chk.plan

    while True:
        header = []
        if plan:
            header = [t["hdr_version"].format(plan.get("version", "?")),
                      t["hdr_from"].format(series(plan.get("from")))]
        items = ([("install", t["opt_install"]), ("details", t["opt_details"])] if chk.status == "READY" else []) \
            + [("exit", t["opt_exit"])]
        pick = ui.menu([label for _, label in items], header, status_lines(t, chk.status, plan))
        action = items[pick][0] if pick is not None else "exit"
        if action == "exit":
            break
        if action == "details":
            details(ui, t, plan)
            continue

        try:   # before asking: if it can't fit, say so now (boot is checked once mounted)
            Installer(plan, chk.path, t).check_space(with_boot=False)
        except SpaceError as e:
            ui.message(*space_lines(t, e.rows))
            continue
        if not ui.confirm([t["confirm_q"].format(plan.get("version", "")), "", t["confirm_1"],
                           t["confirm_2"], "", t["confirm_inst"]]):
            continue
        bat = battery() if REAL else None
        if bat and bat[0] < MIN_BATTERY and not bat[1]:
            ui.message([t["battery_title"].format(bat[0]), "", t["battery_1"], "", t["press_a"]], {0: RED})
            continue

        job = Installer(plan, chk.path, t)
        job.start()
        st = ui.progress(job)
        job.join()
        if st["space"]:   # stopped before writing anything
            ui.message(*space_lines(t, st["space"]))
            continue
        if st["error"]:
            ui.message([t["fail_title"]] + textwrap.wrap(st["error"], 44)[:4] + ["", t["fail_1"], t["fail_2"]], {0: RED})
            ui.log_viewer(job.log.lines)
            continue
        job.retire()
        lines = [t["done_title"], "", t["done_files"].format(st["copied"])]
        if st["kept"]:
            lines.append(t["done_kept"].format(st["kept"]))
        if st["deleted"]:
            lines.append(t["done_deleted"].format(st["deleted"]))
        if st["dirs_kept"]:
            lines.append(t["done_dirs_kept"].format(st["dirs_kept"]))
        colors = {0: GREEN}
        # new system files or a new kernel only take over after a restart:
        # then A restarts the console for real (and only A: no skipping it)
        restart = bool(plan.get("boot") or plan.get("rootfs"))
        if restart:
            lines += ["", t["done_restart"]]
            colors[len(lines) - 1] = YELLOW
        lines += ["", t["press_a_reboot"] if restart else t["press_a"]]
        ui.message(lines, colors, keys=(BTN_A,) if restart else (BTN_A, BTN_B, BTN_MENU))
        if restart:
            reboot(ui, t)
        break

    ui.quit()


if __name__ == "__main__":
    main()
