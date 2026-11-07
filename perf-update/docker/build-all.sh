#!/bin/sh
# Runs inside debian:bookworm, started by perf-update/build.sh.
# /repo = this repo (ro), /cache = pcsx_rearmed + libretro-common checkouts (ro), /out = output.
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

# --- minarch ---
cp -a /repo/src /b/src
rm -rf /b/src/minarch/libretro-common
cp -a /cache/libretro-common /b/src/minarch/libretro-common
cd /b/src
# libmsettings is only linked against; the device keeps its own copy
$CC $ARCH -O2 -fpic -shared -o /b/libmsettings.so libmsettings/msettings.c -ldl -lrt
cd minarch
$CC minarch.c ../common/utils.c ../common/api.c ../platform/platform.c -o /out/minarch.elf \
	$ARCH -fomit-frame-pointer -DGL_VERTEX_SHADER -DSTBI_FAILURE_USERMSG \
	-I. -I./libretro-common/include -I../common -I../platform -I../libmsettings -I/usr/include/SDL2 \
	-DPLATFORM=\"rg35xx\" -DUSE_SDL2 -Ofast -std=gnu99 \
	-DBUILD_DATE=\"$(date +%Y.%m.%d)\" -DBUILD_HASH=\"$(git -C /repo rev-parse --short HEAD 2>/dev/null || echo perf)\" \
	-L/b -lmsettings -lSDL2 -lSDL2_image -lSDL2_ttf -lEGL -lGLESv2 -lpthread -lm -lz -w

# --- minui (launcher menu: collections picker) ---
cd /b/src/minui
$CC minui.c ../common/utils.c ../common/api.c ../platform/platform.c -o /out/minui.elf \
	$ARCH -fomit-frame-pointer -DGL_VERTEX_SHADER -DSTBI_FAILURE_USERMSG \
	-I. -I../common -I../platform -I../libmsettings -I/usr/include/SDL2 \
	-DPLATFORM=\"rg35xx\" -DUSE_SDL2 -Os -std=gnu99 \
	-DBUILD_DATE=\"$(date +%Y.%m.%d)\" -DBUILD_HASH=\"$(git -C /repo rev-parse --short HEAD 2>/dev/null || echo perf)\" \
	-L/b -lmsettings -lSDL2 -lSDL2_image -lSDL2_ttf -lEGL -lGLESv2 -lpthread -lm -lz -ldl -w
arm-linux-gnueabihf-strip /out/minui.elf

for f in /out/minarch.elf /out/minui.elf /out/pcsx_rearmed_libretro.so; do
	v=$(arm-linux-gnueabihf-readelf -V "$f" | grep -oE "GLIBC_2\.[0-9]+" | sort -uV | tail -1)
	echo "$f needs $v (MiaUI has GLIBC_2.37)"
done

# --- Updater.pak zip (same format as MiaUI's official updates) ---
# update_<crc32>.tar.gz is extracted to / by local_updater.py. Files only, no directory
# entries, so extracting over / never changes directory modes or owners.
rm -rf /stage && mkdir -p /stage/root/opt/minui/bin /stage/root/userdata/Cores /stage/zip/Updater.pak
install -m 755 /out/minarch.elf /stage/root/opt/minui/bin/minarch.elf
install -m 755 /out/minui.elf /stage/root/opt/minui/bin/minui.elf
install -m 666 /out/pcsx_rearmed_libretro.so /stage/root/userdata/Cores/pcsx_rearmed_libretro.so
cd /stage/root
tar --numeric-owner --owner=1000 --group=100 --mtime='2026-10-31 12:00' -cf /stage/update.tar \
	./opt/minui/bin/minarch.elf ./opt/minui/bin/minui.elf ./userdata/Cores/pcsx_rearmed_libretro.so
gzip -n -9 /stage/update.tar
CRC=$(python3 -c "import zlib,sys; print(format(zlib.crc32(open(sys.argv[1],'rb').read()) & 0xffffffff, '08x'))" /stage/update.tar.gz)
cp /repo/skeleton/ROMS/Tools/Updater.pak/local_updater.py /stage/zip/Updater.pak/
# launch.sh as shipped in the official v1.0.3 update
printf '#!/bin/sh\n\ncd "$(dirname "$0")"\n\npython ./local_updater.py\n' > /stage/zip/Updater.pak/launch.sh
chmod 755 /stage/zip/Updater.pak/launch.sh /stage/zip/Updater.pak/local_updater.py
mv /stage/update.tar.gz /stage/zip/Updater.pak/update_$CRC.tar.gz
cd /stage/zip
rm -f /out/miaui-v1.0.3-perf-audio.zip
zip -q -r -X /out/miaui-v1.0.3-perf-audio.zip Updater.pak
echo "update_$CRC.tar.gz:"
tar tvzf Updater.pak/update_$CRC.tar.gz
