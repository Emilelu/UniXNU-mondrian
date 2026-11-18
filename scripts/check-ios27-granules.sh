#!/bin/sh
# Compile the xnu-12377 granule constants the way the arm64e build does.
#
# This is scripts/check-xnu-granules.py from UniXNU with the two defines that
# xnu-12377 needs and the framework copy does not pass yet:
#   * KERNEL_PRIVATE - 12377 guards pexpert/arm64/board_config.h and
#     osfmk/arm64/proc_reg.h with it, so the framework command stops at an
#     #error before it reaches the assertions;
#   * VMAPPLE - proc_reg.h requires a CPU geometry (APPLEH16, APPLEACC8 or
#     VMAPPLE); the 4 KiB BCM2837 machine config is the generic one.
# Re-run the framework copy when it gains those flags; drop this script then.
#
# The check is static: it compiles the header constants, it does not build a
# kernel. 4 KiB means ARM_PGSHIFT 12, TG0 = 0 and TG1 = 2 in TCR_EL1_BOOT.
set -eu
TREE=${1:-${K60_XNU_TREE:-../UniXNU/out/mondrian/ios-27.0.1-24A446/mondrian_ios27/tree}}
CLANG=${CLANG:-clang}

if [ ! -f "$TREE/refer/xnu/pexpert/pexpert/arm64/board_config.h" ]; then
	echo "check-ios27-granules: no xnu refer tree at $TREE" >&2
	echo "pass the tree path, or run unixnu fetch first" >&2
	exit 2
fi

OUT=$(mktemp -d "${TMPDIR:-/var/tmp}/ios27-granules.XXXXXX")
trap 'rm -rf "$OUT"' EXIT

cat > "$OUT/BCM2837.S" <<'EOF'
#include <pexpert/arm64/board_config.h>
#include <arm64/proc_reg.h>
.if ARM_PGSHIFT != 12
.error "page shift"
.endif
.if ((TCR_EL1_BOOT >> 14) & 3) != 0
.error "TG0"
.endif
.if ((TCR_EL1_BOOT >> 30) & 3) != 2
.error "TG1"
.endif
.data
.quad TCR_EL1_BOOT
.quad ARM_PGBYTES
EOF

"$CLANG" --target=aarch64-none-elf -D__arm64__=1 -DKERNEL_PRIVATE -DVMAPPLE \
	-DASSEMBLER -D__ASSEMBLER__ -DARM64_BOARD_CONFIG_BCM2837 \
	-ffreestanding -Werror -c \
	-I "$TREE/refer/xnu/osfmk" -I "$TREE/refer/xnu/pexpert" \
	-I "$TREE/refer/xnu/EXTERNAL_HEADERS" \
	"$OUT/BCM2837.S" -o "$OUT/BCM2837.o"

llvm-objcopy -O binary "$OUT/BCM2837.o" "$OUT/BCM2837.bin"
python3 - "$OUT/BCM2837.bin" <<'PY'
import struct
import sys

data = open(sys.argv[1], 'rb').read()
tcr, page = struct.unpack_from('<QQ', data)
assert page == 4096, f'ARM_PGBYTES={page}, expected 4096'
assert (tcr >> 14) & 3 == 0, 'TG0 is not 4 KiB'
assert (tcr >> 30) & 3 == 2, 'TG1 is not 4 KiB'
print(f'granules: 4 KiB BCM2837, TCR_EL1_BOOT=0x{tcr:016x}, ARM_PGBYTES={page}')
PY
