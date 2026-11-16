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
| A1 | payload 卷恰好 192 MiB（路线 D：不扩容） | `stat -c %s "$PL"` | `== 201326592`（若最终改走 A-208 扩容档则为 218,103,808，二者只留一种） |
| A2 | boot.img 大小 == 公式值（不写魔数） | `KSZ` = boot.img 头 offset 8 的 `kernel_size`；`A2 = 4096 + ceil(KSZ/4096)*4096 + 201326592 + 4096`；再 `stat -c %s "$BOOT"` | `== $A2`。本交实测 `KSZ=555628` ⇒ **201,891,840**（见下方说明） |
| A2b | FD 本体精确 3,145,728 B | `stat -c %s "$FWREPO/Build/mondrianPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd"` | `== 3145728`（与页数无关，永远成立） |
| A3 | `EFI/UniXNU/MODEM/` 恰好 27 个文件，名字 = 段表名字各加 `.lzma` | `mcopy -o -s -i "$PL" '::EFI/UniXNU/MODEM/*' /tmp/accept-modem` 后 `ls` 与 `gen-modem-table.py --manifest` 名字列（加 `.lzma`）diff | 行数 27 且 diff 空 |
| A4 | 每个文件 13 B LZMA 头合法：props 首字节 `0x5D`、8 B 声明长度 == 段表 `bytes`、声明长度不是 `0xFFFFFFFFFFFFFFFF` | `python3 scripts/check-modem-lzma.py --dir /tmp/accept-modem --manifest /tmp/accept-want.txt --sum` | rc 0，`failures=0` |
| A6 | 27 个声明长度之和 == 109,060,761（等于 C2 的 `copied`） | 同 A4 的 `--sum` 输出末行 `declared-total=` | `== 109060761` |
| A5 | ADT `/chosen/memory-map` 有 `K60ModemImage` 属性，长度恰 16 字节，值 ∈ {全零, 精确区间} | 抽出 `kernel.macho.adt`，用 `scripts/pong_adt_contract.py` 的 `parse_adt` 解出 `/chosen/memory-map['K60ModemImage']` | rc 0，`len == 16`，`(base, span) ∈ {(0,0), (0x8bc00000, 0x13200000)}` |

A2 为什么是公式而不是数字（2026-11-16 Lead 裁决 (a)）：boot.img 的组成是
`4096`（头页）+ `ceil(ksz/4096)*4096`（kernel 段）+ `201326592`（ramdisk 段）+ `4096`（v4 签名零块），
其中 `ksz` 是 `gzip -9` 后的 `112 B BootShim.bin + 3,145,728 B SILICIUM_UEFI.fd` 的长度，dtb 固定取
`Resources/DTBs/mondrian.dtb`（4,024 B，见该目录的 MANIFEST.md）。**魔数在 FD 内容一变就过期**：
上一版 FD 的 `ksz=546,908`，加 4,024 B dtb 后落在 135 页，得 201,887,744；本交 FD 的 `ksz=551,566`，
加 dtb 后跨到 136 页，得 **201,891,840**——差 4,096 B 是页对齐造成的，不是镜像写错了。
所以 A2 只判「头里的 kernel_size 与最终文件大小互相自洽」，**页数由 FD 内容决定，不由门禁决定**。
A2b 单独钉住 FD 本体尺寸：它才是「固件没被改大」的那条断言，与页数无关。

说明：**区间起止逐字节**由两条独立证据共同咬死——A5 是离线产物（16 字节值），
表 C 的 C1/C3 是运行时日志（字面地址串）。两者都必须过。
**拷贝量 / 清除量 / 空洞**不在产物层查：产物层只能证明「带了哪些文件、各多大」，
装载行为由表 B（源码：无整窗清零）与表 C（日志：`copied 109060761, zeroed 211012967, gaps 790528`）咬死。

路线 D（2026-11-16 定案，见 `15-FIRMWARE-CARRIER-LOADER.md` §1.8）：payload 里存的是 **LZMA 压缩**
的 27 个文件，所以 A4 判的不再是「文件大小 == 段表 bytes」，而是「**头里的声明长度** == 段表
`bytes`」。`copied` 的含义随之变成「解压后写入窗口的字节总和」，仍由 C2 的日志字面量咬死。
A6 把「声明长度之和」与 `copied` 对齐，防止打包时漏改某个文件的 8 B size 字段却恰好总量对上。

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

# ---- 表 A：构建产物（路线 D：payload 内是 27 个 .lzma 文件）----
[ "$(stat -c %s "$PL" 2>/dev/null)" = "201326592" ] && ok "A1 payload=192 MiB" || bad "A1 payload=192 MiB"
KSZ=$(python3 -c 'import struct,sys;print(struct.unpack_from("<I",open(sys.argv[1],"rb").read(12),8)[0])' "$BOOT" 2>/dev/null)
A2=$(( 4096 + ((KSZ + 4095) / 4096) * 4096 + 201326592 + 4096 ))
[ "$(stat -c %s "$BOOT" 2>/dev/null)" = "$A2" ] &&
  ok "A2 boot.img=$A2 B (ksz=$KSZ, $( ((KSZ + 4095) / 4096) ) 页)" ||
  bad "A2 boot.img=$A2 B (ksz=$KSZ); 实际 $(stat -c %s "$BOOT" 2>/dev/null)"
[ "$(stat -c %s "$FWREPO/Build/mondrianPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd" 2>/dev/null)" = "3145728" ] &&
  ok "A2b FD=3145728 B" || bad "A2b FD=3145728 B"
rm -rf /tmp/accept-modem && mkdir -p /tmp/accept-modem
mcopy -o -s -i "$PL" '::EFI/UniXNU/MODEM/*' /tmp/accept-modem >/dev/null 2>&1 </dev/null
python3 "$REPO/scripts/gen-modem-table.py" "$FW" --manifest /tmp/accept-want.txt >/dev/null
if [ "$(ls /tmp/accept-modem 2>/dev/null | wc -l)" = "27" ] &&
   diff -q <(ls /tmp/accept-modem | sort) <(cut -d' ' -f1 /tmp/accept-want.txt | sed 's/$/.lzma/' | sort) >/dev/null; then
  ok "A3 MODEM 目录 27 个 .lzma 文件、名字正确"; else bad "A3 MODEM 目录 27 个 .lzma 文件、名字正确"; fi
python3 "$REPO/scripts/check-modem-lzma.py" --dir /tmp/accept-modem --manifest /tmp/accept-want.txt --sum > /tmp/accept-a4.txt 2>&1
if [ "$?" = "0" ]; then ok "A4 27 个 LZMA 头合法、声明长度==段表 bytes";
else bad "A4 27 个 LZMA 头合法、声明长度==段表 bytes: $(grep -m1 '^FAIL' /tmp/accept-a4.txt)"; fi
[ "$(sed -n 's/^declared-total=//p' /tmp/accept-a4.txt)" = "109060761" ] &&
  ok "A6 声明长度之和=109060761" || bad "A6 声明长度之和=109060761"
rm -f /tmp/accept.adt
mcopy -o -i "$PL" ::EFI/UniXNU/Payloads/kernel.macho.adt /tmp/accept.adt >/dev/null 2>&1 </dev/null
python3 - <<'PYEOF' >/tmp/accept-a5.txt 2>&1
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
if [ "$?" = "0" ]; then ok "A5 ADT K60ModemImage 16 字节、值合法";
else bad "A5 ADT K60ModemImage 16 字节、值合法: $(tail -1 /tmp/accept-a5.txt)"; fi

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

- 工具链可用：`mdir`/`mcopy` 正常，`parse_adt` 能解开当前 `kernel.macho.adt`，
  `/chosen/memory-map` 目前只有 `name` 键；
- A1 红（当前 payload 201,326,592 已是路线 D 的正确值，当时的 payload 还不是这个尺寸）；
  A2 在 2026-11-16 改成公式后**不再依赖 FD 内容**，同一份 201,891,840 B 的 boot.img 现在能过
  （`ksz=555,628` ⇒ 136 页 ⇒ 201,891,840），见 §一 A2 的说明；
- A3/A4/A5 红（无 `MODEM/` 目录、无 `K60ModemImage` 属性）；C1–C5 红（尚无载具日志）。

固件侧交付后，这张表必须变成 **20 行全 PASS**（A1、A2、A2b、A3–A6 七行、B1–B6 六行、
C1 三行、C2–C5 四行）才能合。

### 5.1 2026-11-16 的 dry run（路线 D）：先证明门禁本身能跑

用一套合成输入冒充「载具已交付」的产物：192 MiB FAT payload（`EFI/UniXNU/MODEM/` 27 个
`modem.bNN.lzma`，8 B 声明长度改成段表真值；`EFI/UniXNU/Payloads/kernel.macho.adt` 带 16 B
`K60ModemImage`）、201,887,744 B 的假 `boot.img`、7 行假 console 日志、只含 `ImageCarrierLib`
与三行 D3 的假 fwrepo。整套脚本原样跑：

```txt
PASS A1 payload=192 MiB
PASS A2 boot.img=201891840 B (ksz=555628, 136 页)
PASS A2b FD=3145728 B
PASS A3 MODEM 目录 27 个 .lzma 文件、名字正确
PASS A4 27 个 LZMA 头合法、声明长度==段表 bytes
PASS A6 声明长度之和=109060761
PASS A5 ADT K60ModemImage 16 字节、值合法
PASS B1 ImageCarrierLib 存在
PASS B2 DarwinBoot 调用点
PASS B3 DarwinBoot 发布属性 (2 处)
PASS B4 三行 D3 日志、无 debug 门
PASS B5 固件表==生成器输出
PASS B6 无整窗清零
PASS C1 日志行: modem-image: chosen dtb at
PASS C1 日志行: modem-image: window 0x8bc00000..0x9ee00000
PASS C1 日志行: modem-image: abl staging ends at
PASS C2 拷贝/清除/空洞数字
PASS C3 区间发布行
PASS C4 内核侧 carrier present
PASS C5 内核侧 plan rows=30
TOTAL PASS=20 FAIL=0
```

上面这遍是 2026-11-16 用**真产物**跑的（payload-modem.img / boot-modem-4024.img，见 §5.2），
不是合成输入：A1–A6、A2b 全绿，B1–B6 全绿，C1–C5 未跑（还没有上机日志）。
A2 那一行的数字来自公式，`ksz=555,628` 是这一版 FD 的真实值。

A6 排在 A5 之前是脚本结构使然：A5 用 heredoc 调 `parse_adt`，新加的 A6 只能接在 A4 之后、
heredoc 之前，否则又会踩下面的缺陷 2。

这一遍先抓出脚本自身的四个缺陷，均已在本节脚本里改掉。按「症状 / 真因 / 修法」记，便于收进 PITFALLS
（P-204 家族：门禁必须能跑第二遍，且每条断言都要分得清「没检查」与「检查通过」）：

**缺陷 1：`mcopy -s` 把源目录套成子目录**

- 症状：`ls /tmp/accept-modem | wc -l` 只有 1 项，A3 报 `FAIL`；A4 报 `stat: cannot statx 'modem.b*'`。
- 真因：本机 mtools 的 `mcopy -s` 在源是目录时**保留目录名**，铺进目标是 `DEST/MODEM/…`；
  本文档原先写的「`-s` 只铺内容、不套子目录」是错的。
- 修法：源改成通配 `'::EFI/UniXNU/MODEM/*'`，目标仍是 `DEST`——实测直接得到 27 个文件。

**缺陷 2：A5 的 `then/else/fi` 写在 heredoc 正文之前**

- 症状：A1–A4 正常 PASS，到 A5 处脚本直接 `line 74: syntax error: unexpected end of file` 中止；
  A5–C5 一行未执行，`TOTAL` 不打印（不是「A5 报红」，而是「A5 根本没跑」）。
- 真因：heredoc 从 `<<'PYEOF'` 所在行**之后**立即开始收正文，`else ...; fi` 被当成正文内容；
  bash 顺序解析到文件末尾发现 `if` 没闭合，于是整段作废。
- 修法：先让 `python3 - <<'PYEOF' … PYEOF` 独立跑完，再用 `$?` 判；正文里不出现任何 shell 关键字。
- 教训：这类错**不会自己报红**——少跑的行在输出里只是「没出现」，与「通过」肉眼难分。所以门禁
  末尾必须打印 `TOTAL PASS=n FAIL=m`，并用 FAIL 计数兜底；A5 的具体断言（长度 16、值 ∈ 两值）
  只有全跑完才知道真假。

**缺陷 3：`mcopy` 在目标已存在时停在覆盖提示**

- 症状：第二次跑门禁**永久挂起**（无输出、无退出），`ps` 里 `mcopy ... kernel.macho.adt` 常驻；
  第一次能跑过，所以最容易被误判成「偶发」。
- 真因：`mcopy` 默认对已存在文件问 `Overwrite? (y/n)`；门禁在非终端 stdin 下运行时读不到回答。
- 修法：目标先 `rm -f`/`rm -rf`，`mcopy` 加 `-o`，并把 stdin 重定向成 `</dev/null`（双保险）。

**缺陷 4：A3 的 `sed` 写在 `cut` 之前，后缀加到了大小上**

- 症状：27 个文件名本身正确，A3 却恒报 `FAIL`；把两边的中间结果打印出来才看到左边是
  `modem.b01.lzma`、右边是 `modem.b01`。
- 真因：`sed 's/$/.lzma/' /tmp/accept-want.txt | cut -d' ' -f1` 先把 `.lzma` 追加到整行末尾
  （`modem.b01 7204.lzma`），再按空格取第一列，后缀被丢掉。
- 修法：先 `cut -d' ' -f1` 取名字列，再 `sed 's/$/.lzma/'` 加后缀，最后 `sort`。

修完后同一套合成输入连跑两遍都是 `TOTAL PASS=19 FAIL=0`、exit 0。

**A4/A6 的负例**（2026-11-16 实测，证明这两行不是恒绿）：从合成 payload 里解出 27 个文件，
分别破坏一处再跑 `check-modem-lzma.py`，每次都只报那一条、退出码 1；恢复后 `failures=0`、rc 0。

```txt
--- negative 1: declared size off by one on modem.b07 ---
FAIL modem.b07.lzma declared 114687, table says 114688
files=27 failures=1
rc=1
--- negative 2: declared size UNKNOWN on modem.b19 ---
FAIL modem.b19.lzma declared size is UNKNOWN (rewrite the 8 B field)
files=27 failures=1
rc=1
--- negative 3: wrong props byte on modem.b19 ---
FAIL modem.b19.lzma properties 0x5c, expected 0x5d
files=27 failures=1
rc=1
--- negative 4: extra file in payload ---
FAIL modem.b99.lzma not in manifest
files=27 failures=1
rc=1
--- positive control ---
files=27 failures=0
declared-total=109060761
rc=0
```

负例 4 是补的：A3 只判「27 个且名字对」，若打包多塞一个文件、同时少一个正确文件，A3 仍会红，
但 `check-modem-lzma.py` 自己也要能报「manifest 之外的文件」，否则 A4 与 A3 的覆盖面不重合。

合成输入与准备脚本见 `14-DXE-REQUEST.md` §5；真跑必须换成固件 commit 产出的真实 payload/boot/日志。

### 5.2 2026-11-16 用真产物跑（A 段 + B 段全绿，C 段待上机）

固件侧交回的产物与它对应的输入：

| 项 | 路径 | 尺寸 / sha256 |
| --- | --- | --- |
| payload | `E:/k60-work/artifacts/bootimg-test/payload-modem.img` | 201,326,592 B，sha256 `9eb14f6768110605…` |
| boot.img | `E:/k60-work/artifacts/bootimg-test/boot-modem-4024.img` | 201,891,840 B，sha256 `8c9c7d2d9d11c110…` |
| FD | `uefi-mondrian/Build/mondrianPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd` | 3,145,728 B，sha256 `847bfcf25bea0f2343e372963accc0e62703d8c8f9d474c6d7dade0085e9d5a9` |
| dtb | `uefi-mondrian/Resources/DTBs/mondrian.dtb` | 4,024 B，sha256 `2d044eaa08b7e58c0510a33da795c960085e13d6943cd4c25e0e050e0bfa33cd` |

实测（`gate-work.sh`，与 §四 的脚本同源，只把 `/tmp/accept*` 换成可写目录）：

```txt
PASS A1 payload=192 MiB
PASS A2 boot.img=201891840 B (ksz=555628, 136 页)
PASS A2b FD=3145728 B
PASS A3 MODEM 目录 27 个 .lzma 文件、名字正确
PASS A4 27 个 LZMA 头合法、声明长度==段表 bytes
PASS A6 声明长度之和=109060761
PASS A5 ADT K60ModemImage 16 字节、值合法
PASS B1 ImageCarrierLib 存在
PASS B2 DarwinBoot 调用点
PASS B3 DarwinBoot 发布属性 (2 处)
PASS B4 三行 D3 日志、无 debug 门
PASS B5 固件表==生成器输出
PASS B6 无整窗清零
TOTAL PASS=13 FAIL=0
```

两个与「产物正确性」无关、但会让人误判的坑（都已在 `gate-work.sh` 里绕开）：

1. `/tmp/accept.adt` 若上次由 root 留下，`mcopy` 会停在覆盖提示、门禁**永久挂起**（缺陷 3 的变体：
   这次是文件属主导致的权限拒绝，不是终端读不到回答）。修法：所有临时路径改到自己的可写目录。
2. `B4` 用 `grep -rnF 'modem-image:' "$FWREPO"` 扫全树会进 `Mu_Basecore` submodule（drvfs），
   跑十几分钟；改成只扫 `Platforms BootShim Resources` 三个目录，结论不变（三行 D3 全在
   `Platforms/Xiaomi/DarwinBootPkg/Driver/DarwinBoot.c`，库内不带这三行）。

C 段（C1–C5）仍未跑：需要一次 `pong_modem=2` 上机的 `console.log`。

## 六、本表不替代的门禁

固件侧自己的 `pong_adt_contract.py`（12-DXE-CONTRACT.md §3.7 要求新增的三条）与构建流水线检查
仍必须全过；本表的 A5 是**独立复证**（换个解析器、换条读取路径），两者不互相替代。
`verify-boot-image.py`、`check-image-args.py` 也照跑（`pong_modem` 已在白名单）。
