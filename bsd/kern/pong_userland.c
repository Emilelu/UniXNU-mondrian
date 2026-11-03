#include <pexpert/arm64/board_config.h>
/* Pong / 20G81 static-init progress, recorded by the existing kernel console. */
/* Retired: boot progress uses the existing console; do not register a
 * private sysctl solely to let PID 1 print its first message. */
#if defined(PONG_INIT_SYSCTL_LOG) && PONG_INIT_SYSCTL_LOG
#include <sys/param.h>
#include <sys/systm.h>
#include <sys/proc.h>
#include <sys/sysctl.h>
#include <sys/errno.h>

static int
pong_boot_log SYSCTL_HANDLER_ARGS
{
    char message[256] = {0};
    if (req->newptr == USER_ADDR_NULL || req->newlen == 0) return EINVAL;
    if (proc_pid(req->p) != 1) return EPERM;
    int error = sysctl_handle_string(oidp, message, sizeof(message), req);
    if (error) return error;
    printf("Pong init: %s\n", message);
    return 0;
}
SYSCTL_PROC(_kern, OID_AUTO, pong_boot_log,
    CTLTYPE_STRING | CTLFLAG_WR | CTLFLAG_LOCKED,
    0, 0, pong_boot_log, "A", "PID 1 boot milestones");
#endif
