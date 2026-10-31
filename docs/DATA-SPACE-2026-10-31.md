# Data ENOSPC 与 32 GiB 内部布局（2026-10-31）

## 已确认的错误

用户在 iOS 启动进度条停止后抄录：

```
disk5s1 launchd: ENOSPC: ttype INSERT num_blocks 121 free_blocks 1208 ... threshold_blocks 1310
... usermanagerd: ENOSPC ...
... logd_helper: ENOSPC ...
current xid: 2339 ... 2357
```

APFS 明确拒绝写事务：free_blocks 低于它要求的事务阈值。这是实际的磁盘空间问题，
不是因为统计行还在滚动就能排除的。xid 增加不等于这些 INSERT 成功或 UI 正在推进。
按历史容器的 4096 字节块，1208 块约 4.72 MiB，1310 块约 5.12 MiB。
不降低阈值，不静音 ENOSPC 来掩盖写失败。

## 外层分区不等于内部容器

历史安装清单经 SHA-256 校验，外层均为独立 unixnu：

- /dev/block/sda38，4 KiB LBA 53342976..61731583。
- 34,359,738,368 字节 = 32 GiB；Android userdata 不是本次修复目标。
- SHNGROOT 描述 OS、SystemOS、Data 三个窗口；Data 内还有 GPT 和 APFS。

| 区域 | 起点（unixnu 内） | 容量/长度 |
| --- | ---: | ---: |
| OS | 1 MiB | 5,096,113,664 B，约 4.746 GiB |
| SystemOS | 4862 MiB | 2,665,480,192 B，约 2.482 GiB |
| Data（最近历史安装） | 7420 MiB | GPT 窗口 258 MiB，内部 APFS **256 MiB** |
| Data 之后未分配给窗口 | 约 7.498 GiB 后 | 约 **24.502 GiB** |

因此 32 GiB 没有充分利用；内部小 Data 不会自动借用窗口外空白。
扩大裸文件长度、SHNGROOT 长度或 GPT 分区长度都不等于扩大 APFS 分配器。
三层容量必须一起核对。

## 历史证据：不要只看文件名

最近保存的安装记录是 `/tmp/k60-data-install-256/installation.json`，
时间 2026-10-30 23:10:14+08；比 512d 的 22:57:23+08 更晚。

| 安装记录 | 内部 APFS | GPT 窗口 | 原镜像 |
| --- | ---: | ---: | --- |
| k60-data-install-256 | 256 MiB | 258 MiB | /tmp/k60-data256-gpt.img |
| k60-data-install-512d | 512 MiB | 514 MiB | /tmp/k60-data512d-gpt.img |

两个历史镜像卷 UUID 均为 `1BCD69FF-24A5-48B1-94B6-8FE592B2F597`，所以 UUID 不能区分它们。
512d 是空 mkapfs 容器；256 是 Apple 创建的种子，原始普通文件 36 个、目录 162 个、
逻辑文件字节合计 589,907（约 0.56 MiB）。本地只读解析与清单一致，GPT 主备头和表 CRC 通过。

历史安装器没有读回校验，因此以上仍是**历史快照**；手机当前布局必须重新读取。
旧 SHNGROOT 的 image_bytes 可能保留先前较大窗口的末端，不能把它当作 APFS 容量。
此前“当前 Data 已确定为 512 MiB”的说法撤回；最新历史记录指向 256 MiB。

## 是容量太小，还是日志写满？

目前可证实：Data 当初分配很小，当前 APFS 报 ENOSPC。原始种子普通文件只有约 0.56 MiB，
运行时内容/元数据之后发生了增长，但尚未统计手机当前目录，不能断言主要来源就是日志。
两者也可能共同存在：小容器很容易被启动日志、数据库、缓存等耗尽。

K60WATCH、KX、MiniIOMobileFramebuffer 的屏幕文本首先是控制台诊断，不等于逐行写入 APFS。
用户态日志服务可能另外保存日志，必须在当前备份上统计 /logs、/db、/mobile 等目录。
文件逻辑大小/stream allocation 与容器物理用量不完全相同：元数据、快照、克隆共享、
checkpoint 等也会占空间。不能只把日志文件大小相加就宣称解释了所有已用块。
SIGKILL 的原因仍需 reason namespace/code 等信息；ENOSPC 并不直接证明所有 sig=9 都由此造成。

## 已准备的只读采集工具

`scripts/inspect-k60-data.py`：

1. capture 只接受 root recovery ADB，核对 unixnu 几何、无挂载/无 holders。
2. 校验 SHNGROOT SHA-256、窗口范围/重叠，再读回完整 Data GPT 窗口到 PC。
3. 对第二次设备读取的 SHA-256 与备份匹配，重读头确认采集中窗口表未变。
4. 校验 GPT 主备头/表 CRC，解析最新 APFS checkpoint、容量、卷 UUID。
5. `--usage` 仅在本地遍历备份元数据，按两级目录汇总 stream allocation 并列出大文件。
   报告可能包含私有路径，不上传 Data/keybags 或该报告到公开 CI/仓库。
6. 工具不含格式化、挂载、卸载、分区写入、切换窗口或删除文件命令。

```sh
# 从 WSL 调用 Windows adb.exe；输出目录必须不存在。
python3 scripts/inspect-k60-data.py capture \
  --adb /mnt/d/Android/platform-tools/adb.exe --serial 6033dbec \
  --output-dir /mnt/d/Android/k60-ios/backups/data-before-grow-2026-10-31 \
  --usage

# 已保存镜像的离线模式；不代表手机当前状态。
python3 scripts/inspect-k60-data.py offline \
  --manifest /tmp/k60-data-install-256/shngroot-with-data.bin \
  --data-image /tmp/k60-data256-gpt.img --usage
```

已在 256/512d 两份镜像上验证：窗口哈希、GPT 主备 CRC、APFS 容量正确；
损坏 SHA、合法哈希下的窗口重叠、超大或重叠的新布局会被拒绝。
元数据统计分别得到 36 个普通 stream 和 0 个，与各原始镜像一致。
尚未对当前手机做 capture；手机处于 XNU 时没有 ADB，须先进入 recovery。

## 可回退的布局预案（未执行）

外层 32 GiB GPT 分区不变。保留 OS/SystemOS 和旧 Data 的字节；在空白区放置扩大后的副本：

| 区域 | 规划 |
| --- | --- |
| OS / SystemOS | 保留原偏移与字节 |
| 旧 Data | 保留在 7420 MiB，切换时在 SHNGROOT 里另命名，例如 DataPrevious |
| 新 Data | 从 8 GiB 偏移开始，APFS 22 GiB，GPT 包装增加 2 MiB |
| 末尾余量 | 约 1.998 GiB |

此预案对两份历史布局均无重叠；SHNGROOT 最多 4 窗口，可保留旧数据引用。
实际切换仍须以 live capture 为准，并核对驱动只发布名为 Data 的当前窗口，
防止相同卷 UUID 的两个副本同时被发布。

### 先处理容量限制

- 当前 `kern_exec.c` 的 UFS Data 分支仍拒绝 >2 GiB；这是历史 scratch 上限，
  必须只对持久 UFS 路径改为与已验证 unixnu 窗口边界相符的检查，保留 RAM seed 的小容量约束。
- 旧安装脚本不是保留数据扩容器。仓库版只允许首次新增；本地扩展版会直接覆写旧镜像，
  缺备份、APFS UUID 核对及读回。本次不直接运行旧 --replace-existing-data 流程。
- GPT 包装器目前整图读入并反复分配 bytearray；22 GiB 会需要大量内存，
  实际构建前应改为流式/稀疏写入并验证相同 GPT 布局，不能按小种子方式直接处理大图。

### 在副本上真正扩大 APFS

优先保留现有块级文件系统/UUID：提取当前 Data GPT 中实际 APFS 分区到新文件，
仅扩大新副本；macOS hdiutil 以 raw disk image 附加，按 PhysicalStore 精确匹配 container，
再用 `diskutil apfs resizeContainer <实际容器> limits -plist` 预检，
`diskutil apfs resizeContainer <实际容器> 0` 扩容。
对附加对象验证 Virtual / Disk Image / 非 Internal / WholeDisk / 目标容量后才能执行。
检查卷 UUID、内容/元数据以及 `fsck_apfs -n`，正常分离，再包装 GPT。
现代 macOS 写出的特性必须检查仍兼容 iOS 16 APFS。

现有 `seed-data-grow.py` 输入是 DBRDISK1，K60 .dbr 实为 raw NXSB，不能直接套用。
`hdiutil resize` 不能代替 APFS 容器扩容。现有 Linux/Windows 工具没有核实可用的保留数据
APFS grow 路径；不猜 ioctl、不手改 NXSB/spaceman，也不把新的空种子冒充原卷扩容。
不把当前 Data 上传到公开 Actions/artifacts。现有 CI 只创建新种子，不能保留手机当前 Data。

最后：扩大后的 GPT 镜像及完整回退方案先在主机验证，写入 unixnu 空白区域后读回校验；
全部通过再提交单块 SHNGROOT 引用切换。本文仅为计划，没有写入设备。


## 2026-10-31 15:40 执行记录：ENOSPC 归因与 2 GiB Data 安装（已验证）

live capture（root Android KernelSU，只读，双重哈希）给出决定性证据：

- 当前 Data 容器确认 256 MiB（checkpoint xid 2405，与控制台 xid 2339→2357 同源），
  卷 `OwnerData` 已分配 261,971,968 / 268,435,456 字节 = **97.6%**。
- 占用归因：`/db/uuidtext` 122.2 MiB、`/db/diagnostics` 71.8 MiB、`/db/analyticsd`
  25.8 MiB、`/log/com.apple.xpc.launchd` 15.0 MiB、`/containers/Shared` 8.4 MiB ——
  **日志占 94%**。"日志写爆"从假设变为实测结论；同时 256 MiB 本身也太小。
- 完整备份：`D:/Android/k60-ios/backups/data-before-grow-2026-10-31/`，
  SHA-256 `203184993ce09ba80786e257ac23e77cebbddf43348fa7de1d1a394d75259517`，
  第二次设备读取哈希一致，manifest 前后未变。

修复（在 PC 上构建，写入窗口后读回验证）：

- mkapfs 2045 MiB（523,520 块）：上限 `0x80000000` = 2048 MiB 是内核
  `kern_exec.c` UFS 分支的检查值，标准包装器 + 2 MiB 会超出，所以 APFS 收缩到
  2045 MiB，最终 GPT 窗口 2047 MiB ≤ 上限 —— **零内核改动**。
- 卷 UUID 保持 defconfig 的 `1BCD69FF-24A5-48B1-94B6-8FE592B2F597`，
  容器 UUID 沿用 Apple 种子的 `068446EE-…`，label OwnerData。
- 镜像 SHA-256：raw `0915f6c2…`，GPT 窗口 `562d80ec…`。
- 安装：`--replace-existing-data`，offset 7420 MiB 不变，OS/SystemOS 未动；
  dry-run 先行，manifest 由安装器重写为 2047 MiB。
- **读回验证**：整窗 SHA-256 与推送镜像一致；APFS 解析通过
  （1.997 GiB，xid 1）；fresh free blocks ≈ 523,515，
  是 ENOSPC 阈值 1310 的 **399 倍**。
- 证据：`D:/Android/k60-ios/backups/data2g-install-2026-10-31/install-verify.json`。

旧 258 MiB 窗口的字节完整保存在 PC 备份中；SHNGROOT 单块写失败也不会破坏
OS/SystemOS。回退 = 重新推送备份镜像 + 恢复 258 MiB 的 manifest 条目。
