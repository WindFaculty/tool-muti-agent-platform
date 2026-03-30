from __future__ import annotations

import argparse
import json
import sys

from app.agent.controller import AgentController
from app.agent.task_spec import TaskSpec
from app.config.settings import Settings

# Import profiles so they self-register via @ProfileRegistry.register(...)
import app.profiles.calculator_profile  # noqa: F401
import app.profiles.explorer_profile  # noqa: F401
import app.profiles.notepad_profile  # noqa: F401
import app.profiles.unity_editor_profile  # noqa: F401

from app.profiles.registry import ProfileRegistry


def build_parser(profile_names: list[str]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Windows GUI agent for desktop automation.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"Available profiles: {', '.join(profile_names) or '(none registered)'}",
    )
    parser.add_argument("--dry-run", action="store_true", help="Plan and log actions without sending input.")
    parser.add_argument("--verbose", action="store_true", help="Print progress to stdout during a run.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-windows", help="Enumerate visible top-level windows.")
    subparsers.add_parser("list-profiles", help="List all registered app profiles.")
    capabilities_parser = subparsers.add_parser("list-capabilities", help="List structured capabilities for a profile.")
    capabilities_parser.add_argument(
        "--profile",
        required=True,
        choices=profile_names,
        metavar="PROFILE",
        help=f"Profile name. One of: {', '.join(profile_names)}",
    )

    inspect_parser = subparsers.add_parser("inspect", help="Launch or attach to an app and dump control trees.")
    inspect_parser.add_argument(
        "--app",
        required=True,
        choices=profile_names,
        metavar="APP",
        help=f"Profile name. One of: {', '.join(profile_names)}",
    )

    run_parser = subparsers.add_parser("run", help="Execute a bounded task with a profile.")
    run_parser.add_argument(
        "--profile",
        required=True,
        choices=profile_names,
        metavar="PROFILE",
        help=f"Profile name. One of: {', '.join(profile_names)}",
    )
    task_source = run_parser.add_mutually_exclusive_group(required=True)
    task_source.add_argument("--task", help="Task description string.")
    task_source.add_argument("--task-file", metavar="FILE", help="Path to a YAML task spec file.")
    run_parser.add_argument("--confirm-destructive", action="store_true")
    run_parser.add_argument(
        "--json-output",
        action="store_true",
        default=True,
        help="Emit structured JSON output (default: on).",
    )

    return parser


def resolve_task(args: argparse.Namespace, profile) -> str | TaskSpec:
    if args.task:
        task_spec = profile.task_spec_from_alias(args.task)
        return task_spec if task_spec is not None else args.task
    task_spec = TaskSpec.from_file(args.task_file)
    if task_spec.profile != profile.name:
        raise ValueError(
            f"Task spec profile '{task_spec.profile}' does not match requested profile '{profile.name}'."
        )
    return task_spec


def main() -> None:
    profile_names = ProfileRegistry.names()
    parser = build_parser(profile_names)
    args = parser.parse_args()
    settings = Settings.default()
    settings.dry_run = bool(args.dry_run)
    controller = AgentController(settings)

    if args.command == "list-windows":
        print(json.dumps(controller.list_windows(), indent=2))
        return

    if args.command == "list-profiles":
        print(json.dumps({"profiles": profile_names}, indent=2))
        return

    if args.command == "list-capabilities":
        print(json.dumps(controller.list_capabilities(ProfileRegistry.get(args.profile)), indent=2))
        return

    if args.command == "inspect":
        print(json.dumps(controller.inspect(ProfileRegistry.get(args.app)), indent=2))
        return

    if args.command == "run":
        profile = ProfileRegistry.get(args.profile)
        task = resolve_task(args, profile)
        if isinstance(task, TaskSpec) and task.dry_run:
            controller._settings.dry_run = True
        task_confirm_destructive = task.confirm_destructive if isinstance(task, TaskSpec) else False
        result = controller.run(
            profile,
            task,
            confirm_destructive=bool(args.confirm_destructive or task_confirm_destructive),
        )
        print(json.dumps(result, indent=2))
        return

    print(f"Unsupported command: {args.command}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
