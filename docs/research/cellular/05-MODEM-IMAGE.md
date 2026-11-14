# 05 — modem 镜像段表与 L1 加载器（K60ModemImage）

日期：2026-11-14。分支 `feat/cellular`（worktree `E:/hackios/k60-cellular`）。
上游任务书：Lead 2026-11-14 的 cellular L1 任务（「把 0611/0613 同款的 ADSP 加载器模式套到 modem」）。

**一句话结论**：`modem.mdt` 是 ELF32 容器，含 30 个 `PT_LOAD`，覆盖 `0x8bc00000..0x9ee00000`，
与 DT 里 `mpss-region` 的 `reg = <0x00 0x8bc00000 0x00 0x13200000>` **逐字节吻合**；
段表已固化成 `drivers/PongCellular/pong_modem_table.h`，加载器 `K60ModemImage.c` 只做「校验 + 按字节搬 + 逐段清 bss」，
宿主测试两个（Python 段表/补丁一致性、C 加载器行为）全绿，补丁 `patches/xnu/0620-k60-modem-image.patch` 已挂进 `patches/xnu/series`。
**这一轮没有做 PAS 握手**（`PAS_INIT_IMAGE`/`AUTH_AND_RESET`），那是 L2；本轮交付物是「能被内核编译进去且行为可验证的搬运器」。

---

## 1. 三条互相独立的证据链

段表的正确性不靠单一来源。下面三条证据彼此独立，且结论一致：

| 证据 | 来源 | 它单独能证明什么 |
|---|---|---|
| ELF 段表 | 设备上 `/vendor/firmware_mnt/image/modem.mdt`（5884 B，sha256 `78d5f2f45aefeab7d2920bc5753009ade0371aa7d9be5eb0f2d21a72704c1fb8`） | 30 个段的 paddr/大小/顺序 |
| 设备树 carveout | 活 Android DT `/proc/device-tree/reserved-memory/mpss-region@8bc00000/reg`，抄进 `dts/mondrian.dts:231-234` | 目标窗口的基址与长度 |
| Android 分区布局 | `/dev/block/sde7` = `modem_a` 380 MiB，只读 vfat 挂 `/vendor/firmware_mnt`（`docs/research/cellular/01-ANDROID-INVENTORY.md:15`、`:75-82`） | 固件确实来自 modem 分区，不是打包进 boot 的 |

三条对上的具体数字：ELF 段表里最低 paddr = `0x8bc00000`、最高段结束 = `0x9ee00000`；
DT 的 `mpss-region` 基址 = `0x8bc00000`、长度 = `0x13200000`，`0x8bc00000 + 0x13200000 = 0x9ee00000`。
即**镜像的最低地址贴着窗口下界、最高地址贴着窗口上界**，这不是巧合能解释的。

`docs/research/cellular/02-DT-TRUTH.md:202-203` 早已记下这个吻合，但当时没有段表逐行数据；本文补上。

---

## 2. `modem.mdt` 头部实测

解析脚本：`scripts/gen-modem-table.py`（`struct.unpack_from` 直读，不依赖 pyelftools）。

```
size        5884
magic       \x7fELF      class 1 (ELF32)      data 1 (LE)
e_machine   0xa4        (AArch64)
e_entry     0x8bc00000  (= 第一个 PT_LOAD 的 p_paddr，即入口就是镜像基址)
e_phoff     52
e_phentsize 32
e_phnum     32          (其中 2 条 type=0，有效 PT_LOAD 30 条)
```

`phdr[0]` 与 `phdr[31]` 的 `p_type == 0`（`PT_NULL`），**不参与装载**。它们各自对应一个真实存在的文件：

- `modem.b00` = 1076 B，正好等于 `phdr[0].p_filesz`；
- `modem.b31` = 4808 B，正好等于 `phdr[31].p_filesz`。

这两个文件在 `image/` 目录里存在、大小与 phdr 一致，但 `p_type == 0` 意味着 bootloader/PAS 不会把它们拷进 carveout。
加载器必须**按 p_type 过滤**，不能按「文件存在就装」或「按 bNN 序号顺序装」。
`scripts/gen-modem-table.py` 的过滤条件就是 `p_type == 1`（`PT_LOAD`）。

---

## 3. 30 个 `PT_LOAD` 全表

列含义：`idx` = phdr 索引（也是文件名 `modem.b%02d` 的编号）；`paddr` = 目标物理地址；
`filesz` = 从文件拷贝的字节数；`memsz` = 段占用总字节；`bss` = `memsz - filesz`（必须清零）；
`gap` = 与上一段结束之间的空洞（PAS 不碰，加载器也不碰）。

| idx | 文件 | paddr | filesz | memsz | bss | gap |
|---|---|---|---|---|---|---|
| 1 | `modem.b01` | `0x8bc00000` | 7204 | 8192 | 988 | — |
| 2 | `modem.b02` | `0x8bc02000` | 805556 | 806912 | 1356 | — |
| 3 | `modem.b03` | `0x8bcc7000` | 14756 | 16384 | 1628 | — |
| 4 | `modem.b04` | `0x8bccb000` | 15588 | 16384 | 796 | — |
| 5 | `modem.b05` | `0x8bccf000` | 13112 | 16384 | 3272 | — |
| 6 | `modem.b06` | `0x8bcd3000` | 34880 | 36864 | 1984 | — |
| 7 | `modem.b07` | `0x8bd00000` | 114688 | 114688 | 0 | 0x24000 |
| 8 | `modem.b08` | `0x8bd20000` | 2743284 | 2744320 | 1036 | 0x4000 |
| 9 | `modem.b09` | `0x8bfc0000` | 37184 | 40960 | 3776 | 0x2000 |
| 10 | `modem.b10` | `0x8bfd0000` | 49152 | 49152 | 0 | 0x6000 |
| 11 | `modem.b11` | `0x8bfdc000` | 4138640 | 4141056 | 2416 | — |
| 12 | `modem.b12` | `0x8c400000` | 262144 | 262144 | 0 | 0x31000 |
| 13 | `modem.b13` | `0x8c440000` | 4784128 | 4784128 | 0 | — |
| 14 | `—（纯 bss，无文件）` | `0x8c8d0000` | 0 | 4096 | 4096 | — |
| 15 | `modem.b15` | `0x8c8d1000` | 3518216 | 3518464 | 248 | — |
| 16 | `modem.b16` | `0x8cc40000` | 473648 | 475136 | 1488 | 0x14000 |
| 17 | `modem.b17` | `0x8ccc0000` | 3690496 | 3690496 | 0 | 0xc000 |
| 18 | `modem.b18` | `0x8d045000` | 14095752 | 45514752 | 31419000 | — |
| 19 | `modem.b19` | `0x8fbad000` | 16584207 | 16584704 | 497 | — |
| 20 | `modem.b20` | `0x90b7e000` | 6541320 | 6545408 | 4088 | — |
| 21 | `—（纯 bss，无文件）` | `0x911c0000` | 0 | 163696640 | 163696640 | 0x4000 |
| 22 | `modem.b22` | `0x9addd000` | 120256 | 122880 | 2624 | — |
| 23 | `modem.b23` | `0x9ae00000` | 40935488 | 40939520 | 4032 | 0x5000 |
| 24 | `modem.b24` | `0x9d510000` | 8377984 | 8380416 | 2432 | 0x5000 |
| 25 | `modem.b25` | `0x9dd40000` | 1290846 | 1294336 | 3490 | 0x32000 |
| 26 | `modem.b26` | `0x9de7c000` | 8960 | 12288 | 3328 | — |
| 27 | `modem.b27` | `0x9de7f000` | 290304 | 290816 | 512 | — |
| 28 | `modem.b28` | `0x9dec6000` | 102208 | 102400 | 192 | — |
| 29 | `modem.b29` | `0x9dedf000` | 10760 | 12288 | 1528 | — |
| 30 | `—（纯 bss，无文件）` | `0x9dee2000` | 0 | 15851520 | 15851520 | — |

汇总：

```
段数            30
拷贝字节        109,060,761
bss 字节        211,012,967
合计足迹        320,073,728   (0x1313F000)
窗口            320,864,256   (0x13200000)
余量            790,528       (0x000C1000)
span            0x8bc00000 .. 0x9ee00000
```

### 3.1 全部 30 段都是 4096 对齐的

`paddr % 4096 == 0` 且 `(paddr + memsz) % 4096 == 0`，30 段无一例外。
这一点让 `scripts/gen-modem-table.py` 可以要求 `p_offset % 4096 == 0`（ELF 文件内的偏移也全部页对齐），
同时也是「按段拷贝」与「按页拷贝」在本镜像上恰好等价于地址计算的原因 —— 但**不等于可以按页拷贝**，见 §6.1。

### 3.2 空洞合计正好等于余量

11 处空洞：`0x24000 + 0x4000 + 0x2000 + 0x6000 + 0x31000 + 0x14000 + 0xc000 + 0x4000 + 0x5000 + 0x5000 + 0x32000`
= `0x000C1000` = 790,528 B，**正好等于窗口减足迹的余量**。

这构成一个自洽性证明：镜像并不是「连续填满 306 MiB」，而是「30 个段 + 11 个洞，最外沿恰好顶到窗口两端」。
如果 DT 的 `reg` 长度写错（比如写成 0x13210000 或 0x13100000），这个等式立刻不成立。

---

## 4. 三个「文件缺失」的段其实是纯 bss 段

`image/` 目录里**没有** `modem.b14`、`modem.b21`、`modem.b30`。最初的直觉是「固件不完整」，实测否定：

| idx | paddr | p_filesz | p_memsz | 结论 |
|---|---|---|---|---|
| 14 | `0x8c8d0000` | **0** | 4096 | 纯 bss，4 KiB |
| 21 | `0x911c0000` | **0** | 163,696,640 | 纯 bss，156 MiB |
| 30 | `0x9dee2000` | **0** | 15,851,520 | 纯 bss，15.1 MiB |

三个文件的 `p_filesz` 都是 0，所以「文件不存在」是**正确状态**，不是缺件。
这与 ADSP 的 `adsp.b24`（纯 bss 7,245,824 B）是同一形态（`docs/research/audio/ADSP-PAS1.md:30-44`）。

生成器与加载器都据此把 `part` 写成 `((const char *)0)`：

```c
{ 0x8c8d0000UL,        0,      4096, ((const char *)0) }, /* segment 14 */
{ 0x911c0000UL,        0, 163696640, ((const char *)0) }, /* segment 21 */
{ 0x9dee2000UL,        0,  15851520, ((const char *)0) }, /* segment 30 */
```

加载器对 `part == NULL` 的行**只清 bss、不读文件**；对 `bytes == 0 && bss == 0` 的行才报 `K60ModemBadSegment`。
（ADSP 加载器的同一条校验在 `drivers/PongPower/K60AdspImage.c` 的 `k60_adsp_plan`。）

### 4.1 seg21 的 bss 比整个拷贝量还大

`seg21.bss = 163,696,640` > 全部拷贝字节 `109,060,761`。
这直接否掉了「先把整个 306 MiB 窗口清零，再逐段拷贝」的写法 —— 那样会写 320 MiB，
其中 156 MiB 会被 seg21 的清零再覆盖一遍。正确做法：**只对每个段自己的 `[paddr+filesz, paddr+memsz)` 区间清零**，
这也是 `k60_modem_copy` 的实现。

---

## 5. PAS id = 4（不是 1，也不是 IPA 的 15）

L2 要发 `PAS_INIT_IMAGE` / `PAS_AUTH_AND_RESET` 时必须带对 peripheral id，写错就是「SCM 返回非 0」或者更糟 ——
打到别的远程处理器上。取证如下：

1. `E:/k60-work/references/UniXNU-pong-upstream/scripts/make-pong-adt-ipados18.py:320`：
   `('pong,pas-id', struct.pack('<I', 4))`，同一节点的 `:317` 是 `compatible = "qcom,cape-modem-pas"`、
   `:319` 是 `model = "Qualcomm Snapdragon X65"`、`:321` 是 `pong,firmware-region` 0x8bc00000/0x13200000、`:322` 是 `pong,ipa-version 0x0501`。
2. 参考实现 `E:/k60-work/references/phk110-port/drivers/modem/hakios.mpss.c:1050`：
   `#define PAS_MPSS_DEFAULT 4 /* dt: qcom,pas-id of qcom,mss */`；同文件 `:1794` `#define PAS_IPA_DEFAULT 15`（IPA 是 15，别混）。
3. **活 Android DT 的 `remoteproc-mss@04080000` 没有 `qcom,pas-id` 属性**。
   实测 `od` 该路径报 `No such file or directory`；属性全集只有 clock-names/clocks/compatible/cx-supply/cx-uV-uA/glink-edge/
   interconnect-names/interconnects/interrupt-names/interrupts-extended/memory-region/mx-supply/mx-uV-uA/name/phandle/
   `qcom,qmp`/`qcom,smem-state-names`/`qcom,smem-states`/reg/reg-names/status。
   所以 4 **不是从 DT 字面值读来的**，而是 cape 平台的编译期默认 + pong ADT 记录。

⇒ 本树 DT（`dts/mondrian.dts:250-283`）也照抄了「无 `qcom,pas-id`」的形态；
L2 写 PAS 代码时应把 4 写成代码里的常量并注明出处，**不要**去 DT 里找这个属性。
（`qcom,ipa@3e00000` 的 `pas-ids = <0x0f>` 是 IPA 的 15，与 modem 无关，见 `dts/mondrian.dts:295-334`。）

---

## 6. 代码：`K60ModemImage.h` / `K60ModemImage.c`

刻意与 ADSP 加载器**同形**（`drivers/PongPower/K60AdspImage.h` / `.c`），只换常量与命名，
理由是：同一套校验语义已经在 ADSP 上过了真机（audio 线），换一套写法等于重新引入未知。

```c
/* drivers/PongCellular/K60ModemImage.h */
enum { K60ModemBadArg = -1, K60ModemBadSegment = -2, K60ModemOutsideWindow = -3,
       K60ModemOverlap = -4, K60ModemReadFailed = -5 };

typedef struct {
    uint32_t paddr;
    uint32_t bytes;
    uint32_t bss;
    const char *part;
} K60ModemSegment;

#include "pong_modem_table.h"      /* K60_MODEM_BASE / WINDOW / SEGMENTS + 30 行表 */

typedef struct {
    uint32_t base; uint32_t window; uint32_t segments;
    uint32_t copied; uint32_t zeroed;
} K60ModemPlan;

typedef int (*K60ModemRead)(const char *part, void *dst, uint32_t bytes);

int k60_modem_plan(K60ModemPlan *plan);
int k60_modem_copy(void *window, size_t window_bytes, K60ModemRead read);
```

`k60_modem_plan` 的校验顺序（与 ADSP 完全一致）：

1. `bytes == 0 && bss == 0` → `K60ModemBadSegment`（空行）
2. `bytes != 0 && part == NULL` → `K60ModemBadSegment`（有数据却没文件名）
3. `!in_window(paddr, bytes + bss)` → `K60ModemOutsideWindow`
4. `i && s->paddr < prev_end` → `K60ModemOverlap`（按表顺序检查，表必须已按 paddr 升序）

`in_window` 用 64 位算术避免 `paddr + bytes` 溢出：

```c
static bool in_window(uint32_t paddr, uint32_t bytes)
{
    return paddr >= K60_MODEM_BASE &&
        (uint64_t)paddr + bytes <= (uint64_t)K60_MODEM_BASE + K60_MODEM_WINDOW;
}
```

`k60_modem_copy` 要求 `window && read && window_bytes >= K60_MODEM_WINDOW`，然后逐段：

```c
uint8_t *at = (uint8_t *)window + (s->paddr - K60_MODEM_BASE);
if (s->bytes) { if (read(s->part, at, s->bytes) != 0) return K60ModemReadFailed; }
for (uint32_t z = 0; z < s->bss; z++) at[s->bytes + z] = 0;
```

### 6.1 为什么必须按字节拷，不能按页拷

段起点页对齐，但**文件末尾不对齐**：

- `modem.b19`：从 `0x8fbad000` 起 16,584,207 B，结束于 `0x90b7de0f`；
- `modem.b25`：从 `0x9dd40000` 起 1,290,846 B，结束于 `0x9de7b25e`。

按页拷会多写最多 4095 B 到下一段的地盘（或窗口外）。ADSP 那边有同样的形态（`adsp.b10` 装在 `0x86e0b2c0`），
所以 `K60AdspImage.c` 的注释与这里一致：**PAS 按字节搬**。

---

## 7. 表是生成的，不是手写的

`scripts/gen-modem-table.py`（109 行）从 `modem.mdt` 直读 phdr 生成 `pong_modem_table.h`。
关键点：

- `find(root, name)` **先试 `name + '.bin'`，再试 `name`**。
  这是踩出来的：`E:/k60-work/firmware/modem/` 里同时存在 `modem.b01`（7232 B，被 `adb shell` 的 CRLF 转换污染）
  与 `modem.b01.bin`（7204 B，`adb exec-out` 的字节精确副本）。第一次生成时报
  `modem.b01 is 7232 bytes, table says 7204`，根因就是拿到了污染副本。
  **取固件必须用 `adb exec-out`，不能用 `adb shell`**（`docs/research/cellular/01-ANDROID-INVENTORY.md` 已记）。
- 校验：ELF32 / `e_phentsize == 32` / `p_offset % 4096 == 0` / `memsz >= filesz` /
  `filesz > 0` 时文件必须存在且大小相等。任一失败即 `SystemExit`，不会写出半张表。
- 表头三行注释里写明「Generated by ... Do not edit」，与 `pong_adsp_table.h` 同格式。

重新生成的命令：

```bash
python3 scripts/gen-modem-table.py E:/k60-work/firmware/modem > drivers/PongCellular/pong_modem_table.h
```

---

## 8. 注册进内核的三处改动

### 8.1 `patches/xnu/0620-k60-modem-image.patch`

三个 new file：`bsd/dev/pong_modem_image.c`、`bsd/dev/pong_modem_image.h`、`bsd/dev/pong_modem_table.h`。
格式沿用 0612：`new file mode 100644` + `index 0000000..1111111` + `--- /dev/null` + `+++ b/X` + **`@@ -0,0 +1,N @@`**。
最后那个 hunk 头是硬要求 —— 写成 `@@ -0,0 +1 @@` 会让 `git apply` **静默生成 0 字节文件**（`LEDGER.md:245`）。

`patches/xnu/series` 末尾追加一行（现 230 行）：

```
0620-k60-modem-image.patch
```

紧接在 `0616-k60-init-legacy-helper.patch` 之后。

### 8.2 `scripts/append-conffiles.py`

conf/files 的 hunk **不能在 patch 里锚定**（树是重建的，P-171），所以由构建驱动在 anchor 出现后追加。
在 `ENTRIES` 里 `pong_adsp_image.c` 之后插入：

```python
"bsd/dev/pong_modem_image.c\t\t\tstandard",
```

`ANCHOR` 不变（`bsd/dev/pong_buttons.c\t\t\tstandard`）。
注意：本 worktree 的 `ENTRIES` 比 `origin/main` 少一条 `pong_pmic_rail.c`（main 已加，本分支落后 78 个提交）；
merge 时这一处会冲突，按「两边都保留」解决即可。

### 8.3 为什么代码不放 `drivers/PongPower/`

`scripts/check-adsp-claims.py` 的 `GUARDED` 前缀包含 `drivers/PongPower/K60Adsp*`、`K60Fat`、`K60Smem`、`patches/xnu/061`；
改动这些前缀必须在 `docs/research/audio/ADSP-CLAIMS.toml` 里有 verified 断言。
modem 代码放 `drivers/PongCellular/` + `patches/xnu/062x`，天然避开这道门禁，也不去动 audio 线的证据文件。

---

## 9. 宿主测试

### 9.1 `scripts/tests/test-k60-modem-image.py`

四组检查，最后一项是**防漂移**：

1. `modem.mdt` 结构：ELF32、`e_phentsize == 32`、`e_phnum == 32`、`PT_LOAD == 30`；
2. 逐段：`filesz == 0` 的段必须**没有**对应文件；`filesz > 0` 的段文件必须存在且大小相等；`memsz >= filesz`；
   页对齐；按 paddr 排序后不重叠；
3. 边界：`lo == K60_MODEM_BASE` 且 `hi == K60_MODEM_BASE + K60_MODEM_WINDOW`；
4. 交叉校验 `pong_modem_table.h` 的 base/window/segments 与 30 行的 paddr/bytes/bss/part，
   **并且**解析 `0620` 补丁里的三个 new file，与 repo 里的三份文件逐字节比对（include 名归一化后）。
   这一步保证「内核里编译的那份」和「测试验的那份」永远是同一份。

实测输出：

```
NOTE modem.b14 is pure bss (4096 bytes, no file)
NOTE modem.b21 is pure bss (163696640 bytes, no file)
NOTE modem.b30 is pure bss (15851520 bytes, no file)
TESTS OK 30 segments, 0x8bc00000..0x9ee00000 (320864256 bytes), base 0x8bc00000, table+patch agree
```

### 9.2 `scripts/tests/test-k60-modem-loader.c`

真分配 `0x13200000` 字节，填 `0x11`，然后用 `stub_read`（填 `0xa5` 并计数）跑 `k60_modem_plan` + `k60_modem_copy`：

- `plan.segments == 30`、`plan.copied == 109060761`、`plan.zeroed == 211012967`；
- `reads` 次数 == 有 `bytes` 的行数（27），`bytes_read == plan.copied`；
- **逐段**检查首字节与末字节是 `0xa5`、bss 首字节与末字节是 `0`（不是只查第一段和最后一段）；
- 末段之后的字节仍是 `0x11`（若末段正好顶到窗口末尾，则要求 `buf[window-1] == 0`）；
- `failing_read` → `K60ModemReadFailed`；`NULL` window / 短 window / `NULL` plan → `K60ModemBadArg`。

编译与运行：

```bash
gcc -O1 -Wall -Wextra -Werror -Idrivers/PongCellular \
    -o /tmp/t-modem scripts/tests/test-k60-modem-loader.c drivers/PongCellular/K60ModemImage.c
/tmp/t-modem
```

实测输出：

```
plan segments=30 copied=109060761 zeroed=211012967 base=0x8bc00000 window=0x13200000
TESTS OK 7
```

---

## 10. 与 ADSP 加载器的差异（只有这些）

| 项 | ADSP | modem |
|---|---|---|
| 基址 | `0x86300000` | `0x8bc00000` |
| 窗口 | `0x03100000` (49 MiB) | `0x13200000` (306 MiB) |
| `e_phnum` | 26 | 32 |
| 有效 `PT_LOAD` | 24 | 30 |
| 纯 bss 段 | 1 个（`adsp.b24`，7,245,824 B） | 3 个（`b14`/`b21`/`b30`，合计 179,552,256 B） |
| 表文件 | `pong_adsp_table.h` | `pong_modem_table.h` |
| 生成器 | `scripts/gen-adsp-table.py` | `scripts/gen-modem-table.py` |
| PAS id | 1（`K60_PAS_ADSP`） | **4**（见 §5） |
| 拷贝方式 | 按字节 | 按字节（同） |

顺带纠正一处旧文档：`docs/research/cellular/03-SCOPE.md:54` 写「只需换 e_phnum（ADSP 26 → modem 32）」；
实测 ADSP 的 `adsp.mdt` 是 5404 B、`e_phnum = 26`、`type=0` 出现在 index 0 与 25 ⇒ **有效 PT_LOAD 24**。
准确说法是「`e_phnum` 26 → 32，有效 `PT_LOAD` 24 → 30」。

---

## 11. 这一轮没做的事（明确边界）

- **没有 PAS 握手**：`PAS_INIT_IMAGE` / `PAS_MEM_SETUP` / `PAS_AUTH_AND_RESET` / `PAS_SHUTDOWN` 都没写。
  本轮交付的是「能把 30 个段正确搬进 carveout 的搬运器」，不负责让 X65 跑起来。
- **没有读分区**：`K60ModemRead` 只是回调类型，真正的 FAT 读（从 `modem_a` 分区挂 vfat 找 `image/modem.bNN`）在 L2 接。
- **没有检查 modem 是否已在运行**：Android 侧 `/sys/class/remoteproc/4080000.remoteproc-mss/state` 现在是 `running`，
  从 Android 热切过来时它已经在跑。加载前必须先判这个状态（`patches/cellular/README.md` 的禁止事项第 3 条），
  否则等于对运行中的 PAS 发 `AUTH_AND_RESET`。这是 L2 的第一件事。
- **没有碰 IPA**（`qcom,ipa@3e00000`，pas-id 15）。数据通路是 L3+。
- **没有 boot**。按 Lead 任务书，镜像与脚本准备好后交 Lead，由 Lead 在用户明确同意后执行。

### 下一步（L2）的判据

1. 读 `modem_a` 分区（`/dev/block/sde7`，vfat，只读挂载）拿 30 个段；
2. 检查 `4080000.remoteproc-mss` 是否已 running（是则先 `PAS_SHUTDOWN` 或直接放弃本轮）；
3. `PAS_MEM_SETUP` → 逐段 `PAS_INIT_IMAGE` → `PAS_AUTH_AND_RESET`（peripheral = 4）；
4. 等 SMP2P `ready`（IPCC client 0，signal 2，见 `dts/mondrian.dts:250-283` 的 `interrupt-names = "ready"`）；
5. GLINK over SMEM 建 `IPCRTR` 通道 → 发 QRTR `NEW_LOOKUP` 到 node 0 → 收 20 字节应答且服务号 ∈ {21,1,11,3,16}。

---

## 12. 复现全部检查

```bash
# 1) 段表一致性 + 补丁一致性
python3 scripts/tests/test-k60-modem-image.py

# 2) 加载器行为
gcc -O1 -Wall -Wextra -Werror -Idrivers/PongCellular \
    -o /tmp/t-modem scripts/tests/test-k60-modem-loader.c drivers/PongCellular/K60ModemImage.c && /tmp/t-modem

# 3) 补丁可被 git apply 解析
python3 scripts/check-patch-apply.py --all
```

`check-patch-apply.py --all` 实测：`✅ 305 个改动的补丁都能被 git apply 解析（P-162）`。

---

## 13. 文件清单

| 文件 | 行/字节 | sha256 |
|---|---|---|
| `drivers/PongCellular/K60ModemImage.h` | — | `dcd8c980dbdca1d2ce855616ed832d244d46f67aea4ec44309c5581e8dd01707` |
| `drivers/PongCellular/K60ModemImage.c` | 74 行 | `aee32a35be73de30318796f3fca2ae34a0d50ea19328fa94ea3c3356716527ea` |
| `drivers/PongCellular/pong_modem_table.h` | 39 行 | `edd4bda36094ca4cea818fc9ee49990e27a5e9b2ba5633da822471321b10e37a` |
| `scripts/gen-modem-table.py` | 109 行 | `a1dfc346970a092932bda080648d16b2d10eded080e8dd26c64d4cf69feb84ac` |
| `scripts/tests/test-k60-modem-image.py` | — | `545995d1aa16e58a5e38cc37e95ab0f3cbed7c5ac67ab5e589c54931e8540af8` |
| `scripts/tests/test-k60-modem-loader.c` | 113 行 | `fda7df1250b6dcfbb2a91b98365d539c466612679fd3a55fc7555e21de247cf7` |
| `patches/xnu/0620-k60-modem-image.patch` | 200 行 | `77943f480c7cd88a59e58806f221b70e3aeb32a4870fe22ca44c48bcff38caeb` |

固件侧（不进仓库，只做证据）：`modem.mdt` 5884 B / `78d5f2f4…`；`modem.b00` 1076 B / `28b59b8e…`；
`modem.b23` 41,229,188 B / `da38557b…`。全部 30 个文件在 `E:/k60-work/firmware/modem/*.bin`，合计 109,072,529 B。
