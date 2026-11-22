# iOS 27 cellular ①–⑦ 可执行判据

日期：2026-11-22。分支：feat/cellular-27。范围：本线唯一的硬件项 cellular
（X70 modem / DXE 载具 / QRTR）。本文不构建、不上机、不 flash，也不改共享树。

## 0. 结论

七步现在各有一条可执行命令、一个期望读数、一条负向命令和一个必须变红的负向读数。
判据实现是 `scripts/check-cellular-27-criteria.py`，回归是
`scripts/tests/test-cellular-27-criteria.py`。

- 有证据：① 同 SoC 先例与载具源码；② 官方页逐条要求；③ 27 镜像段表；
  ④ 组件目录与 27 include；⑤ 27 树 apply 实测；⑥ 宿主 loader/QRTR 测试；
  ⑦ 已有判官与夹具。
- 有推断：没有。本文不把“应该能”写成判据。
- 不知道：③ 的 GLINK/QRTR 服务表；⑤ 的 27 data-mount 接入；⑥ 的真实固件
  服务表；⑦ 的设备 W1/W2/F3。它们各自保持 PENDING，不能用宿主测试代替。

## 1. 怎么运行

```sh
python3 scripts/check-cellular-27-criteria.py --step same_model
python3 scripts/check-cellular-27-criteria.py --step same_model --mutate
python3 scripts/check-cellular-27-criteria.py --self-test
python3 scripts/tests/test-cellular-27-criteria.py
```

`--step` 正常退出 0（PASS）、1（FAIL）、2（PENDING）。`--mutate`
故意喂坏输入，退出 1 才表示判据真的会红；退出 0 表示坏输入没被抓到。
`--self-test` 对七步各跑一次正向和一次负向，全部符合才打印
`CELLULAR 27 CRITERIA SELF-TEST PASS 7/7`。

依赖：WSL 的 `gcc`、27 树 `/opt/k60/trees/ios27-out/feeds/xnu-3199e8bc`、
`E:/k60-work/firmware/modem`、`E:/k60-work/wt-pitfall/patches/xnu-12377`。
任一依赖缺失时对应步骤打印 PENDING，`--self-test` 不会通过；这是有意的，
不能把“环境没装”当成“判据通过”。

## 2. 七步判据

| 步 | 命令 | 期望读数 | 负向命令 | 负向必须读到 |
| --- | --- | --- | --- | --- |
| ① same_model | `--step same_model` | `K60_MODEM_SEGMENTS=30 K60_MODEM_BASE=0x8bc00000UL K60_MODEM_WINDOW=0x13200000UL anchors=19/19` | `--step same_model --mutate` | `missing K60_MODEM_BASE 0x8bc00000UL` |
| ② official | `--step official` | `anchors=12/12 baseband=22-31,25,29,56 userdata=60-85,82 concepts=68-70 qcom=7-9` | `--step official --mutate` | `missing EFS 写入仍保存在内存中，重启后重新加载原厂数据` |
| ③ decompile | `--step decompile` | `TESTS OK 30 segments, 0x8bc00000..0x9ee00000 (320864256 bytes), base 0x8bc00000, table+p patch agree` | `--step decompile --mutate` | `e_phnum is 31, expected 32` |
| ④ wide | `--step wide` | `QcomBaseband=present verified_devices=0 board_include=ArmDTPlatform,ArmCpu,XnuPrelink QcomBaseband=absent` | `--step wide --mutate` | `verified_devices is not empty` |
| ⑤ plan | `--step plan` | `apply 0626=0 0627=0 0628=0 0630=0 0629=1 anchor_grep=1` | `--step plan --mutate` | `corrupted patch rejected` |
| ⑥ deep | `--step deep` | `loader=TESTS OK 7 TESTS OK 13 groups (lookup, hello, new_server, data, servloc, dms, verdict, services, malformed, node, discovery, qmi bounds, dms errors)` | `--step deep --mutate` | `QRTR version mismatch` |
| ⑦ verify | `--step verify` | `W1=20 EFS=12 BUNDLE=9 FIXTURES=9 JUDGE=self-test STRICT=PASS` | `--step verify --mutate` | `VERDICT: FAILED` |

每条判据的 `PRECEDENT`、`CONCLUSION` 和 `UNKNOWN` 也在
`--step` 输出里。片段 `docs/research/eight-step/cellular-27.toml`
的七步各有 `criterion_command`、`criterion_expected`、
`criterion_negative_command`、`criterion_negative_expected`、
`precedent`、`conclusion` 和 `unknown` 字段。

## 3. 先例与“无先例”

| 机制 | 先例或依据 | 裁定 |
| --- | --- | --- |
| PAS4 顺序：INIT_IMAGE → MEM_SETUP → AUTH_AND_RESET | `docs/research/cellular/19-MODEM-BRINGUP-FLIGHT.md:15-19`（pong，Nothing Phone 2，SM8475/X65）；`E:/k60-work/references/phk110-port/drivers/modem/hakios.mpss.c:1047-1051`（PAS_MPSS_DEFAULT=4，0x8b800000） | 有先例，可用于①和⑥的机制 |
| 载具逐段拷贝与 bss 清零 | `docs/research/audio/ADSP-PAS1.md:30-34`（PAS 序列）；`drivers/PongPower/K60AdspImage.c:9-13`、`drivers/PongCellular/K60ModemImage.c:67-91`（同一形状的宿主实现） | 有源码证据，不是设备结论 |
| 官方页的 modem 启动、EFS/NV、Data 卷要求 | `E:/hackios/UniXNU/docs/zh/porting/baseband.md:22-31`、`:25`、`:56`；`E:/hackios/UniXNU/docs/zh/guide/userdata.md:60-85`；`E:/hackios/UniXNU/docs/zh/concepts/userdata.md:68-70`；`E:/hackios/UniXNU/docs/zh/drivers/qcom-baseband.md:7-9` | 规范来源；缺口是 27 proprietary-files 还没有 modem/EFS 条目 |
| 组件目录里的 QcomBaseband | `E:/hackios/UniXNU/components.toml:563-581`，`:575` 的 `verified_devices = []`；`E:/hackios/k60-gates/board.toml:362-364` 的 include 没有它 | 只能借传输层语义；无本板/同 SoC 可用先例 |
| 27 data-mount 后再插 PAS 探针 | `docs/research/cellular/20-IOS27-PORT-PLAN.md:95-99` 与 `:654-661` 说锚点未落；27 树 `git grep native_owner_data_stage` 为 0 行 | **无先例**；不把 0629 接进代码或判据 |
| GLINK/QRTR 服务表 | 27 树只有镜像段表，没有服务号/通道名/初始化顺序的反汇编 | **不知道**；③ 保持 `done=false` |
| 日志通路（用于将来 ⑦ 的设备读数） | `E:/hackios/k60-gates/docs/research/ios27/PRECEDENT-REQUIRED.md:16-17`；`E:/hackios/UniXNU-sheng/package/BootLog.c:1-8`（userdata 末尾 32 MiB） | 有先例；本文没有把日志机制接进 cellular 判据 |

## 4. 负向 dry-run 的真实读数

2026-11-22 在本工作树执行 `python3 scripts/check-cellular-27-criteria.py --self-test`，
得到：

```
same_model  normal PASS  anchors=19/19
same_model  mutated FAIL  K60_MODEM_BASE=0x00000000UL
official    normal PASS  anchors=12/12
official    mutated FAIL  EFS 写入仍保存在内存中 sentence removed
decompile   normal PASS  TESTS OK 30 segments
decompile   mutated FAIL  e_phnum is 31, expected 32
wide        normal PASS  verified_devices=0
wide        mutated FAIL  verified_devices=["pong"]
plan        normal PASS  apply 0626=0 0627=0 0628=0 0630=0 0629=1 anchor_grep=1
plan        mutated FAIL  mutated 0626 apply rc=128
deep        normal PASS  loader=TESTS OK 7, qrtr=TESTS OK 13 groups
deep        mutated FAIL  qrtr_mutated rc=134
verify      normal PASS  W1=20 EFS=12 BUNDLE=9 FIXTURES=9 JUDGE=self-test STRICT=PASS
verify      mutated FAIL  nohead strict rc=1 verdict=FAILED
CELLULAR 27 CRITERIA SELF-TEST PASS 7/7
```

`plan` 的 rc=128 是 git apply 对损坏 patch 的返回值；`deep` 的 rc=134
是 QRTR 测试在版本被改坏后 abort。两者都证明输入真的变红，不证明设备行为。

## 5. 这些判据不证明什么

- 不证明 modem 已在 K60 上启动；没有一次 27 console，W1/W2/F3 仍是 PENDING。
- 不证明 GLINK/QRTR 服务表已懂；③ 的 `done=false` 保持不变。
- 不证明 QcomBaseband 能在本板复用；④ 的 `verified_devices` 为空。
- 不证明 27 data-mount 已有先例；⑤ 的 0629 仍不 apply。
- `--self-test 7/7` 只证明判据实现和负向输入，不证明基带可用。

## 6. 文件

- `scripts/check-cellular-27-criteria.py`：七步判据与负向 dry-run。
- `scripts/tests/test-cellular-27-criteria.py`：宿主回归，成功行
  `K60 CELLULAR 27 CRITERIA PASS 7/7`。
- `docs/research/eight-step/cellular-27.toml`：七步的判据字段；它仍是
  candidate fragment，门禁只读 `docs/research/EIGHT-STEPS.toml`，合并前不生效。
