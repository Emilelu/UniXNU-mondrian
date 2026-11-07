/* Bounded UI crash capture derived from HackiOS user_exception_trace.c.
 * Exception delivery is unchanged; no polling threads or periodic probes.
 */
#include <pexpert/arm64/board_config.h>
#if defined(ARM64_BOARD_CONFIG_PONG) && (DEVELOPMENT || DEBUG)
#include <arm/thread.h>
#include <kern/misc_protos.h>
#include <kern/task.h>
#include <kern/thread.h>
#include <mach/exception_types.h>
#include <machine/machine_routines.h>
#include <string.h>
#include <vm/vm_map.h>
#include <vm/vm_shared_region.h>

extern char *proc_name_address(struct proc *p);
extern int proc_pid(struct proc *p);
void pong_ui_exception(exception_type_t, mach_exception_data_t,
    mach_msg_type_number_t, thread_t);

void
pong_ui_exception(exception_type_t exception, mach_exception_data_t code,
    mach_msg_type_number_t count, thread_t thread)
{
	static unsigned records[5];
	static const char * const names[] = { "SpringBoard", "backboardd", "containermanagerd", "contextstored", "biomed" };
	static const unsigned message_regs[] = { 0, 1, 2, 3, 8, 16 };
	if (!ml_get_interrupts_enabled() || thread != current_thread() ||
	    (exception != EXC_BREAKPOINT && exception != EXC_BAD_INSTRUCTION)) return;
	task_t task = get_threadtask(thread);
	const arm_saved_state_t *state = get_user_regs(thread);
	struct proc *proc = get_bsdtask_info(task);
	if (task == kernel_task || proc == NULL || state == NULL || !is_saved_state64(state)) return;
	const char *name = proc_name_address(proc);
	unsigned which;
	for (which = 0; which < 5 && strcmp(name, names[which]) != 0; which++) { }
	if (which == 5 || __atomic_fetch_add(&records[which], 1, __ATOMIC_RELAXED) >= 4) return;
	vm_shared_region_t region = vm_shared_region_get(task);
	uint32_t slide = region ? region->sr_slide : 0;
	if (region) vm_shared_region_deallocate(region);
	printf("Pong UI crash: %s[%d] exception=%d code=0x%llx/0x%llx pc=0x%llx lr=0x%llx sp=0x%llx cache_slide=0x%x\n",
	    name, proc_pid(proc), exception, count ? code[0] : 0, count > 1 ? code[1] : 0,
	    (uint64_t)get_saved_state_pc(state), (uint64_t)get_saved_state_lr(state),
	    (uint64_t)get_saved_state_sp(state), slide);
	for (unsigned i = 0; i < sizeof(message_regs) / sizeof(message_regs[0]); i++) {
		user_addr_t address = get_saved_state_reg(state, message_regs[i]);
		char text[128] = { 0 };
		vm_size_t length = 0;
		if (address < 0x100000000ULL || address >= MACH_VM_MAX_ADDRESS ||
		    copyinstr(address, text, sizeof(text) - 1, &length) != 0 || length < 7) continue;
		bool printable = true;
		for (unsigned c = 0; c < 6; c++) printable &= text[c] >= 0x20 && text[c] < 0x7f;
		if (printable) printf("Pong UI crash: x%u text=%s\n", message_regs[i], text);
	}
	uint64_t fp = get_saved_state_fp(state), sp = get_saved_state_sp(state), frame[2];
	for (unsigned depth = 0; depth < 12; depth++) {
		if (fp < sp || fp - sp > 1024 * 1024 || fp >= MACH_VM_MAX_ADDRESS - sizeof(frame) ||
		    (fp & 15) || copyin(fp, frame, sizeof(frame)) != 0) break;
		printf("Pong UI crash: frame%u lr=0x%llx\n", depth, frame[1]);
		if (frame[0] <= fp) break;
		fp = frame[0];
	}
}
#endif
