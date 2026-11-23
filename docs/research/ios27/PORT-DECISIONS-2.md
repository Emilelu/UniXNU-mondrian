# 七项「必须补」清单的收口 — 2026-11-23

来源：`E:/k60-work/scratch/parity-expand-report.md`（9 来源 1460 条账本）。

| # | 条目 | 处置 | 证据 / 提交 |
| --- | --- | --- | --- |
| 1 | qsort bounded recursion（zizhan `0003`） | **已抄** `0572` | `git apply --check` rc=0；`UniXNU-zizhan 034a0b0`；提交 `4e7d5045` |
| 2 | native-4k-bootstrap-capacity | **已抄** `0574` | 来自我们自己 16 线；27 base 缺 16 页分支；rc=0；提交 `76b6ca0d` |
| 5 | zzx-pmap-sync-64bit-pa | **已抄** `0573` | 16 线已有、27 base 仍是 `pp << PAGE_SHIFT`；rc=0；提交 `76b6ca0d` |
| 4 | source-corecrypto14-bootstrap | **not-applicable** | 27 feed 里 `grep -rn corecrypto_kext_start osfmk bsd libkern` = 0 命中，`configs/mondrian_ios27_defconfig` 也没有 `XNU_SOURCE_CORECRYPTO14` 键 ⇒ 27 的 corecrypto 引导走另一条路，16 线那套「给无 bootstrap 的树补调用」在这里没有落点 |
| 3 | trust-cache defer-img4（+ ready-guard） | **deferred** | 27 的 `bsd/kern/kern_trustcache.c` 1,350 行且已含 `#include <libkern/img4/interface.h>`（`:37`）、`<img4/firmware.h>`（`:48`）、`img4if` 判空（`:128`）、五参 img4 签名（`:165-181`）；16 线四补丁对它 `apply --check` 全 FAIL（形态不同，不是锚点漂移）。必须在 27 的 img4 路径上重新推导，**非 stage-0 阻塞** |
| 6 | `0306` console snapshot | **deferred** | 依赖 `k60_console_export.c`/`k60_usblog.c`，现由 `0548`/`0547` 提供，但「上一次启动日志」能力在 stage-0 已有 `0546` ramoops + `0554`/`0556` 帧缓冲见证 + `-enable_kprintf_spam` 覆盖；再叠一条 console 起之前的写入路径收益低、风险高 |
| 7 | `0331` prevlog replay | **deferred** | 同上；`arm_init.c:281` 锚点不存在，需按 `0546` 现锚点重切；stage-0 不需要 |

## 判定规则（本轮新增，写给后来者）

「能 `git apply` 就抄」是错的。本轮三次证明：

1. **能 apply ≠ 能链接**：`0564` 调 `native_adreno_connect_granted` 而树里无定义 ⇒ `0571` 补。
2. **能 apply ≠ 会生效**：`0558`/`0559` 的开关被 `board.toml` 冲掉 ⇒ 补 `-uketextconsole`/`-ukedeferredconsole`。
3. **能 apply ≠ 该抄**：`kern_exec.c` 段与 `0562` 完全重复；trust-cache 四补丁对 27 的文件形态不适用。

判据顺序固定为：**先看这个机制在本树存不存在（符号/文件/宏）→ 再看重复 → 再看 apply → 最后看编译与链接**。
