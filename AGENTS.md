# Agent instructions

This repository owns the Redmi K60 (mondrian, SM8475) device configuration,
peripherals, firmware selection, partition layout, power policy and packaging.
The shared SM8475 resources live in `UniXNU-sm8475-common`; the loader lives in
`uefi-mondrian`; the build driver, the documentation site and the component
catalog live in `UniXNU`.

The porting record in `porting.toml` is the authoritative device state. Every
subsystem change updates the record in the same pull request.

## Required reading

| Task | Required reading |
| --- | --- |
| Every port | [Porting](https://unixnu.com/porting/), [repository format](https://unixnu.com/porting/device-repository), [component catalog](https://unixnu.com/reference/components), [porting records](https://unixnu.com/porting/records) |
| Bring-up order | [Bring-up order](https://unixnu.com/porting/bring-up) — seven stages, one visible result each |
| Debugging | [Debugging and logs](https://unixnu.com/guide/debugging) — green bar, entry probe colour bars, panic screen, the `boot-progress` diagnostic page |
| Kernel | [Selected OS profile](profiles), XNU source, [patch reference](https://unixnu.com/xnu/source-and-patches), ordered patch series |
| Images | [Prelink](https://unixnu.com/concepts/prelink), [payload](https://unixnu.com/concepts/payload), [UEFI firmware](https://unixnu.com/porting/uefi-firmware) |
| Prior art | `D:\Android\k60-ios\PRIOR-ART-FIRST.md`, `D:\Android\k60-ios\READING-INDEX.md` |
| Failure reading | `D:\Android\k60-ios\FIRST-BOOT-PLAYBOOK.md`, `D:\Android\k60-ios\deliverables\delta2\21-FAILURE-MODE-MATRIX.md`, `D:\Android\k60-ios\deliverables\delta2\12-EARLY-BOOT-EVIDENCE-PLAN.md` |
| Collaboration | `D:\Android\k60-ios\COLLABORATION-RULES.md` |

## Research before writing code

Before implementing a feature, driver or patch, survey the existing
repositories and branches. Do not start writing first.

0. Local patches first. Before any kernel change — new feature, bug fix or
   adaptation — read every patch this tree already carries:
   `patches/xnu/` (the closed 16.6.1 series, 64 files: SMP, timers, cache,
   watchdog, display, keybags), `patches/xnu-ipados18/` (the darwin24
   series), and the reference trees' patch directories. A problem being
   solved "new" may already carry a proven answer, or a constraint that
   explains why the obvious fix is wrong. Example: the PSCI SMP recipe
   existed in both series, and re-deriving it cost a boot cycle.
1. Sync: `bash scripts/k60-sync-refs.sh`. It fetches every reference repository
   under `D:\Android\k60-ios` and the WSL trees and reports which upstream moved.
   Never quote code from a repository whose upstream you have not fetched.
2. Look for what changed: `git log --all --since=<date> --oneline` in each
   repository, then `git log main..<branch>` for a suspicious branch.
3. Search: `git grep -n <keyword> $(git rev-list --all)`.
4. Record the finding before coding: what was found (repository, branch,
   file:line), whether it fits this board (XNU version, machine config, boot
   chain, SoC), the licence status, and the decision to reuse, adapt or build.
5. Licence rule: hardware facts and register maps are free to reference; code,
   patches and scripts need a licence. A repository without a licence keeps all
   rights — read the idea, write your own.

The upstream survey for the iOS 16 to 27 ladder lives in
`docs/ROUTE-A-18-UPSTREAM.md`.

## 分支

- 一个改动一个分支：`feat/<topic>`、`fix/<topic>`、`docs/<topic>`、`refactor/<topic>`、
  `chore/<topic>`、`perf/<topic>`、`wip/<topic>`。
- 分支只有在改动经过验证、记录更新之后才合并进 `main`。

# 提交规范（铁则）

遵循 [feflow/git-commit-style-guide](https://github.com/feflow/git-commit-style-guide)：

```
<type>(<scope>): <subject>

<body>

<footer>
```

- `type` 取 `feat` / `fix` / `docs` / `style` / `refactor` / `perf` / `test` / `build` / `ci` / `chore` / `revert` 之一。
- `scope` 可选，写受影响模块，例如 `xnu`、`userland`、`uefi`、`readme`、`series`。
- `subject` 说清做了什么：英文、祈使式、不超过 50 字符、结尾不加句号。
- `body` 说明**为什么**这样改以及影响面，每行不超过 72 字符；`footer` 写 `BREAKING CHANGE:` 或关联 issue。
- 一次提交只做一件事；代码与文档分成两个提交，同一 PR 里提交。
- 提交者固定为 `Emilelu <kimiuso@vip.qq.com>`，不要使用临时或占位身份。
- 已发布的历史不重写；确需修正（例如作者信息错误）时先说明再强推。
## Device rules

- Probe the device before acting: `bash scripts/k60-device.sh state` reports
  `adb`, `fastboot` or `none`, and the same script performs the matching
  transition (`android`, `bootloader`, `boot <image>`). Do not ask for a manual
  power cycle while a software path exists.
- Only `fastboot boot`. Never `fastboot flash` an Android partition. `persist`
  holds the KeyMint database and a rollback destroys every key.
- After every boot, fill in `porting.toml` within five minutes and keep
  `python3 scripts/check-porting-paths.py --quiet` at zero errors.
- Completion levels follow the completion criteria, not the fact that hardware
  was touched. Topology parsing alone stays `implemented`.
- Record the device observation, the command, the full revision and the result.
  A photograph of the panel is the primary evidence on this board.

## Reading a failure

The board has no serial console, so the screen is the log. Split every failure
into one of four segments and read the matching evidence source:

| Segment | Symptom | Evidence |
| --- | --- | --- |
| Before UEFI | black screen, no UniXNU trace | boot image header, firmware base and size |
| Inside UEFI | menu or entry dies | Tools → Advanced Logger |
| Inside DarwinBoot | loader progress line stops | the last drawn line, the refusal message |
| Inside XNU | scroll starts, then dies | the last lines, the panic screen, the `boot-progress` page |

The failure mode matrix in `D:\Android\k60-ios\deliverables\delta2\21-FAILURE-MODE-MATRIX.md`
maps each symptom to its evidence, its verdict and the next step.

## Commands

Run from the UniXNU checkout:

```sh
./unixnu defconfig mondrian_defconfig --device ../UniXNU-mondrian
./unixnu fetch --device ../UniXNU-mondrian
./unixnu status --device ../UniXNU-mondrian --json
./unixnu build kernel --device ../UniXNU-mondrian
./unixnu build payload --device ../UniXNU-mondrian --unique-chip-id "$UNIXNU_UNIQUE_CHIP_ID" \
  --trust-cache prebuilt/20G81-trustcache.bundle
./unixnu bootimg --device ../UniXNU-mondrian --uefi ../uefi-mondrian \
  --dtb out/mondrian/ipados-18.7.10-22H374/mondrian/device-tree/hardware.dtb \
  --ramdisk out/mondrian/ipados-18.7.10-22H374/mondrian/payload/payload.img \
  -o /mnt/d/Android/k60-ios/boot-darwin24.img
```

This route builds the kernel without the profile's prelink step, so prelink
runs separately:

```sh
python3 scripts/build-darwin24-platform.py     # kernel, applies patches/xnu-ipados18
python3 scripts/k60-prelink-darwin24.py         # prelink, 54,808,576 bytes
python3 scripts/verify-boot-img-payload.py --img <image> --payload <payload> --kernel <kernel>
```

Device state, boot and log capture:

```sh
bash scripts/k60-device.sh state
bash scripts/k60-device.sh boot /mnt/d/Android/k60-ios/boot-darwin24.img
```

Never flash the boot partition: every experiment image goes through
`fastboot boot`, so the partition on the phone stays as it is.

## Calling WSL from the host shell

`wsl.exe` rebuilds its command line from argv, so the quotes around a
`bash -lc "..."` payload are lost on the way. Any semicolon inside that payload
then becomes a separator in the distro's outer shell: the part after it runs
outside WSL, with the variables unset and the paths wrong. This has cost
several wrong conclusions (an empty `$K`, an unset `$pat`, a loop that ran in
the wrong shell).

Two safe forms:

```sh
# a script on the Windows side, fed on stdin - content never passes the
# Windows command line
wsl.exe -d Ubuntu-24.04 -- bash -s < /c/Users/Emilelu/AppData/Local/Temp/step.sh

# a script inside WSL, with MSYS path conversion turned off
MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu-24.04 -- bash /tmp/step.sh
```

Both keep semicolons, variables and loops intact. A one-line payload without
semicolons still works, but anything longer belongs in a script file.

## Porting record

Read `porting.toml` and the [record guide](https://unixnu.com/porting/records)
before implementation. Update each affected area's findings or evidence with its
code change. `porting.toml` is the authoritative device record; the site renders
the same text.

```sh
python3 scripts/check-porting-paths.py --quiet
```

## Reference repositories

`scripts/k60-sync-refs.sh` covers the thirteen repositories under
`D:\Android\k60-ios` and the WSL trees. `docs/FORK-REVIEW.md` records their
branches and the reasoning behind every adopted change.
