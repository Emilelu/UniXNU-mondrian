# DPU 直扫所需的最小 wire 侧面（只列不加字段就能做的部分）

给 display 立项时对照用。这一页只回答一个问题：**在 `PongScanoutWire` 一个字节都不加的前提下，
「让显示直接扫合成器的 surface」还差什么。**需要新字段的部分单独列在 §3，不混进来，免得把两件事
读成一件。

---

## 1 直扫需要的信息，与 v1 已有的字段

| 直扫需要知道 | v1 wire 里有没有 | 位置 |
| --- | --- | --- |
| 源像素在哪（GPU/物理地址） | **有** | `PongScanoutFrame.address`（`PongScanoutWire.h:12`） |
| 源行距（pitch） | **有** | `PongScanoutFrame.stride`，实测 5,888（面板 5,760） |
| 宽、高 | **有** | `width` / `height` |
| 像素格式 | **有**（目前只用了 `PongScanoutBgra=1`） | `PongScanoutModeInfo.format` 与 frame 的 `format` |
| 源字节数 | **有** | `bytes`（仅作校验，见 `PongAdrenoScanout.cpp:129` 的尺寸闸门） |
| 扫哪一块面板缓冲 | **没有** | v1 的 `reserved` 必须为 0；双缓冲要 v2 的 `target` |
| 复用凭证 / 旧映射驱逐 | **没有** | v2 的 `token` / `evict` |
| 面板节拍（TE / vsync） | **不在 wire 里** | 内核直接读 INTF 寄存器：`PongDsiPanel.cpp:84` 的 `IntfFrameCount=0xac`、`IntfTearSyncVsync=0x288`、`IntfTearAutorefresh=0x2b4` |

**结论一（这条是本节的重点）**：直扫所需的几何信息 v1 已经全有——地址、行距、宽高、格式。
`token`/`evict`/`target` 是**拷贝路径**（GPU blit 到面板缓冲、再翻页）需要的东西，不是直扫需要的。
所以「零拷贝」与「v2 会签」是两件事，可以先做前者。

## 2 不加字段就能做的最小形状：单缓冲直扫

做法：内核把 DPU 的源地址/行距/宽高按这一帧的 `address`/`stride`/`width`/`height` 编程，让面板直接扫
合成器的 surface，**GPU 一次拷贝都不做**。判据是 present 段那四个数整段消失（见
`check-gpu27-zero-copy.py` 的四条），而不是变小。

「不加字段」的接缝只有一个：`PongScanoutModeInfo.format` 现在只取 `PongScanoutBgra=1`，
可以约定一个新值（如 `2 = 直扫`）表示「这一帧按源几何直扫，不做拷贝」。这是**语义**上的新取值，
不是结构上的新字段——所以 48 B 布局、四条 `static_assert`、`PongAdrenoScanout.cpp:129` 的尺寸闸门
全都不用动。**这条要给 display 决定**（见 §5 第 1 问）。

三件必须同时成立，缺一条就白做：

1. **面板行距按 surface 的编程**。现在每帧一次全屏拷贝的根因就在这：源 5,888、面板 5,760，
   `drivers/PongMetal/GpuScanoutPresenter.h:87-89` 自己写着「只有两条路：把 pitch 差消掉（拥有与
   surface 同 pitch 的扫描缓冲，需要 DPU 编程），或者完全不拷贝」。**直扫就是第二条路。**
2. **单缓冲的上屏时机**。没有双缓冲就没有「另一块可以写」，所以换帧必须落在面板不扫这块内存的时候：
   `IntfTearSyncVsync`（`:0x288`）与 `IntfTearAutorefresh`（`0x2b4`）是现成的闸门；
   渲染侧的节奏靠既有 `PongScanoutWaitInfo`（500 ms 超时）+ `Done` 握手，不需要新记录。
3. **写者唯一**。合成器写 surface 与面板扫同一块内存必须串行，否则会出现半帧。
   现在这条靠 `pong_gpu_only` 那个开关的同一套判据（GPU 帧成功才不许 CPU 合成）——直扫模式下它是
   必须项，不是可选项。

## 3 需要 v2 才有、因此不在这一页范围的部分

- **双缓冲直扫**（写一块、扫另一块）：要 `target`（哪块），并通常要 `token`/`evict` 管复用与驱逐。
- **拷贝路径的双缓冲**：zizhan 已经这么做了（`PongAdrenoScanout.cpp:98-107` 的 `Pending` 带 `slot`/
  `evict`/`target`，`Kept` 池 `KeptCount=4`），但那条路**仍然是拷贝**，不解除 120 fps 那堵墙。

换句话说：**先做单缓冲直扫，能立刻验证「拷贝消失」这条判据；双缓冲是它的下一档，不是它的前提。**

## 4 不加字段时会看到的两类失败

- **撕裂**：换帧落在扫描窗口内。判据：拍屏或 TE 计数与帧计数对不上；不是判读器能查的，要上机看。
- **欠载（underrun）**：面板要扫的时候内存还没准备好，表现为间歇黑条/闪。
  这两类都不会在 `Pong Metal: scanout frames=` 那行里出现——**这正是为什么要先有直扫的判据**，
  否则「GPU 段消失但屏幕花」会被判成成功。

## 5 要 display 决定的三件事

1. `format` 新取值（如 `2 = 直扫`）这条路能不能接受；若不能，那就要么加一个 `mode` 字段（进 v2），
   要么用别的方法表达（例如 mode 请求里已有的 `bytes` 字段留作标志位——这需要它同意语义）。
2. 单缓冲直扫作为第一档是否够用（我们先验证「拷贝消失」，双缓冲随后）。
3. 行距与 CTL 页的编程归谁：CTL 页两棵树说法冲突（`PongDsiPanel.cpp:115-123` 的六个 `0x0ae16000+i*0x1000`
   vs t970 的 `0x2000+0x200*n`），直扫要写 CTL，**这个冲突必须先探针证，不能照抄**。

## 6 引用

- 布局与版本语义、四向矩阵：`GPU-27-SCANOUT-WIRE-PROPOSAL.md` §2.1 / §2.3
- 120 fps 的墙与三种半成品：`GPU-27-BUDGET-120FPS.md` §5 / §6
- 判据（拷贝整段消失）与它的休眠状态：`GPU-27-DEEP-EVIDENCE.md` #6
- 官方口径：`unixnu.com/zh/porting/gpu` 的 `#frame-path`、`#render-mode`
