# 洋红横杠不是显示通路故障：缩放字体写穿了字形缓冲区

状态：只读分析（冻结期，未构建、未上机）。结论有两条独立证据：现场照片的几何测量，
以及代码里可静态判定的越界。

## 1. 现场照片

`E:\iOS Port\Work\scratch\photo-band1.png` 取自用户照片 `e4027cca7c14286838f2237cd937b0b0b5e0589e4618c98de9f37fab1b573a4a`
（870×1803）。逐像素测量：

- 洋红（`#FF00FF`）横条 **29 行**，条高 25–29 px，**条间距固定 50 px**；
- 每条左界 x≈110–210 px，右端参差（长的到右边缘，短的只到中段）；
- 条内是实心填充，放大 3 倍后看不到任何字形笔画（`photo-band1.png`）；
- 顶部另有一条独立横条，底部有阶梯状短条堆叠。

「等距、左对齐、长度随文本长度变化」只可能来自**逐行文本**；实心说明每个字符的位图
被填成了整块。行距 50 px（照片）对应 1440 宽面板上的 16×3=48 px 字高，与启动参数
`k60_fontscale=3` 完全吻合。

## 2. 代码

`osfmk/console/video_console.c`：

- `iso_font[256 * 16]`（`iso_font.c:306-309`）——一个字形 **16 字节**，每字节一行 8 像素。
- `vc_render_char()` 从 `iso_font + ch * ISO_CHAR_HEIGHT` 开始，**按行读这 16 字节**：

```c
for (line = 0; line < ISO_CHAR_HEIGHT; line++) {   /* 上游原样 */
    unsigned char mask = 1;
    do { *current.longptr++ = (*theChar & mask) ? 0xFFFFFFFF : 0; } while (mask <<= 1);
    theChar++;
}
```

- `patches/xnu-12377/0544-k60-console-font-scale.patch` 为了放大字格，定义了
  `#define VC_CH (ISO_CHAR_HEIGHT * vc_k60_sy)`，并在同一个补丁里把上面这行也改成了
  `for (line = 0; line < VC_CH; line++)`。`VC_CH` 是**格子高度**（scale=3 时 48），
  不是位图行数（恒 16）。
- 后果：每个字符读 48 字节（越过本字形 32 字节，读到后面两个字形），写
  `48 × 8 × 4 = 1536` 字节进

```c
static unsigned char vc_rendered_char[ISO_CHAR_HEIGHT * ((REN_MAX_DEPTH / 8) * ISO_CHAR_WIDTH)];
```

即 **512 字节**——每画一个字符溢出 1024 字节。字形因此全是垃圾，屏幕表现为实心色块。

## 3. 机器判据

```
python3 scripts/check-font-render-bounds.py --tree <xnu 树>
```

- 产生洋红照片的那棵树（`/opt/k60/trees/ios27-out/.../tree/.cache/xnu-work`）：
  `FAIL .../video_console.c:1402: vc_render_char walks the font bitmap with "VC_CH", which is the scaled cell height, not the 16-byte glyph`
- 修好的补丁应用后：`FONT OK 1 glyph loop(s) walk ISO_CHAR_HEIGHT; VC_CH only in screen-row helpers`
- `scripts/tests/test-font-render-bounds.py`：4 个用例（好树 / 坏 render / 坏的其他函数 / 缺文件）。

`VC_CH` 在 `vc_reverse_cursor`、`vc_scroll_down`、`vc_scroll_up` 里是**对的**——它们走的是
屏幕行；检查器只禁它在 `vc_render_char` 和无名函数里出现。

## 4. 结论与影响

1. **显示通路是通的**：内核在自己的控制台上逐行打印，行距、左边界、行宽都正确。
   之前把它读成「显示没起来」是误判；不需要为此移植 `GopFramebuffer` 才能拿到文本输出
   （`GopFramebuffer` 仍然是 SpringBoard 要 provider 的另一件事，见 `DISPLAY-STACK-PORT.md`）。
2. **修法只有一行**：`vc_render_char` 的循环边界恢复 `ISO_CHAR_HEIGHT`。已从
   `0544-k60-console-font-scale.patch` 中删掉那个 hunk（净行数不变，其余 hunk 偏移不受影响），
   并用干净源树 `git apply --check` 验证通过。
3. **仍需上机确认**：修好后应看到可读的白字黑底日志。这是解冻后第一次诊断飞行的判据：
   `k60_fontscale=3` + 修正后的 0544，照片里必须能读出字符轮廓，而不是横杠。
4. 教训与 P-260 同族：一个宏代表「格子高度」时，不能再拿它当「位图行数」。已登记 **P-313**，
   并接入 `check-rules.py`（193 条，0 失败）。
