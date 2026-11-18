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
args = count | t0<<4 | t1<<6 | t2<<8；成功 = x0==0；x1..x3 是结果寄存器，不是 payload 判决），宏名改成 `K60M_SCM_*` 以避免同一
内核里两套同名符号。调用序列沿用 `docs/research/audio/ADSP-PAS1.md` 的裁决：

1. `PAS_AUTH_AND_RESET`：args(1,0,0,0)，参数 = peripheral；
2. 每个有字节的段一条 `PAS_INIT_IMAGE`：args(2, VAL, RW, 0)，参数 = peripheral, phys；
3. `PAS_MEM_SETUP`：args(3,0,0,0)，参数 = peripheral, base, span。

SMC 本体是 x0..x7 寄存器绑定 + `smc #0` 内联汇编（`K60ModemPas.c`），失败行打印
`K60MODEM scm cmd=%#x rc=%d x0=%#llx x1=%#llx`。

### 2.1 SCM_INTERRUPTED 的续调修正（2026-11-18）

k16 C-M2 的 `E:/k60-work/evidence/usblog-20261118-204241/console.log:479-480` 是
`scm cmd=0x1 rc=-1 x0=0x1 x1=0x82` 后接 `init_image failed`。旧封装只发一次 SMC，把非零 x0 一律分类为 `K60ModemPasDenied=-1`；
这个 rc 不是 Linux errno。**x0=1 是 QCOM_SCM_INTERRUPTED，表示同一次调用尚未完成，不是 TZ 已拒绝 metadata。** 此时 x1=0x82 还等于 INIT_IMAGE 的输入 arginfo，不能当作最终 PAS 错误。

主依据是 Android common 的 `drivers/firmware/qcom_scm-smc.c::__scm_smc_do_quirk()`（固定标签 [android13-5.15-2024-03_r9](https://android.googlesource.com/kernel/common/+/refs/tags/android13-5.15-2024-03_r9/drivers/firmware/qcom_scm-smc.c)）：x0=1 时继续，重送原 x1..x5/x7，并保留返回的 x6 上下文。同 SoC 参考 `E:/k60-work/references/phk110-port/drivers/modem/hakios.mpss.c:1298-1327` 也是相同形状（只参考 ABI 事实，未复制无授权代码）。

提交 `92657c8f` 修正 PAS4 封装：首调 fn、续调 x0=1、每轮重建原参数、传回 x6，最多 100 次；耗尽返回独立的 `K60ModemPasInterrupted=-3`。它不重写 metadata、不改 PA、不修 IPA 的独立单次 SMC 封装。新增 `drivers/PongCellular/tests/run-modem-scm-continuation.sh` 编译实际 `K60ModemPas.c`，模拟 monitor 覆盖一次/多次中断、输入寄存器被改写、64 位 x6、最终 x0 非零拒绝、x1 非零但 x0=0 视为成功、transport -12、100 次耗尽和第 100 次成功。k17 内核 `9b21321f...` 已离线编译，未打包/未上机。

2026-11-18 追加修正：`k60_modem_scm_ok()` 改为只判 `x0==0`。依据 Linux v6.6 `drivers/firmware/qcom_scm-smc.c::__scm_smc_do_quirk()` / `__scm_smc_call()`：`res.a0` 是返回码，`a1..a3` 只是结果寄存器，`__scm_smc_call()` 返回 `smc_res.a0`。因此 `x1=0x82` 不是 payload 判决，不能让 `x0=0` 的完成态被误判为拒绝。宿主 `test-modem-scm-continuation.c` 的 `x1=0x82` 用例改为期望成功，另用 `x0=-22` 覆盖最终拒绝；`test-k60-modem-pas.c` 断言 `(0,1)=1`。`0621` 新文件 hunk 同步更新为 113 行。以上仍是离线证据，未上机。

### 2.2 metadata 的 CRLF 污染（2026-11-18 审计，未上机）

`K60ModemMetadata.h` 原来从 adb pull 的 `modem.mdt`（5,909 B，含 25 个 CRLF）生成；干净二进制 `modem.mdt.bin` 是 5,884 B。
取 `modem.mdt[:5884]` 后，前 1,076 B 的 ELF header 正确，但 4,808 B hash segment 从偏移 1,455 起被 25 个 `0x0d` 插入并截掉末尾 25 B：与 `modem.mdt.bin[:5884]` 有 **3,362 B 不同**。旧 CRC32 `0x5ce97b8d` / SHA256 `09180d7c...` 只是对污染数据自洽，所以旧门禁没发现。
已用干净 binary 重新生成：5,884 B，CRC32 `0xac600b5d`，SHA256 `78d5f2f45aefeab7d2920bc5753009ade0371aa7d9be5eb0f2d21a72704c1fb8`。这不会解释 k16 的 `x0=1`（续调发生在 auth 之前）；它会在 INIT_IMAGE 真正完成后让 hash 校验失败。新 header 尚未编入 UEFI FD、尚未打包/上机，所以 k17 目前不是可飞行候选。

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
