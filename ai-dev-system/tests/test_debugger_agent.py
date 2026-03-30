from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from agents.debugger_agent import DebugAgent


class DebugAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = DebugAgent()

    def test_summarize_console_filters_mcp_noise(self) -> None:
        payload = {
            "structured_content": {
                "data": [
                    {
                        "type": "Exception",
                        "message": "<b><color=#2EA3FF>MCP-FOR-UNITY</color></b>: Client handler exited (remaining clients: 1)",
                        "file": "./Library/PackageCache/com.coplaydev.unity-mcp@abc/Editor/Helpers/McpLog.cs",
                    },
                    {
                        "type": "Warning",
                        "message": "Player missing saved preference key",
                        "file": "Assets/Scripts/Player.cs",
                    },
                    {
                        "type": "Log",
                        "message": "Scene verification completed",
                        "file": "Assets/Scripts/Verifier.cs",
                    },
                ]
            }
        }

        analysis = self.agent.summarize_console(payload)

        self.assertEqual(analysis["counts"]["noise_filtered"], 1)
        self.assertEqual(analysis["counts"]["app_warnings"], 1)
        self.assertEqual(analysis["counts"]["app_logs"], 1)
        self.assertEqual(analysis["counts"]["app_errors"], 0)

    def test_analyze_console_reports_clean_console(self) -> None:
        lesson = self.agent.analyze_console(
            {
                "counts": {
                    "app_errors": 0,
                    "app_warnings": 0,
                    "app_logs": 0,
                    "noise_filtered": 0,
                }
            }
        )

        self.assertIsNotNone(lesson)
        self.assertEqual(lesson.category, "verification")
        self.assertIn("clean", lesson.summary.lower())

    def test_unknown_package_message_is_not_suppressed(self) -> None:
        payload = {
            "structured_content": {
                "data": [
                    {
                        "type": "Error",
                        "message": "<b><color=#2EA3FF>MCP-FOR-UNITY</color></b>: Failed to deserialize command payload",
                        "file": "./Library/PackageCache/com.coplaydev.unity-mcp@abc/Editor/Helpers/McpLog.cs",
                    }
                ]
            }
        }

        analysis = self.agent.summarize_console(payload)

        self.assertEqual(analysis["counts"]["noise_filtered"], 0)
        self.assertEqual(analysis["counts"]["app_errors"], 1)


if __name__ == "__main__":
    unittest.main()
