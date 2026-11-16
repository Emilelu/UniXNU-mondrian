# 上机卡：GPU Metal 硬件加速 · `gpu-msseed-20261117`

写入时间：2026-11-17 00:30 +08:00（**上机之前**）
分支：`feat/gpu-metal-hw`（HEAD 含 `5ea63d9f`）
镜像：`E:/k60-work/artifacts/gpu-msseed-20261117/boot.img`

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

- 证据目录：
- S1： / S2： / S3： / S4： / S5：
- 判决：
- 结论与下一步：
