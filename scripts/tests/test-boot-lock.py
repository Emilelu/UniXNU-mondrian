#!/usr/bin/env python3
"""test-boot-lock.py — 机器级 boot claim 的可执行判据（P-238）。

2026-11-18 用户把上机规则从「只有 Lead 能 boot」改成「哪个 agent 先抢到就哪个 boot」。
先到先得只有在**单写者**成立时才是安全的：两个 agent 同时 `fastboot boot` 会让后者的
抓取对着已经换了镜像的设备，日志与镜像对不上，比没日志更坏。

因此这条 claim 必须用**可执行**的判据钉住四件事：
1. 持有者存在时，第二个申请者必须被拒绝，且错误里带 `K60_BOOT_BUSY` 与持有者信息；
2. 持有者退出（含崩溃）后，锁必须自动可用 —— 不能留下需要人工清理的死锁文件；
3. 释放时要写下 `releasedAt`，否则事后无法判断谁在什么时候占用过设备；
4. 没有 `-Actor` 时必须拒绝，匿名 claim 等于没有归属。

需要 powershell.exe；没有就跳过并明确说明（不静默通过）。
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOCK_PS1 = os.path.join(REPO, "scripts", "k60-boot-lock.ps1")

FAILED = []


def case(name, condition, detail=""):
    if condition:
        print("ok   %s" % name)
    else:
        print("FAIL %s %s" % (name, detail))
        FAILED.append(name)


def find_powershell():
    for name in ("powershell.exe", "pwsh.exe", "powershell", "pwsh"):
        found = shutil.which(name)
        if found:
            return found
    for candidate in (
        r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
        "/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
    ):
        if os.path.exists(candidate):
            return candidate
    return None


def scratch_parent():
    """A directory both sides can see.

    Under WSL `tempfile.mkdtemp()` lands in /tmp, which powershell.exe cannot
    open — every case then fails for a path reason and the test looks like a
    locking regression. Use the durable state directory when it exists.
    """
    for candidate in ("/mnt/e/iOS Port/Work/state", "E:/iOS Port/Work/state"):
        if os.path.isdir(candidate):
            return candidate
    return None


def to_windows_path(path):
    """Translate a path so powershell.exe can open it."""
    if len(path) > 2 and path[1] == ":" and path[2] in "\\/":
        return path.replace("/", "\\")
    try:
        done = subprocess.run(["wslpath", "-w", path], capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              check=False)
    except OSError:
        return path
    translated = (done.stdout or "").strip()
    return translated or path


def holder_script(ps1, lock, actor, release_marker, hold_seconds):
    # Hold until the test says so, not for a fixed duration: under the full
    # registry dozens of checks run concurrently and a fixed 8-second window is
    # enough for the contender's PowerShell startup to outlast it, which would
    # make "a second claimant is refused" fail for a scheduling reason rather
    # than a locking reason. The deadline is only a safety net.
    return (
        ". '%s'; "
        "$c = Enter-K60BootLock -Path '%s' -Actor '%s' -Serial '6033dbec' -Image 'boot.img'; "
        "$deadline = (Get-Date).AddSeconds(%d); "
        "while (-not (Test-Path -LiteralPath '%s') -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 100 }; "
        "Exit-K60BootLock -Claim $c"
    ) % (ps1, lock, actor, hold_seconds, release_marker)


def contender_script(ps1, lock, actor):
    return (
        ". '%s'; "
        "$c = Enter-K60BootLock -Path '%s' -Actor '%s' -Serial '6033dbec' -Image 'boot.img'; "
        "if ($c) { Exit-K60BootLock -Claim $c; Write-Output 'ACQUIRED' }"
    ) % (ps1, lock, actor)


def anonymous_script(ps1, lock):
    return (
        ". '%s'; "
        "$c = Enter-K60BootLock -Path '%s' -Actor '' -Serial '6033dbec' -Image 'boot.img'; "
        "Write-Output 'ACQUIRED'"
    ) % (ps1, lock)


def run(shell, command, timeout=90):
    return subprocess.run(
        [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )


def wait_for(predicate, seconds=20.0):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.2)
    return False


def main():
    shell = find_powershell()
    if not shell:
        print("SKIP a PowerShell host is required to execute the boot claim")
        return 0
    if not os.path.exists(LOCK_PS1):
        print("FAIL scripts/k60-boot-lock.ps1 is missing")
        return 1

    with tempfile.TemporaryDirectory(dir=scratch_parent()) as scratch:
        # Keep local paths for existence checks and Windows paths for the
        # PowerShell command line, so the same test runs from MSYS and from WSL.
        lock_local = os.path.join(scratch, "device.lock")
        owner_local = lock_local + ".owner.json"
        release_local = os.path.join(scratch, "release.marker")
        lock = to_windows_path(lock_local)
        owner = to_windows_path(owner_local)
        release_marker = to_windows_path(release_local)
        ps1 = to_windows_path(LOCK_PS1)

        holder = subprocess.Popen(
            [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
             holder_script(ps1, lock, "holder-agent", release_marker, 120)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        try:
            case("the first claimant writes owner metadata", wait_for(lambda: os.path.exists(owner_local)), owner)
            record = {}
            if os.path.exists(owner_local):
                try:
                    record = json.loads(open(owner_local, encoding="utf-8").read())
                except ValueError as error:
                    case("owner metadata is valid JSON", False, error)
            case("the owner is attributed to the claiming actor", record.get("actor") == "holder-agent", record)
            case("the owner records the device serial", record.get("serial") == "6033dbec", record)

            contender = run(shell, contender_script(ps1, lock, "contender-agent"), timeout=60)
            combined = (contender.stdout or "") + (contender.stderr or "")
            case("a second claimant is refused", "ACQUIRED" not in combined, combined[-400:])
            case("the refusal names K60_BOOT_BUSY", "K60_BOOT_BUSY" in combined, combined[-400:])
            case("the refusal reports who holds the claim", "holder-agent" in combined, combined[-400:])
        finally:
            # Release deterministically, then reap the holder.
            try:
                open(release_local, "w", encoding="utf-8").close()
            except OSError:
                pass
            try:
                holder.wait(timeout=60)
            except subprocess.TimeoutExpired:
                holder.kill()
                holder.wait()

        case("the claim is released when the holder exits", wait_for(lambda: _released(owner_local), 20.0), _read(owner_local))

        again = run(shell, contender_script(ps1, lock, "next-agent"), timeout=60)
        case("the claim is reusable after release", "ACQUIRED" in (again.stdout or ""), (again.stdout or "")[-300:])
        case("a released claim stamps releasedAt", _released(owner_local), _read(owner_local))

        anonymous = run(shell, anonymous_script(ps1, lock), timeout=60)
        anonymous_text = (anonymous.stdout or "") + (anonymous.stderr or "")
        case("an anonymous claim is refused", "ACQUIRED" not in anonymous_text, anonymous_text[-300:])

        # The trap that cost a whole design iteration: POSIX `flock` and the
        # supervisor's FileShare::None handle are different lock domains. On WSL a
        # shell probe happens to fail (the 9p open hits the Windows sharing
        # violation), but that is an accident of the mount, not a lock contract —
        # so the only property worth pinning is the safe direction: while Windows
        # holds the claim, a shell probe must never report that it acquired it.
        flock = shutil.which("flock")
        bash = shutil.which("bash")
        if flock and bash:
            with tempfile.TemporaryDirectory(dir=scratch_parent()) as probe_scratch:
                probe_local = os.path.join(probe_scratch, "device.lock")
                probe = to_windows_path(probe_local)
                probe_release = to_windows_path(os.path.join(probe_scratch, "release.marker"))
                holder2 = subprocess.Popen(
                    [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                     holder_script(ps1, probe, "flock-holder", probe_release, 60)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                    encoding="utf-8", errors="replace",
                )
                try:
                    case("the second holder actually took its claim",
                         wait_for(lambda: os.path.exists(probe_local + ".owner.json"), 30.0), probe)
                    blind = subprocess.run([bash, "-c", 'flock -n "$1" -c true', "bash", probe_local],
                                           capture_output=True, text=True, encoding="utf-8",
                                           errors="replace", check=False)
                    case("a shell-side flock never looks free while the claim is held",
                         blind.returncode != 0,
                         "flock rc=%d (must be non-zero): a shell probe that reports free here is exactly "
                         "the false safety flash.sh used to have" % blind.returncode)
                finally:
                    try:
                        open(os.path.join(probe_scratch, "release.marker"), "w", encoding="utf-8").close()
                    except OSError:
                        pass
                    try:
                        holder2.wait(timeout=60)
                    except subprocess.TimeoutExpired:
                        holder2.kill()
                        holder2.wait()
        else:
            print("skip POSIX flock is unavailable; the cross-domain trap cannot be demonstrated here")

    if FAILED:
        print("\nTESTS FAILED %d: %s" % (len(FAILED), ", ".join(FAILED)))
        return 1
    print("\nTESTS OK")
    return 0


def _read(path):
    try:
        return json.loads(open(path, encoding="utf-8").read())
    except (OSError, ValueError):
        return {}


def _released(path):
    return bool(_read(path).get("releasedAt"))


if __name__ == "__main__":
    sys.exit(main())
