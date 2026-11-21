# 27 内核没有控制台：两次 0 字节飞行的真实含义

日期：2026-11-21
证据命令都在下面，数字来自当前盘上的两个内核。

## 一句话

27 内核里**没有任何把文字送到 USB 串口的代码**。所以那两次 `fastboot boot` 得到 0 字节，不能用来判断内核有没有跑起来——镜像在构建时就注定了不会出字。

## 实测

```
$ llvm-nm-18 --defined-only <kernel> | grep -oE '_(pong|k60)_[a-z0-9_]*(console|serial)[a-z0-9_]*'
== ipados-16.6.1-20G81 (cellular-k49)
_k60_console_export_sysctl
_k60_serial_clock
_k60_usblog_console_up
_pong_ramoops_console_init
_pong_ramoops_console_write
== ios-27.0.1-24A446 (ios27-out)
_k60_serial_clock
```

17 条控制台/串口符号里 27 只剩一个 `_k60_serial_clock`（时钟，不是输出通道）。`pong_ramoops*` 也不在，所以连「panic 前的最后一屏」这条后路也没有。

## 它们本来是哪些补丁带来的

| 补丁 | 作用 | 27 series 里有吗 |
| --- | --- | --- |
| `patches/xnu/0243-k60-console-export.patch` | `k60_console_export` sysctl + `k60_usblog_console_up()` 状态机 | 无 |
| `patches/xnu/0300-k60-usblog-ep0.patch` | EP0 上的 USB 日志通道（真正把字节推出去的那一层） | 无 |
| `patches/xnu/0306-k60-console-snapshot.patch` | 控制台快照（重放最后一屏） | 无 |
| `patches/xnu/0331-k60-prevlog-replay.patch` | 上一次启动的残留日志重放 | 无 |
| `patches/xnu/0232-k60-pong-adreno-ramoops-bridge.patch` | `pong_ramoops_console_init/write` | 无 |

`patches/xnu-12377/series` 共 33 条，`grep -E 'console|usb'` 只命中 `0543-k60-ios27-panel-console.patch` 与 `0544-k60-console-font-scale.patch`——**它们在屏上画字，不在串口上出字**。两者不是同一件事：`0543` 解决「内核能动之后屏幕上看得见」，`0300` 解决「我们这边收得到」。

## 由此被推翻的结论

- 「设备静默挂死、需要人工复位」——挂死是真的（两次都没回 fastboot），但**它不是从日志推出来的**，是从「设备不枚举」推出来的；0 字节本身不构成内核没跑的证据。`F2-PREDICTION.md` 里 INVALID 的定义仍然成立，只是原因换了：不是「跑了但 gadget 没枚举」，而是「构建里没有 gadget 这一层」。
- 「prelink 的 203 个桩在 console 之前可达性为 0，所以可以飞」——这个论证的方向仍然对，但它依赖「console 会起来」；console 根本不在这颗内核里，所以那次飞行不可能验证它。

## 下一步（按顺序，都可离线验）

1. 把 `0243` + `0300` 移植到 `patches/xnu-12377/series`，判据是重编后 27 内核 `llvm-nm` 里出现 `_k60_usblog_console_up`，且 16 线内核符号集不变。
2. 移植前先确认这两条补丁在 12377 上的依赖面：它们碰 `iokit/` 与 `osfmk/` 的哪些文件，是否与已落的 `0540/0541/0542` 重叠。
3. 只有第 1 条绿了，`fastboot boot` 的 0 字节才重新成为「有信息量的 0 字节」；在那之前任何飞行都是盲飞（铁则 8）。

## 纪律

- 不许用「屏幕上有字」代替「串口有字」：两者的失败面不同（面板控制台在 `0543`，串口在 `0300`）。
- 不许把这次发现写成「内核没跑」——它只说明**我们听不到**，说明不了它有没有说话。
