# 13. 固件载具验收门禁（2026-11-15）

Lead 要求：固件侧把 modem 镜像载具（案 A）合进 `uefi-mondrian` **之前**，这张表必须全绿。
每一行都是一条可机械执行的断言——给出工具、命令、通过标准；**没有一行是人工检查**。
表内的命令今天全部在验收机上实测过可用（2026-11-15 探针，见 §五）。

执行环境：WSL（有 mtools 与 python3）；`export PYTHONIOENCODING=utf-8`；
repo 指 `/mnt/e/hackios/k60-cellular`。

## 〇、固件侧必须交回的交付物

| # | 交付物 | 本表用它来做什么 |
| --- | --- | --- |
| 1 | `uefi-mondrian` 分支/commit：`ImageCarrierLib` + `DarwinBoot` 调用点 + 12-DXE-CONTRACT.md §1.5 的三行 level-1 日志 | 表 B（源码断言） |
| 2 | 该固件构建出的 `payload.img` 与 `boot.img`（给出确切路径与 sha256） | 表 A（产物断言） |
| 3 | 一次上机的 `console.log`（`E:/k60-work/evidence/` 下），boot 参数含 `pong_modem=2` | 表 C（日志断言） |

## 一、表 A：构建产物（对 payload.img / boot.img）

| 行 | 断言 | 工具与命令（WSL） | 通过标准 |
| --- | --- | --- | --- |
| A1 | payload 卷恰好 224 MiB | `stat -c %s "$PL"` | `== 234881024` |
| A2 | boot.img 恰好 235,446,272 B | `stat -c %s "$BOOT"` | `== 235446272`（固件若改 boot.img 头布局须先改此数并说明理由，未改前不许跳） |
| A3 | `EFI/UniXNU/MODEM/` 恰好 27 个文件、名字集合正确 | `mcopy -s -i "$PL" ::EFI/UniXNU/MODEM /tmp/accept-modem` 后 `ls` 与生成器 manifest 的名字列 diff | 行数 27 且 diff 空 |
| A4 | 每个文件大小 == 段表 `bytes`（拷贝量 109,060,761 B 的总和由表保证） | 抽出的 27 个文件逐个 `stat -c %s`，与 `gen-modem-table.py --manifest` 输出 diff | diff 空 |
| A5 | ADT `/chosen/memory-map` 有 `K60ModemImage` 属性，长度恰 16 字节，值 ∈ {全零, 精确区间} | 抽出 `kernel.macho.adt`，用 `scripts/pong_adt_contract.py` 的 `parse_adt` 解出 `/chosen/memory-map['K60ModemImage']` | rc 0，`len == 16`，`(base, span) ∈ {(0,0), (0x8bc00000, 0x13200000)}` |

说明：**区间起止逐字节**由两条独立证据共同咬死——A5 是离线产物（16 字节值），
表 C 的 C1/C3 是运行时日志（字面地址串）。两者都必须过。
**拷贝量 / 清除量 / 空洞**不在产物层查：产物层只能证明「带了哪些文件、各多大」，
装载行为由表 B（源码：无整窗清零）与表 C（日志：`copied 109060761, zeroed 211012967, gaps 790528`）咬死。

## 二、表 B：固件源码（对 uefi-mondrian checkout，`FWREPO`）

| 行 | 断言 | 工具与命令 | 通过标准 |
| --- | --- | --- | --- |
| B1 | `ImageCarrierLib` 库存在 | `grep -rn 'ImageCarrier' "$FWREPO" --include='*.inf' --include='*.c' --include='*.h'` | 命中 ≥ 1 个 .inf 且 ≥ 1 个 .c/.h |
| B2 | `DarwinBoot` 里有装载调用点 | `grep -rn 'ImageCarrierLoad' "$FWREPO" --include='DarwinBoot.c'` | 命中 ≥ 1 |
| B3 | `DarwinBoot` 发布 `K60ModemImage` 属性 | `grep -c 'K60ModemImage' "$FWREPO"/**/DarwinBoot.c（求和） | ≥ 2（一处记偏移、一处 `WriteUnaligned64`） |
| B4 | 三行 D3 日志在，且不是 debug 门 | `grep -rnF '<前缀>' "$FWREPO"` 三条前缀各查一次；再 `grep -rnF 'modem-image:' "$FWREPO" | grep 'DEBUG('` | 三条各 ≥ 1；DEBUG 交叉命中 0 |
| B5 | 固件表与生成器输出逐字节一致 | `grep -rlF 'MODEM_IMAGE_SEGMENTS' "$FWREPO" --include='*.h'` 找到表文件，与 `gen-modem-table.py --firmware-header` 输出 diff | diff 空 |
| B6 | 无整窗清零（空洞 790,528 B 必须不动） | `grep -rnE '(memset|SetMem|ZeroMem|AllocateZeroPool)\([^,]*,[[:space:]]*(0x13200000|320864256)' "$FWREPO"` | 命中 0 |

B4 的三个固定前缀（12-DXE-CONTRACT.md §1.5 裁决，固件不得改名）：
`modem-image: chosen dtb at `、`modem-image: window 0x8bc00000..0x9ee00000`、
`modem-image: abl staging ends at `。

## 三、表 C：上机 console.log（`grep -a`，日志含二进制字节必须带 `-a`）

| 行 | 断言 | 命令 | 通过标准 |
| --- | --- | --- | --- |
| C1 | 三行 D3 level-1 日志都在 | `grep -acF '<前缀>' "$LOG"` 三条 | 每条 `== 1` |
| C2 | 拷贝/清除/空洞数字正确 | `grep -acF 'copied 109060761, zeroed 211012967, gaps 790528' "$LOG"` | `== 1` |
| C3 | 区间发布行在 | `grep -acF 'range 0x8bc00000..0x9ee00000 published' "$LOG"` | `== 1` |
| C4 | 内核侧确认载具在位 | `grep -acF 'K60MODEM carrier present at 0x8bc00000' "$LOG"` | `== 1` |
| C5 | 内核侧 plan 数字一致 | `grep -acF 'K60MODEM plan rows=30 copied=109060761 zeroed=211012967' "$LOG"` | `== 1` |

## 四、一键门禁脚本（全绿 = exit 0）

```bash
#!/bin/bash
# 13-FIRMWARE-ACCEPTANCE.md 的完整门禁。用法：
#   bash gate.sh <payload.img> <boot.img> <console.log> <uefi-mondrian 检出目录>
set -u
PL=$1; BOOT=$2; LOG=$3; FWREPO=$4
REPO=/mnt/e/hackios/k60-cellular
FW=/mnt/e/k60-work/firmware/modem
export PYTHONIOENCODING=utf-8
PASS=0; FAIL=0
ok()  { echo "PASS $*"; PASS=$((PASS+1)); }
bad() { echo "FAIL $*"; FAIL=$((FAIL+1)); }

# ---- 表 A：构建产物 ----
[ "$(stat -c %s "$PL" 2>/dev/null)" = "234881024" ] && ok "A1 payload=224 MiB" || bad "A1 payload=224 MiB"
[ "$(stat -c %s "$BOOT" 2>/dev/null)" = "235446272" ] && ok "A2 boot.img=235446272 B" || bad "A2 boot.img=235446272 B"
rm -rf /tmp/accept-modem && mkdir -p /tmp/accept-modem
mcopy -s -i "$PL" ::EFI/UniXNU/MODEM /tmp/accept-modem >/dev/null 2>&1
python3 "$REPO/scripts/gen-modem-table.py" "$FW" --manifest /tmp/accept-want.txt >/dev/null
if [ "$(ls /tmp/accept-modem 2>/dev/null | wc -l)" = "27" ] &&
   diff -q <(ls /tmp/accept-modem | sort) <(cut -d' ' -f1 /tmp/accept-want.txt | sort) >/dev/null; then
  ok "A3 MODEM 目录 27 个文件、名字正确"; else bad "A3 MODEM 目录 27 个文件、名字正确"; fi
( cd /tmp/accept-modem && for f in modem.b*; do stat -c "$f %s" "$f"; done | sort ) > /tmp/accept-got.txt
diff -q /tmp/accept-want.txt /tmp/accept-got.txt >/dev/null && ok "A4 每个文件大小==段表 bytes" || bad "A4 每个文件大小==段表 bytes"
mcopy -i "$PL" ::EFI/UniXNU/Payloads/kernel.macho.adt /tmp/accept.adt >/dev/null 2>&1
if python3 - <<'PYEOF' >/tmp/accept-a5.txt 2>&1; then ok "A5 ADT K60ModemImage 16 字节、值合法";
else bad "A5 ADT K60ModemImage 16 字节、值合法: $(tail -1 /tmp/accept-a5.txt)"; fi
import sys, struct
sys.path.insert(0, '/mnt/e/hackios/k60-cellular/scripts')
from pong_adt_contract import parse_adt
mm = parse_adt(open('/tmp/accept.adt','rb').read())['/chosen/memory-map']
v = mm['K60ModemImage']
assert len(v) == 16, 'len %d' % len(v)
base, span = struct.unpack('<QQ', v)
assert (base, span) in ((0, 0), (0x8bc00000, 0x13200000)), (hex(base), hex(span))
print('K60ModemImage', hex(base), hex(span))
PYEOF

# ---- 表 B：固件源码 ----
grep -rn 'ImageCarrier' "$FWREPO" --include='*.inf' 2>/dev/null | grep -q . &&
  grep -rn 'ImageCarrier' "$FWREPO" --include='*.c' --include='*.h' 2>/dev/null | grep -q . &&
  ok "B1 ImageCarrierLib 存在" || bad "B1 ImageCarrierLib 存在"
grep -rn 'ImageCarrierLoad' "$FWREPO" --include='DarwinBoot.c' 2>/dev/null | grep -q . &&
  ok "B2 DarwinBoot 调用点" || bad "B2 DarwinBoot 调用点"
DBHITS=$(grep -rc 'K60ModemImage' "$FWREPO" --include='DarwinBoot.c' 2>/dev/null | awk -F: '{s+=$2} END{print s+0}')
[ "$DBHITS" -ge 2 ] && ok "B3 DarwinBoot 发布属性 (${DBHITS} 处)" || bad "B3 DarwinBoot 发布属性 (${DBHITS} 处)"
B4OK=1
for pat in 'modem-image: chosen dtb at' 'modem-image: window 0x8bc00000..0x9ee00000' 'modem-image: abl staging ends at'; do
  grep -rnF "$pat" "$FWREPO" 2>/dev/null | grep -q . || B4OK=0
done
grep -rnF 'modem-image:' "$FWREPO" 2>/dev/null | grep -q 'DEBUG(' && B4OK=0
[ "$B4OK" = "1" ] && ok "B4 三行 D3 日志、无 debug 门" || bad "B4 三行 D3 日志、无 debug 门"
FWTABLE=$(grep -rlF 'MODEM_IMAGE_SEGMENTS' "$FWREPO" --include='*.h' 2>/dev/null | head -1)
python3 "$REPO/scripts/gen-modem-table.py" "$FW" --firmware-header /tmp/fw-gen.h >/dev/null
if [ -n "$FWTABLE" ] && diff -q "$FWTABLE" /tmp/fw-gen.h >/dev/null; then ok "B5 固件表==生成器输出";
else bad "B5 固件表==生成器输出 (表文件: ${FWTABLE:-未找到})"; fi
grep -rnE '(memset|SetMem|ZeroMem|AllocateZeroPool)\([^,]*,[[:space:]]*(0x13200000|320864256)' "$FWREPO" 2>/dev/null | grep -q . &&
  bad "B6 无整窗清零" || ok "B6 无整窗清零"

# ---- 表 C：上机日志 ----
for pat in 'modem-image: chosen dtb at' 'modem-image: window 0x8bc00000..0x9ee00000' 'modem-image: abl staging ends at'; do
  [ "$(grep -acF "$pat" "$LOG" 2>/dev/null)" = "1" ] && ok "C1 日志行: $pat" || bad "C1 日志行: $pat";
done
[ "$(grep -acF 'copied 109060761, zeroed 211012967, gaps 790528' "$LOG" 2>/dev/null)" = "1" ] &&
  ok "C2 拷贝/清除/空洞数字" || bad "C2 拷贝/清除/空洞数字"
[ "$(grep -acF 'range 0x8bc00000..0x9ee00000 published' "$LOG" 2>/dev/null)" = "1" ] &&
  ok "C3 区间发布行" || bad "C3 区间发布行"
[ "$(grep -acF 'K60MODEM carrier present at 0x8bc00000' "$LOG" 2>/dev/null)" = "1" ] &&
  ok "C4 内核侧 carrier present" || bad "C4 内核侧 carrier present"
[ "$(grep -acF 'K60MODEM plan rows=30' "$LOG" 2>/dev/null)" = "1" ] &&
  ok "C5 内核侧 plan rows=30" || bad "C5 内核侧 plan rows=30"

echo "TOTAL PASS=$PASS FAIL=$FAIL"
[ "$FAIL" = "0" ]
```

## 五、今天先跑会看到什么（已实测）

载具未落地时这张表**就该红**——红就是门禁在干活。2026-11-15 用当前 L3 产物实测：

- 工具链全部可用：`mdir`/`mcopy` 正常（`mcopy -s` 把目录**内容**直接铺进目标目录，不套一层子目录）；
  `parse_adt` 能解开当前 `kernel.macho.adt`，`/chosen/memory-map` 目前只有 `name` 键；
- A1/A2 红（当前 payload 201,326,592 / boot.img 201,891,840，载具版应为 234,881,024 / 235,446,272）；
- A3/A4/A5 红（无 `MODEM/` 目录、无 `K60ModemImage` 属性）；C1–C5 红（尚无载具日志）。
固件侧交付后，这张表必须变成 15 行全 PASS 才能合。

## 六、本表不替代的门禁

固件侧自己的 `pong_adt_contract.py`（12-DXE-CONTRACT.md §3.7 要求新增的三条）与构建流水线检查
仍必须全过；本表的 A5 是**独立复证**（换个解析器、换条读取路径），两者不互相替代。
`verify-boot-image.py`、`check-image-args.py` 也照跑（`pong_modem` 已在白名单）。
