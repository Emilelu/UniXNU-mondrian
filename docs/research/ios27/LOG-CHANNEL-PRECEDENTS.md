# 早期日志通道：官方要求与成功先例对照

调查日期 2026-11-23，冻结期离线取证（不构建、不上机）。目的：在改任何代码前，先用官方文档与同 SoC 成功先例回答一个问题——iOS 27 在这块板上，内核最早能从哪条通道说话。

## 1 官方要求（`docs/zh/porting/log-capture.md`）

该页把抓日志拆成四个阶段，逐阶段给「所需支持」与「保存结果」：

| 阶段 | 所需支持 | 保存结果 |
| --- | --- | --- |
| UEFI 菜单 | GOP 显示、菜单输入、Advanced Logger 和二维码插件 | 扫描屏幕导出的固件 `.log` 文件 |
| XNU 入口 | **UART 或屏幕诊断** | 串口日志或最后检查点/panic 的照片 |
| 存储 | 预留日志区域、内核写入器和 Linux 或 recovery 读取器 | 内核消息缓冲和诊断快照 |
| 重复测试 | 可用的日志读取与返回 bootloader 功能 | 每次启动独立的证据目录 |

同一页第 3 节还写明：「停在绿色交接条时，按入口探针步骤操作」——绿色交接条是官方认可的入口见证。

结论：官方在「XNU 入口」这一阶段只承认两条通道，**UART 或屏幕诊断**；持久化日志（存储阶段）是下一步，不是入口阶段的手段。

## 2 sheng（SM8550，能进系统）

- `board.toml:66` 的 27 组 `kernel_args` 含 `-v`、`serial=3`、`sheng-log=1`。
- `patches/xnu-12377/` 只有 18 条补丁，`grep -rln 'console\|dpu\|DPU'` 在 sheng 的 27 补丁里 **0 命中**——它没有移植任何视频控制台补丁。
- 真正的日志通道是内核侧的 `package/BootLog.c`。文件头注释原文：

  > Diagnostic log on UFS (boot argument sheng-log=1): every 2 s the text the board page would show (the diagnostic page, the live banner, the GPU rows, a caught panic message) and the kernel message buffer are written to the last 32 MiB of userdata through NativeUfs's bounded log window, so a run can be read back afterwards.

  窗口布局（4096 字节块）：0 头、1..32 内核消息缓冲、33.. 文本槽 16 块环形；版本 5 把消息区做成环形流。
- 它是**编进内核**的：`scripts/build-gop-legacy-display.py:245-246` 把 `kits/sheng/BootLog.c` 编成 `BootLog.o`。
- 它依赖 NativeUfs 的接口（`package/BootLog.c:30-34`，全部 `weak_import`）：
  `native_ufs_log_open(uint64_t *, uint64_t *, const char **)`、`native_ufs_log_write(uint64_t, uint32_t, const void *)`、`native_ufs_export_blocks()`、`native_ufs_export_write(...)`、`native_ufs_log_sync()`。
- 读取器：`scripts/read-sheng-log.py`（经 Linux log reader 的 USB CDC ACM shell 取回，`porting.toml:645` 记录了 151 轮 / 2,254,981 字节 / 635 个消息块的验收）。

⇒ **sheng 能进系统，不证明视频控制台可用；它绕开了视频控制台，用 UFS 分区日志。** 而且它的日志通道依赖 NativeUfs——不是「不依赖任何驱动」的通道。

## 3 我们 27 线的现状

- `configs/mondrian_ios27_defconfig:20` 是 `CONFIG_XNU_NATIVE_UFS=n`，`build-xnu-generic.sh:646` 的 `-force_load libNativeUfs.a` 在 Linux 上没有生产者（P-310）。⇒ 没有 `native_ufs_log_*`，sheng 那条路走不通，除非先移植 NativeUfs。
- USB CDC 控制台（`0547-k60-usblog-ep0.patch`）要有 USB 栈才可读，入口阶段没有。
- 视频控制台（`0543` + `0552` + `0577`）是唯一「理论上最早」的通道，但：
  - `DarwinBootPkg/Driver/DarwinBoot.c:555-559`（我们自己的注释）：loader 里每一次直接写 `Video[0]` 都「reached the panel zero times」，只有 GOP `Blt` 有上屏记录；
  - `DarwinBoot.c:657-660`：`FillScreen`、跳板绿条、`DiagDraw` 阶段文字，四次飞行零次上屏。
  - 最近一次飞行（`boot.img f71f71bf…`）屏幕是「洋红在右、左边黑」，串口 0 字节。

## 4 三条通道的前提与证据状态

| 通道 | 前提 | 证据状态 |
| --- | --- | --- |
| UART | 板上有可用 UART，且固件/内核已初始化该 UART | **未查**。官方把它列为入口阶段的首选；K60 是否有可用测试点/复用未确认 |
| 屏幕诊断 | boot_args `Video[]` 正确 + 内核完成映射 + 面板扫描的正是这块缓冲 | 部分失败：能写亮一半，说明 Video[] 非零、映射成功，但几何或扫描缓冲不对 |
| UFS 日志 | NativeUfs 的 bounded log window 可用 | 先例完整（sheng `BootLog.c`），但我们 27 没有 NativeUfs |

⇒ 在「找 100% 方案」的前提下，不能把视频控制台当作唯一通道：先查 UART（官方首选、代价最低），查不到再考虑移植 NativeUfs 日志窗口；视频控制台的几何问题单独定案。

## 5 附带发现：`BootArgs.h` 是 Darwin 22 形状，27 内核要 Darwin 23

已记入 `docs/engineering/IOS27-FLIGHT-BLOCKERS.toml` 的 `boot-args-abi-608`，此处只记证据位置：

- 平台 `Platforms/Xiaomi/DarwinBootPkg/Driver/BootArgs.h`：`DARWIN_BOOT_LINE_LENGTH 608`、`CommandLine[608]`、`BootFlags == 0x2d0`、`MemorySizeActual == 0x2d8`、`sizeof == 0x2e0`。
- 框架 catalog `E:/iOS Port/Sources/Repos/UniXNU/UniXNU/drivers/DarwinBoot/DarwinBootPkg/Driver/BootArgs.h`：`CommandLine[1024]`、`MemorySizeActual == 0x478`、`sizeof == 0x480`。
- 27 内核 `pexpert/pexpert/arm64/boot.h`：`BOOT_LINE_LENGTH 1024`、`bootFlags` 0x470、`memSizeActual` 0x478。

## 6 UART 通道的具体位置（live FDT，2026-11-02 dump）

`/mnt/e/iOS Port/Work/reports/live-6033dbec-fdt.dts`：

- 头顶 `chosen` 节点第 17 行：`stdout-path = "/soc/qcom,qup_uart@99c000:115200n8"` —— **bootloader 的 stdout 就是这颗 UART，115200 8N1**。
- `/aliases` 第 422 行：`serial0 = "/soc/qcom,qup_uart@99c000"`；第 423 行 `hsuart0 = "/soc/qcom,qup_uart@894000"`。
- 节点本体（第 12604–12619 行）：

  ```
  qcom,qup_uart@99c000 {
      compatible = "qcom,msm-geni-console";
      reg = <0x99c000 0x4000>;
      reg-names = "se_phys";
      interrupts = <0x00 0x260 0x04>;   /* GIC SPI 608, level high */
      clock-names = "se-clk", "m-ahb", "s-ahb";
      clocks = <0x24 0x64>, <0x24 0x86>, <0x24 0x87>;
      pinctrl-names = "default", "sleep";
      pinctrl-0 = <0xc2>; pinctrl-1 = <0xc3>;
      qcom,wrapper-core = <0xc4>;
      status = "ok";
  };
  ```

- 同树还有 `sbu_uart_en_ctrl`（第 4557 行起，`uart_audio_en_*` 引脚）与 `qupv3_se7_2uart` 的 active/sleep 引脚定义 —— 这条 UART 是 USB-C SBU 上复用的那条（K60 的工厂调试口），不是普通排针。

结论：UART 通道在设备树里是**完整且已启用**的（bootloader 已把它设成 stdout），但它物理上经 USB-C SBU 复用，需要确认是否需要专用转接板才能引出；这是「能不能拿到 UART」的唯一未定项，不再是「设备树里有没有 UART」的问题。

## 7 sheng 的视频输出也不是「PE 文本控制台」

`UniXNU-sheng/porting.toml` 的 `[[area]] id = "display"` 一节：

- `status = "implemented"`，`components = ["GopFramebuffer"]`，`paths = ["package/*Display*", "package/*Framebuffer*", "package/*Backlight*", "package/AppleARMBacklight.cpp", ...]`；
- `configuration` 第一条：`Select GopFramebuffer; CONFIG_XNU_NATIVE_LEGACY_DISPLAY=y`；
- `procedure` 第一条：`Verify GOP address, dimensions, stride and pixel layout before enabling presentation.`；
- `completion`：`A known frame appears with correct geometry and colors, then userland presentation and backlight controls work.`

即：sheng 的屏幕输出来自一整套 **GopFramebuffer + 后期 display 归档**（`package/LegacyDisplayProbe.cpp` 等），不是 XNU 的 `PE_initialize_console(kPETextMode)` 文本控制台。它的「屏幕上能看到东西」与本项目当前尝试的 `0543/0552/0577` 不是同一条技术路线。

⇒ 本板族（SM8550/SM8475 + 同一套 UEFI GOP）上，已被证明能工作的早期通道只有两条：**物理 UART** 与 **UFS 分区日志**。视频通路要工作，前提是先有 GopFramebuffer 这一层（sheng 的 `CONFIG_XNU_NATIVE_LEGACY_DISPLAY`），而不是只把 PE 文本控制台指向 `Video[0]`。

## 9 用户裁决（2026-11-23 21:36）：没有 UART 硬件

用户明确回答「没有UART硬件」⇒ 官方 log-capture 在 XNU 入口阶段允许的两条通道里，**UART 这条在本机不可用**，只剩「屏幕诊断」。

这改变三条通道的排序：

| 通道 | 状态 | 结论 |
| --- | --- | --- |
| UART（0x99c000, 115200n8） | **无硬件**（用户确认） | 排除，不再作为方案 |
| 屏幕诊断（内核文本控制台） | 洋红只覆盖右半、串口 0 字节；本板族无先例 | **唯一剩下的入口通道**，必须先证明几何/扫描缓冲 |
| UFS 分区日志（sheng `BootLog.c`） | 先例完整，但它写的是 **userdata 最后 32 MiB** | **不能直接照搬**：K60 的 userdata 是 Android 分区，写进去就是破坏 Android 数据 |

因此 sheng 的日志方案只能以「在我们自己的 unixnu 分区内预留日志窗口」的形式移植，而那要改三窗口布局与镜像构建（Data/SystemOS 之外的保留区），属于构建期变更，冻结解除前不做。

下一步（离线）：把「屏幕诊断」这条路做成可判定——用固件菜单（已验证能正常显示）在启动前把 GOP 的 `HorizontalResolution`/`VerticalResolution`/`PixelsPerScanLine`/`FrameBufferBase` 打到屏幕上，再由内核的 `Video[]` 对照，确定内核文本控制台的几何是否与面板一致。这是唯一不需要动存储布局的入口通道。

## 10 现场照片的像素级判读（2026-11-23 21:40，证据 m63053）

重新取出用户 2026-11-22 的现场照片（`m63053-e4027cca.jpg`，870×1803）逐块看，之前的文字描述「洋红在右、左边黑」并不完整。真实画面是：

- **洋红是纯 `#FF00FF`**（红+蓝满值，绿为 0），不是渐变、不是面板坏线；
- 形状是**一组横向条带**：左侧从约 x≈110 px 开始，右端参差不齐（有的到 x≈800，有的只到 x≈500），条带之间有黑色间隙；屏幕最上方还有一块阶梯状的洋红大块；
- 条带宽度大多在 30–40 px（照片坐标），间距不规则；
- 没有任何文字、没有图标、没有「绿色交接条」。

这组特征排除了三个假设：

1. **不是「内核没写进去」**：`#FF00FF` 只可能来自我们写的 32 位 BGRA 值 `0x00FF00FF`（magenta），说明内核的写确实到了面板。
2. **不是「纯几何偏移」**：纯基址/行宽偏移会产生连续整块或对角斜纹，不会产生这种「每行长度不同、右端参差」的条带。
3. **不是面板坏线**：颜色纯、边界锐利、位置与内核写入模式相关。

剩下最符合的解释是**步长/像素格式错配**：内核按 `Video[2]`（GOP 的 `PixelsPerScanLine × 4`）逐行写 `v_rowbytes/4` 个 32 位字，而面板/DPU 实际按另一种 stride 或 bpp 扫描，于是「每行写了一部分、其余被下一行覆盖或跳过」，形成参差条带。

判据（下一次能看到屏幕时，一张照片即可定案）：`0556` 的四象限图（左上红/右上绿/左下蓝/右下白 + 原点 64×64 黄）——

| 照片结果 | 结论 | 修法 |
| --- | --- | --- |
| 四块颜色各就各位、边界贴屏 | 几何与格式都对，问题在文字路径 | 查 `vc_initialize` 的字体/光标 |
| 四块颜色对但只占半屏/有重复 | stride 错配 | 改 `Video[2]` 或内核 `v_rowbytes` |
| 颜色错位（红绿互换等） | 像素格式错配（BGRA vs RGBA/565）| 改 `v_depth`/格式或面板配置 |
| 仍是洋红条带 | 我们写的填充根本没生效，洋红另有来源 | 追 0556 之前的写入者 |

这张照片把「屏幕诊断」这条唯一通道从「完全未知」推进到「只剩一个二选一的判据」，但**仍不足以直接改代码**——需要那张四象限照片。

> **另一种同样成立的读法（不能排除）**：条带的间距约 55 px、左边界整齐、右端参差，也符合「文本控制台以 `k60_fontscale=3` 渲染出巨大的方块字形」——即内核其实在打字符，只是字体/缩放让每个字变成实心块。若成立，说明文本控制台**已经工作**，问题只在字体与缩放，而不是 stride。
>
> 两种读法的判别同样是那张四象限照片：若四象限正常，则条带是字形；若仍条带，则不是字形。

