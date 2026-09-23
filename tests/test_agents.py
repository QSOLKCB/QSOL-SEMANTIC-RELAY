import json
import os
import shlex
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from semantic_relay.agents import CommandAgent


class AgentTests(unittest.TestCase):
    def test_label_preserves_argument_boundaries(self) -> None:
        agent = CommandAgent(
            ("python", "-c", "print('two words')", "argument with spaces", "semi;colon")
        )
        self.assertEqual(shlex.split(agent.label), list(agent.command))

    def test_relative_script_path_is_resolved_before_workdir_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "client.py"
            script.write_text(
                "import sys; print('SEEN:' + sys.stdin.read().strip())\n",
                encoding="utf-8",
            )
            previous = Path.cwd()
            os.chdir(root)
            try:
                agent = CommandAgent.from_string(
                    f"{shlex.quote(sys.executable)} client.py"
                )
            finally:
                os.chdir(previous)

            self.assertEqual(Path(agent.command[1]), script.resolve())
            self.assertEqual(agent.invoke("hello"), "SEEN:hello")

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
