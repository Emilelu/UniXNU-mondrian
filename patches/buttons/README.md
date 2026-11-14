# K60 按键线的板级配置建议（board.toml）

> 基线：`/mnt/e/hackios/k60-buttons` 的 `feat/buttons` 分支（`main` = `a7fbcdb`，含 repo-hygiene 的 `K60_REPO` 修复）。
> 本目录只放**本线（buttons）**的产出。内核侧按键驱动
> （`patches/xnu/zzzz…-pong-physical-keys.patch`）由触摸线持有，本线不改。
> `board.toml` 属 **Lead 写作用域**，本线只交 diff 建议，不落盘。

## 文件

| # | 文件 | 作用 | 验证状态 |
|---|---|---|---|
| — | `board-toml-adt-buttons.diff` | 给 `board.toml` 插入 `[adt.buttons.*]`（`/buttons` 节点：`button-names`、`home-button-type`）与 `[adt.arm-io.pong-buttons.*]`（PMIC 仲裁器六个常量） | `git apply --check` 通过（见下） |

应用方式（由 Lead 执行）：

```bash
cd /mnt/e/hackios/k60-buttons      # 或 k60-usb，两仓 board.toml 目前逐字节相同
git apply --check patches/buttons/board-toml-adt-buttons.diff
git apply         patches/buttons/board-toml-adt-buttons.diff
```

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

## `[adt.buttons.*]` 的理由

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

## `[adt.arm-io.pong-buttons.*]` 的理由

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

`compatible = "pong,pm8350-keys"` 是**可选**的：驱动从不读 `compatible`
（`zzzz…-pong-physical-keys.patch:172-199` 只读六个属性），2026-11-14 上机镜像的 ADT 里该节点
**没有** `compatible` 也正常工作。写它只为与 yibiya 对齐、便于人读。

## 现状与必要说明（2026-11-14 复核）

- `E:/hackios/k60-buttons/board.toml` 与 `E:/hackios/k60-usb/board.toml` 逐字节相同（各 256 行），
  `grep '^\[adt'` 只有 `pong-touch` 四段，**没有** `[adt.buttons.*]`、**没有** `[adt.arm-io.pong-buttons.*]`。
- 但 2026-11-14 的上机镜像（`E:/k60-work/artifacts/usb-20261114b`，ADT sha256 `18a514e7…`）里
  `/arm-io/pong-buttons` **存在**、`/buttons` **不存在**。来源已查明：WSL 框架树
  `/opt/k60/trees/k60build/profiles/os/ipados-16.6.1-20G81/profile.toml:149-158` 有该节点
  （`["adt"."arm-io"."pong-buttons"]`，只有 `.u64`/`.u32`，没有 `.string`），而该文件是
  `git status` 里的 ` M`（**未提交**）。即：那一次能通按键，靠的是这处本地未提交改动。
- 因此本 diff 的作用是**把该配置从「WSL 里的未提交改动」变成「仓库里可复现的板级契约」**。
  若 Lead 先更新了 OS profile，请确认两处取值一致（`merge()` 顺序是 arch → soc → os profile → board，
  board 覆盖 profile，值相同则无副作用）。

## 验收

1. 落盘后重新生成一次 ADT（`make ... adt` 或整机构建）。
2. 用 `docs/research/buttons/tools/adt-inspect.py` 检查：

   ```bash
   python3 docs/research/buttons/tools/adt-inspect.py <kernel.macho.adt> --grep button-names
   python3 docs/research/buttons/tools/adt-inspect.py <kernel.macho.adt> --path /device-tree/arm-io/pong-buttons
   ```

   期望：`/device-tree/buttons` 的 `button-names` = `hold\0voldown\0volup\0`、`home-button-type` = 2；
   `/device-tree/arm-io/pong-buttons` 六个属性齐全。
3. 上机日志应出现 `Pong keys: PMIC windows mapped, pon-ppid=0x13 volume-up-ppid=0x18d`
   （已有 234 次记录，见 `docs/research/buttons/03-REVERSE.md`）。

## 未包含（交 Lead 决策）

- **长按电源键复位钩子**：zizhan 的 `patches/xnu-ipados18/0010-pong-power-key-reset.patch` 给
  `bsd/dev/pong_buttons.c` 加了 `pong_button_reset_hook`（长按 3 s 调平台 reset，boot-arg
  `pong_button_reset` 可调）。K60 的 `bsd/dev/pong_buttons.c` 由
  `patches/xnu/zzzz…-pong-physical-keys.patch` 提供，在触摸线写作用域内，本线不改。
- **内核侧中断路径**：pong 的 246 行中断版（PDC pin1 → SPI 481）需要在 `pong_buttons.c` 里加
  `channels`/`pdc` 窗口映射与 `armcpu_spi_attach`，同样落在上述被占用的补丁里。
