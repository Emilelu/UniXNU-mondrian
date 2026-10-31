# route-a-18 状态（2026-10-31 round 7）

## 本轮：darwin24 prelink 数据从真实 kernelcache 提取

### 22H374 kernelcache 解压成功
用 pong 的 `decompress-ipados18-kernelcache.py`（它自己解出来了：`bvx2` 魔数在这里是 **LZFSE**，不是 LZSS）：

```
kernelcache.release.ipad7c    17,218,385 B  (IM4P, krnl, KernelCacheBuilder_release-2931.140.3)
  ↓ lzfse -decode
kernelcache.decompressed      48,562,204 B  fat Mach-O, 1 slice arm64
  sha256 7f730f49240b76ca4b5938b152479cba1b729ac4c188e233e73665394f04ba43
```

### 段表（关键对照）

| 段 | 22H374 (darwin24) | 我们的 kernel 构建 |
|---|---|---|
| `__TEXT` vmaddr | `0xfffffff007004000` | **完全相同**（`ARM64_LINK_ADDR`） |
| `__DATA` vmsize | `0xb4000` | 我们 `0x150000`（K60 更大，仍装不下 slide 0） |
| `__PRELINK_TEXT` | `0xfffffff005130000` | 我们 `ARM64_PLKSEG_ADDR=0xfffffff004004000` |

段表结构完全同代，`__TEXT` 地址一致是最好的消息——**我们的链接地址选择和 Apple 22H374 一致**。

### prelink roots：32/32 全部存在

`__PRELINK_INFO` 是 XML 片段（没有 `<?xml` 头，以 `<dict>` 开头），共 **229 个 kext**。
我们 20G81 用的 32 个 roots 在 darwin24 里**一个不缺**：

```
our roots still present: 32/32
```

这意味着 **darwin24 的 kext 依赖图与 darwin22 基本一致**，prelink roots 列表可以原样沿用。

### profile 已更新

`profiles/os/ipados-18.7.10-22H374/profile.toml` 的 `["kernel"."prelink"]`：
- `kernelcache_sha256` → `7f730f49…`（darwin24 真实值，替换 20G81 的 `d260defc…`）
- `roots` → 32 个（内容不变，但现在是**从 22H374 验证过的**）
- 注释更新为 darwin24 的段表事实

## 设备状态

`boot-darwin24.img` 已刷入（21:20 左右），此后 fastboot/adb 均无设备响应——正在启动或已停机。
**等用户提供屏幕内容**才能判断 darwin24 内核是否起来。

## 下一步

1. 依据屏幕结果决定：UEFI 层 / 内核层 / kext 层的缺口
2. 若内核起来了但 kext 加载失败 → 用已提取的 22H374 kext 做 prelink（本轮的段表+roots 已就绪）
3. trust cache 仍待转 22H374 的 `.dmg.trustcache` → payload bundle（用户态阶段才阻塞）
