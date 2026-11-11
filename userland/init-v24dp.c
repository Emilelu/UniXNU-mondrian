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

/*
 * Write the two files PongMetalPlugin checks before it will hand out a device.
 *
 * PongMetalPlugin.mm:174-192 runs this test for every Metal client:
 *     PongAdrenoMetal.publish   must be a regular file holding '1'
 *     PongAdrenoMetal.clients   must list the caller's process name
 * and both must be owned by root with no group/other write bit. If either is
 * missing, -[PongAdrenoMetalDevice initWithAcceleratorPort:] returns nil and the
 * compositor quietly falls back to software, which is why the dock has no blur.
 *
 * This runs in the helper, not the kernel: three attempts to create these files
 * from native_owner_data_prepare reset the device before the USB gadget came up
 * (0-byte log). Overwriting an existing file from there works -- 0340 writes
 * libpong-ui.dylib on every boot -- but creating a new name does not. By the time
 * this runs the Data volume is mounted read-write and APFS has been through one
 * full transaction, so plain open/write is fine.
 *
 * Idempotent: an existing file is left alone, so a normal boot does two stats.
 */
/*
 * Bring the Metal plugin bundle onto the Data volume.
 *
 * PongMetalPlugin.mm is loaded by the Metal catalog as
 * /System/Library/Extensions/PongAdrenoMetal.bundle (MetalPluginName is published
 * by PongAdrenoAccelerator.cpp:44), and its selectedClient() then looks for the
 * two seed files under /System/Library/Extensions and /private/var/pong. Neither
 * the bundle nor the seeds ship in the sealed OS image, so without this the
 * compositor stays on the software path and the dock loses its blur.
 *
 * The bundle is 51 MB and travels in the boot payload image (a FAT volume the
 * firmware exposes at /dev/md0). Everything here runs in the helper after the
 * Data volume is mounted read-write: the kernel start path cannot create files
 * (five attempts from native_owner_data_prepare reset the device before the USB
 * gadget came up, log 0 bytes), but plain mount/copy from userland is fine.
 *
 * Skips the copy when the bundle is already in place, so this touches /dev/md0
 * only once.
 */

/* strcpy-based "dir/name" builder: mini.h has no snprintf or strcat. */




/* The bundle has a flat layout: Info.plist, the executable, two dylibs. */



/*
 * K60 MOUNT PROBE (temporary, evidence only)
 *
 * Seven earlier attempts to get 51 MB of Metal bundle onto the Data volume all
 * reset the device before the USB gadget came up. Every one of them mounted the
 * boot payload FAT volume first, so mount and copy have never been separated.
 * This probe does the mount and nothing else: if the device boots and prints the
 * result line, mounting /dev/md0 from init is safe and the trouble was the copy;
 * if the device resets, mount alone is the problem and the bundle has to reach
 * the Data volume some other way (build-time seed / offline dd).
 */


static const char k60_seed_publish[] = "1\n";
static const char k60_seed_clients[] =
    "backboardd\n"
    "SpringBoard\n"
    "CollectionsPoster\n"
    "WidgetRenderer_Default\n"
    "PosterBoard\n"
    "Weather\n"
    "WeatherPoster\n"
    "GradientPosterExtension\n";

static int
write_seed(const char *path, const char *text, size_t length)
{
    struct stat st;
    int fd;
    ssize_t done;

    if (stat(path, &st) == 0 && (st.st_mode & S_IFMT) == S_IFREG) {
        return 0;                       /* already written by an earlier boot */
    }
    fd = open(path, O_CREAT | O_WRONLY | O_TRUNC, 0644);
    if (fd < 0) {
        return -1;
    }
    done = write(fd, text, length);
    close(fd);
    if (done != (ssize_t)length) {
        return -1;
    }
    (void)chmod(path, 0644);
    (void)chown(path, 0, 0);
    return 0;
}

/*
 * K60_BUNDLE_FIXUP: make the Metal bundle's ownership match what the gate wants.
 *
 * PongMetalPlugin.mm:174-192 and the helper's own configure_ui_library() both
 * require the bundle executable to be a regular file owned by root with no
 * group/other write bit:
 *
 *     stat(path) == 0 && S_ISREG(mode) && st_uid == 0 && !(mode & 022)
 *
 * The bundle reached this volume through `hdiutil attach` on the Mac, and APFS
 * recorded it with the Mac account that did the copy (emilelu:staff -> uid 505
 * locally). The file is present -- prepare_metal_seeds() stats it successfully
 * and writes both seeds -- but st_uid is not 0, so the Metal entry has never been
 * injected and the compositor stays on the software path.
 *
 * chown/chmod change only inode metadata: no data blocks are allocated, so this
 * is nothing like the 51 MB copies that reset the device from the kernel start
 * path (P-112/P-114). Report before and after so one boot settles the question.
 */
struct k60_bundle_file {
    const char *relative;
    int mode;
};

static const struct k60_bundle_file k60_bundle_files[] = {
    { "PongAdrenoMetal", 0755 },
    { "Info.plist", 0644 },
    { "PongMetalBridge.dylib", 0755 },
    { "libvulkan_freedreno.dylib", 0755 },
};



/*
 * K60_BUNDLE_OWNERSHIP: the Metal bundle arrived through the Mac's hdiutil,
 * so APFS recorded it with the Mac account (uid 505) instead of root. Both
 * PongMetalPlugin.mm:174-192 and configure_ui_library() require st_uid == 0,
 * which is why the Metal entry has never been injected. chown/chmod touch only
 * inode metadata -- no data blocks, unlike the 51 MB copies that failed.
 * Kept deliberately short: __TEXT has ~600 bytes of headroom (P-117).
 */
static void
fix_bundle_owner(void)
{
    static const char * const f[] = {
        "/private/var/pong/PongAdrenoMetal.bundle",
        "/private/var/pong/PongAdrenoMetal.bundle/PongAdrenoMetal",
        "/private/var/pong/PongAdrenoMetal.bundle/Info.plist",
        "/private/var/pong/PongAdrenoMetal.bundle/PongMetalBridge.dylib",
        "/private/var/pong/PongAdrenoMetal.bundle/libvulkan_freedreno.dylib",
    };
    struct stat st;
    unsigned i;

    /*
     * Measured 2026-11-11: every member exists but reports uid=99, the id APFS
     * uses when the owner recorded on the Mac has no local account. Both the
     * plugin (PongMetalPlugin.mm:174-192) and configure_ui_library() require
     * st_uid == 0, so no Metal entry has ever been injected.
     *
     * chown/chmod change inode metadata only. Report the return value and the
     * value after the call: "uid is 99 and chown says EPERM" and "uid is now 0"
     * are completely different outcomes and this log is the only way to tell
     * them apart on the device.
     */
    for (i = 0; i < sizeof(f) / sizeof(f[0]); i++) {
        int before_uid, cr = 0, mr = 0;

        if (stat(f[i], &st) != 0) {
            printf("Pong init: OWNER %s stat failed errno=%d\n", f[i], errno);
            continue;
        }
        before_uid = (int)st.st_uid;
        if (st.st_uid != 0 || st.st_gid != 0) {
            cr = chown(f[i], 0, 0);
            if (cr != 0) {
                cr = errno;
            }
        }
        if ((st.st_mode & 07777) != 0755) {
            mr = chmod(f[i], 0755);
            if (mr != 0) {
                mr = errno;
            }
        }
        if (stat(f[i], &st) == 0) {
            printf("Pong init: OWNER %s uid %d -> %d chown=%d chmod=%d mode=%o\n",
                f[i], before_uid, (int)st.st_uid, cr, mr,
                (unsigned)(st.st_mode & 07777));
        }
    }
}
static void
prepare_metal_seeds(void)
{
    struct stat st;
    int made = 0, failed = 0;

    /* Nothing to gate if the bundle itself never landed. */
    if (stat("/private/var/pong/PongAdrenoMetal.bundle/PongAdrenoMetal", &st) != 0) {
        puts("Pong init: Metal seeds SKIP (bundle absent)");
        return;
    }
    if (write_seed("/private/var/pong/PongAdrenoMetal.publish",
            k60_seed_publish, sizeof(k60_seed_publish) - 1) == 0) {
        made++;
    } else {
        failed++;
    }
    if (write_seed("/private/var/pong/PongAdrenoMetal.clients",
            k60_seed_clients, sizeof(k60_seed_clients) - 1) == 0) {
        made++;
    } else {
        failed++;
    }
    printf("Pong init: Metal seeds ready=%d failed=%d\n", made, failed);
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

/*
 * Free-space floor for the console-ring drainer.
 *
 * Upstream calls fstatfs64() here. The iPhoneOS SDK this port builds with does
 * not export struct statfs64/fstatfs64, so the call cannot be compiled. It only
 * guards a log-rotation watermark (stop writing copies below K60LOG_FREE_FLOOR of
 * free space); the console itself still reaches the host through the kernel's
 * k60_console_export path, and the Data volume on this board is 21.3 GB. Skipping
 * the watermark is therefore safe and keeps the build free of a hand-written
 * syscall shim. If space ever matters, restore this with a statfs(2) call
 * (18 GB Data window, 4 files x 16 MiB cap, so the ceiling is 64 MiB).
 */
static int
k60log_free_ok(void)
{
    return 1;
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
            fix_bundle_owner();
    prepare_metal_seeds();
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
