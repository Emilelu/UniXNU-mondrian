#!/usr/bin/env python3
"""Refuse tracked files that carry a credential or a LAN login target.

Iron rule 10: the build host on the LAN is environment, not project. Its
address and password must never reach a commit, because a push publishes the
entire history and a force-push does not recall what was already cloned.

The gate looks for the *shape of a secret in use* — a password handed to
sshpass, an SSH target on a private network, a password piped into sudo — not
for how documentation describes the procedure. Placeholders such as
``<password>`` / ``<user>@<mac-host>`` stay legal, so the docs can still explain
the workflow without naming the machine.
"""
import re
import subprocess
import sys

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

ROOT = subprocess.check_output(
    ["git", "rev-parse", "--show-toplevel"], text=True).strip()

PLACEHOLDER = r"(?!<|\$|\{|%|@)"

PATTERNS = [
    # sshpass -p 1015 … / sshpass -p mysecret …
    (re.compile(r"\bsshpass\s+-p\s+" + PLACEHOLDER + r"\S+"), "password on the sshpass command line"),
    # user@192.168.1.10 — an SSH/scp target on a private network
    (re.compile(r"@(?:192\.168|10|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}"), "LAN login target"),
    # password: hunter2 / PASSWD=…
    (re.compile(r"(?i)\b(?:password|passwd|pwd)\s*[:=]\s*" + PLACEHOLDER + r"\S+"), "inline password"),
    # echo 1015 | sudo -S …
    (re.compile(r"\becho\s+" + PLACEHOLDER + r"\S+\s*\|\s*sudo\s+-S\b"), "password piped into sudo"),
]

# Files whose job is to describe the gate itself, plus prose that documents the
# procedure with placeholders only.
ALLOW = {
    "scripts/check-secrets.py",
    "docs/engineering/RULES.toml",
    "AGENTS.md",
}


def tracked_files():
    out = subprocess.check_output(
        ["git", "-C", ROOT, "ls-files", "-z"]).decode("utf-8", "replace")
    return [p for p in out.split("\0") if p]


def main() -> int:
    files = tracked_files()
    bad = []
    for rel in files:
        if rel in ALLOW:
            continue
        try:
            with open(f"{ROOT}/{rel}", "rb") as handle:
                raw = handle.read()
        except OSError:
            continue
        if b"\0" in raw[:4096]:
            continue
        text = raw.decode("utf-8", "replace")
        for line_no, line in enumerate(text.splitlines(), 1):
            if "<" in line and ">" in line and "sshpass" in line:
                # documentation that shows the shape with placeholders
                stripped = line
                for pattern, _ in PATTERNS:
                    stripped = pattern.sub("", stripped)
                if "sshpass" not in stripped:
                    continue
            for pattern, label in PATTERNS:
                if pattern.search(line):
                    bad.append(f"{rel}:{line_no}: {label}: {line.strip()[:90]}")

    if bad:
        print("❌ 仓库里出现了不该提交的环境信息（铁则 10）：")
        for item in bad:
            print("  " + item)
        print("   把主机地址/口令从文件里删掉，改放到仓库之外的本地说明；")
        print("   文档里只写 <user>@<mac-host> 这种占位符。")
        return 1

    print(f"✅ secrets 检查通过（{len(files)} 个受管文件里没有口令或 LAN 登录目标）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
