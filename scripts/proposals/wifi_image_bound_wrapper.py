#!/usr/bin/env python3
"""Offline image-binding proposal. No real supervisor/device execution is possible.

Only nonbootable wifi-source-fixture-v1 containers are admitted. A future production
adapter needs independently reviewed build-time provenance and actual image readback;
this fixture format is not that attestation and cannot rehabilitate historical c8.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts/eight-step-gate.py"
PATCH = ROOT / "scripts/proposals/wifi-eight-step-gate.patch"
DATA = ROOT / "docs/research/EIGHT-STEPS.toml"
SUPERVISOR = ROOT / "scripts/boot-and-capture.ps1"
GIT = "C:/Program Files/Git/cmd/git.exe" if os.name == "nt" else "/usr/bin/git"
SOURCE = "drivers/PongWifi/PongWifiPci.cpp"
FORMAT = "wifi-source-fixture-v1"
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
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            value.update(chunk)
    return value.hexdigest()


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


def supervisor_plan():
    # Inert representation only. Deliberately invalid device serial and nonbootable
    # image make this a fixture plan. No code executes or resolves these arguments.
    return {"script": "scripts/boot-and-capture.ps1",
            "script_sha256": file_digest(SUPERVISOR), "executable": False,
            "argv": ["-Image", "fixture-image.json", "-Seconds", "300",
                     "-WaitFastboot", "0", "-OutDir", "fixture-evidence",
                     "-Serial", "fixture-no-device"]}


def sha(value, label):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value),
            label + " requires a full lowercase SHA256")
    return value


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


def frozen_inputs(manifest_path, manifest, binding):
    root = manifest_path.parent.resolve()
    frozen = manifest.get("frozen") or {}
    listing = local_file(root, frozen.get("file"))
    require(file_digest(listing) == sha(frozen.get("list_sha256"), "frozen.list_sha256"),
            "frozen list hash mismatch")
    entries = {}
    for line in listing.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        require(match is not None, "malformed frozen entry: " + line)
        value, name = match.groups()
        require(name not in entries, "duplicate frozen entry: " + name)
        path = local_file(root, name)
        require(file_digest(path) == value, "frozen file hash mismatch: " + name)
        entries[name] = (path, value)
    roles = binding.get("files") or {}
    require(set(roles) == ROLES, "historical binding missing/unknown roles: " +
            repr(sorted(ROLES.symmetric_difference(roles))))
    require(len(set(roles.values())) == len(ROLES), "frozen roles must name distinct files")
    require(set(roles.values()).issubset(entries), "binding file absent from frozen list")
    return {role: entries[name] for role, name in roles.items()}


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


def proposed_gate(steps, scope, observation):
    # Fixed trusted repository code only; no executable/runner can be supplied by input.
    with tempfile.TemporaryDirectory(prefix="wifi-image-gate-") as directory:
        tree = Path(directory)
        (tree / "scripts").mkdir()
        (tree / "docs/research").mkdir(parents=True)
        shutil.copyfile(GATE, tree / "scripts/eight-step-gate.py")
        for options in (("--check",), ()):
            done = subprocess.run([GIT, "apply", *options, str(PATCH)], cwd=tree, env=clean_env(),
                                  capture_output=True, text=True, encoding="utf-8", timeout=20)
            require(done.returncode == 0, "proposed gate patch rc=" + str(done.returncode) +
                    ": " + done.stdout + done.stderr)
        # Only the unrelated renderer invocation changes for isolated Windows Python;
        # flash selection, evidence, prediction and active-floor code remain verbatim.
        gate_path = tree / "scripts/eight-step-gate.py"
        gate_text = gate_path.read_text(encoding="utf-8")
        old = "['python3', os.path.join(REPO, 'scripts', 'render-eight-step-table.py')"
        require(gate_text.count(old) == 1, "unknown renderer invocation")
        gate_path.write_text(gate_text.replace(old,
            "[sys.executable, '-I', '-X', 'utf8', os.path.join(REPO, 'scripts', 'render-eight-step-table.py')"),
            encoding="utf-8")
        shutil.copyfile(steps, tree / "docs/research/EIGHT-STEPS.toml")
        # Unrelated renderer only; selection/evidence/prediction logic is the real patch.
        (tree / "scripts/render-eight-step-table.py").write_text(
            "raise SystemExit(0)\n", encoding="utf-8")
        # The gate's env transport is derived exclusively from checked input. Ambient
        # Python injection, K60 scopes, identity/archive hints and skip flags are dropped.
        env = clean_env()
        env.update(PYTHONIOENCODING="utf-8", K60_FLASH_ITEMS=scope,
                   K60_FLASH_OBSERVATION=observation)
        done = subprocess.run([sys.executable, "-I", "-X", "utf8", str(tree / "scripts/eight-step-gate.py"),
                               "--flash"], cwd=tree, env=env, capture_output=True,
                              text=True, encoding="utf-8", timeout=20)
        return {"exit_code": done.returncode, "stdout": done.stdout, "stderr": done.stderr}


class RecordedFakeRunner:
    """In-process recorder only: no subprocess, callback, command, or device API."""
    def __init__(self, exit_code=0):
        self.exit_code = exit_code
        self.calls = []

    def run(self, plan):
        self.calls.append(plan)
        return self.exit_code


def validate(manifest_path, image_path, review_path, scope):
    manifest_path, image_path = Path(manifest_path).resolve(), Path(image_path).resolve()
    raw_manifest = manifest_path.read_bytes()
    manifest = parse(raw_manifest)
    comp = manifest.get("components") or {}
    image_hash = file_digest(image_path)
    require(image_hash == sha(comp.get("boot_img"), "components.boot_img"),
            "outer image hash mismatch")
    revision = (manifest.get("repo") or {}).get("head")
    require(isinstance(revision, str) and re.fullmatch(r"[0-9a-f]{40}", revision),
            "repo.head requires a full 40-character revision")
    require(type((manifest.get("repo") or {}).get("dirty_files")) is int and
            manifest["repo"]["dirty_files"] == 0, "manifest source tree is not clean")
    # c8 has no such historical record. Do not create/default it from current env/files.
    binding = manifest.get("proposal_binding")
    require(isinstance(binding, dict), "missing historical proposal_binding; no backfill allowed")
    require(type(binding.get("schema_version")) is int and binding["schema_version"] == 1 and
            binding.get("format") == FORMAT,
            "unsupported binding format; offline source fixture only")
    require(review_path is not None, "missing reviewed identity input")
    review = parse(Path(review_path).read_bytes())
    require(review.get("purpose") == "offline-fixture-only", "review is not fixture-only")
    require(review.get("manifest_sha256") == digest(raw_manifest), "manifest review hash mismatch")
    require(review.get("source_revision") == revision, "review revision mismatch")
    require(review.get("gate_base_sha256") == file_digest(GATE), "gate base revision/hash mismatch")
    require(review.get("gate_patch_sha256") == file_digest(PATCH), "gate patch hash mismatch")
    require(review.get("active_floor_sha256") == file_digest(DATA), "active floor hash mismatch")
    plan = supervisor_plan()
    require(review.get("supervisor") == plan and binding.get("supervisor") == plan,
            "supervisor script/parameter plan mismatch")
    require(comp.get("boot_img_path") == "fixture-image.json" and image_path.name == "fixture-image.json",
            "fixture image path does not match supervisor plan")
    files = frozen_inputs(manifest_path, manifest, binding)
    observation = parse(files["observation"][0].read_bytes())
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
    # Known targets come from the checked TOML, not a hardcoded tag/name list.
    import tomllib
    hardware = (tomllib.loads(files["steps"][0].read_text(encoding="utf-8")).get("hardware") or {})
    require(isinstance(hardware, dict) and all(isinstance(value, dict) for value in hardware.values()),
            "malformed hardware records")
    trusted = tomllib.loads(DATA.read_text(encoding="utf-8"))["hardware"]
    active = {key for key, value in trusted.items() if value.get("status", "active") == "active"}
    require(active.issubset(hardware) and all(hardware[key].get("status", "active") == "active"
            for key in active), "trusted active floor omitted or demoted")
    require(set(hardware).issubset(trusted), "unknown target in artifact hardware records")
    require(set(names).issubset(hardware), "unknown target in explicit scope")

    image = parse(image_path.read_bytes())
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

    source = files["source"][0].read_bytes()
    kind = subprocess.run([GIT, "-c", "safe.directory=" + str(ROOT),
                           "--no-replace-objects", "cat-file", "-t", revision],
                          cwd=ROOT, env=clean_env(), capture_output=True, timeout=20)
    require(kind.returncode == 0 and kind.stdout.strip() == b"commit",
            "source revision must name an existing commit object")
    git = subprocess.run([GIT, "-c", "safe.directory=" + str(ROOT), "--no-replace-objects",
                          "cat-file", "blob", revision + ":" + SOURCE], cwd=ROOT,
                         env=clean_env(),
                         capture_output=True, timeout=20)
    require(git.returncode == 0 and git.stdout == source, "source snapshot/revision mismatch")
    require(b"PongWifiPciRead(" in source and source in kernel,
            "WiFi source bytes absent from fixture kernel")
    archive = files["archive"][0].read_bytes()
    require(files["archive"][1] == sha(comp.get("wifi_archive"), "components.wifi_archive"),
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
    config = files["config"][0].read_text(encoding="utf-8").splitlines()
    config_values = [line for line in config if line.startswith("CONFIG_XNU_PONG_WIFI=")]
    require(len(config_values) == 1 and config_values[0] in
            ("CONFIG_XNU_PONG_WIFI=y", "CONFIG_XNU_PONG_WIFI=n"), "unknown WiFi build config")
    compile_record = parse(files["compile_commands"][0].read_bytes())
    require(compile_record == {"format": "source-fixture-no-compiler", "source": SOURCE,
            "source_revision": revision, "source_sha256": digest(source)},
            "compile record/revision/source mismatch")
    link_record = parse(files["link_record"][0].read_bytes())
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
                "config_sha256": files["config"][1],
                "compile_commands_sha256": files["compile_commands"][1],
                "link_record_sha256": files["link_record"][1],
                "steps_sha256": files["steps"][1], "gate_base_sha256": file_digest(GATE),
                "gate_patch_sha256": file_digest(PATCH),
                "active_floor_sha256": file_digest(DATA), "supervisor": plan}
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
    require(prediction.get("success") == observation["success"] and
            prediction.get("failure") == observation["failure"], "gate prediction/spec mismatch")
    return {"identity": identity, "observation": obs_id, "scope": names,
            "code_present": True, "activation": state, "steps": files["steps"][0],
            "image": str(image_path), "manifest_sha256": digest(raw_manifest),
            "supervisor_plan": plan}


def execute(manifest_path, image_path, review_path=None, scope=None, runner=None):
    # Exact class disallows a passed real runner/callback. CLI constructs this itself.
    runner = RecordedFakeRunner() if runner is None else runner
    result = {"exit_code": 1, "runner_calls": 0, "gate": None, "error": None}
    try:
        require(type(runner) is RecordedFakeRunner, "only the recorded in-process fake is supported")
        checked = validate(manifest_path, image_path, review_path, scope)
        gate = proposed_gate(checked.pop("steps"), scope, checked["observation"])
        result["gate"] = gate
        require(gate["exit_code"] == 0, "proposed flash gate refused rc=" + str(gate["exit_code"]))
        # Detect replacement during validation/gate before the fake boundary.
        require(file_digest(image_path) == checked["identity"]["image_sha256"],
                "image changed after gate")
        require(file_digest(manifest_path) == checked["manifest_sha256"],
                "manifest changed after gate")
        # Recheck all frozen evidence/review/script identities after the gate; comparison
        # intentionally excludes temporary gate output. This remains an offline recorder,
        # not an atomic device execution protocol.
        repeated = validate(manifest_path, image_path, review_path, scope)
        repeated.pop("steps")
        require(repeated == checked, "bound inputs changed during gate")
        result.update(checked)
        result["exit_code"] = runner.run({"kind": "recorded-fake-only", **checked})
    except (ValueError, OSError, KeyError, TypeError, AttributeError, subprocess.SubprocessError) as error:
        result["error"] = str(error)
    if type(runner) is RecordedFakeRunner:
        result["runner_calls"] = len(runner.calls)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--review")
    parser.add_argument("--scope")
    args = parser.parse_args()
    result = execute(args.manifest, args.image, args.review, args.scope)
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
