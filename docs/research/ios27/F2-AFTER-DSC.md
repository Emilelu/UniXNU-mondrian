# 补上 DSC 集成后的一次飞行：判据先写

日期：2026-11-21
镜像：`bootimg` 用新固件卷 `SILICIUM_UEFI.fd` sha256 `e0e56979e6b331ea395e5034…`（旧 `d56ea4c9…`）重打
依据：`porting/uefi-firmware.md#required-integration`（六模块 + 两库映射），`guide/debugging.md#green-bar`

## 为什么飞这一张

三张黑屏图的共同点已经收敛到固件层：加载器接受我们的 fileset 入口（`0xfffffff00ad96488` 在
`__TEXT_EXEC` 文件范围内，`Member.Entry == Kernel->Entry` 成立），串口 gadget 符号在
（87 vs 16.6.1 的 170），对照图（旧固件卷 + 16.6.1 内核）串口与 `K60AUTORESET` 都正常。

同时新门禁对官方 `#required-integration` 复核出 4 项缺失：`DiskIoDxe.inf`、`Fat.inf` 不在 DSC
`[Components]`，`HobLib`、`FdtLib` 没有映射。已在 `uefi-mondrian` `f2abb98` 补齐，固件卷重建成功，
`AARCH64/DiskIoDxe.efi`（20,992 B）、`Fat.efi`（45,568 B）都在 11:55 产出。

## 判据（先写后飞）

| 观察 | 判定 |
| --- | --- |
| 屏幕出现 UniXNU 菜单或顶部绿条 | 固件层通了 ⇒ 黑屏确实是集成缺口；接着按 `#green-bar` 第 1 步记 `DARWINBOOT:` 日志 |
| 屏幕仍全黑，但设备 6 s 后自己回 fastboot | 入口探针第三阶段（MMU 已开）在跑 ⇒ 用复位时刻作检查点 |
| 屏幕仍全黑，设备静默挂死 | 固件层仍有缺口 ⇒ 按 `#green-bar` 第 2 步要入口探针，但探针的 `PANIC_VA = 0xFFFFFFF00BF69B04` 是参考内核的 `_panic`，必须先按本内核 `_panic` 地址参数化 |
| 串口有日志 | 直接按日志读阶段，同时修正 `F2-AFTER-INVALID.md` 的「唯一 console 是 USB CDC-ACM」推断 |

## 入口探针的前置（官方 `#green-bar` 第 2 步的「支持的内核」）

`scripts/patch-xnu-entry-probe.py:45` 写死 `PANIC_VA = 0xFFFFFFF00BF69B04`，注释说明它为参考内核
固定；我们的 27 内核 `_panic` 地址不同，所以 `[payload] panic_screen = true` 会被拒。要按官方第 2 步
走，先把该地址改成按内核符号表解析（我们能离线从 `kernel.macho` 的符号表读出 `_panic`），这不改变
探针逻辑，只是把「参考内核坐标」换成「本内核坐标」。

## 结果（2026-11-21 12:06）

飞行 `boot.img` sha256 `0cff417833bd59b0bb64f826…`（新固件卷 `e0e56979…`，补齐官方六模块 + 两库映射）：

- `fastboot boot` 成功（`Sending 197164 KB OKAY`、`Booting OKAY`）。
- 串口仍然 `port-not-observed`、`bytes=0`、`complete=False`；150 s 内 `returnedToFastboot=False`。
- 之后 `fastboot devices`、`adb devices`、`Get-PnpDevice`（`VID_18D1|VID_1209|VID_05C6`）全部为空。
- 用户确认屏幕：**全黑，什么都没显示**。

⇒ 补齐 DSC 集成**没有**让固件界面起来。下一格是单变量 A/B：用**已知能起界面**的旧固件卷
`cf448571…`（3,145,728 B，`E:\k60-work\artifacts\old-fd-cf448571.fd`）+ 同一个 27 payload 打一张图，
`E:\k60-work\artifacts\f2-oldfd\boot.img`（201,887,744 B）。

判据：旧卷 + 27 payload 出现绿条/菜单 ⇒ 问题在新固件卷（PE 或卷内容）；仍然全黑 ⇒ 问题在 payload 侧
（27 内核在固件读取 payload 之后、界面绘制之前就出事），此时才轮到入口探针。

## 纪律

- 只 `fastboot boot`，永不 flash、不写 `/dev/block/sda38`。
- 每次飞行前写完判据；0 字节按 INVALID 处理，同镜像必须重跑一次。
