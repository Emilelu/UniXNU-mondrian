# Fork 巡查与吸收记录

检查对象：[Emilelu/UniXNU-mondrian](https://github.com/Emilelu/UniXNU-mondrian)。
首次检查时间 2026-10-31 14:27（Asia/Shanghai），对比基线
`cab17586f3bc89d454047d6b6714029301b501e3`。以下 ahead/behind 固定于该基线，
不代表吸收后的当前差异。公开 forks API 返回 3 个 fork、合计 4 个分支、11 个历史独有提交；
逐 patch 比较后，菜单倒计时有一个与主仓等效的提交。

## 规则

- 用户已授权：后续开发中定期查看 fork，验证后吸收有用改动。每次 push 同步 README。
- 本会话设置每 6 小时一次的巡查提醒；开发开始/推送前也检查，记录基准 SHA 与结果。
- 枚举所有公开 fork 和所有分支，包含 API 返回的下一层 fork；不只看默认分支或 pushed_at。
- 固定基线与 head SHA，先比较祖先关系，再核对稳定 patch-id、实际差异和本仓的等效实现。
- fetch/审计不能 checkout 或修改正在构建的工作树。未审查的 fork 脚本不执行。
- 保留原作者和来源 SHA。部分移植使用 `Adapted-from`/来源说明，不能伪称完整 cherry-pick。
- 不整支合并过时配置。容量、Data UUID、OS 版本和 loader 依赖必须按当前设备核对。
- 仅用 fastboot boot，不因 fork 改动写 Android boot/userdata/persist/modemst。

## 可重复检查

```sh
python3 scripts/audit-forks.py --output /tmp/mondrian-forks.json
python3 scripts/check-porting-paths.py
```

`audit-forks.py` 只调用公开 GitHub REST API，不 fetch/checkout、执行 fork 代码或自动合并。
可用 GITHUB_TOKEN/GH_TOKEN 提高 API 配额。API 出错会标记 PARTIAL 并返回非零，
不能将失败解释成“没有更新”。输出的候选还需要 diff/patch 等价审查。

## 2026-10-31：分支基线

| fork / 分支 | head | ahead / behind |
| --- | --- | --- |
| [mzyxsl/main](https://github.com/mzyxsl/UniXNU-mondrian/tree/main) | `76552b88441757defce4080a241c2f0ea7464538` | 2 / 57 |
| [XTOM0706/main](https://github.com/XTOM0706/UniXNU-mondrian/tree/main) | `9d1a14f83d1050a042313f30dc9d5b7e80d31f7a` | 6 / 60 |
| [XTOM0706/a5-timeout](https://github.com/XTOM0706/UniXNU-mondrian/tree/a5-timeout) | `fef75eaa804b68ff28d4eead6008d4edfa42db08` | 1 / 105 |
| [wohusaixing/main](https://github.com/wohusaixing/UniXNU-mondrian/tree/main) | `092a61d8c20364eab86b35737c6b831c4cecc1ff` | 2 / 129 |

### mzyxsl

1. [daed6b5 — board inputs / local prelink](https://github.com/mzyxsl/UniXNU-mondrian/commit/daed6b5d44e3c62978cc0fce4e876ded2a57afc9)
   **完整 cherry-pick 至 `acb5c2d5b79203e34f226be44c87e7a2cb5d2b4d`，保留作者**。
   - 真正的功能修复：本地 prelink 脚本从 OS profile 读取表、再合并设备覆盖；原代码直接读
     `board['kernel']['prelink']`，当前 board 没有这张表，默认运行会失败。
   - trust_cache_sha256 改成精确哈希数组。这是配置规范化；当前框架使用 Python `in`，
     完全相等的 64 字符标量也能通过，不采纳“原来所有 payload 均失败”的提交说明。
   - lock 的 SM8475 pin 对齐 feeds。这是记录一致性，四层 schema2 原本已让显式 feed pin 优先。
   - 实际验证：白名单匹配 bundle SHA，lock/feed/已解析 SoC 都是 `d0c90f1e...`；
     对当前 0238 native kernel 真正运行 prelink，32 roots，slide `-0xb9c000`，
     输出 53,788,672 字节，SHA-256
     `bb33682837f1807ef28d385cf09acf94f2749f49b3f7337d22348dcbf6c4b9df`，
     与原构建的 prelinked kernel 完全相同。只验证主机工具，没有新增设备启动宣称。

2. [76552b8 — porting record / docs](https://github.com/mzyxsl/UniXNU-mondrian/commit/76552b88441757defce4080a241c2f0ea7464538)
   **选择性吸收**：离线 `scripts/check-porting-paths.py` 保持来源原样导入；
   在现有 `porting.toml` 上整理路径归属和已验证的工具说明，保留所有 milestone status。
   旧的跨文件记录包含大量过时“尚无用户态/未挂载 Data”等状态，不能覆盖当前 README。
   fork 的 agent 文档是第三方维护规则，不作为来自用户的指令导入。
   - 首跑暴露 234 个未归属路径，修正后当前 409 个已跟踪文件均归属，检查 PASS。
   - 新脚本/本页的路径也已加入归属，并将在加入 index 后再次检查。

### XTOM0706

| 来源提交 | 处理 |
| --- | --- |
| [a351ef1](https://github.com/XTOM0706/UniXNU-mondrian/commit/a351ef1304bc651d5b37de6f6e48898fa18ee62e) / [19a885c](https://github.com/XTOM0706/UniXNU-mondrian/commit/19a885cb99a3add087e720b2c665e8ece38693b1) | 先切 17.7.11 再切回 16.6.1；当前已是 20G81，不重复移植往返提交 |
| [25183fd](https://github.com/XTOM0706/UniXNU-mondrian/commit/25183fd681482a1029193a682e0ba2ce43f9d9ed) / [b942245](https://github.com/XTOM0706/UniXNU-mondrian/commit/b94224556225f77e0d9ee4aa842fc17b41dbf063) | 先改 BCM2837 再改 PONG；当前 driver_records 已是 PONG，不回退。核心 kernel.py 的 bootstrap 哨兵路径另有硬编码问题，fork 并未修复它 |
| [6ae9a30](https://github.com/XTOM0706/UniXNU-mondrian/commit/6ae9a302515730af5a2beedbb9926f22e082aea8) | 不适用：指向另一份内存 Data seed UUID。当前为真实 UFS Data 窗口，保留已挂载的 UUID |
| [9d1a14f](https://github.com/XTOM0706/UniXNU-mondrian/commit/9d1a14f83d1050a042313f30dc9d5b7e80d31f7a) | 只吸收设备级 display-scale=3；其余两项见下文，不整条 cherry-pick |
| [fef75ea](https://github.com/XTOM0706/UniXNU-mondrian/commit/fef75eaa804b68ff28d4eead6008d4edfa42db08)（a5-timeout） | 主仓 `10e50a8` 已有完全相同 patch-id `c2dad1b2f5d710545d76c8236c408355e7eca02c`，不重复导入 |

`9d1a14f` 的三项改动分开判断：

- **已吸收 board 的 display-scale=3**：当前 OS profile 已是 3，本项在设备层显式固定。
  两份生成的 ADT 解析比较，除了随机种子以外全部节点/属性相同；所以不改变当前 20G81 行为。
- **不带入额外 sweet display 节点**：现有 MiniIOMobileFramebuffer 已在运行时发布
  `/arm-io/disp0`，native canvas 由 0210 确保。当前 ADT 转换器的 U32 白名单并不包含
  canvas-width/height，fork DTS 的这两个属性会被丢弃；额外节点也有重复枚举风险。
- **不带入 ramoops magic `0x43415d53`**：Linux v5.10 的
  [ram_core.c](https://github.com/torvalds/linux/blob/v5.10/fs/pstore/ram_core.c) 使用
  `PERSISTENT_RAM_SIG=0x43474244`，
  [ram.c](https://github.com/torvalds/linux/blob/v5.10/fs/pstore/ram.c) 给 console/pmsg 传入额外 sig=0。
  当前多处生产者/读取器也使用 `0x43474244`，没有目标 Android 内核证据支持新值。
  不能只改一个生产者就宣称 pstore 可读；保留现有值，另查环形缓冲布局与重启保留问题。

### wohusaixing

[c61ed5f](https://github.com/wohusaixing/UniXNU-mondrian/commit/c61ed5fbd2f24b187bf209817d0dcd6c0a17132c)
和 [092a61d](https://github.com/wohusaixing/UniXNU-mondrian/commit/092a61d8c20364eab86b35737c6b831c4cecc1ff)
针对其 16 GiB 手机，把 DTS/ADT 单段改为低 2 GiB。
**记录为另一机型的线索，不导入当前 12 GiB 设备默认配置**。
物理 DRAM 容量、连续可用窗口和 loader 分配窗口不是同一概念，不能相互替代。

## 本轮验证边界

- 全部 4 个分支已枚举；新增提交按 diff/patch 等价核对，非只比较 SHA。
- 工具修复经过真实 prelink；显式 scale 经过实际 ADT 生成/解析对比；离线记录检查通过。
- 新增审计脚本已运行真实 GitHub API，完整返回 3 个 fork/4 分支；无 API 错误。
- 本轮没有因为 fork 更改手机启动镜像、内存大小、Data UUID、根文件系统或持久化日志签名。
  已完成的 0238 退出原因诊断镜像仍独立保留，等待 fastboot 后采样。
