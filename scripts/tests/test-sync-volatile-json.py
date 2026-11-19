"""输入镜像里的构建回执字段不能被当成输入漂移（P-188 同族）。

`mac-build/native-ufs/bindings.json` 是真正的输入：它给出 IOBlockStorageDevice 的
虚表绑定。但同一个文件里还有 `compiled_object_sha256`，那是上一次编译出来的
`NativeUfs.o` 的哈希——构建每跑一次就把它重写一次。于是镜像与仓库永远只差这一行，
`iron-5` 就报「输入被改过」，而唯一的「修法」是把镜像回执覆盖回仓库的旧值，等于
拿旧产物冒充新输入。

这个测试断言三件事：
1. 只差 `compiled_object_sha256` 时判定为一致（不报漂移）。
2. 其它字段不同仍然报差异（不能因为忽略一个字段就整体放过）。
3. 键集合不同也报差异（结构变了必须同步）。
"""

import importlib.util
import json
import os
import pathlib
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[2]
SYNC = REPO / "scripts" / "sync-device-input.py"

failures = []


def load():
    # The tool refuses to import without a named mirror (P-184), and that refusal is
    # the right behaviour: it is what stops a line from cross-polluting the shared
    # tree. The test only needs the comparison helper, so name a scratch mirror.
    os.environ.setdefault("K60_DEVICE_INPUT", str(pathlib.Path(tempfile.gettempdir()) / "k60-mirror-unused"))
    spec = importlib.util.spec_from_file_location("sync_device_input", SYNC)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except SystemExit:
        raise
    return module


def record(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ((" · " + detail) if detail and not ok else ""))
    if not ok:
        failures.append(name + ((" · " + detail) if detail else ""))


def write(path, payload):
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


BASE = {
    "fixed_prelink_base": "0xfffffff004420000",
    "original_candidate_sha256": "d260de",
    "compiled_object_sha256": "ffd03e",
    "virtual_methods_checked": 190,
    "concrete_overrides": 23,
    "bindings": {"__ZN20IOBlockStorageDevice10gMetaClassE": "0xfffffff006ead1d0"},
    "actual_io_qualified": False,
}


def main():
    record("the sync tool exists", SYNC.is_file(), str(SYNC))
    if not SYNC.is_file():
        return
    module = load()

    record(
        "the volatile field list names the compile receipt",
        "compiled_object_sha256" in getattr(module, "VOLATILE_JSON_FIELDS", ()),
        "VOLATILE_JSON_FIELDS must contain compiled_object_sha256",
    )

    if not hasattr(module, "json_equal_ignoring_volatile"):
        record("the comparison helper exists", False, "json_equal_ignoring_volatile is missing")
        return
    record("the comparison helper exists", True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        a = tmp / "repo.json"
        b = tmp / "mirror.json"

        write(a, BASE)
        other = dict(BASE)
        other["compiled_object_sha256"] = "b7f31a"
        write(b, other)
        record(
            "only the compile receipt differs => equal",
            module.json_equal_ignoring_volatile(a, b),
            "a rewritten compiled_object_sha256 must not count as input drift",
        )

        changed = dict(BASE)
        changed["virtual_methods_checked"] = 191
        write(b, changed)
        record(
            "a real field differs => not equal",
            not module.json_equal_ignoring_volatile(a, b),
            "virtual_methods_checked is an input and must be compared",
        )

        write(a, BASE)
        changed = dict(BASE)
        changed["compiled_object_sha256"] = "b7f31a"
        changed["virtual_methods_checked"] = 191
        write(b, changed)
        record(
            "receipt plus a real field => not equal",
            not module.json_equal_ignoring_volatile(a, b),
            "ignoring one field must not hide another field's change",
        )

        fewer = {k: v for k, v in BASE.items() if k != "concrete_overrides"}
        write(a, BASE)
        write(b, fewer)
        record(
            "a missing key => not equal",
            not module.json_equal_ignoring_volatile(a, b),
            "a structural change is drift even if the values agree",
        )

        write(a, BASE)
        b.write_text("{not json", encoding="utf-8")
        record(
            "an unreadable side => not equal",
            not module.json_equal_ignoring_volatile(a, b),
            "malformed JSON must fall back to a byte comparison",
        )

    print()
    if failures:
        print("FAILED %d case(s):" % len(failures))
        for f in failures:
            print("  - " + f)
        raise SystemExit(1)
    print("TESTS OK: a rebuild receipt is not input drift, and real changes still are")


if __name__ == "__main__":
    main()
