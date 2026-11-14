# K60 按键补丁系列

> 基线：`/mnt/e/hackios/k60-buttons` 的 `feat/buttons` 分支（`main` = `90d8271`）。
> 本目录只放**本线（buttons）**的补丁。内核侧按键驱动（`patches/xnu/zzzz…-pong-physical-keys.patch`）
> 由触摸线持有，本线不改。

## 应用顺序

```bash
cd /mnt/e/hackios/k60-buttons
git apply --check patches/buttons/0001-adt-buttons-node.patch
git apply         patches/buttons/0001-adt-buttons-node.patch
```

| # | 文件 | 作用 | 验证状态 |
|---|---|---|---|
| 0001 | `0001-adt-buttons-node.patch` | `scripts/make-pong-adt.py` 在 `node('options')` 与 `node('product', …)` 之间插入 `node('buttons', …)`：`button-names = volup/voldown/hold`、`home-button-type = 2`、`opposed-power-vol-buttons = 1` | `git apply --check` 通过；隔离副本打补丁后 `py_compile` 通过；`make-pong-adt.py --dram-size 0x200000000` 生成 ADT 成功（12,132 B），`pong_adt_contract.audit_adt()` 无告警，产物里 `buttons` / `button-names` / `home-button-type` / `opposed-power-vol-buttons` 各命中 1 次（本线**未**跑整机构建、未上机） |

## 0001 的理由

MobileGestalt 从 `/buttons` 读 `button-names` 与 `home-button-type`（`UniXNU-docs/docs/zh/guide/mobilegestalt.md:26-27`、
`docs/zh/porting/device-tree.md:223`）。K60 的 `scripts/make-pong-adt.py` 只生成 `/arm-io/pong-buttons`，
没有 `/buttons`，于是平台按「有 Home 键的 iPad」回退（pong 的注释原话：
"Missing HomeButtonType defaults to a Home-button iPad in Gestalt"）。K60 只有电源/音量上/音量下三个实体键，
没有 Home 键，所以 `button-names` 里**不写** `menu`。

写法直接照抄同 SoC 兄弟仓：

- `UniXNU-pong/scripts/make-pong-adt-ipados18.py:301-307`
- `UniXNU-zizhan/scripts/make-pong-adt-ipados18.py:330-336`（与 pong 完全相同）
- `UniXNU-liuqin/scripts/make-liuqin-adt.py:176-179`（无 `opposed-power-vol-buttons`）

`opposed-power-vol-buttons=1` 只有 pong/zizhan 用，`UniXNU-docs` 里 grep 不到；它表示电源键与音量键分居两侧，
K60 与 pong 同为竖排两侧布局，故照抄。

## 未包含（交 Lead 决策）

- **长按电源键复位钩子**：zizhan 的 `patches/xnu-ipados18/0010-pong-power-key-reset.patch` 给 `bsd/dev/pong_buttons.c`
  加了 `pong_button_reset_hook`（长按 3 s 调平台 reset，boot-arg `pong_button_reset` 可调）。K60 的
  `bsd/dev/pong_buttons.c` 由 `patches/xnu/zzzz…-pong-physical-keys.patch` 提供，该文件在触摸线写作用域内，本线不改。
- **内核侧中断路径**：pong 的 246 行中断版（PDC pin1 → SPI 481）需要在 `pong_buttons.c` 里加
  `channels`/`pdc` 窗口映射与 `armcpu_spi_attach`，同样落在上述被占用的补丁里。
