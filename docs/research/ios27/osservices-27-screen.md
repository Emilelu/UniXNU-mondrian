# 一页纸：iOS 27 首次飞行读屏判据（K60 / 24A446）

> 用法：boot 前把这一页放在第二块屏上，屏上出现什么就只看**那一行**，不要临场推理。
> **冻结期间（2026-11-22 03:02 起，`docs/engineering/BOOT-FREEZE.md` state=frozen）本页不执行**：任何
> `fastboot boot` 被拦，解冻条件是「同一次启动内日志通路 + 自动引导 + 看门狗自动复位」。解冻后再用。
> 状态：判据是**离线推出来的假设**，尚无一次飞行确认。第一次读到结果后回填
> `osservices-27.md §B.3` 与本页的「已确认」列。
> 证据寿命（P-307）：ramoops 在 DRAM，掉电/复位即归零 ⇒ 本页的证据只能用**屏上照片**，不要指望日志跨复位留存；
> 这也是 P-300「0 字节日志 ≠ 内核没跑」的另一半原因。
> 前提：本镜像 = stage-0（无 kext、无 root mount）；13 个静默槽位在
> `[PE_init_iokit() :806, bsd_init() :926)` 窗口内，USB 控制台尚未起来。

## 判据表

| # | 屏上现象 | 唯一结论 | 下一步命令 |
|---|---|---|---|
| 1 | 全黑，连 F2 色条都没有 | 内核**没跑到** `_start` 之后的取 `boot_args.Video.v_baseAddr` 处，或 loader 给的 `v_baseAddr == 0`（F2_BAR 首两条是 `ldr x9,[args,#0x28]` + `cbz x9,9f`，地址为 0 时一条都不画） | 先分叉：`bash scripts/k60-device.sh state`；再看这次 boot.img 的 ADT `video` 节点是否带基址 —— 这是**加载器/固件**面，转 platform27，不是本线的 13 项 |
| 2 | 只有色条：红（row 256）/ 黄（row 272）/ 青，或其中一两条 | 内核在跑；红 = `_start`，黄 = `bootstrap_tables_ready`，青 = `common_start`。缺哪条就停在哪条之前 | 记录**最后一条颜色**与行号，附 boot.img sha256；无白字 ⇒ 还没到 `PE_init_iokit()`，仍是平台/加载器面 |
| 3 | 白字出现，最后一行是 `fileset: original component called an unmapped kernel function from 0x…` | **命中 13 项之一**（或别的桩；看返回地址落在哪张表）。这是本线要的那条证据 | 抄下 `from` 后的返回地址与 x0/x1 三值；按 `silent13.toml` 的 13 个加载点比对，命中即回填 close 证据 |
| 4 | 白字出现，最后一行是 `NativePrelink: invalid early security initializer…` 或 `… outside … code` | AMFI 的 early init **没跑起来**：不是桩，是 `early_security_init` 地址/阶段/段属性不满足（`OSKext.cpp:8497-8551` 的四条件） | 转内核/打包面：核 `profile.toml` 的 `early_security_init = com.apple.driver.AppleMobileFileIntegrity=0xfffffff00921000c` 与该 kext 的 RX 段；本线只记录，不改 |
| 5 | 白字滚过 `PE_init_iokit` 之后、停在别处（apfs / AMFI 签名 / 第一个任务） | 13 项**没被触发**，失败在更后面（`vnode_check_signature`、`apfs_vfsop_mount`、trust-cache 钩子） | 13 项从"静默优先"降为"未触发但有机制"；把最后一行交给对应线，本线按 §B.9 记一笔 |
| 6 | 白字滚到 `bsd_init` 之后，USB 控制台枚举、有字节流 | 13 项**整段通过**（窗口走完没炸） | 抓 USB 日志归档；13 项仍不 close —— pass 只说明这次没调用，close 需要 §C 的六类证据之一 |

## 三条不许临场推翻的约定

1. **0 字节 ≠ 内核没跑。** USB CDC-ACM 在 `bsd_init` 之后才枚举，13 项全在它之前；判死要看屏，不看日志。
2. **黑屏两义必须分开。** 有 F2 色条 ⇒ 内核在跑，问题在内核/kext；无色条 ⇒ 先怀疑 `v_baseAddr`（加载器面）。这一条分错会把平台问题算到 prelink 头上。
3. **`fileset:` 的返回地址是原始镜像里的调用点**，不是本板地址 —— 直接拿它去 `silent13.toml` 比 `site`，不要先减 slide（`collection_slide = 0x0`）。

## 抄录清单（照抄，不要概括）

- boot.img 文件名 + sha256；`kernel.json` 的 `candidate_sha256`
- 最后一条颜色条（红/黄/青）或最后一行白字（逐字）
- 若有 `fileset:`：`from 0x…`、`x0 0x…`、`x1 0x…`
- 拍照（本板证据以照片为准）

## 回填位置

- 本页「已确认」列 + `docs/research/ios27/osservices-27.md` §B.3
- 命中 13 项时：`docs/research/ios27/osservices-27-silent13.toml` 该槽加 close 证据（授权：2026-11-21，只加证据、不动 `unreachable.toml` 审计）
- 命中第 3 行且返回地址不在 13 个加载点：说明「一个目标被 5 个 bundle 共用」的绑定错，改 `silent13.toml` 的 `bundles` 并用 `scripts/check-osservices27-silent13.py --strict` 复验
