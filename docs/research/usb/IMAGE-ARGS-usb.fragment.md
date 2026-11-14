# 交给 gates 线合并：`k60_usbvend` 的镜像参数白名单 + BOOT-ARGS 行

> 提出者：usb-agent（k60-usb），2026-11-14。触发：`0410-k60-usb-vendor-loopback.patch`（commit `0160785`）
> 新增 boot arg `k60_usbvend`。它写在**补丁**里而不是 `drivers/`，所以 `scripts/check-boot-args.py`
> 扫不到、不会红；但 `k60-lead/scripts/check-image-args.py` 的 `ALLOWED_ADDITIONS` 是硬名单，
> 任何带 `k60_usbvend=2` 的实验镜像会被 `image-arg-audit: REFUSED` 拒掉。

## 1. 症状（实测）

`python3 /mnt/e/hackios/k60-lead/scripts/check-image-args.py --image <带 k60_usbvend=2 的 boot.img>`

```
image-arg-audit: REFUSED
  - argument k60_usbvend is not in board.toml kernel_args and is not a declared addition (ALLOWED_ADDITIONS in this gate)
```

判定逻辑（`check-image-args.py:150-156`）：镜像里出现、但 `board.toml` 的 `[payload].kernel_args` 里没有的参数，
必须在 `ALLOWED_ADDITIONS` 里，否则报错。`k60_usblog` 已在 board.toml 里（所以它不需要进白名单），
`k60_usbvend` 是本线新加的、刻意不进 board.toml 的实验开关，因此需要白名单。

## 2. diff 1：`scripts/check-image-args.py` 白名单加一项（`k60-lead` 仓）

```diff
--- a/scripts/check-image-args.py
+++ b/scripts/check-image-args.py
@@ -44,7 +44,7 @@
 ALLOWED_ADDITIONS = {
     "pong_wifi", "k60_wifi_rsc", "k60_wifi_stage", "pong_wifi_dma_mib",
     "pong_wifi_diag", "pong_wifi_test", "pong_wifi_alt", "pong_wifi_band",
     "pong_wifi_cycle", "k60bt", "k60bt_stage", "k60bt_warm",
     "pong_audio_probe", "pong_rail_probe", "pong_adsp", "pong_touch_se",
-    "sheng-gpu-addon",
+    "sheng-gpu-addon", "k60_usbvend",
 }
```

（`:42-43` 的注释已经要求「每个进白名单的名字也必须在 `docs/engineering/BOOT-ARGS.md` 里登记」，
所以第 3 段是配套动作，不是可选项。）

## 3. diff 2：`docs/engineering/BOOT-ARGS.md` 加一行（k60-usb 仓，5 列格式）

插在 `k60_usblog` 那行（`:34`）之后：

```diff
--- a/docs/engineering/BOOT-ARGS.md
+++ b/docs/engineering/BOOT-ARGS.md
@@ -34,2 +34,3 @@
 | `k60_usblog` | 调试 | 0/1/2 | 代码默认 | `0300-k60-usblog-ep0.patch` USB 日志级别 | 刷机时的主要日志通道 |
+| `k60_usbvend` | 调试 / USB | 0/1/2 | 0（= 0409 原样） | `0410-k60-usb-vendor-loopback.patch`：0 = 67 字节两接口 CDC-ACM、无回环；1 = 98 字节复合描述符（IAD + IF2 vendor 0xff/0xfe，EP 0x03 OUT / 0x83 IN）+ EP6→EP7 回环；2 = 控制台描述符不变、回环跑 CDC 数据对 EP2→EP3（普通 COM 口可验） | mode 1 的 IF2 主机侧没有驱动，要用 libusb 直接开；mode 2 必须同时开 `k60_usblog`（控制台让位给回环） |
```

## 4. 字节预算（608 上限）

`usb-20261114h`（mode 0）实测 `image-arg-audit: OK (29 arguments, 575 bytes)`。
加 `k60_usbvend=2` 是 +15 字节 = **590 字节**，距离 `DARWIN_BOOT_LINE_MAX = 607` 还有 17 字节余量，
与 `BOOT-ARGS.md:7` 记的「591 字节、余 17」同一个量级。**不需要为它腾别的位置。**

## 5. 为什么 `check-boot-args.py` 不会红（不需要改）

`scripts/check-boot-args.py:47` 只扫 `drivers/**/*.{c,cpp,mm,h}` 里 `PE_parse_boot_argn("…")` 的字面量，
`k60_usbvend` 的解析写在 `patches/usb/0410-k60-usb-vendor-loopback.patch`（打补丁进 `bsd/dev/k60_usblog.c`），
源码树 `drivers/` 里没有它 ⇒ 这个门禁看不见它。这是**已知盲区**，不是本线的绕过：
两种做法都可以（把解析挪进 `drivers/` 需要重排补丁），本线选择保留在补丁里、用 image-arg 白名单兜底。

## 6. 合并后的验证命令

```bash
# 1) 白名单生效（用已有镜像 + 手工核对的参数集，或用新构建的 usb-20261114h2）
python3 /mnt/e/hackios/k60-lead/scripts/check-image-args.py \
  --image /mnt/e/k60-work/artifacts/usb-20261114h2/boot.img
# 期望：image-arg-audit: OK (30 arguments, 590 bytes)

# 2) 文档一致性
cd /mnt/e/hackios/k60-usb && PYTHONIOENCODING=utf-8 python3 scripts/check-docs.py
```

## 7. 三档语义（写进 BOOT-ARGS 的依据）

| `k60_usbvend` | 描述符 | 回环端点 | 主机侧怎么验 |
|---|---|---|---|
| 0（默认，未设） | 67 字节 / 2 接口 CDC-ACM（= 0409） | 无 | 与 usb-20261114g 完全相同，做 A/B 对照 |
| 1 | 98 字节 / 3 接口：IAD + IF2 vendor（0xff/0xfe），EP 0x03 OUT / 0x83 IN（= 0406 复合布局） | EP6 OUT 收 → EP7 IN 发回 | IF2 没有系统驱动，需 libusb/IOKit 直接开接口 |
| 2 | 67 字节 / 2 接口 CDC-ACM（控制台让位） | CDC 数据对 EP2 OUT 收 → EP3 IN 发回 | 普通 COM 口即可，`docs/research/usb/echo-test.ps1` 逐字节回显判定 |

mode 2 的存在理由：本机 Windows 侧没有 pyusb/libusb/gcc（只有 `WinUSBCoInstaller2.dll`），
mode 1 的裸接口验证需要另找主机工具；mode 2 用系统自带 usbser 驱动就能做端到端回环，
是 0410 的**首选判据**，mode 1 是描述符侧的对照实验。
