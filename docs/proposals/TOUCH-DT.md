# 触摸 DT 属性缺失 —— 待批准的修复提案

> 状态：**未实施**。触摸在 `docs/SCOPE-FREEZE.toml` 里处于冻结状态。
> 日期：2026-11-12
> 发现方式：核对驱动 `configuration()` 的断言 vs 构建出的 ADT 实际属性

---

## 问题

`pong_goodix.c` 的 `configuration()` 用一串短路 `&&` 断言 DT 属性，**任何一项不满足就返回 false**，
`pong_goodix_init()` 打印 `Pong touch: missing/incompatible K60 DT; normal UI boot continues` 后直接返回。

构建出的 ADT 里 `pong-touch` 节点实际是：

```dts
pong-touch {
    unixnu,adt-name = "pong-touch";
    spi-base = <0x00 0x990000>;
    tlmm-base = <0x00 0xf000000>;
    gcc-base = <0x00 0x100000>;
    rsc-base = <0x00 0x17a20000>;
    cmd-db-base = <0x00 0x80860000>;
    gpio-offset = <0x100000>;
    pins = <0x10 0x11 0x12 0x13 0x15 0x14>;
    max-x = <0x438>;      /* 1080 */
    max-y = <0x96c>;      /* 2412 */
}
```

驱动断言：

```c
property(entry,"avdd-gpio",&avdd_gpio,4) &&
property(entry,"max-x",&max_x,4) && property(entry,"max-y",&max_y,4) &&
...
pins[3]==19 && pins[4]==21 && pins[5]==20 && avdd_gpio==71 &&
max_x==14400 && max_y==32000;
```

| 断言 | ADT 实际 | 结果 |
|---|---|---|
| `avdd_gpio == 71` | **属性不存在** | `property()` 返回 false |
| `max_x == 14400` | 1080 | false |
| `max_y == 32000` | 2412 | false |
| `pins[3]==19 && pins[4]==21 && pins[5]==20` | 16,17,18,19,21,20 | true |

**`configuration()` 必然返回 false。**

## 后果

`pong_goodix_init()` 在 `configuration()` 之后才调用 `bring_up()` / `touch_thread()`，
七层诊断（device confirm、SPI mode select、CFG-DL、COORD-MODE 等）全在里面。
所以**这些诊断一次都没有执行过** —— 代码在内核里，但不可达。

这解释了为什么加了十几轮的触摸诊断，上机日志里一行都看不到。

## 根因：两个来源，一个生效一个不生效

`board.toml` 里 `[adt.arm-io.pong-touch.*]` 有正确的值：

```toml
[adt.arm-io.pong-touch.string]
compatible = "xiaomi,m11a-spi"
[adt.arm-io.pong-touch.u32]
avdd-gpio = 71
max-x = 14400
max-y = 32000
```

但 **`unixnu` 的 devicetree 生成器忽略 `[adt.arm-io.*]` 表** —— 它只把带
`unixnu,adt-name` 的 DT 节点导出为 `/arm-io` 子节点。yibiya 在
`fix/k60-input-adt` 分支的 `1e1a70e` 才加上这个能力，我们没有那个修复。

所以 `board.toml` 的这三个值从未进入 ADT，而 DTS 里的值（1080×2412 是**面板像素分辨率**，
不是触摸 IC 的原始坐标范围）生效了。

## 提议的修复（二选一）

### 方案 A：改 DTS（改动小，2 分钟）

```dts
pong-touch {
    ...
    compatible = "xiaomi,m11a-spi";
    avdd-gpio = <71>;
    max-x = <14400>;    /* GT9916R 原始坐标范围 0..14399 */
    max-y = <32000>;    /* 0..31999，不是面板的 1080x2412 */
};
```

代价：DTS 与 board.toml 仍然重复维护，将来可能再次漂移。

### 方案 B：移植 yibiya 的生成器修复（治本，但要动 unixnu）

取 `1e1a70e fix(adt): preserve configured arm-io metadata`，让 `[adt.arm-io.*]` 生效。
之后 board.toml 成为唯一来源，DTS 里可以删掉这些属性。

注意：那个修复会拒绝"配置的 arm-io 子节点与已导出硬件节点重名"，
所以我们**必须**从 DTS 或 board.toml 里删掉其中一份，否则构建直接报错。

## 建议

**先做方案 A**，让这一轮上机能看到触摸日志；确认诊断内容正确后，再评估方案 B。

## 相关提交（yibiya）

- `81dd415 fix(board): run the touch driver at its publishing stage` —— 加 `k60_touch_se=6`；
  我们 board.toml 第 179 行**已有**这个参数，不是我们的问题
- `04bda86 fix(touch,power): land the handshake, config download and battery link` ——
  确认 **1488 字节的 config 包匹配本机**（config_id `0x640fdf7d`, version `0x46`）
- `1e1a70e fix(adt): preserve configured arm-io metadata` —— 方案 B 的基础
