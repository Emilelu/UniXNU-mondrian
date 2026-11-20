/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* The boot-argument reader: the only way a driver learns it was asked to run. */
#ifndef PONG_STUB_PEXPERT_PEXPERT_H
#define PONG_STUB_PEXPERT_PEXPERT_H
#include <sys/types.h>
/* V: xnu pexpert/pexpert/pexpert.h:351, boolean_t PE_parse_boot_argn(...) */
boolean_t PE_parse_boot_argn(const char *arg_string, void *arg_ptr, int max_arg);
#endif
