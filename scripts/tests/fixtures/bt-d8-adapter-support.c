/* SPDX-License-Identifier: GPL-2.0-only */
/* Test-only translation unit for the real qbt_linux.c adapter.  Keeping it
 * separate avoids including btqca.h twice (the upstream header has no guard)
 * and gives the harness controlled access to qbt_linux.c's static owner. */
#include "qbt_linux.c"
void fixture_set_startup_owner(struct qbt *q) { startup_owner = q; }
int fixture_startup_owner_is_null(void) { return startup_owner == NULL; }
