import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from semantic_relay.agents import CommandAgent, _join_command, _split_command


class AgentTests(unittest.TestCase):
    def test_windows_command_parsing_preserves_backslashes(self) -> None:
        self.assertEqual(
            _split_command(r"python scripts\client.py", windows=True),
            ("python", r"scripts\client.py"),
        )

    def test_windows_command_parsing_strips_grouping_quotes(self) -> None:
        self.assertEqual(
            _split_command(r'python "scripts\client file.py"', windows=True),
            ("python", r"scripts\client file.py"),
        )

    def test_windows_command_parsing_handles_escaped_quotes_and_spaces(self) -> None:
        self.assertEqual(
            _split_command(
                r'python -c "print(\"hello world\")"',
                windows=True,
            ),
            ("python", "-c", 'print("hello world")'),
        )

    def test_windows_command_parsing_round_trips_list2cmdline(self) -> None:
        cases = (
            ("python", "-c", 'print("hello world")'),
            ("python", r"scripts\\client.py", "argument with spaces"),
            ("tool.exe", r"C:\\Program Files\\relay\\client.exe", r'{"key":"two words"}'),
            ("tool.exe", "", r"trailing\\"),
        )
        for argv in cases:
            with self.subTest(argv=argv):
                command = subprocess.list2cmdline(argv)
                self.assertEqual(_split_command(command, windows=True), argv)

    def test_windows_command_label_round_trips_argv(self) -> None:
        cases = (
            ("python", "-c", 'print("hello world")'),
            ("tool.exe", r"C:\\Program Files\\relay\\client.exe", "argument with spaces"),
            ("tool.exe", r'{"key":"two words"}', r"trailing\\"),
        )
        for argv in cases:
            with self.subTest(argv=argv):
                label = _join_command(argv, windows=True)
                self.assertEqual(_split_command(label, windows=True), argv)

    def test_posix_command_label_round_trips_argv(self) -> None:
        argv = ("python", "-c", "print('two words')", "argument with spaces", "semi;colon")
        label = _join_command(argv, windows=False)
        self.assertEqual(_split_command(label, windows=False), argv)

    def test_label_preserves_argument_boundaries(self) -> None:
        agent = CommandAgent(
            ("python", "-c", "print('two words')", "argument with spaces", "semi;colon")
        )
        self.assertEqual(shlex.split(agent.label), list(agent.command))

    def test_relative_script_path_is_resolved_before_workdir_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scripts = root / "scripts"
            scripts.mkdir()
            script = scripts / "client.py"
            script.write_text(
                "import sys; print('SEEN:' + sys.stdin.read().strip())\n",
                encoding="utf-8",
            )
            previous = Path.cwd()
            os.chdir(root)
            try:
                agent = CommandAgent.from_string(
                    f"{shlex.quote(sys.executable)} scripts/client.py"
                )
            finally:
                os.chdir(previous)

            self.assertEqual(Path(agent.command[1]), script.resolve())
            self.assertEqual(agent.invoke("hello"), "SEEN:hello")

    def test_bare_argument_is_not_rewritten_when_matching_local_entry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "run").write_text("not an argument path\n", encoding="utf-8")
            previous = Path.cwd()
            os.chdir(root)
            try:
                agent = CommandAgent.from_string("ollama run qwen2.5:3b")
            finally:
                os.chdir(previous)

            self.assertEqual(agent.command, ("ollama", "run", "qwen2.5:3b"))

    def test_invoke_uses_empty_workdir_and_stripped_environment(self) -> None:
        code = (
            "import json, os; "
            "print(json.dumps({'files': sorted(os.listdir('.')), "
            "'secret': os.environ.get('SEMANTIC_RELAY_TEST_SECRET')}))"
        )
        agent = CommandAgent((sys.executable, "-c", code))
        with patch.dict(os.environ, {"SEMANTIC_RELAY_TEST_SECRET": "fixture-leak"}, clear=False):
            result = json.loads(agent.invoke("ignored"))
        self.assertEqual(result["files"], [])
        self.assertIsNone(result["secret"])


if __name__ == "__main__":
    unittest.main()
