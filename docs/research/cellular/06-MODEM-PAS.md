# 06 — modem PAS 握手与 boot-arg 门控（K60ModemPas / K60ModemBoot，L2）

日期：2026-11-14。分支 `feat/cellular`（worktree `E:/hackios/k60-cellular`）。
上游任务书：Lead 2026-11-14 m02278——「选 A：进 L2，加 boot-arg 门控的调用点先打日志」。

**一句话结论**：L2 交付的是一条**默认完全静默**的 modem PAS 路径：`pong_modem=1` 时，内核在
Data 卷挂载后读 306 MiB carveout 头页的 16 B 签名判断镜像是否已在位，在位才按
`AUTH_AND_RESET → 逐段 INIT_IMAGE → MEM_SETUP` 顺序发 SMC（peripheral = 4），每步一行
`K60MODEM` 判决；任何一步失败都会打印步骤名与返回值。默认（不传 boot-arg）时探针第一行
就返回，不映射、不打印、不发 SMC。

---

## 1. peripheral id = 4 的取证

活 Android DT 的 `remoteproc-mss@04080000` **没有** `qcom,pas-id` 属性（实测：
`od -An -tx4 /proc/device-tree/soc/remoteproc-mss@04080000/qcom,pas-id` 报 `No such file or directory`，
属性清单见 `docs/research/cellular/04-DT-NODES.md`）。所以 4 不是 DT 字面值，而是两个独立来源一致给出的平台默认：

| 来源 | 位置 | 原文 |
|---|---|---|
| Pong ADT 生成器 | `E:/k60-work/references/UniXNU-pong-upstream/scripts/make-pong-adt-ipados18.py:320` | `('pong,pas-id', struct.pack('<I', 4))`（同节点 `:317` compatible `qcom,cape-modem-pas`、`:319` model `Qualcomm Snapdragon X65`） |
| 参考移植 | `E:/k60-work/references/phk110-port/drivers/modem/hakios.mpss.c:1050` | `#define PAS_MPSS_DEFAULT 4 /* dt: qcom,pas-id of qcom,mss */` |

同文件 `hakios.mpss.c:1794` 记 `PAS_IPA_DEFAULT 15`，与活 DT 里 `qcom,ipa@3e00000` 的
`pas-ids = <0x0f>`（`dts/mondrian.dts:295` 起）互为印证——说明这套编号在该 SoC 上是自洽的，
modem=4 与 IPA=15 并存。ADSP 是 1（`drivers/PongPower/K60AdspPas.h` 的 `K60_PAS_ADSP 1u`）。

实现落在 `drivers/PongCellular/K60ModemPas.h` 的 `#define K60_PAS_MODEM 4u`，并由宿主测试
`scripts/tests/test-k60-modem-pas.c` 的 `check_constants` 锁死。

## 2. SMC 编码器（照抄 ADSP 形状，只换常量名）

编码器与 `drivers/PongPower/K60AdspPas.h` 完全同构（SMC64 bit30 | SiP owner 2<<24 | svc<<8 | cmd；
args = count | t0<<4 | t1<<6 | t2<<8；成功 = x0==0 && x1==0），宏名改成 `K60M_SCM_*` 以避免同一
内核里两套同名符号。调用序列沿用 `docs/research/audio/ADSP-PAS1.md` 的裁决：

1. `PAS_AUTH_AND_RESET`：args(1,0,0,0)，参数 = peripheral；
2. 每个有字节的段一条 `PAS_INIT_IMAGE`：args(2, VAL, RW, 0)，参数 = peripheral, phys；
3. `PAS_MEM_SETUP`：args(3,0,0,0)，参数 = peripheral, base, span。

SMC 本体是 x0..x7 寄存器绑定 + `smc #0` 内联汇编（`K60ModemPas.c`），失败行打印
`K60MODEM scm cmd=%#x rc=%d x0=%#llx x1=%#llx`。

## 3. 载体问题的 L2 处置：签名自检，而不是搬运

`docs/research/audio/ADSP-CARRIER.md` 已裁决：109 MB 量级的固件字节无法嵌内核（23.5 MB 的 ADSP
都不行），`vmd0/md0` 是死路（`esr 0x96000010`），内核自己读块设备要给 NativeUfs 加接口 = 独立工程。
modem 完全同构且更大：`copied = 109,060,761` B（`docs/research/cellular/05-MODEM-IMAGE.md` §3）。

所以 L2 **不做 copy 载体**，改为「载体在位自检」：`modem.b01` 落在 carveout 首地址 `0x8bc00000`，
它前 16 B 是固定模式（从本地 `E:/k60-work/firmware/modem/modem.b01.bin` 实测）：

```
0e c0 00 58   00 c0 00 58   00 c0 00 58   00 c0 00 58
```

`k60_modem_carrier_ok()`（`K60ModemPas.h`）逐字节比对该模式；探针用 `ml_io_map_unmappable`
（同 `K60AdspBoot.c` 的选择：`ml_io_map()` 的 io_submap 只有 8 MiB，306 MiB 会 panic）映射
**一个 4 KiB 头页**（`K60_MODEM_PROBE_PAGE 0x1000`），签名不匹配就打印
`K60MODEM carrier absent: no modem image staged at 0x8bc00000` +
`K60MODEM pas skipped, nothing was handed to the secure monitor` 并返回 0 —— **绝不盲发 SMC**。
将来固件按固定物理地址把镜像放进 carveout 时（payload FAT 方案是 L3），这个自检零成本命中。

顺带的安全含义：设备从 Android 热重启过来时 modem 已经在运行（实测
`/sys/class/remoteproc/4080000.remoteproc-mss/state` = `running`），盲发 `AUTH_AND_RESET` 会
重置一台正在工作的调制解调器。签名自检让这种情况在第一时间被打印出来而不是被触发。

## 4. 调用点与门控

- 门控：`k60_modem_probe_from_handoff()` 第一行 `PE_parse_boot_argn("pong_modem", &enabled, sizeof(enabled))`，
  不存在或为 0 直接 `return 0`（不打印）。同款门控见 `K60AdspBoot.c` 的 `pong_adsp`。
- 调用点：`patches/xnu/0621-k60-modem-pas.patch` 在 `bsd/kern/kern_exec.c` 的 Data 挂载成功块
  （`(void)k60_adsp_probe_from_handoff();` 之后、`native_owner_data_stage = 3;` 之前）插入
  `{ extern int k60_modem_probe_from_handoff(void); (void)k60_modem_probe_from_handoff(); }`。
  锚行 `native_owner_data_stage = 3;` 在该文件中唯一（grep -c = 1）。
- 注册：`patches/xnu/series` 在 `0620-k60-modem-image.patch` 后追加 `0621-k60-modem-pas.patch`；
  `scripts/append-conffiles.py` ENTRIES 在 `bsd/dev/pong_modem_image.c` 后加
  `bsd/dev/pong_modem_pas.c` 与 `bsd/dev/pong_modem_boot.c`（P-171：conf/files 由构建驱动追加，不能在补丁期锚定）。

## 5. 日志契约（Boot 判据）

`pong_modem=1` 启动后，日志按序出现，且**所有行都以 `K60MODEM` 开头**：

```
K60MODEM probe begin
K60MODEM plan rows=30 copied=109060761 zeroed=211012967 base=0x8bc00000 window=0x13200000
K60MODEM copy skipped: image already staged at 0x8bc00000
K60MODEM auth_reset ok
K60MODEM init_image ok segments=27
K60MODEM mem_setup ok base=0x8bc00000 span=0x13200000
```

失败形态（每一步都有对应的失败行，含步骤名与 rc）：`plan failed rc=%d` / `copy failed rc=%d` /
`auth_reset failed rc=%d` / `init_image failed seg=%u addr=%#x bytes=%u rc=%d` / `mem_setup failed rc=%d`。
`init_image` 只对有字节的段发（30 段中 27 个有文件，b14/b21/b30 是纯 bss），成功行打 `segments=27`。

**本轮最重要的预期结果**：由于 L2 没有载体，真实上机最可能看到的是

```
K60MODEM probe begin
K60MODEM plan rows=30 copied=109060761 zeroed=211012967 base=0x8bc00000 window=0x13200000
K60MODEM carrier absent: no modem image staged at 0x8bc00000
K60MODEM pas skipped, nothing was handed to the secure monitor
```

这不是失败：它证明 (a) 门控生效、(b) 段表在内核里活着、(c) 探针宁可不发 SMC 也不猜。

## 6. 验证记录（host 层）

| 验证 | 命令 | 结果 |
|---|---|---|
| PAS 编码器/常量/签名 | `gcc -O1 -Wall -Wextra -Werror -Idrivers/PongCellular -o /mnt/e/k60-work/artifacts/tests/t-modem-pas scripts/tests/test-k60-modem-pas.c` 后运行 | `TESTS OK 5 groups (fn, args, ok, carrier, constants)`，exit 0 |
| 加载器行为（L1 回归） | 同目录 `t-modem`（`test-k60-modem-loader.c` + `K60ModemImage.c`） | `plan segments=30 copied=109060761 zeroed=211012967` + `TESTS OK 7`，exit 0 |
| 段表/补丁一致性（含 0621 三文件 + 调用点锚） | `python3 scripts/tests/test-k60-modem-image.py /mnt/e/k60-work/firmware/modem` | `TESTS OK 30 segments, 0x8bc00000..0x9ee00000 (320864256 bytes), base 0x8bc00000, table+p patch agree`，exit 0 |
| 0621 可 apply（对 0614 之后的 kern_exec.c） | `patch -p1 --dry-run --batch --fuzz=0` 于备份副本 `/root/kern_exec.backup.c`（sha256 `c4d91d027780f5aa…`） | `DRYRUN OK`，插入点 7838/7840 行 |
| 全补丁解析 | `python3 scripts/check-patch-apply.py --all` | `✅ 307 个改动的补丁都能被 git apply 解析（P-162）`，exit 0 |

## 7. 边界与留给 L3 的东西

- 本轮**没有**把镜像字节送进 carveout 的载体（payload FAT `EFI/UniXNU/ADSP/` 同款方案待做），
  因此真实 SMC 序列在 L2 的上机里预期不会执行到 `auth_reset ok`。
- 本轮**没有**碰 IPA（PAS 15）、没有读/写 `modemst1/modemst2/fsg/fsc`、没有 fastboot flash。
- 08 段（上机）由 Lead 执行；判据见 §5。
