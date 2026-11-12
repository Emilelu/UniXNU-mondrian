/*
 * Pong / UniXNU adaptation of HackiOS stage0 and init (MIT; see ../LICENSE).
 * Static Darwin 22 executable; optional 20G81 UI library is configured separately.
 */
#include "mini.h"

/* Apple clang may lower zero-initialized aggregates to bzero even freestanding. */
void bzero(void *p, size_t n) { memset(p, 0, n); }

/* Reuse the ordinary console path; boot progress must not depend on a
 * custom sysctl or its name lookup/locking before launchd can start. */
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

static int unpack_boot_jobs(const char *archive, const char *dest);

static void
prepare_var(void)
{
    static char buf[65536];
    char args[4096] = {0}, device[96] = {0};
    size_t len = sizeof(args);
    struct stat root, var;
    int root_ok = stat("/", &root) == 0;
    int separate = root_ok && stat("/private/var", &var) == 0 &&
                   root.st_dev != var.st_dev;
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
    int fd = open("/private/var/.pong-write-check", O_CREAT | O_EXCL | O_WRONLY, 0600);
    if (fd < 0) { printf("Pong init: Data not writable: errno=%d\n", errno); return; }
    close(fd); unlink("/private/var/.pong-write-check");
    /*
     * 0406: apply() normally ships /pong/etc/var.skel and /pong/var-seed on the
     * OS window, and that step never ran here: the root is a sealed union with
     * no /pong at all. The kernel writes the same tree as a PONGJOB1 archive
     * next to the helper, so expand it before reading the skeleton.
     */
    {
        struct stat sk;
        if (stat("/pong/etc/var.skel", &sk) != 0) {
            /* unpack_boot_jobs only creates entries under dest, never dest
             * itself; boot-jobs works because K60DATA pre-creates that one. */
            mkdir("/private/var/pong/root", 0755);
            int n = unpack_boot_jobs("/private/var/pong/var.pack",
                "/private/var/pong/root");
            printf("Pong init: var.pack expand result=%d\n", n);
        }
    }
    if (read_text("/pong/etc/var.skel", buf, sizeof(buf)) < 0 &&
        read_text("/private/var/pong/root/pong/etc/var.skel", buf, sizeof(buf)) < 0) {
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
            char source[512];
            struct stat probe;
            /* 0406: apply() would have staged these under /pong on the OS
             * window, which this sealed root cannot carry. The archive expands
             * to the writable volume instead, so try that prefix first. */
            strcpy(source, field[5]);
            if (stat(source, &probe) != 0 && strncmp(field[5], "/pong/", 6) == 0) {
                char rebased[512];
                strcpy(rebased, "/private/var/pong/root");
                strcpy(rebased + strlen("/private/var/pong/root"), field[5]);
                strcpy(source, rebased);
            }
            result = copy_new(source, field[4], (int)number(field[1], 8),
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

/* Expand the archive the kernel writes next to the helper. The format is in
 * scripts/pack-boot-jobs.py: a header, then one fixed record per entry
 * followed by the name, the link target and the data. The kernel cannot create
 * 406 files safely before PID 1 exists, so it does one write of the archive and
 * this runs the loop in user space, where open/write/mkdir already work. */
#define PONGJOB_HEADER 12
#define PONGJOB_RECORD 24

/* read() is a raw syscall here and may return a short count; the archive is
 * parsed positionally, so every field must be filled before it is decoded. */
static int
read_full(int fd, void *buf, size_t want)
{
    unsigned char *p = buf;
    size_t done = 0;
    while (done < want) {
        ssize_t n = read(fd, p + done, want - done);
        if (n <= 0) return -1;
        done += (size_t)n;
    }
    return 0;
}

static int
unpack_boot_jobs(const char *archive, const char *dest)
{
    struct stat st;
    if (stat(archive, &st) != 0 || (st.st_mode & S_IFMT) != S_IFREG) return -1;
    int in = open(archive, O_RDONLY, 0);
    if (in < 0) return -1;
    unsigned char head[PONGJOB_HEADER];
    if (read_full(in, head, sizeof(head)) != 0 ||
        memcmp(head, "PONGJOB1", 8) != 0) { close(in); return -1; }
    unsigned count = (unsigned)head[8] | ((unsigned)head[9] << 8) |
                     ((unsigned)head[10] << 16) | ((unsigned)head[11] << 24);
    char path[512];
    int made = 0, failed = 0;
    for (unsigned i = 0; i < count; i++) {
        unsigned char rec[PONGJOB_RECORD];
        if (read_full(in, rec, sizeof(rec)) != 0) { failed++; break; }
        /* '<IIIIII': mode@0 uid@4 gid@8 size@12 nlen@16 dlen@20. Reading
         * size from 8 skipped a field, so nlen decoded as the file size and
         * every path was built from a name that ran into the payload. */
        unsigned mode = (unsigned)rec[0] | ((unsigned)rec[1] << 8) |
                        ((unsigned)rec[2] << 16) | ((unsigned)rec[3] << 24);
        unsigned size = (unsigned)rec[12] | ((unsigned)rec[13] << 8) |
                        ((unsigned)rec[14] << 16) | ((unsigned)rec[15] << 24);
        unsigned nlen = (unsigned)rec[16] | ((unsigned)rec[17] << 8) |
                        ((unsigned)rec[18] << 16) | ((unsigned)rec[19] << 24);
        unsigned dlen = (unsigned)rec[20] | ((unsigned)rec[21] << 8) |
                        ((unsigned)rec[22] << 16) | ((unsigned)rec[23] << 24);
        char name[512];
        if (nlen == 0 || nlen >= sizeof(name)) {
            failed++; break;
        }
        if (read_full(in, name, nlen) != 0) { failed++; break; }
        name[nlen] = 0;
        size_t dl = strlen(dest);
        if (dl + 1 + nlen + 1 > sizeof(path)) { failed++; break; }
        strcpy(path, dest);
        path[dl] = '/';
        strcpy(path + dl + 1, name);
        if ((mode & S_IFMT) == S_IFDIR) {
            if (mkdir(path, mode & 07777) == 0 || errno == 17) made++;
            else failed++;
        } else if ((mode & S_IFMT) == S_IFLNK) {
            char target[512];
            if (dlen == 0 || dlen >= sizeof(target)) {
                failed++;
                (void)lseek(in, (off_t)(dlen + size), SEEK_CUR);
                continue;
            }
            if (read_full(in, target, dlen) != 0) { failed++; break; }
            target[dlen] = 0;
            if (symlink(target, path) == 0 || errno == 17) made++;
            else failed++;
            if (size) (void)lseek(in, (off_t)size, SEEK_CUR);
        } else if ((mode & S_IFMT) == S_IFREG) {
            int out = open(path, O_WRONLY | O_CREAT | O_TRUNC, mode & 07777);
            if (out < 0) {
                if (failed < 3) {
                    printf("Pong init: unpack open failed errno=%d name=%s\n",
                           errno, name);
                }
                failed++;
                /* Skip this entry's data, or the next record is read from the
                 * middle of a file and every following entry is garbage. */
                (void)lseek(in, (off_t)size, SEEK_CUR);
                continue;
            }
            unsigned left = size;
            char buf[4096];
            while (left) {
                size_t want = left < sizeof(buf) ? left : sizeof(buf);
                ssize_t got = read(in, buf, want);
                if (got <= 0) { failed++; break; }
                if (write(out, buf, (size_t)got) != got) { failed++; break; }
                left -= (unsigned)got;
            }
            close(out);
            if (left) (void)lseek(in, (off_t)left, SEEK_CUR);
            else made++;
        } else {
            failed++;
        }
    }
    close(in);
    printf("Pong init: boot-jobs unpack entries=%u made=%d failed=%d\n",
           count, made, failed);
    return failed ? -1 : 0;
}

/* bindfs needs a real directory on writable Data. Never follow an existing
 * symlink here: these root-owned views are later read by mobile processes. */
static int
wallpaper_directory(const char *path)
{
    struct stat st;
    if (lstat(path, &st) != 0) {
        if (errno != 2 || mkdir(path, 0755) != 0)
            return -1;
    } else if ((st.st_mode & S_IFMT) != S_IFDIR || st.st_uid != 0 || (st.st_mode & 022)) {
        return -1;
    }
    return chown(path, 0, 0) != 0 || chmod(path, 0755) != 0 ? -1 : 0;
}

/* Expose exactly the names in the preserved Apple directory. The view holds
 * symlinks only, not images or renamed iPad metadata pretending to be iPhone
 * content. A compatible phone catalogue must actually be supplied by 20G81. */
static int
wallpaper_aliases(void)
{
    static unsigned char entries[4096];
    const char *stock = "/private/var/pong/stock-wallpaper";
    const char *view = "/private/var/pong/Wallpaper";
    int fd = open(stock, O_RDONLY | O_DIRECTORY, 0), failed = 0, made = 0;
    off_t position = 0;
    ssize_t n;
    if (fd < 0) return -1;
    while ((n = getdirentries(fd, entries, sizeof(entries), &position)) > 0) {
        size_t offset = 0;
        while (offset < (size_t)n) {
            struct dirent record;
            const struct dirent *entry = &record;
            size_t header = offsetof(struct dirent, d_name);
            if ((size_t)n - offset < header) { failed = 1; break; }
            memcpy(&record, entries + offset, header);
            if ((size_t)n - offset < header || entry->d_reclen < header + 1 ||
                entry->d_reclen > (size_t)n - offset || !entry->d_namlen ||
                entry->d_namlen >= sizeof(entry->d_name) ||
                header + entry->d_namlen + 1 > entry->d_reclen ||
                entries[offset + header + entry->d_namlen] != 0) {
                failed = 1; break;
            }
            memcpy(record.d_name, entries + offset + header, entry->d_namlen + 1);
            offset += entry->d_reclen;
            if (!strcmp(entry->d_name, ".") || !strcmp(entry->d_name, "..")) continue;
            size_t length = entry->d_namlen;
            int valid = 1;
            for (size_t i = 0; i < length; i++)
                if (!entry->d_name[i] || entry->d_name[i] == '/') valid = 0;
            char source[512], target[512], existing[512];
            size_t sl = strlen(stock), tl = strlen(view);
            if (!valid || sl + length + 2 > sizeof(source) || tl + length + 2 > sizeof(target)) {
                failed = 1; break;
            }
            memcpy(source, stock, sl); source[sl++] = '/';
            memcpy(source + sl, entry->d_name, length + 1);
            memcpy(target, view, tl); target[tl++] = '/';
            memcpy(target + tl, entry->d_name, length + 1);
            struct stat st;
            if (lstat(target, &st) == 0) {
                ssize_t count = (st.st_mode & S_IFMT) == S_IFLNK ?
                    readlink(target, existing, sizeof(existing)) : -1;
                if (count < 0 || count != (ssize_t)strlen(source) || memcmp(existing, source, (size_t)count)) {
                    printf("Pong init: wallpaper alias conflict %s\n", target);
                    failed = 1; break;
                }
            } else if (errno != 2 || symlink(source, target) != 0) {
                failed = 1; break;
            }
            made++;
        }
        if (failed) break;
    }
    if (n < 0) failed = 1;
    close(fd);
    printf("Pong init: genuine stock wallpaper aliases=%d result=%d\n", made, failed ? -1 : 0);
    return failed || made == 0 ? -1 : 0;
}

/* Same composition as HackiOS init: hide physical audio plug-ins before
 * mediaserverd scans them. Keep mediaserverd for VideoToolbox/HEIC decoding.
 * The optional job set is a real 20G81 directory supplied in writable Data. */
static void
prepare_boot_services(void)
{
    /* Expand the curated job set first: the bind below needs a populated
     * source directory, and the archive is written by the kernel next to the
     * helper before PID 1 exists. */
    (void)unpack_boot_jobs("/private/var/pong/boot-jobs.pack",
        "/private/var/pong/boot-jobs");
    int wallpaper_ready = 0;
    int wallpaper_dirs = wallpaper_directory("/private/var/pong/stock-wallpaper") == 0 &&
                         wallpaper_directory("/private/var/pong/Wallpaper") == 0;
    if (!wallpaper_dirs)
        printf("Pong init: wallpaper view directories unavailable errno=%d\n", errno);
    static const struct { const char *source, *target; } views[] = {
        /* 0401: bind over the directory launchd actually reads. The stock
         * apply() pipeline leaves a /pong/LaunchDaemons symlink behind, but the
         * sealed root here has no /pong at all, so a bind to that path was
         * always skipped ("source/target unavailable") and launchd ran the
         * full stock set. The target must exist for bindfs to attach, and
         * /System/Library/LaunchDaemons does. */
        {"/private/var/pong/boot-jobs", "/System/Library/LaunchDaemons"},
        {"/private/var/pong/empty-hal", "/System/Library/Audio/Plug-Ins/HAL"},
        {"/private/var/pong/empty-hal", "/Library/Audio/Plug-Ins/HAL"},
        /* 0402: launchd reads its service cache from here, not from the
         * LaunchDaemons directory. The kernel writes the curated cache (22
         * CORE jobs, no App-cryptex programs) to the Data volume, so it has
         * to be bound over the stock one or launchd keeps using stock. */
        {"/private/var/pong/xpc", "/System/Library/xpc"},
        /* Keep a read-only path to stock assets before overlaying their
         * directory. The RAM view contains aliases, not copied pictures. */
        {"/Library/Wallpaper", "/private/var/pong/stock-wallpaper"},
        {"/private/var/pong/Wallpaper", "/Library/Wallpaper"}
    };
    for (unsigned i = 0; i < sizeof(views)/sizeof(views[0]); i++) {
        struct stat source, target;
        if (strcmp(views[i].source,"/Library/Wallpaper")==0 &&
            (!wallpaper_dirs || stat("/Library/Wallpaper/Collections/Collections~ipad.plist",&source)!=0 ||
             (source.st_mode&S_IFMT)!=S_IFREG)) {
            puts("Pong init: stock wallpaper view SKIP (genuine 20G81 catalogue unavailable)");
            continue;
        }
        if (strcmp(views[i].target,"/Library/Wallpaper")==0 && !wallpaper_ready) {
            puts("Pong init: wallpaper aliases SKIP (stock view or aliases unavailable)");
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
        if (strcmp(views[i].source,"/Library/Wallpaper")==0 && result==0)
            wallpaper_ready = wallpaper_aliases() == 0;
    }
}

static void
configure_ui_library(void)
{
    const char *path="/private/var/pong/libpong-ui.dylib";
    /* 0404: SpringBoard is injected by default. k60_ui_springboard=0 removes
     * only that target, which is how the constructor was ruled out as the cause
     * of the stuck main queue; leaving that experiment as the default made
     * boot-v36..v39 present no frame at all. */
    const char *base="/private/var/pong/libpong-ui.dylib SpringBoard backboardd containermanagerd containermanagerd_system mediaserverd Preferences";
    const char *metal="; /private/var/pong/PongAdrenoMetal.bundle/PongAdrenoMetal backboardd";
    char conf[512],args[4096]={0};size_t length=sizeof(args);
    {
        int k60_sb = 1;
        if (sysctlbyname("kern.bootargs", args, &length, NULL, 0) == 0) {
            for (char *p=args;*p;) {
                while(*p==' ')p++;
                if (strncmp(p,"k60_ui_springboard=0",20)==0 && (!p[20] || p[20]==' ')) {
                    k60_sb = 0;
                }
                while (*p && *p!=' ') p++;
            }
        }
        if (!k60_sb) {
            base = "/private/var/pong/libpong-ui.dylib backboardd containermanagerd containermanagerd_system mediaserverd Preferences";
        }
        args[0]=0; length=sizeof(args);
    }
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

int
main(int argc, char **argv, char **envp)
{
    (void)argc; (void)argv; (void)envp;
    int fd = open("/dev/console", O_RDWR, 0);
    if (fd >= 0) {
        dup2(fd, 0); dup2(fd, 1); dup2(fd, 2);
        if (fd > 2) close(fd);
    }
    boot_stage("static 20G81 helper entered; console open returned");
    /* Upstream init does this before handing the console to non-root jobs. */
    (void)chmod("/dev/console", 0666);
    (void)chdir("/");
    puts("Pong init: HackiOS userland adapter / iOS 16.6.1 20G81 / static arm64");
    /* maxvnodes tuning is optional; the owner mount hook already publishes
     * skipIgnition in the commpage and exec apple strings before this helper. */
    boot_stage("preparing writable Data seed");
    prepare_var();
    boot_stage("Data preparation returned");
    prepare_calendar();
    prepare_runtime_paths();
    prepare_boot_services();
    configure_ui_library();
    char *next[] = {"/sbin/launchd", NULL};
    char *env[] = {
        "PATH=/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME=/var/root", "TMPDIR=/var/tmp/",
        /* PITFALLS P-22: the reference board keeps its cache under
         * /private/preboot, this port's union mount exposes it at
         * /System/Library/Caches/com.apple.dyld (boot probe: rc=0 there,
         * rc=2 under /private/preboot). Pointing at preboot made dyld report
         * "Library not loaded: /usr/lib/libSystem.B.dylib (no dyld cache)" and
         * launchd died as PID 1 before any job could run. */
        "DYLD_SHARED_CACHE_DIR=/System/Library/Caches/com.apple.dyld/",
        "DYLD_FALLBACK_LIBRARY_PATH=/System/Library/Frameworks:/usr/lib",
        NULL
    };
    puts("Pong init: exec original 20G81 launchd; stdin/stdout -> /dev/null, stderr -> /dev/console");
    boot_stage("exec original /sbin/launchd.ios");
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
    /* DECISIONS.md:344 — our root is a sealed read-only union and carries no
     * /sbin/launchd.ios (that rename belongs to the offline apply() pipeline),
     * so PID 1 must exec the stock path or die with ENOENT. */
    execve("/sbin/launchd", next, env);
    int exec_error = errno;
    (void)dup2(2, 1);
    errno = exec_error;
    boot_stage("original launchd exec returned an error");
    printf("Pong init: launchd exec failed: errno=%d (%s)\n", errno, strerror(errno));
    /* A genuine PID 1 exec failure must remain visible to normal kernel handling. */
    return 127;
}
