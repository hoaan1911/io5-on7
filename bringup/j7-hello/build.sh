#!/bin/bash
# Build the J7 Prime hello shim and pack it as a Samsung boot image using the DT table of
# your stock boot.img (./boot.img). Output: out/j7-hello-boot.img
set -euo pipefail
cd "$(dirname "$0")"
CC=${CC:-aarch64-linux-gnu-gcc}
OBJCOPY=${OBJCOPY:-aarch64-linux-gnu-objcopy}
NM=${NM:-aarch64-linux-gnu-nm}
READELF=${READELF:-aarch64-linux-gnu-readelf}
STOCK=${1:-boot.img}
# GCC-only flag -fno-tree-loop-distribute-patterns is not accepted by Clang.
if $CC --version 2>/dev/null | head -1 | grep -qi clang; then
  LDFLAGS="-Wl,--build-id=none -Wl,-N"
  CFLAGS="-O2 -ffreestanding -nostdlib -fno-pic -fno-builtin -mgeneral-regs-only -mstrict-align -fno-stack-protector -Wall -Wextra"
else
  LDFLAGS="-Wl,--build-id=none -Wl,--no-warn-rwx-segments -Wl,-N"
  CFLAGS="-O2 -ffreestanding -nostdlib -fno-pic -fno-builtin -fno-tree-loop-distribute-patterns -mgeneral-regs-only -mstrict-align -fno-stack-protector -Wall -Wextra"
fi
mkdir -p out
for f in start.S hello.c console.c; do
	$CC $CFLAGS -c $f -o out/${f%.*}.o
done
abs=$($READELF -r out/hello.o out/console.o | grep -c ABS64 || true)
[ "$abs" = 0 ] || { echo "error: $abs absolute relocations in C objects" >&2; exit 1; }
$CC $CFLAGS $LDFLAGS -static -T shim.ld \
	out/start.o out/hello.o out/console.o -o out/hello.elf
$OBJCOPY -O binary out/hello.elf out/Image
end=$($NM out/hello.elf | awk '$3=="_end"{print $1}')
truncate -s $((16#$end)) out/Image
# non-empty ramdisk: S-Boot dislikes a zero-size one
(cd out && rm -rf rd && mkdir rd && cd rd && echo x > x && find . | cpio -o -H newc --quiet | gzip -9 > ../ramdisk.bin)
python3 samsung_bootimg.py selftest "$STOCK"
python3 samsung_bootimg.py pack --kernel out/Image --ramdisk out/ramdisk.bin \
	--dt-from "$STOCK" --cmdline "console=null" --name ios-j7hello -o out/j7-hello-boot.img
python3 samsung_bootimg.py unpack out/j7-hello-boot.img out/check >/dev/null && echo "repack check OK"
ls -l out/Image out/j7-hello-boot.img
