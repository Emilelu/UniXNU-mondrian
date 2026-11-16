#!/usr/bin/env python3
"""Offline proposal only: session admission, not an MHI or hardware emulator.

No active build imports this file. All protocol/freshness approvals default false.
A test can supply a synthetic contract; that is not evidence about QCA6490.
"""

from collections import deque
from dataclasses import dataclass
from enum import Enum
import errno
from typing import Callable, Optional


class State(str, Enum):
    NEW = "new"
    PREPARING = "preparing"
    READY = "ready"
    IN_FLIGHT = "in_flight"
    WAIT_MISSION = "wait_mission"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    STOPPING = "stopping"
    CLOSED = "closed"


@dataclass(frozen=True)
class Contract:
    """External proof obligations, never inferred from cached EE or PM masks."""
    protocol_qualified: bool = False
    completion_freshness_qualified: bool = False
    direct_path_qualified: bool = False


@dataclass(frozen=True)
class Token:
    generation: int
    admission: int


@dataclass(frozen=True)
class Completion:
    # Abstract host correlation, not an assertion that hardware echoes generation.
    token: Token
    fresh: bool = False
    transfer_complete: bool = False


@dataclass(frozen=True)
class TransferResult:
    error: int = 0
    completion: Optional[Completion] = None


@dataclass(frozen=True)
class Event:
    generation: int
    kind: str
    direct: bool = False
    error: int = -errno.EIO
    mission_fresh: bool = False


class SessionModel:
    """One serialized state owner plus generation-tagged producer events.

    Reentrant pump callbacks may post events. They cannot dispatch this owner.
    This Python model relies on that explicit single-owner assumption. It is
    not a lock/CAS implementation and proves nothing about multiprocessor code.
    """

    def __init__(self, contract: Contract = Contract(), *,
                 prepare: Optional[Callable] = None,
                 ready: Optional[Callable] = None,
                 transport: Optional[Callable] = None,
                 mission: Optional[Callable] = None):
        self.contract = contract
        self.prepare = prepare or (lambda model: 0)
        self.ready = ready or (lambda model: 0)
        self.transport = transport or (
            lambda model, token: TransferResult(-errno.EOPNOTSUPP))
        self.mission = mission or (lambda model: 0)
        self.generation = 1
        self.state = State.NEW
        self.owner_running = False
        self.transport_active = False
        self.events = deque()
        self.trace = []
        self.metrics = {}
        self._initialize_session()

    def _initialize_session(self):
        self.first_error = 0
        self.error_phase = None
        self.cached_ee = "PBL"
        self.pbl_started = False
        self.image_ready = False
        self.ready_started = False
        self.ready_done = False
        self.admission = None
        self.completion_validated = False
        self.metrics[self.generation] = {
            "prepare": 0, "ready": 0, "admissions": 0, "bhie_calls": 0,
            "mission": 0, "stale_events": 0,
        }

    @property
    def counts(self):
        return self.metrics[self.generation]

    @property
    def terminal(self):
        return self.state in (State.SUCCEEDED, State.FAILED,
                              State.STOPPING, State.CLOSED)

    def post(self, kind: str, *, generation=None, direct=False,
             error=-errno.EIO, mission_fresh=False):
        event = Event(self.generation if generation is None else generation,
                      kind, direct, error, mission_fresh)
        self.events.append(event)
        return event

    def _fail(self, error, phase):
        # A late callback/EE never replaces the first causal failure.
        if not self.first_error:
            self.first_error = error if error < 0 else -errno.EIO
            self.error_phase = phase
        if self.state not in (State.STOPPING, State.CLOSED):
            self.state = State.FAILED
        self.trace.append((self.generation, "failed", phase, self.first_error))
        return self.first_error

    def report_failure(self, error, *, generation=None):
        """Immediate same-thread pump error publication; not an ISR/MP primitive.

        A real multi-CPU producer needs a generation-checked atomic failure
        mailbox plus owner notification. Merely queueing behind MISSION loses.
        """
        if generation is not None and generation != self.generation:
            return False
        self._fail(error, "nested_failure")
        return True

    def _call(self, callback, phase):
        try:
            ret = callback(self)
        except Exception:
            return self._fail(-errno.EIO, phase + "_exception")
        if ret != 0:
            return self._fail(ret, phase)
        return self.first_error

    def _run_ready_once(self):
        if not self.image_ready or self.ready_started or self.terminal:
            return
        self.ready_started = True  # latch before any callback can pump
        self.counts["ready"] += 1
        if self._call(self.ready, "ready") or self.terminal:
            return
        self.ready_done = True
        self.state = State.READY

    def _run_pbl_once(self, direct):
        if self.pbl_started or self.terminal:
            return
        self.pbl_started = True  # includes allocation and firmware preparation
        self.state = State.PREPARING
        self.counts["prepare"] += 1
        if self._call(self.prepare, "prepare") or self.terminal:
            return
        self.image_ready = True
        self._run_ready_once()
        if direct and not self.terminal:
            self._submit_once(direct=True)

    def _submit_once(self, *, direct):
        # Re-check before modifying cached EE, allocations, registers or doorbells.
        if self.terminal or self.admission is not None:
            return
        if not self.image_ready or not self.ready_done:
            self._fail(-errno.EPROTO, "submit_before_ready")
            return
        if not self.contract.protocol_qualified:
            self._fail(-errno.EOPNOTSUPP, "protocol_unqualified")
            return
        if direct and not self.contract.direct_path_qualified:
            self._fail(-errno.EOPNOTSUPP, "direct_path_unqualified")
            return
        if not self.contract.completion_freshness_qualified:
            self._fail(-errno.EOPNOTSUPP, "completion_freshness_unqualified")
            return
        self.admission = Token(self.generation, 1)
        self.counts["admissions"] += 1
        self.state = State.IN_FLIGHT
        # Attempt count, not completed physical transfers. No retry on any return.
        self.counts["bhie_calls"] += 1
        self.transport_active = True
        try:
            outcome = self.transport(self, self.admission)
        except Exception:
            outcome = TransferResult(-errno.EIO)
        finally:
            self.transport_active = False
        if self.terminal:
            return  # cancellation/error won while the transport pumped
        if outcome.error:
            self._fail(outcome.error, "bhie")
            return
        completion = outcome.completion
        if (completion is None or completion.token != self.admission or
                not completion.fresh or not completion.transfer_complete):
            self._fail(-errno.EIO, "completion_unqualified")
            return
        self.completion_validated = True
        self.state = State.WAIT_MISSION

    def _run_mission(self, fresh):
        # Never publish success from cached EE before the transition returns.
        if self.state != State.WAIT_MISSION or not self.completion_validated:
            return
        if not fresh:
            self._fail(-errno.EIO, "mission_unqualified")
            return
        self.counts["mission"] += 1
        if self._call(self.mission, "mission") or self.terminal:
            return
        self.cached_ee = "AMSS"
        self.state = State.SUCCEEDED

    def _dispatch(self, event):
        if event.generation != self.generation:
            self.counts["stale_events"] += 1
            self.trace.append((event.generation, "stale_event", event.kind))
            return
        if event.kind == "POWER_DOWN":
            self.power_down()
            return
        if self.terminal:
            self.trace.append((self.generation, "terminal_skip", event.kind))
            return
        if event.kind == "PBL":
            self._run_pbl_once(event.direct)
        elif event.kind == "READY":
            self._run_ready_once()
        elif event.kind == "SBL":
            # An EE observation is data, not a deduplication or admission lock.
            self.cached_ee = "SBL"
            self._submit_once(direct=False)
        elif event.kind == "DIRECT":
            self._submit_once(direct=True)
        elif event.kind == "MISSION":
            self._run_mission(event.mission_fresh)
        elif event.kind == "FAIL":
            self._fail(event.error, "external")
        else:
            raise ValueError("unknown model event: " + event.kind)

    def run_snapshot(self):
        """Splice one shared list snapshot, matching the audited st_worker shape."""
        if self.owner_running:
            return False
        self.owner_running = True
        local = list(self.events)
        self.events.clear()
        try:
            for event in local:
                self._dispatch(event)
        finally:
            self.owner_running = False
        return bool(local)

    def drain(self, budget=100):
        for unused in range(budget):
            if not self.run_snapshot():
                return
        raise RuntimeError("model event budget exhausted")

    def power_down(self):
        # May be requested while a nested wait pumps. Do not self-flush here.
        if self.state == State.CLOSED:
            return
        self._fail(-errno.ECANCELED, "power_down")
        self.state = State.STOPPING
        self.events.clear()

    def finish_power_down(self, *, quiesced):
        # quiesced is an external lifecycle precondition, not a hardware action.
        if (self.state != State.STOPPING or self.owner_running or
                self.transport_active or not quiesced):
            raise RuntimeError("owner/transport/device not proven quiescent")
        self.events.clear()
        self.state = State.CLOSED

    def new_session_after_reset(self, *, reset_confirmed):
        if (self.state != State.CLOSED or self.owner_running or
                self.transport_active or not reset_confirmed):
            raise RuntimeError("new session requires closed owner and confirmed reset")
        self.events.clear()
        self.generation += 1
        self.state = State.NEW
        self._initialize_session()

    def result(self):
        if self.first_error:
            return self.first_error
        return 0 if self.state == State.SUCCEEDED else -errno.EINPROGRESS
