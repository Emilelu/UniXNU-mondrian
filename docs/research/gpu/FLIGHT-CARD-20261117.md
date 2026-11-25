# 上机卡：GPU Metal 硬件加速 · `gpu-msseed-20261117`

写入时间：2026-11-17 00:30 +08:00（**上机之前**）
分支：`feat/gpu-metal-hw`（HEAD 含 `5ea63d9f`）
镜像：`E:/iOS Port/Work/artifacts/gpu-msseed-20261117/boot.img`

## 1. 本飞唯一目的

验证「生成器把 `.publish`/`.clients` 放到 `addons/` 之后，用户态能不能拿到 Metal 设备」。
上一飞（`gpu-scanout2-20261116`，`dbb93478…`）内核侧 published 成功、扫描输出闸门已开
（`PONG SCANOUT: actual framebuffer handoff available`），但用户态仍回退 18 次、
`present #` 0 次 —— 与「标记文件落在 `/private/var/ngpu/` 而不是 `…/addons/`」完全一致。

## 2. 本飞带入的改动（每项都有证据）

| 改动 | 提交 | 静态 | 单元 | 产物 |
| --- | --- | --- | --- | --- |
| 两个标记文件改放 `addons/` | `5ea63d9f` | 生成器 `SEEDS` 带前缀；`0610` 建 `K60_METAL_ROOT "/addons"`；plugin `:182` 读 `%s/PongAdrenoMetal.publish` | `scripts/tests/test-metal-seed-path.py` 4/4 ✅ | 重新生成 blob（6 bodies），`check-metal-blob.py` ✅ |
| 扫描输出 + `pong_metal=1` | `1b8eaf47` 等 | `board.toml` | — | `image-arg-audit: OK (30 args / 594 B)` |
| open trace 不再解引用回收指针 | `0589a33a` | `check-patch-apply.py` ✅ | `test-open-trace-no-name-deref.py` 4/4 | 上一飞真机无 panic |

## 3. 已知未闭合项

| 项 | 状态 | 阻碍本飞？ |
| --- | --- | --- |
| `PongMetalBridge.dylib` 是 2026-11-09 预编译产物 | 未核对是否落后上游 | 不阻碍：若本飞仍回退，下一步就重建 bridge |
| `gprobe=0` 未取 | 判断为调试项 | 不阻碍 |
| backboardd 崩 13 次 | 未解释 | 不阻碍：判据已含 S4 |
| selector 7 / IOConnectTrap 假成功 | 已知缺口 | 不阻碍：属下一层 |

## 4. 判据（先写死）

成功需同时满足 S1–S5：

- **S1** `K60KEXC` 0 次且无真实 `K60PANIC`（`restart windows ready` banner 不算）
- **S2** 出现 `present #` ≥ 1 次
- **S3** `software renderer fallback installed` == 0
- **S4** `crashed: backboardd` == 0
- **S5** `SpringBoard` ≥ 100

失败分级：

- **F1** 出现 `K60KEXC`/真实 panic ⇒ 停飞，符号化定位后再补证据
- **F2** 无 panic 但 S2/S3 不满足 ⇒ 记为 FAIL(F2)，下一步固定为重建 `PongMetalBridge.dylib`（源码在 Mac，`scripts/build-pong-metal-bridge.py`），不再改 boot-arg
- **F3** S2/S3 满足但 S4/S5 不满足 ⇒ 取崩溃栈与帧率数据，转性能/稳定性

## 5. 结果登记（上机后填写）

- 镜像：`80a128075c52ff21b1bebd2af0d03f7d1231ca114925c9a225e6b2046fb9532e`（30 args / 594 B）
- 证据目录：`E:/iOS Port/Work/evidence/usblog-20261117-003205`（214,656 B，抓取完整，未因 panic 中断）
- S1 ✅：`K60KEXC` 0 次，无真实 panic
- S2 ❌：`present #` 0 次
- S3 ❌：`software renderer fallback installed` 18 次
- S4 ❌：`crashed: backboardd` 15 次
- S5 ❌：`SpringBoard` 13 次
- 判决：**FAIL(F2)**

### 关键判读：这一改没有可观测效果

`K60METAL deploy files=6/6 error=0`（`:480`）说明 6 个文件都写成功，但
**回退次数与上一飞完全一致（18）**，`present #` 仍是 0。也就是说：
把 `.publish`/`.clients` 从 `/private/var/ngpu/` 移到 `…/addons/` 之后，
用户态行为没有变化 —— 这个「路径不一致」是我从两边源码推出来的**合理假设**，
但**本飞没有证实它是断点**（缺少「改回裸名 → 现象变化」的真红对照）。

诚实结论：seed 路径改动可以作为「与上游一致」保留，但**不能记为根因修复**。
断点仍在更上游：要么插件根本没被 backboardd 加载，要么加载了但
`MTLCreateSystemDefaultDevice()` 之前的加速器客户端打开失败。

### 下一步（按 F2 固定动作）

1. 先确认插件是否被加载：在 `0610` 部署后打印 `PongAdrenoMetal.bundle` 的
   `Info.plist` 是否可读、`PongAdrenoMetal` 是否被 `dlopen` 过（内核侧只能证明文件存在，
   用户态侧要看 backboardd 是否扫描到该 bundle）。
2. 按 F2 的第二项重建 `PongMetalBridge.dylib`（Mac 侧 `scripts/build-pong-metal-bridge.py`），
   我们的副本是 2026-11-09 的产物，落后上游 7 天的提交（`8eb264d`、`e89d27d`、`4f1752f`）。
3. 每一步都要有静态/单元/产物证据，并另写一张上机卡预写判据后才飞。
