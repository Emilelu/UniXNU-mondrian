# The eight-step spec (EIGHT-STEP SPEC)

> Purpose: turn "follow the eight steps" into a procedure that can be executed,
> checked and reproduced, instead of eight adjectives.
>
> Core principle: **the output of every step must answer one concrete question;
> if it cannot, the step is not done.**

---

## Overview

| Step | Name | Question it answers | Key output |
|---|---|---|---|
| ① | Same model | How far has the same model got? | Device list + best known state + the gap |
| ② | Official | What do the official docs and drivers require? | Requirement list + source `file:line` |
| ③ | Reverse engineering | What are this device's real parameters? | Measured data, every parameter with a source |
| ④ | Wide search | **Does something off the shelf already do this?** | Component catalogue search + reuse list |
| ⑤ | Plan | What exactly changes, and on what basis? | Change list, every item traceable to evidence |
| ⑥ | Deep dive | Which "uncertain" items remain? | Uncertainty list, all resolved |
| ⑦ | Local verification | How do we prove it is right without flashing? | Local verification command + output |
| ⑧ | On device | How is success or failure decided on the real phone? | Pre-declared criteria + log lines |

---

## ① Same model (同型)

**Purpose**: look at the same model first so work somebody already finished is
not repeated.

**Mandatory**
1. Check the device record at `https://unixnu.com/devices/<device>` (does one
   exist, what state is it in)
2. Check the branches under local `references/` for the same model or codename
3. Check public ports of the same model (XDA / the GitHub topic `unixnu`)

**Evidence format**
```
model + repository URL/commit + what they implemented + where they are stuck + where we go further
```

**Pass condition**
- can answer "what is the best state reached by the same model"
- can answer "has anyone already done what we are about to do"

**Anti-patterns**
- ❌ using another **model's** driver as evidence for this model
  (2026-11-12: the POCO X5 Pro's `hakios.goodix.c` was taken as PHK110's)
- ❌ writing "referenced pong" without saying how far pong actually got

---

## ② Official (官方)

**Purpose**: obtain the authoritative requirement instead of guessing.

**Mandatory**
1. Read the matching page at `https://unixnu.com/zh/porting/<subsystem>` and
   list its requirements one by one
2. Read the official driver source (vendor kernel / Linux mainline) and locate
   the key functions and structures

**Evidence format**
```
URL + section number/title; source file:line + function name
```

**Pass condition**
- can cite a specific item from the official documentation (not "I read it")
- can name the key functions and line numbers in the official implementation

**Anti-patterns**
- ❌ writing "referenced the official driver" without a `file:line`
- ❌ treating an old vendor driver as official (vendor and mainline differ)

---

## ③ Reverse engineering (反编译)

**Purpose**: obtain the real parameters of **this device**. This is the only
step that rules out "another model's parameters do not apply".

**Mandatory**
1. live FDT decompilation (this phone's DTB, not another one's)
2. on-device forensics from the Android side (`/proc/device-tree`,
   `/sys/class/...`, dmesg)
3. firmware extraction / disassembly where required

**Evidence format**
```
DTB sha256 + decompile path + property values
Android command + full output
```

**Pass condition**
- every key parameter (address / pin / clock / ID / supply) has a **local**
  source
- no parameter is left "inferred from another model"

**Anti-patterns**
- ❌ substituting a mainline dtsi index for the local FDT
  (2026-11-12: cape/sm8475 carries m/s_ahb at index 134/135, mainline sm8450 at
  118/119)
- ❌ checking register addresses without checking supplies and clocks

---

## ④ Wide search (广域 / **Reuse first**)

**Purpose**: **stop rebuilding wheels.** This is the step most often skipped
and the most expensive to skip.

**Mandatory (in order, none optional)**

1. **★ Search the official UniXNU component catalogue**
   - File: `UniXNU/components.toml` (25 components)
   - Page: `https://unixnu.com/zh/reference/components`
   - **Every entry must get an answer**: is there something usable? If not, why
     not?

2. **★ Search the official driver repository list**
   - Page: `https://unixnu.com/zh/drivers/repositories`
   - 27 official drivers + 12 community drivers + 9 device branches
   - The same "is anything usable" answer is mandatory here too

3. **Search sibling ports on the same SoC**
   - Example: the PHK110 / d22ap / taro family on SM8475

4. **Search implementations for the same peripheral chip**
   - Example: other models with the same touch controller or the same WiFi chip

5. **Cross-check multiple sources**
   - At least 2 independent sources agree on the same parameter

**Evidence format**
```
[catalog_checked] UniXNU/components.toml, all 25 components compared one by one:
  - QcomGeniSpi: usable/not usable + reason
  - AdrenoMetal: usable/not usable + reason
  ...
[repositories_checked] unixnu.com/zh/drivers/repositories, 27 official drivers:
  - ...
[same_soc] ...
[same_chip] ...
[cross_check] ...
```

**Pass condition**
- **`catalog_checked = true` with a verdict** (use / do not use + reason)
- an available official component with a hand-written wheel instead → **FAIL**

**Anti-patterns**
- ❌ searching only same-SoC ports and skipping the official catalogue
  (2026-11-12: a hand-written GENI SPI bitbang, while the official
  `QcomGeniSpi` already has a DMA path)
- ❌ writing "referenced xxx" without saying whether it can be used directly

---

## ⑤ Plan (方案)

**Purpose**: turn the conclusions of the first four steps into concrete changes.

**Mandatory**
1. list every file that will change
2. tag every change with the source it rests on (which item of ①②③④)
3. state the expected outcome

**Evidence format**
```
| File | Change | Basis |
|---|---|---|
| drivers/X.c | add Y | ③ DTB property zz=0x... (file:line) |
```

**Pass condition**
- every change traces back to a piece of evidence from the first four steps
- no change is justified by "experience"

**Anti-patterns**
- ❌ a plan containing "should be" or "might be"

---

## ⑥ Deep dive (深挖)

**Purpose**: drive every "uncertain" item in the plan to a definite answer.

**Mandatory**
1. list every uncertain item in the plan explicitly
2. give each item a verification method and run it until there is a conclusion
3. the conclusion must be falsifiable (it must be possible to say "if it were A
   we would see this, if it were B we would see that")

**Evidence format**
```
| Uncertain item | Verification | Conclusion | Basis |
|---|---|---|---|
```

**Pass condition**
- the uncertainty list is empty, or every item has a conclusion
- the plan no longer contains hedging words

**Anti-patterns**
- ❌ treating "deep dive" as "read the code a few more times"

---

## ⑦ Local verification (核验)

**Purpose**: prove the implementation is correct **without flashing**. This is
the last gate before the phone is touched.

**Mandatory (three kinds, none optional)**

1. **Static comparison**
   - compare key constants / struct offsets / timing against the official
     implementation **line by line**
   - example: the packed offset of `goodix_ic_info_misc` against our `misc + N`

2. **Offline unit test**
   - feed our parser the known input (the byte sequence from the reference
     implementation)
   - verify the output matches

3. **Artefact inspection**
   - symbols, strings, size, signature, segment layout
   - example: `strings kernel.macho | grep <marker>`, `__TEXT <= 16384`

**Evidence format**
```
command + full output + conclusion (one entry per kind)
```

**Pass condition**
- every code change has matching local verification evidence
- **"it compiles" does not count**

**Anti-patterns**
- ❌ running `make` successfully and calling that ready to flash
- ❌ verifying one dimension only (size but not logic)

---

## ⑧ On device (上机)

**Purpose**: confirm on the real phone, and make success or failure readable at
a glance.

**Mandatory**
1. **before flashing**, declare the criteria (in `EIGHT-STEPS.toml` under
   `prediction`)
   - `success`: the exact log line that appears on success (it has to be
     greppable)
   - `failure`: the line that appears on failure
2. change **one** variable only (everything else stays at the last successful
   configuration)
3. keep a rollback image
4. after flashing, compare against the criteria instead of "it looks about right"

**Evidence format**
```
log file name + the matched line verbatim + criteria comparison
```

**Pass condition**
- the `success` criterion matched
- a `failure` match is recorded in PITFALLS

**Anti-patterns**
- ❌ flashing with no declared criteria and explaining afterwards that "it
  really did work"
- ❌ changing several variables at once, which makes attribution impossible

---

## Gate mapping

| Stage | Requirement |
|---|---|
| `build` | ①-⑥ all have evidence |
| `flash` | ①-⑦ all, plus `prediction.success` / `prediction.failure` for ⑧ |

**Extra hard requirement for `④ Wide search`**: `catalog_checked = true` and a
non-empty `catalog_result`. That is the machine guarantee behind "do not rebuild
wheels".

---

## Why this spec exists

On 2026-11-12 the user pointed out:

> "To stop falling into the same pits and rebuilding the same wheels, the
> eight-step process needs a thorough and reasonable definition."

Before that, "the eight steps" were one table in `EIGHT-STEP-EVIDENCE.md` with a
✅/◐/❌ per cell; nothing said what each step had to do, and nothing said what
counted as finished.

The results:
- ③ Reverse engineering: only the DT was read, supplies and clocks were not
  checked
- ④ Wide search: only same-SoC ports were searched, **the official component
  catalogue was never opened** → a hand-written GENI SPI, while the official
  `QcomGeniSpi` has a DMA path
- ⑦ Local verification: only a build was run, no static comparison and no unit
  test

这份规范把每一步变成"答不出这个问题就不算完成"。

### 判废信息必须指到"少了什么"

2026-11-16 补。同一天有两次判废，都因为信息只说"不对"而多花了一个构建周期：

| 判废信息 | 少了什么 | 代价 |
|---|---|---|
| `build-strict: FATAL: frozen inputs changed during the build; this run is void` | 哪几个文件变了 | 一轮构建被判废，事后才从 `git status` 猜出是九个 `__pycache__/*.pyc`（P-224） |
| 合并后 `git diff --stat` 只显示 44 行新增 | 相对合并前少了哪四块 | 一次合并把 `board_dir()`、`__pycache__` 剪枝、wifi 归档块和内核断言整段吃掉，等到构建失败才发现（P-226） |

规则：**任何判废、拒绝、不一致的报告，都必须点名具体对象**——文件路径、行号、
缺失的块名、期望值与实测值。只写"不一致""changed""failed"等于把排查成本
转嫁给下一个人，而且下一班人往往就是几小时后的自己。

落地方式：判废语句里带上 diff 或清单（`freeze` 打印变动的文件、门禁打印缺失的
块名），并且门禁脚本要**断言"存在"**而不是只断言"没坏"——`check-build-strict-blocks.py`
就是按这条写的：它逐块断言 `board_dir()`、`__pycache__` 剪枝、`.config` 守卫、
gate 标记、内核符号断言都在，缺哪个就报哪个。
