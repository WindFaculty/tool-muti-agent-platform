from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from tools.workflow_report import build_workflow_report, format_workflow_report


class WorkflowReportTests(unittest.TestCase):
    def test_build_workflow_report_collects_failures_and_verification(self) -> None:
        summary = {
            "task_id": "demo",
            "task_title": "Demo Task",
            "workflow_status": "failed",
            "stopped_after_step": "prepare_scene",
            "steps": [
                {
                    "step_id": "prepare_scene",
                    "status": "failed",
                    "details": {
                        "create_scene": {
                            "structured_content": {
                                "error": "Current scene has unsaved changes.",
                            }
                        }
                    },
                },
                {
                    "step_id": "verify_scene",
                    "status": "completed",
                    "details": {
                        "console_analysis": {
                            "counts": {
                                "app_errors": 1,
                                "app_warnings": 2,
                                "app_logs": 0,
                                "noise_filtered": 4,
                            },
                            "app_errors": [{"type": "Error", "message": "NullReferenceException"}],
                            "app_warnings": [{"type": "Warning", "message": "Missing icon"}],
                            "app_logs": [],
                        },
                        "expected_objects": {
                            "Player": {
                                "structured_content": {
                                    "data": {"instanceIDs": [], "totalCount": 0}
                                }
                            }
                        },
                        "screenshot": {
                            "structured_content": {
                                "data": {"fullPath": "D:/repo/unity-client/Assets/Screenshots/demo.png"}
                            }
                        },
                    },
                },
            ],
        }

        report = build_workflow_report(summary)

        self.assertEqual(report["overall_status"], "failed")
        self.assertEqual(report["failed_step_count"], 1)
        self.assertEqual(report["failed_steps"][0]["step_id"], "prepare_scene")
        self.assertEqual(report["failed_steps"][0]["category"], "editor_unsaved_changes")
        self.assertFalse(report["failed_steps"][0]["retryable"])
        self.assertEqual(report["verification_reports"][0]["counts"]["app_warnings"], 2)
        self.assertEqual(report["verification_reports"][0]["status"], "console-errors-and-missing-objects")
        self.assertEqual(report["verification_reports"][0]["missing_objects"], ["Player"])
        self.assertEqual(
            report["verification_reports"][0]["screenshot"],
            "D:/repo/unity-client/Assets/Screenshots/demo.png",
        )

    def test_format_workflow_report_outputs_readable_summary(self) -> None:
        report = {
            "task_title": "Demo Task",
            "overall_status": "completed",
            "step_count": 4,
            "failed_steps": [],
            "verification_reports": [
                {
                    "step_id": "verify_scene",
                    "status": "missing-objects",
                    "counts": {
                        "app_errors": 0,
                        "app_warnings": 0,
                        "app_logs": 1,
                        "noise_filtered": 3,
                    },
                    "top_errors": [],
                    "top_warnings": [],
                    "top_logs": ["Log: Verification completed"],
                    "screenshot": "D:/repo/unity-client/Assets/Screenshots/demo.png",
                    "missing_objects": ["Player"],
                }
            ],
        }

        formatted = format_workflow_report(report)

        self.assertIn("Overall status: completed", formatted)
        self.assertIn("Verification verify_scene [missing-objects]: errors=0, warnings=0, logs=1, noise_filtered=3", formatted)
        self.assertIn("Screenshot: D:/repo/unity-client/Assets/Screenshots/demo.png", formatted)
        self.assertIn("Missing objects: Player", formatted)
        self.assertIn("Logs:", formatted)

    def test_extract_missing_objects_accepts_instance_id_matches(self) -> None:
        summary = {
            "task_id": "demo",
            "task_title": "Demo Task",
            "steps": [
                {
                    "step_id": "verify_scene",
                    "status": "completed",
                    "details": {
                        "console_analysis": {"counts": {}},
                        "expected_objects": {
                            "Player": {
                                "structured_content": {
                                    "data": {"instanceIDs": [123], "totalCount": 1}
                                }
                            }
                        },
                    },
                }
            ],
        }

        report = build_workflow_report(summary)

        self.assertEqual(report["verification_reports"][0]["missing_objects"], [])

    def test_build_workflow_report_marks_retryable_transport_failures(self) -> None:
        summary = {
            "task_id": "demo",
            "task_title": "Demo Task",
            "workflow_status": "failed",
            "stopped_after_step": "load_scene",
            "steps": [
                {
                    "step_id": "load_scene",
                    "status": "failed",
                    "details": {
                        "load_existing_scene": {
                            "structured_content": {
                                "message": "Editor is reloading, please retry.",
                                "data": {"reason": "reloading"},
                            }
                        }
                    },
                }
            ],
        }

        report = build_workflow_report(summary)

        self.assertEqual(report["failed_steps"][0]["category"], "transport_retryable")
        self.assertTrue(report["failed_steps"][0]["retryable"])
        self.assertEqual(report["failed_steps"][0]["reason_codes"], ["reloading"])

    def test_build_workflow_report_marks_workflow_transport_exceptions_as_retryable(self) -> None:
        summary = {
            "task_id": "demo",
            "task_title": "Demo Task",
            "workflow_status": "failed",
            "steps": [
                {
                    "step_id": "verify_scene",
                    "status": "failed",
                    "details": {
                        "exception": {
                            "structured_content": {
                                "message": "RuntimeError: Connection closed by remote host",
                                "data": {"reason": "transport_exception"},
                            }
                        }
                    },
                }
            ],
        }

        report = build_workflow_report(summary)

        self.assertEqual(report["failed_steps"][0]["category"], "transport_retryable")
        self.assertTrue(report["failed_steps"][0]["retryable"])
        self.assertEqual(report["failed_steps"][0]["reason_codes"], ["transport_exception"])

    def test_format_workflow_report_includes_failure_category_and_retryability(self) -> None:
        report = {
            "task_title": "Demo Task",
            "overall_status": "failed",
            "step_count": 1,
            "failed_steps": [
                {
                    "step_id": "load_scene",
                    "category": "transport_retryable",
                    "retryable": True,
                    "reason_codes": ["reloading"],
                    "messages": ["Editor is reloading, please retry."],
                }
            ],
            "verification_reports": [],
            "stopped_after_step": "load_scene",
        }

        formatted = format_workflow_report(report)

        self.assertIn("Failed steps: 1", formatted)
        self.assertIn("[transport_retryable; retryable=yes; reasons=reloading]", formatted)
        self.assertIn("Stopped after step: load_scene", formatted)


if __name__ == "__main__":
    unittest.main()
