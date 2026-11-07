# route-a-18 里程碑：darwin24 内核在 Linux 上编译成功

**2026-10-31 20:58**，本项目第一颗 iOS 18 (darwin 24) 内核构建完成。

## 产物

```
mach.development.pong.unstripped.noctf
  size    20,847,560 bytes
  sha256  57b01c6476e3398d2f7a18bc9e096db18f41eed1012bf146ffd64879ff1ac024
  Mach-O  magic 0xfeedfacf, cputype arm64 (0x0100000c), MH_EXECUTE, 25 load commands
  来源    xnu-11417.140.69 @ 43a90889846e00bfb5cf1d255cdc0a701a1e05a4
  补丁    pong 聚合补丁 0001-pong-darwin24.patch (12,396 行，单次 apply)
  宿主    Linux (WSL Ubuntu-24.04)，/opt/unixnu-linux 工具链
```

## 九个必须解决的问题（每个都曾是硬失败）

| # | 问题 | 解法 |
|---|---|---|
| 1 | 树布局 | pong 期望 `refer/ipados18/<name>` 检出；`--no-checkout` 克隆后必须真正 checkout |
| 2 | 聚合补丁 | 单文件 12,396 行，一次 apply 到 xnu-11417 |
| 3 | MACHINE_CONFIG | **darwin24 白名单是 PONG**，不是 darwin22/23 的 BCM2837（`MakeInc.def:32`） |
| 4 | PLATFORM | 必须 `PLATFORM=iPhoneOS`，否则报 `Unsupported PLATFORM <路径>` |
| 5 | availability.pl | `AvailabilityVersions-143.7` 装进 fakeroot；`make_symbol_aliasing.sh` 在 installhdrs 里就调用它 |
| 6 | fakeroot SDK | libplatform 头 + libdispatch `os/*.h` 经 `unifdef -DKERNEL=1` 生成 firehose 头 |
| 7 | libcc_kext.a | **必须为本机 LLVM 现编**，不能借用 16.6.1 的：PGO 运行时提供 `OSKext.cpp` 需要的 `___llvm_profile_*` 三下划线符号 |
| 8 | LD_KERNEL_ARCHIVES | 传给 make 的变量名是这个（不是 `KERNEL_EXTRA_ARCHIVES`），且会**替换**默认列表——必须自己带上 `-lfirehose_kernel` |
| 9 | LD_KERNEL_LIBS | `libcc_kext.a` 通过这个变量进链接（16.6.1 脚本同款） |

## 说明

- `pong_ramoops_diagnostic_write` 由本地 750 字节的 freestanding 源提供（`libRouteA18Support.a`），
  转发到 `kprintf`。真实实现在 PongPlatform24 套件归档里，我们尚未构建；这样聚合补丁保持字节不变，
  溯源完整。
- 可复现脚本：`k60-work/build-darwin24-linux.sh`（九步，带幂等检查）。

## 下一步

1. K60 面板参数（1440×3200 DSC）替换 pong 的 1080×2412
2. DarwinBoot24 + ADT（K60 内存布局与 unixnu 分区几何）
3. prelink + payload 打包 → fastboot boot 到控制台输出
