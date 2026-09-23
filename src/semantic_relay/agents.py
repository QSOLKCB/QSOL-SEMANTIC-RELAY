from __future__ import annotations

from dataclasses import dataclass
import os
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol


class Agent(Protocol):
    """Minimal agent interface used by the experiment runner."""

    @property
    def label(self) -> str: ...

    def invoke(self, prompt: str) -> str: ...


_SAFE_ENV_KEYS = (
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "LANG",
    "LC_ALL",
    "OLLAMA_HOST",
)


@dataclass(frozen=True)
class CommandAgent:
    """Invoke one fresh, restricted subprocess per prompt.

    Supported commands must be pure stdin/stdout model clients with no tool or
    filesystem access. This class reduces incidental leakage by running each
    invocation in a fresh empty working directory and passing only a small
    environment allowlist. It is not a general-purpose OS security sandbox.

    The command receives the prompt on stdin and must emit its response on stdout.
    Existing relative path arguments are resolved against the invocation directory
    before the subprocess switches to its fresh empty working directory.
    `shell=False` is intentional: commands are parsed once with `shlex.split` and
    executed directly.
    """

    command: tuple[str, ...]
    timeout_seconds: float = 120.0

    @classmethod
    def from_string(cls, command: str, timeout_seconds: float = 120.0) -> "CommandAgent":
        argv = tuple(shlex.split(command))
        if not argv:
            raise ValueError("agent command must not be empty")

        invocation_dir = Path.cwd()
        resolved_argv: list[str] = []
        for argument in argv:
            candidate = Path(argument)
            if not candidate.is_absolute():
                invocation_candidate = invocation_dir / candidate
                if invocation_candidate.exists():
                    argument = str(invocation_candidate.resolve())
            resolved_argv.append(argument)

        return cls(tuple(resolved_argv), timeout_seconds)

    @property
    def label(self) -> str:
        return shlex.join(self.command)

    def invoke(self, prompt: str) -> str:
        env = {key: os.environ[key] for key in _SAFE_ENV_KEYS if key in os.environ}
        with tempfile.TemporaryDirectory(prefix="semantic-relay-agent-") as workdir:
            completed = subprocess.run(
                self.command,
                input=prompt,
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
                shell=False,
                cwd=workdir,
                env=env,
            )
        if completed.returncode != 0:
            stderr = completed.stderr.strip()
            raise RuntimeError(
                f"agent command failed with exit code {completed.returncode}: {stderr}"
            )
        return completed.stdout.strip()
