#include <pexpert/arm64/board_config.h>
/* Bounded kernel-side progress, without a private sysctl or user copy. */
#if defined(PONG) && (DEVELOPMENT || DEBUG)
#include <sys/param.h>
#include <sys/systm.h>
#include <sys/proc.h>
#include <kern/startup.h>
#include <machine/machine_routines.h>

volatile int pong_init_user_seen;
static TUNABLE(bool, pong_init_notes, "pong_init_trace", false);
void pong_init_note(const char *);
void
pong_init_note(const char *stage)
{
    static unsigned count;
    if (!pong_init_notes || !pong_init_user_seen || count >= 32 ||
        !ml_get_interrupts_enabled()) return;
    proc_t p = current_proc();
    if (!p || proc_pid(p) != 1) return;
    ++count;
    printf("Pong init: %s\n", stage);
}
#endif
