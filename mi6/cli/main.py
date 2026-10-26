"""Command line entry point: read arguments, call the core, format the result (RF-7; plan, section 4).

The CLI holds no business rules: every check lives in mi6.core. This module
only maps domain exceptions to messages and exit codes (plan, section 4.7).
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from mi6.cli import messages, prompts, render
from mi6.cli.prompts import NoTerminalError
from mi6.core import operations, storage, validation
from mi6.core.errors import (
    AuthenticationError,
    CorruptDataError,
    DataAccessError,
    DuplicateMissionError,
    InsecurePermissionsError,
    MissionNotFoundError,
    OperationInProgressError,
    StorageError,
    SymlinkError,
    UnsafeEnvironmentError,
    ValidationError,
)

EXIT_OK = 0
EXIT_REJECTED = 1
EXIT_USAGE = 2
EXIT_FAILURE = 3
EXIT_ABORTED = 130

_EXIT_CODES: tuple[tuple[type[BaseException], int], ...] = (
    (ValidationError, EXIT_REJECTED),
    (AuthenticationError, EXIT_REJECTED),
    (DuplicateMissionError, EXIT_REJECTED),
    (MissionNotFoundError, EXIT_REJECTED),
    (NoTerminalError, EXIT_USAGE),
    (StorageError, EXIT_FAILURE),
)


class UsageError(Exception):
    """Unknown command, or missing or extra arguments (exit code 2)."""


class _HelpRequested(Exception):
    """Raised as soon as -h/--help is parsed, before required arguments are checked."""


class _ArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that never prints English text nor exits on its own."""

    def error(self, message: str) -> None:  # type: ignore[override]
        raise UsageError(message)

    def exit(self, status: int = 0, message: str | None = None) -> None:  # type: ignore[override]
        raise UsageError(message or "")


class _HelpAction(argparse.Action):
    def __init__(self, option_strings: Sequence[str], dest: str, **kwargs: object) -> None:
        super().__init__(option_strings, dest=argparse.SUPPRESS, default=argparse.SUPPRESS, nargs=0)

    def __call__(self, parser, namespace, values, option_string=None) -> None:  # type: ignore[override]
        raise _HelpRequested()


def build_parser() -> argparse.ArgumentParser:
    """Build the parser for ``create``, ``list`` and ``archive`` (plan, section 4.1)."""
    parser = _ArgumentParser(prog="mi6", add_help=False, allow_abbrev=False)
    _add_help(parser)
    commands = parser.add_subparsers(dest="command", required=True, parser_class=_ArgumentParser)

    create = commands.add_parser("create", add_help=False, allow_abbrev=False)
    _add_help(create)
    _add_agent(create)
    _add_code_name(create)
    create.add_argument("-t", "--threat", dest="threat", required=True)
    create.set_defaults(handler=_run_create)

    list_command = commands.add_parser("list", add_help=False, allow_abbrev=False)
    _add_help(list_command)
    _add_agent(list_command)
    list_command.set_defaults(handler=_run_list)

    archive = commands.add_parser("archive", add_help=False, allow_abbrev=False)
    _add_help(archive)
    _add_agent(archive)
    _add_code_name(archive)
    archive.set_defaults(handler=_run_archive)
    return parser


def main(argv: Sequence[str] | None = None, data_dir: str | os.PathLike[str] | None = None) -> int:
    """Run mi6 and return its exit code. ``data_dir`` defaults to ``~/.mi6``."""
    _configure_output()
    try:
        return _main(argv, data_dir)
    except (KeyboardInterrupt, EOFError):
        render.print_safe(messages.ABORTED_BY_AGENT, file=sys.stderr)
        return EXIT_ABORTED


def _main(argv: Sequence[str] | None, data_dir: str | os.PathLike[str] | None) -> int:
    try:
        args = build_parser().parse_args(None if argv is None else list(argv))
    except _HelpRequested:
        render.print_safe(messages.HELP)
        return EXIT_OK
    except UsageError:
        render.print_safe(messages.ERR_USAGE, file=sys.stderr)
        render.print_safe(messages.HELP, file=sys.stderr)
        return EXIT_USAGE

    handler: Callable[[argparse.Namespace, Path], None] = args.handler
    try:
        target = storage.resolve_data_dir() if data_dir is None else Path(data_dir)
        handler(args, target)
    except EOFError:
        raise
    except Exception as exc:
        render.print_safe(_error_message(exc), file=sys.stderr)
        return _exit_code(exc)
    return EXIT_OK


def _run_create(args: argparse.Namespace, data_dir: Path) -> None:
    agent, code_name, threat = operations.preflight_create(data_dir, args.agent, args.code_name, args.threat)
    prompts.require_terminal()
    report = validation.normalize_report(prompts.read_report_body())
    if operations.agent_exists(data_dir, agent):
        password = prompts.prompt_password(messages.PASSWORD_PROMPT)
        confirmation = None
    else:
        password, confirmation = prompts.read_new_password(
            messages.PASSWORD_NEW.format(agent=agent), messages.PASSWORD_REPEAT
        )
    mission = operations.create_mission(data_dir, agent, code_name, str(threat), report, password, confirmation)
    render.print_safe(
        messages.CREATE_OK.format(
            code_name=render.sanitize_output(mission.code_name),
            threat=mission.threat_level,
            agent=agent,
        )
    )


def _run_list(args: argparse.Namespace, data_dir: Path) -> None:
    report = operations.list_active_missions(data_dir, args.agent)
    agent = validation.validate_agent_code(args.agent)
    render.print_safe(render.format_mission_list(agent, report))


def _run_archive(args: argparse.Namespace, data_dir: Path) -> None:
    mission = operations.get_active_mission(data_dir, args.agent, args.code_name)
    render.print_safe(
        messages.ARCHIVE_PREVIEW.format(
            code_name=render.sanitize_output(mission.code_name),
            threat=mission.threat_level,
        )
    )
    prompts.require_terminal()
    password = prompts.prompt_password(messages.PASSWORD_PROMPT)
    archived = operations.archive_mission(data_dir, args.agent, args.code_name, password)
    render.print_safe(messages.ARCHIVE_OK.format(code_name=render.sanitize_output(archived.code_name)))


def _error_message(exc: BaseException) -> str:
    """Translate an exception into the agent-facing text, never showing a traceback."""
    if isinstance(exc, ValidationError):
        return _validation_message(exc)
    if isinstance(exc, AuthenticationError):
        return messages.ERR_AUTH
    if isinstance(exc, DuplicateMissionError):
        status = str(exc.status)
        return messages.ERR_DUPLICATE.format(
            code_name=render.sanitize_output(exc.code_name),
            status_es=messages.DUPLICATE_STATUS_LABELS.get(status, render.sanitize_output(status)),
        )
    if isinstance(exc, MissionNotFoundError):
        return messages.ERR_NOT_FOUND.format(code_name=render.sanitize_output(exc.code_name))
    if isinstance(exc, NoTerminalError):
        return messages.ERR_NO_TERMINAL
    if isinstance(exc, InsecurePermissionsError):
        if exc.current_mode & 0o077:
            return messages.ERR_PERMISSIONS.format(
                path=_path(exc),
                current=f"{exc.current_mode:04o}",
                expected=f"{exc.expected_mode:o}",
            )
        return messages.ERR_OWNER.format(path=_path(exc))
    if isinstance(exc, SymlinkError):
        return messages.ERR_SYMLINK.format(path=_path(exc))
    if isinstance(exc, CorruptDataError):
        return messages.ERR_CORRUPT.format(path=_path(exc))
    if isinstance(exc, OperationInProgressError):
        return messages.ERR_IN_PROGRESS
    if isinstance(exc, UnsafeEnvironmentError):
        return messages.UNSAFE_ENVIRONMENT_MESSAGES.get(exc.reason, messages.UNEXPECTED)
    if isinstance(exc, DataAccessError):
        return messages.ERR_DATA_ACCESS.format(path=_path(exc), reason=_errno_reason(exc.os_error_name))
    return messages.UNEXPECTED


def _exit_code(exc: BaseException) -> int:
    for exception_type, code in _EXIT_CODES:
        if isinstance(exc, exception_type):
            return code
    return EXIT_FAILURE


def _validation_message(exc: ValidationError) -> str:
    template = messages.VALIDATION_MESSAGES.get((exc.field, exc.rule))
    if template is None:
        field = messages.FIELD_LABELS.get(exc.field, render.sanitize_output(exc.field))
        return messages.ERR_VALIDATION.format(field=field)
    return template.format(length=exc.length if exc.length is not None else "?")


def _errno_reason(name: str) -> str:
    return messages.ERRNO_REASONS.get(name, messages.ERRNO_UNKNOWN.format(name=render.sanitize_output(name)))


def _path(exc: StorageError) -> str:
    if exc.path is None:
        return messages.UNKNOWN_PATH
    return render.sanitize_output(os.fspath(exc.path))


def _configure_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(errors="replace")
            except (ValueError, OSError):
                pass


def _add_help(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-h", "--help", action=_HelpAction)


def _add_agent(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-a", "--agent", dest="agent", required=True)


def _add_code_name(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-n", "--code-name", "--name", dest="code_name", required=True)
