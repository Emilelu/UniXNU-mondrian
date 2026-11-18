/* k60probe: prove that application traffic crosses the Pong WiFi link.
 *
 * A launchd job (com.pong.netprobe) runs this after the interface appears. It
 * polls the gateway with a plain HTTP GET, then repeats the request to show a
 * sustained transfer. Everything is raw BSD sockets through libmini; there is
 * no dyld, no Foundation and no libSystem in this binary.
 */
#include "mini.h"

#define INADDR(a,b,c,d) ((uint32_t)(a) | ((uint32_t)(b) << 8) | ((uint32_t)(c) << 16) | ((uint32_t)(d) << 24))

struct sockaddr_in {
    uint8_t  sin_len;
    uint8_t  sin_family;
    uint16_t sin_port;
    uint32_t sin_addr;
    char     sin_zero[8];
};

static int
connect_ip(uint32_t addr, uint16_t port)
{
    struct sockaddr_in sin;
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) return -1;
    memset(&sin, 0, sizeof sin);
    sin.sin_len = sizeof sin;
    sin.sin_family = AF_INET;
    sin.sin_port = (uint16_t)((port >> 8) | (port << 8));
    sin.sin_addr = addr;
    if (connect(fd, &sin, sizeof sin) != 0) {
        close(fd);
        return -1;
    }
    return fd;
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
    write(fd, req, sizeof req - 1);
    write(fd, host, strlen(host));
    write(fd, "\r\nUser-Agent: k60probe\r\n\r\n", 27);
    while ((n = (int)read(fd, buf, sizeof buf)) > 0) {
        total += n;
        if (first) {
            first = 0;
            for (i = 0; i < sizeof head - 1 && i < (unsigned)n && buf[i] != '\r'; i++) head[i] = buf[i];
            head[i] = 0;
            if (strncmp(head, "HTTP/", 5) == 0) {
                const char *p = head + 5;
                while (*p && (*p < '0' || *p > '9')) p++;
                status = 0;
                while (*p >= '0' && *p <= '9') status = status * 10 + (*p++ - '0');
            }
            dprintf(out, "k60probe: %s status %d line %s\n", host, status, head);
        }
        if (total > (int)sizeof buf) break;
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
