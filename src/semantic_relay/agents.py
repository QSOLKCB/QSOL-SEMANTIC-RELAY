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


def _split_windows_commandline(command: str) -> tuple[str, ...]:
    """Parse a Windows command line using Microsoft backslash/quote rules."""
    arguments: list[str] = []
    length = len(command)
    index = 0

    while index < length:
        while index < length and command[index] in " \t":
            index += 1
        if index >= length:
            break

        argument: list[str] = []
        in_quotes = False

        while index < length:
            character = command[index]

            if character in " \t" and not in_quotes:
                break

            if character == "\\":
                slash_start = index
                while index < length and command[index] == "\\":
                    index += 1
                slash_count = index - slash_start

                if index < length and command[index] == '"':
                    argument.extend("\\" * (slash_count // 2))
                    if slash_count % 2:
                        argument.append('"')
                        index += 1
                    elif in_quotes and index + 1 < length and command[index + 1] == '"':
                        argument.append('"')
                        index += 2
                    else:
                        in_quotes = not in_quotes
                        index += 1
                else:
                    argument.extend("\\" * slash_count)
                continue

            if character == '"':
                if in_quotes and index + 1 < length and command[index + 1] == '"':
                    argument.append('"')
                    index += 2
                else:
                    in_quotes = not in_quotes
                    index += 1
                continue

            argument.append(character)
            index += 1

        arguments.append("".join(argument))

        while index < length and command[index] in " \t":
            index += 1

    return tuple(arguments)


def _split_command(command: str, *, windows: bool | None = None) -> tuple[str, ...]:
    """Split a command string using the host platform's argv quoting rules."""
    if windows is None:
        windows = os.name == "nt"

    if windows:
        return _split_windows_commandline(command)
    return tuple(shlex.split(command))


@dataclass(frozen=True)
class CommandAgent:
    """Invoke one fresh, restricted subprocess per prompt.

    Supported commands must be pure stdin/stdout model clients with no tool or
    filesystem access. This class reduces incidental leakage by running each
    invocation in a fresh empty working directory and passing only a small
    environment allowlist. It is not a general-purpose OS security sandbox.

    The command receives the prompt on stdin and must emit its response on stdout.
    Explicit relative path arguments such as `./client` or `scripts/client.py`
    are resolved against the invocation directory before the subprocess switches to
    its fresh empty working directory. Bare command arguments are left unchanged.
    `shell=False` is intentional: command strings are split using platform-aware
    quoting rules and executed directly.
    """

    command: tuple[str, ...]
    timeout_seconds: float = 120.0

    @classmethod
    def from_string(cls, command: str, timeout_seconds: float = 120.0) -> "CommandAgent":
        argv = _split_command(command)
        if not argv:
            raise ValueError("agent command must not be empty")

        invocation_dir = Path.cwd()
        resolved_argv: list[str] = []
        for argument in argv:
            candidate = Path(argument)
            is_explicit_relative_path = (
                not candidate.is_absolute()
                and (
                    argument.startswith(".")
                    or "/" in argument
                    or "\\" in argument
                )
            )
            if is_explicit_relative_path:
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
