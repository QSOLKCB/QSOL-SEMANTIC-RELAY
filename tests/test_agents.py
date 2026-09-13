import json
import os
import shlex
import sys
import unittest
from unittest.mock import patch

from semantic_relay.agents import CommandAgent


class AgentTests(unittest.TestCase):
    def test_label_preserves_argument_boundaries(self) -> None:
        agent = CommandAgent(
            ("python", "-c", "print('two words')", "argument with spaces", "semi;colon")
        )
        self.assertEqual(shlex.split(agent.label), list(agent.command))

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
