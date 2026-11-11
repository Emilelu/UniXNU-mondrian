# 硬性铁则

> ## 开工前必读（环境事实全在下面这些文档里，不要问用户）
> **`docs/ENVIRONMENT.md`** — 手机序列号/ADB 切 fastboot/Mac SSH 凭据/WSL 网关/构建命令
> **`docs/REPO-INVENTORY.md`** — 48 个本地 git 仓库清单
> **`docs/LOCAL-ASSETS.md`** — 官方驱动源码/固件/反汇编产物索引
> **`docs/YIBIYA-PICK.md`** — yibiya fork 采纳分析
> **`docs/PITFALLS.md`** — 已踩过的坑（88 条）
>
> **`docs/PITFALL-TO-RULE-INDEX.md`** — **99 条坑 → 12 条铁则的反查表
>   （遇到现象先查这里，就知道该守哪条铁则）**
> **`docs/TOOLBOX.md`** — **所有可复用工具的位置与用法（做之前先搜这里）**
> **`docs/PLAYBOOKS.md`** — **可复用操作流程 PB-1..PB-9（复制粘贴可复现）**
> **`docs/DATA-VOLUME-DEPLOY.md`** — **往 Data 卷放文件的三种方法**
> **`docs/PHK110-REFERENCE.md`** — 同 SoC 邻居项目 684 行调研
> **`docs/K60-TOUCH-DT-EVIDENCE.md`** — 触摸从 Android 取到的权威硬件数据
>
> **任何环境问题先在上述文档里查，查不到才动手探测。**
> **要做某件事之前，先在 TOOLBOX 搜工具、在 PLAYBOOKS 搜流程。**

---

# 第一章 最高优先级铁则（违反即返工，无例外）

这 25 条是 99 条 PITFALLS 提炼出的根因，违反任何一条都会重复犯错。

> **反查表**：`docs/PITFALL-TO-RULE-INDEX.md`（按现象查该守哪条）

## ★1（原 HR-33）先整篇读，禁止先 grep

**触发场景**：要查某个驱动/文档里的行为依据。

**规则**：
- 文档 **<500 行** → **整篇读完再动手**，禁止先 grep 片段
- 同一文件一个会话内 **grep 最多两次**；超过就说明该方法不适合，改整篇读
- 源码函数 → **整段读**（含前后注释和调用点），不要只 grep 一行

**为什么**：grep 只给片段，看不到上下文和顺序。本会话多次因为只 grep 到
`brl_send_config` 中间的 `msleep(100)` 就以为结束，漏掉了调用方的
`reset()` 和 `get_ic_info()` 重读，导致 config 下载成功但芯片没生效。

**正确做法**：
```bash
# 读整个函数（含前后 20 行）
sed -n "$((N-20)),$((N+80))p" file.c
# 或直接整文件读
cat file.c
```

---

## ★2（原 HR-34）任何改动必须能指出「文件:行号」依据

**规则**：
- 改动前必须能说出依据：`goodix_brl_hw.c:493` 这样精确到行
- 禁止「试试看」「可能是」「大概」
- 如果偏离文档，必须写出**实测反证**并登记到 PITFALLS.md

**为什么**：本会话触摸排查 200+ 轮，大部分时间花在「猜一个地址→刷机→失败」
的循环上。有依据的改动（如 config 三阶段协议）一次就成功。

---

## ★3（原 HR-27）先抄清单逐条执行，禁止跳步

**规则**：
- 每个硬件有独立 `docs/K60-<HW>-CHECKLIST.md`
- **未建 checklist 不得动该硬件的代码**
- **未走完 checklist 不得改代码**；要改必须先指出「第 N 条 FAIL」

**为什么**：跳步导致反复回到已排除的假设上。

---

## ★4（原 HR-28）选型必须有同型设备的成功证据

**规则**：
- 抄任何实现前，先确认「同 SoC / 同芯片」的仓库里它被验证过
- 触摸：K60=GT9916R，与 ruby 同款 → 协议层抄 ruby
- **zizhan 触摸是 ST FTS 不是 Goodix** → 只能参考总线/电源架构

---

## ★5（原 HR-40）变动必须及时 commit

**规则**：
- 每完成一个可验证小步立刻 commit（编译通过 / 设备验证通过 / 一个逻辑改动完成）
- **禁止攒到「全部做完再提交」**
- 主仓脏文件任何时候应 **≤5**；>20 视为流程违规
- commit message 必须含证据（日志文件:行号 / sha256 / 实测输出）

**为什么**：脏工作区是上下文压缩后**唯一**的成果载体，一旦误操作永久丢失。
本会话实测 `UniXNU-pong` 脏 387 个、`pong-adreno` 脏 116 个，
导致同步脚本无法 rebase，上游更新永远进不来。

---

## ★6（原 HR-44）用户重复交代同一件事 = 文档缺陷，立刻补进去

**规则**：
- 用户**第二次**提到同一件事时，立刻写进 `ENVIRONMENT.md` 或本文件
- **禁止只回答「记住了」而不落文档** —— 那等于没记住
- 回复里要指出写到了哪个文件哪一节

**已因这条栽过的**：ADB 切 fastboot、Mac 可 SSH、"要做索引"、
"变动及时 commit"、"300 秒复位是自动化调试"。

---

## ★7（原 HR-17）动外部资源前先探活

**规则**：
```bash
# 任何依赖外部机器（Mac / 设备 / 网络）的操作前必须先探
fastboot devices || adb devices
sshpass -p <password> ssh -o ConnectTimeout=8 <user>@<mac-host> 'echo OK'
```
探活失败 → 换路径或等待，**不要在离线机器上排计划**。

---

## ★8（HR-45）boot-args 硬上限 608 字符，加参数前必须量长度

**限制来源（XNU 源码，精确到行）**

```
pexpert/pexpert/arm64/boot.h:26
#define BOOT_LINE_LENGTH        608

pexpert/pexpert/arm64/boot.h:69
char CommandLine[BOOT_LINE_LENGTH];
```

- arm64 上限 **608 字节**（含结尾 NUL）→ **实际可用 607 字符**
- arm32 更小：`boot.h:14` 是 256

**超限后果**：boot-args 被静默截断，尾部参数丢失或截断在某个词中间，
内核在 USB gadget 初始化前就死 —— **表现为「刷进去没反应/串口无输出」**，
极易误判成内核崩溃或驱动问题。

**铁则（强制）**

1. **每次改 `packv15.sh` 的 `G = (...)` 后立刻量长度**：
   ```bash
   python3 - <<'PY'
   import io,re
   s=io.open('<workspace>/scratch/packv15.sh',encoding='utf-8').read()
   a=re.search(r'G = \("(.*?)"\)',s,re.S).group(1)
   print('chars=%d  limit=607  %s' % (len(a), 'OK' if len(a)<=600 else 'OVER'))
   PY
   ```

2. **留 8 字符余量**：目标是 **≤600**，不是 ≤607。

3. **加新参数前先删等长的旧参数**，或者用更短的名字。

4. **打包脚本必须自带护栏**（已在 `packv15.sh` 里加了断言）。

5. **最容易被忽略的长参数**：
   ```
   37  pong_init_path=/private/var/pong/init
   33  pong_allow_unauthenticated_root=1
   27  k60_tolerate_cache_loader=1
   25  k60_skip_firmware_mount=1
   ```

**补充：board.toml 里的 args 不生效**

`packv15.sh` 的 `G = (...)` 才是打包时真正写入的 boot-args。
改 `board.toml` 对已打包镜像**没有影响**，两边都要改或者只改 packv15.sh。

---

## ★9（HR-46）分支卫生、及时合并 main、README/porting.toml 随现状更新

**用户 2026-11-10 明确要求，这几件事不要反复提醒。**

### 1. 清理冗余分支

- **完工的旧分支**（已合并进 main，或明确废弃）定期删除
- **长期不动的分支**（>30 天无提交且未被依赖）评估后删除
- 删除前必须确认内容已在 main 或别的分支留存：
  ```bash
  git branch --merged main          # 已合并，可删
  git branch -v --sort=-committerdate  # 按最近提交排序
  git log main..<branch> --oneline  # 空 = 无独有提交，可删
  ```
- **禁止删除有未合并提交的分支**（除非先 cherry-pick 或确认废弃并记录原因）

### 2. 工作分支有重大进展要及时合并到 main

- **完成一个硬件/一个里程碑 → 立刻合并 main**，不要长期挂着
- 合并前必须：构建通过 + 设备验证通过
- 合并方式：`git checkout main && git merge --no-ff <work-branch>`
- 合并后跑一次构建确认 main 可构建
- **禁止把 main 当垃圾桶**：main 任何时候都应可构建

### 3. README 必须反映当前真实状态

README 里必须包含（且随进展更新）：
- 当前各硬件状态表（CPU/UFS/显示/触摸/GPU/WiFi/蓝牙/音频/基带/USB/电源）
- 每项用真实状态词：`device-verified` / `implemented` / `partial` / `not started`
- **禁止把 implemented 说成"已完成"**（HR-37）
- 已知限制（limits）诚实列出
- 构建与刷机步骤

### 4. porting.toml 必须符合官方规范并随现状更新

- `porting.toml` 有**官方 schema 要求**，字段和取值必须合规
- 每个 hardware area 的 `status` 必须与实际一致：
  - `device-verified` — 有真机日志证据
  - `implemented` — 代码完成但未真机验证
  - `planned` — 计划中
  - 未做的 area **必须存在且标 planned**，不能省略
- `components` / `paths` / `inputs` / `evidence` 字段随代码变更同步
- **每次硬件状态变化后立刻更新 porting.toml**，不要攒着

### 5. 每次大提交后自检清单

```bash
# 分支
git branch --merged main | grep -v main          # 应定期清空
git log main..HEAD --oneline | wc -l             # 工作分支独有提交数

# 状态文档
grep -c 'device-verified' porting.toml README.md
grep -c 'planned' porting.toml
```

**这几项都不是"有空再做"，是提交流程的一部分。**

---

## ★10（HR-47）commit 之后必须 push：本地提交不等于成果存在

**用户 2026-11-10 明确要求：「commit 后每天都要 push，GitHub 上各仓库好几天没 push 了」。**

### 规则

1. **commit 之后立刻 push**，不要攒着。
   ```bash
   git add -A && git commit -m "..." && git push origin HEAD
   ```

2. **重大进展必须当天 push**：完成一个硬件、解决一个 blocker、合并 main 后，
   **立刻 push 到远端**。本地仓库对任何人（包括未来的自己）都不可见。

3. **每日定时任务必须包含 push**（已加入每日 09:00 / 21:00 的仓库同步任务）。

4. **push 前自检**：
   ```bash
   git status --porcelain | wc -l      # 应 0
   git log origin/main..HEAD --oneline # 有内容就必须 push
   ```

5. **push 失败要当场修**，不能跳过：
   - 代理问题 → `scripts/fix-git-proxy.sh`（HR-41）
   - 分叉 → 先 `git pull --rebase`，冲突人工解决
   - 权限 → 检查 remote url 与凭据

### 为什么

本会话中主仓曾连续多天只在本地提交（`fix/k60-measured-high-window`
领先 main 21 个提交却从未 push），导致：
- 远端 `main` 停在 `6c1e1f1`，与实际状态严重脱节
- 别人（yibiya / Seanding1998 等协作者）看不到进展
- 一旦本地磁盘故障，全部成果丢失

### 与 HR-40 的关系

- **HR-40**：变动及时 **commit**（本地保住）
- **HR-47**：commit 后及时 **push**（远端保住）
- 两条都要做，缺一不可。

### 每日任务里的 push 覆盖范围

`scripts/sync-all-repos.sh` 的 B 类工作仓库在 rebase 后应执行 push
（当前脚本只做 fetch+rebase，**push 需要补上**）。

---

## ★11（HR-48）push 必须在 Windows 侧执行，WSL 里的 git 没有凭据会静默挂起

**2026-11-11 实测，浪费 1 小时以上。**

### 症状

WSL 里 `git push` **没有任何输出，永远不返回**，`timeout` 杀掉后仍是"未推送"。
看起来像网络慢、像代理配错、像 pack 太大 —— **全都不是**。

### 真因

```
$ GIT_TERMINAL_PROMPT=0 git push --force origin main
remote: No anonymous write access.
fatal: Authentication failed for 'https://github.com/...'
```

**WSL 的 git 没有任何 GitHub 凭据配置：**
```bash
git config --global --get credential.helper    # 空
ls ~/.git-credentials                          # 不存在
```
git 于是尝试**交互式询问用户名/密码**，但后台运行没有 TTY →
**永远阻塞在 HTTP 401，不输出任何东西。**

### Windows 侧有完整凭据

```
git 2.54.0.windows.1
credential.https://github.com.helper = !'C:/Program Files/GitHub CLI/gh.exe' auth git-credential
凭据管理器: git:https://github.com (User: Emilelu)
            gh:github.com:Emilelu
```

### 铁则

1. **push 一律在 Windows 侧跑**：
   ```powershell
   Set-Location 'E:\hackios\UniXNU-mondrian'
   $env:GIT_TERMINAL_PROMPT='0'
   git push --force --progress origin main
   ```

2. **WSL 里只做 fetch / 构建 / 刷机**，不做 push。

3. **任何非交互 git 命令都要加 `GIT_TERMINAL_PROMPT=0`**，
   缺少凭据时**立刻报错**而不是挂死。

4. **排查「push 卡住」的标准顺序（不要先怀疑网络）**：
   ```bash
   # ① 认证能过吗？（最快，直接暴露真因）
   GIT_TERMINAL_PROMPT=0 git push origin main 2>&1 | head -5
   # ② 出现 "No anonymous write access" = 凭据问题 → 去 Windows 推
   # ③ 只有认证能过、仍卡住，才查网络 / pack 大小
   ```

5. **区分 GET 和 POST**：`ls-remote` / `fetch` 是 GET（匿名可读，能成功），
   **`push` 是 POST 且需要认证**。
   **「ls-remote 秒回但 push 卡死」几乎必然是认证问题，不是网络问题。**

### 连带教训

为了这个假象，我曾改 `http.postBuffer=500MB`、`http.version=HTTP/1.1`、
甚至用 filter-repo 重写整个历史 —— **都没解决卡住**（虽然重写历史本身确实该做）。
**先把认证验通，再谈带宽和 pack 大小。**

实测：切到 Windows 侧后，21.77 MB / 8497 个对象**一次推送成功**，耗时不到一分钟。

---

## ★12（HR-49）能复用的工具、流程、命令，立刻写文档——不要等用户提醒

**用户 2026-11-11 明确要求，且此前已多次因「失忆」返工。**

### 规则

**任何一次操作中，只要出现下列任一情况，当轮就写进文档：**

1. **写出了一个能跑通的脚本/命令序列** → 存到 `scripts/` 或 `scratch/`，
   并在对应手册里登记
2. **发现了一个工具的位置**（apfsck、linux-apfs-rw、mcopy、otool…）→
   写进 `docs/TOOLBOX.md`
3. **走通了一条以前没走过或走得很痛苦的流程**（如 dd 整个分区、payload 注入、
   挂载 APFS、构建 userland）→ 写成步骤文档
4. **发现某个已有文档写了但不完整**（比如 TWRP dd 流程只在 archive 里）→
   补全或在新手册里引用
5. **同一步骤做了第二次** → 说明第一次就该文档化，立刻补

### 判断标准（一句话）

> **「如果上下文被清空，下一个人/未来的我能不能只看文档复现这一步？」**
> 不能 → 写文档。

### 文档落点（不要建散乱文件）

| 内容类型 | 落点 |
|---|---|
| 环境事实（IP/凭据/串口/设备状态） | `docs/ENVIRONMENT.md` |
| 流程/铁则/禁止事项 | `docs/HARD-RULES.md` |
| **可复用工具清单** | **`docs/TOOLBOX.md`** |
| **可复用操作流程** | **`docs/PLAYBOOKS.md`** |
| 某个子系统的专向手册 | `docs/<TOPIC>.md`（如 `DATA-VOLUME-DEPLOY.md`） |
| 踩过的坑 | `docs/PITFALLS.md` |
| 文件/仓库在哪 | `docs/LOCAL-ASSETS.md` / `docs/REPO-INVENTORY.md` |

### 已因此建立的文档（示例）

- `docs/DATA-VOLUME-DEPLOY.md` — 往 Data 卷放文件的三条路径（payload.img /
  dd unixnu / 内核内嵌 blob），含本地 APFS 工具清单
- `docs/TOOLBOX.md` — 所有可复用工具的位置与用法
- `docs/PLAYBOOKS.md` — 可复用操作流程

### 反面教材（真实发生）

- **TWRP dd 整个 32 GiB unixnu 分区**的流程只在 `docs/archive/` 里，
  每次都要重新找 → 已整理进 `DATA-VOLUME-DEPLOY.md`
- **本地有 apfsck / linux-apfs-rw / Python APFS 工具**，但从未登记，
  用户不得不提醒"本地好像也有一些 python 写的 apfs 工具"
- **payload.img 是 FAT、可用 mcopy 注入**，这条本次才发现，
  而 `packv15.sh` 一直在用 mcopy 却没人写下来

### 执行要求

**每个回合结束时问自己：本轮有没有产生可复用的东西？有就写。**

---

## ★13（HR-50）遇到坑必须**当轮**写进文档，且必须升为可检索的条目

**用户三次指出同一问题，说明"记文档"这件事本身没有可执行的强制形式。**

### 什么算"坑"（必须记）

只要出现下列任一情况，**当轮就写，不许攒**：

1. 一个操作**失败过一次又修好**（构建失败、补丁打不上、脚本报错、启动 panic）
2. **同一件事做了第二次**（说明第一次就该文档化）
3. 一个**工具/资源找不到**（SDK、脚本、驱动源码、凭据）—— 先 `find` 全盘确认
4. **假设被实测推翻**（AVDD、报告地址、init 能启动……）
5. 某个**参数/开关**存在但一直没生效（0391 从未入 series、`k60_panic_reset` 从未传）
6. **看起来能编过但运行时炸**（ncmds=10 的 init、union 挂载 Extensions）

### 记在哪（按类型，不许建散乱文件）

| 类型 | 落点 | 要求 |
|---|---|---|
| 踩过的坑 | `docs/PITFALLS.md` | 编号 `P-NN`，含：症状 / 真因 / 正确做法 / 判别命令 / 教训 |
| 流程规则 | `docs/HARD-RULES.md` | 编号 `HR-NN`；最重要的进「第一章 ★N」 |
| 可复用工具 | `docs/TOOLBOX.md` | 路径 + 用法 + **默认扫描范围** |
| 可复用流程 | `docs/PLAYBOOKS.md` | 编号 `PB-N`，复制粘贴可复现 |
| 环境事实 | `docs/ENVIRONMENT.md` | 路径/凭据/版本，一句话可查 |
| 硬件权威数据 | `docs/K60-<HW>-DT-EVIDENCE.md` 等 | 从实机读到的原始值 + 来源 |

### 硬性形式要求（否则等于没记）

1. **PITFALLS 条目必须能被 grep 到症状关键词**
   —— 例如搜 "new blank line at EOF" 要能命中 P-96。
2. **每条必须带「判别命令」**：下次遇到同样现象，跑一条命令就能确认是不是这个坑。
3. **发现已有文档里写过但没执行，要把执行方式写进铁则**（本条就是这么来的）。
4. **工具类条目必须写明「处理范围」**：
   `fix_hunk_counts.py` 原来硬编码两个路径 → 新补丁不被处理 → 等于没工具。
   已改为默认扫 `patches/xnu/*.patch`。

### 每轮收尾自检（三条）

```
□ 本轮有没有失败过又修好的东西？→ 写 P-NN
□ 本轮有没有第二次做的事？      → 写 PB-N 或 TOOLBOX
□ 本轮有没有"以为没有其实有"的资源？→ 写 ENVIRONMENT + P-NN
```

**任何一条为「是」而没写文档，本轮不算完成。**

### 违反记录（真实发生）

| 时间 | 违反 | 代价 |
|---|---|---|
| 2026-11-11 | iPhoneOS SDK 在 Mac 自定义路径下没记 | 绕了 1 轮去研究装 Xcode，而 SDK 一直在 |
| 2026-11-11 | 补丁 hunk 三要求没记 | 0404 返工 4 次 |
| 2026-11-11 | `fix_hunk_counts.py` 只扫硬编码路径没记 | 新补丁不被处理，重复手数行数 |
| 2026-11-11 | **本铁则本身没建立** | 用户三次指出同一问题 |

---

## ★14（HR-51）构建链的四个真相源，改错地方等于没改

**来源**：P-13/P-14/P-15/P-16/P-40/P-42/P-44/P-45/P-73/P-90/P-92/P-96（12 条坑）

**四条铁律**：

1. **`patches/xnu/series` 是产物，真相源是 `scratch/SERIES-FINAL.txt`**
   （P-90）。`buildv15.sh:12` 每次 `cp -f` 覆盖。改 series 必须先改后者。

2. **补丁要改三处，少一处就被覆盖**（P-44）：
   ```
   ① E:\hackios\UniXNU-mondrian\patches\xnu\<name>.patch   （仓库）
   ② /tmp/usb-cdc-mainline/device/patches/xnu\<name>.patch （构建输入）
   ③ 构建树 .cache/xnu-work/<target>                         （已应用状态）
   ```

3. **构建读的是 `$B/tree/.cache/xnu-work`，不是 device 仓的 `iokit/`**（P-40）。
   `out`/`out2`/`out3` 是历史树，可用于对照（P-42）。

4. **补丁插入位置必须在 series 末尾**（P-53）；**锚点依赖全部前序补丁后的真实状态**
   （P-52）——不能凭记忆生成，必须 `sed -n` 读真实文件。

**每次构建前自检**：
```bash
grep -n '<新补丁名>' <workspace>/scratch/SERIES-FINAL.txt   # 在真相源里吗
cd <xnu-work> && git apply --check <patch>                       # 上下文对吗
```

---

## ★15（HR-52）补丁格式有三个 git apply 硬性要求，错一个就返工

**来源**：P-13/P-46/P-92/P-96（4 条）

1. **新增文件段必须有 `@@ -0,0 +1,N @@`**，且 N = 实际 `+` 行数。
   缺 hunk 头 → `git apply` **静默建 0 字节文件**（P-13）。
   删行后不同步改 N → `corrupt patch`（P-96）。

2. **新增文件段最后一行不能是裸 `+`**
   → `git apply` 报 `new blank line at EOF` 并拒绝（P-96）。

3. **上下文必须逐字匹配**，包括被跳过中间行；
   两个补丁在同一锚点插入 → 后一个必然失败，改行号无用（P-92）。
   要合并补丁或换锚点。

**固定流程**（PB-10）：
```bash
python3 <workspace>/scratch/fix_hunk_counts.py   # 默认全扫 patches/xnu
python3 <workspace>/scratch/fix_bare_lines.py
cd <xnu-work> && git apply --check <patch>           # 必须无输出
```
**`patch --dry-run` 通过不算数** —— 构建用 `git apply`，判定更严。

**手写 `@@` 行号会连续错（P-109）——用 `difflib.unified_diff` 生成补丁**：
```python
orig = open(原始文件).read().split('\n'); new = list(orig)
i = next(i for i,l in enumerate(orig) if l.strip() == '目标行')   # 用内容定位
new = new[:i] + NEW + new[i:]
d = list(difflib.unified_diff(orig, new, fromfile='a/x', tofile='b/x',
                              lineterm='', n=3))
open(patch,'w').write('\n'.join(['diff --git a/x b/x'] + d) + '\n')
```
**源文件必须是"本补丁应用前"的真实构建树副本**（P-110：本机有三份不同的
`kern_exec.c`，用错树则所有锚点都错）。

**批量修改类工具的默认行为必须是"不动"**（P-102）：
`fix_hunk_counts.py` 曾改成「默认全扫 `patches/xnu/*.patch`」，
一次运行误改了 10 个本来正常的补丁（其中一个 17 个 hunk）。
现在默认不处理任何文件，必须显式传路径。
**跑完必须 `git status` 对比基线，只保留预期文件。**

---

## ★16（HR-53）门控开关：先查「哪个函数读哪个 arg」，再谈为什么没生效

**来源**：P-36/P-43/P-47/P-53/P-55/P-58/P-69/P-97/P-98（9 条）

**这一类坑的共同形态**：功能明明实现了，就是不执行。

**必查三件事**：
1. **默认值**：`static int x;` = 0 = 关闭；`enabled=0` 时第一行就 return（P-36）
2. **读取位置**：`PE_parse_boot_argn("名字", ...)` 的**确切拼写**
   （P-97：`k60_panic_reset` ≠ `k60_autoreset`，是两个开关）
3. **`#if` 包裹**：`#if defined(PONG)` 在某些文件里恒为假，代码被预处理器删除（P-43）

**双门控**（P-58）：音频/触摸等有**两道**门控，只设一道不执行；
两道都过可能挂死，要逐一验证。

**阶段门控的插入位置必须在"危险调用之前"**（P-69），不是之后。

**boot-args 是共享预算**（HR-45，608 硬限）：
腾字符的**安全顺序**（P-98）：
```
低风险：epoch / k60_touch_delay / k60_touch_diag / k60_touch_bb_us（源码有默认值）
高风险不可动：k60_skip_iosurface / pong_software_keybag / amfi_get_out_of_my_way
              / cs_enforcement_disable / k60_usblog
```

---

## ★17（HR-54）MMIO 三件事：窗口要够大、偏移要真实、地址要虚拟

**来源**：P-01/P-02/P-63/P-64/P-78/P-82/P-83（7 条）

1. **`io_submap` 只有 8 MiB**，`ml_io_map` 满了会 panic（P-63）
2. **MMIO 窗口必须覆盖最大引脚偏移**：
   TLMM 64 KiB 让 gpio71（`0x147000`）越界 → 写全部落空（P-82/P-64）
3. **必须用虚拟地址调 `rd()/wr()`**，物理地址 → data abort（P-78，两次）
4. **大窗口读不等于真读过**：某接口单次最多 8 字节，
   48/64 字节的"数据"是回绕假象（P-83）

**每次访问 MMIO 前**：
```c
if (!map) { printf("map failed %#lx\n", phys); return; }   // 必须判空
```

---

## ★18（HR-55）硬件协议层：先反编译控制器，再写协议；同型号可抄但要核对

**来源**：P-31/P-33/P-38/P-48/P-49/P-59/P-65/P-66/P-67/P-70/P-79/P-80/P-83~P-88（18 条）

1. **只反编译协议层不够，必须反编译控制器层**（P-80）
2. **不要盲目试"厂商私有寄存器"** —— 两次导致整机复位（P-79）
3. **同型号芯片可直接抄协议，但引脚/时钟/电源要独立核对**：
   K60 GT9916R 与 ruby 同款 → 协议可抄；
   但 **MISO 是 GPIO 17 不是 16**（P-70）、**GENI SE 是 SE4 不是 SE1**（P-38）
4. **ruby 的 MT6360 寄存器偏移不能套到 pm8350c**（P-85）
5. **SPMI PPID 只有 12 位**，扫 `0x4000+` 永远匹配不到（P-84）
6. **RPMh 用 ACTIVE TCS4 不是 slot0**（P-86）；
   **完成判据是 `CMD_STATUS` 不是 `IRQ_STATUS`**（P-87）
7. **`CMD_ROOT_OFF`（bit31）是硬件授权控制，软件写不进去**（P-66）；
   **`cbcr bit31=0` 是"未关闭"不是"未开启"**（P-67）
8. **SE 时钟未开时访问会挂死整机**（P-49）——"能通过 configuration()" 反而是灾难

---

## ★19（HR-56）证据判定：日志里没有 ≠ 没运行；单一字段不判完成度

**来源**：P-04/P-05/P-06/P-07/P-08/P-10/P-21/P-22/P-23/P-41/P-45/P-56/P-60/P-71/P-72/P-81（16 条）

1. **「日志里没有某驱动输出」不等于「驱动没运行」**（P-56）
2. **不要只看 `status` 字段判完成度**，必须读实测记录（P-71）
3. **交付物目录存在 ≠ 交付完成**（P-72）
4. **认版本按「日志字符串组合」，不按文件名或单一标识**（P-21）
5. **镜像启动 0 字节日志 ≠ 设备坏**，先用历史镜像对照（P-41）
6. **同名不同物**：`scratch/payload-0461.img` ≠ `boot-0461` 里的 payload（P-23）
7. **不要凭 `summary` 一句话推断仓库覆盖范围**（P-81）
8. **「120Hz 生效」是错表述**：软件排帧 ≠ 面板切档（P-60）
9. **计数型断言会过期**：`count==N` 随代码变化失效（P-05）

**判据硬化**：任何「完成/生效」的断言，必须给出
**可复现命令 + 原始输出**，不接受间接推断。

---

## ★20（HR-57）init / 用户态：不重编能手工作的二进制，用内核侧做

**来源**：P-18/P-19/P-20/P-21/P-26/P-27/P-28/P-30/P-32/P-34/P-35/P-94/P-95/P-99/P-100/P-101（16 条）

1. **在重编一个"能工作的二进制"之前，先核实新功能是否真的非它不可**（P-101）
   —— 内核侧往往能做同样的事（0340 部署 libpong-ui 就是先例）
2. **不要手工编译 init**：`ld64.lld 18` 的 `-static` 未实现，
   产物是动态链接 → `EXEC_EXIT_REASON_BAD_MACHO`（P-19）
3. **签名的正确工具是 `ldid-lite.py`**（P-99）：
   macOS 26 的 codesign 产出 18 KB 签名，能启动的只有 408 B
4. **`__entitlements` 要 `-sectcreate` 进 `__TEXT` 段**，不是 codesign blob（P-99）
5. **`-headerpad` 对静态链接无效**，ldid-lite 需要现成空间（P-100）
6. **密封根上 `bindfs` 一律 EPERM**（P-27）；
   **union 父目录 `/System/Library/*` 会破坏 dyld cache → pid 1 panic**（P-93）
7. **`mount("apfs", ...)` 对某些卷返回 `ENEEDAUTH(79)`**（P-28）
8. **内核写文件必须 `vnode_close(vp, 0, ctx)`**，传 `FWRITE` 会 panic（P-18）
9. **"能启动的二进制"必须立刻落进仓库**（P-104）：
   设备上能跑的 init 曾只存在于 `/tmp/initbuild/`，`0391` 一生效就永久覆盖丢失。
   `/tmp` 不是存储；判断版本看**日志特征字符串**，不看文件名或大小。
10. **动手挂载前先读消费方代码**（P-105）：`PongMetalPlugin.mm:174` 本来就搜
    `/System/Library/Extensions` 和 `/private/var/pong` 两个目录，
    后者可写，所以密封根上的 bindfs/mkdir 从头到尾都不需要。
    密封根上 `mkdir`=EROFS、`bindfs`=EPERM（P-27），不要再试。

---

## ★21（HR-58）subagent 只能做「单窗口可完成 + 必须产出文件」的任务

**来源**：P-12/P-61/P-72/P-91（4 条）

1. **开放任务（"调试到能用"）会空转退出，零产出**（P-91）
2. **一个 subagent 只做一件可在单窗口完成的事**，并**必须产出一个文件**
3. **subagent 的结论必须交叉验证**（P-61）
4. **核心调研文档必须主 agent 亲自读**，不能派 Explore 只拿片段（P-12）
5. **需要多轮硬件验证的任务不要派 subagent**，主 agent 自己做

---

## ★22（HR-59）仓库与同步：push 在 Windows、pull 要真拉、版本要先对齐

**来源**：P-77/P-89/P-90（3 条）

1. **push 必须在 Windows 侧**（P-89）：WSL 无 GitHub 凭据，会静默挂起等密码
2. **只 `git fetch` 不 `git pull` = 读的是旧代码**（P-77）
3. **`patches/xnu/series` 是产物**（P-90）

---

## ★23（HR-60）不要重复造轮子：先查 zizhan / 官方仓库 / 本地工具

**来源**：P-75/P-76/P-80/P-81（4 条）

1. **不查 `UniXNU-zizhan`（同 SoC 超集）就动手 = 必然重复造轮子**（P-76）
2. **跳过八步③（Android 反编译）→ 协议用错，整段白费**（P-75）
3. **本地已有工具/源码/固件要先检索**：`docs/LOCAL-ASSETS.md` + `docs/TOOLBOX.md`
4. **「某资源不存在」的结论必须先用 `find` 全盘确认**（P-95：
   iPhoneOS SDK 一直在 Mac 上，`xcrun` 查不到而已）

---

## ★24（HR-61）改构建脚本前必须 `diff -u` 黄金脚本

**来源**：P-14/P-15/P-16/P-17（4 条）

1. **删两行 `LD_KERNEL_ARCHIVES` 会让平台驱动整层不链接**（P-14）
2. **`cp -a` 覆盖已有 `tree/` 会让 unixnu 跳过整段补丁应用**（P-15）
3. **清 `tree/` 会连 `.cache/fakeroot` 与 `.cache/sources` 一起删**（P-16）
4. **`unixnu bootimg` 产出的布局错误**（P-17）

---

## ★25（HR-62）「能编过」不等于「能运行」：运行时判据优先

**来源**：P-19/P-49/P-94/P-99（4 条）

1. **两个都是合法 arm64 Mach-O，一个能启动一个 panic**（P-94）：
   判据是 `ncmds=9` + 签名 408 B，不是"编译无错误 + codesign 通过"
2. **ncmds / 签名体积 / load command 列表都要核对**
3. **"能通过 configuration()" 可能是灾难**（P-49）

**通用形式**：任何"成功"的判断，**必须有一个运行时可观测的判据**，
不能停在"编译通过 / 工具返回 0 / 文件存在"。

4. **启动关键路径（kernel init → `exec launchd`）禁止大 IO**（P-112/P-114）：
   七次对照锁定——内核侧任何文件写入都死；**init 里写 124 B 安全（pid 276）**，
   但同一位置**拷 51 MB 就死（0 字节日志）**。
   ⇒ 判据是「这段路径上做同步大 IO」，不是「内核 vs 用户态」。
   小文件（<1 KB）可作探针；大文件（MB 级）必须挪到 launchd 之后、
   或 fork 后台进程、或异步。

5. **启动路径上禁止同步大 IO**（P-108）：在 `native_owner_data_prepare` 这类
   启动早期函数里同步拷贝 51 MB，会让 USB gadget 来不及枚举，结果是
   **日志 0 字节 + 复位**，看起来像内核崩了但其实是启动太慢。
   大文件要么在 init 之后做、要么异步、要么只在真缺时做一次。
5. **幂等逻辑要逐项判断缺什么**：不是"检查一个代表性文件就全跳过"，
   也不是"每次都全做"。P-107 漏了种子，P-108 又变成每次全拷，两个极端都错。

---


---

## ★26（HR-63）往文件系统放东西之前，先查构建脚本怎么放的

**来源**：P-115 / P-116（7 次死机实验）+ DATA-VOLUME-DEPLOY.md 的整个历史

**这条铁则解决的问题**：想让某个文件出现在设备上，第一反应是"在运行时写"，
这是错的。官方移植项目几乎都在**构建时**解决。

### 固定顺序（不许跳）

1. **查构建脚本的 Data/seed 入口**
   ```bash
   grep -n 'data_seed\|var\.seed\|var\.skel\|userdata\|data_image' userland/build.py
   grep -rn 'var-seed\|data-2g\|install.*ufs.*data' scripts/
   ```
2. **查 init 的消费侧**：`prepare_var()` 怎么解析 `var.skel`
   —— **把 `field[0][0]` 的所有分支都列出来**（`d`/`l`/`f`），
   不要看到第一个分支就下结论。
3. **查有没有现成的离线装载工具**
   ```
   scripts/data2g-install.sh        # Android 侧 dd 直写 unixnu
   scripts/install-pong-ufs-data.py # 官方同款
   scripts/build-pong-userdata-image.py
   ```
4. **只有以上都不成立时**，才考虑运行时写。而且必须遵守 ★20 第 4 条
   （启动关键路径禁止大 IO）。

### 硬性约束

- **`var.skel` 总大小 < 64 KiB**（init 里 `static char buf[65536]`）。
  目录条目便宜，文件条目要数着放。
- **`var.skel` 的 `f` 行源路径在密封根的 `/pong/var-seed/`**，
  也就是**构建时打进 OS 镜像**。运行时改不了。
- **不要指望 `mount("msdos", "/dev/md0")` 在启动路径上工作**：
  实测从 kernel 和 init 两个位置都试过，设备在 USB 枚举前复位（日志 0 字节）。

### 反例（本会话真实浪费）

| 做法 | 代价 |
|---|---|
| 在 `native_owner_data_prepare` 里 mount + 拷 | 4 次死机 |
| 在 init 里 mount + 拷 51 MB | 1 次死机 |
| 手写 `copy_one_file()` 循环 | 2 次编译失败（`snprintf`/`strcat` 不在 mini.h） |
| **读 `build.py data_seed()`** | **2 分钟，直接得到正解** |

---


---

## ★27（HR-64）改嵌入式二进制后必须查段表，不能只看文件大小

**来源**：P-117（7 次死机的真正原因）

**判据**：`__TEXT` 段 `filesize` 必须 ≤ 16,384（1 页）。
超了就 exec 失败，症状是**日志 0 字节 + 自动复位**，跟文件 I/O 无关。

### 每次改 init 后必跑

```bash
python3 - init <<'PY'
import struct, sys
d = open(sys.argv[1],'rb').read()
n = struct.unpack_from('<I', d, 16)[0]; off = 32
for _ in range(n):
    c, s = struct.unpack_from('<II', d, off)
    if c == 0x19:
        seg = d[off+8:off+24].split(b'\x00')[0].decode()
        fo, fs = struct.unpack_from('<QQ', d, off+40)
        if seg == '__TEXT':
            print('__TEXT filesize=%d %s' % (fs, 'OK' if fs <= 16384 else 'OVER 1 PAGE!'))
    off += s
PY
```

### 三条硬规则

1. **`__TEXT` 剩余量约 600 B**（35.5 KB 版实测：`__text` 9,692 + `__cstring` 4,141
   + `__const` 337 + `__entitlements` 237 + 头 1,344 = 15,751 / 16,384）。
   **加功能前先删等量死代码。**
2. **不调用的 `static` 函数照样参与编译并占 `__TEXT`**。
   删功能时必须连函数体一起删，注释掉调用没用。
3. **"0 字节日志"先查段表，再查其他**。这个症状在本项目被归因错过 3 次
   （P-108 同步大 IO / P-112 内核建文件 / P-114 启动路径大 IO），全是错的。

### 放不下时的出路

- 拆成多阶段：`init` + `/private/var/pong/init2`（init exec 它）
- 挪回内核侧（内核没有 `__TEXT` 单页限制）
- 大常量数组让编译器放 `__DATA`（去掉 `const`，或放 `__DATA,__const`）

---


---

## ★28（HR-65）「0 字节日志」先查日志开没开，再查代码

**来源**：P-118（2026-11-11 一天 8 次死机，全因缺 `debug=0x140`）

### 硬规则

1. **boot-args 里的日志相关项是红线，任何精简都不许动**：
   ```
   debug=0x140  applog=1  k60_console_export=1  k60_usblog=2  epoch=<固定值>
   ```
   缺任何一个 → 主机看到 0 字节，但内核可能活得好好的。
2. **看到 0 字节日志时的检查顺序**（不许跳）：
   ```
   ① args 里有没有 debug=0x140 / applog / k60_console_export / k60_usblog
   ② 与上一次成功启动的镜像 diff args（一行命令）
   ③ 才看内核/init/补丁
   ```
3. **每次刷机前必须与"黄金 args"对比**（gate.py 的 [A] 项强制执行）。
4. **`--force-new-series` 之类的手动放行，不能用于 args 红线**。

### 判别命令

```bash
# 从镜像提取 args 并与黄金集对比
mcopy -n -i <img> ::/EFI/UniXNU/unixnu.toml /tmp/x.toml
GOLD="debug=0x140 applog=1 k60_console_export=1 k60_usblog=2 epoch="
for t in $GOLD; do
  grep -q "$t" /tmp/x.toml || echo "❌ MISSING: $t"
done
```

### 为什么值得单独一条铁则

这一天我因为这一个缺失：
- 改了 init 二进制 6 次（`__TEXT` 跨页、`BUNDLE_FIXUP`、bundle 拷贝、mount 探针）
- 改了内核补丁 3 次（0404 写文件、只 audit、移除）
- 做了 8 次刷机实验
- 写了 P-117（`__TEXT` 单页）——**这条虽然是真实约束，但不是当时的死因**

**如果第一次看到 0 字节就去 diff args，这一切都不会发生。**

---


---

## ★32（HR-67）跟进上游必须覆盖「全部分支」，且必须能报「新增了什么」

**来源**：2026-11-11 用户两次纠正
1. 「他也在不断建新分支啊 岂不是可以继续抄 跟进上游的脚本要覆盖所有分支」
2. 「他可能会时不时建新分支 我想要的是及时同步他所有分支新commit」

### 当时的事实

- `yibiya-upstream` 镜像是**单分支 refspec**：
  `+refs/heads/upstream-fix:refs/remotes/origin/upstream-fix`
  → `git fetch --all` 永远只拉一个分支，其它 5 个分支（含当天新建的
  `fix/ui-startup-blob`，含 319 个我们 main 没有的提交）**从未下载**。
- `sync-all-repos-v2.sh` 里 `yibiya` 出现 0 次，脚本只做 fetch 不记录 SHA，
  所以即使拉到了也答不出「这次有什么新的」。

### 硬规则

1. **所有 `*-upstream` 镜像必须使用全分支 refspec**：
   ```bash
   git config remote.origin.fetch '+refs/heads/*:refs/remotes/origin/*'
   ```
   任何 `+refs/heads/<单个分支>:` 的写法都是缺陷。
2. **必须用 `fetch --all --prune`**，让上游删掉的分支本地也清掉。
3. **必须有增量状态文件**：`/mnt/e/k60-work/.upstream-branches.json`
   记录每个仓库每个分支上次看到的 SHA。判定：
   - 状态里没有的分支 → `[新分支]` + 列出最近 5 个提交
   - SHA 变了 → `[更新]` + 列出 `old..new` 全部提交
4. **唯一入口**：`python3 /mnt/e/k60-work/scripts/track-upstream-branches.py`
   已接入 `sync-all-repos-v2.sh`，每次同步自动跑。
5. **不要只看主分支**。2026-11-11 的教训：答案在 `fix/ui-startup-blob`
   的 `f291b52`（把 CFPreferences 从 constructor 移到主队列），
   而那个分支因为 refspec 限制从来没被下载过。

### 判别（30 秒）

```bash
# 每个镜像的 refspec 必须是全分支
for d in /mnt/e/k60-work/references/*-upstream; do
  printf '%-40s %s\n' "$(basename $d)" "$(git -C "$d" config --get remote.origin.fetch)"
done
# 出现 +refs/heads/<具体名字>: 就是缺陷
```

### 为什么值得单独一条铁则

我因为「只跟一个分支」错过了：
- `fix/ui-startup-blob`：319 个提交，含 backboardd 崩溃的直接修复
- `feat/first-frame-20261107`：GPU 第一帧、停掉刷屏的 0365、修 ~70s 复位的 0358/0364
- `UniXNU-pong-upstream`：8 个分支（含 ios16、native-ios18e、write-tracking）
- `pong-unixnu-upstream`：14 个分支

**上游不是一条线，是一棵树。只跟一条线等于闭着眼睛。**

---

# 第二章 规则正文（按编号）
## 铁则 1（HR-01）：**访问 RSC/RPMh 前必须确认 `ml_io_map` 成功 —— 原「RSC 禁止访问」是误诊**

> **2026-11-09 22:40 重大更正**：实测证明 RSC（`0x17a00000`）**完全可以安全读写**。

### 原错误结论（已作废）
> "RSC（`0x17a00000`/`0x17a20000`）首读整机死，禁止访问"

### 真相
驱动代码里：
```c
static vm_offset_t tlmm, gcc, se, rsc, cmd_db;
...
tlmm   = ml_io_map(TLMM_PHYS + gpio_offset, TLMM_SIZE) - gpio_offset;
gcc    = ml_io_map(GCC_PHYS, GCC_SIZE);
se     = ml_io_map(SE_PHYS, SE_SIZE);
cmd_db = ml_io_map_wcomb(CMD_DB_PHYS, CMD_DB_SIZE);
// ❌ 没有 rsc = ml_io_map(RSC_PHYS, RSC_SIZE);
```

**`rsc` 全局变量永远是 0**，于是：
```c
#define TCS(reg)  (rsc + 0xd00 + (reg))
wr(TCS(TCS_CONTROL), ...);   // 写物理地址 0xd00 -> data abort
```

**这不是「RSC 危险」，这是「空指针解引用」。**

### 实测证据（2026-11-09 22:40，内核 `d2eda50a`，镜像 `9d03cc26`）
```
Pong touch: stage10 rsc=0xfffffff188f59000 cmd_db=0xfffffff188f69000   ← 映射成功
goodix: rails on (ldoc2=0x42c00, AVDD gpio71=1)                        ← RPMh 写成功
系统正常到用户态，131,988 B 日志，无挂死
```

### 新铁则
1. **访问任何 MMIO 前必须先检查 `ml_io_map()` 返回值非 0**；
   返回 0 → 立刻打印并 `return`，**绝不能继续用该指针**。
2. **RSC/RPMh 是合法可用的**。RSC 基址：
   - `rsc@17a00000`，`reg = <0x17a00000 0x10000 0x17a10000 0x10000 0x17a20000 0x10000 0x17a30000 0x10000>`
   - `reg-names = "drv-0","drv-1","drv-2","drv-3"`
   - **`qcom,drv-id = <0x02>` → APPS 用 DRV 2 = `0x17a20000`**
   - `qcom,tcs-offset = <0xd00>`
3. 写 RPMh 前确认 `TCS_STATUS` 空闲，按 `rpmh_write()` 的完整序列
   （清 trigger/enable → 写 MSGID/ADDR/DATA → WAIT_FOR_COMPLETION → CMD_ENABLE → trigger → 轮询 IRQ_STATUS → 清理）。

### 教训
**「某地址不能访问」的结论，必须先排除「映射失败返回 0」这一层。**
一个未初始化的指针会让任何地址看起来都"致命"。这与 HR-14（存在≠完成）同源：
**把「表观现象」当成「根因」。**

## 铁则 2（HR-02）：**GENI 控制器（SPI/I2C）访问前必须完成完整前置序列**

### 违反后果
**整机死，零控制台输出**（死在 USB gadget 初始化之前，所以连日志都没有）。

### 必须的前置顺序（来自 sheng `TouchProbe.cpp:399-424`）
1. **GPLL0 投票 + 等 lock**（`GCC+0x62018` bit0，轮询 `PLL_MODE bit31`）
2. **QUP 分支投票**（`GCC_VOTE`，注意 **K60 是 QUP0 用 bit 6-14，不是 sheng 的 QUP1 bit 18-26**）
3. **等分支时钟离 off**，判定式必须含 HWCG（`!(cbcr & CLK_OFF) || (cbcr & 2)`）
4. **配置 TLMM 引脚功能**（在碰引擎**之前**）
5. **映射 SE + wrapper 两个窗**
6. 若 `IF_DISABLE_RO` bit0=1：需要 `use_dma` 或 `allow_fifo_disabled`

### SoC 地址禁止照抄 sheng
| 项 | sheng（SM8550）| **K60（SM8475）** |
|---|---|---|
| QUP wrapper | QUP1 `0xac0000` | **QUP0 `0x990000`** |
| 投票位 | 18-26 | **6-14** |
| GPLL0 enable | `0x52018` | **`0x62018`** |
| GCC 基址 | — | `0x100000` |

**关键**：sheng 在 QUP1 上验证过的「读 CORE 安全」**不能搬到 QUP0**。

### 证据出处
- `QcomGeniSpi/GeniSpi.h:211-212`（「the caller must know that」SE 时钟已在跑）
- `sheng/package/TouchProbe.cpp:399-424`
- `docs/research/GENI-ACCESS-PRECONDITIONS.md`（本文档的详细展开）

### 检查方法
```bash
grep -n 'geni_spi_init\|geni_transfer\|aw882xx_bus_init\|aw882xx_probe_one' <文件>
```
**命中 = 必须有对应的前置序列，且前置序列要在访问前执行完。**

### 已发生的违规（2026-11-09，两次）
| 驱动 | GENI | 结果 |
|---|---|---|
| 触摸 | SPI SE4 `0x990000` | 0 日志挂死 |
| 音频 | I2C `0x880000` | 0 日志挂死 |

---

## 铁则 3（HR-03）：**改任何 MMIO 访问前，先查该地址是否属于「已证明安全」集合**

### 违反后果
同上，整机死。

### 截至 2026-11-09 的实测状态
**已证明安全**（真机执行过且存活）：
```
GCC 窗口 0x1270004, 0x1270008, 0x1274dc, 0x1274e4, 0x1274e8, 0x1274f8, 0x162008
```

**从未执行过**（**新增访问 = 未知风险**）：
```
0x162018 (GPLL0 enable)
0x100000  (GPLL0 mode)
0x133000  (QUP0 CORE_CBCR)
0x13300c  (QUP0 CORE_2X_CBCR)
```

**禁止访问**：
```
0x17a00000, 0x17a20000 (RSC)
```

### 检查方法
```bash
# 列出你新增的所有 MMIO 偏移，逐个对照上面的清单
grep -oE 'gcc \+ 0x[0-9a-f]+' <文件> | sort -u
```

### 新增未知地址的正确做法
不要一次加多个未知访问。**一次只加一个**，上机验证存活后再加下一个。

---

## 铁则 4（HR-04）：**「0 日志」不等于「代码没跑到」——先验证 ring 是否存活**

### 原因
- 触摸/按键驱动在 `bsd_init.c` **1160 行**初始化，早于 `k60_usblog_start()`（**1340 行**）180 行
- 早期 printf 写入 ramoops ring，USB 起来后回放
- **但**：`K60PREV none` 表示 ring 在重启间**不存活**（DRAM 掉电）→ 挂死那次的 printf 永久丢失

### 因此
| 观测到的现象 | 真实含义 |
|---|---|
| 有日志，正常退出 | 代码跑到了，正常返回 |
| **0 日志** | 挂在 **USB 枚举之前**的任何位置，**无法从日志定位** |
| 有 `K60PREV none` | 上次启动的 ring 没保留（正常关机）|
| 有 `K60PREV begin` | 上次是热复位，ring 有内容（罕见）|

### 正确的诊断方法
**分段存活探测**：用 boot-arg 把代码分成 N 段，每段做到底就 return。
- 判据 = `capture.json` 的 `bytes`：**>100KB 活 / =0 死**
- 二分定位，不需要日志

### 检查方法
如果你准备「加 printf 看最后一行」——**先确认 ring 是否存活**（`grep K60PREV` 历史日志）。
如果不存活，改用分段探测。

---

## 铁则 5（HR-05）：**boot-args 必须从 payload 提取验证，不能看打包脚本源码**

### 原因
`packv15.sh` 里的 `G = ("...")` 只是**意图**，实际写进镜像的是 `/tmp/v15.toml` 的内容。
中间任何环节失败（mcopy 失败、模板被覆盖）都会导致「脚本看着对，镜像里是旧的」。

### 正确方法
```bash
ksize=$(python3 -c "import struct,io;print(struct.unpack_from('<I', io.open('$IMG','rb').read(), 8)[0])")
rat=$((4096 + ((ksize + 4095) / 4096 * 4096)))
dd if=$IMG of=/tmp/pay.img bs=1 skip=$rat count=201326592 2>/dev/null
mcopy -n -i /tmp/pay.img ::/EFI/UniXNU/unixnu.toml /tmp/toml.txt
python3 -c "
import io,re
s=io.open('/tmp/toml.txt',encoding='latin1').read()
m=re.search(r'args\s*=\s*\"([^\"]*)\"', s, re.S)
print(len(m.group(1).split()), 'tokens')
"
```

### 已发生的违规
曾验证出 `boot-v15` 镜像实际是 **25 tokens 含 `k60_touch_se=1`**（危险版本），
而 `packv15.sh` 当时显示 24 tokens 无 `touch_se` —— 差点上传了挂死镜像。

---

## 铁则 6（HR-06）：**补丁必须从「真实树」生成，不能手写 hunk**

### 违反后果
- `corrupt patch at line N`
- `unterminated conditional directive`
- 补丁 apply 后丢行（`#endif` 被吞）

### 正确流程
```bash
# 1. clone 一份干净 feed
git clone --shared --no-checkout <feed> /tmp/regen
git -C /tmp/regen checkout --detach <base-commit>
# 2. 按 series 顺序 apply 到「目标补丁的前一条」
# 3. 在真实文件上做编辑
# 4. diff -u 生成补丁
# 5. git apply --check 验证
```

### 补丁插入位置
**新补丁必须放在 series 末尾**，因为它的上下文是按「全部前序补丁应用后」生成的。
插在中间会让后续补丁 apply 失败。

### 已发生的违规（≥4 次）
手写 `@@` 计数导致 `#endif` 被吞、patch 体积从 931 行变 364 行等。

---

## 铁则 7（HR-07）：**series 引用的每个文件必须真实存在且已提交**

### 违反后果
**任何干净 clone 都无法构建。**

### 已发生的违规（2026-11-09 发现）
`patches/xnu/series:195` 引用 `0403-k60-goodix-fw.patch`，该文件**从未提交过**
（commit `6c1e1f1` 只加了 series 那一行）。

### 检查方法（每次改 series 后必须跑）
```bash
cd <repo>
while read -r f; do
  [ -z "$f" ] && continue
  git ls-tree HEAD "patches/xnu/$f" | grep -q . || echo "❌ 未提交或不存在: $f"
done < patches/xnu/series
```

---

## 铁则 8（HR-08）：**构建日志不动 ≠ 构建卡住**

### 原因
`make -j8` 缓冲输出，XNU 的 make 到结束才刷。

### 检查方法
```bash
pgrep -af 'make.*build_all' | head -1   # 有进程 = 在编译
```
**不要**看 `/tmp/build-v15.log` 的 mtime。

---

## 铁则 9（HR-09）：**UI/显示层「已工作」的东西，不要为了「用官方组件」而重写**

### 背景
官方依赖顺序表要求用 `GopFramebuffer` / `DisplayTimingProbe` / `AppleARMBacklight` / `GeniI2c`，
但我们自研的显示层**已在真机验证**：首帧 1440×3200 + 背光 + 120Hz + SpringBoard。

### 规则
- **已 device-verified 的能力**，除非官方组件能解决**具体缺陷**，否则**不动**
- 换组件前必须回答：「现有实现有什么具体问题？官方组件如何解决？」
- 答不出来 = 不换

---

## 铁则 10（HR-10）：**任何「已解决」的结论必须带真机证据，否则标「推断」**

### 禁止的表述
- 「应该能工作」
- 「官方验证过所以我们也行」（SoC 不同，见 HR-02）
- 「代码看起来对」

### 必须的表述
| 级别 | 要求 |
|---|---|
| `device-verified` | 有真机日志/截图，带日志路径 + 行号 + 镜像 sha256 |
| `host-verified` | 有真实编译输出（`rc=0`），不是 `-fsyntax-only` |
| `implemented` | 代码/补丁存在且 apply 干净 |
| `planned` | 只有设计 |
| **推断** | 只有逻辑链，**不得作为动手依据** |

### 官方校验器接受的五个值
`planned` / `implemented` / `host-verified` / `device-verified` / `not-applicable`
（`UniXNU/scripts/porting-record.py` 硬编码）

---

---

## 铁则 11（HR-11）：**区分「构建产物」与「设备盘上状态」**

### 为什么要这条
2026-11-09 审计 agent 搜索 60 个 `boot-*.img` 发现 TWRP 命中 0，
据此判定「TWRP 不可得，可复现性 C 级」。**这个判定是错的。**

真实情况：**TWRP 在设备盘上的 `boot` 分区里**，`fastboot reboot recovery` 就能进。
它不是我们的构建产物，是第三方独立刷入的。

### 规则
搜索某能力是否存在时，必须明确范围：

| 范围 | 决定什么 |
|---|---|
| **构建产物**（`boot-*.img`、`out/`）| 「别人从这个仓构建能拿到什么」|
| **设备盘上状态**（`/dev/block/by-name/*`）| 「维护者这台机器能做什么」|

**用构建产物否定设备能力 = 口径错误。**

### 检查方法
在断言「X 不存在」之前，明确回答：
1. 我搜的是构建产物还是设备盘上？
2. 如果搜的是构建产物，这个能力是否**本来就应该**在盘上（如 TWRP、已格式化分区）？
3. 有没有可能它是「前置条件」而非「构建产物」？

### 已发生的违规
`repro-audit/RISKS.md` §R7 判定 TWRP 不可得（C 级）→ 实际是 B 级（标准刷入操作）。
详见 `docs/TWRP-FACT-CLARIFICATION.md`。

---

## 铁则 12（HR-12）：**派任务/写代码前必须核实「已知前提」，标证据来源和日期**

### 为什么要这条
2026-11-09 派了 5 个 subagent，**3 个推翻了任务书的前提**。不是 agent 出错，
是任务书基于**过时或错误**的假设，导致 agent 花大量时间纠正而非推进。

| Subagent | 任务书写的前提 | 实际（带证据） |
|---|---|---|
| `5898cb8e` OS/电源 | 「DarwinBoot 落后官方 129 行」 | 2539/2829 是**字节**不是行；我们 `DarwinBoot.c` **反而多 28 行**（739 vs 711）|
| `7fe96011` SMMU | 「我们有三份自己写的 SMMU」 | `pong_goodix.c` **零行 SMMU**（5 份副本实测 `smmu=0`）；官方 `ArmSmmu4K` **已在 `drivers/PongAdreno/` 里被编译使用** |
| `7fe96011` 显示 | 「K60 没有 GOP」 | **有**（`SimpleFbDxe` 在 `APRIORI.inc:29`、`DXE.inc:45`）；不适用的理由不同 |
| `77f4d518` 基带 | 「K60 没有 GLINK/QRTR/SMEM」 | **DT 层全在**（`qcom,smem` FDT:11809、`smp2p-modem` 11924、`glink-edge` 11309-11351、`mpss_region` 173-176），缺的是**代码** |

### 规则

**派 agent 前**，对每一个「已知 X」问三句：
1. **证据在哪？**（文件:行号 / 日志行 / commit / sha256）
2. **什么时候的？**（是否可能已过时）
3. **范围对吗？**（构建产物 vs 设备盘上，见 HR-11）

**证据不全的前提，任务书里必须写「待核实」而不是「已知」。**

### 检查方法
任务书里每个「已知/确认/已证实」的断言，后面必须有括号标注：
```
（证据：<文件>:<行号> 或 <日志路径>:<行号>，<日期>）
```
**没有标注的，一律改成「待核实」。**

### 同理适用于写代码
改代码前如果基于某条「已知」，先 `grep` 验证。本轮 `touch_thread` 里
`ml_io_map(RSC_PHYS,...)` 就是因为没核对「RSC 禁止访问」（HR-01 已记录 5 处研究文档），
浪费了 4 轮排查。

### 已发生的违规
- 2026-11-09：5 个任务书里 3 个前提错误
- 2026-11-09：`touch_thread` 违反 HR-01，4 轮排查作废

---

## 铁则 13（HR-13）：**结论必须区分「软件层声称」与「硬件层实测」**

### 为什么要这条
本轮把「120Hz 生效」当成结论写进 `HANDOFF.md`，但实际只是 **`refreshHz()` 返回 120**。
没有发任何 DSI 切档命令（`PongDsiPanel.cpp` 只发 `0x11/0x29/0x51`）。

### 规则
| 表述 | 需要的证据 |
|---|---|
| 「硬件 X 生效」 | 硬件侧测量：示波器 / 面板自报告 / 寄存器回读确认切换 |
| 「软件层按 X 配置」 | 代码路径 + 日志打印 |
| 「日志显示 X」 | 日志原文 |

**禁止**：用「软件层打印了 X」直接推「硬件 X 生效」。

### 检查方法
每写一句「XX 生效/工作/成功」，问：
- 这是**软件发生了什么**，还是**硬件发生了什么**？
- 如果是硬件，**测量手段是什么**？

### 已发生的违规
2026-11-09：「120Hz 生效」→ 实际是软件排帧，面板扫描率未验证。
已记入 `PITFALLS.md` **P-60**。

---

## 附：本文件与其他文档的关系

| 文档 | 用途 | 权威性 |
|---|---|---|
| **本文件（HARD-RULES.md）** | 绝对禁止清单 | **最高** |
| `PITFALLS.md` | 踩过的坑（症状→根因→修复） | 高 |
| `docs/research/<hw>/01-08` | 各硬件八步调研 | 中（可能过时）|
| `HANDOFF.md` | 交接状态 | 中 |
| `porting.toml` | 官方格式的能力记录 | 高（受官方校验器约束）|

**冲突时以本文件为准。**

---

## 维护规则

1. **每条铁则必须有**：违反后果 + 禁止范围 + 检查方法 + 已发生违规
2. **每次踩到新坑**，先判断是「新坑」还是「某条铁则的违反」
   - 是违反 → 在该铁则下追加「已发生违规」
   - 是新坑 → 先加进 `PITFALLS.md`，若它属于「绝对禁止」类，**同时加进本文件**
3. **禁止重排编号**（外部文档有引用）

## 铁则 14（HR-14）：**subagent 的交付物目录存在 ≠ 交付完成，必须等它的完成消息**

- **症状（2026-11-09 21:33，我犯的）**：
  看到 `impl/touch-power/` 下有 5 个文件（含 `PMIC-RESEARCH.md`、`SPMI-WRITE-PLAN.md`），
  就当成"subagent 已完成"，并据此向用户汇报结论。实际 **`EVIDENCE.md` 6 秒前还在写**，
  subagent 仍在工作，交付物是**半成品**。

- **铁则**：
  **只有收到 subagent 的「完成消息」（`background subagent ... finished` 或
  `Agent <id> sent a message: ...完成...`）才算交付。**
  在收到之前：
  1. 可以读它的文件作为**参考资料**，但**不得当作结论汇报**
  2. **不得基于它改代码**
  3. 汇报时必须写明「该 agent 仍在运行，结论未定」

- **判定方法（30 秒）**：
  ```bash
  ls -l --time-style=+%H:%M:%S <交付目录>   # 看 mtime
  date +%H:%M:%S                          # 与当前时间比较
  ```
  **若最新文件 mtime 在最近 2 分钟内 → 仍在写 → 不是最终交付。**
  更可靠：等 `finished` 消息。

- **为什么我会犯**：文件存在给了"已完成"的错觉。但 agent 是边写边存的，
  目录结构在任务开始几分钟后就出现了。

- **关联**：HR-11（build artifact ≠ on-device state）是同一类错误——
  **把"某物存在"当成"某事已完成"**。HR-14 是它在 subagent 场景的实例。

## 铁则 15（HR-15）：**任何硬件移植的第一步是读完 unixnu.com 官方对应页面**

- **症状（2026-11-09 22:52，用户指出）**：
  触控/WiFi/蓝牙/音频/电源/GPU 五个硬件都做了大量"调研"，
  **但没有一篇文档引用 `unixnu.com/zh/porting/*` 的官方页面**。
  直到用户贴出 `https://unixnu.com/zh/porting/power#audio` 才去读。

- **官方页面清单（每个硬件都有）**：
  | 硬件 | 页面 |
  |---|---|
  | 适配顺序 | `/zh/porting/drivers` |
  | 平台与内存 | `/zh/porting/platform` |
  | UFS | `/zh/porting/ufs` |
  | 显示与亮度 | `/zh/porting/display` |
  | 触控、按键与键盘 | `/zh/porting/input` |
  | GPU 与 Metal | `/zh/porting/gpu` |
  | Wi-Fi | `/zh/porting/network` |
  | 蓝牙 | `/zh/porting/bluetooth` |
  | USB | `/zh/porting/usb` |
  | 基带 | `/zh/porting/baseband` |
  | DSP、音频与电源 | `/zh/porting/power` |
  | 组件选择 | `/zh/reference/components` |
  | 设备树 | `/zh/porting/device-tree` |
  | 固件集成 | `/zh/porting/uefi-firmware` |

- **铁则**：
  1. **移植任何硬件前，先 `web_fetch` 对应官方页面，把「源码与接口」「适配步骤」「预期结果」逐条抄进调研文档**
  2. 官方页面里点名的参考源码（`TouchProbe.cpp`、`QcomRpmh.c`、`CpuFreqProbe.cpp`、`AudioProbe.cpp`、`ShengBattmgr.c` 等）**必须在本机找到并逐段对照**
  3. 官方页面的**步骤编号就是验收顺序**（例：input 页 6 步 = 窗口/电源复位/DMA/芯片ID+固件/坐标/多点）
  4. 没有引用官方页面的调研文档，**视为未完成**

- **为什么重要**：官方页面直接给出了本机已有的参考实现路径。
  例如 input 页第 2 步"实现电源/复位控制"、power 页"`QcomRpmh.h` 资源投票"，
  都是我们反复试错后才发现的。

## 铁则 16（HR-16）：**八步流程的每一格都必须同步写出「依据」——没有依据的判定一律无效**

- **用户要求（2026-11-09 22:55 原话）**：
  > "之前官方文档也调研过很多次了，结果次次核实八步流程读都不读？
  >  每次八步流程的依据也需要同步写出 这是铁则"

- **铁则**：
  1. **任何八步状态表，每一格（①–⑧）必须带「依据」列**，格式：
     `✅/◐/❌ | 依据 = <官方URL | 文件:行号 | 日志文件:行号 | 实测命令输出>`
  2. **②「官方文档」格的依据必须是 `https://unixnu.com/zh/porting/<page>` 的 URL + 引用段落标题**，
     不能写"已调研"、"参考官方"这类空话。
  3. **判定为 ✅ 的格，必须至少有 1 条「实测」级依据**；
     只有文档依据的，最高只能标 ◐。
  4. **判定为 ❌ 的格，必须写明「缺什么」以及「在哪里找」**。
  5. 没有依据列的八步表，**视为未完成，不得用于决策**。

- **反面案例（本会话）**：
  | 项 | 错误做法 | 正确做法 |
  |---|---|---|
  | 触摸 ② | 只列了 `02-official-docs.md`，**从未引用 unixnu.com/zh/porting/input** | 必须写 `https://unixnu.com/zh/porting/input` + "第2节 适配板级路径 6 步" |
  | WiFi ② | 只查了 `components.toml` | 必须写 `https://unixnu.com/zh/porting/network` |
  | 电源 ② | 只查了 `docs/porting/power.md` 本地副本 | 必须写 `https://unixnu.com/zh/porting/power` |
  | GPU ② | 只查了 `GPU-ENABLE-PLAN.md` | 必须写 `https://unixnu.com/zh/porting/gpu` |

- **输出模板（强制）**：
  ```
  | 步 | 判定 | 依据 |
  |---|---|---|
  | ① 同型 | ✅ | `impl/xxx/01-same-hardware.md:9` (7 机型表) |
  | ② 官方 | ✅ | https://unixnu.com/zh/porting/input §2「适配板级路径」6 步 + 官方源码 TouchProbe.cpp |
  | ③ 反编译 | ◐ | live FDT `95c02052…` + `goodix_ts.ko` 未取 |
  | ④ 广域 | ✅ | `WIDE-VALIDATION.md` 12 条多源 |
  | ⑤ 方案 | ✅ | `PLAN.md` 三候选对比 |
  | ⑥ 深挖 | ✅ | `DEEP-DIVE.md` 5 轮 |
  | ⑦ 核验 | ✅ | `VERIFICATION.md` 34 条 M/D/I |
  | ⑧ 上机 | ✅ | `usblog-20261109-225138:335` 实测 |
  ```

### HR-16 补充：**两个「八步」是不同概念**

- **官方八步 = 硬件依赖顺序 1→8**（`https://unixnu.com/zh/porting/drivers` §2）
  1 平台/内存/DMA → 2 UFS → 3 显示 → 4 触控/按键 → 5 GPU → 6 WiFi/蓝牙/USB → 6a 基带 → 7 DSP/音频/电池/电源 → 8 OS服务/打包
- **自编八步 = 单硬件调研流程 ①→⑧**
  ① 同型项目 ② 官方文档 ③ 反编译+真机数据 ④ 广域验证 ⑤ 方案 ⑥ 深挖 ⑦ 核验 ⑧ 上机

**两者必须分开建表、分别写依据**：
- `docs/OFFICIAL-8STEPS.md` —— 官方八步
- `docs/EIGHT-STEP-EVIDENCE.md` —— 自编八步（每硬件一张）

**禁止把两者混在一张表里。**

### HR-15 补充：**官方文档先查本地副本，但必须同时验证时效性**

- **用户要求（2026-11-09 23:15 原话）**：
  > "注意 查本地文档也要确保时效性 本地文档不一定及时同步了官方上游最新版"

- **强制三步（缺一不可）**：
  ```bash
  # 第 1 步：看本地是否存在
  ls E:/hackios/UniXNU/docs/zh/porting/

  # 第 2 步：必须验证本地是否落后上游（关键！）
  git -C E:/hackios/UniXNU fetch
  git -C E:/hackios/UniXNU rev-list --count HEAD..@{u}      # >0 = 落后 N 个提交
  git -C E:/hackios/UniXNU log --oneline HEAD..origin/main  # 落后哪些

  # 第 3 步：落后时读 origin/main 的最新版（不破坏工作区）
  git -C E:/hackios/UniXNU show origin/main:docs/zh/porting/ufs.md
  ```

- **判定规则**：
  | 情况 | 做法 |
  |---|---|
  | 本地存在且 `HEAD..@{u} == 0` | ✅ 直接读本地 |
  | 本地存在但落后 | ⚠️ **必须读 `origin/main:path` 的最新版**，不能只用本地 |
  | 本地不存在 | 才 `web_fetch` |

- **本次实例（2026-11-09 23:12）**：本地 `UniXNU` HEAD `75ae626`（11-07），
  上游 `95ad781` —— **落后 10 个提交**。其中：
  - `f7f9f7a` = UFS 并发官方方案（`RootTransportLayout.h` / `hostIssue` / `hostAwait` / 零拷贝 PRDT / 缓存行陷阱 / 200µs 轮询）
  - `6ae5f83` + `a443832` = **AdrenoMetal 更新**（用户明确提到的"GPU 驱动有更新，性能有优化"）
  - `56afc53` = RamBlock 并发 Direct Data 请求

  **如果只读本地，就会完全错过这些更新。**

- **额外注意**：`UniXNU` 仓库当前有未合并冲突
  （`UU drivers/AppleKeyStoreState`、`UU drivers/ArmCpu`），
  **不能 `git pull`**，只能 `git show origin/main:<path>` 读。

- **症状（2026-11-09 23:10，用户指出）**：
  查官方文档时我一直在 `web_fetch https://unixnu.com/...`，
  **而本地 `E:\hackios\UniXNU\docs\zh\porting\` 就有全部 26 个页面**。
- **本地路径**：
  | 内容 | 路径 |
  |---|---|
  | 中文 porting 页 | `E:\hackios\UniXNU\docs\zh\porting\`（26 篇）|
  | 英文 porting 页 | `E:\hackios\UniXNU\docs\porting\` |
  | 驱动页 | `E:\hackios\UniXNU\docs\drivers\` |
  | 组件定义 | `E:\hackios\UniXNU\components.toml` |
  | 设备记录 | `E:\hackios\UniXNU\docs\.vitepress\device-records\` |
- **铁则**：
  1. **先 `ls E:\hackios\UniXNU\docs\zh\porting\`，读本地文件**
  2. **再 `git -C E:\hackios\UniXNU fetch && git rev-list --count HEAD..@{u}` 检查是否落后上游**
  3. 只有本地没有的页面才 `web_fetch`
  4. **每次读文档前都要先检查上游是否更新**（本会话曾落后 10 个提交，
     其中 `f7f9f7a` 正是 UFS 并发方案、`6ae5f83`/`a443832` 是 AdrenoMetal 更新）
- **教训**：本地有副本还上网抓，既慢又可能拿到与本地不一致的版本。

## 铁则 17（HR-17）：**动外部资源前先查可用性**

- **用户原话（2026-11-10 00:31）**："mac现在其他agent在操作 暂时离线" / "mac已恢复"
- **铁则**：任何依赖外部机器（Mac / 设备 / 网络）的操作前，**必须先探活**：
  ```bash
  timeout 15 sshpass -p '<pw>' ssh -o ConnectTimeout=8 <user>@<host> 'echo OK' || echo OFFLINE
  ```
  探活失败 → 换路径或等待，**不要在离线机器上排计划**。
- **本次实例**：Mac 曾被其他 agent 占用离线，恢复后立即可用（`hdiutil` 可用）。

## 铁则 18（HR-18）：**"先查" —— 任何行动前先做最小查证**

- **用户原话（2026-11-10）**："先查"
- **铁则**：在写代码 / 刷机 / 下结论之前，**先做一次最小查证**：
  | 场景 | 最小查证 |
  |---|---|
  | 要改驱动 | `grep` 确认函数是否已存在（本会话两次因 `k60_spmi_init` 不存在而编译失败）|
  | 要用工具 | `ls` 确认工具在本地（本会话一直在 web_fetch 官方文档，而本地 `E:\hackios\UniXNU\docs\zh\porting\` 就有 26 篇）|
  | 要用外部机器 | SSH 探活 |
  | 要写分区 | 先读头部确认 APFS 结构，不要整盘读写 |
  | 要下结论 | 先验证前提（本会话"INT=0 说明芯片活着"因默认下拉而作废）|
- **30 秒判定**：任何"我准备做 X"之前，先问"X 的前提我验证了吗？"

## 铁则 19（HR-19）：**写驱动前必须完成八步 ③（Android 侧反编译取证）**

- **教训（2026-11-10 用户指出）**："所以之前八步流程铁则根本就没遵守" —— 触摸 stage 8-15 全错，
  因为跳过了 ③，把 pong 的 Berlin-D 协议直接套在 K60 的 M11A(GTP) 芯片上。
- **铁则**：任何硬件的 ⑤ 方案之前，③ 必须完成且落档：
  ```bash
  adb shell cat /proc/device-tree/<节点>/compatible     # 芯片型号
  adb shell ls /sys/class/input/event*/device/name      # 驱动名
  adb pull /vendor/lib/modules/<驱动>.ko               # 拉 .ko
  llvm-objdump -d <驱动>.ko | grep -A20 '<读写函数>'     # 拿协议帧格式
  ```
- **判据**：③ 产出（芯片型号 + 协议帧格式 + 寄存器地址）写进 `EIGHT-STEP-EVIDENCE.md` 后，
  才允许写驱动代码。

---

## HR-20 任何硬件动作前必须跑 `hw-preflight.sh`

**背景**：HR-15/HR-16 都只是"要求"，而本会话已经被证明——**只靠要求必然失忆**。
光触摸一项就因未查 `UniXNU-zizhan` 白耗 20+ 轮（P-76）。

**规则**：对任何硬件做**改代码 / 构建 / 刷机**之前，必须先执行：

```bash
wsl -u root -e bash <workspace>/scratch/hw-preflight.sh <硬件名>
# 例：hw-preflight.sh touch
#     hw-preflight.sh bluetooth
#     hw-preflight.sh wifi
```

**脚本强制做四件事，全部通过才打印 `PREFLIGHT OK`：**

1. **拉取**所有参考仓库到最新（`git pull --ff-only`，含 `UniXNU-zizhan` 超集）
2. **盘点**本地所有该硬件相关产物（zizhan / pong / sheng / 官方文档 / impl 目录）
3. **校验**是否读过（对照 `impl/<hw>-8step/` 下是否有 ③④ 文档）
4. 打印**必须先读的文件清单**

**没有 `PREFLIGHT OK` 就动手 = 违反 HR-20。**

---

## HR-21 硬件实现优先级：抄 zizhan → 抄 pong → 抄 sheng → 自研

**背景**：`UniXNU-zizhan` 是 **pong 的超集**（用户 2026-11-10 明示），
615 文件 / 21 个 xnu 补丁，覆盖 CPU/平台/UFS/RAM/显示/GPU-Metal/触摸/电源/WiFi/音频。

**优先级固定为：**

| 优先级 | 来源 | 说明 |
|---|---|---|
| 1 | `UniXNU-zizhan` | 同 SM8475，最接近，21 个补丁已公布验证 |
| 2 | `UniXNU-pong` | zizhan 的上游，SM8475 |
| 3 | `UniXNU-sheng` | Novatek 触摸参考，**但自己声明未在设备验证**（`TouchProbe.cpp:7-8`）|
| 4 | 官方组件 `UniXNU/drivers/*` | `QcomGeniSpi` / `ShengNovatekTouch` 等 |
| 5 | 自研 | **只有在 1-4 都确认无覆盖时才允许** |

**用户明示（2026-11-10）**：
> "全面转向抄zizhan的仓库修复所有硬件。zizhan没驱动的硬件就先不要重复造轮子了，否则就是浪费时间"

**即：zizhan 没有的硬件，先跳过，不重造轮子。**

---

## HR-22 ③ 反编译必须逐层做全（芯片/控制器/电源/板级）

见 P-80。四层缺一不可：

| 层 | K60 对应 |
|---|---|
| 芯片协议 | `goodix_core.ko`、`xiaomi_touch.ko` |
| **控制器** | **`spi-msm-geni.ko`、`i2c-msm-geni.ko`**（本会话曾完全遗漏）|
| 电源/时钟 | dts regulator / clock 节点 |
| 板级 | live FDT |

---

## HR-23 物理地址与虚拟地址严格分离

见 P-78。

- 物理地址常量**必须**以 `_PHYS` 结尾
- `_PHYS` 只允许出现在 `ml_io_map()` 的参数位置
- 所有 `rd()/wr()` 只接受映射后的虚拟变量
- 违反 = 必然 data abort（本会话已犯 2 次）

---

## HR-24 分区镜像必须"一步到位"构建，禁止缝缝补补

**用户指令（2026-11-10）**：
> "unixnu分区总是缝缝补补，正确方法应该是构建分区镜像的时候一步到位弄全再写入设备啊"

### 禁止的做法

| 反模式 | 后果 | 本会话实例 |
|---|---|---|
| 先 dd 一个文件，再 dd 另一个文件 | 状态漂移、部分更新 | `pong/init` 单独 dd、GPU bundle 单独塞 |
| 在设备上改完再往回同步 | 设备与源不一致 | D/E 双树漂移 P-73 |
| 每次只追加一项，靠"下次补" | 永远补不完 | 触摸 20+ 轮逐个寄存器试 |

### 正确做法：单一构建脚本产出完整镜像

**一次构建必须产出：**

| 产物 | 内容 |
|---|---|
| `kernel.macho` | 内核（含全部补丁）|
| `kernelcache` | 生成/校验后的缓存 |
| boot image | 内核 + ADT + boot-args |
| **unixnu APFS seed（完整）** | `/private/var/pong/` 下**全部**内容：`init`、`PongAdrenoMetal.bundle/`、`libvulkan_freedreno.dylib`、`Info.plist`、配置 |
| Data 窗口镜像 | 从 seed 展开，**一次 dd 写入** |

**判据：** 单条命令 `./build-all.sh` 跑完 → 直接 `fastboot boot` + 单次 `dd` 写 Data → 中间不再有任何手工补写。

### 实施要求

1. **seed 内容用清单驱动**，不用手写路径：
   ```
   seed-manifest.txt   # 每行一个 源路径 -> 目标路径
   ```
2. **构建后校验**：`apfs.py ls` 必须能列出清单里每一项，缺一项就 fail build
3. **写入只做一次**：`dd` 命令写在脚本里，产出带 sha256 的最终镜像
4. **启动前自检**：boot-args 与镜像内容由同一份配置生成，不允许手工改 boot-args

### 当前状态

- `scratch/packv15.sh` 只做 boot image
- Data seed 靠 Mac 上 `k60-make-data-seed.py` + `hdiutil`（分步执行）
- **需要统一为 `build-all.sh`**（待建，见 BACKLOG）

---

## HR-25 `yibiya/UniXNU-mondrian` 是 madatory 参考源（2026-11-10 用户指定）

**用户指令**：
> "https://github.com/yibiya/UniXNU-mondrian/commits/upstream-fix/ 这是fork我们的仓库
>  他今天的新commit看看能否当作参考"
> "今后这个仓库也要当成参考源之一 记住"

### 仓库

| 项 | 值 |
|---|---|
| URL | `https://github.com/yibiya/UniXNU-mondrian` |
| 关注的 branch | **`upstream-fix`**（随时可能有新提交）|
| 性质 | **我们自己 `UniXNU-mondrian` 的 fork**，同设备 K60 |
| 价值 | 同设备另一条实现路线，可能已解决我们卡住的问题 |

### 强制要求

1. **HR-20 的 `hw-preflight.sh` 已加入此仓库**：每次硬件工作前自动 `fetch` 并列出
   相对我们 HEAD 的新提交
2. **每次会话开始、以及每次"卡住超过 2 轮"时，必须检查 `upstream-fix` 有无新提交**
3. 有新提交 → 先读 diff，再决定是否继续自己的路线

### 与 HR-21 优先级的合并

更新后的参考优先级：

| 优先级 | 来源 | 说明 |
|---|---|---|
| **0** | **`yibiya/UniXNU-mondrian` `upstream-fix`** | **同设备 fork，最可能已有答案** |
| 1 | `UniXNU-zizhan` | 同 SM8475 超集，21 补丁已发布验证 |
| 2 | `UniXNU-pong` | zizhan 上游，SM8475 |
| 3 | `UniXNU-sheng` | Novatek 触摸参考（未设备验证）|
| 4 | 官方组件 `UniXNU/drivers/*` | QcomGeniSpi 等 |
| 5 | 自研 | 仅当 0-4 都确认无覆盖 |

---

## HR-26 调研与排障必须整篇读取，禁止反复 grep 片段

**触发场景（2026-11-10 用户当场纠正）**

我在排查触摸帧问题时，对 `references/ruby-bringup/docs/touch-goodix-9916r.md`
（291 行）反复执行：

```
grep -n -A12 'CONF' ...
grep -n '0x10308' ...
sed -n '/## 5.3/,/## 6/p' ...     ← 只取一节
grep -nE 'bitbang|spi_xfer' ...
```

结果：**读了 6 次，仍然漏掉了第 7、8 节里的关键信息**——
而 §7 的 bring-up 记录表和 §8 的调试清单，恰好直接命中我当时的问题。
用户质问："你为什么不能一次性读完文档？"

**事实：291 行的文档，`cat` 一次的成本远低于 6 次 grep。**

**铁则（强制）**

1. **判断"要不要整篇读"**：
   - 文档 **< 500 行** → **必须整篇读**，禁止先 grep
   - 文档 **500–2000 行** → 先 `wc -l`，再整篇读（可分批，但必须读完全部）
   - 文档 **> 2000 行** → 先读目录/章节标题（`grep -n '^#'`），然后**整章读**，
     不允许跨章跳着 grep

2. **代码文件同样适用**：
   - 目标函数/结构 **< 300 行** → 一次 `sed -n 'a,bp'` 读完整函数
   - 不允许"读两行实现 + 猜其余"

3. **一个文件一次会话内最多 grep 两次**；第三次之前必须整篇读。

4. **调研参考实现时，先列文件清单 + 大小**，再按大小决定读法：
   ```
   find . -name '*.md' -o -name '*.patch' | xargs ls -l   # 先看规模
   ```

5. **禁止的行为**：
   - 用 grep 结果"拼出"对文档的理解
   - 只读某一节就下结论
   - 同一文件重复 grep 同一关键词的不同上下文

**为什么这条重要**

grep 只能验证"我已经想到的假设"，**无法发现我没想到的东西**。
真正的答案往往在我没 grep 到的那一节。整篇读才能看到
"bring-up 记录表里别人踩过的同一个坑"。

**成本对比（实测）**

| 做法 | 工具调用 | 获得信息 |
|---|---|---|
| 6 次 grep | 6 次往返 | 遗漏 §7/§8 |
| 1 次 sed 150,400p | 1 次往返 | 全部 291 行 |

**执行检查**：读参考文档前，先 `wc -l`；< 500 行就直接整篇 `sed -n '1,$p'`。

---

## HR-27 排障必须先抄完参考文档的调试清单，逐条执行，禁止跳步

**触发场景（2026-11-10 用户两次当面纠正）**

ruby 文档 `touch-goodix-9916r.md` §8「调试清单」有 8 条，我读了，
但**从未按顺序执行**，而是直接跳到第 6/7 条去猜帧地址。

**那份清单的前三条，恰好就是根因所在：**

```
1. I2C5 空闲时 SCL/SDA 都为 1；否则先查 pinmux/输入使能。
2. 读 LDO3/LDO2 EN/VOUT；旧值通常是 0x80/0xB0、0x80/0x40。
3. 写 VOUT 后回读必须是 0x3A/0xD0；EN 使能后应为 0xC4。
```

而 §3.2 明确写着：

> **「只写 enable 位会让 AVDD 欠压，芯片完全不启动；这也是 P1f/P1g
> 一直读到全 0 的原因。」**

**我从来没有真正读回过 VOUT 值。** 每次都是「写进去了 → 假设生效」。

**铁则（强制）**

1. **拿到参考文档后，第一件事**：把它的「调试清单 / 检查项 / bring-up 记录」
   **原样抄成一份本地 checklist 文件**（`docs/<TARGET>-CHECKLIST.md`），
   每条保留原文 + 编号 + 判据。
2. **严格按编号顺序执行**，每条都要填：
   - `做了什么`（具体命令/代码）
   - `实测值`（原始数据，不是"应该"）
   - `判据`（文档原文的期望值）
   - `结论`（PASS / FAIL / 未执行）
3. **清单未走完之前，禁止改代码**。想改代码必须先指出"清单第 N 条 FAIL"。
4. **每轮结束必须更新 checklist 文件**，让上下文压缩后能靠文件恢复真实进度。

---

## HR-28 禁止"改成 X 试试"——每个改动必须能指出文档依据

**触发场景（2026-11-10）**

ruby 文档 §5.3 白纸黑字写着：

> **「触摸数据地址 `0x10308`。」**

我把 `touch_address` 从 `0x10308`（misc+44）改成 `0x10400`（misc+24），
理由只有一句「0x10400 在变」。**这是没有文档依据的改动，已撤回。**

**铁则（强制）**

**任何"试试看"的改动，提交前必须能回答：**

| 问题 | 要求 |
|---|---|
| 这个改动的参考依据在哪？ | `文件:行号` 或 `文档 §章节` |
| 文档里那个值是什么？我的值是什么？ | 两个值都要写出 |
| 为什么可以偏离文档？ | 必须有实测反证（不是"感觉"） |

**答不出来就不许改。** 如果确实要偏离文档，必须：
1. 在代码注释里写明「文档说 X，实测是 Y，证据是 <日志文件:行>」
2. 在 checklist 里记一条 `DEVIATION`
3. 偏离后如果结果不对，第一件事是**恢复文档值**

---

## HR-29 上下文压缩后必须从磁盘恢复状态，禁止凭记忆

**触发场景（本会话反复发生）**

上下文多次压缩后，我遗忘：
- 已经试过哪些地址
- 参考文档的具体数值
- 哪些假设已被排除

**铁则（强制）**

**每轮开始，若不确定当前状态，按顺序读这三个文件，不看记忆：**

```
1. docs/<TARGET>-CHECKLIST.md    ← 当前执行到清单第几条，哪些 PASS/FAIL
2. docs/RUBY-TOUCH-REFERENCE.md  ← 参考文档的关键数值与结论
3. docs/PITFALLS.md 的最近 3 条  ← 刚踩过什么坑
```

**这三个文件是唯一的进度真相源。** 记忆、日志摘要、上一轮的叙述都不可靠。

**维护要求**：
- checklist 的状态必须**在每轮实际做了什么之后立刻更新**
- 不允许"等会儿一起更新"
- 更新的内容必须是可验证的事实（实测值、日志文件名），不是叙述

---

## HR-30 已排除假设必须登记，禁止重复尝试

**铁则（强制）**

每排除一个假设，立刻写入 `docs/PITFALLS.md`，格式：

```
### P-NN <假设> 已排除（<日期> <日志文件名>）
**假设**：...
**实测**：...（原始日志行）
**结论**：排除
**不要再试**：...
```

**开始新一轮工作前，先看这份清单，确认即将尝试的东西不在里面。**

本会话已排除但仍差点重复的：
- `0x10308` 写入会被静默丢弃 → 不要再试着"写 sync"
- `0x10400` 是 raw/计数器缓冲区（[3..7] 固定 e8 08 e8 08 01）→ 不是帧
- GENI SE4 FIFO 被硬件禁用 → 只能 bit-bang
- `pm8350c ppid 0x2c2` 在 SPMI 上找不到 → 换寻址方式，不是放弃电压检查

---

# 第二部分：通用硬件驱动铁则（适用于所有硬件，不只触摸）

> 用户 2026-11-10 明确要求：
> **「铁则不仅仅是触摸 后续所有硬件驱动都一样要有充分依据」**
>
> 下面每条铁则对触摸、WiFi、GPU、音频、基带、USB、蓝牙、电池、传感器
> 等**所有硬件驱动**同等强制。

## HR-31 每个硬件必须有独立的 CHECKLIST 文件

**文件命名**：`docs/<HW>-CHECKLIST.md`
（如 `K60-WIFI-CHECKLIST.md`、`K60-GPU-CHECKLIST.md`、`K60-AUDIO-CHECKLIST.md`）

**文件结构与 `K60-TOUCH-CHECKLIST.md` 完全相同**：

1. 顶部写明参考来源（仓库 / 文档路径 / commit）
2. 抄录参考文档的「调试清单 / bring-up 记录 / 检查项」**原文**
3. 逐条状态表：`条 | 项目 | 状态(PASS/FAIL/未执行) | 实测值 | 判据（文档原文）`
4. 「已排除假设」表（含日志文件名作为证据）
5. 「下一步（严格按清单顺序）」

**没有 CHECKLIST 文件的硬件，不允许开始写驱动代码。**

## HR-32 硬件选型必须有「同型设备已成功」的证据

**在任何硬件驱动开工前，必须回答：**

| 问题 | 要求 |
|---|---|
| 有没有同 SoC / 同芯片的设备已经跑通？ | 给出仓库 URL + commit + 该仓库的 porting.toml status |
| 该设备的 `status` 是什么？ | `device-verified` / `implemented` / `planned` / `not-applicable` |
| 它用的驱动路径是什么？ | 具体文件 + 关键函数行号 |
| 我们的硬件与它差在哪？ | 逐项列出（引脚、电源、总线、时钟） |

**`status = planned` 或 `components = []` 表示对方也没做 —— 不许假装有参考。**
**必须明确写下「本硬件无 device-verified 参考，属于自研」，然后才允许自行设计。**

## HR-33 参考文档必须整篇读，禁止 grep 拼接理解（强化 HR-26）

**适用范围扩大到所有硬件的文档与源码，不只触摸。**

- 文档 < 500 行 → **整篇读**
- 文档 500–2000 行 → `wc -l` 后**分批读完全部**
- 文档 > 2000 行 → 先列章节标题，再**整章读**
- **同一文件一次会话内最多 grep 两次**；第三次前必须整篇读

**为什么这条对每个硬件都重要**：
本会话在触摸上，因为 grep 拼理解，漏掉了 ruby §7 的 bring-up 记录表
（里面明确写了「默认电压 VMC 3.0V / VTP 1.8V 是根因」），
导致在帧地址上盲试了十几轮。

**同样的错误在 WiFi/GPU 上会以同样的方式发生。**

## HR-34 每个硬件改动必须能指出参考依据（强化 HR-28）

提交前必须能回答三个问题：

1. **参考依据在哪？** `文件:行号` 或 `文档 §章节` 或 `其他设备仓库:文件:行号`
2. **文档/参考里写的是什么？我的实现是什么？** 两个都要写出
3. **为什么可以偏离？** 必须有实测反证（日志文件名 + 行号），不是"感觉"

**答不出来就不许改。**

**特别禁止的表述**：
- 「试试看」「猜测」「可能是」「按理说」
- 「改成 X 看会不会好」
- 无依据地改变文档里明确给出的常量/地址/时序

## HR-35 硬件状态必须能从磁盘恢复（强化 HR-29）

**每个硬件独立维护状态，不依赖上下文记忆。**

每轮工作开始，若不确定状态，按顺序读：

```
1. docs/<HW>-CHECKLIST.md          ← 该硬件执行到第几条
2. docs/<HW>-REFERENCE.md          ← 参考文档的关键数值
3. docs/PITFALLS.md 最近 5 条       ← 刚踩过什么坑
4. docs/HANDOFF.md 该硬件章节       ← 历史结论
```

**这三个文件是唯一的进度真相源。记忆、日志摘要、上一轮叙述都不可靠。**

## HR-36 已排除假设必须按硬件分区登记（强化 HR-30）

`docs/PITFALLS.md` 中每条必须带硬件标签：

```
### P-NN [TOUCH] <假设> 已排除（<日期> <日志文件名>）
### P-NN [WIFI]  <假设> 已排除（...）
### P-NN [GPU]   <假设> 已排除（...）
```

**开始新一轮工作前，先看对应硬件的排除清单，确认即将尝试的东西不在里面。**

## HR-37 硬件驱动完成的判据是设备证据，不是代码写完

**每个硬件的完成定义**（照抄 UniXNU 生态的 status 语义）：

| status | 含义 | 需要的证据 |
|---|---|---|
| `planned` | 只有计划 | — |
| `implemented` | 代码落地、能编译、主机侧验证 | 构建日志 + 主机测试 |
| **`device-verified`** | **真机跑通并被观测到** | **串口日志原始行 + 可复现步骤** |
| `host-verified` | 仅在主机环境验证 | 主机日志 |

**禁止把 `implemented` 说成「已完成」。**
**只有 `device-verified`（日志原文 + 可复现步骤）才算该硬件修好。**

## HR-38 每次硬件切换前必须写交接段落

**从一个硬件转到另一个时**，必须先在 `docs/HANDOFF.md` 写一段：

```
## [HW] 当前状态（YYYY-MM-DD HH:MM）
- 内核 SHA: <sha256>
- 镜像 SHA: <sha256>
- 最后一次有效日志: <目录名>
- checklist 状态: 第 N 条 PASS / 第 M 条 FAIL
- 已排除: <引用 PITFALLS 编号>
- 下一步: <严格按 checklist 的下一条>
```

**理由**：上下文压缩后，这段文字是唯一能让人（和未来的我）知道
「这个硬件到底做到哪了」的东西。

## 各硬件当前状态总览（每轮更新）

| 硬件 | CHECKLIST | 参考来源 | status | 阻塞点 |
|---|---|---|---|---|
| 触摸 | `K60-TOUCH-CHECKLIST.md` | ruby-ios-bringup (GT9916R, device-verified) + zizhan | 清单第 2 条 FAIL | 电源 VOUT 未回读验证 |
| WiFi | **待建** | zizhan `network` (device-verified) | 未开始 | — |
| GPU | **待建** | zizhan `gpu` (implemented, 95.3fps) | 未开始 | — |
| 音频 | **待建** | zizhan `audio` (planned, 无参考) | 自研 | — |
| 基带 | **待建** | zizhan `cellular` (planned, components=[]) | 自研 | — |
| USB | **待建** | 待查 | — | — |
| 蓝牙 | **待建** | 待查 | — | — |
| 电池 | **待建** | 待查 | — | — |

**规则：表中「待建」的硬件，在建好 CHECKLIST 之前不许动代码。**

## HR-39 调试前必须建立「本地资源索引」并检索，禁止反复发现已有文件

**触发场景（2026-11-10 严重返工）**

触摸驱动排查了 200+ 轮，反复盲试帧地址、电源、时序。
结果发现 `/mnt/e/k60-work/impl/touch-protocol/refs/` 里**早就有完整官方 Goodix
BerlinD 驱动源码**（`goodix_brl_hw.c`、`goodix_brl_spi.c`、`goodix_cfg_bin.c`、
`goodix_ts_core.c` 等），以及 `goodix_cfg_group_m11a.bin` config 固件。

**如果第 1 轮就检索到这个目录，config 下载协议当天就能实现，不会拖 200 轮。**

**根因**：所有文件分散在 `impl/`、`scratch/`、`references/` 等几十个目录，
没有索引，靠记忆和碰运气查找。

**铁则（强制）**

1. **每个硬件开始前，先建该硬件的「本地资源清单」**，追加到对应 CHECKLIST 顶部：
   ```
   ## 本地资源索引（先看这里！）
   | 资源 | 路径 | 用途 |
   |------|------|------|
   | 官方驱动 goodix_brl_hw.c | /mnt/e/k60-work/impl/touch-protocol/refs/ | config下载+复位时序 |
   | config 固件 bin | scratch/goodix-fw/goodix_cfg_group_m11a.bin | 1627B config |
   | firmware bin | scratch/goodix-fw/goodix_firmware_m11a.bin | 223744B |
   ```

2. **开始调试前，对目标硬件做一次全盘检索**：
   ```bash
   find /mnt/e/k60-work /mnt/e/hackios -ipath '*<hw>*' -o -iname '*goodix*' ...
   ```
   把结果登记进索引。**没查全盘之前禁止改代码。**

3. **建立全局索引文件 `docs/LOCAL-ASSETS.md`**，分区列出所有参考源：
   - 官方驱动源码（impl/touch-protocol/refs/）
   - 各硬件参考仓库（references/）
   - 固件/bin/配置（scratch/goodix-fw/ 等）
   - 反汇编产物（scratch/*.ko）
   每周或每次大任务开始时更新。

4. **发现某个关键文件花了 >10 分钟** → 立刻把它补进索引，
   并反思为什么之前没检索到，把教训记入该硬件 checklist。

5. **索引检索优先于「凭记忆重造」**：在任何"我看看能不能实现 X"之前，
   先确认本地是否已有 X 的参考实现。

---

## HR-40 变动必须及时 commit，禁止让工作成果长期悬在脏工作区

**触发场景（用户 2026-11-10 点名，此前多次强调过但未落成铁则）**

本会话实测的脏文件数量触目惊心：

```
UniXNU-pong      dirty=387
pong-adreno      dirty=116
UniXNU-pong(ref) dirty=144
pong-adreno-metal dirty=106
UniXNU-docs      dirty=576
UniXNU-liuqin    dirty=105
UniXNU-mondrian  dirty=14   ← 当前主仓
```

**后果（本会话真实踩过）**：
1. 自动同步脚本无法安全 rebase，只能跳过 → **上游更新永远进不来**
2. `git checkout -- <file>` 曾撤销整个文件的补丁改动（`pong_owner_shared_cache_mount`
   整个函数消失，被迫删 `.cache/xnu-work` 重新解包）
3. 上下文压缩后，脏工作区是**唯一**的成果载体，一旦误操作就永久丢失
4. 无法用 `git log` / `git diff` 追溯"什么时候改了什么"

**铁则（强制）**

1. **每完成一个可验证的小步，立刻 commit**。判断标准：
   - 编译通过 → commit
   - 单测/设备验证通过 → commit
   - 一个逻辑改动完成（哪怕很小）→ commit
   - **禁止**攒到"全部做完再提交"

2. **commit message 必须包含证据**：
   ```
   <type>(<scope>): <一句话改动>

   证据: <日志文件名:行号 / sha256 / 实测输出>
   ```
   type: `fix` / `feat` / `docs` / `chore` / `refactor`

3. **禁止长期脏工作区**：任何仓库脏文件 > 20 个，视为**流程违规**，
   必须先 commit 或 stash 再继续。**主仓（UniXNU-mondrian）任何时候脏文件应 ≤ 5**。

4. **提交前必查**：
   ```bash
   git status --porcelain | wc -l     # 应 ≤ 5
   git diff --stat                    # 确认改动范围
   ```

5. **每个硬件的工作分支独立**：
   - 触摸：`fix/k60-touch`
   - WiFi：`feat/k60-wifi`
   - GPU：`feat/k60-gpu`
   **禁止所有硬件改动混在 main 上。**

6. **每天结束时（或定时任务里）必须检查**：
   ```bash
   for r in <repo list>; do
     n=$(git -C $r status --porcelain | wc -l)
     [ $n -gt 5 ] && echo "⚠️ $r dirty=$n 需要 commit"
   done
   ```

**与 HR-07 的关系**：HR-07 只要求「series 引用的文件必须已提交」，
本铁则要求**所有工作成果**都及时提交，范围更大。

---

## HR-41 WSL 网关 IP 变动会静默破坏 git 代理，每次同步前必须自检

**触发场景（2026-11-10 实测，导致所有 git fetch 失败）**

```bash
# 症状
git fetch → fatal: unable to access '...': Proxy CONNECT aborted

# 根因
git config --global http.proxy = http://172.27.64.1:17890   ← 旧网关，已失效
当前实际网关                    = 198.18.0.2                 ← WSL 重启后变了
DNS: github.com → 198.18.0.150                              ← 被代理软件劫持成 fake-ip
```

**WSL 每次重启/宿主网络变化后，虚拟网关 IP 可能改变**，
而 `git config --global http.proxy` 里写死的是旧 IP → **所有 fetch/push 静默失败**。

**铁则（强制）**

1. **同步脚本开头必须先做代理自检**，探测顺序：
   ```bash
   GW=$(ip route | grep default | awk '{print $3}' | head -1)
   for host in "$GW" 172.17.0.1 127.0.0.1; do
     for port in 7890 7897 10809 17890 1080; do
       # 端口通 + 真能访问 github 才算可用
       timeout 15 env https_proxy="http://$host:$port" \
         git ls-remote https://github.com/UniXNU/UniXNU.git HEAD >/dev/null 2>&1 && \
         WORKING="http://$host:$port" && break 2
     done
   done
   ```

2. **找不到代理时不要死等，直接清空配置走直连**：
   ```bash
   git config --global --unset http.proxy
   git config --global --unset https.proxy
   ```
   **实测直连可用**（`git ls-remote` 返回 HEAD sha），比错代理快得多。

3. **脚本**：`E:\k60-work\scripts\fix-git-proxy.sh`（已实现，自动探测+修复+验证）

4. **每次同步报告里必须打印实际使用的代理**，便于事后排查。

5. **如果 DNS 解析出 `198.18.x.x`**，说明流量被代理软件接管（fake-ip 模式），
   此时**必须走代理**，直连会失败；反之 DNS 正常但代理不通则走直连。

---

## HR-42 从外部仓库导入补丁必须先查本地编号，撞车则重编号

**触发场景（2026-11-10 从 yibiya fork 导入）**

yibiya 的 `0400-k60-pid26-slide.patch` 与我们自建的
`0400-k60-shared-cache-root-union.patch` **编号相同但内容完全不同**。
直接 `cp` 会覆盖，直接 cherry-pick 会冲突。

已发生的撞车：

| 编号 | 我们 | yibiya |
|---|---|---|
| 0400 | `k60-shared-cache-root-union` | `k60-pid26-slide` |
| 0401 | `k60-touch-off` | `k60-embedded-init` |
| 0399 | `k60-shared-cache-root-layout` | （无）|

**铁则（强制）**

1. **导入前必查**：
   ```bash
   ls patches/xnu/ | grep -E '^0<num>-'
   grep -nE '^0<num>-' patches/xnu/series
   ```

2. **撞车时取本地最大编号 +1**，并在 commit message 和
   `docs/YIBIYA-PICK.md`（或对应导入记录）里写明：
   ```
   原编号 0400 与本地 0400-k60-shared-cache-root-union 撞车，
   重编号为 0403。
   ```

3. **补丁内容不能混**：不同来源的同名补丁语义完全不同，
   重编号后必须保持内容一致，只改文件名。

4. **series 顺序也重要**：补丁应用顺序影响上下文匹配，
   新补丁追加在末尾（除非明确需要插在中间）。

5. **导入后必须验证**：
   ```bash
   cd /tmp/usb-cdc-mainline/device && \
     git -C patches/xnu apply --check <新补丁>   # 或在构建时验证
   ```

**关联**：`docs/YIBIYA-PICK.md` 记录了与 yibiya fork 的完整采纳分析。

---

## HR-43 设备能进 ADB 就用 `adb reboot bootloader`，不要要求手动上电

**触发场景（用户 2026-11-10 明确告知）**

移植调试中设备经常停在 Android（或 boot 失败后落回 Android），
此时只要能 `adb devices` 看到设备，**就直接用 ADB 切 fastboot**：

```bash
adb devices                      # 确认设备在
adb reboot bootloader            # 直接进 fastboot，不需要手动长按电源键
sleep 8
fastboot devices                 # 确认已进 fastboot
```

**不要在设备可用 ADB 时要求用户手动长按电源键**，那会打断自动化循环。

### 完整的状态切换矩阵

| 当前状态 | 切到 fastboot 的方法 |
|---|---|
| **Android / ADB** | `adb reboot bootloader` ← 首选 |
| fastboot | 已在，直接刷 |
| 黑屏 / 无响应 | 长按电源 10 秒强制关机再开机 |
| 9008 (EDL) | 需要 firehose 工具 |

### 与 300s 自动复位的关系

`k60_selftest_reboot=300` 是有意的自动化复位：内核跑到 300 秒会自己回 fastboot。
所以正常循环是：

```
fastboot boot <img>  →  抓 300s 串口  →  内核自动回 fastboot  →  刷下一个
```

**但如果内核崩在 300 秒之前**（例如 boot 失败落到 Android），
就要靠 ADB 切回来，而不是等。

### 探活顺序（每次操作前）

```bash
# 1. fastboot?
fastboot devices
# 2. 不在？试 adb
adb devices
# 3. 在 adb → 切 fastboot
adb reboot bootloader && sleep 8 && fastboot devices
# 4. 都没有 → 才提示用户手动上电
```

---

## HR-44 用户重复交代同一件事 = 文档缺陷，必须立刻补进去

**触发场景（2026-11-10 多次发生）**

用户反复说过的：
- "ADB 状态可以 reboot 到 fastboot"（说了至少 2 次）
- "Mac 可以 SSH 连接"（说了至少 2 次）
- "本地有很多文件夹，应该做索引"（说完才建 LOCAL-ASSETS）
- "变动及时 commit"（之前要求过但没落成铁则）
- "300 秒复位是自动化调试"（我先理解错了）

**每次都是我回答「记住了」但没写进文档，下一轮又忘。**

**铁则（强制）**

1. **用户第二次提到同一件事时，立刻做两件事**：
   - 写进 `docs/ENVIRONMENT.md`（环境事实）或 `docs/HARD-RULES.md`（流程规则）
   - 在回复里指出写到了哪个文件哪一节

2. **禁止只回答「记住了」「明白了」而不落文档**——那等于没记住。

3. **每次开工前先读 `docs/ENVIRONMENT.md`**，不要靠上下文记忆。

4. **判断标准**：
   - 环境/凭据/路径/设备状态 → `ENVIRONMENT.md`
   - 工作流程/必须做/禁止做 → `HARD-RULES.md`
   - 已踩过的坑 → `PITFALLS.md`
   - 文件/仓库在哪 → `LOCAL-ASSETS.md` / `REPO-INVENTORY.md`

5. **文档要能一眼找到**：`HARD-RULES.md` 开头有索引块，
   `ENVIRONMENT.md` 是唯一权威环境表。

---
