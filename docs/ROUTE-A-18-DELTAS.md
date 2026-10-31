# pong → K60 板级差异清单（route-a-18 第一步）

来源：本地 UniXNU-pong main（64ddf28）逐文件阅读。

## 1. 面板/显示（K60 已有可用栈，回填参数即可）

- pong: 1080×2412, stride 4320, DCS 背光（`dts/pong.dts` 存在）
- K60: 1440×3200, DSC video mode, 背光另一路 —— 我们的 MiniIOMobileFramebuffer 已在 K60 上工作（0210/0213）
- 动作: **保留 K60 显示栈**；pong 的 PongBacklight/panel 选择逻辑对照移植

## 2. 触摸

- pong: Goodix Berlin-D（drivers/GoodixTouch/ + userland/touch.c）
- K60: Goodix（同族），LOCKSCREEN-2026-10-28.md 记录 RSC 块 0x17a00000 访问死——pong 的 Goodix 代码可对照我们的 0240-0243 移植版
- 动作: 对照 pong 的 GoodixTouch 与我们 ios-sweet-k60/patches 的 0240-0243

## 3. 存储（几何差异最大的一项）

- pong: OS/SystemOS/8 GiB Data 三窗口，root_match UUID 见其 ADT 生成器
- K60: unixnu 分区 LBA 53342976..61731583（32 GiB），OS 4.746G + SystemOS 2.482G + Data 2 GiB（已实测）
- 动作: **保留 K60 的 unixnu 几何与 2 GiB Data**；pong 的 NativeUfs 代码同 SoC 直接用

## 4. GPU（pong 的最大贡献）

- PongAdreno（A730）+ AdrenoMetal + PongMetal: GMU/HFI/CP/Clocks/SMMU4K/Firmware 全栈
- K60 = 同款 A730；我们 16.6.1 的 0231/0232 只是 stub/bridge
- 动作: 整体搬 pong 的 A730 栈，替换我们的 stub

## 5. 电源/音频/WiFi/按键

- PongPower: ADSP/AudioReach/TFA9873/PMIC —— K60 同族（PM8350c）
- PongWifi: QCA6490/ath11k —— K60 是 QCA6490 同款
- 按键: PMIC PON 事件 → HID —— K60 的 K60KeypadDeviceLib 已工作，保留

## 6. 固件/ADT

- pong: DarwinBoot24 + Pong ADT 生成器（CPU affinity/timer/GIC/UFS 资源 + PMIC/Goodix 自定义属性）
- K60: uefi-mondrian DarwinBoot22 + 我们的 ADT（display-scale=3 等）
- 动作: **换 DarwinBoot24**（22H374 ABI），ADT 生成器以 pong 为基础改 K60 面板/按键属性

## 7. 需要的新输入

- 22H374 IPSW: kernelcache + dyld shared cache + App cryptex（Apple CDN，按需下载）
- Pong modem/vendor firmware（作者标注 local；我们要找 QCN/ModemFS 替代或先跳过 WiFi/音频）

## 8. Linux 构建链（关键工作量）

- `scripts/build-xnu-ipados18.sh`（1116 行）无 Linux 分支；CI 全 macos-15-intel
- 方案: 把 16.6.1 已验证的 `scripts/linux/prepare-xnu.py` + `kernel.py:linux_env()`（HOST_CC/MIGCOM/CLT_PREFIX）注入法接入该脚本
- `/opt/unixnu-linux` 工具链已就绪（16.6.1 用的是同一套）
- firehose: 16.6.1 fakeroot 的 libfirehose_kernel.a 先复制过渡，之后按 10063→11417 差异重编

## 9. 证据等级提示

- pong porting.toml: 13×source / 0×host / 0×device —— "桌面"无 device 证据链
- `migration-state.json`: image_hashes_used=false，镜像不回读
- 结论: 路线可信（作者实机做过 + 同 SoC），但每一步我们都要自己留 device 证据（沿用 0235-0241 探针栈）

## 10. 执行顺序

1. fetch xnu-11417.140.69 + 22H374 IPSW 成件
2. Linux 构建链接入（prepare-xnu.py + linux_env → build-xnu-ipados18.sh）
3. 出 darwin24 最小内核（K60 面板参数）→ fastboot boot 验证到控制台输出
4. 挂 pong 的 NativeUfs/ArmCpu → 到 mount 成功
5. HackiOS init（pong userland，K60 Data 布局）→ 到用户态
6. A730 GPU → 桌面

--- 分支: route-a-18 ｜ 16.6.1 成果在 main ｜ 17.7.11 尝试在 route-a-17 ---
