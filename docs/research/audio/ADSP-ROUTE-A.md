# ADSP Route A：QMP load_state + TCS4 双轨投票

**Status:** implementation checkpoint, 2026-11-17. 用户明确放宽 HR-01 并选择路线 A。
**Scope:** `drivers/PongPower/K60AdspRouteA.c/.h`、`K60AdspBoard.c` 的 `resources()` 回调，
以及 `scripts/tests/test-k60-route-a.c`。生产 `resources_cb` 不再返回 -63；失败仍返回
`K60BoardUnsupported(-63)`，成功才置 `resources=1`。**未上机。**

## 1. 为什么是 TCS4

K60 是 SM8475，与 Zizhan、Pong 同 SoC。Zizhan 的 ADSP 在真机上工作，
`PongAdsp.cpp:503-521` 的顺序是：QMP `load_state on` → 读 cmd-db 的 `lcx.lvl`/`lmx.lvl`
→ 取最高 level → 写 RPMh TCS4；`PongRpmh.cpp:27-48` 的 TCS4 基址是
`0xd00 + 4 * 0x2a0 = 0x1780`。K60 触摸的 P-86 记录同板 TCS4 投票 48/49 次成功
（`caps=0x800c8104 count=8 ncpt=16 ver=0x20700 tcs4_idle=1`），所以 TCS4 在本板不是猜测。

K60 DT `mondrian.dts:5119-5129` 的 `tcs-config=<02 03 00 02 01 02 03 00 04 01>`
按 mainline 解码 ACTIVE=0-2、SLEEP=3-4，与 Zizhan 的同一串配置一致；但 Zizhan 的
`docs/plan/2026-11-07-lockscreen-suspend-design.md:66-76` 明确把该解码标为未解决的
ownership 冲突，而它的工作代码仍用 TCS4。这里跟工作代码，不重新推导槽号。

## 2. 实现（K60AdspRouteA.c）

所有访问都经调用方注入的 `K60RouteAIo`（`map/unmap/kick/tick`）；host 测试逐次计数
map、read、write。物理常量：

| 区域 | 物理地址 | 长度 | flags |
|---|---:|---:|---:|
| AOSS QMP 描述符 | `0x0c300000` | `0x1000` | `0x7` |
| IPCC doorbell | `0x0ed18000` | `0x1000` | `0x7` |
| cmd-db | `0x80860000` | `0x20000` | `0x7` |
| RSC DRV-2 | `0x17a20000` | `0x10000` | `0x7` |

1. **QMP 打开**（`qmp_open`）：校验描述符 magic `0x4d41494c`（`MAIL`）、version `1`，
   读 `MBOX_OFFSET`/`MBOX_SIZE` 并校验 `box` 为 4 的倍数、`box >= 0x3c`、
   `bytes <= 0x400`、消息框容得下 104 字节；按 Zizhan `QcomQmp.c` 的
   MCORE_LINK/MCORE_LINK_ACK/MCORE_CH/UCORE_CH/MCORE_CH_ACK 握手。
2. **发送 load_state**：在邮箱 +4 处写 100 字节消息
   `{class: image, res: load_state, name: adsp, val: on}`，长度字写 100，写后触发
   IPCC offset `0x0c`（AOP client 0 / GLINK_QMP signal 0），等待 AOP 把长度字清零。
3. **读取 cmd-db**：用 `k60_cmd_db_find()` 找 `lcx.lvl`、`lmx.lvl`；取
   `level_count - 1` 作为最高档。Zizhan 的 `qcom_rpmh_level_index(...,0xffffffff)` 在
   K60 是 `NoLevel`（P-191），所以直接用表的最后一个索引，不继承这个差异。
4. **RSC 检查**：只接受 v2（`(drv>>16)&0xff == 2`），`max_tcs >= 8`、`ncpt >= 1`，
   且 TCS4 status word `0x1780+0x18` 非零；否则 `TCS4 unavailable`，绝不写未声明的槽。
   若 TCS3 status 为 0，则按 ncpt 扫描 TCS3 command enable/address，避免覆盖同地址的旧命令。
5. **写两轨**：每轨一次 RPMh active-only 命令：MSGID `0x10108`、address 来自 cmd-db、
   data=最高 level index；清 control bit 24/16、清 cmd_enable、清 IRQ，写
   wait_for_cmpl=1、cmd_enable=1、control `1<<16`，再写 `(1<<16)|(1<<24)`，轮询
   command status `0x10100` 和 TCS idle；完成后清 cmd_enable/IRQ/control bit24。

失败路径：任何一步失败都只输出 `K60ROUTEA: ...` 并释放已建立映射，返回 -1；调用方
`K60AdspBoard.c` 打印 `K60ADSP: Route A acquisition failed; no PAS/SMEM mutation`，
返回 -63，不置 `resources`，不进入 SMEM/SMEM alloc/INIT_IMAGE/MEM_SETUP/COPY/BSS/AUTH。
成功路径打印两条 rail 地址/索引，置 `resources=1`，随后 owner 阶段照常执行。

## 3. 与 HR-01 的关系

`docs/ops/HARD-RULES.md` 的 2026-11-17 用户裁决段记录本次授权：仅允许
`K60AdspRouteA.c` 和 `K60AdspBoard.c` 的 `resources()` 使用 AOSS QMP、cmd-db、
DRV-2（0x17a20000）和 TCS4 的两条 lcx/lmx 命令；`0x17a00000` 仍绝对禁止；不碰
PAS/SMC/SMEM/lease；失败即 -63。其他任何路径仍按原 HR-01 禁止。

## 4. 已执行的验证

- 主机单测：`cc -std=c11 -O1 -Wall -Wextra -Werror -I drivers/PongPower
  scripts/tests/test-k60-route-a.c drivers/PongPower/K60AdspRouteA.c
  drivers/PongPower/K60PmicRail.c` → `TESTS OK route-a: 8 scenarios`。
  覆盖成功、QMP 打开失败、缺少 lmx、TCS3 同地址冲突、TCS4 不可用、RSC v3、caps 不足、
  TCS3 槽位容量。
- 板级单测：`TESTS OK board-ownership: 9 scenarios`，新增 Route A 成功场景验证
  `ResourcesHeld=1` 和 release 清零。
- owner-claim：`TESTS OK owner-claim: 18 scenarios` 和
  `TESTS OK real-board refusal: map_smem=0 alloc=0 init=0 mem=0 load=0 auth=0 publish=0`。
- 电池归档构建：`bash scripts/build-battery-archive.sh ...` exit 0，
  `libK60PhysicalBattery.a` 111792 B，
  SHA256 `75dd1e72cb7d422aa125dcb3ff39ca51b0f8586127d2e40ed10f2e3366bedffa`，
  构建报告确认 `K60AdspRouteA.c` 由真实 Darwin clang 编译。
- 内核构建：`kernel.macho` 129,052,672 B，SHA256
  `58d27efa5339a0503058945ba4ef42a5501d0812083da9ec8544218f1438f8d8`，字符串包含
  `K60ROUTEA`；ADSP carrier 23,506,184 B / 26 records / SHA256 `6633...` 已链接。
- payload：201,326,592 B，SHA256 `0562f343c3aac96eff4cf29cbbe678f32555be8ed1b441227f7762b80315fde0`。
- boot image：201,887,744 B，SHA256 `7d5918c506020d7e1fed129851baf706bd17bd5b2d0a4d978a44a33953db8f20`，
  `check-image-args.py` 通过（30 arguments / 598 bytes）。这些构建是离线产物，不是硬件证据。

## 5. 未覆盖 / 未证明

- 未上机；没有任何 QMP/TCS4 在 K60 XNU 下的硬件成功证据。
- QMP 消息超时是固定轮询循环；AOP 负载/时序未测。
- 只实现 Zizhan 的“最高档”选择，不解释 cmd-db level 的物理含义，也不读回实际轨电压。
- 失败后不回滚已写的第一条轨；若第二条轨失败，第一条轨的投票保留到重启。这是本实现的
  已知边界，不是已证明安全的恢复策略。
- 不处理 SMP2P、GLINK、SMMU lease、PAS AUTH 之后的 DSP 状态机；这些仍由既有 owner 阶段负责。
- TCS4 槽号来自 Zizhan 工作代码与 K60 P-86 触摸记录；mainline tcs-config 解码冲突未解决。
- 生产 `resources()` 成功现在会使 `live()` 返回真；在真实硬件上首次成功前，不把该路径当已验证。
