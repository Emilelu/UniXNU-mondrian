/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/* Pong SM8475 thermal sensors: read-only tsens v2 reader for the XNU kernel.
 *
 * This file is the master copy. patches/xnu/0617-k60-thermal-tsens.patch carries
 * it into the XNU tree verbatim as bsd/dev/pong_thermal.c; the patch is what the
 * kernel build sees, because the kernel cannot include drivers/PongThermal.
 * scripts/check-thermal-kernel-patch.py fails when the two copies differ.
 *
 * What it does: maps the two TM windows and the two SROT windows, reads the
 * hardware version and the enable bit, then samples all 32 sensors once a second,
 * prints the five pressure-level domains and hands the resulting level to
 * bsd/dev/pong_thermal_pm.cpp, which publishes it through IOPMrootDomain. It never
 * writes a register, never touches an interrupt, and never programs a trip point:
 * those need calibration coefficients this board does not expose
 * (docs/research/thermal/01 section 4).
 *
 * Register map: mainline Linux drivers/thermal/qcom/tsens-v2.c:12-27, 94-101.
 * Board addresses: DTB /soc/thermal-sensor@c263000 and @c265000, reg[0] = TM and
 * reg[1] = SROT (docs/research/thermal/01-SAME-HARDWARE.md section 2). */
#include <pexpert/arm64/board_config.h>
#if defined(PONG)
#include <kern/clock.h>
#include <kern/sched_prim.h>
#include <kern/thread.h>
#include <libkern/libkern.h>
#include <pexpert/pexpert.h>
#include <sys/pong_thermal.h>
#include <sys/pong_thermal_level.h>
#include <sys/systm.h>

extern vm_offset_t ml_io_map(vm_offset_t phys_addr, vm_size_t size);

/* bsd/dev/pong_thermal_pm.cpp: hands one pressure level to IOPMrootDomain. It returns
 * without doing anything until IOKit has a root domain, which is why it is called every
 * round rather than once from pong_thermal_init. */
extern void pong_thermal_pm_publish(unsigned int level);

#define PONG_THERMAL_WINDOW     0x1000UL
#define PONG_THERMAL_POLL_MS    1000
#define PONG_THERMAL_HEARTBEAT  30   /* poll rounds between unconditional lines */

struct pong_thermal_controller {
	uint64_t tm_phys;
	uint64_t srot_phys;
	const char *label;
	volatile uint32_t *tm;
	volatile uint32_t *srot;
	uint32_t hw_ver;
	uint32_t ctrl;
	int mapped;
};

static struct pong_thermal_controller pong_thermal_controllers[PONG_THERMAL_CONTROLLERS] = {
	{ 0x0c263000ull, 0x0c222000ull, "tsens0", 0, 0, 0, 0, 0 },
	{ 0x0c265000ull, 0x0c223000ull, "tsens1", 0, 0, 0, 0, 0 },
};

static uint32_t
pong_thermal_rd(const volatile uint32_t *base, uint32_t offset)
{
	return base[offset / 4u];
}

/* One 32-bit load per sensor; the caller owns the mapping. */
static int
pong_thermal_sample(struct pong_thermal_controller *c, unsigned base_slot,
    int32_t milli_c[PONG_THERMAL_SENSOR_COUNT], uint32_t raw[PONG_THERMAL_SENSORS_PER_CONTROLLER])
{
	struct pong_thermal_reading reading;
	unsigned i;
	int valid = 0;

	if (!c->mapped) {
		for (i = 0; i < PONG_THERMAL_SENSORS_PER_CONTROLLER; i++) {
			milli_c[base_slot + i] = INT32_MIN;
			raw[i] = 0;
		}
		return 0;
	}
	for (i = 0; i < PONG_THERMAL_SENSORS_PER_CONTROLLER; i++) {
		raw[i] = pong_thermal_rd(c->tm, PONG_THERMAL_TM_SN_STATUS(i));
		if (pong_thermal_decode(raw[i], &reading) == PONG_THERMAL_OK) {
			milli_c[base_slot + i] = reading.milli_c;
			valid++;
		} else {
			milli_c[base_slot + i] = INT32_MIN;
		}
	}
	return valid;
}

static void
pong_thermal_read_all(int32_t milli_c[PONG_THERMAL_SENSOR_COUNT])
{
	uint32_t raw[PONG_THERMAL_SENSORS_PER_CONTROLLER];
	unsigned c;

	for (c = 0; c < PONG_THERMAL_CONTROLLERS; c++) {
		(void)pong_thermal_sample(&pong_thermal_controllers[c],
		    c * PONG_THERMAL_SENSORS_PER_CONTROLLER, milli_c, raw);
	}
}

/* Boot-time dump: one line per sensor, so a serial capture names every sensor.
 * The percentages are the value the pressure-level consumer will see. */
static void
pong_thermal_dump(void)
{
	int32_t milli_c[PONG_THERMAL_SENSOR_COUNT];
	uint32_t raw[PONG_THERMAL_SENSORS_PER_CONTROLLER];
	unsigned c, i;

	for (c = 0; c < PONG_THERMAL_CONTROLLERS; c++) {
		struct pong_thermal_controller *ctl = &pong_thermal_controllers[c];

		if (!ctl->mapped) {
			printf("PongThermal: %s not mapped; skipping\n", ctl->label);
			continue;
		}
		printf("PongThermal: %s tm=%#llx srot=%#llx ver=%u.%u.%u ctrl=%#x enabled=%d\n",
		    ctl->label, (unsigned long long)ctl->tm_phys,
		    (unsigned long long)ctl->srot_phys,
		    PONG_THERMAL_VER_MAJOR(ctl->hw_ver), PONG_THERMAL_VER_MINOR(ctl->hw_ver),
		    PONG_THERMAL_VER_STEP(ctl->hw_ver), ctl->ctrl,
		    pong_thermal_ctrl_enabled(ctl->ctrl));
		(void)pong_thermal_sample(ctl, c * PONG_THERMAL_SENSORS_PER_CONTROLLER, milli_c, raw);
		for (i = 0; i < PONG_THERMAL_SENSORS_PER_CONTROLLER; i++) {
			const struct pong_thermal_sensor *sensor =
			    pong_thermal_sensor_at(c * PONG_THERMAL_SENSORS_PER_CONTROLLER + i);
			int32_t mc = milli_c[c * PONG_THERMAL_SENSORS_PER_CONTROLLER + i];

			if (sensor == 0) {
				continue;
			}
			if (mc == INT32_MIN) {
				printf("PongThermal: %s[%u] %s zone%u raw=%#x no-valid-reading\n",
				    ctl->label, i, sensor->name, sensor->zone, raw[i]);
			} else {
				printf("PongThermal: %s[%u] %s zone%u %d.%d C\n",
				    ctl->label, i, sensor->name, sensor->zone,
				    (int)(mc / 1000), (int)((mc < 0 ? -mc : mc) % 1000) / 100);
			}
		}
	}
}

/* Five pressure-level domains, hottest sensor of each. The macOS side reads the
 * same five groups (docs/research/thermal/05-PRESSURE-LEVEL.md section 2). */
static void
pong_thermal_domains(int32_t domains[PONG_THERMAL_DOMAINS])
{
	int32_t milli_c[PONG_THERMAL_SENSOR_COUNT];

	pong_thermal_read_all(milli_c);
	pong_thermal_domain_max(milli_c, domains);
}

static void
pong_thermal_worker(void *arg, wait_result_t result)
{
	int32_t domains[PONG_THERMAL_DOMAINS];
	int32_t previous[PONG_THERMAL_DOMAINS];
	K60TlState level_state;
	uint64_t deadline;
	unsigned round = 0, i;

	(void)arg;
	(void)result;
	for (i = 0; i < PONG_THERMAL_DOMAINS; i++) {
		previous[i] = INT32_MIN;
	}
	memset(&level_state, 0, sizeof(level_state));
	for (;;) {
		bool changed = false;
		unsigned level;

		pong_thermal_domains(domains);
		for (i = 0; i < PONG_THERMAL_DOMAINS; i++) {
			/* one-degree bucket: a quieter log than 32 lines a second */
			if (domains[i] == INT32_MIN || previous[i] == INT32_MIN ||
			    domains[i] / 1000 != previous[i] / 1000) {
				changed = true;
			}
			previous[i] = domains[i];
		}
		if (changed || ++round >= PONG_THERMAL_HEARTBEAT) {
			round = 0;
			printf("PongThermal: little=%d big=%d gpu=%d npu=%d ddr=%d mC\n",
			    domains[PONG_THERMAL_DOMAIN_LITTLE], domains[PONG_THERMAL_DOMAIN_BIG],
			    domains[PONG_THERMAL_DOMAIN_GPU], domains[PONG_THERMAL_DOMAIN_NPU],
			    domains[PONG_THERMAL_DOMAIN_DDR]);
		}
		/* Hysteresis lives in k60tl_step: a trip already crossed is released only
		 * below its temperature minus the DT's hysteresis. Publishing is a no-op
		 * until the root domain exists, and after that only on a level change. */
		level = k60tl_step(&level_state, domains);
		pong_thermal_pm_publish(level);
		clock_interval_to_deadline(PONG_THERMAL_POLL_MS, NSEC_PER_MSEC, &deadline);
		assert_wait_deadline((event_t)pong_thermal_controllers, THREAD_UNINT, deadline);
		(void)thread_block(THREAD_CONTINUE_NULL);
	}
}

void
pong_thermal_init(void)
{
	uint32_t enabled = 1;
	thread_t thread;
	unsigned c;

	/* Absent boot-arg leaves the compiled-in default alone: PE_parse_boot_argn
	 * returns FALSE both for "absent" and for "0", so its result is ignored. */
	(void)PE_parse_boot_argn("pong_thermal", &enabled, sizeof(enabled));
	if (enabled == 0) {
		printf("PongThermal: disabled by boot-arg pong_thermal=0\n");
		return;
	}
	for (c = 0; c < PONG_THERMAL_CONTROLLERS; c++) {
		struct pong_thermal_controller *ctl = &pong_thermal_controllers[c];

		ctl->tm = (volatile uint32_t *)ml_io_map((vm_offset_t)ctl->tm_phys,
		    PONG_THERMAL_WINDOW);
		ctl->srot = (volatile uint32_t *)ml_io_map((vm_offset_t)ctl->srot_phys,
		    PONG_THERMAL_WINDOW);
		if (ctl->tm == 0 || ctl->srot == 0) {
			printf("PongThermal: %s window mapping failed (tm=%p srot=%p)\n",
			    ctl->label, (void *)ctl->tm, (void *)ctl->srot);
			continue;
		}
		ctl->mapped = 1;
		ctl->hw_ver = pong_thermal_rd(ctl->srot, PONG_THERMAL_SROT_HW_VER);
		ctl->ctrl = pong_thermal_rd(ctl->srot, PONG_THERMAL_SROT_CTRL);
	}
	pong_thermal_dump();
	if (!pong_thermal_controllers[0].mapped && !pong_thermal_controllers[1].mapped) {
		printf("PongThermal: no controller mapped; not polling\n");
		return;
	}
	if (kernel_thread_start(pong_thermal_worker, 0, &thread) == KERN_SUCCESS) {
		thread_deallocate(thread);
		printf("PongThermal: polling %u controllers every %u ms\n",
		    PONG_THERMAL_CONTROLLERS, PONG_THERMAL_POLL_MS);
	} else {
		printf("PongThermal: worker thread failed; boot snapshot only\n");
	}
}
#endif /* PONG */
