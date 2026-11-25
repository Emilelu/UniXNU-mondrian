// Minimal glue for the upstream source-storage runtime.
//
// SourceStorage.cpp and its 27 policy helpers expect the vendor diagnostic
// counters and a few optional UFS helpers. Our own driver exports the factory
// (native_ufs_source_create) and the real block devices; the symbols below are
// observation-only or bench-only and are deliberately inert here. Keeping them
// in one small translation unit avoids dragging the whole vendor driver in.
#include <stdint.h>

extern "C" {
volatile uint64_t boot_log_errors = 0;
volatile uint64_t boot_log_rounds = 0;
volatile uint64_t boot_log_state = 0;
volatile uint64_t boot_log_open_refusal = 0;
void boot_log_tick(uint64_t) {}

int native_ufs_part_read(uint32_t, uint64_t, uint32_t, void *) { return -1; }
int native_ufs_part_find(const char *, uint32_t *, uint64_t *, uint64_t *) { return -1; }
int native_ufs_dme_get(uint32_t, uint32_t, uint32_t *) { return -1; }
void native_ufs_set_spin(uint32_t) {}
void native_ufs_set_zero_copy(int) {}
volatile uint64_t native_ufs_block_authenticates = 0;

// SourceStorage.cpp asks the linker for the vendor objects' static initialisers
// by name. Our objects are compiled into the same archive, but Mach-O keeps
// those initialisers local, so give the runtime an explicit no-op they can bind.
void k60_sub_io_block() __asm("__GLOBAL__sub_I_IOBlockStorageDevice.cpp");
void k60_sub_io_block() {}
void k60_sub_native_ufs() __asm("__GLOBAL__sub_I_NativeUfs.cpp");
void k60_sub_native_ufs() {}
void k60_sub_native_ram() __asm("__GLOBAL__sub_I_NativeRamBlock.cpp");
void k60_sub_native_ram() {}
}
