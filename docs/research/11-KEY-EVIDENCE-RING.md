# 关键证据：clocks_on() 曾经成功执行过（2026-11-09 15:55）

> 这是第 4 轮定位的决定性发现，纠正了前 3 轮的假设方向。

## 证据原文（`evidence/usblog-20261108-213652/console.log:240`）

```
PONG APFS: SystemOS UUID appeared; rechecking IOMedia
goodix: clocks stay off: 0 0x80000002 0x4220          ← clocks_on() 执行完成并打印
K60 USBLOG: st=2 ev=0 cfg=0 dtr=0 fl=0                ← 此时 USB 还没枚举（st=2）
goodix: no valid firmware version: 00 00...
Pong touch: Goodix initialization failed; normal UI boot continues
K60 USBLOG: bus reset                                  ← 之后 USB 才开始枚举
```

## 三个关键推论

### 推论 1：`clocks_on()` 的三个 CBCR 读取是**安全的**
历史证明 `rd(GCC_QUP0_M_AHB_CBCR)`（`gcc+0x27004`）、`rd(GCC_QUP0_S_AHB_CBCR)`（`gcc+0x27008`）、
`rd(GCC_QUP0_SE4_CBCR)`（`gcc+0x274dc`）**执行过且没有挂死**，返回 false 后安全走 bitbang。

### 推论 2：`clocks_on()` 返回 false 时**不挂死**，能安全走到 bitbang
历史日志证明：`clocks stay off` → `no valid firmware version`（bitbang 探测）→
`Goodix initialization failed; normal UI boot continues` → 系统继续启动。
**完美闭环，没有挂死。**

### 推论 3：**0 日志 ≠ 挂死在 clocks_on**
这是最重要的纠正。触摸驱动在 `bsd_init` 早期运行，此时 **USB 控制台还没枚举**（`st=2`）。
所以：
- **如果不挂死**：后续 USB 起来后回放 ring，日志能看到（历史就是这样）
- **如果挂死**：USB 永远起不来，日志 0 字节 —— 但**挂死点可能在任何位置**

## 因此，新的排查方向

| 之前假设 | 现在的评估 |
|---|---|
| S1: 首次读 CORE/CORE_2X 挂死 | **仍可能**（这两个地址无历史证据），但不是唯一 |
| S2: io_supply_on 写 RSC 挂死 | **仍可能** |
| S3: geni_spi_init 访问 SE 挂死 | **仍可能** |

**关键：必须加「在最早阶段就写入 ring 的 printf」，而不是依赖 USB 控制台。**

## 下一步必须做的事（唯一正确路径）

在 `pong_goodix_init()` 和 `touch_thread()` 的**每一个关键步骤**前加 printf，
并且**确认这些 printf 即使 USB 没起来也会被 ring 记录、后续回放**。

具体埋点（按顺序）：
```c
pong_goodix_init() {
    printf("Pong touch: init entered\n");        ← 埋点 1
    ...
    if (!configuration()) {...}
    printf("Pong touch: configuration ok\n");     ← 埋点 2
    kernel_thread_start(touch_thread, ...);
}

touch_thread() {
    printf("Pong touch: thread entered\n");       ← 埋点 3（关键！区分线程是否启动）
    tlmm=ml_io_map(...);
    printf("Pong touch: io_map done\n");          ← 埋点 4
    if (!bring_up()) {...}
}

bring_up() {
    printf("Pong touch: bring_up entered\n");     ← 埋点 5
    gpio_output(PIN_RESET,...);
    printf("Pong touch: reset pin done\n");       ← 埋点 6
    if (clocks_on()) {
        printf("Pong touch: clocks_on returned true\n");  ← 埋点 7
        ...
        const char *problem=geni_spi_init(...);
        printf("Pong touch: geni_spi_init done: %s\n", problem?problem:"ok"); ← 埋点 8
```

**上机后看最后一个出现的埋点，就是挂死位置。**
