# 追加：解析器不是黑屏的原因（2026-11-21 13:30，独立子代理复核 + 宿主 harness）

上面「结果二」把黑屏归因为 `39fa61c` 的解析器移植。**这个归因是错的**，必须改。下面是可复算的证据。

## 1. 移植块与官方 pin 逐字节相同

`git cat-file -p 3c75734:DarwinBootPkg/Driver/DarwinBoot.c` 的 `ParseKernelHeader` + fileset 遍历块，与 `39fa61c` 搬进
`Platforms/Xiaomi/DarwinBootPkg/Driver/DarwinBoot.c` 的那段**字节相同**。也就是说：我们不是"写坏了"，是把官方实现原样搬进来。

## 2. 解析器在菜单之前根本不会执行

调用链（全部实测 grep，只有一条）：

```
UniXNUPkg/Application/UniXNU/UniXNU.c:39     UniXNURun (ImageHandle, Host)
UniXNUPkg/Library/UniXNULib/Main.c:51        UniXNURun (...)
UniXNUPkg/Library/UniXNULib/Boot.c:58        gBS->LocateProtocol (&gUniXNULoaderProtocolGuid, ...)
UniXNUPkg/Library/UniXNULib/Boot.c:93        Loader->Boot (Loader, &Request)
DarwinBootPkg/Driver/DarwinBoot.c            Status = ParseKernel (Image, ImageSize, &Kernel)
```

`DarwinBootEntry` 只做一件事：`LocateProtocol` → 若已存在且 `Revision == UNIXNU_LOADER_REVISION` 就
`ReinstallProtocolInterface(..., &mLoader)` 并打印 `DARWINBOOT: replaced loader in RAM`。它**不调用** `ParseKernel`。
所以「驱动 dispatch 阶段崩」在代码路径上不成立——那条路径上没有任何解析。

## 3. 二分量到的其实是「拒绝」与「尝试」

`Main.c:184` `Countdown = TRUE` → `:186` `UniXNUMenuRun` → `:220` `UniXNUBootEntry`；`Menu.c:110-120` 用
`Config->Timeout * 1000`（默认 **5 s**）；`Main.c:229-232` 在加载被拒或返回后打印 `'%s' returned: %r` 并把
`Countdown = FALSE`（注释：*so a broken default cannot loop*）。

于是两张卷的行为差别是：

- **旧卷**（`ab98d09`，PE 54,784 B）：`ParseKernelHeader` 第一条 `(U32 (Data + 8) != 0) || (U32 (Data + 12) != 2)` 直接
  `EFI_UNSUPPORTED`——**微秒级拒绝**，菜单重画、计数停止，所以用户看得到界面。
- **新卷**（`39fa61c`/`5a3130f`，PE 55,296 B）：解析成功 → `Boot` **真的开始执行** → 分配 256 MB `EfiLoaderCode`
  窗口（`WINDOW_SIZE` `:21`，`:875` 处 `AllocatePool`/窗口分配）、把 93 MB 集合拷进去（`:910`）、`ExitBootServices`
  （`:1025`）、跳到入口（`:1032`）。如果这段拷贝与 GOP 帧缓冲重叠，**面板当场变黑**，而内核可能还没跑到 USB。

⇒ 二分得到的是「加载被拒绝 vs 加载被尝试」，不是「dispatch 有 bug vs 没有 bug」。

## 4. 两张真实卷只差这个驱动

从实际 `boot.img` 里解出的两张卷：DarwinBoot FFS `0xD836`/PE 55,296（含移植）vs `0xD636`/54,784（回退）；
`FVMAIN` 仍有 0x790（1,936 B）空闲；整个 3,694,600 B 的 `FVMAIN` 里另一处差异只是另一个模块 8 字节的 `LLD PDB.`
链接哈希（`0x2e1a0`）；PE 结构/重定位检查两张都过（30 条重定位、0 错）。所以「卷不同」= 「这个驱动不同」，没别的变量。

## 5. 宿主 harness 在真实内核上通过

`E:\k60-work\scratch\fileset-parser\`（`harness.c` 用 EDK2 薄壳 + `PROT_NONE` 守卫页 + poison + `sigsetjmp` + `alarm(5)`）：

```
kernel : /opt/k60/trees/ios27-out/…/kernel/kernel.macho  93061120 bytes
[1] real collection: status=EFI_SUCCESS segments=10 base=0xfffffff007004000
    end=0xfffffff00c8c4000 entry=0xfffffff00ad96488
[2] copy plan: 10 segments, 0 outside the file, span 0x58c0000 <= window 0x10000000
[3] LC_FILESET_ENTRY commands: 32
[4] truncations: 22 clean, 0 bad
[5] 9 个负例全部 EFI_LOAD_ERROR（cpusubtype/sizeofcmds 越界/零长度命令/名字偏移/成员入口改写/成员头越界 …）
HARNESS-RESULT: PASS checks=22 failures=0 traps=0
[old] ab98d09 ParseKernel: status=EFI_UNSUPPORTED （同一文件，KERNEL 结构原样未动）
```

⇒ 解析器在真实产物上是**正确且必要**的：它接受我们 27 的集合，旧版拒绝。它也补掉了一个真实缺陷：
`39fa61c:230-231` 先读 `Length = U32 (Data + Offset + 4)` 再判 8 字节是否还在，且 `Offset += Length` 没有零/越界守卫
（`cmdsize == 0` 会死循环）。这个已在 `fix/fileset-parser-guarded` 的 `5a3130f` 里加了边界检查。

## 6. 因此下一步的判据改成这样

黑屏只剩三个候选，按可能性排：

1. **装载窗口覆盖帧缓冲**：`Boot` 分配 256 MB、地址与 `Kernel.Base & (BLOCK_SIZE-1)` = `0x4000` 同余，然后拷 93 MB。
   旧卷从不分配这些，所以回退卷无法区分。
2. **内核在 `ExitBootServices` 之后立刻死**（同样 0 字节控制台）。
3. 镜像之外的东西。

**最便宜的判别实验（不用重打固件）**：用带解析器的卷启动，在 5 s 倒计时内按任意键（`Menu.c:209-217`：`UserActive = TRUE;
RemainingMs = -1` 取消计时），然后手动选 entry 0。
→ 若菜单留在屏幕上、只在选完条目后黑屏：解析器在硬件上被洗清，问题在交棒；读固件 Advanced Logger，把 `Video[0]` 与
`Video[2]*Video[4]` 跟窗口地址比。
→ 若菜单压根没出现：本节分析作废，卷不是变量。

为了让这个实验不必抢时间，已加 `diag/menu-hold-20261121` 分支：`board.toml` 的 `timeout = 5` 改 `-1`
（= *wait for a key*），镜像重建中。这条改动是**诊断值**，不发布。

## 纪律（不变）

- 只 `fastboot boot`，永不 flash、不写 `/dev/block/sda38`。
- 0 字节按 INVALID 处理，同镜像必须重跑一次。
- 结论必须能由别人用仓库里的命令复算；口径不一致时先改结论，不改判据。
