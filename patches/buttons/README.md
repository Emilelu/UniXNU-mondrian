# K60 按键线的板级配置记录（board.toml）

> 基线：`/mnt/e/hackios/k60-buttons` 的 `feat/buttons` 分支，已 rebase 到 `origin/main` = `314497d`。
> 本目录只放**本线（buttons）**的产出。内核侧按键驱动
> （`patches/xnu/zzzz…-pong-physical-keys.patch`）由触摸线持有，本线不改。
> `board.toml` 属 **Lead 写作用域**，本线只记录结论，不落盘。

## 现状（2026-11-14 结案，两段都已在仓库里）

- `[adt.buttons.*]` 由 Lead 落进 `board.toml:268-276`（main `174fb69`）：`:268` `.string`
  （`compatible="buttons"`、`device_type="buttons"`）、`:272` `.strings`
  （`button-names=["hold","voldown","volup"]`）、`:275` `.u32`（`home-button-type=2`）。
- `[adt.arm-io.pong-buttons.*]` 由 Lead 落进 `board.toml:267-280`（main `5cd8924` "fix(adt): own
  the pong-buttons node instead of a build-copy edit"）：`.u64` 三个基址 + `.u32` `ee`/`pon-ppid`/
  `volume-up-ppid`。仓库自此自洽，不再依赖构建机 profile 的未提交改动。
- 本目录原先的 `board-toml-adt-buttons.diff` **已按 Lead 指示删除**，本线不再交 diff。
  删除前它已被改成纯追加（只补 `[adt.arm-io.pong-buttons.*]`），因为旧版同时含
  `[adt.buttons.*]`，与 main 的段重复 —— 那种 diff `git apply --check` 会**通过**，但打完
  `tomllib` 直接报 `Cannot declare ('adt','buttons','string') twice`。
  **教训：`git apply --check` 不能当验收，打完必须解析一次 TOML。**
- 下面两节保留取值来源与推导，供复核用；**不需要再落盘**。

## 为什么不是补丁 `scripts/make-pong-adt.py`

上一版交的是 `0001-adt-buttons-node.patch`（改 `scripts/make-pong-adt.py`），**已删除**：
`board.toml:1` 是 `schema_version = 2`，此时 ADT 由 `scripts/unixnu/devicetree.py` 的 `generate()`
生成（`payload.py:231-236` 的 `if ctx.schema_version == 2:` 分支），`make-pong-adt.py` 只在
`else` 分支（`payload.py:237` 起）被调用 —— 在 K60 上**永远不会执行**，改它是死代码。

真正生效的入口只有一处：`devicetree.py:388-390`

```python
for name in ('defaults', 'options', 'product', 'buttons'):
    if name in platform or name in ('defaults', 'options', 'product'):
        children.append(platform_node(name, platform.get(name, {})))
```

即 `/buttons` **只在 `[adt].buttons` 存在时发射**；`/arm-io/*` 只认 `[adt.arm-io.*]`（`devicetree.py:384`）。
所以两段都必须写进 `board.toml`。

## `[adt.buttons.*]` 的理由（已落盘）

MobileGestalt 从 `/buttons` 读 `button-names` 与 `home-button-type`
（`UniXNU-docs/docs/zh/guide/mobilegestalt.md:26-27`、`docs/zh/porting/device-tree.md:223`）。
没有该节点时平台按「有 Home 键的 iPad」回退（pong 的注释原话：
"Missing HomeButtonType defaults to a Home-button iPad in Gestalt"）。K60 只有电源/音量上/音量下三个
实体键，没有 Home 键，所以 `button-names` 里**不写** `menu`。

取值照抄同 SoC 兄弟仓 yibiya/main 的 `board.toml:256-264`（提交 `8e691d5`）：

- `[adt.buttons.string]`：`compatible="buttons"`、`device_type="buttons"`
- `[adt.buttons.strings]`：`button-names = ["hold", "voldown", "volup"]`
- `[adt.buttons.u32]`：`home-button-type = 2`

**不写** `opposed-power-vol-buttons`：`UniXNU-docs` 里 grep 不到该键、yibiya 的 board.toml 也没有，
只有 pong/zizhan 的旧 ADT 脚本用过，缺依据。

## `[adt.arm-io.pong-buttons.*]` 的理由（已由 main `5cd8924` 落盘）

`bsd/dev/pong_buttons.c` 的 `configuration()` 用 `SecureDTLookupEntry(NULL,"/arm-io/pong-buttons")`
查节点，并逐属性校验六个值（`patches/xnu/zzzz…-pong-physical-keys.patch:173-199`）：
`core-base` / `cnfg-base` / `observer-base` / `ee` / `pon-ppid` / `volume-up-ppid`。
缺节点打印 `Pong keys: DT node /arm-io/pong-buttons not found`，缺属性打印
`Pong keys: missing <prop>`，值不符打印 `Pong keys: unexpected bases …`。

取值来源（三源一致）：

- 官方参考 `ButtonProbe.cpp:26-27`：`kCore 0xc400000`、`kCnfg 0xc42d000`、`kObsrvr 0xc440000`、
  `kPonPpid 0x013`、`kGpioPpid 0x18d`
- K60 live FDT 反编译（`docs/research/buttons/03-REVERSE.md`）：PON IRQ7 = 电源、IRQ6 = 音量减、
  `pm8350 gpio6`（`gpios=<0x57b 0x06 0x01>`，ACTIVE_LOW）= 音量加
- yibiya `board.toml:271-281`（提交 `8e691d5`）：同六个值

落盘内容（与 yibiya 同值；Lead 落盘时**没有**写 `compatible` —— 驱动从不读它，见 `board.toml:273-280`）：

```toml
[adt.arm-io.pong-buttons.u64]
core-base = "0xc400000"
cnfg-base = "0xc42d000"
observer-base = "0xc440000"

[adt.arm-io.pong-buttons.u32]
ee = 0
pon-ppid = "0x013"
volume-up-ppid = "0x18d"
```

## 复现性（已闭合）

- 仓库 `board.toml` 现自带两段，用 `unixnu.devicetree.generate()` 重生成 ADT 得
  **14,660 B / 23 节点**：`/device-tree/buttons`（`button-names` = `hold / voldown / volup`、
  `home-button-type=0x2`）与 `/device-tree/arm-io/pong-buttons`（六属性）**同时存在**。
  干净重建不再需要任何构建机本地改动。
- 历史（已不再依赖）：2026-11-14 的上机镜像（`E:/k60-work/artifacts/usb-20261114b`，
  ADT sha256 `18a514e7…`）里只有 `/arm-io/pong-buttons`、没有 `/buttons`，其节点来自 WSL 框架树
  `/opt/k60/trees/k60build/profiles/os/ipados-16.6.1-20G81/profile.toml:149-158` 的未提交改动。
  `5cd8924` 把这六行搬进 `board.toml` 后该依赖消失（`merge()` 顺序 arch → soc → os profile → board，
  board 覆盖 profile；取值相同无副作用）。

## 验收（复核用）

1. 重新生成一次 ADT（`make ... adt` 或整机构建），并解析一次 TOML 确认没重复表：
   `python3 -c "import tomllib;print(sorted(tomllib.load(open('board.toml','rb'))['adt']))"`
2. 用 `docs/research/buttons/tools/adt-inspect.py` 检查：

   ```bash
   python3 docs/research/buttons/tools/adt-inspect.py <kernel.macho.adt> --grep button-names
   python3 docs/research/buttons/tools/adt-inspect.py <kernel.macho.adt> --path /device-tree/arm-io/pong-buttons
   ```

   期望：`/device-tree/buttons` 的 `button-names` = `hold / voldown / volup`（NUL 分隔）、
   `home-button-type` = 2；`/device-tree/arm-io/pong-buttons` 六个属性齐全。
3. 上机日志应出现 `Pong keys: PMIC windows mapped, pon-ppid=0x13 volume-up-ppid=0x18d`
   （已有 234 次记录，见 `docs/research/buttons/03-REVERSE.md`）。

## 未包含（Lead 决定暂不做）

- **长按电源键复位钩子**：zizhan 的 `patches/xnu-ipados18/0010-pong-power-key-reset.patch` 给
  `bsd/dev/pong_buttons.c` 加了 `pong_button_reset_hook`（长按 3 s 调平台 reset，boot-arg
  `pong_button_reset` 可调）。K60 的 `bsd/dev/pong_buttons.c` 由
  `patches/xnu/zzzz…-pong-physical-keys.patch` 提供，在触摸线写作用域内；2026-11-14 Lead 决定
  等触摸线空闲再协调，本线不做。
- **内核侧中断路径**：pong 的 246 行中断版（PDC pin1 → SPI 481）需要在 `pong_buttons.c` 里加
  `channels`/`pdc` 窗口映射与 `armcpu_spi_attach`，同样落在上述被占用的补丁里。
