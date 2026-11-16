/* Host-only declaration: the fixture supplies the boot-argument parser. */
#ifndef K60_RAIL_TEST_PEXPERT_H
#define K60_RAIL_TEST_PEXPERT_H
int PE_parse_boot_argn(const char *name, void *out, int bytes);
#endif
