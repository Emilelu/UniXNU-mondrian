# S2 规格：把 F1 / F11 / F3 三个偏差修进 0500 后端

状态：2026-11-14 已生成补丁并离线验证，**未上机**。本文件对应 `docs/research/bt/06-DEEP-DIVE.md`
里的 F1（阻塞 S2）、F11（阻塞 S1）、F3（阻塞 S2）三条偏差，以及顺带补上的 F12。

- 补丁：`patches/xnu/0508-k60-bt-s2-smmu-rcg-reset.patch` = `patches/bt/0002-k60-bt-s2-smmu-rcg-reset.patch`
- sha256 `c4bf1ded55fe9bd03b7c10943ed41fff47464037c06c893b6dfd0984f02fd4f2`，18,393 B / 391 行
- 作用对象：`patches/xnu/0500-k60-bt-qbt-new-files.patch` 创建的 `bsd/dev/qbt_k60.c`
  （抽取值 1,249 行，sha256 `8451c8706ecf75a79fba49ba7e3bda769ee73fcac5f357a46c9d484df3878748`），
  必须排在 `0507`（S1c 只读探针）**之后**——两者的锚点不重叠，顺序由 `series` 决定。
- 接线：**选项 B**，`patches/xnu/series` 在 `0507` 之后插入一行；`patches/bt/series` 同步登记。

## 1. 三处修改分别修什么

| 偏差 | 改法 | 证据 |
|---|---|---|
| **F1** GENI DMA 把虚拟指针当物理地址、SMMU 流 0x483 从未 bypass | `#ifdef KERNEL` 走 `kmem_alloc_contig` + `pmap_find_phys` + `ptoa_64`，再调用本文件内新建的 `k60_smmu_bypass(dma_pa, bytes)`；失败即 `kmem_free` 回卷，控制器绝不启动 | 板子自己的 `bsd/dev/k60_usblog.c`（`patches/xnu/0300`）已用同一套 planner 为 DWC3 流 0 装 bypass，并在每次启动打印 `SMMU sCR0 0x00200406`；FDT `mondrian.dts:10715` `iommus = <0x5b 0x483 0>`；官方路径见 `docs/porting/bluetooth.md:45-62` 第 1 步 |
| **F11** SE20 RCG 根时钟从未打开 | `k60_gcc_set_se_rate()` 先读 CMD：若 `ROOT_OFF` 置位则写 `ROOT_EN` 并轮询 500×1 µs；再写 CFG；最后 `CMD = (cmd & ~ROOT_OFF) \| ROOT_EN \| UPDATE` 并轮询 `UPDATE`/`ROOT_OFF` 同时清零 | Linux `clk-rcg2.c:64-75`（`is_enabled()` = `ROOT_OFF` 清零）、`:981-1002`（`set_force_enable()`）、`:111-135`（`update_config()`）；触摸线对 QUP0 SE4 做过同样的动作并活着读到 SE 寄存器（`zzzz…pong-touch-console.patch:307-339`） |
| **F3** `k60_stop_engine()` 轮询 0xe40（任何 GENI 头文件里都不存在） | 改成读 `SE_DMA_TX_IRQ_STAT 0xC40` / `SE_DMA_RX_IRQ_STAT 0xD40` 的 `TX_RESET_DONE`/`RX_RESET_DONE` BIT(3)；FSM reset 用 `0xC58`/`0xD58` 具名宏 | `linux-geni-se-v6.6.h:106`/`:110`/`:240`/`:246`；`qcom_geni_serial.c:1004-1010` |
| **F12**（顺带）首个 SE 访问前没有 CBCR 就绪检查 | `k60_gcc_set_se_rate()` 结尾 `return k60_gcc_wait_halt(K60_GCC_WRAP2_SE20_HALT)`，把 SE20 分支的 halt 轮询变成 set_rate 的返回值 | `clk-branch.h` `CBCR_CLK_OFF BIT(31)`、`HWCG_EN BIT(1)`；0500 自己已有 `k60_gcc_wait_halt()` |

## 2. SMMU planner 是从哪搬的

`bsd/dev/k60_usblog.c`（`patches/xnu/0300:288-523`）里那套 `smmu_plan_bank` / `smmu_plan` /
`smmu_configure` 是 `drivers/NativeUfs/SmmuTakeover.h` 的 1:1 C 移植，本补丁只做三件事：

1. 把 `vm_offset_t s` 换成 `struct k60_region k60.smmu`（用 `k60_read32`/`k60_write32`，
   后者自带 `dsb sy`；0300 的 `usb_rd` 用 `dmb oshld`，等价性在 S2 上机时由读回值验证）；
2. 把流号固定成 `K60_BT_SMMU_SID 0x483`，bank/group 上界 78/120 与 0300 一致；
3. 去掉 0300 的 dump 打印，换成两行 `[bluetooth] smmu …`：plan 一行（slot/bank/firmware-bank/action/dma），
   configure 后一行（SMR/S2CR/CBAR/CBA2R/SCTLR 读回值）。

算法本身一字未改：IDR0 BIT(30)（AArch64 stage-1）+ IDR2 BIT(12) 必须置位；地址宽度按
`(idr2 >> {0,4,8}) & 15` 查表；`pages = 1 << (((idr1 >> 28) & 7) + 1)`；`(pages + banks) * 4096 <= 0x100000`；
bank 从高往低取、拒绝 `bank < (idr1 >> 16) & 255`（stage-2 only）；扫描 SMR/S2CR 时把「已占用本 bank」
与「同流号冲突」区分开；`smmu_plan()` 对两类 "reserved context bank …" 错误重试 `bank_from_top = 1..7`；
`smmu_configure()` 先写 SCTLR=0、CBA2R=1、CBAR=0x10000 并逐个读回，再写 S2CR=bank（TYPE=TRANSLATE）、
SMR=0x80000000|stream，最后再读回一次。任何一步不符即返回字符串原因，`k60_smmu_bypass()` 打日志并
返回 `-EIO`，`k60_bt_power_on()` 随之失败——**不会带着未 bypass 的 DMA 去碰引擎**。

## 3. 上机时要看的行

`k60bt=1 k60bt_stage=2`（或直接去掉 `k60bt_stage`）后，控制台按顺序应出现：

```
[bluetooth] smmu plan sid 0x483 slot <n> bank <n> firmware-bank <n> action install|reuse|migrate dma 0x…
[bluetooth] smmu sid 0x483 slot <n> bank <n> SMR 0x80000483 S2CR 0x<n> CBAR 0x10000 CBA2R 0x1 SCTLR 0x0
[bluetooth] clocks vote cbcr core=… core2x=… m=… s=… se=…
[bluetooth] power=1 result=0 baud=… firmware=…
```

判据（仍然只读 `capture.json` 的 `verdict`/`panicMarker`，不用 `logstat.py`）：

| 现象 | 结论 |
|---|---|
| 两行 `smmu` 都在，`SCTLR 0x0`、`CBAR 0x10000`、`CBA2R 0x1`、`SMR 0x80000483` | F1 已修好，可以继续看 RCG |
| `smmu plan failed sid 0x483: …` | 该 bank 被别的流占用或几何不符——把整行贴回本文件，按错误串决定换 bank 还是换算法 |
| `smmu configure failed: …` | 写后读回不符，说明这台机器的 SMMU 不接受该 bypass 编码（0300 的注释已记过 TYPE=BYPASS 读回成 FAULT 的先例） |
| 完全没有 `smmu` 行就死机 | 死在 `k60_map(0x15000000)` 或更早，仍属 S1c 阶梯要回答的问题 |

## 4. 为什么现在就写，而不是等 S1c 上机结果

F1 的修法不依赖任何设备读数（0300 已在本板跑通、流号来自 FDT），F11/F3 的修法同样只有源码证据、
没有猜测成分；把它们先做进补丁，S1c 阶梯一旦证明「SE20 可达」，S2 就不必再等一轮构建。反过来，
如果 S1c 死在 s5/s6/s7（RCG 三档），这版 `k60_gcc_set_se_rate()` 正好是要复用的代码，改起来只需调一处。

## 4.1 已构建的镜像（2026-11-14）

| tag | boot.img sha256 | kernel | 用途 |
|---|---|---|---|
| `bt-s2-20261114b` | `c3ea7b6079bb94cc18dfb86e4ba3f80710d5607433f08974c84a5a29052c76be` | `138385e92767a6bb2faa5f9918b1b68c68062de29ad76817303a6f9765a8ab4a` | **不带任何 `k60bt` 参数**：用来证明 0508 对普通启动完全惰性（BT 线程不启动，新代码一行都不执行） |

其余哈希：payload `f4ce3db51caedecbca66bb477493e3be67e980d33e62284e9ba27fc996569a4d`、
payload kernel `ec2b35a828e0b9a64a885eaca679f1bf27f778cb310aafa60edaf3ae15421e5e`、
adt `56c6d450755ddf9e4e6b6aa389e7398f1db41bc249d8a4b8e90e189d67e7eacb`、
dtb `2d044eaa08b7e58c0510a33da795c960085e13d6943cd4c25e0e050e0bfa33cd`、
fd `cf4485712c2999c1fb7c1937a5b1f836dd3e9150073fb9b151b581d375195d0f`；
series 225 条 `7e5e3e4eb931829383948c0425c088888a9393813bc8051c84c69568458a3bdd`；
`repo head a415e1f`、`dirty_files 0`；`verify-boot-image: OK`。

**上机顺序（板子物理断电复位后）**：先 boot `bt-s2-20261114b`（无参数，一次普通启动，证明 0508 惰性）→
再按 S1c 五档阶梯（a1→a5，见 `S1-PROBE-SPEC.md` §4.1）。前者的判据只有一条：跑到用户态、控制台无 panic。

## 5. ⑦ 本地验证记录

| 项 | 结果 |
|---|---|
| 生成器 | `E:/k60-work/scratch/bt-s2/gen.py`（6 个 anchor，每个断言 `count == 1`） |
| 基线 | `/tmp/bt-s2` = `0500` + `0507` 应用后的 `bsd/` 全树 |
| 补丁 | 18,393 B / 391 行，sha256 `c4bf1ded55fe9bd03b7c10943ed41fff47464037c06c893b6dfd0984f02fd4f2` |
| `git apply --check` | `APPLY_CHECK_OK`（在干净树上重放 0500 + 0507 + 0508） |
| `clang -fsyntax-only` | `PASS bsd/dev/qbt_k60.c rc=0`（`BT_ROOT=/tmp/bt-s2-check`，`.CFLAGS` 取自 out3 的 `DEVELOPMENT_ARM64_PONG`） |
| 主机测试分支 | `clang -std=gnu11 -DK60_BT_HOST_TEST -fsyntax-only` rc=0，只有 2 条既有 warning（`armcpu_spi_mask` 恒真、`K60_QUP_HW_VER_REG` 与 0500 重复定义），都来自 0500/0507，非本次引入 |
| 内核构建 | `bt-s2-20261114b` 构建通过（kernel 54,177,792 B，series 225），`verify-boot-image: OK` |
| 打点数 | 36 个 `probe: ` 打点保持不动（0507 的阶梯不受影响） |

## 6. 风险与回滚

- 新增 `#include <mach/vm_param.h>`/`<mach/vm_statistics.h>`/`<vm/pmap.h>`/`<vm/vm_kern.h>` 与
  `extern ppnum_t pmap_find_phys(pmap_t, addr64_t);`——与 `0300` 的包含集合同源，不引入新依赖。
- `k60_gcc_wait_halt()` 在文件里定义得比 `k60_gcc_set_se_rate()` 晚，补丁在 RCG 宏旁边加了前置声明，
  否则 `-Wimplicit-function-declaration` 会报错（第一版就是这里红的）。
- 回滚 = 从 `series` 删掉 `0508` 一行；`0507` 与 `0500` 不受影响。
- 上机风险：`k60_smmu_bypass()` 会写 SMMU 全局寄存器。0300 每次启动都在写同一批寄存器（流 0），
  所以「写 SMMU 会挂死」的先例不存在；但 **BT 的流号 0x483 首次被写**，若挂死，症状会是
  `k60_map(0x15000000)` 之后、第一行 `smmu plan` 之前或之后立刻断线——因此 `k60_smmu_bypass()`
  在读 IDR 之前就打点（`k60_log` 里已有 plan 行前的 map 成功日志由 `k60_bt_power_on` 给出）。
