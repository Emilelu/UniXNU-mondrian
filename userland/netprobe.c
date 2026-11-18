/* k60probe: prove that application traffic crosses the Pong WiFi link.
 *
 * A launchd job (com.pong.netprobe) runs this after the interface appears. It
 * polls the gateway with a plain HTTP GET, then repeats the request to show a
 * sustained transfer. Everything is raw BSD sockets through libmini; there is
 * no dyld, no Foundation and no libSystem in this binary.
 *
 * Every wait is bounded: a connect or a read that never completes would keep
 * the probe inside one call for the whole polling window and say nothing.
 */
#include "mini.h"

#define INADDR(a,b,c,d) ((uint32_t)(a) | ((uint32_t)(b) << 8) | ((uint32_t)(c) << 16) | ((uint32_t)(d) << 24))
#define FIONBIO 0x8004667eu
#define EINPROGRESS 36
#define SOL_SOCKET 0xffff
#define SO_NOSIGPIPE 0x1022

struct sockaddr_in {
    uint8_t  sin_len;
    uint8_t  sin_family;
    uint16_t sin_port;
    uint32_t sin_addr;
    char     sin_zero[8];
};

struct fdset { int32_t bits[32]; };

/* Wait for a descriptor to become writable (connect finished) or readable. */
static int
wait_fd(int fd, int writing, int seconds)
{
    struct fdset set;
    struct timeval tv;

    memset(&set, 0, sizeof set);
    set.bits[fd / 32] = (int32_t)(1u << (fd % 32));
    tv.tv_sec = seconds;
    tv.tv_usec = 0;
    return select(fd + 1, writing ? 0 : &set, writing ? &set : 0, 0, &tv) > 0;
}

static int
connect_ip(uint32_t addr, uint16_t port)
{
    struct sockaddr_in sin;
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    int on = 1, off = 0;

    if (fd < 0) return -1;
    setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &on, sizeof on);
    ioctl(fd, FIONBIO, &on);
    memset(&sin, 0, sizeof sin);
    sin.sin_len = sizeof sin;
    sin.sin_family = AF_INET;
    sin.sin_port = (uint16_t)((port >> 8) | (port << 8));
    sin.sin_addr = addr;
    if (connect(fd, &sin, sizeof sin) != 0) {
        /* A local station has no route until the address configuration
         * completes, and that failure is immediate; only a connection that is
         * actually in progress deserves a wait. */
        if (errno != EINPROGRESS || !wait_fd(fd, 1, 10)) {
            close(fd);
            return -1;
        }
    }
    ioctl(fd, FIONBIO, &off);
    return fd;
}

static int
send_all(int fd, const char *buf, unsigned length)
{
    unsigned sent = 0;

    while (sent < length) {
        ssize_t n = write(fd, buf + sent, length - sent);
        if (n > 0) { sent += (unsigned)n; continue; }
        if (n < 0 && errno == 35 && wait_fd(fd, 1, 5)) continue;
        return -1;
    }
    return 0;
}

/* Status code: skip "HTTP/", the version number and the space, then the digits. */
static int
status_of(const char *head)
{
    const char *p = head;
    int status = 0;

    if (strncmp(p, "HTTP/", 5) != 0) return 0;
    p += 5;
    while (*p && *p != ' ') p++;
    while (*p == ' ') p++;
    while (*p >= '0' && *p <= '9') status = status * 10 + (*p++ - '0');
    return status;
}

static int
fetch(int out, uint32_t addr, const char *host, int tag)
{
    static const char req[] = "GET / HTTP/1.0\r\nHost: ";
    char buf[512];
    char head[128];
    int fd, n, total = 0, status = 0, first = 1;
    unsigned i;

    fd = connect_ip(addr, 80);
    if (fd < 0) return -1;
    dprintf(out, "k60probe: connected %s\n", host);
    if (send_all(fd, req, sizeof req - 1) != 0 ||
        send_all(fd, host, (unsigned)strlen(host)) != 0 ||
        send_all(fd, "\r\nUser-Agent: k60probe\r\n\r\n", 27) != 0) {
        close(fd);
        dprintf(out, "k60probe: %s could not be asked\n", host);
        return -1;
    }
    while (total < 4096 && wait_fd(fd, 0, 15)) {
        n = (int)read(fd, buf, sizeof buf);
        if (n <= 0) break;
        total += n;
        if (first) {
            first = 0;
            for (i = 0; i < sizeof head - 1 && i < (unsigned)n && buf[i] != '\r'; i++) head[i] = buf[i];
            head[i] = 0;
            status = status_of(head);
            dprintf(out, "k60probe: %s status %d line %s\n", host, status, head);
        }
    }
    close(fd);
    dprintf(out, "k60probe: %s tag %d bytes %d\n", host, tag, total);
    return total;
}

int
main(int argc, char **argv, char **envp)
{
    int out = open("/dev/console", O_WRONLY, 0);
    int waited = 0, round, ok = 0;

    (void)argc; (void)argv; (void)envp;
    if (out < 0) out = 2;
    dprintf(out, "k60probe: started; waiting for the gateway\n");
    while (waited < 700) {
        if (fetch(out, INADDR(192,168,31,1), "192.168.31.1", 0) >= 0) { ok = 1; break; }
        usleep(5000000);
        waited += 5;
        if (waited % 60 == 0) dprintf(out, "k60probe: still waiting after %d s\n", waited);
    }
    if (!ok) {
        dprintf(out, "k60probe: no HTTP response within %d s\n", waited);
        return 1;
    }
    fetch(out, INADDR(93,184,216,34), "example.com", 1);
    for (round = 0; round < 3; round++) {
        usleep(20000000);
        fetch(out, INADDR(192,168,31,1), "192.168.31.1", round + 2);
    }
    dprintf(out, "k60probe: done\n");
    return 0;
}
