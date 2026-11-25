# 08 上机判读矩阵与实测：usb-20261115c（mode 2 回归）与 usb-20261115d（mode 1 判 P1/P2）

两张图都带 0411（mode 1 用 0xEF/0x02/0x01 复合设备描述符 + 三条 EP3 beacon）。判据来自
RESEARCH.md §24.8 与 §25。本线不 boot：镜像由 Lead 飞，设备 `6033dbec` 在 fastboot。
**2026-11-15 实测：c = PASS，d = PASS；P1 成立且已修复、P2 以修正后的判据 PASS、P3 不做**（详见各节实测小节）。

## 镜像身份

| 图 | 参数 | 作用 | 判什么 |
| --- | --- | --- | --- |
| `usb-20261115c` | `k60_usbvend=2` | mode 2 + 0411 | 回归：合体改动不破坏已 PASS 的回环 |
| `usb-20261115d` | `k60_usbvend=1` | mode 1 + 0411 | 判定 P1（主机绑定）与 P2（状态门 / ring） |

顺序：先 c 后 d。c 没复现回环，d 就不飞。（2026-11-15：c/d 均已飞完并 PASS。）

## c：mode 2 回归

mode 2 按设计把控制台门掉（`k60_usbvend_mode == 2`），所以 `console.log` 仍是 0 字节，
**这不是失败**。c 的证据是 COM 口上的回环本身：

1. `docs/research/usb/echo-test.ps1` 打该 COM 口，必须 `sent=64 received=64` 且逐字节一致（byte for byte）；
2. `capture.json` 里 `portSeen=true`、`portOpened=true`、`openErrors=0`，且无重枚举、`returnedToFastboot=false`；
3. mode 2 下 `ud_beacon()` 第一道门（`k60_usbvend_mode != 1`）直接 return，beacon 不写 EP3，
   所以 `K60BEACON:` 行在 c 上**必然没有**，判据 5c 给 SKIP 是预期。

判据口径（2026-11-15 Lead 裁决，c 实测后修正）：**0 字节采集本身不判有罪**。先看 `capture.json`：
`returnedToFastboot=true`（autoreset=300 窗口到期、设备已回 fastboot）或端口从未出现 → 该次采集作废、
重飞；只有端口在线且设备未回 fastboot 时，0 字节 / 回环不逐字节一致才算 0411 有罪。
（c 实测就是反例：同一镜像第一飞 0 字节、第二飞全流程 PASS。）

| c 的结果 | 结论 | 下一步 |
| --- | --- | --- |
| 回环逐字节一致、端口稳定 | 0411 对 mode 2 无副作用 | 飞 d（已完成） |
| 端口在线但 0 字节 / 回环不符 / 反复重枚举 | 0411 本身有问题（beacon 与回环共用 EP3 的 `tx_active` 记账） | 修 0411 重出 c；不浪费 d 的窗口 |
| `returnedToFastboot=true` 或端口未出现 | 采集作废（窗口到期） | 重飞，不判 0411 |

### c 实测（2026-11-15，Lead 飞）

- 第一飞：opened-no-data，0 字节 —— autoreset=300 窗口已到期，设备已回 fastboot，采集作废；
- 第二飞 `boot-and-echo.ps1` 全流程：COM5 在 9.5 s 出现，`sent=64 received=64`，
  `RESULT: PASS (echo matched byte for byte)`，echo-exit=0；
- 证据：`E:/iOS Port/Work/evidence/usb-echo-20261115-c/`（echo.log 为 UTF-16LE）。
- **结论：0411 没有破坏 mode-2 回环。c = PASS。**

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

### d 实测（2026-11-15，Lead 飞）

证据 `E:/iOS Port/Work/evidence/usblog-20261115-170518/`：`console.log` 3733 行 / 265,561 B；
`capture.json` state=captured-budget-complete、complete=true、openErrors=0、returnedToFastboot=false。

1. **主机侧（P1 判定）**：MI_00 → USB Serial Device (COM6)，Ports OK；MI_02 → "K60 XNU console"
   Status=Error（无驱动）；顶层 USB Composite Device OK。控制台恢复：K60 USBLOG 255 行（判据 1 PASS），
   boot 日志与 SpringBoard 133 行（:1039–:3173）完整，panic 0。
2. **P2 以修正后的判据 PASS**：P2 的原始规格（主机经 EP3 驱动 beacon）被否证，判据改为内核自发
   `K60BEACON:` 行；beacon 五条全在（console.log:1-5：`cfg mode1 ep6 ok ep7 ok` / `dtr 0` /
   `dtr 1` / `dtr 1` / `gate open`），判据 5c PASS。同一因果的另一面是 5b SKIP：vendor 对 armed
   但主机无驱动写它（与 MI_02 Error 同源）——主机对 EP3/EP6 都只读不写。
3. 寄存器与请求行：:278 `setup 80 06 0100 len 64`；:424 `setup 80 06 0200 len 98`；:425
   `setup 00 09 0001`；:426 `cfg 98 bytes ep6 0 ep7 0 DALEPENA 0x000000ef echo 1 on 6/7`
   （DALEPENA 0x3 → 0xef）。
4. 判据执行器：**6 pass / 1 fail / 1 skip**。5b SKIP 的因果见第 2 条（与 P2 修正口径同源）。
   判据 2（heartbeat）117/131：heartbeat 线程全程在跑——tick 从 :266 到
   最后一行、每个 tick 都是 run=1 halt=0 DALEPENA 0xef、中位间隔 16 行、末次 SpringBoard 后还有
   33 个 tick；缺口是 ramoops 定长环形缓冲在 SpringBoard 突发期丢最旧行（arm_init.c:120-171）
   的采集窗口伪影，非设备故障。

### MI_02 无驱动 = Error 的定性（答 Lead 问题）

**预期形状，且必须出现**：

- IF2 是 vendor `0xff/0xfe`，Windows 没有自带驱动 → 设备管理器标 Error 是「枚举成功、无驱动」的
  正常表现。**不要求它不出现**——出现才证明 98 字节配置的 IF2 枚举了，EP6/EP7 裸接口访问通道在；
  MI_02 不出现才说明 IF2 没枚举（复合配置有问题）。
- 与 RESEARCH.md §24.6 一致：IF2 没有系统驱动，EP6/EP7 写入需要 Mac IOKit 或 WSL usbip；
  本机 Windows 没有 libusb，所以判据 5b（vendor 回环）在 d 上 SKIP 是预期。

### 最终裁决

- **P1 成立且已修复**：mode-1 控制台静默的根因是设备级串口绑定（device class 02/02）；
  0xEF/0x02/0x01 复合声明后，主机按复合功能绑定，控制台经 MI_00 完整出字（SpringBoard 全量、无 panic）。
- **P2 以修正后的判据 PASS**：原始规格（主机经 EP3 驱动 beacon）被否证，判据改为内核自发的
  `K60BEACON:` 行；configured + dtr + gate 三条 beacon 全到，5c PASS。
- **P3 不做**（Lead 裁决）；本线正式收工，转待命。

## 引用

- 设计与证伪方法：RESEARCH.md §24.8、§25（§25.2 为本文实测记录）
- 补丁：`patches/usb/0411-k60-usb-composite-beacon.patch`
- 采集：`E:/iOS Port/Sources/Hardware/k60-gates/scripts/capture-k60-usblog.ps1`；上机脚本 `E:/iOS Port/Work/scratch/usb/boot0410b-lead.sh`（Lead-only）
- 实测证据：`E:/iOS Port/Work/evidence/usb-echo-20261115-c/`（c）、`E:/iOS Port/Work/evidence/usblog-20261115-170518/`（d）