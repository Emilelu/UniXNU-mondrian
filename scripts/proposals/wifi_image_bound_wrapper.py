#!/usr/bin/env python3
"""Offline advisory-only image-binding diagnostics. No device path is executable.

The default API captures each checked input once as immutable bytes, then hashes,
parses and compares those captured bytes. It never invokes the supervisor,
fastboot, PowerShell, a shell or a configurable command, never calls a device
runner, and never reports flash authorization. Paths are display locators only.
A path replacement, an in-place write to the same inode, and a downstream tool
that reopens a path are reported as boundaries; they cannot be repaired by a
second path validation because no second path validation is used for a decision.

legacy_vulnerable_probe() is a deliberately isolated reproduction of the known
historical path-bound defect. It reaches only the exact in-process recorder and
exists to keep the once-fake-runner-call failure visible. It is never an
acceptance path and never reports authorization.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts/eight-step-gate.py"
PATCH = ROOT / "scripts/proposals/wifi-eight-step-gate.patch"
DATA = ROOT / "docs/research/EIGHT-STEPS.toml"
SUPERVISOR = ROOT / "scripts/boot-and-capture.ps1"
GIT = "C:/Program Files/Git/cmd/git.exe" if os.name == "nt" else "/usr/bin/git"
SOURCE = "drivers/PongWifi/PongWifiPci.cpp"
FORMAT = "wifi-source-fixture-v1"
MODE = "advisory-only"
ROLES = {"source", "config", "archive", "compile_commands", "link_record",
         "observation", "steps"}


class Refused(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Refused(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_digest(path):
    with open(path, "rb") as stream:
        return digest(stream.read())


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key: " + key)
        result[key] = value
    return result


def parse(data):
    result = json.loads(data, object_pairs_hook=unique_object)
    require(isinstance(result, dict), "JSON root must be an object")
    return result


def clean_env():
    # No GIT_*, Python injection, PATH/HOME config, K60 identity or scope hints.
    keep = {"SYSTEMROOT", "WINDIR", "TEMP", "TMP"}
    env = {key: value for key, value in os.environ.items() if key.upper() in keep}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    return env


def sha(value, label):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value),
            label + " requires a full lowercase SHA256")
    return value


@dataclass(frozen=True)
class Snapshot:
    """One open-and-read capture. data is the only content used after capture."""
    data: bytes
    sha256: str
    locator: str
    label: str

    def report(self):
        return {"sha256": self.sha256, "bytes": len(self.data),
                "locator": self.locator, "locator_is_display_only": True}


@dataclass(frozen=True)
class Captured:
    """All decision inputs, captured once from their sources before any check."""
    manifest: Snapshot
    image: Snapshot
    review: Snapshot
    frozen_list: Snapshot
    files: dict
    gate: Snapshot
    patch: Snapshot
    floor: Snapshot
    supervisor: Snapshot
    source_blob: object
    source_error: object


def capture(path, label):
    """Open once, read once. No path hash is taken before or after this read."""
    try:
        with Path(path).open("rb") as stream:
            data = stream.read()
    except OSError as error:
        raise Refused("cannot capture " + label + ": " + str(error)) from error
    return Snapshot(data=data, sha256=digest(data), locator=str(path), label=label)


def verify_snapshot(snapshot, label):
    require(isinstance(snapshot, Snapshot), label + " snapshot missing")
    require(digest(snapshot.data) == snapshot.sha256, label + " snapshot digest mismatch")


def local_file(root, name):
    require(isinstance(name, str) and name and "\\" not in name,
            "invalid frozen relative path: " + repr(name))
    relative = Path(name)
    require(not relative.is_absolute() and ":" not in name and ".." not in relative.parts,
            "frozen path must stay inside the artifact directory: " + name)
    current = root
    for part in relative.parts:
        current = current / part
        require(not current.is_symlink(), "symlink in frozen path: " + name)
    path = current.resolve()
    require(path.is_relative_to(root) and path.is_file(), "frozen file missing: " + name)
    return path


def parse_frozen_listing(data):
    entries = {}
    for line in data.decode("utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        require(match is not None, "malformed frozen entry: " + line)
        value, name = match.groups()
        require(name not in entries, "duplicate frozen entry: " + name)
        entries[name] = value
    return entries


def capture_frozen(root, listing, manifest):
    frozen = manifest.get("frozen") or {}
    require(listing.sha256 == sha(frozen.get("list_sha256"), "frozen.list_sha256"),
            "frozen list hash mismatch")
    entries = parse_frozen_listing(listing.data)
    captured = {}
    for name in entries:
        snapshot = capture(local_file(root, name), "frozen " + name)
        require(snapshot.sha256 == entries[name], "frozen file hash mismatch: " + name)
        captured[name] = snapshot
    return captured


def role_files(captured, manifest):
    listing = parse_frozen_listing(captured.frozen_list.data)
    require(captured.frozen_list.sha256 ==
            sha((manifest.get("frozen") or {}).get("list_sha256"), "frozen.list_sha256"),
            "frozen list hash mismatch")
    binding = manifest.get("proposal_binding") or {}
    roles = binding.get("files") or {}
    require(set(roles) == ROLES, "historical binding missing/unknown roles: " +
            repr(sorted(ROLES.symmetric_difference(roles))))
    require(len(set(roles.values())) == len(ROLES), "frozen roles must name distinct files")
    require(set(roles.values()).issubset(listing), "binding file absent from frozen list")
    require(set(captured.files) == set(listing), "captured frozen set differs from listing")
    result = {}
    for role, name in roles.items():
        snapshot = captured.files.get(name)
        require(snapshot is not None, "frozen file missing: " + name)
        require(snapshot.sha256 == listing[name], "frozen file hash mismatch: " + name)
        result[role] = snapshot
    return result


def supervisor_plan(supervisor=None):
    # Inert representation only. Deliberately invalid device serial and nonbootable
    # image make this a fixture plan. No code executes or resolves these arguments.
    snapshot = supervisor if supervisor is not None else capture(SUPERVISOR, "supervisor script")
    return {"script": "scripts/boot-and-capture.ps1",
            "script_sha256": snapshot.sha256, "executable": False,
            "argv": ["-Image", "fixture-image.json", "-Seconds", "300",
                     "-WaitFastboot", "0", "-OutDir", "fixture-evidence",
                     "-Serial", "fixture-no-device"]}


def try_capture_source(revision):
    """Capture the source Git object as bytes. A missing/invalid object is reported later."""
    if not isinstance(revision, str) or re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        return None, "source revision must be a full 40-character commit"
    kind = subprocess.run([GIT, "-c", "safe.directory=" + str(ROOT),
                           "--no-replace-objects", "cat-file", "-t", revision],
                          cwd=ROOT, env=clean_env(), capture_output=True, timeout=20)
    if kind.returncode != 0 or kind.stdout.strip() != b"commit":
        return None, "source revision must name an existing commit object"
    blob = subprocess.run([GIT, "-c", "safe.directory=" + str(ROOT), "--no-replace-objects",
                           "cat-file", "blob", revision + ":" + SOURCE], cwd=ROOT,
                          env=clean_env(), capture_output=True, timeout=20)
    if blob.returncode != 0:
        return None, "source blob unavailable for the checked revision"
    return Snapshot(data=blob.stdout, sha256=digest(blob.stdout),
                    locator=revision + ":" + SOURCE, label="source blob"), None


def capture_inputs(manifest_path, image_path, review_path=None):
    """Capture every decision input once. No path is reopened for a decision later."""
    manifest_path, image_path = Path(manifest_path).resolve(), Path(image_path).resolve()
    manifest_snapshot = capture(manifest_path, "manifest")
    manifest = parse(manifest_snapshot.data)
    binding = manifest.get("proposal_binding")
    # c8 has no such historical record. Do not create/default it from current env/files.
    require(isinstance(binding, dict), "missing historical proposal_binding; no backfill allowed")
    require(review_path is not None, "missing reviewed identity input")
    review_snapshot = capture(Path(review_path).resolve(), "review")
    root = manifest_path.parent
    frozen = manifest.get("frozen") or {}
    frozen_snapshot = capture(local_file(root, frozen.get("file")), "frozen list")
    files = capture_frozen(root, frozen_snapshot, manifest)
    image_snapshot = capture(image_path, "image")
    gate_snapshot = capture(GATE, "trusted gate")
    patch_snapshot = capture(PATCH, "unapplied gate patch")
    floor_snapshot = capture(DATA, "trusted active floor")
    supervisor_snapshot = capture(SUPERVISOR, "supervisor script")
    revision = (manifest.get("repo") or {}).get("head")
    source_blob, source_error = try_capture_source(revision)
    return Captured(manifest=manifest_snapshot, image=image_snapshot,
                    review=review_snapshot, frozen_list=frozen_snapshot, files=files,
                    gate=gate_snapshot, patch=patch_snapshot, floor=floor_snapshot,
                    supervisor=supervisor_snapshot, source_blob=source_blob,
                    source_error=source_error)


def activation(args):
    require(isinstance(args, str), "payload_args must be a string")
    tokens = args.split()
    values = [token.split("=", 1)[1] for token in tokens if token.startswith("pong_wifi=")]
    # Duplicate or unfamiliar values are ambiguous, even if the final token is zero.
    if values == ["1"]:
        return "enabled"
    if values == ["0"]:
        return "disabled"
    return "unknown"


def evaluate(captured, scope):
    """Evaluate only captured bytes. Never opens an input path for a decision."""
    for snapshot, label in (("manifest", "manifest"), ("image", "image"),
                            ("review", "review"), ("frozen_list", "frozen list"),
                            ("gate", "trusted gate"), ("patch", "unapplied gate patch"),
                            ("floor", "trusted active floor"),
                            ("supervisor", "supervisor script")):
        verify_snapshot(getattr(captured, snapshot), label)
    for name, snapshot in captured.files.items():
        verify_snapshot(snapshot, "frozen " + name)

    raw_manifest = captured.manifest.data
    manifest = parse(raw_manifest)
    comp = manifest.get("components")
    require(isinstance(comp, dict), "manifest components must be an object")
    image_hash = captured.image.sha256
    require(image_hash == sha(comp.get("boot_img"), "components.boot_img"),
            "outer image hash mismatch")
    revision = (manifest.get("repo") or {}).get("head")
    require(isinstance(revision, str) and re.fullmatch(r"[0-9a-f]{40}", revision),
            "repo.head requires a full 40-character revision")
    require(type((manifest.get("repo") or {}).get("dirty_files")) is int and
            manifest["repo"]["dirty_files"] == 0, "manifest source tree is not clean")
    binding = manifest.get("proposal_binding")
    require(isinstance(binding, dict), "missing historical proposal_binding; no backfill allowed")
    require(type(binding.get("schema_version")) is int and binding["schema_version"] == 1 and
            binding.get("format") == FORMAT,
            "unsupported binding format; offline source fixture only")

    review = parse(captured.review.data)
    require(review.get("purpose") == "offline-fixture-only", "review is not fixture-only")
    require(review.get("manifest_sha256") == captured.manifest.sha256, "manifest review hash mismatch")
    require(review.get("source_revision") == revision, "review revision mismatch")
    require(review.get("gate_base_sha256") == captured.gate.sha256,
            "gate base revision/hash mismatch")
    require(review.get("gate_patch_sha256") == captured.patch.sha256, "gate patch hash mismatch")
    require(review.get("active_floor_sha256") == captured.floor.sha256,
            "active floor hash mismatch")
    plan = supervisor_plan(captured.supervisor)
    require(review.get("supervisor") == plan and binding.get("supervisor") == plan,
            "supervisor script/parameter plan mismatch")
    require(comp.get("boot_img_path") == "fixture-image.json" and
            Path(captured.image.locator).name == "fixture-image.json",
            "fixture image path does not match supervisor plan")

    files = role_files(captured, manifest)
    observation = parse(files["observation"].data)
    obs_id = observation.get("id")
    require(isinstance(obs_id, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", obs_id),
            "missing/invalid observation identifier")
    require(review.get("observation") == obs_id, "review observation mismatch")
    require(observation.get("format") == "wifi-observation-fixture-v1",
            "observation binding is missing or unknown")
    require(isinstance(scope, str) and scope.strip(), "missing explicit scope")
    names = scope.split(",")
    require(all(name and name == name.strip() for name in names) and len(names) == len(set(names)),
            "empty/duplicate/noncanonical explicit scope")
    # Known targets come from the captured TOML, not a hardcoded tag/name list.
    hardware = (tomllib.loads(files["steps"].data.decode("utf-8")).get("hardware") or {})
    require(isinstance(hardware, dict) and all(isinstance(value, dict) for value in hardware.values()),
            "malformed hardware records")
    trusted = tomllib.loads(captured.floor.data.decode("utf-8"))["hardware"]
    active = {key for key, value in trusted.items() if value.get("status", "active") == "active"}
    require(active.issubset(hardware) and all(hardware[key].get("status", "active") == "active"
            for key in active), "trusted active floor omitted or demoted")
    require(set(hardware).issubset(trusted), "unknown target in artifact hardware records")
    require(set(names).issubset(hardware), "unknown target in explicit scope")

    image = parse(captured.image.data)
    require(image.get("format") == FORMAT, "unsupported image; no real boot image adapter")
    payload = image.get("payload")
    require(isinstance(payload, dict), "missing fixture payload readback")
    require(digest(canonical(payload)) == sha(comp.get("payload"), "components.payload"),
            "payload readback hash mismatch")
    kernel = base64.b64decode(payload.get("kernel_base64", ""), validate=True)
    require(digest(kernel) == sha(comp.get("payload_kernel"), "components.payload_kernel"),
            "payload kernel readback hash mismatch")
    require(payload.get("args") == manifest.get("payload_args"), "payload args readback mismatch")
    requested = manifest.get("kernel_args_requested")
    require(isinstance(requested, list) and all(isinstance(item, str) and item and
            len(item.split()) == 1 for item in requested), "invalid kernel_args_requested")
    keys = [item.split("=", 1)[0] for item in requested]
    require(len(keys) == len(set(keys)), "duplicate/conflicting requested args")
    require(all(item in payload["args"].split() for item in requested),
            "requested args missing from payload readback")
    require(image.get("source_revision") == revision, "image revision mismatch")

    source = files["source"].data
    require(captured.source_blob is not None,
            captured.source_error or "source revision must name an existing commit object")
    verify_snapshot(captured.source_blob, "source blob")
    require(captured.source_blob.data == source, "source snapshot/revision mismatch")
    require(b"PongWifiPciRead(" in source and source in kernel,
            "WiFi source bytes absent from fixture kernel")
    archive = files["archive"].data
    require(files["archive"].sha256 == sha(comp.get("wifi_archive"), "components.wifi_archive"),
            "WiFi archive hash mismatch")
    require(comp.get("wifi_archive_path") == binding["files"]["archive"],
            "WiFi archive path mismatch")
    require(base64.b64decode(image.get("archive_base64", ""), validate=True) == archive,
            "fixture archive readback mismatch")
    archived = parse(archive)
    require(archived.get("format") == "wifi-source-archive-fixture-v1" and
            archived.get("source_sha256") == digest(source) and
            base64.b64decode(archived.get("source_base64", ""), validate=True) == source,
            "archive source membership mismatch")
    config = files["config"].data.decode("utf-8").splitlines()
    config_values = [line for line in config if line.startswith("CONFIG_XNU_PONG_WIFI=")]
    require(len(config_values) == 1 and config_values[0] in
            ("CONFIG_XNU_PONG_WIFI=y", "CONFIG_XNU_PONG_WIFI=n"), "unknown WiFi build config")
    compile_record = parse(files["compile_commands"].data)
    require(compile_record == {"format": "source-fixture-no-compiler", "source": SOURCE,
            "source_revision": revision, "source_sha256": digest(source)},
            "compile record/revision/source mismatch")
    link_record = parse(files["link_record"].data)
    require(link_record == {"format": "source-fixture-no-linker", "archive_sha256": digest(archive),
            "kernel_sha256": digest(kernel), "source_revision": revision},
            "link record/archive/revision mismatch")
    state = activation(payload["args"])
    # Code membership is independent of enable flags. Even disabled/unknown must select
    # WiFi. Unknown other formats fail above; names and eight_step_items prove nothing.
    require("wifi" in names, "WiFi code present requires explicit wifi scope")
    identity = {"image_sha256": image_hash, "source_revision": revision,
                "payload_args": payload["args"], "kernel_args_requested": requested,
                "payload_sha256": comp["payload"], "kernel_sha256": digest(kernel),
                "wifi_archive_sha256": digest(archive), "source_sha256": digest(source),
                "config_sha256": files["config"].sha256,
                "compile_commands_sha256": files["compile_commands"].sha256,
                "link_record_sha256": files["link_record"].sha256,
                "steps_sha256": files["steps"].sha256,
                "gate_base_sha256": captured.gate.sha256,
                "gate_patch_sha256": captured.patch.sha256,
                "active_floor_sha256": captured.floor.sha256,
                "supervisor": plan}
    require(observation.get("identity") == identity, "observation identity mismatch")
    require(observation.get("activation") == state, "observation activation mismatch")
    require(observation.get("scope") == names, "observation scope mismatch")
    require(observation.get("success") and observation.get("failure"),
            "observation success/failure prediction missing")
    wifi_steps = (hardware.get("wifi") or {}).get("step") or {}
    prediction = (wifi_steps.get("device") or {}).get("prediction") or {}
    verify = wifi_steps.get("verify") or {}
    reference = binding["files"]["observation"]
    require(verify.get("reference") == reference and prediction.get("reference") == reference,
            "gate observation reference mismatch")
    require(verify.get("observation") == obs_id, "gate verification observation mismatch")
    require(prediction.get("observation") == obs_id, "gate prediction observation mismatch")
    require(prediction.get("success") == observation["success"] and
            prediction.get("failure") == observation["failure"], "gate prediction/spec mismatch")
    capture_report = {
        "manifest": captured.manifest.report(), "image": captured.image.report(),
        "review": captured.review.report(), "frozen_list": captured.frozen_list.report(),
        "gate": captured.gate.report(), "patch": captured.patch.report(),
        "floor": captured.floor.report(), "supervisor": captured.supervisor.report(),
        "source_blob": captured.source_blob.report() if captured.source_blob else None,
        "frozen_files": {name: snapshot.report()
                         for name, snapshot in sorted(captured.files.items())}}
    return {"identity": identity, "observation": obs_id, "scope": names,
            "code_present": True, "activation": state, "capture": capture_report,
            "image": captured.image.locator, "manifest_sha256": captured.manifest.sha256,
            "supervisor_plan": plan}


def diagnostic_path_digest(path):
    """Diagnostic only: models a downstream consumer reopening a path. Never a decision."""
    return digest(Path(path).read_bytes())


def boundary_report(captured):
    """Post-decision path reads exist only to show what a path consumer would see."""
    drift = {}
    for name, snapshot in (("manifest", captured.manifest), ("image", captured.image),
                           ("review", captured.review), ("frozen_list", captured.frozen_list),
                           ("gate", captured.gate), ("patch", captured.patch),
                           ("floor", captured.floor), ("supervisor", captured.supervisor)):
        try:
            now = diagnostic_path_digest(snapshot.locator)
        except OSError:
            now = None
        drift[name] = {"captured_sha256": snapshot.sha256,
                       "path_now_sha256": now, "same": now == snapshot.sha256}
    return {"captured_once": True, "decision_reopened_path": False,
            "post_capture_path_reads": "diagnostic-only; never consulted by a check",
            "path_drift": drift,
            "same_inode_limit": "an in-place write changes the path's current bytes but "
                                "cannot change a captured snapshot or any advisory decision",
            "downstream_limit": "a final consumer that reopens a path is not bound to the "
                                "captured bytes; this wrapper cannot prove or provide that handoff",
            "cross_process_limit": "supervisor/fastboot atomic handoff is outside this "
                                   "offline proof and is not claimed"}


def base_result():
    return {"mode": MODE, "advisory": True, "diagnostic": True,
            "advisory_exit_code": 1, "checks": "failed",
            "flash_authorized": False, "flash_authorization": "none",
            "device_runner_calls": 0, "device_paths_invoked": False, "error": None}


def advisory_from_inputs(captured, scope):
    result = base_result()
    try:
        result.update(evaluate(captured, scope))
        result["checks"] = "passed"
        result["advisory_exit_code"] = 0
    except (ValueError, OSError, KeyError, TypeError, AttributeError,
            subprocess.SubprocessError) as error:
        result["error"] = str(error)
    result["boundaries"] = boundary_report(captured)
    result["device_runner_calls"] = 0
    result["flash_authorized"] = False
    return result


def advisory(manifest_path, image_path, review_path=None, scope=None):
    """Default API: sole capture, advisory checks, zero device-runner calls."""
    result = base_result()
    try:
        captured = capture_inputs(manifest_path, image_path, review_path)
        result.update(advisory_from_inputs(captured, scope))
    except (ValueError, OSError, KeyError, TypeError, AttributeError,
            subprocess.SubprocessError) as error:
        result["error"] = str(error)
    result["device_runner_calls"] = 0
    result["flash_authorized"] = False
    return result


def execute(manifest_path, image_path, review_path=None, scope=None, runner=None):
    """Compatibility default: no device runner is accepted; runner=None is advisory-only."""
    require(runner is None, "advisory-only execute() has no device runner; "
                            "the isolated legacy probe is a separate explicit API")
    return advisory(manifest_path, image_path, review_path, scope)


class RecordedFakeRunner:
    """Exact legacy in-process recorder: no subprocess, callback, command or device API."""
    def __init__(self, exit_code=0):
        self.exit_code = exit_code
        self.calls = []

    def run(self, plan):
        self.calls.append(plan)
        return self.exit_code


def legacy_vulnerable_probe(manifest_path, image_path, review_path=None, scope=None,
                            window_open=None, during_gate=None, window_close=None):
    """Reproduce the known path-bound once-fake-call defect. Diagnostic, not acceptance.

    The two path validations model the historical before/after-gate checks. window_open
    may expose temporary-good evidence, window_close may restore bad evidence or replace
    the path before the fake boundary. The recorder is reached only through this
    explicit legacy probe; no device runner exists.
    """
    fake = RecordedFakeRunner()
    result = {"kind": "legacy-vulnerable-path-binding-diagnostic",
              "mode": "legacy-diagnostic-only", "advisory": False, "diagnostic": True,
              "flash_authorized": False,
              "flash_authorization": "none", "device_runner_calls": 0,
              "runner_calls": 0, "legacy_fake_accepted": False, "error": None,
              "validated_image_sha256": None, "path_now_sha256": None,
              "path_matches_validated": None}
    try:
        require(type(fake) is RecordedFakeRunner,
                "only the exact in-process legacy recorder is supported")
        if window_open is not None:
            window_open()
        first = evaluate(capture_inputs(manifest_path, image_path, review_path), scope)
        if during_gate is not None:
            during_gate()
        second = evaluate(capture_inputs(manifest_path, image_path, review_path), scope)
        require(second == first, "legacy path validation changed during its window")
        # The historical flow reached the fake with a plan containing a path, not the
        # validated bytes. This is exactly the defect the probe keeps visible.
        if window_close is not None:
            window_close()
        plan = {"kind": "legacy-recorded-fake-only",
                "image_path": str(image_path),
                "validated_image_sha256": first["identity"]["image_sha256"],
                "validated": first}
        result["validated_image_sha256"] = first["identity"]["image_sha256"]
        fake.run(plan)
        result["legacy_fake_accepted"] = True
        result["path_now_sha256"] = diagnostic_path_digest(image_path)
        result["path_matches_validated"] = (
            result["path_now_sha256"] == result["validated_image_sha256"])
    except (ValueError, OSError, KeyError, TypeError, AttributeError,
            subprocess.SubprocessError) as error:
        result["error"] = str(error)
    result["runner_calls"] = len(fake.calls)
    result["device_runner_calls"] = 0
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--review")
    parser.add_argument("--scope")
    parser.add_argument("--legacy-diagnostic", action="store_true",
                        help="run the isolated known-vulnerable fake-only probe")
    args = parser.parse_args()
    if args.legacy_diagnostic:
        result = legacy_vulnerable_probe(args.manifest, args.image, args.review, args.scope)
        print(json.dumps(result, indent=2, ensure_ascii=True))
        return 0 if result["legacy_fake_accepted"] else 1
    result = advisory(args.manifest, args.image, args.review, args.scope)
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return result["advisory_exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
