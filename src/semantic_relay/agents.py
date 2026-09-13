from __future__ import annotations

from dataclasses import dataclass
import shlex
import subprocess
from typing import Protocol


class Agent(Protocol):
    """Minimal agent interface used by the experiment runner."""

    @property
    def label(self) -> str: ...

    def invoke(self, prompt: str) -> str: ...


@dataclass(frozen=True)
class CommandAgent:
    """Invoke one fresh subprocess per prompt.

    The command receives the prompt on stdin and must emit its response on stdout.
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
        return cls(argv, timeout_seconds)

    @property
    def label(self) -> str:
        return shlex.join(self.command)

    def invoke(self, prompt: str) -> str:
        completed = subprocess.run(
            self.command,
            input=prompt,
            text=True,
            capture_output=True,
            timeout=self.timeout_seconds,
            check=False,
            shell=False,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip()
            raise RuntimeError(
                f"agent command failed with exit code {completed.returncode}: {stderr}"
            )
        return completed.stdout.strip()
