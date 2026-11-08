#!/bin/sh
# Runs inside debian:bookworm, started by perf-update/build.sh.
# /repo = this repo (ro), /cache = pcsx_rearmed + libretro-common checkouts (ro), /out = output.
#
# Builds the MiaUI 2.0.1 update for a console on MiaUI 2.0.0: minui.elf (Y adds a game to
# collections), Tools/Collections.pak (create, rename, delete them) and pcsx_rearmed_libretro.so
# (NEON code keeps d8-d15), packaged for 2.0's Updater.
set -e

dpkg --add-architecture armhf
apt-get -qq update >/dev/null
apt-get -qq install -y gcc-arm-linux-gnueabihf g++-arm-linux-gnueabihf make git python3 zip \
	libsdl2-dev:armhf libsdl2-image-dev:armhf libsdl2-ttf-dev:armhf \
	libgles-dev:armhf libegl-dev:armhf zlib1g-dev:armhf >/dev/null 2>&1

CC=arm-linux-gnueabihf-gcc
ARCH="-marm -mcpu=cortex-a9 -mfpu=neon-fp16 -mfloat-abi=hard"

# --- PCSX ReARMed (cores/makefile hash + cores/patches/pcsx_rearmed.patch) ---
rm -rf /b && mkdir /b
cp -a /cache/pcsx_rearmed /b/pcsx_rearmed
cd /b/pcsx_rearmed
git apply /repo/cores/patches/pcsx_rearmed.patch
make -f Makefile.libretro platform=rg35xx CROSS_COMPILE=arm-linux-gnueabihf- -j"$(nproc)" >/out/pcsx-build.log 2>&1 \
	|| { tail -40 /out/pcsx-build.log; exit 1; }
arm-linux-gnueabihf-strip -o /out/pcsx_rearmed_libretro.so pcsx_rearmed_libretro.so

# --- minui (launcher menu) ---
cp -a /repo/src /b/src
cd /b/src
# libmsettings is only linked against; the console keeps its own (2.0's) copy
$CC $ARCH -O2 -fpic -shared -o /b/libmsettings.so libmsettings/msettings.c -ldl -lrt
cd minui
$CC minui.c nekobit.c nekobit_ui.c quickmenu.c ../common/utils.c ../common/api.c ../common/i18n.c ../platform/platform.c \
	-o /out/minui.elf $ARCH -fomit-frame-pointer \
	-I. -I../common -I../platform -I../libmsettings -I/usr/include/SDL2 \
	-DPLATFORM=\"rg35xx\" -DUSE_SDL2 -Os -std=gnu99 \
	-DBUILD_DATE=\"$(date +%Y.%m.%d)\" -DBUILD_HASH=\"$(git -C /repo rev-parse --short HEAD 2>/dev/null || echo 2.0.1)\" \
	-L/b -lmsettings -lSDL2 -lSDL2_image -lSDL2_ttf -lEGL -lGLESv2 -lpthread -lm -lz -ldl -w
arm-linux-gnueabihf-strip /out/minui.elf

for f in /out/minui.elf /out/pcsx_rearmed_libretro.so; do
	v=$(arm-linux-gnueabihf-readelf -V "$f" | grep -oE "GLIBC_2\.[0-9]+" | sort -uV | tail -1)
	echo "$f needs $v (MiaUI has GLIBC_2.37)"
done

# --- Updater.pak zip, MiaUI 2.0's format: update_<crc32>.tar.gz = plan.json + the files ---
rm -rf /stage && mkdir -p /stage/tar/rootfs/opt/minui/bin /stage/tar/userdata/Cores /stage/zip/Updater.pak
cp /out/minui.elf /stage/tar/rootfs/opt/minui/bin/minui.elf
cp /out/pcsx_rearmed_libretro.so /stage/tar/userdata/Cores/pcsx_rearmed_libretro.so
mkdir -p /stage/tar/userdata/Tools/Collections.pak
cp /repo/skeleton/ROMS/Tools/Collections.pak/launch.sh /repo/skeleton/ROMS/Tools/Collections.pak/collections.py \
	/stage/tar/userdata/Tools/Collections.pak/
python3 /repo/perf-update/docker/make_plan.py /stage/tar > /stage/tar/plan.json
cat /stage/tar/plan.json
cd /stage/tar
# files only, plan.json first: 2.0's Updater refuses folder entries
tar -cf /stage/update.tar --owner=0 --group=0 --format=gnu plan.json \
	rootfs/opt/minui/bin/minui.elf userdata/Cores/pcsx_rearmed_libretro.so \
	userdata/Tools/Collections.pak/launch.sh userdata/Tools/Collections.pak/collections.py
gzip -n -9 /stage/update.tar
CRC=$(python3 -c "import zlib,sys; print('%08x' % (zlib.crc32(open(sys.argv[1],'rb').read()) & 0xffffffff))" /stage/update.tar.gz)
cp /repo/perf-update/updater/local_updater.py /stage/zip/Updater.pak/
printf '#!/bin/sh\n\ncd "$(dirname "$0")"\n\npython ./local_updater.py\n' > /stage/zip/Updater.pak/launch.sh
chmod 755 /stage/zip/Updater.pak/launch.sh /stage/zip/Updater.pak/local_updater.py
mv /stage/update.tar.gz /stage/zip/Updater.pak/update_$CRC.tar.gz
cd /stage/zip
rm -f /out/miaui-v2.0.1-update.zip
zip -q -r -X /out/miaui-v2.0.1-update.zip Updater.pak
echo "update_$CRC.tar.gz:"
tar tvzf Updater.pak/update_$CRC.tar.gz
