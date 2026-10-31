# 双系统分区（安卓 + UniXNU）

官方实验性方案：`UniXNU/scripts/dual_sys/partition.py`。它通过 ADB 识别布局，
**在线缩小 F2FS，再在 userdata 尾部创建 `unixnu` 分区**，保留 userdata 的起始、
类型、GUID 和属性；新块设备为 `/dev/block/by-name/unixnu`。安卓 `/data` 保留。

## 硬前提

- TWRP recovery：root ADB、能解密 `/data`、recovery 内核支持
  `F2FS_IOC_RESIZE_FS` 在线缩容。
- F2FS：4 KiB 块、512 块 segment、每 section 一个 segment、checkpoint 开启。
- `userdata` 是最后一个已占用分区；有空闲 GPT 项；尚无 `unixnu`。
- 主/备 GPT 一致；512/4096 逻辑扇区；常规 128 字节分区项。
- recovery 内有 `sh`/`dd`/`blockdev`/`sha256sum`/`cmp`/`readlink`/`sync`/`umount`。

K60（mondrian）有第三方 TWRP 3.7.1_12 v8.6 A14 / OFRP 设备树，但**必须先验证**
其 F2FS 在线缩容与解密能力。先跑只读 `partition.py inspect`，不要直接 apply。

## 流程

1. **备份**：重要文件拷到 PC；可选把 `userdata`/`metadata` 离线 dd 到另一块磁盘
   （TWRP 文件级备份可能缺加密元数据）。分区备份不能替代文件备份。
2. 进 TWRP，确认 root ADB、解密并挂载 `/data`，关闭 MTP。
3. `python3 scripts/dual_sys/partition.py inspect`（只读）——确认布局受支持。
4. 交叉编译 AArch64 静态 helper：
   `aarch64-linux-gnu-gcc -static -O2 -Wall -Wextra -Werror scripts/dual_sys/f2fs-shrink.c -o out/dual_sys/f2fs-shrink`
5. `partition.py plan --size-gib <N> --helper ... --output out/dual_sys/preview`；
   审阅 `plan.json`/GPT，保留整个输出目录。
6. **用户确认后**才 `apply`；执行期间保持供电，不操作 TWRP。
7. `reboot recovery` -> `partition.py verify` -> 确认文件可读 -> 重启安卓验证。
8. `unixnu` 尚未格式化。配置 K60 的 UFS/Data/root 指向
   `/dev/block/by-name/unixnu`；**默认构建命令可能仍指向安卓 userdata**，写前核对。

## 风险

- 实验性；脚本不自动重试/回滚。F2FS 缩容中断、GPT 写一半都可能损坏数据。
- 恢复 GPT 不能撤销 F2FS 数据迁移；完整恢复需原分区容量 + 匹配的 metadata 备份。
- Data 无法读取时不要格式化；先保存 stage/dmesg，由设备维护者判断。

官方文档：https://unixnu.com/zh/porting/dual-system-partition


## unixnu 内部 Data 空间（2026-10-31 补充）

双系统外层 unixnu 已有 32 GiB，不代表其内部 APFS Data 可用 32 GiB。
最近历史安装：OS 4.746 GiB、SystemOS 2.482 GiB、Data APFS 256 MiB
（7420 MiB 偏移、GPT 窗口 258 MiB）；窗口之后约 24.502 GiB 尚未利用。
该历史清单未做设备读回，实际修复前必须从 recovery 重新获取布局与当前 Data 副本。

用户日志已确认 Data APFS 写事务 ENOSPC。只读备份和保留旧卷的 22 GiB Data 预案见
[DATA-SPACE-2026-10-31.md](DATA-SPACE-2026-10-31.md)。不需再次缩 Android F2FS；
不得把旧首次安装/replace-existing-data 脚本当作保留数据的 APFS 扩容器。
