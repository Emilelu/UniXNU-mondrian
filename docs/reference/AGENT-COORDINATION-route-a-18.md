# 协作日志（route-a-18）

> append-only。每条一行，带时间戳与产物引用。新条目追加在末尾，不改旧条目。
> 格式沿用 `D:\Android\k60-ios\AGENT-COORDINATION.md`：
> `[作者][HH:MM][状态] 摘要 - 细节 [artifacts: ...]`

[route-a-18][02:30][DONE] 首次到达可读 panic 屏 - 0244 面包屑改画帧缓冲：ramoops 暂存页在硬挂时读不回 DRAM，改为 32x32 ARGB 方块（x=64/160/256 三列）。第三列只命中第 1 块，死点锁定 ml_parse_cpu_topology [artifacts: patches/xnu-ipados18/0244-k60-breadcrumbs.patch, docs/ROUTE-A-18-STATE.md]

[route-a-18][02:58][DONE] CPU 拓扑修复 - Android 侧实测 physical_package_id 0/0/0/0/1/1/1/2、CPU part 0xd46 x4 / 0xd47 x3 / 0xd48 x1，SM8475 是三簇；dtsi 的扁平 reg 0x000..0x700 会被 XNU 当成八个物理簇，撞 MAX_CPU_CLUSTERS=1。改 dts 为真实 MPIDR + 内核上限提到 3 [artifacts: dts/mondrian.dts, patches/xnu-ipados18/0245-k60-cpu-clusters.patch]

[route-a-18][03:45][DONE] panic 文字可读 - darwin24 补丁系列从来没带 16.6.1 的 k60_fontscale，把 0214 移植成 0246，字号 1 -> 4 [artifacts: patches/xnu-ipados18/0246-k60-console-font-scale.patch]

[route-a-18][04:30][DONE] porting.toml 回填 - pong 的 13 条 evidence 全是 kind=source；这里按官方记录规范写 host/device 证据（必须带 command 与 40 位 revision）。os_profile 从 16.6.1 改为 18.7.10-22H374，认领 9 个新脚本，check-porting-paths.py 从 10 error 降到 0 [artifacts: porting.toml, scripts/k60-device.sh]

[route-a-18][11:10][DONE] 上游生态调研 - iOS 16~27 可行性、四个仓库与 UniXNU 组织 28 仓的分支快照、可摘取件；结论不迁移 26/27（arm64e + 身份从 A13 起 + 27 的 dyld 缓存 5.95 GiB 撑爆 6 GiB 共享区）[artifacts: docs/ROUTE-A-18-UPSTREAM.md, docs/FORK-REVIEW.md]

[route-a-18][11:15][DONE] 同步机制 - scripts/k60-sync-refs.sh 覆盖 D 盘 13 仓与 WSL 侧 4 仓，fetch 不 pull，输出落后报告；首次运行即发现 ios-sweet-k60 落后 2，其中一份是同日的 iOS 26/27 评估 [artifacts: scripts/k60-sync-refs.sh]
