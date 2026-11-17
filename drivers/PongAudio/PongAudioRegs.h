/* SPDX-License-Identifier: BSD-2-Clause-Patent
 *
 * K60 (Redmi K60 / mondrian / SM8475 / "cape") audio register map for the
 * AP-side blocks: TLMM pads, the QUPV3 wrapper-2 serial engine that carries the
 * speaker amplifiers, and the Awinic AW882xx register file. Nothing here is
 * reachable through the ADSP, so none of it needs PAS1 or a PRM vote.
 *
 * Every constant below carries the evidence that fixes it. Register names are
 * never used as evidence for a value.
 *
 *   L  E:/k60-work/scratch/audio-work/live-fdt.dts   Android live FDT (authoritative)
 *   G  /home/emilelu/k60tmp/gcc-sm8450.c             vendor gcc driver, qupv3 branch table
 *   S  /mnt/e/k60-work/references/pong-power/        Pong reference, same SoC (SM8475)
 *   M  /home/emilelu/wifi-inputs/linux/drivers/i2c/busses/i2c-qcom-geni.c, include/linux/soc/qcom/geni-se.h
 *   H  /mnt/e/k60-work/references/phk110-port/drivers/audio/hakios.speaker.c  AW882xx family
 */
#ifndef PONG_AUDIO_REGS_H
#define PONG_AUDIO_REGS_H

/* ---- TLMM pads ------------------------------------------------------------
 * L:1347  pinctrl@f000000, compatible "qcom,cape-pinctrl", reg <0xf000000 0x1000000>
 * S:PongAudio.cpp:120  pins.open(0xf100000, 0xd0000)  -> the GPIO register
 *        block is TLMM base + 0x100000, not the node base.
 * S:PongAudio.cpp:120-129  GPIO n lives at n * 0x1000; +0 config, +4 in/out.
 * Same shape in the K60 touch driver: patches/xnu/zzzz*pong-touch-console.patch:137
 *        ml_io_map(TLMM_PHYS + gpio_offset + 0x1000 * pin, IO_PAGE_SIZE).
 */
/* One 4 KiB register window. io_map() rounds every mapping up to the arm64
 * 16 KiB page (osfmk/arm/io_map.c:88-142), so one window costs four pages of
 * the 8 MiB kernel-wide io_submap - see SOUNDWIRE.md section 7. */
#define PONG_AUDIO_WINDOW_SIZE      0x00001000u
#define PONG_AUDIO_TLMM_PHYS        0x0f000000u
#define PONG_AUDIO_TLMM_GPIO_OFF    0x00100000u
#define PONG_AUDIO_GPIO_STRIDE      0x00001000u
#define PONG_AUDIO_GPIO_CFG         0x0u    /* [1:0] pull, [5:2] function, [8:6] drive, [9] output */
#define PONG_AUDIO_GPIO_IO          0x4u    /* bit0 in, bit1 out */
#define PONG_AUDIO_GPIO_IRQ_CFG     0x8u
#define PONG_AUDIO_GPIO_IRQ_STATUS  0xcu
#define PONG_AUDIO_GPIO_EGPIO_EXISTS (1u << 11)   /* touch patch:163-166 */
#define PONG_AUDIO_GPIO_APPS_CTRL    (1u << 12)   /* set only when bit 11 says eGPIO exists */
#define PONG_AUDIO_GPIO_PULL_UP     3u
#define PONG_AUDIO_GPIO_PULL_NONE   0u
#define PONG_AUDIO_GPIO_FN_GPIO     0u
#define PONG_AUDIO_GPIO_FN_QUP15    1u   /* pinctrl-sm8450.c:1472-1473 PINGROUP(56, qup15, ...) */

/* K60 amplifier pads, all four from L:13318-13341 (aw882xx_smartpa@34 / @35). */
#define PONG_AUDIO_AMP0_RESET_GPIO  1u   /* L:13322 reset-gpio <0x3c 0x01 0x00> */
#define PONG_AUDIO_AMP1_RESET_GPIO  3u   /* L:13335 reset-gpio <0x3c 0x03 0x00> */
#define PONG_AUDIO_AMP0_IRQ_GPIO    88u  /* L:13321 irq-gpio <0x3c 0x58 0x2008> */
#define PONG_AUDIO_AMP1_IRQ_GPIO    63u  /* L:13334 irq-gpio <0x3c 0x3f 0x2008> */
#define PONG_AUDIO_SPKSW_GPIO       52u  /* L:13329 spksw-gpio <0x3c 0x34 0x00> */
#define PONG_AUDIO_I2C_SCL_GPIO     56u  /* L:3562-3593 qupv3_se15_i2c_pins active */
#define PONG_AUDIO_I2C_SDA_GPIO     57u

/* ---- GCC ----------------------------------------------------------------
 * L:788-799  clock-controller@100000, reg <0x100000 0x1f4200>
 * G:2417-2422 wrap2_s0_clk      .halt_reg 0x2e00c, .enable_reg 0x62010, BITS(4)
 * G:2404-2409 wrap2_core_clk    .halt_reg 0x33280, .enable_reg 0x62010, BITS(0)
 * G:2391-2396 wrap2_core_2x_clk .halt_reg 0x3328c, .enable_reg 0x62010, BITS(3)
 * G:2603-2610 wrap_2_m_ahb_clk  .halt_reg 0x2e004, .enable_reg 0x62010, BITS(2), hwcg bit 1
 * G:2618-2625 wrap_2_s_ahb_clk  .halt_reg 0x2e008, .enable_reg 0x62010, BITS(1), hwcg bit 1
 * G:888-896   wrap2_s0_clk_src  .cmd_rcgr 0x2e014 (SE15 = wrapper 2, SE0)
 * NOTE: wrapper 0/1 vote through 0x62008; wrapper 2 through 0x62010. Copying
 * the touch driver's 0x62008 would vote the wrong wrapper.
 */
#define PONG_AUDIO_GCC_PHYS         0x00100000u
#define PONG_AUDIO_GCC_RCG_WIN      0x0002e000u   /* one page covers 0x2e000..0x2efff */
#define PONG_AUDIO_GCC_CBC_WIN      0x00033000u   /* 0x33280, 0x3328c */
#define PONG_AUDIO_GCC_VOTE_WIN     0x00062000u   /* 0x62010 */
#define PONG_AUDIO_GCC_VOTE_WRAP2   0x00062010u
#define PONG_AUDIO_GCC_WRAP2_MASK   0x0000001fu   /* core|s_ahb|m_ahb|core_2x|s0 */
#define PONG_AUDIO_GCC_CBC_CORE     0x00033280u
#define PONG_AUDIO_GCC_CBC_CORE_2X  0x0003328cu
#define PONG_AUDIO_GCC_CBC_M_AHB    0x0002e004u
#define PONG_AUDIO_GCC_CBC_S_AHB    0x0002e008u
#define PONG_AUDIO_GCC_CBC_S0       0x0002e00cu
#define PONG_AUDIO_GCC_RCG_SE15     0x0002e014u
#define PONG_AUDIO_GCC_DFS_LEVELS   8u           /* touch patch:313-324 walks 8 DFS levels */

/* GPLL0 (G:gcc-sm8450.c:50-62): the PLL block starts at GCC+0x0, its enable vote is
 * a bit inside 0x62018, PLL_MODE is offset 0x0 of that block and the lock
 * indication is BIT(31) (M:clk-alpha-pll.c:17-34, PLL_LOCK_DET). HR-02 step 1
 * requires this vote and the lock wait before any QUP branch is touched. */
#define PONG_AUDIO_GCC_PLL_WIN       0x00000000u   /* GCC+0x0: PLL_MODE, one page */
#define PONG_AUDIO_GCC_PLL0_ENABLE   0x00062018u   /* in the vote window, delta 0x18 */
#define PONG_AUDIO_GCC_PLL0_MODE     0x00000000u   /* in the PLL window, delta 0x0 */
#define PONG_AUDIO_GCC_PLL0_VOTE     (1u << 0)
#define PONG_AUDIO_GCC_PLL_LOCK_DET  (1u << 31)
#define PONG_AUDIO_CBCR_CLK_OFF     (1u << 31)   /* clk-branch.c:50-59 halt test */
#define PONG_AUDIO_CBCR_HWCG        (1u << 1)    /* "running" when HW gating is on */

/* ---- QUPV3 wrapper 2 SE0 = the amplifier I2C bus -------------------------
 * L:13301-13310  i2c@880000, qcom,i2c-geni, reg <0x880000 0x4000>, pinctrl-0 <0x100>
 * sm8450.dtsi:981-999  i2c15: i2c@880000, clocks <&gcc GCC_QUPV3_WRAP2_S0_CLK>
 * S:PongAudio.cpp:130-144  the same bring-up for wrapper 1 SE5, four constants differ.
 */
#define PONG_AUDIO_SE15_PHYS        0x00880000u
#define PONG_AUDIO_SE15_SIZE        0x00004000u

/* ---- Awinic AW882xx ------------------------------------------------------
 * L:13318-13329  aw882xx_smartpa@34 (sound-channel 0, spksw-gpio 52)
 * L:13331-13341  aw882xx_smartpa@35 (sound-channel 1, no spksw-gpio)
 * H:355-401      register file, identical offsets across the AW882xx family
 * H:340-350      chip id table
 * Read/write: the probe only reads the registers below. The replay pass that
 * follows it (PongAudioAmpReplay.h) writes the tuning table, so the two write
 * targets are named here as well.
 */
#define PONG_AUDIO_AMP_ADDR0        0x34u
#define PONG_AUDIO_AMP_ADDR1        0x35u
#define AW_REG_ID                   0x00u   /* read = chip id; write 0x55aa = soft reset */
#define AW_REG_SYSST                0x01u
#define AW_REG_SYSINTM              0x03u   /* mask, readable */
#define AW_REG_SYSCTRL              0x04u
#define AW_REG_SYSCTRL2             0x05u   /* volume, top six bits kept */
#define AW_REG_I2SCTRL              0x06u
#define AW_REG_DBGCTRL              0x14u
#define AW_REG_VBAT                 0x21u
#define AW_REG_TEMP                 0x22u
#define AW_REG_PVDD                 0x23u
#define AW_REG_VSNTM1               0x50u
#define AW_REG_EFRH4                0x78u
#define AW_REG_EFRH3                0x79u
#define AW_REG_EFRL4                0x7cu
#define AW_REG_EFRL3                0x7du

/* Status bits (H:363-401). */
#define AW_SYSST_PLLS               (1u << 0)
#define AW_SYSST_OTHS               (1u << 1)
#define AW_SYSST_OCDS               (1u << 3)
#define AW_SYSST_CLKS               (1u << 4)
#define AW_SYSST_NOCLKS             (1u << 5)
#define AW_SYSST_WDS                (1u << 6)
#define AW_SYSST_SWS                (1u << 8)
#define AW_SYSST_BSTS               (1u << 9)
#define AW_SYSST_BSTOCS             (1u << 11)
#define AW_SYSST_UVLS               (1u << 14)
#define AW_SYSST_OVP2S              (1u << 15)
#define AW_SYSST_FAULTS 	(AW_SYSST_OVP2S | AW_SYSST_UVLS | AW_SYSST_BSTOCS | AW_SYSST_WDS | 	 AW_SYSST_NOCLKS | AW_SYSST_OCDS | AW_SYSST_OTHS)

/* AW_SYSCTRL bits (H:376-380). */
#define AW_SYSCTRL_PWDN             (1u << 0)
#define AW_SYSCTRL_AMPPD            (1u << 1)
#define AW_SYSCTRL_HMUTE            (1u << 8)

/* ---- WCD938x / LPASS: recorded here, not touched by this probe -----------
 * Kept next to the amp map so the next file does not have to re-derive them.
 * L:2494-2523  wcd938x_reset_active/sleep pin mux gpio43, 16 mA; active is output-high
 * L:32567-32646 audio-ref-clk tx_core_clk: codec-lpass-clk-id 0x30c, ext 19.2 MHz
 * L:23349-23367 va_swr_master swrm-io-base 0x33b0000, swr_master_id 3, irq 0x1f0/0x208
 * S:PongWcd938.h:59-120  the SM8475 codec bring-up order; every LPASS access needs
 *        two PRM block votes plus the 0x30c clock acknowledgement first, so none
 *        of it can run before the ADSP answers.
 */
#define PONG_AUDIO_CODEC_RESET_GPIO 43u
#define PONG_AUDIO_TX_CORE_CLK_ID   0x30cu
#define PONG_AUDIO_TX_CORE_HZ       19200000u
#define PONG_AUDIO_VA_SWR_PHYS      0x033b0000u
#define PONG_AUDIO_TX_MACRO_PHYS    0x03220000u
#define PONG_AUDIO_VA_MACRO_PHYS    0x033f0000u

#endif /* PONG_AUDIO_REGS_H */
