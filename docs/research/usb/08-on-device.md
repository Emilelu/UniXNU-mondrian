# 08 上机判读矩阵：usb-20261115c（mode 2 回归）与 usb-20261115d（mode 1 判 P1/P2）

两张图都带 0411（mode 1 用 0xEF/0x02/0x01 复合设备描述符 + 三条 EP3 beacon）。判据来自
RESEARCH.md §24.8 与 §25。本线不 boot：镜像由 Lead 飞，设备 `6033dbec` 在 fastboot。

## 镜像身份

| 图 | 参数 | 作用 | 判什么 |
| --- | --- | --- | --- |
| `usb-20261115c` | `k60_usbvend=2` | mode 2 + 0411 | 回归：合体改动不破坏已 PASS 的回环 |
| `usb-20261115d` | `k60_usbvend=1` | mode 1 + 0411 | 判定 P1（主机绑定）与 P2（状态门 / ring） |

顺序：先 c 后 d。c 没复现回环，d 就不飞。

## c：mode 2 回归

mode 2 按设计把控制台门掉（`k60_usbvend_mode == 2`），所以 `console.log` 仍是 0 字节，
**这不是失败**。c 的证据是 COM 口上的回环本身：

1. `docs/research/usb/echo-test.ps1` 打该 COM 口，必须 `sent=64 received=64` 且逐字节一致（byte for byte）；
2. `capture.json` 里 `portSeen=true`、`portOpened=true`、`openErrors=0`，且无重枚举、`returnedToFastboot=false`；
3. mode 2 下 `ud_beacon()` 第一道门（`k60_usbvend_mode != 1`）直接 return，beacon 不写 EP3，
   所以 `K60BEACON:` 行在 c 上**必然没有**，判据 5c 给 SKIP 是预期。

| c 的结果 | 结论 | 下一步 |
| --- | --- | --- |
| 回环逐字节一致、端口稳定 | 0411 对 mode 2 无副作用 | 飞 d |
| 0 字节 / 回环不逐字节一致 / 端口反复重枚举 | 0411 本身有问题（beacon 与回环共用 EP3 的 `tx_active` 记账） | 修 0411 重出 c；不浪费 d 的窗口 |

## d：mode 1 判 P1 / P2

先在设备管理器一眼核对（不用等采集）：

- `USB\VID_1209&PID_0001&MI_00`（以及 `MI_01`）出现 = 0xEF 描述符生效，主机按复合功能绑定；
- COM 口号可能变化（新建 devnode）。采集脚本按 `SERIALCOMM` 的 usbser 项解析，不要写死 COM5。

beacon 三条（0411 实现：累积发送；新 beacon 用 ENDTRANSFER 替换仍 pending 的旧传输，
晚开端口能一次读全历史）：

```
K60BEACON: cfg mode1 ep6 ok ep7 ok
K60BEACON: dtr 1
K60BEACON: gate open
```

`cfg` 那行若为 `cfg mode1 ep6/ep7 failed`，说明 mode 1 必需的 vendor 端点没配置成功：
把那行与 `K60 USBLOG: cfg 98 bytes ep6 … ep7 … DALEPENA …` 一起贴回，按 §20.2 分支 B/C 处理。

| console.log 观测 | MI_xx | 结论 | 下一步 |
| --- | --- | --- | --- |
| 有 `K60 USBLOG` 行（判据 1 过） | 出现 | **P1 成立并被 0xEF 修好**：主机绑定是根因，控制台恢复 | 跑完整判据表，mode 1 收尾 |
| beacon 三条齐但 0 字节 console | 出现 | P2 的门已满足（configured + dtr + gate 都到了），缺陷在 ring 快照或文本 drain（记作 P2prime） | 下一轮打印 `pong_ramoops_snapshot` 返回值与 ring 头 |
| 有 `cfg`、无 `dtr` 或无 `gate open` | 出现 | **P2 成立**：主机没发 line-state（`dtr` 恒假）或 gate 没开 | 查 usbser 在复合功能下何时发 `0x22`；对照图把 `dtr` 从门里去掉 |
| 0 字节且无任何 beacon | 不出现 | 主机从没读到 EP3：**P1 未被修好**（绑定仍错）或 EP3 链断（P3） | 出 `k60_usbvend=3` 单变量图（P3，Lead 批准后） |
| 0 字节且无任何 beacon | 出现 | EP3 链断（P3）：端点配置或资源冲突 | 同上 |

判据 5c（`K60BEACON:` 三行）由 `python3 docs/research/usb/analyze-capture.py <evidence-dir>` 自动给出：
三条齐 PASS；缺任一 FAIL；一行都没有 SKIP。

## 引用

- 设计与证伪方法：RESEARCH.md §24.8、§25
- 补丁：`patches/usb/0411-k60-usb-composite-beacon.patch`
- 采集：`E:/hackios/k60-gates/scripts/capture-k60-usblog.ps1`；上机脚本 `E:/k60-work/scratch/usb/boot0410b-lead.sh`（Lead-only）
