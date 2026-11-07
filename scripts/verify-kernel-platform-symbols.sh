#!/usr/bin/env bash
# Verify the platform driver is really inside the freshly linked kernel.
set -uo pipefail
A=/tmp/k60build/out/route-a18/Pong-iPadOS18-native/build/xnu/ios-obj/DEVELOPMENT_ARM64_PONG/mach.development.pong.unstripped.noctf
NM=/usr/bin/llvm-nm
OD=/usr/bin/llvm-objdump

echo "=== artifact ==="
ls -la "$A"

echo
echo "=== llvm-nm total lines ==="
"$NM" "$A" 2>&1 | wc -l

echo
echo "=== ArmDTPlatform / pong_cpu / ramoops symbols ==="
"$NM" "$A" 2>/dev/null | grep -iE 'ArmDTPlatform|pong_cpu|pong_ramoops' | head -20

echo
echo "=== objdump syms count ==="
"$OD" --macho --syms "$A" 2>/dev/null | wc -l

echo
echo "=== C++ mangled platform symbols via strings on the symtab ==="
python3 - "$A" <<'PY'
import struct, sys
data = open(sys.argv[1], 'rb').read()
ncmds = struct.unpack_from('<I', data, 16)[0]
p = 32
symoff = nsyms = stroff = strsize = None
for _ in range(ncmds):
    cmd, sz = struct.unpack_from('<II', data, p)
    if cmd == 0x2:  # LC_SYMTAB
        symoff, nsyms, stroff, strsize = struct.unpack_from('<IIII', data, p + 8)
    p += sz
print('LC_SYMTAB symoff=%s nsyms=%s strsize=%s' % (symoff, nsyms, strsize))
if not nsyms:
    print('no symbol table')
    raise SystemExit
strtab = data[stroff:stroff + strsize]
hits = [b'ArmDTPlatform', b'pong_cpu_start', b'pong_ramoops_console_write',
        b'pong_ramoops_diagnostic_write', b'ArmCpu']
for h in hits:
    print(f'  {h.decode():32s} in string table: {h in strtab}')
PY
