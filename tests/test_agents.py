import json
import os
import shlex
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from semantic_relay.agents import CommandAgent, _split_command


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
