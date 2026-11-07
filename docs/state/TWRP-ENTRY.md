# 进入 TWRP 的正确方式（2026-11-08 用户确认，勿再踩坑）

- **TWRP 已集成在我们的 boot 镜像里**，不需要单独的 `twrp.img`，也不需要 `fastboot boot twrp.img`。
- 进入方式：设备在 fastboot 下执行 **`fastboot reboot recovery`**。
- 验证：`adb devices` 显示 `<serial>  recovery`（例如 `6033dbec  recovery`）。
- 不要在 `D:/`、`E:/`、`F:/` 里搜索 "twrp*.img"——**不存在也不需要**；此前为此浪费过时间。
- TWRP 内 `adb shell` 是 uid=0，具备 dd 能力；任何写盘命令前必须做只读自审与回读校验（见 `docs/reference/PITFALLS-FROM-HISTORY.md` 第 305、688 条）。
