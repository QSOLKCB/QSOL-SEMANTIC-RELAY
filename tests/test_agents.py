import shlex
import unittest

from semantic_relay.agents import CommandAgent


class AgentTests(unittest.TestCase):
    def test_label_preserves_argument_boundaries(self) -> None:
        agent = CommandAgent(
            ("python", "-c", "print('two words')", "argument with spaces", "semi;colon")
        )
        self.assertEqual(shlex.split(agent.label), list(agent.command))


if __name__ == "__main__":
    unittest.main()
