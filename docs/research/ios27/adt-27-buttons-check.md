# 27 侧 ADT 字节核对：/buttons 四字段与 /arm-io/pong-buttons 六属性

**结论（一行）**：用仓内 `scripts/unixnu/devicetree.py` 的 `generate()` 生成的 27 ADT
（16,648 B、26 个节点）里，`/device-tree/buttons` 的四个字段与
`/device-tree/arm-io/pong-buttons` 的六个属性逐字存在、逐值相符；
同一份 ADT 里 `/device-tree/arm-io/pong-touch` 的十个属性也全部相符。
「board.toml 写了」与「ADT 字节里有」之间从此有可复跑的证据链。

## 这条证据补的是哪个缝

2026-11-12 的两笔 pick 就是从这个缝里掉下去的：

| 提交 | 时间 | 动作 |
| --- | --- | --- |
| `97b84eb7` | 2026-11-12 21:33 | "pick 88 commits" —— 把 `[adt.arm-io.pong-buttons]` 加进 board.toml |
| `3b3ff9ce` | 2026-11-12 21:35 | "never let a pick overwrite the board contract" —— 把它删掉 |

16.6.1 仓今天的 `board.toml` 只剩 `[adt.buttons.*]`（:268 / :272 / :275），
`docs/research/EIGHT-STEPS.toml:406` 记着当时这份节点「只活在 /opt 装配输入里」。
27 仓在 `board.toml:284-299` 补回了节点，并在 :285-287 记着一次干净重建打印过
`Pong keys: DT node /arm-io/pong-buttons not found`——驱动是按精确名断言这六个属性的
（`bsd/dev/pong_buttons.c:45-50`）。

## 复跑命令

`scripts/gen-27-adt-buttons.py` 不写死任何路径，四个输入全部当参数传；
`--work` 指到临时目录时脚本跑完自删，指到别处则保留 dtb / 反编译 dts / ADT 供比对。

```sh
python3 scripts/gen-27-adt-buttons.py \
  --board      <构建输入镜像>/board.toml \
  --dts        <构建输入镜像>/dts/mondrian.dts \
  --os-profile <UniXNU>/profiles/os/ios-27.0.1-24A446/profile.toml \
  --framework  <UniXNU> \
  --include-dir <sm8475-common feed>/dts \
  --work       <证据目录>
```

输入取**构建输入镜像**（`/opt/k60/trees/gates-device/`，与 `k60-gates` 检出同一份），不取任意分支的
设备仓检出：2026-11-21 实测某条 stale 分支上同一文件的 `dts` 与镜像不一致（见文末「两棵树」一节）。
`--include-dir` **必须显式给**：`mondrian.dts` 的 `/include/ "sm8475.dtsi"` 在 soc feed 里而不在设备仓，
写死相对路径换台机器就会 `Couldn't open "sm8475.dtsi"`。本次用的正是
`/opt/k60/trees/ios27-out/feeds/UniXNU-sm8475-common-6ebb3d7f/dts`。

脚本内部四步，每一步都能单独看见：

1. `dtc -I dts -O dtb`：硬件 dts 编成 `hardware.dtb`（4,307 B）；
2. `dtc -I dtb -O dts` 反编译回 `hardware.decompiled.dts`（4,597 B、225 行）——
   证明这份输入是可往返的合法 FDT；
3. `devicetree.py:311 generate()` 生成 `kernel.macho.adt`（16,648 B、26 节点）；
4. 按 ADT 节点表格式（`devicetree.py:13-22` 的编码器、`scripts/test-devicetree-handoff.py:30-56`
   的同款解码）遍历节点，逐属性比对期望值。

## 实际输出（2026-11-21，WSL，PASS）

```
hardware.dtb 4,307 B → kernel.macho.adt 16,648 B, 26 ADT node(s)
dtc round trip: hardware.dtb → hardware.decompiled.dts 4,597 B, 225 lines

node                                property          expected             in the ADT           verdict
/device-tree/buttons                compatible        buttons              buttons              ok
/device-tree/buttons                device_type       buttons              buttons              ok
/device-tree/buttons                button-names      hold/voldown/volup   hold/voldown/volup   ok
/device-tree/buttons                home-button-type  0x2                  0x2                  ok
/device-tree/arm-io/pong-buttons    core-base         0xc400000            0xc400000            ok
/device-tree/arm-io/pong-buttons    cnfg-base         0xc42d000            0xc42d000            ok
/device-tree/arm-io/pong-buttons    observer-base     0xc440000            0xc440000            ok
/device-tree/arm-io/pong-buttons    ee                0x0                  0x0                  ok
/device-tree/arm-io/pong-buttons    pon-ppid          0x13                 0x13                 ok
/device-tree/arm-io/pong-buttons    volume-up-ppid    0x18d                0x18d                ok
/device-tree/arm-io/pong-touch      compatible        xiaomi,m11a-spi      xiaomi,m11a-spi      ok
/device-tree/arm-io/pong-touch      spi-base          0x990000             0x990000             ok
/device-tree/arm-io/pong-touch      tlmm-base         0xf000000            0xf000000            ok
/device-tree/arm-io/pong-touch      gcc-base          0x100000             0x100000             ok
/device-tree/arm-io/pong-touch      gpio-offset       0x100000             0x100000             ok
/device-tree/arm-io/pong-touch      avdd-gpio         0x47 (71)            0x47 (71)            ok
/device-tree/arm-io/pong-touch      max-x             0x3840 (14400)       0x3840 (14400)       ok
/device-tree/arm-io/pong-touch      max-y             0x7d00 (32000)       0x7d00 (32000)       ok
/device-tree/arm-io/pong-touch      pins              <16 17 18 19 21 20>  <16 17 18 19 21 20>  ok
/device-tree/arm-io/pong-touch      bitbang-pins      <16 17 18 19>        <16 17 18 19>        ok

verdict: PASS (exit 0)
```

## 反例（脚本不是空跑）

把 board.toml 里 `home-button-type = 2` 与 `pon-ppid = "0x013"` 两行删掉再跑，
同一个脚本给出：

```
/device-tree/buttons              home-button-type  0x2   absent  FAIL
/device-tree/arm-io/pong-buttons  pon-ppid          0x13  absent  FAIL

verdict: FAIL (exit 1) — /device-tree/buttons:home-button-type: missing;
                         /device-tree/arm-io/pong-buttons:pon-ppid: missing
```

即缺字段会红、且指名到节点与属性；2026-11-12 那种「pick 顺手删掉节点」的形态，
这条命令会当场拦住。

## 两棵树：一次「我这棵树编不过」的更正

第一版这一节写成「27 设备仓的 `dts/mondrian.dts` 今天编不过」，Lead 在 `diag/menu-hold-20261121`
上复现不了，于是逐项对齐——结论是**两棵树、两个阶段**，我那句判断把范围说过头了：

| 项 | 我读的那棵 | Lead 验的那棵 |
| --- | --- | --- |
| 检出 | `E:/hackios/xnekom-ios27` | `E:/hackios/k60-gates` |
| 分支 / HEAD | `feat/xnu27-data-gate` @ `7fd04d89` | `diag/menu-hold-20261121` @ `988f7ee8`（Lead 记的是 `c1a39f08`） |
| `dts/mondrian.dts` sha256 | `e9871e43…` | `ea688315…`（= `/opt/k60/trees/gates-device/dts/mondrian.dts`） |
| `:100` 处 | 注释正文，缺 `/*` | `\t/*`，正常闭合 |
| `dtc -I dts -O dtb` | `syntax error`，无产物 | 零诊断，4,307 B |

真实的因果：破坏是**真的**，来自合并提交 `585fe75a7`（"merge(ios27): land the iOS 27.0.1 stage-0 line
beside the 16.6.1 one"）把 `1e2e6814` 那段的注释开头丢了；修复也**已经在**——
`e1b6c15f` "fix(dts): restore the comment opener the merge dropped"（`dts/mondrian.dts | 2 ++`），
它已进 `remotes/emilelu/main`，`k60-gates` 的分支也带着。我读的是还没带这个修复的 stale 检出，
于是把「某个分支的坏状态」说成了「仓库今天坏了」。

因此本页的 PASS **不再需要任何临时改动**：上面那份复跑命令用的是未修改的镜像 dts
（`sha256 ea688315…`），2026-11-21 重跑结果与首版完全一致——dtb 4,307 B、ADT 16,648 B / 26 节点、
反编译 4,597 B / 225 行、`verdict: PASS (exit 0)`。

判据（已写进坑位 P-298 正文）：报「我这棵树编不过」必须同时给 `git rev-parse HEAD`、该文件
`sha256`、完整工具输出；三条不齐时它可能只是本地副本漂移，不许当成仓库缺陷扩散。

## 边界

- 这份 ADT 是**离线合成**的：输入是 27 设备仓的 `board.toml` 与 `dts`、27 的 OS profile、
  仓储 `devicetree.py`；不是构建线产出的 `payload/kernel.macho.adt`。
  它证明的是「同样的输入经同一条生成器路径，节点必定进 ADT」，不替代构建产物核对。
- `adt.unique_chip_id` 在 27 profile 里是 `required`，离线跑传的是合成值 `1`，
  只影响 `/chosen` 的 `unique-chip-id` / `chip-id`，与输入节点无关。
- 生成器是 `generate()`，与 `payload.py:232-236` 在 schema 2 下实际调用的是同一个函数。
- 主机侧 python3 是 3.14（`C:\Users\Emilelu\AppData\Local\Python\pythoncore-3.14-64`），
  脚本用标准库 `tomllib` + 子进程调 `dtc`，没有第三方依赖。
