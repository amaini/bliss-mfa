"""Process supervision that isolates the authentication core from management components.

Only critical components (native authentication and its adapter) decide service health.
Management and commercial components (license agent, appliance API, portal, management
TLS proxy) restart independently with bounded backoff and can never stop the core.
"""
import os
import subprocess
import time
from dataclasses import dataclass, field

import httpx


class CriticalExit(RuntimeError):
    """The authentication core failed; the service manager must restart the service."""


@dataclass
class Component:
    name: str
    command: list
    env: dict | None
    critical: bool
    health: tuple | None = None  # (url, headers)
    verify: object = True


@dataclass
class _State:
    component: Component
    process: subprocess.Popen | None = None
    log: object = None
    failures: int = 0
    started_at: float = 0.0
    next_start: float = 0.0
    history: list = field(default_factory=list)


def restart_delay(failures, *, initial, maximum):
    if failures <= 0:
        return 0
    return min(initial * 2 ** (failures - 1), maximum)


class Supervisor:
    def __init__(self, components, *, cwd, log_dir, backoff_initial=1, backoff_max=60,
                 stable_after=60, ready_timeout=30):
        names = [c.name for c in components]
        if len(set(names)) != len(names):
            raise ValueError('Duplicate component name')
        self.cwd = cwd
        self.log_dir = log_dir
        self.backoff_initial = backoff_initial
        self.backoff_max = backoff_max
        self.stable_after = stable_after
        self.ready_timeout = ready_timeout
        self.states = {c.name: _State(c) for c in components}

    def _launch(self, state):
        if state.log:
            state.log.close()
        state.log = open(self.log_dir / (state.component.name + '.log'), 'a', encoding='utf-8')  # noqa: SIM115
        state.process = subprocess.Popen(state.component.command, cwd=self.cwd, env=state.component.env,
                                         stdout=state.log, stderr=state.log)
        state.started_at = time.monotonic()

    def _healthy(self, component):
        url, headers = component.health
        try:
            response = httpx.get(url, headers=headers, timeout=2, verify=component.verify, trust_env=False)
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    def _wait_ready(self, state, error):
        deadline = time.monotonic() + self.ready_timeout
        while True:
            if state.process.poll() is not None:
                raise error(f'{state.component.name} exited during startup; inspect its private log')
            if state.component.health is None or self._healthy(state.component):
                return
            if time.monotonic() >= deadline:
                raise error(f'{state.component.name} startup timed out')
            time.sleep(.1)

    def start(self, check=False):
        """Start the core and wait for it. In check (preflight) mode also require management readiness."""
        core = [s for s in self.states.values() if s.component.critical]
        management = [s for s in self.states.values() if not s.component.critical]
        for state in core:
            self._launch(state)
        for state in core:
            self._wait_ready(state, CriticalExit)
        for state in management:
            self._launch(state)
        if check:
            for state in management:
                self._wait_ready(state, RuntimeError)

    def poll(self):
        """One supervision step. Raises CriticalExit only when the authentication core fails."""
        now = time.monotonic()
        for state in self.states.values():
            process = state.process
            if process is not None and process.poll() is not None:
                if state.component.critical:
                    raise CriticalExit(f'{state.component.name} exited; restarting the engine service')
                # A component that ran stably before failing starts a fresh backoff series.
                if now - state.started_at >= self.stable_after:
                    state.failures = 0
                state.failures += 1
                state.history.append(process.returncode)
                state.process = None
                state.next_start = now + restart_delay(
                    state.failures, initial=self.backoff_initial, maximum=self.backoff_max)
            elif process is None and not state.component.critical and now >= state.next_start:
                self._launch(state)

    def run(self, stopping, stop_file=None, interval=.5):
        while not stopping.wait(interval):
            if stop_file and stop_file.exists():
                stop_file.unlink()
                return
            self.poll()

    def pid(self, name):
        process = self.states[name].process
        return process.pid if process is not None and process.poll() is None else None

    def alive(self, name):
        return self.pid(name) is not None

    def failures(self, name):
        return self.states[name].failures

    def kill(self, name):
        process = self.states[name].process
        if process is not None:
            process.kill()
            process.wait()

    def stop(self):
        for state in self.states.values():
            process = state.process
            if process is not None and process.poll() is None:
                _terminate_tree(process)
            if state.log:
                state.log.close()
                state.log = None


def _terminate_tree(process):
    if os.name == 'nt':
        # PHP-CGI is a child of the owned gateway; stop the entire owned tree.
        try:
            subprocess.run(['taskkill.exe', '/PID', str(process.pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=False)
        except (OSError, subprocess.TimeoutExpired):
            process.terminate()
    else:
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
