# 27 ABI 实测：SoftwareAES 类布局与 AppleKeyStore selector 表

本文件回答 §A.4 的两个 `unknown`，全部来自 **24A446 kernelcache 的二进制**，离线、可重跑。
不构建、不上机、不写共享树。每条结论都带命令与偏移，换一个 artifact 就要重跑（§C 规则 4）。

## 0. 材料与工具

| 项 | 值 |
|---|---|
| kernelcache | `/home/emilelu/kc24A446/ipsw/24A446/kernelcache.decompressed`，77,987,840 B |
| sha256 | `fa07057bf34f33af1ec26681ad0c87c13e5aaa548a300740eddb0e92876e5f95` |
| 与 profile 的关系 | 与 `UniXNU/profiles/os/ios-27.0.1-24A446/profile.toml` 的 `kernelcache_sha256` **逐字节相同** |
| ipsw | `3.1.749`（`/home/emilelu/bin/ipsw`） |
| LLVM | `18.1.3`（`llvm-objdump-18` / `llvm-nm-18`） |

提取命令（只读；输出到 `kc24A446/extract/`、`kc24A446/all/`）：

```sh
K=/home/emilelu/kc24A446/ipsw/24A446/kernelcache.decompressed
ipsw kernel kexts "$K" | grep -i 'keystore\|cryptoaccel'
ipsw kernel extract "$K" com.apple.driver.AppleSEPKeyStore -o /home/emilelu/kc24A446/extract
ipsw kernel extract "$K" com.apple.iokit.IOCryptoAcceleratorFamily -o /home/emilelu/kc24A446/extract
```

代价：`kernel kexts` 约 2 s；单 kext `extract` 约 1 s；`--all` 305 个 kext 约 1 min。

## 1. SoftwareAES：27 的类布局

### 1.1 类元数据（`ipsw kernel cpp --json`）

```sh
ipsw kernel cpp -c IOService --json "$K"
ipsw kernel cpp -c IOCryptoAccelerator --json "$K"
ipsw kernel cpp -c IOAESAccelerator --json "$K"
```

| 类 | bundle | `Size` | vtable 槽数 | 新增槽 |
|---|---|---|---|---|
| `IOService` | `com.apple.kernel` | 136 = **0x88** | **168**（0x000–0x538） | — |
| `IOCryptoAccelerator` | `com.apple.iokit.IOCryptoAcceleratorFamily` | 136 = **0x88** | **169** | 1（0x540） |
| `IOAESAccelerator` | 同上 | 288 = **0x120** | **181** | 12（0x548–0x5a0） |

即：`IOService` 168 槽 → `IOCryptoAccelerator` 只加 **1** 个槽（0x540）→ `IOAESAccelerator` 再加 **12** 个槽（0x548–0x5a0），合计 181。
`IOAESAccelerator` 的对象大小 0x120 − 0x88 = **0x98**，与 `OriginalAESABI.h` 的 `originalFields[0x98]` 一致。

### 1.2 `IOAESAccelerator` 自己覆写的槽（`ipsw kernel cpp --methods -c IOAESAccelerator`）

19 个槽：`0x000, 0x008, 0x038, 0x2b0, 0x378, 0x3a8, 0x540, 0x548, 0x550, 0x558, 0x560, 0x568, 0x570, 0x578, 0x580, 0x588, 0x590, 0x598, 0x5a0`。
其中 0x540 是 `IOCryptoAccelerator` 的那 1 个新槽（`"subclass is required to implement getAlgorithmName"` 说明它就是 `getAlgorithmName`），
0x548–0x5a0 正好 12 个 = `performAES`×2、`isKeySupported`、`getSupportedOptions`、`performAESQuantum`、`completeAESQuantum`、
`performImmediateAES`、`disableHardwareKey`、`createSpecialKeys`、`_queueLocked`、`_startCommand`、`_completeAES`。

### 1.3 与 `drivers/SoftwareAES/OriginalAESABI.h` 的对照

| 断言（`OriginalAESABI.h:43-46`） | 27 实测 | 结论 |
|---|---|---|
| `sizeof(IOService) == 0x88` | 136 | 成立 |
| `sizeof(IOCryptoAccelerator) == 0x88` | 136 | 成立 |
| `sizeof(IOAESAccelerator) == 0x120` | 288 | 成立 |
| `sizeof(IOAESIV) == 16` | 纯 C 结构，不随类布局变 | 未测（保持 16 线值） |
| `offsetof(IOAESKeyData, selector) == 36` | 4 + 32 = 36 | 未测（结构布局稳定，保持 16 线值） |
| 「16 个虚函数」 | `IOCryptoAccelerator` 1 + `IOAESAccelerator` 12 = **13 个新槽**，但假头把 1 个放在 `IOAESAccelerator` 里声明 | 槽位总量 168+13 = 181 = 27 的 181，**槽位对齐** |

关键点：假头里 `IOCryptoAccelerator` 是空的（0 虚函数），`IOAESAccelerator` 声明 13 个虚函数（`getAlgorithmName` + 12 个）。
编译后 `getAlgorithmName` 落在 0x540、其余 12 个落在 0x548–0x5a0，**与 Apple 的 27 vtable 逐个槽位对齐**。
因此 §A.1 原来的「16 个虚函数」不是 16，而是 **1 + 12**；`sizeof` 三条断言在 27 上全部成立。

### 1.4 余下风险（未测项，不写成结论）

1. **方法签名**：槽位数与顺序对上，不代表参数寄存器/返回类型对上；Apple 的方法签名只能从 `__LINKINFO`/KPI 或反汇编读，本次没有做。
2. **PAC discriminator**：27 的 vtable 槽全部带 `pac` 值（`ipsw kernel cpp --methods` 每行有 `pac=0x...`），虚调用是 `blraa x9, x17`
   带 discriminator。`OriginalAESABI.h` 的类在 arm64e 下由编译器自行签名；**槽位对齐**降低但不消除「认证失败」风险。
3. **`IOAESKeyData` / `IOAESIV`**：纯数据结构，无元数据可读；沿用 16 线实测值，标 `inferred`，不标 `binary`。

## 2. AppleKeyStore：27 的 selector 表

### 2.1 27 没有独立的 `com.apple.driver.AppleKeyStore`

`ipsw kernel kexts "$K"` 列出 **323** 个 kext，其中与 key store 相关的只有：

```
0xfffffff00772bd80: com.apple.driver.AppleSEPKeyStore (2)
0xfffffff0079793f0: com.apple.iokit.IOCryptoAcceleratorFamily (1.0.1)
0xfffffff007db26c0: com.apple.kec.corecrypto (27.0)
```

**没有 `com.apple.driver.AppleKeyStore`**。24A446 上 AppleKeyStore 的实现（`AppleKeyStore.cpp` / `AppleKeyStoreHelper.cpp` /
`AppleKeyStoreUserClient` / `AppleKeyStoreTest`）全部在 `com.apple.driver.AppleSEPKeyStore` 这个 kext 里：

- 提取物：`com.apple.driver.AppleSEPKeyStore`，363,432 B，sha256 `15e5ba621625a7827050d2bdf7f1625bd8d0df1c7bfbcf3b62b38e95524df670`
- `ipsw kernel cpp --inheritance -c AppleKeyStoreUserClient`：`AppleKeyStoreUserClient` → `IOUserClient` → `IOService` → `IORegistryEntry` → `OSObject`
- 类大小：`AppleKeyStore` **0x1f8**、`AppleKeyStoreUserClient` **0x118**、`AppleKeyStoreCommand` **0x28**

对 K60 的直接含义：27 的 keybag 是 **SEP 后端**（`AppleSEPKeyStore`）。K60 没有 SEP，这个 kext 即使加载也起不来；
`AppleKeyStoreState` 要做的是「自己提供那个用户客户端」，不是去等 `com.apple.driver.AppleKeyStore`。

### 2.2 selector 分派：函数、跳转表、入口

`llvm-objdump-18 --macho -d com.apple.driver.AppleSEPKeyStore` 后，在 `__TEXT_EXEC` 里找到唯一的分派器：

| 项 | 值 |
|---|---|
| 函数入口 | `0xfffffff0095d095c`（前一条 `0xfffffff0095d0958: hint #0x22` 是 PAC 入口） |
| selector 0 | 单独处理，跳 `0xfffffff0095d0b58` |
| selector 1..0xa9 | `subs w28, w1, #0x1` → `cmp w28, #0xa8` → `b.hi` 默认；跳转表 `0xfffffff0095d8f10`（**0xa9 = 169** 个 32-bit 项，基址 `0xfffffff0095d0a48`） |
| 默认（拒绝）处理器 | `0xfffffff0095d6a5c`：`mov w24, #0x2c2; movk w24, #0xe000, lsl #16` ⇒ 返回 **0xe00002c2**（`kIOReturnUnsupported` 族） |

解码方法（可重跑）：`__TEXT_EXEC` vmaddr `0xfffffff0095c0180`，fileoff `32768`；表项 `target = 0xfffffff0095d0a48 + (int32)entry`。

### 2.3 169 个有效 selector 的分组

169 个 selector 落到 **126 个不同 handler**：其中 20 个落默认（拒绝），52 个落 8 个共享 handler，117 个各自独占一个 handler。按组列出：

| handler | selector 数 | selector（hex） |
|---|---|---|
| `0xfffffff0095d6a5c`（拒绝） | 20 | `0x19, 0x1c, 0x1d, 0x2f, 0x3b–0x3e, 0x63, 0x66, 0x67, 0x86, 0x88, 0x9e, 0xa3–0xa8` |
| `0xfffffff0095d0a54`（公共路径） | 10 | `0x2d, 0x2e, 0x30, 0x34, 0x38, 0x40, 0x6d, 0x74, 0x94, 0xa1` |
| `0xfffffff0095d0ba8` | 8 | `0x4a–0x4f, 0x54, 0x55` |
| `0xfffffff0095d59b0`（assert 组） | 4 | `0x1a, 0x1b, 0x64, 0x65` |
| `0xfffffff0095d0e08` | 2 | `0x15, 0x16` |
| `0xfffffff0095d0c7c` | 2 | `0x45, 0x8c` |
| `0xfffffff0095d0c04` | 2 | `0x5c, 0x9d` |
| `0xfffffff0095d0e74` | 2 | `0x6a, 0x9c` |
| `0xfffffff0095d0d40` | 2 | `0x7b, 0x9a` |
| 117 个独占 handler | 1 each | `0x01–0x14, 0x17, 0x18, 0x1e–0x2c, 0x31–0x33, 0x35–0x37, 0x39, 0x3a, 0x3f, 0x41–0x44, 0x46–0x49, 0x50–0x53, 0x56–0x62, 0x68, 0x69, 0x6b, 0x6c, 0x6e–0x73, 0x75–0x85, 0x87, 0x89–0x93, 0x95–0x99, 0x9b, 0x9f, 0xa0, 0xa2, 0xa9` |

**互证**：`0x1a / 0x1b / 0x64 / 0x65` 这一组与 16 线 `MiniAppleKeyStore.cpp:30-50` 的
`kAKSAssertHold / kAKSAssertDrop / kAKSAssertPromote / kAKSAssertConsume` 完全一致；并且 kext 内
`0xfffffff0095f7084` 的函数里确实有 `cmp w1, #0x65` / `cmp w1, #0x1b` / `cmp w23, #0x64` / `cmp w23, #0x1a` 四条比较。
这四点把「这张表就是 AKS selector 表」从形状证据提升为指令级证据。

### 2.4 `AppleKeyStoreState` 的 15 个 selector 对 27 表

`NativeKeyStoreEvents.cpp` 实现 15 个 selector：`0, 4, 5, 7, 9, 12, 13, 14, 17, 26, 27, 35, 55, 101, 102`（十进制）
= `0x00, 0x04, 0x05, 0x07, 0x09, 0x0c, 0x0d, 0x0e, 0x11, 0x1a, 0x1b, 0x23, 0x37, 0x65, 0x66`。

| 十进制 | hex | 27 表 | 结论 |
|---|---|---|---|
| 0 | 0x00 | 单独入口 `0x95d0b58` | 有 |
| 4 / 5 | 0x04 / 0x05 | 独立 handler | 有 |
| 7 | 0x07 | 独立 handler `0x95d2f4c` | 有 |
| 9 | 0x09 | 独立 handler `0x95d2780` | 有 |
| 12 / 13 | 0x0c / 0x0d | 独立 handler | 有 |
| 14 | 0x0e | 独立 handler `0x95d2750` | 有 |
| 17 | 0x11 | 独立 handler `0x95d2b70` | 有 |
| 26 / 27 | 0x1a / 0x1b | assert 组 `0x95d59b0` | 有 |
| 35 | 0x23 | 独立 handler `0x95d2b68` | 有 |
| 55 | 0x37 | 独立 handler `0x95d1504` | 有 |
| 101 | 0x65 | assert 组 `0x95d59b0` | 有 |
| **102** | **0x66** | **默认拒绝 `0x95d6a5c`** | **27 不支持** |

结论：15 个里 **14 个在 27 表里有对应入口，1 个（102 = `kAKSNotifyStateIsSet`）在 27 被明确拒绝**。
这不是「stub 少实现」，而是 27 的真实 kext 也不接受它 ⇒ stub 对 102 应当与 27 一致地返回 `0xe00002c2`，不要为了「全绿」把
`kIOReturnError` 改成 `kIOReturnSuccess`（§C.1 已把它列为禁止动作）。

### 2.5 与 16 线表的差异（只记差异，不推断原因）

16 线枚举 21 个 selector（`MiniAppleKeyStore.cpp:30-50`），27 的有效集是 169 个（0 + 1..0xa9）。
16 线的 21 个编号在 27 表里的状态：`0x00,0x07,0x08,0x09,0x0a,0x0b,0x0c,0x0e,0x11,0x17,0x1a,0x1b,0x1f,0x20,0x23,0x28,0x64,0x65,0x66,0x67,0x73`
中，**只有 0x66、0x67 被 27 拒绝**（默认组），其余 19 个都有入口。`0x73`（kAKSPrewarm）在 27 的 handler 是 `0x95d4b28`。

## 3. 复现与判据

```sh
K=/home/emilelu/kc24A446/ipsw/24A446/kernelcache.decompressed
ipsw kernel cpp -c IOAESAccelerator --json "$K"
ipsw kernel cpp -c IOAESAccelerator --methods "$K"
ipsw kernel cpp -c IOCryptoAccelerator --json "$K"
ipsw kernel cpp -c AppleKeyStoreUserClient --inheritance "$K"
ipsw kernel extract "$K" com.apple.driver.AppleSEPKeyStore -o /tmp/ks
llvm-objdump-18 --macho -d /tmp/ks/com.apple.driver.AppleSEPKeyStore | grep -n '95d095c\|95d8f10'
```

**判据（可证伪）**

1. 若 `ipsw kernel cpp --json -c IOAESAccelerator` 的 `Size` 不是 288，或 `--methods` 的槽数不是 181，则 §1 全部作废，重测。
2. 若 `IOAESAccelerator` 的 12 个尾槽不是从 0x548 连续到 0x5a0，则 `OriginalAESABI.h` 的声明顺序必须重排，不能直接编。
3. 若 `AppleSEPKeyStore` 的反汇编里 `0xfffffff0095d8f10` 的 0xa9 项解出的目标不是落在 `0xfffffff0095d0a54–0xfffffff0095d8310` 之间，则 §2.2 的表不是 selector 表。
4. 若 `cmp w1, #0x65` / `cmp w1, #0x1b` 不在 `0xfffffff0095f7084` 附近，则 §2.3 的互证不成立。
5. 换 kernelcache（sha256 变化）⇒ 以上全部重跑；本文件的结论只适用于 `fa07057b…`。
