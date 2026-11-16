#!/usr/bin/env python3
"""Guards for 0610's second deploy root.

The deploy used to write only /private/var/ngpu/addons, while the legacy init
helper injects the plugin from /private/var/pong. Both roots have to be written
or backboardd never loads the plugin and MTLCreateSystemDefaultDevice() stays
nil - which is what every boot up to 2026-11-17 showed, even though the deploy
itself reported files=6/6 error=0.

These cases assert the *contract between three places*: the path the kernel
writes, the path init-v24dp.c injects, and the names the blob generator emits.
A test on the patch text alone would pass while the three disagreed.
"""
import io
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PATCH = os.path.join(REPO, "patches", "xnu", "0610-k60-metal-plugin-deploy.patch")
INIT = os.path.join(REPO, "userland", "init-history", "init-v24dp.c")
GEN = os.path.join(REPO, "scripts", "gen-k60-metal-blob.py")

ROOT = "/private/var/ngpu"
INJECT = "/private/var/pong"


def read(path):
    with io.open(path, encoding="utf-8", newline="") as handle:
        return handle.read()


def added_lines():
    """Return the text of the added-file hunk's '+' lines, without prefixes."""
    text = read(PATCH)
    lines = text.split("\n")
    start = None
    for index, line in enumerate(lines):
        if line.startswith("@@ -0,0 +1,"):
            start = index
            break
    if start is None:
        raise AssertionError("patch has no added-file hunk")
    body = []
    for line in lines[start + 1:]:
        if line.startswith("--- a/"):
            break
        if line.startswith("+"):
            body.append(line[1:])
    return body, lines[start]


def inject_path(name):
    """Mirror the C branch for one blob-relative name."""
    prefix = "addons/"
    if not name.startswith(prefix):
        return None
    return INJECT + "/" + name[len(prefix):]


def cases():
    body, header = added_lines()
    joined = "\n".join(body)

    def test_the_second_root_is_defined():
        assert '#define K60_METAL_INJECT "%s"' % INJECT in joined

    def test_the_first_root_is_unchanged():
        assert '#define K60_METAL_ROOT "%s"' % ROOT in joined

    def test_both_inject_directories_are_created():
        assert joined.count('k60_metal_mkdir(K60_METAL_INJECT, p, scratch)') == 1
        assert joined.count(
            'k60_metal_mkdir(K60_METAL_INJECT "/PongAdrenoMetal.bundle", p, scratch)'
        ) == 1

    def test_the_branch_only_handles_addons_names():
        assert 'memcmp(name, "addons/", sizeof("addons/") - 1) == 0' in joined

    def test_the_hunk_header_matches_its_body():
        declared = int(re.search(r"\+1,(\d+)", header).group(1))
        assert declared == len(body), (declared, len(body))

    def test_the_inject_path_matches_what_init_injects():
        init = read(INIT)
        # init-v24dp.c hard-codes the bundle binary it execs into backboardd.
        match = re.search(r'(/private/var/pong/PongAdrenoMetal\.bundle/[^ "]+) backboardd"',
                          init)
        assert match is not None, "init-v24dp.c no longer carries the inject line"
        expected = match.group(1)
        assert inject_path("addons/PongAdrenoMetal.bundle/PongAdrenoMetal") == expected

    def test_every_bundle_file_lands_under_the_bundle_directory():
        for name in ("Info.plist", "PongAdrenoMetal", "PongMetalBridge.dylib",
                     "libvulkan_freedreno.dylib"):
            got = inject_path("addons/PongAdrenoMetal.bundle/" + name)
            assert got == INJECT + "/PongAdrenoMetal.bundle/" + name

    def test_the_two_markers_land_at_the_inject_root():
        for marker in ("publish", "clients"):
            got = inject_path("addons/PongAdrenoMetal." + marker)
            assert got == INJECT + "/PongAdrenoMetal." + marker

    def test_the_generator_still_emits_addons_names():
        # If the generator stopped emitting "addons/", the C branch would never
        # fire and the inject copy would silently disappear.
        text = read(GEN)
        assert 'addons/PongAdrenoMetal.bundle/' in text
        assert 'addons/PongAdrenoMetal.clients' in text
        assert 'addons/PongAdrenoMetal.publish' in text

    def test_the_summary_reports_the_injected_count():
        assert 'inject=%u' in joined
        assert 'count, injected, error' in joined

    def test_the_modes_pass_the_init_helpers_own_check():
        # init-v24dp.c only injects when the binary is uid 0 and
        # !(st_mode & 022); the kernel writes as root, so the mode is the half
        # that can silently regress.
        text = read(GEN)
        pairs = re.findall(r"\('(addons/[^']+)',\s*0o(\d+)\)", text)
        assert pairs, "generator no longer declares modes in the expected shape"
        for name, mode in pairs:
            value = int(mode, 8)
            assert value & 0o022 == 0, (name, oct(value))

    return [
        test_the_second_root_is_defined,
        test_the_first_root_is_unchanged,
        test_both_inject_directories_are_created,
        test_the_branch_only_handles_addons_names,
        test_the_hunk_header_matches_its_body,
        test_the_inject_path_matches_what_init_injects,
        test_every_bundle_file_lands_under_the_bundle_directory,
        test_the_two_markers_land_at_the_inject_root,
        test_the_generator_still_emits_addons_names,
        test_the_summary_reports_the_injected_count,
        test_the_modes_pass_the_init_helpers_own_check,
    ]


def main():
    failures = []
    tests = cases()
    for test in tests:
        try:
            test()
        except Exception as error:  # noqa: BLE001 - report and continue
            failures.append((test.__name__, error))
            print("FAIL %s: %s" % (test.__name__, error))
        else:
            print("ok %s" % test.__name__)
    print("TESTS OK %d case(s) (%d failure(s))" % (len(tests), len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
