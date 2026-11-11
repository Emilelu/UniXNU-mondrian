/*
 * Pong / UniXNU adaptation of HackiOS stage0 and init (MIT; see ../LICENSE).
 * Static Darwin 22 executable; optional 20G81 UI library is configured separately.
 */
#include "mini.h"

/* Apple clang may lower zero-initialized aggregates to bzero even freestanding. */
void bzero(void *p, size_t n) { memset(p, 0, n); }

/* Reuse the ordinary console path; boot progress must not depend on a
 * custom sysctl or its name lookup/locking before launchd can start. */
static int  g_pong_data_writable;

static void
boot_stage(const char *message)
{
    printf("Pong init: %s\n", message);
}

static unsigned long
number(const char *s, int base)
{
    unsigned long v = 0;
    while (*s >= '0' && *s <= '9' && *s - '0' < base)
        v = v * (unsigned)base + (unsigned)(*s++ - '0');
    return v;
}

static int
read_text(const char *path, char *buf, size_t cap)
{
    int fd = open(path, O_RDONLY, 0);
    size_t used = 0;
    ssize_t n;
    if (fd < 0) return -1;
    while (used + 1 < cap && (n = read(fd, buf + used, cap - used - 1)) > 0)
        used += (size_t)n;
    close(fd);
    buf[used] = 0;
    return (int)used;
}

static int
copy_new(const char *source, const char *dest, int mode, int uid, int gid)
{
    char buf[4096];
    int in = open(source, O_RDONLY, 0), out;
    ssize_t n;
    if (in < 0) return -1;
    out = open(dest, O_WRONLY | O_CREAT | O_EXCL, mode);
    if (out < 0) { close(in); return errno == 17 ? 0 : -1; }
    int ok = 0;
    while ((n = read(in, buf, sizeof(buf))) > 0) {
        ssize_t done = 0;
        while (done < n) {
            ssize_t w = write(out, buf + done, (size_t)(n - done));
            if (w <= 0) { ok = -1; break; }
            done += w;
        }
        if (ok) break;
    }
    if (n < 0) ok = -1;
    close(in); close(out);
    if (ok) { unlink(dest); return -1; }
    return chmod(dest, mode) || chown(dest, uid, gid) ? -1 : 0;
}

static void
prepare_var(void)
{
    static char buf[65536];
    char args[4096] = {0}, device[96] = {0};
    size_t len = sizeof(args);
    struct stat root, var;
    boot_stage("var: stat root");
    int root_ok = stat("/", &root) == 0;
    int separate = root_ok && stat("/private/var", &var) == 0 &&
                   root.st_dev != var.st_dev;
    boot_stage("var: stat root done");
    printf("Pong init: var separate=%d\n", separate);
    /* Explicit device only. Never guess disk numbers or format an existing disk. */
    if (!separate && sysctlbyname("kern.bootargs", args, &len, NULL, 0) == 0) {
        args[sizeof(args) - 1] = 0;
        const char *key = "pong_data_device=";
        for (char *p = args; *p;) {
            while (*p == ' ') p++;
            if (strncmp(p, key, strlen(key)) == 0) {
                p += strlen(key);
                size_t n = 0;
                while (*p && *p != ' ' && n + 1 < sizeof(device)) device[n++] = *p++;
                device[n] = 0;
                break;
            }
            while (*p && *p != ' ') p++;
        }
        if (root_ok && strncmp(device, "/dev/disk", 9) == 0) {
            /* Apple APFS 2142 mount ABI already used by the qualified Pong owner hook. */
            uint8_t payload[0x150] = {0};
            uint64_t fspec = (uint64_t)(uintptr_t)device, flags = 0;
            uint16_t mode = 1;
            uint32_t owner = 99;
            memcpy(payload, &fspec, 8); memcpy(payload + 8, &flags, 8);
            memcpy(payload + 16, &mode, 2);
            memcpy(payload + 0x144, &owner, 4); memcpy(payload + 0x148, &owner, 4);
            int result = mount("apfs", "/private/var", 0, payload);
            int error = result ? errno : 0;
            separate = result == 0 && stat("/private/var", &var) == 0 &&
                       root.st_dev != var.st_dev;
            printf("Pong init: Data mount %s result=%d errno=%d\n", device, result, error);
        }
    }
    if (!separate) {
        puts("Pong init: no separate writable Data volume; var seed skipped (required for full iOS startup)");
        return;
    }
    boot_stage("var: write-check open");
    int fd = open("/private/var/.pong-write-check", O_CREAT | O_EXCL | O_WRONLY, 0600);
    if (fd < 0) { printf("Pong init: Data not writable: errno=%d\n", errno); return; }
    close(fd); unlink("/private/var/.pong-write-check");
    g_pong_data_writable = 1;
    boot_stage("var: write-check done");
    if (read_text("/pong/etc/var.skel", buf, sizeof(buf)) < 0) {
        printf("Pong init: var.skel unavailable: errno=%d\n", errno); return;
    }
    int made = 0, errors = 0;
    for (char *line = buf; *line;) {
        char *end = strchr(line, '\n'), *field[6] = {line};
        int count = 1;
        if (end) *end = 0;
        for (char *p = line; *p; p++) if (*p == '\t' && count < 6) {
            *p = 0; field[count++] = p + 1;
        }
        int result = 0;
        if (count == 5 && field[0][0] == 'd') {
            struct stat st;
            if (lstat(field[4], &st) != 0) {
                result = mkdir(field[4], (int)number(field[1], 8));
                if (!result) result = chmod(field[4], (int)number(field[1], 8)) ||
                    chown(field[4], (int)number(field[2], 10), (int)number(field[3], 10));
                if (!result) made++;
            } else if ((st.st_mode & S_IFMT) != S_IFDIR) result = -1;
        } else if (count == 3 && field[0][0] == 'l') {
            struct stat st;
            if (lstat(field[2], &st) != 0) result = symlink(field[1], field[2]);
        } else if (count == 6 && field[0][0] == 'f') {
            result = copy_new(field[5], field[4], (int)number(field[1], 8),
                              (int)number(field[2], 10), (int)number(field[3], 10));
        }
        errors += result != 0;
        if (!end) break;
        line = end + 1;
    }
    printf("Pong init: writable Data ready, created=%d seed-errors=%d\n", made, errors);
}

/* Repair older Data seeds without replacing valid user timezone settings.
 * On 20G81 /usr/share/zoneinfo already links back into this Data directory. */
static void
prepare_runtime_paths(void)
{
    struct stat st;
    /* The sparse restore skeleton omits these database parents. Consumers
     * run as mobile and cannot create a multi-level path in one mkdir. */
    static const char *mobile_dirs[]={
        "/private/var/mobile/Library/CoreDuet",
        "/private/var/mobile/Library/CoreDuet/Knowledge",
        "/private/var/mobile/Library/IdentityServices",
        "/private/var/mobile/Library/IdentityServices/PDS",
        "/private/var/mobile/Library/Logs",
        "/private/var/mobile/Library/Logs/CrashReporter"
    };
    for (unsigned i=0;i<sizeof(mobile_dirs)/sizeof(mobile_dirs[0]);i++) {
        const char *p=mobile_dirs[i];
        if (lstat(p,&st)==0) continue;
        if (mkdir(p,0700)!=0 || chown(p,501,501)!=0 || chmod(p,0700)!=0)
            printf("Pong init: mobile database parent unavailable %s errno=%d\n",p,errno);
    }
    const char *zone = "/private/var/db/timezone/zoneinfo";
    const char *local = "/private/var/db/timezone/localtime";
    if (stat("/usr/share/zoneinfo.default/UTC", &st) == 0 && stat(zone, &st) != 0) {
        int present = lstat(zone, &st) == 0;
        if ((!present || (st.st_mode & S_IFMT) == S_IFLNK) &&
            (!present || unlink(zone) == 0)) {
            if (symlink("/usr/share/zoneinfo.default", zone) == 0)
                puts("Pong init: timezone path repaired -> /usr/share/zoneinfo.default");
            else printf("Pong init: timezone path repair failed: errno=%d\n", errno);
        }
    }
    if (stat(local, &st) != 0 && stat("/usr/share/zoneinfo.default/UTC", &st) == 0) {
        int present = lstat(local, &st) == 0;
        if ((!present || (st.st_mode & S_IFMT) == S_IFLNK) &&
            (!present || unlink(local) == 0) &&
            symlink("/var/db/timezone/zoneinfo/UTC", local) != 0)
            printf("Pong init: localtime fallback failed: errno=%d\n", errno);
    }
    if (lstat("/private/var/cores", &st) != 0) {
        if (mkdir("/private/var/cores", 01775) == 0)
            (void)chmod("/private/var/cores", 01775);
        else printf("Pong init: cores directory unavailable: errno=%d\n", errno);
    }
}

/* IOKit's fallback calendar is initialized before ArmDTPlatform is matched.
 * The packager supplies a per-build UTC epoch; PID 1 applies it before any
 * stock daemon sees 1970 timestamps. */
static void
prepare_calendar(void)
{
    char args[4096] = {0};
    size_t len=sizeof(args);
    if (sysctlbyname("kern.bootargs",args,&len,NULL,0)!=0) return;
    args[sizeof(args)-1]=0;
    for (char *p=args;*p;) {
        while (*p==' ') p++;
        if (strncmp(p,"epoch=",6)==0) {
            unsigned long epoch=number(p+6,10);
            if (epoch>=978307200UL) {
                struct timeval tv={.tv_sec=(long)epoch,.tv_usec=0};
                int result=settimeofday(&tv,NULL);
                printf("Pong init: calendar epoch=%lu result=%d errno=%d\n",
                       epoch,result,result?errno:0);
            }
            return;
        }
        while (*p && *p!=' ') p++;
    }
}

/* Same composition as HackiOS init: hide physical audio plug-ins before
 * mediaserverd scans them. Keep mediaserverd for VideoToolbox/HEIC decoding.
 * The optional job set is a real 20G81 directory supplied in writable Data. */
/* K60: launchd honours /private/var/db/com.apple.xpc.launchd/disabled.plist.
 * The label list is DATA, not code: read /private/var/pong/disabled-labels.txt
 * (one label per line, '#' comments) and emit an XML plist at runtime. That way
 * a daemon can be re-enabled (Wi-Fi, Bluetooth, location, ... once their drivers
 * exist) by editing one text file on the Data volume, with no init rebuild. */
static const char *const k60_default_disabled[] = {
    "com.apple.Safari.passwordbreachd",
    "com.apple.SafariBookmarksSyncAgent",
    "com.apple.webinspectord",
    "com.apple.Safari.History",
    "com.apple.safarifetcherd",
    "com.apple.WebBookmarks.webbookmarksd",
    "com.apple.AuthenticationServicesCore.AuthenticationServicesAgent",
    "com.apple.webkit.webpushd",
    "com.apple.watchdogd",
};

static int
k60_emit_label(int fd, const char *label, unsigned len)
{
    static const char pre[] = "<key>";
    static const char mid[] = "</key><true/>\n";
    if (write(fd, pre, sizeof(pre) - 1) < 0) return -1;
    if (write(fd, label, len) < 0) return -1;
    if (write(fd, mid, sizeof(mid) - 1) < 0) return -1;
    return 0;
}

static void
prepare_launchd_disabled(void)
{
    (void)mkdir("/private/var/db", 0755);
    (void)mkdir("/private/var/db/com.apple.xpc.launchd", 0755);
    const char *out = "/private/var/db/com.apple.xpc.launchd/disabled.plist";
    int fd = open(out, O_CREAT | O_WRONLY | O_TRUNC, 0644);
    if (fd < 0) {
        printf("Pong init: disabled.plist open errno=%d\n", errno);
        return;
    }
    static const char head[] =
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" "
        "\"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">\n"
        "<plist version=\"1.0\">\n<dict>\n";
    static const char tail[] = "</dict>\n</plist>\n";
    (void)write(fd, head, sizeof(head) - 1);

    unsigned count = 0;
    int in = open("/private/var/pong/disabled-labels.txt", O_RDONLY, 0);
    if (in >= 0) {
        static char buf[8192];
        ssize_t n = read(in, buf, sizeof(buf) - 1);
        close(in);
        if (n > 0) {
            buf[n] = 0;
            char *line = buf;
            while (*line) {
                char *end = strchr(line, '\n');
                if (end) *end = 0;
                char *p = line;
                while (*p == ' ' || *p == '\t') p++;
                if (*p && *p != '#') {
                    size_t len = strlen(p);
                    while (len && (p[len-1] == '\r' || p[len-1] == ' ')) p[--len] = 0;
                    if (len && k60_emit_label(fd, p, (unsigned)len) == 0) count++;
                }
                if (!end) break;
                line = end + 1;
            }
        }
    }
    if (!count) {
        for (unsigned i = 0; i < sizeof(k60_default_disabled)/sizeof(k60_default_disabled[0]); i++) {
            if (k60_emit_label(fd, k60_default_disabled[i],
                    (unsigned)strlen(k60_default_disabled[i])) == 0) count++;
        }
    }
    (void)write(fd, tail, sizeof(tail) - 1);
    close(fd);
    printf("Pong init: disabled.plist wrote %u labels\n", count);
}

static void
prepare_boot_services(void)
{
    static const struct { const char *source, *target; } views[] = {
        {"/private/var/pong/boot-jobs", "/pong/LaunchDaemons"},
        {"/private/var/pong/empty-hal", "/System/Library/Audio/Plug-Ins/HAL"},
        {"/private/var/pong/empty-hal", "/Library/Audio/Plug-Ins/HAL"},
        /* Keep a read-only path to stock assets before overlaying their
         * directory. The RAM view contains aliases, not copied pictures. */
        {"/Library/Wallpaper", "/private/var/pong/stock-wallpaper"},
        {"/private/var/pong/Wallpaper", "/Library/Wallpaper"}
    };
    for (unsigned i = 0; i < sizeof(views)/sizeof(views[0]); i++) {
        struct stat source, target;
        if (i==4) {
            int r1 = stat("/private/var/pong/stock-wallpaper/Collections/Collections~ipad.plist",&source);
            if (r1 != 0) {
                puts("Pong init: wallpaper aliases SKIP (stock view unavailable)");
                continue;
            }
            /* Guard (v10guard): never enter the bindfs mount unless both the
             * bindfs source and the mount target exist. Target first: when
             * /Library/Wallpaper is absent from the OS window that is the
             * primary reason this alias cannot apply. */
            struct stat gs, gt;
            int gtgt = stat("/Library/Wallpaper",&gt);
            int gsrc = stat("/private/var/pong/Wallpaper",&gs);
            if (gtgt != 0) { puts("Pong init: wallpaper alias SKIP (no target)"); continue; }
            if (gsrc != 0) { puts("Pong init: wallpaper alias SKIP (no source)"); continue; }
        }
        if (strcmp(views[i].target,"/Library/Wallpaper")==0 &&
            stat("/private/var/pong/stock-wallpaper/Collections/Collections~ipad.plist",&source)!=0) {
            puts("Pong init: wallpaper aliases SKIP (stock view unavailable)");
            continue;
        }
        if (lstat(views[i].source,&source)!=0 || (source.st_mode&S_IFMT)!=S_IFDIR ||
            source.st_uid!=0 || (source.st_mode&022)!=0 ||
            stat(views[i].target,&target)!=0 || (target.st_mode&S_IFMT)!=S_IFDIR) {
            printf("Pong init: optional boot view SKIP %s (source/target unavailable)\n",views[i].target);
            continue;
        }
        int result=mount("bindfs",views[i].target,MNT_RDONLY,(void *)views[i].source);
        printf("Pong init: boot view %s -> %s result=%d errno=%d\n",
               views[i].source,views[i].target,result,result?errno:0);
    }
}

static void
configure_ui_library(void)
{
    const char *path="/private/var/pong/libpong-ui.dylib";
    const char *base="/private/var/pong/libpong-ui.dylib SpringBoard backboardd containermanagerd containermanagerd_system mediaserverd Preferences";
    const char *metal="; /private/var/pong/PongAdrenoMetal.bundle/PongAdrenoMetal backboardd";
    char conf[512],args[4096]={0};size_t length=sizeof(args);
    memcpy(conf,base,strlen(base)+1);
    struct stat st;
    if (stat(path,&st)!=0 || (st.st_mode&S_IFMT)!=S_IFREG || st.st_uid!=0) {
        puts("Pong init: UI compatibility library absent; SKIP");return;
    }
    if(sysctlbyname("kern.bootargs",args,&length,NULL,0)==0) {
        args[sizeof(args)-1]=0;
        for(char *p=args;*p;) {
            while(*p==' ')p++;
            if(strncmp(p,"pong_metal=1",12)==0 && (!p[12] || p[12]==' ')) {
                if(stat("/private/var/pong/PongAdrenoMetal.bundle/PongAdrenoMetal",&st)==0 &&
                   (st.st_mode&S_IFMT)==S_IFREG && st.st_uid==0 && !(st.st_mode&022)) {
                    memcpy(conf+strlen(base),metal,strlen(metal)+1);
                    puts("Pong init: native Metal entry enabled for backboardd");
                }
                break;
            }
            while(*p && *p!=' ')p++;
        }
    }
    int result=sysctlbyname("kern.exec_inject",NULL,NULL,conf,strlen(conf)+1);
    printf("Pong init: UI library configuration result=%d errno=%d\n",result,result?errno:0);
}

/*
 * drainer-block.inc - inserted into userland/init.c before main().
 * Persist the kernel console ring (kern.pong_ramoops sysctl, boot-arg
 * k60_console_export=1) to the Data volume.  Hard caps: 4 files x 16 MiB
 * (rename rotation, newest always console.log), writes stop for good
 * below 500 MiB free on the volume.  See docs/references/CONSOLE-FULL-CAPTURE.md.
 */

struct k60c_hdr {
    uint32_t magic, sig, capacity, size, start, flags;
    uint64_t total, dropped, from, avail;
};

#define K60C_MAGIC          0x4B363043U     /* "K60C" */
#define K60C_FLAG_BEHIND    0x1U
#define K60C_CHUNK          65536U
#define K60LOG_DIR          "/private/var/pong"
#define K60LOG_NFILES       4
#define K60LOG_MAX          (16UL * 1024 * 1024)
#define K60LOG_FREE_FLOOR   (500ULL * 1024 * 1024)
#define K60LOG_FSYNC_BYTES  65536U

static char          k60log_buf[sizeof(struct k60c_hdr) + K60C_CHUNK];
static int           k60log_fd = -1;
static unsigned long k60log_size;
static unsigned long k60log_unsynced;
static long          k60log_last_fsync;
static unsigned long k60log_since_spacecheck;
static int           k60log_stopped;

static long
k60log_now(void)
{
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return tv.tv_sec;
}

static int
k60log_free_ok(void)
{
    struct statfs64 sfs;
    if (fstatfs64(k60log_fd, &sfs) != 0)
        return 0;
    return sfs.f_bavail * (unsigned long long)sfs.f_bsize >= K60LOG_FREE_FLOOR;
}

static void
k60log_stop(const char *why)
{
    if (k60log_fd >= 0) {
        int n = dprintf(k60log_fd, "\n===== K60LOG STOP: %s =====\n", why);
        if (n > 0)
            k60log_size += (unsigned long)n;
        fsync(k60log_fd);
    }
    k60log_stopped = 1;
}

static int
k60log_open(void)
{
    struct stat st;
    k60log_fd = open(K60LOG_DIR "/console.log", O_WRONLY | O_CREAT | O_APPEND, 0644);
    if (k60log_fd < 0)
        return -1;
    k60log_size = (fstat(k60log_fd, &st) == 0) ? (unsigned long)st.st_size : 0;
    k60log_unsynced = 0;
    k60log_since_spacecheck = 0;
    k60log_last_fsync = k60log_now();
    return 0;
}

static int
k60log_rotate(void)
{
    static const char *names[K60LOG_NFILES] = {
        K60LOG_DIR "/console.log", K60LOG_DIR "/console.1.log",
        K60LOG_DIR "/console.2.log", K60LOG_DIR "/console.3.log"
    };
    fsync(k60log_fd);
    close(k60log_fd);
    k60log_fd = -1;
    unlink(names[K60LOG_NFILES - 1]);
    for (int i = K60LOG_NFILES - 2; i >= 0; i--)
        (void)rename(names[i], names[i + 1]);
    return k60log_open();
}

static int
k60log_write(const char *p, size_t n)
{
    while (n > 0 && !k60log_stopped) {
        if (k60log_size >= K60LOG_MAX && k60log_rotate() != 0) {
            k60log_stop("rotation failed");
            break;
        }
        unsigned long room = K60LOG_MAX - k60log_size;
        size_t chunk = n < room ? n : room;
        size_t done = 0;
        while (done < chunk) {
            ssize_t w = write(k60log_fd, p + done, chunk - done);
            if (w <= 0) {
                k60log_stop("write failed");
                return -1;
            }
            done += (size_t)w;
        }
        k60log_size += chunk;
        k60log_unsynced += chunk;
        k60log_since_spacecheck += chunk;
        n -= chunk;
        p += chunk;
        if (k60log_since_spacecheck >= 4UL * 1024 * 1024) {
            k60log_since_spacecheck = 0;
            if (!k60log_free_ok()) {
                k60log_stop("free space floor (500 MiB)");
                return -1;
            }
        }
        if (k60log_unsynced >= K60LOG_FSYNC_BYTES ||
            k60log_now() - k60log_last_fsync >= 1) {
            fsync(k60log_fd);
            k60log_unsynced = 0;
            k60log_last_fsync = k60log_now();
        }
    }
    return k60log_stopped ? -1 : 0;
}

static int
k60log_pull(uint64_t *cursor, struct k60c_hdr *hdr)
{
    size_t outlen = sizeof(k60log_buf);
    if (sysctlbyname("kern.pong_ramoops", k60log_buf, &outlen,
                     cursor, sizeof(*cursor)) != 0)
        return errno == 2 ? 1 : -1;
    if (outlen < sizeof(*hdr))
        return -1;
    memcpy(hdr, k60log_buf, sizeof(*hdr));
    if (hdr->magic != K60C_MAGIC)
        return -1;
    return 0;
}

static void __attribute__((noreturn))
k60log_drain_main(void)
{
    mkdir(K60LOG_DIR, 0755);
    if (k60log_open() != 0) {
        printf("Pong drainer: cannot open log file, errno=%d\n", errno);
        _exit(0);
    }
    uint64_t cursor = 0;
    struct k60c_hdr hdr;
    int rc = k60log_pull(&cursor, &hdr);
    if (rc == 1)
        _exit(0);
    if (rc != 0) {
        printf("Pong drainer: ring export unreadable, errno=%d\n", errno);
        _exit(0);
    }
    if (hdr.flags & K60C_FLAG_BEHIND) {
        int n = dprintf(k60log_fd, "\n===== K60LOG GAP at boot: %llu early bytes overwritten =====\n",
            hdr.total - hdr.size);
        if (n > 0)
            k60log_size += (unsigned long)n;
    }
    {
        int n = dprintf(k60log_fd, "\n===== K60LOG boot epoch=%ld ring_total=%llu dropped=%llu =====\n",
            k60log_now(), hdr.total, hdr.dropped);
        if (n > 0)
            k60log_size += (unsigned long)n;
    }
    for (;;) {
        rc = k60log_pull(&cursor, &hdr);
        if (rc != 0) {
            usleep(250000);
            continue;
        }
        if (hdr.avail > 0) {
            if (hdr.flags & K60C_FLAG_BEHIND) {
                int n = dprintf(k60log_fd, "\n===== K60LOG GAP: %llu bytes lost (total=%llu) =====\n",
                    hdr.total - hdr.size - cursor, hdr.total);
                if (n > 0)
                    k60log_size += (unsigned long)n;
            }
            if (k60log_write(k60log_buf + sizeof(hdr), hdr.avail) != 0) {
                for (;;)
                    usleep(1000000);
            }
            cursor = hdr.from + hdr.avail;
        }
        if (hdr.avail < K60C_CHUNK)
            usleep(100000);
    }
}

int
main(int argc, char **argv, char **envp)
{
    (void)argc; (void)argv; (void)envp;
    int fd = open("/dev/console", O_RDWR, 0);
    if (fd >= 0) {
        dup2(fd, 0); dup2(fd, 1); dup2(fd, 2);
        if (fd > 2) close(fd);
    }
    printf("Pong init: alive, console ready\n");
    boot_stage("helper entered");
    /* Upstream init does this before handing the console to non-root jobs. */
    (void)chmod("/dev/console", 0666);
    (void)chdir("/");
    puts("Pong init: HackiOS adapter [v10guard]");
    /* maxvnodes tuning is optional; the owner mount hook already publishes
     * skipIgnition in the commpage and exec apple strings before this helper. */
    boot_stage("preparing writable Data seed");
    prepare_var();
    prepare_launchd_disabled();
    boot_stage("Data preparation returned");
    prepare_calendar();
    prepare_runtime_paths();
    prepare_boot_services();
    configure_ui_library();
    char *next[] = {"/sbin/launchd", NULL};
    char *env[] = {
        "PATH=/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME=/var/root", "TMPDIR=/var/tmp/",
        "DYLD_SHARED_CACHE_DIR=/System/Library/Caches/com.apple.dyld/",
        "DYLD_FALLBACK_LIBRARY_PATH=/usr/lib",
        NULL
    };
    puts("Pong init: exec original 20G81 launchd; stdin/stdout -> /dev/null, stderr -> /dev/console");
    /* K60/mondrian deviation: the pong route renames the stock binary to
     * /sbin/launchd.ios on its writable root. Our root is a sealed read-only
     * union and /sbin/launchd is still the stock binary, so exec it directly. */
    boot_stage("exec original /sbin/launchd");
    /* 20G81 launchd rejects an interactive stdout before its PID 1 setup.
     * Keep diagnostics on fd 2; fd 1 must not inherit this helper's console. */
    int nullfd = open("/dev/null", O_RDWR, 0);
    if (nullfd < 0 || dup2(nullfd, 0) < 0 || dup2(nullfd, 1) < 0) {
        if (nullfd > 2) close(nullfd);
        (void)dup2(2, 1);
        printf("Pong init: non-interactive launchd descriptors failed: errno=%d\n", errno);
        return 127;
    }
    if (nullfd > 2) close(nullfd);
    execve("/sbin/launchd", next, env);
    int exec_error = errno;
    (void)dup2(2, 1);
    errno = exec_error;
    boot_stage("original launchd exec returned an error");
    printf("Pong init: launchd exec failed: errno=%d (%s)\n", errno, strerror(errno));
    /* A genuine PID 1 exec failure must remain visible to normal kernel handling. */
    return 127;
}
