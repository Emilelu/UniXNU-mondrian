#!/usr/bin/env python3
"""Host-only advisory-only contract tests; no C build, real image generation or device I/O.

The default wrapper is exercised through captured immutable bytes only. Every negative
asserts zero device-runner calls, no authorization, and a diagnostic error. A separate
isolated legacy probe preserves the known once-fake-runner path-binding defect as a
regression: it is expected to accept a temporary-good window and reach the exact
in-process recorder once, and that expected failure is printed as a diagnostic, never
counted as acceptance. Optional --c8-manifest/--c8-image checks the historical files
read-only; c8 still fails its missing proposal_binding.
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
sys.modules[spec.name] = wrapper
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

    def paths(self):
        return (self.root / "build-manifest.json", self.root / "fixture-image.json",
                self.root / "review.json")

    def run(self, scope="wifi", review=True):
        return wrapper.advisory(self.root / "build-manifest.json", self.root / "fixture-image.json",
                                self.root / "review.json" if review else None, scope)

    def capture(self):
        return wrapper.capture_inputs(self.root / "build-manifest.json",
                                      self.root / "fixture-image.json",
                                      self.root / "review.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--c8-manifest")
    parser.add_argument("--c8-image")
    args = parser.parse_args()
    assert bool(args.c8_manifest) == bool(args.c8_image), "supply both c8 inputs"
    before = {str(path): wrapper.file_digest(path)
              for path in (wrapper.GATE, DATA, wrapper.PATCH, wrapper.SUPERVISOR)}
    results, failures, diagnostics, rows = [], [], [], []
    real_run = subprocess.run
    commands = []

    def guarded_run(command, **kwargs):
        # The default advisory path launches Git inspection only. No gate execution,
        # PowerShell, shell, supervisor or device command is permitted.
        assert not kwargs.get("shell")
        assert command[0] in ("git", wrapper.GIT), command
        if command[1] == "-c":
            assert command[2:5] == ["safe.directory=" + str(ROOT), "--no-replace-objects",
                                    "cat-file"], command
            assert kwargs.get("cwd") == ROOT, command
        else:
            assert command[1] == "apply", command
        commands.append([str(part) for part in command])
        return real_run(command, **kwargs)

    def row(label, ok, result=None, detail=None):
        output = {"case": label, "pass": bool(ok)}
        if result is not None:
            output.update({"checks_exit": result.get("advisory_exit_code"),
                           "device_runner_calls": result.get("device_runner_calls"),
                           "flash_authorized": result.get("flash_authorized"),
                           "error": result.get("error")})
            if "runner_calls" in result:
                output.update({"runner_calls": result.get("runner_calls"),
                               "legacy_fake_accepted": result.get("legacy_fake_accepted"),
                               "path_matches_validated": result.get("path_matches_validated")})
        if detail is not None:
            output["detail"] = detail
        print(json.dumps(output, ensure_ascii=True))
        rows.append(output)
        if not ok:
            failures.append(label)
        return output

    subprocess.run = guarded_run
    try:
        with tempfile.TemporaryDirectory(prefix="wifi-bound-tests-") as temp:
            root = Path(temp)
            def check(label, mutation=None, want=1, needle=None, scope="wifi", review=True,
                      fixture_args="-v applog=1 pong_wifi=1 k60_wifi_rsc=2"):
                fixture = Fixture(root / ("case-%02d" % len(results)), fixture_args)
                if mutation:
                    mutation(fixture)
                result = fixture.run(scope, review)
                output = (result.get("error") or "") + json.dumps(result.get("identity"),
                                                                 ensure_ascii=True)
                ok = (result.get("advisory_exit_code") == want and
                      result.get("device_runner_calls") == 0 and
                      result.get("flash_authorized") is False and
                      (needle is None or needle in output))
                row(label, ok, result, {"needle": needle, "want": want})
                if not ok:
                    print(json.dumps(result, ensure_ascii=True))
                results.append(result)
                return fixture, result

            fixture, positive = check("advisory positive source fixture; zero runner", want=0)
            assert positive["mode"] == "advisory-only"
            assert positive["checks"] == "passed" and positive["flash_authorization"] == "none"
            assert positive["boundaries"]["captured_once"] is True
            assert positive["boundaries"]["decision_reopened_path"] is False
            print(json.dumps({"fixture_inputs": positive["identity"],
                              "manifest_sha256": positive["manifest_sha256"],
                              "observation": OBSERVATION, "code_present": positive["code_present"],
                              "activation": positive["activation"]}, ensure_ascii=True))

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
            assert disabled["device_runner_calls"] == 0
            _, unknown = check("missing activation flag conservatively retains WiFi scope", want=0,
                               fixture_args="-v applog=1")
            check("duplicate conflicting requested args", fixture_args="-v applog=1 pong_wifi=0 pong_wifi=1",
                  needle="duplicate/conflicting requested args")
            assert unknown["activation"] == "unknown" and unknown["code_present"]

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
            def stale_manifest(f):
                f.manifest["tag"] = "wifi-looking-tag-does-not-authorize"
                f.put("build-manifest.json", wrapper.canonical(f.manifest))
            check("review pins entire manifest", stale_manifest, needle="manifest review hash")
            def bad_review_hash(f):
                f.review["manifest_sha256"] = "0" * 64
                f.save_review()
            check("review manifest hash mismatch", bad_review_hash, needle="manifest review hash mismatch")
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
            def stale_prediction(f):
                f.hardware["wifi"]["step"]["device"]["prediction"]["observation"] = "old-observation"
                f.refresh()
            check("stale prediction reference fails advisory checks", stale_prediction,
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

            # ---- default library entry point has no runner seam ----
            execute_fixture = Fixture(root / "case-execute-default")
            execute_ok = wrapper.execute(execute_fixture.root / "build-manifest.json",
                                         execute_fixture.root / "fixture-image.json",
                                         execute_fixture.root / "review.json", "wifi")
            rejected = False
            rejected_fake = wrapper.RecordedFakeRunner()
            try:
                wrapper.execute(execute_fixture.root / "build-manifest.json",
                                execute_fixture.root / "fixture-image.json",
                                execute_fixture.root / "review.json", "wifi", rejected_fake)
            except wrapper.Refused:
                rejected = True
            row("execute(runner=None) advisory-only; arbitrary runner refused before call",
                execute_ok["advisory_exit_code"] == 0 and execute_ok["device_runner_calls"] == 0 and
                execute_ok["advisory"] is True and rejected and rejected_fake.calls == [],
                execute_ok, {"rejected": rejected, "fake_calls": len(rejected_fake.calls)})

            # ---- captured-byte boundaries: default path, zero device runner ----
            def boundary(label, ok, detail):
                row(label, ok, None, detail)
                diagnostics.append({"case": label, "pass": bool(ok), "detail": detail})

            path_fixture = Fixture(root / "case-path-replacement")
            captured = path_fixture.capture()
            path_fixture.put("fixture-image.json", b"replacement image bytes after capture")
            after = wrapper.advisory_from_inputs(captured, "wifi")
            drift = after["boundaries"]["path_drift"]["image"]
            boundary("path replacement: captured bytes still evaluated, path drift reported",
                     after["advisory_exit_code"] == 0 and after["device_runner_calls"] == 0 and
                     after["flash_authorized"] is False and drift["same"] is False and
                     captured.image.sha256 == after["identity"]["image_sha256"],
                     {"captured_sha256": captured.image.sha256,
                      "path_now_sha256": drift["path_now_sha256"], "same": drift["same"]})

            inode_fixture = Fixture(root / "case-inode-mutation")
            captured = inode_fixture.capture()
            image_path = inode_fixture.root / "fixture-image.json"
            inode_before = os.stat(image_path).st_ino
            original = image_path.read_bytes()
            with image_path.open("r+b") as stream:
                stream.seek(0)
                stream.write(bytes([original[0] ^ 1]) + original[1:])
                stream.flush()
            inode_after = os.stat(image_path).st_ino
            after = wrapper.advisory_from_inputs(captured, "wifi")
            drift = after["boundaries"]["path_drift"]["image"]
            boundary("same-inode in-place write: captured bytes unchanged, path bytes drift",
                     inode_before == inode_after and after["advisory_exit_code"] == 0 and
                     after["device_runner_calls"] == 0 and drift["same"] is False,
                     {"same_inode": inode_before == inode_after,
                      "captured_sha256": captured.image.sha256,
                      "path_now_sha256": drift["path_now_sha256"], "same": drift["same"]})

            bad_fixture = Fixture(root / "case-restored-race")
            bad_fixture.hardware["wifi"]["step"]["device"]["prediction"]["observation"] = "old-observation"
            bad_fixture.refresh()
            captured_bad = bad_fixture.capture()
            bad_result = wrapper.advisory_from_inputs(captured_bad, "wifi")
            bad_fixture.hardware["wifi"]["step"]["device"]["prediction"]["observation"] = OBSERVATION
            bad_fixture.refresh()
            repaired_path = bad_fixture.run()
            boundary("restored race: captured bad evidence stays failed after path repaired",
                     bad_result["advisory_exit_code"] == 1 and
                     bad_result["device_runner_calls"] == 0 and
                     repaired_path["advisory_exit_code"] == 0,
                     {"captured_bad_exit": bad_result["advisory_exit_code"],
                      "repaired_path_exit": repaired_path["advisory_exit_code"],
                      "captured_bad_error": bad_result["error"]})

            downstream_fixture = Fixture(root / "case-downstream-reopen")
            captured = downstream_fixture.capture()
            downstream_fixture.put("fixture-image.json", b"downstream consumer would read this")
            now = wrapper.diagnostic_path_digest(downstream_fixture.root / "fixture-image.json")
            boundary("downstream path reopen: diagnostic digest differs from captured digest",
                     now != captured.image.sha256,
                     {"captured_sha256": captured.image.sha256, "reopened_sha256": now,
                      "boundary": "downstream reopen is outside this wrapper's proof"})

            # ---- explicit isolated legacy defect regression: exactly one fake call ----
            legacy_fixture = Fixture(root / "case-legacy-defect")
            legacy_image = legacy_fixture.root / "fixture-image.json"
            good_image = legacy_image.read_bytes()
            bad_image = b'{"format":"legacy-bad-image-after-window"}'
            legacy_fixture.put("fixture-image.json", bad_image)
            def open_window():
                legacy_fixture.put("fixture-image.json", good_image)
            def close_window():
                legacy_fixture.put("fixture-image.json", bad_image)
            legacy = wrapper.legacy_vulnerable_probe(
                legacy_fixture.root / "build-manifest.json",
                legacy_fixture.root / "fixture-image.json",
                legacy_fixture.root / "review.json", "wifi",
                window_open=open_window, window_close=close_window)
            legacy_ok = (legacy["legacy_fake_accepted"] is True and legacy["runner_calls"] == 1 and
                         legacy["device_runner_calls"] == 0 and legacy["flash_authorized"] is False and
                         legacy["path_matches_validated"] is False)
            row("legacy-vulnerable probe: expected once-fake acceptance after temp-good window",
                legacy_ok, legacy, {"expected_defect": True})
            if legacy_ok:
                diagnostics.append({"case": "legacy-vulnerable probe accepted once",
                                    "pass": True, "expected_defect": True})
            else:
                # The regression is only useful if the defect is still reproduced.
                failures.append("legacy-vulnerable probe did not reproduce the defect")

            # The default API must not spawn a device/gate consumer; the CLI child is
            # asserted zero-runner in its own process below.
            subprocess.run = real_run
            cli_fixture = Fixture(root / "case-cli")
            cli = subprocess.run([sys.executable, "-I", "-X", "utf8", str(WRAPPER), "--manifest",
                                  str(cli_fixture.root / "build-manifest.json"), "--image",
                                  str(cli_fixture.root / "fixture-image.json"), "--review",
                                  str(cli_fixture.root / "review.json"), "--scope", "wifi"],
                                 cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30)
            cli_result = json.loads(cli.stdout)
            row("CLI advisory-only positive: zero device runner, no authorization",
                cli.returncode == 0 and cli_result["mode"] == "advisory-only" and
                cli_result["advisory_exit_code"] == 0 and cli_result["device_runner_calls"] == 0 and
                cli_result["flash_authorized"] is False,
                cli_result, {"raw_cli_exit": cli.returncode})

            if args.c8_manifest:
                command = [sys.executable, "-I", "-X", "utf8", str(WRAPPER), "--manifest", args.c8_manifest,
                           "--image", args.c8_image, "--scope", "wifi"]
                c8 = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                    encoding="utf-8", timeout=30)
                c8_result = json.loads(c8.stdout)
                ok = (c8.returncode == 1 and c8_result["advisory_exit_code"] == 1 and
                      c8_result["device_runner_calls"] == 0 and
                      c8_result["flash_authorized"] is False and
                      "missing historical proposal_binding" in c8_result["error"])
                row("real c8 read-only rejection: missing binding, zero runner", ok, c8_result,
                    {"command": command, "raw_cli_exit": c8.returncode})
    finally:
        subprocess.run = real_run
    unchanged = before == {str(path): wrapper.file_digest(path)
                           for path in (wrapper.GATE, DATA, wrapper.PATCH, wrapper.SUPERVISOR)}
    if not unchanged:
        failures.append("active inputs changed")
    print(json.dumps({"cases": len(results) + 2 + bool(args.c8_manifest) + len(diagnostics),
                      "failures": failures,
                      "diagnostics": len(diagnostics),
                      "active_inputs_unchanged": unchanged,
                      "fixed_subprocess_calls": len(commands),
                      "source_revision": REVISION, "source_path": SOURCE},
                     ensure_ascii=True))
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
