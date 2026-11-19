/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* The mapping call each driver makes; declared here so a host build can link. */
#ifndef PONG_STUB_ML_IO_MAP_H
#define PONG_STUB_ML_IO_MAP_H
#include <sys/types.h>
vm_offset_t ml_io_map(vm_offset_t phys_addr, vm_size_t size);
vm_offset_t ml_io_map_wcomb(vm_offset_t phys_addr, vm_size_t size);
#endif
