#!/usr/bin/env python3
"""Host-only tests for the unapplied MHI session proposal; no device I/O.

QUALIFIED is deliberately synthetic. A green test is not protocol authority.
Run: python3 -B scripts/tests/test-wifi-mhi-session-model.py
"""

import errno
import importlib.util
import itertools
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
MODEL_PATH = Path(__file__).resolve().parents[1] / "proposals" / "wifi_mhi_session_model.py"
SPEC = importlib.util.spec_from_file_location("wifi_mhi_session_model", MODEL_PATH)
MODEL = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODEL
SPEC.loader.exec_module(MODEL)
Completion = MODEL.Completion
Contract = MODEL.Contract
SessionModel = MODEL.SessionModel
State = MODEL.State
Token = MODEL.Token
TransferResult = MODEL.TransferResult
QUALIFIED = Contract(True, True, True)


def completed(model, token):
    return TransferResult(0, Completion(token, fresh=True, transfer_complete=True))


def model_with(**kwargs):
    kwargs.setdefault("transport", completed)
    return SessionModel(QUALIFIED, **kwargs)


class AdmissionTests(unittest.TestCase):
    def assert_once(self, model, expected=1):
        self.assertEqual(model.counts["admissions"], expected)
        self.assertEqual(model.counts["bhie_calls"], expected)
        self.assertLessEqual(model.counts["prepare"], 1)
        self.assertLessEqual(model.counts["ready"], 1)

    def test_direct_and_sbl_in_same_local_snapshot(self):
        model = model_with()
        model.post("PBL", direct=True)
        model.post("SBL")
        model.post("PBL", direct=True)
        model.post("READY")
        model.drain()
        self.assert_once(model)
        self.assertEqual(model.state, State.WAIT_MISSION)
        self.assertEqual(model.result(), -errno.EINPROGRESS)

    def test_pump_queues_sbl_without_recursing_running_owner(self):
        nested_dispatch = []

        def transfer(model, token):
            self.assertEqual(model.state, State.IN_FLIGHT)
            self.assertEqual(model.counts["admissions"], 1)
            model.post("SBL")
            model.post("PBL", direct=True)
            model.post("READY")
            nested_dispatch.append(model.run_snapshot())
            return completed(model, token)

        model = model_with(transport=transfer)
        model.post("PBL", direct=True)
        self.assertTrue(model.run_snapshot())
        self.assertEqual(nested_dispatch, [False])
        self.assertEqual(len(model.events), 3)
        model.drain()
        self.assert_once(model)

    def test_cached_ee_is_not_the_once_guard(self):
        model = model_with()
        model.post("PBL", direct=True)
        model.drain()
        model.cached_ee = "PBL"  # simulate a late overwrite of cached EE
        model.post("SBL")
        model.post("DIRECT")
        model.drain()
        self.assert_once(model)

    def test_sbl_first_then_direct_and_duplicates(self):
        model = model_with()
        model.post("PBL")
        model.drain()
        for kind in ("SBL", "DIRECT", "SBL", "PBL", "READY"):
            model.post(kind, direct=True)
        model.drain()
        self.assert_once(model)

    def test_duplicate_pbl_from_prepare_and_ready_callbacks(self):
        def callback(model):
            model.post("PBL", direct=True)
            model.post("READY")
            self.assertFalse(model.run_snapshot())
            return 0

        model = model_with(prepare=callback, ready=callback)
        model.post("PBL", direct=True)
        model.drain()
        self.assert_once(model)
        self.assertEqual(model.counts["prepare"], 1)
        self.assertEqual(model.counts["ready"], 1)

    def test_all_duplicate_orderings_after_prepare_call_transport_once(self):
        for ordering in itertools.permutations(("SBL", "DIRECT", "PBL", "READY")):
            with self.subTest(ordering=ordering):
                model = model_with()
                model.post("PBL")
                model.drain()
                for kind in ordering:
                    model.post(kind, direct=True)
                model.drain()
                self.assert_once(model)

    def test_ready_item_alone_does_not_submit(self):
        model = model_with()
        model.post("READY")
        model.post("PBL")
        model.post("READY")
        model.drain()
        self.assert_once(model, 0)
        self.assertTrue(model.ready_done)

    def test_sbl_before_preparation_fails_without_transport(self):
        model = model_with()
        model.post("SBL")
        model.post("PBL", direct=True)
        model.drain()
        self.assert_once(model, 0)
        self.assertEqual(model.result(), -errno.EPROTO)


class FailureTests(unittest.TestCase):
    def test_prepare_failure_prevents_ready_and_bhie(self):
        model = model_with(prepare=lambda model: -errno.ENOMEM)
        model.post("PBL", direct=True)
        model.post("SBL")
        model.drain()
        self.assertEqual(model.result(), -errno.ENOMEM)
        self.assertEqual(model.error_phase, "prepare")
        self.assertEqual(model.counts["ready"], 0)
        self.assertEqual(model.counts["bhie_calls"], 0)

    def test_ready_failure_prevents_bhie(self):
        model = model_with(ready=lambda model: -errno.ETIMEDOUT)
        model.post("PBL", direct=True)
        model.post("SBL")
        model.post("READY")
        model.drain()
        self.assertEqual(model.result(), -errno.ETIMEDOUT)
        self.assertEqual(model.error_phase, "ready")
        self.assertEqual(model.counts["ready"], 1)
        self.assertEqual(model.counts["bhie_calls"], 0)

    def test_direct_bhie_errors_survive_same_and_next_snapshot(self):
        for error in (-errno.EIO, -errno.ETIMEDOUT, -errno.ENOMEM):
            with self.subTest(error=error):
                def transfer(model, token):
                    model.post("SBL")
                    model.post("MISSION", mission_fresh=True)
                    self.assertFalse(model.run_snapshot())
                    return TransferResult(error)

                model = model_with(transport=transfer)
                model.post("PBL", direct=True)
                model.post("SBL")
                model.post("MISSION", mission_fresh=True)
                model.drain()
                self.assertEqual(model.result(), error)
                self.assertEqual(model.error_phase, "bhie")
                self.assertEqual(model.counts["bhie_calls"], 1)
                self.assertEqual(model.counts["mission"], 0)
                self.assertFalse(model.completion_validated)

    def test_queued_sbl_failure_never_retries(self):
        model = model_with(transport=lambda model, token: TransferResult(-errno.EIO))
        for kind in ("PBL", "SBL", "SBL", "DIRECT", "READY", "PBL"):
            model.post(kind, direct=True if kind == "DIRECT" else False)
        model.drain()
        self.assertEqual(model.result(), -errno.EIO)
        self.assertEqual(model.counts["bhie_calls"], 1)

    def test_failed_transfer_orderings_cannot_publish_mission(self):
        for ordering in itertools.permutations(("SBL", "DIRECT", "READY", "MISSION")):
            model = model_with(transport=lambda model, token: TransferResult(-errno.EIO))
            model.post("PBL", direct=True)
            for kind in ordering:
                model.post(kind, mission_fresh=True)
            model.drain()
            self.assertEqual(model.result(), -errno.EIO)
            self.assertEqual(model.counts["bhie_calls"], 1)
            self.assertEqual(model.counts["mission"], 0)

    def test_transport_exception_is_terminal(self):
        def transfer(model, token):
            raise RuntimeError("synthetic transport failure")
        model = model_with(transport=transfer)
        model.post("PBL", direct=True)
        model.post("SBL")
        model.drain()
        self.assertEqual(model.result(), -errno.EIO)
        self.assertEqual(model.counts["bhie_calls"], 1)

    def test_nested_pump_exception_cannot_run_queued_mission(self):
        def nested_callback(model):
            model.post("SBL")
            model.post("MISSION", mission_fresh=True)
            self.assertFalse(model.run_snapshot())
            raise RuntimeError("synthetic nested callback failure")

        def transport(model, token):
            nested_callback(model)
            return completed(model, token)  # deliberately unreachable

        model = model_with(transport=transport)
        model.post("PBL", direct=True)
        model.post("MISSION", mission_fresh=True)
        model.drain()
        self.assertEqual(model.result(), -errno.EIO)
        self.assertEqual(model.counts["bhie_calls"], 1)
        self.assertEqual(model.counts["mission"], 0)

    def test_nested_failure_publication_wins_over_successful_return(self):
        def transfer(model, token):
            model.post("MISSION", mission_fresh=True)
            model.report_failure(-errno.EIO, generation=model.generation)
            self.assertFalse(model.run_snapshot())
            return completed(model, token)

        model = model_with(transport=transfer)
        model.post("PBL", direct=True)
        model.post("MISSION", mission_fresh=True)
        model.drain()
        self.assertEqual(model.result(), -errno.EIO)
        self.assertEqual(model.counts["bhie_calls"], 1)
        self.assertEqual(model.counts["mission"], 0)
        self.assertFalse(model.completion_validated)

    def test_mission_callback_error_wins_over_cached_ee(self):
        def mission(model):
            model.cached_ee = "AMSS"
            return -errno.EIO
        model = model_with(mission=mission)
        model.post("PBL", direct=True)
        model.post("MISSION", mission_fresh=True)
        model.drain()
        self.assertEqual(model.cached_ee, "AMSS")
        self.assertEqual(model.result(), -errno.EIO)
        self.assertEqual(model.state, State.FAILED)

    def test_outer_deadline_failure_survives_late_ee(self):
        model = model_with()
        model.post("PBL", direct=True)
        model.post("FAIL", error=-errno.ETIMEDOUT)
        model.post("MISSION", mission_fresh=True)
        model.drain()
        self.assertEqual(model.result(), -errno.ETIMEDOUT)
        self.assertEqual(model.counts["mission"], 0)

    def test_power_down_does_not_replace_first_bhie_error(self):
        model = model_with(transport=lambda model, token: TransferResult(-errno.EIO))
        model.post("PBL", direct=True)
        model.drain()
        model.power_down()
        self.assertEqual(model.result(), -errno.EIO)
        self.assertEqual(model.error_phase, "bhie")


class QualificationTests(unittest.TestCase):
    def test_defaults_block_every_submission(self):
        model = SessionModel(transport=completed)
        model.post("PBL", direct=True)
        model.drain()
        self.assertEqual(model.error_phase, "protocol_unqualified")
        self.assertEqual(model.counts["bhie_calls"], 0)

    def test_contract_blockers_are_independent(self):
        cases = ((Contract(False, True, True), "protocol_unqualified"),
                 (Contract(True, False, True), "completion_freshness_unqualified"),
                 (Contract(True, True, False), "direct_path_unqualified"))
        for contract, phase in cases:
            with self.subTest(phase=phase):
                model = SessionModel(contract, transport=completed)
                model.post("PBL", direct=True)
                model.drain()
                self.assertEqual(model.error_phase, phase)
                self.assertEqual(model.counts["bhie_calls"], 0)

    def test_sbl_path_does_not_imply_direct_path_qualified(self):
        model = SessionModel(Contract(True, True, False), transport=completed)
        model.post("PBL")
        model.post("SBL")
        model.drain()
        self.assertEqual(model.state, State.WAIT_MISSION)
        self.assertEqual(model.counts["bhie_calls"], 1)

    def test_stale_unknown_mismatched_or_incomplete_completion_fails(self):
        makers = (
            lambda token: None,
            lambda token: Completion(token, False, True),
            lambda token: Completion(Token(token.generation - 1, 1), True, True),
            lambda token: Completion(Token(token.generation, 2), True, True),
            lambda token: Completion(token, True, False),
        )
        for make in makers:
            model = model_with(transport=lambda model, token: TransferResult(0, make(token)))
            model.post("PBL", direct=True)
            model.post("MISSION", mission_fresh=True)
            model.drain()
            self.assertEqual(model.result(), -errno.EIO)
            self.assertEqual(model.error_phase, "completion_unqualified")
            self.assertEqual(model.counts["bhie_calls"], 1)

    def test_mission_observation_needs_freshness_and_transition_success(self):
        model = model_with()
        model.post("PBL", direct=True)
        model.post("MISSION")
        model.drain()
        self.assertEqual(model.result(), -errno.EIO)
        self.assertEqual(model.error_phase, "mission_unqualified")

    def test_early_mission_does_not_short_circuit_submission(self):
        model = model_with()
        model.post("MISSION", mission_fresh=True)
        model.post("PBL", direct=True)
        model.drain()
        self.assertEqual(model.result(), -errno.EINPROGRESS)
        self.assertEqual(model.counts["bhie_calls"], 1)
        model.post("MISSION", mission_fresh=True)
        model.drain()
        self.assertEqual(model.result(), 0)
        model.post("SBL")
        model.drain()
        self.assertEqual(model.counts["bhie_calls"], 1)
        self.assertEqual(model.cached_ee, "AMSS")


class LifecycleTests(unittest.TestCase):
    def test_shutdown_during_pump_invalidates_return_and_local_queue(self):
        def transfer(model, token):
            model.post("SBL")
            model.power_down()
            with self.assertRaises(RuntimeError):
                model.finish_power_down(quiesced=True)
            with self.assertRaises(RuntimeError):
                model.new_session_after_reset(reset_confirmed=True)
            return completed(model, token)
        model = model_with(transport=transfer)
        model.post("PBL", direct=True)
        model.post("SBL")  # already in local list when cancellation is requested
        model.post("MISSION", mission_fresh=True)
        model.drain()
        self.assertEqual(model.state, State.STOPPING)
        self.assertEqual(model.result(), -errno.ECANCELED)
        self.assertEqual(model.counts["bhie_calls"], 1)
        self.assertFalse(model.completion_validated)
        model.finish_power_down(quiesced=True)
        self.assertEqual(model.state, State.CLOSED)

    def test_no_reset_or_shutdown_shortcut_can_rearm_admission(self):
        model = model_with()
        model.post("PBL", direct=True)
        model.drain()
        with self.assertRaises(RuntimeError):
            model.new_session_after_reset(reset_confirmed=True)
        model.power_down()
        with self.assertRaises(RuntimeError):
            model.finish_power_down(quiesced=False)
        model.finish_power_down(quiesced=True)
        with self.assertRaises(RuntimeError):
            model.new_session_after_reset(reset_confirmed=False)

    def test_new_reset_session_drops_old_events_and_allows_one_new_call(self):
        model = model_with()
        model.post("PBL", direct=True)
        model.drain()
        old_generation = model.generation
        model.power_down()
        model.finish_power_down(quiesced=True)
        model.new_session_after_reset(reset_confirmed=True)
        for kind in ("PBL", "SBL", "READY", "MISSION", "POWER_DOWN"):
            model.post(kind, generation=old_generation, direct=True, mission_fresh=True)
        model.post("PBL", direct=True)
        model.post("MISSION", mission_fresh=True)
        model.drain()
        self.assertEqual(model.generation, old_generation + 1)
        self.assertEqual(model.result(), 0)
        self.assertEqual(model.metrics[old_generation]["bhie_calls"], 1)
        self.assertEqual(model.counts["bhie_calls"], 1)
        self.assertEqual(model.counts["stale_events"], 5)

    def test_old_completion_returned_for_new_generation_is_rejected(self):
        old_completions = []

        def save_completion(model, token):
            value = completed(model, token)
            old_completions.append(value)
            return value

        model = model_with(transport=save_completion)
        model.post("PBL", direct=True)
        model.drain()
        model.power_down()
        model.finish_power_down(quiesced=True)
        model.new_session_after_reset(reset_confirmed=True)
        model.transport = lambda model, token: old_completions[0]
        model.post("PBL", direct=True)
        model.post("MISSION", mission_fresh=True)
        model.drain()
        self.assertEqual(model.result(), -errno.EIO)
        self.assertEqual(model.error_phase, "completion_unqualified")
        self.assertEqual(model.counts["bhie_calls"], 1)
        self.assertEqual(model.counts["mission"], 0)

    def test_error_latch_resets_only_after_closed_reset_session(self):
        model = model_with(transport=lambda model, token: TransferResult(-errno.EIO))
        model.post("PBL", direct=True)
        model.drain()
        model.power_down()
        model.finish_power_down(quiesced=True)
        self.assertEqual(model.result(), -errno.EIO)
        model.new_session_after_reset(reset_confirmed=True)
        self.assertEqual(model.result(), -errno.EINPROGRESS)
        self.assertIsNone(model.admission)
        self.assertEqual(model.counts["bhie_calls"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
