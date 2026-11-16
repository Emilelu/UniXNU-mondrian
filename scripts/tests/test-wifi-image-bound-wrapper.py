#!/usr/bin/env python3
"""Meaningful host-only contract tests; no C build, real image generation or device I/O.

Optional --c8-manifest/--c8-image checks the existing historical files read-only.
Each negative asserts zero recorded runner calls. JSON fixtures contain actual pinned
WiFi source, and are explicitly nonbootable/noncompiled. Raw result codes are printed.
"""
from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "scripts/proposals/wifi_image_bound_wrapper.py"
REVISION = "3cf1a08c8a7c60656c9682fb53d1c1b3bf74a185"
OBSERVATION = "wifi-pci-source-fixture"
SOURCE = "drivers/PongWifi/PongWifiPci.cpp"
DATA = ROOT / "docs/research/EIGHT-STEPS.toml"
STEPS = ("same_model", "official", "decompile", "wide", "plan", "deep", "verify")
EVIDENCE = "Offline source fixture: drivers/PongWifi/PongWifiPci.cpp:58; no compiled/device claim."
SUCCESS = "Fixture only: recorder accepts source identity; PongWifiPci.cpp:58 is present."
FAILURE = "Fixture only: any identity/scope/gate mismatch refuses before recorder; no boot occurs."

spec = importlib.util.spec_from_file_location("wifi_image_bound_wrapper", WRAPPER)
wrapper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wrapper)


def toml(data):
    lines = []
    def emit(path, table):
        lines.append("[" + ".".join(path) + "]")
        for key, value in table.items():
            if not isinstance(value, dict):
                lines.append(key + " = " + (str(value).lower() if isinstance(value, bool)
                                           else json.dumps(value)))
        lines.append("")
        for key, value in table.items():
            if isinstance(value, dict):
                emit(path + [key], value)
    emit(["hardware"], data)
    return "\n".join(lines).encode("utf-8")


def record(status):
    steps = {name: {"done": True, "evidence": EVIDENCE} for name in STEPS}
    steps["wide"].update(catalog_checked=True, catalog_result=EVIDENCE)
    steps["verify"].update(local_verified=True, static_check=EVIDENCE, unit_test=EVIDENCE,
                           artifact_check=EVIDENCE, observation=OBSERVATION,
                           reference="observation.txt")
    steps["device"] = {"done": False, "prediction": {"success": SUCCESS, "failure": FAILURE,
                        "observation": OBSERVATION, "reference": "observation.txt"}}
    return {"status": status, "step": steps}


class Fixture:
    def __init__(self, directory, args="-v applog=1 pong_wifi=1 k60_wifi_rsc=2"):
        self.root = directory
        directory.mkdir()
        source = subprocess.run([wrapper.GIT, "-c", "safe.directory=" + str(ROOT),
                                 "--no-replace-objects", "cat-file", "blob", REVISION + ":" + SOURCE],
                                cwd=ROOT, env=wrapper.clean_env(), capture_output=True, timeout=20)
        assert source.returncode == 0, source.stderr
        self.source = source.stdout
        self.kernel = b"NONBOOTABLE SOURCE FIXTURE ONLY\n" + self.source
        self.archive = {"format": "wifi-source-archive-fixture-v1",
                        "source_sha256": wrapper.digest(self.source),
                        "source_base64": base64.b64encode(self.source).decode()}
        import tomllib
        trusted = tomllib.loads(DATA.read_text(encoding="utf-8"))["hardware"]
        self.hardware = {key: record(value.get("status", "active"))
                         for key, value in trusted.items()}
        self.compile_record = {"format": "source-fixture-no-compiler", "source": SOURCE,
                               "source_revision": REVISION,
                               "source_sha256": wrapper.digest(self.source)}
        self.files = {"source": "PongWifiPci.cpp", "config": "build.config",
                      "archive": "source-archive.json", "compile_commands": "compile.json",
                      "link_record": "link.json", "steps": "EIGHT-STEPS.toml",
                      "observation": "observation.txt"}
        self.config = b"CONFIG_XNU_PONG_WIFI=y\n"
        self.image = {"format": wrapper.FORMAT, "source_revision": REVISION,
                      "payload": {"args": args, "kernel_base64": base64.b64encode(self.kernel).decode()}}
        self.manifest = {"tag": "display-only-name-is-irrelevant", "eight_step_items": "display",
                         "repo": {"head": REVISION, "dirty_files": 0},
                         "payload_args": args,
                         "kernel_args_requested": args.split()[2:],
                         "components": {"boot_img_path": "fixture-image.json"},
                         "proposal_binding": {"schema_version": 1, "format": wrapper.FORMAT,
                                              "files": self.files}}
        self.link_record = {"format": "source-fixture-no-linker", "archive_sha256": "",
                            "kernel_sha256": wrapper.digest(self.kernel),
                            "source_revision": REVISION}
        self.observation = {"format": "wifi-observation-fixture-v1", "id": OBSERVATION,
                            "activation": wrapper.activation(args), "scope": ["wifi"],
                            "success": SUCCESS, "failure": FAILURE}
        self.review = {"purpose": "offline-fixture-only", "source_revision": REVISION,
                       "observation": OBSERVATION,
                       "gate_base_sha256": wrapper.file_digest(wrapper.GATE),
                       "gate_patch_sha256": wrapper.file_digest(wrapper.PATCH)}
        self.review["active_floor_sha256"] = wrapper.file_digest(DATA)
        self.review["supervisor"] = wrapper.supervisor_plan()
        self.manifest["proposal_binding"]["supervisor"] = wrapper.supervisor_plan()
        self.refresh()

    def put(self, name, data):
        (self.root / name).write_bytes(data)

    def refresh(self, observation=True, link=True):
        """Freeze a new offline fixture; never used with an existing real artifact."""
        archive = wrapper.canonical(self.archive)
        if link:
            self.link_record["archive_sha256"] = wrapper.digest(archive)
        self.image["archive_base64"] = base64.b64encode(archive).decode()
        image = wrapper.canonical(self.image)
        self.put("fixture-image.json", image)
        comp = self.manifest["components"]
        comp.update(boot_img=wrapper.digest(image), payload=wrapper.digest(wrapper.canonical(self.image["payload"])),
                    payload_kernel=wrapper.digest(self.kernel), wifi_archive=wrapper.digest(archive),
                    wifi_archive_path=self.files["archive"])
        self.put(self.files["source"], self.source)
        self.put(self.files["config"], self.config)
        self.put(self.files["archive"], archive)
        self.put(self.files["compile_commands"], wrapper.canonical(self.compile_record))
        self.put(self.files["link_record"], wrapper.canonical(self.link_record))
        self.put(self.files["steps"], toml(self.hardware))
        if observation:
            self.observation["identity"] = {
                "image_sha256": comp["boot_img"], "source_revision": self.manifest["repo"]["head"],
                "payload_args": self.manifest["payload_args"],
                "kernel_args_requested": self.manifest["kernel_args_requested"],
                "payload_sha256": comp["payload"], "kernel_sha256": comp["payload_kernel"],
                "wifi_archive_sha256": comp["wifi_archive"], "source_sha256": wrapper.digest(self.source),
                "config_sha256": wrapper.file_digest(self.root / self.files["config"]),
                "compile_commands_sha256": wrapper.file_digest(self.root / self.files["compile_commands"]),
                "link_record_sha256": wrapper.file_digest(self.root / self.files["link_record"]),
                "steps_sha256": wrapper.file_digest(self.root / self.files["steps"]),
                "gate_base_sha256": self.review["gate_base_sha256"],
                "gate_patch_sha256": self.review["gate_patch_sha256"],
                "active_floor_sha256": self.review["active_floor_sha256"],
                "supervisor": self.review["supervisor"]}
        self.put(self.files["observation"], wrapper.canonical(self.observation))
        self.refreeze()

    def refreeze(self):
        lines = [wrapper.file_digest(self.root / name) + "  " + name
                 for name in sorted(self.files.values()) if (self.root / name).is_file()]
        self.put("frozen-before.txt", ("\n".join(lines) + "\n").encode())
        self.manifest["frozen"] = {"file": "frozen-before.txt",
                                   "list_sha256": wrapper.file_digest(self.root / "frozen-before.txt")}
        self.save_manifest()

    def save_manifest(self):
        raw = wrapper.canonical(self.manifest)
        self.put("build-manifest.json", raw)
        self.review["manifest_sha256"] = wrapper.digest(raw)
        self.save_review()

    def save_review(self):
        self.put("review.json", wrapper.canonical(self.review))

    def run(self, scope="wifi", review=True, runner=None):
        return wrapper.execute(self.root / "build-manifest.json", self.root / "fixture-image.json",
                               self.root / "review.json" if review else None, scope, runner)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--c8-manifest")
    parser.add_argument("--c8-image")
    args = parser.parse_args()
    assert bool(args.c8_manifest) == bool(args.c8_image), "supply both c8 inputs"
    before = {str(path): wrapper.file_digest(path) for path in (wrapper.GATE, DATA, wrapper.PATCH)}
    results, failures = [], []
    real_run = subprocess.run
    commands = []

    def guarded_run(command, **kwargs):
        # Fixed git inspection/patching and isolated Python gate/CLI are the entire
        # subprocess surface. No callback, shell=True, PowerShell or supervisor.
        assert not kwargs.get("shell")
        if command[0] in ("git", wrapper.GIT):
            if command[1] == "-c":
                assert command[2:5] == ["safe.directory=" + str(ROOT), "--no-replace-objects", "cat-file"], command
                assert kwargs.get("cwd") == ROOT, command
            else:
                assert command[1] == "apply", command
        else:
            assert command[0] == sys.executable and command[1] == "-I", command
            assert any(Path(str(part)).name in ("eight-step-gate.py", WRAPPER.name) for part in command), command
        commands.append([str(part) for part in command])
        return real_run(command, **kwargs)

    subprocess.run = guarded_run
    try:
        with tempfile.TemporaryDirectory(prefix="wifi-bound-tests-") as temp:
            root = Path(temp)
            def check(label, mutation=None, want=1, needle=None, scope="wifi", review=True,
                      fixture_args="-v applog=1 pong_wifi=1 k60_wifi_rsc=2", runner=None):
                fixture = Fixture(root / ("case-%02d" % len(results)), fixture_args)
                if mutation:
                    mutation(fixture)
                result = fixture.run(scope, review, runner)
                ok = result["exit_code"] == want and result["runner_calls"] == (1 if want in (0, 7) else 0)
                output = (result.get("error") or "") + json.dumps(result.get("gate"), ensure_ascii=True)
                ok = ok and (needle is None or needle in output)
                row = {"case": label, "pass": ok, "raw_exit_code": result["exit_code"],
                       "runner_calls": result["runner_calls"],
                       "gate_exit_code": (result.get("gate") or {}).get("exit_code"),
                       "error": result["error"]}
                print(json.dumps(row, ensure_ascii=True))
                results.append(row)
                if not ok:
                    failures.append(label)
                    print(json.dumps(result, ensure_ascii=True))
                return fixture, result

            fixture, positive = check("positive source fixture + parked WiFi + active floor", want=0)
            assert "touch[active]" in positive["gate"]["stdout"] and "wifi[parked]" in positive["gate"]["stdout"]
            assert "gpu[active]" in positive["gate"]["stdout"] and "battery[active]" in positive["gate"]["stdout"]
            assert positive["supervisor_plan"] == wrapper.supervisor_plan()
            print(json.dumps({"fixture_inputs": positive["identity"],
                              "manifest_sha256": positive["manifest_sha256"],
                              "observation": OBSERVATION, "code_present": positive["code_present"],
                              "activation": positive["activation"], "gate_stdout": positive["gate"]["stdout"]},
                             ensure_ascii=True))
            check("actual WiFi source + display scope", scope="display", needle="WiFi code present")
            check("missing explicit scope", scope=None, needle="missing explicit scope")
            check("unknown explicit target", scope="wifi,nosuch", needle="unknown target")
            check("duplicate explicit target", scope="wifi,wifi", needle="duplicate")
            check("missing reviewed identity", review=False, needle="missing reviewed")
            check("disabled activation still requires WiFi scope", scope="display",
                  fixture_args="-v applog=1 pong_wifi=0", needle="WiFi code present")
            _, disabled = check("disabled activation classified separately", want=0,
                                fixture_args="-v applog=1 pong_wifi=0")
            assert disabled["activation"] == "disabled" and disabled["code_present"]
            _, unknown = check("missing activation flag conservatively retains WiFi scope", want=0,
                               fixture_args="-v applog=1")
            check("duplicate conflicting requested args", fixture_args="-v applog=1 pong_wifi=0 pong_wifi=1",
                  needle="duplicate/conflicting requested args")
            assert unknown["activation"] == "unknown" and unknown["code_present"]
            check("fake runner raw exit propagates", want=7, runner=wrapper.RecordedFakeRunner(7))
            check("arbitrary runner rejected", runner=lambda _: 0, needle="recorded in-process fake")

            def bad_supervisor(f):
                f.manifest["proposal_binding"]["supervisor"]["argv"][-1] = "spoofed-device"
                f.save_manifest()
            check("inert supervisor parameter plan mismatch", bad_supervisor, needle="supervisor script/parameter")
            check("malformed manifest JSON root list", lambda f: f.put("build-manifest.json", b"[]"),
                  needle="JSON root must be an object")
            def omitted_floor(f):
                del f.hardware["gpu"]
                f.refresh()
            check("artifact cannot omit trusted active floor", omitted_floor, needle="trusted active floor omitted")
            def demoted_floor(f):
                f.hardware["display"]["status"] = "parked"
                f.refresh()
            check("artifact cannot demote trusted active floor", demoted_floor, needle="trusted active floor omitted")

            def alter_manifest(key, value):
                def mutate(f):
                    f.manifest[key] = value
                    f.save_manifest()
                return mutate
            check("missing historical binding", alter_manifest("proposal_binding", None), needle="no backfill")
            check("image hash mismatch", lambda f: f.put("fixture-image.json", b"wrong image"), needle="outer image")
            check("manifest review mismatch", lambda f: f.put("build-manifest.json", b"{}"), needle="components.boot_img")
            def stale_manifest(f):
                f.manifest["tag"] = "wifi-looking-tag-does-not-authorize"
                f.put("build-manifest.json", wrapper.canonical(f.manifest))
            check("review pins entire manifest", stale_manifest, needle="manifest review hash")
            def revision(f):
                f.manifest["repo"]["head"] = "0" * 40
                f.save_manifest()
            check("full source revision mismatch", revision, needle="review revision")
            def coherent_revision(f):
                revision(f)
                f.review["source_revision"] = "0" * 40
                f.image["source_revision"] = "0" * 40
                f.refresh()
            check("coherently rehashed nonexistent source revision", coherent_revision,
                  needle="existing commit object")
            def tree_revision(f):
                tree = subprocess.run([wrapper.GIT, "-c", "safe.directory=" + str(ROOT),
                                       "--no-replace-objects", "cat-file", "-p", REVISION],
                                      cwd=ROOT, env=wrapper.clean_env(), capture_output=True, timeout=20)
                oid = tree.stdout.splitlines()[0].split()[1].decode("ascii")
                f.manifest["repo"]["head"] = oid
                f.review["source_revision"] = oid
                f.image["source_revision"] = oid
                f.compile_record["source_revision"] = oid
                f.link_record["source_revision"] = oid
                f.refresh()
            check("tree object is not a source commit revision", tree_revision, needle="existing commit object")
            def unknown_format(f):
                f.image["format"] = "android-bootimg-or-unknown"
                f.refresh()
            check("unsupported real or unknown image format", unknown_format, needle="no real boot image adapter")
            def args_mismatch(f):
                f.manifest["payload_args"] += " altered=1"
                f.save_manifest()
            check("exact payload argument mismatch", args_mismatch, needle="args readback")
            def payload_mismatch(f):
                f.manifest["components"]["payload"] = "0" * 64
                f.save_manifest()
            check("payload hash mismatch", payload_mismatch, needle="payload readback hash")
            def kernel_mismatch(f):
                f.manifest["components"]["payload_kernel"] = "0" * 64
                f.save_manifest()
            check("payload kernel hash mismatch", kernel_mismatch, needle="kernel readback hash")
            def archive_hash(f):
                f.manifest["components"]["wifi_archive"] = "0" * 64
                f.save_manifest()
            check("archive component hash mismatch", archive_hash, needle="archive hash")
            def archive_member(f):
                f.archive["source_base64"] = base64.b64encode(b"not the WiFi source").decode()
                f.refresh()
            check("rehashed archive lacks source member", archive_member, needle="source membership")
            def stale_link(f):
                f.link_record["archive_sha256"] = "0" * 64
                f.refresh(link=False)
            check("rehashed link archive mismatch", stale_link, needle="link record/archive")
            def stale_compile(f):
                f.compile_record["source_revision"] = "0" * 40
                f.refresh()
            check("rehashed compiler revision mismatch", stale_compile, needle="compile record/revision")
            def absent_source(f):
                f.kernel = b"NONBOOTABLE FIXTURE WITHOUT WIFI SOURCE"
                f.image["payload"]["kernel_base64"] = base64.b64encode(f.kernel).decode()
                f.link_record["kernel_sha256"] = wrapper.digest(f.kernel)
                f.refresh()
            check("rehashed kernel lacks actual WiFi source", absent_source, needle="WiFi source bytes absent")
            def unknown_config(f):
                f.config = b"CONFIG_XNU_PONG_WIFI=maybe\n"
                f.refresh()
            check("unknown config cannot establish classification", unknown_config, needle="unknown WiFi build config")
            def missing_observation(f):
                (f.root / "observation.txt").unlink()
                f.refreeze()
            check("missing observation file", missing_observation, needle="absent from frozen")
            def stale_observation(f):
                f.observation["identity"]["image_sha256"] = "0" * 64
                f.refresh(observation=False)
            check("rehashed stale observation image identity", stale_observation, needle="observation identity")
            def mismatched_activation(f):
                f.observation["activation"] = "disabled"
                f.refresh()
            check("observation activation mismatch", mismatched_activation, needle="observation activation")
            def missing_id(f):
                del f.observation["id"]
                f.refresh()
            check("missing observation identifier", missing_id, needle="observation identifier")
            def missing_frozen_role(f):
                del f.manifest["proposal_binding"]["files"]["observation"]
                f.save_manifest()
            check("missing historical frozen role", missing_frozen_role, needle="binding missing/unknown roles")
            check("unfrozen config change", lambda f: f.put("build.config", b"CONFIG_XNU_PONG_WIFI=n\n"),
                  needle="frozen file hash mismatch")
            for role in sorted(wrapper.ROLES):
                def missing_role(f, role=role):
                    (f.root / f.files[role]).unlink()
                check("missing frozen " + role, missing_role, needle="frozen file missing")
                def corrupt_role(f, role=role):
                    f.put(f.files[role], b"corrupt frozen artifact")
                check("corrupt frozen " + role, corrupt_role, needle="frozen file hash mismatch")
            def malformed_review(f):
                f.put("review.json", b"[]")
            check("malformed review root list", malformed_review, needle="JSON root must be an object")
            def malformed_nested(f):
                f.manifest["components"] = ["invalid"]
                f.save_manifest()
            check("malformed nested components list", malformed_nested)
            def malformed_image(f):
                raw = b"[]"
                f.put("fixture-image.json", raw)
                f.manifest["components"]["boot_img"] = wrapper.digest(raw)
                f.save_manifest()
            check("malformed image root list with matching outer hash", malformed_image,
                  needle="JSON root must be an object")
            def malformed_observation(f):
                f.put("observation.txt", b"null")
                f.refreeze()
            check("malformed observation root scalar", malformed_observation,
                  needle="JSON root must be an object")
            def unsupported_schema(f):
                f.manifest["proposal_binding"]["schema_version"] = 2
                f.save_manifest()
            check("unknown binding schema", unsupported_schema, needle="unsupported binding format")
            for value in (True, 1.0, "1"):
                def noninteger_schema(f, value=value):
                    f.manifest["proposal_binding"]["schema_version"] = value
                    f.save_manifest()
                check("noninteger binding schema " + repr(value), noninteger_schema,
                      needle="unsupported binding format")
            def invalid_revision(f):
                f.manifest["repo"]["head"] = "abc"
                f.save_manifest()
            check("truncated source revision", invalid_revision, needle="40-character revision")
            def bad_gate(f):
                f.review["gate_base_sha256"] = "0" * 64
                f.save_review()
            check("gate base hash mismatch", bad_gate, needle="gate base revision/hash")
            def active_floor(f):
                f.hardware["touch"]["step"]["official"]["done"] = False
                f.refresh()
            _, floor = check("active floor fails inside actual proposed gate", active_floor,
                             needle="touch ::")
            assert floor["gate"]["exit_code"] != 0
            def wifi_verify(f):
                f.hardware["wifi"]["step"]["verify"]["local_verified"] = False
                f.refresh()
            check("parked WiFi verify fails inside actual proposed gate", wifi_verify,
                  needle="local_verified")
            def stale_prediction(f):
                f.hardware["wifi"]["step"]["device"]["prediction"]["observation"] = "old-observation"
                f.refresh()
            check("stale prediction fails inside actual proposed gate", stale_prediction,
                  needle="observation mismatch")
            env_old = dict(os.environ)
            try:
                os.environ.update(K60_FLASH_ITEMS="display", K60_FLASH_OBSERVATION="old",
                                  K60_EIGHT_STEP_ITEMS="display", K60_WIFI_ARCHIVE_SHA256="0" * 64,
                                  K60_IMAGE_SHA256="0" * 64, K60_SKIP_GATES="1",
                                  GIT_DIR="nonexistent-spoof-repo", GIT_OBJECT_DIRECTORY="nonexistent-spoof-objects",
                                  GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="core.bare", GIT_CONFIG_VALUE_0="true")
                check("environment cannot supply missing scope", scope=None, needle="missing explicit scope")
                check("environment cannot override checked identities or gate scope", want=0)
            finally:
                os.environ.clear()
                os.environ.update(env_old)

            cli = subprocess.run([sys.executable, "-I", "-X", "utf8", str(WRAPPER), "--manifest",
                                  str(fixture.root / "build-manifest.json"), "--image",
                                  str(fixture.root / "fixture-image.json"), "--review",
                                  str(fixture.root / "review.json"), "--scope", "wifi"],
                                 cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30)
            cli_result = json.loads(cli.stdout)
            ok = cli.returncode == 0 and cli_result["exit_code"] == 0 and cli_result["runner_calls"] == 1
            print(json.dumps({"case": "CLI positive fake only", "pass": ok,
                              "raw_exit_code": cli.returncode, "runner_calls": cli_result["runner_calls"]}))
            if not ok:
                failures.append("CLI positive")
            if args.c8_manifest:
                command = [sys.executable, "-I", "-X", "utf8", str(WRAPPER), "--manifest", args.c8_manifest,
                           "--image", args.c8_image, "--scope", "wifi"]
                c8 = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                    encoding="utf-8", timeout=30)
                c8_result = json.loads(c8.stdout)
                ok = (c8.returncode == 1 and c8_result["runner_calls"] == 0 and
                      "missing historical proposal_binding" in c8_result["error"])
                print(json.dumps({"case": "real c8 read-only rejection", "pass": ok,
                                  "command": command, "raw_exit_code": c8.returncode,
                                  "result": c8_result}, ensure_ascii=True))
                if not ok:
                    failures.append("real c8 rejection")
    finally:
        subprocess.run = real_run
    unchanged = before == {str(path): wrapper.file_digest(path) for path in (wrapper.GATE, DATA, wrapper.PATCH)}
    if not unchanged:
        failures.append("active inputs changed")
    print(json.dumps({"cases": len(results) + 1 + bool(args.c8_manifest), "failures": failures,
                      "active_inputs_unchanged": unchanged, "fixed_subprocess_calls": len(commands),
                      "source_revision": REVISION, "source_path": SOURCE}, ensure_ascii=True))
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
