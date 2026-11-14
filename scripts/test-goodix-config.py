#!/usr/bin/env python3
"""Exercise the Goodix command/config completion boundary with a host SPI model."""
from pathlib import Path
import subprocess
import tempfile
import unittest

PATCH = Path(__file__).resolve().parents[1] / 'patches/xnu/zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-touch-console.patch'


class GoodixConfigTest(unittest.TestCase):
    def test_ack_is_not_config_completion(self):
        patch = PATCH.read_text()
        section = patch.split('+++ b/bsd/dev/pong_goodix.c\n', 1)[1].split('\ndiff --git', 1)[0]
        source = '\n'.join(line[1:] for line in section.splitlines() if line.startswith('+'))
        commands = source[source.index('/* Command ACK accepts'):source.index('static bool\ngoodix_apply_config')]
        harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
static uint32_t command_address = 0x10174;
static unsigned reads, writes, slept, scenario;
static uint8_t written[16];
static bool goodix_read(uint32_t address, uint8_t *data, uint32_t length) {
    assert(address == command_address && length == 16);
    reads++;
    if (scenario == 3 && reads == 2) return false;
    memset(data, 0, length);
    data[1] = scenario == 4 || (scenario == 5 && written[3] == 0x91) ? 0x04 : 0x80;
    /* ACK is immediate; firmware state is independently delayed or absent. */
    if (scenario == 1 && reads >= 4) data[0] = 0x80;
    return true;
}
static bool goodix_write(uint32_t address, const uint8_t *data, uint32_t length) {
    assert(address == command_address && length == 16);
    writes++;
    memcpy(written, data, length);
    return true;
}
static void sleep_ms(uint32_t milliseconds) { slept += milliseconds; }
'''
        checks = r'''
static void reset(unsigned next) {
    scenario = next; reads = writes = slept = 0;
}
int main(void) {
    reset(0);
    assert(!goodix_config_command(0x04, "never-completes"));
    assert(reads == 21 && writes == 1 && slept == 402);
    reset(1);
    assert(goodix_config_command(0x05, "delayed-state"));
    assert(reads == 4 && writes == 1 && slept == 42);
    assert(written[2] == 4 && written[3] == 5 && written[4] == 9 && written[5] == 0);
    reset(2);
    uint8_t coordinate = 0;
    assert(goodix_command(5, 0x90, &coordinate, 1, "coordinate"));
    assert(reads == 1 && slept == 2); /* Ordinary ACK does not require config state. */
    reset(3);
    assert(!goodix_config_command(0x06, "read-failure"));
    assert(reads == 2 && writes == 1 && slept == 2);
    reset(4);
    assert(!goodix_config_command(0x04, "checksum-rejected"));
    assert(reads == 1 && writes == 1 && slept == 0);
    reset(2);
    assert(goodix_coordinate_mode());
    assert(writes == 2 && reads == 2 && written[3] == 0x91 && written[4] == 1);
    reset(5);
    assert(!goodix_coordinate_mode()); /* Raw-mode exit alone is not coordinate enable. */
    assert(writes == 2 && reads == 2 && slept == 2);
    puts("ACK-only config rejected; delayed state completes; ordinary ACK and I/O errors distinguished");
}
'''
        with tempfile.TemporaryDirectory(prefix='goodix-config-test-') as name:
            root = Path(name)
            c = root / 'config.c'
            executable = root / 'config-test'
            c.write_text(harness + commands + checks)
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', str(c), '-o', str(executable)], check=True)
            subprocess.run([str(executable)], check=True)


if __name__ == '__main__':
    unittest.main()
