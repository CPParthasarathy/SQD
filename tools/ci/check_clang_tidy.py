#!/usr/bin/env python3
"""Run the controlled Clang-Tidy static-analysis gate."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence


EXPECTED_CLANG_TIDY_VERSION = "22.1.8"

SOURCE_ROOTS = frozenset(
    {
        "components",
        "main",
        "verification",
    }
)

SOURCE_SUFFIXES = frozenset(
    {
        ".c",
        ".cc",
        ".cpp",
        ".cxx",
    }
)


class StaticAnalysisError(RuntimeError):
    """Raised when the static-analysis gate cannot execute reliably."""


def run_command(
    arguments: Sequence[str],
    *,
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    """Execute a command and capture deterministic text output."""

    try:
        return subprocess.run(
            list(arguments),
            cwd=cwd,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as error:
        raise StaticAnalysisError(
            f"Unable to execute command '{arguments[0]}': {error}"
        ) from error


def resolve_executable(requested_path: Path | None) -> Path:
    """Resolve clang-tidy from an explicit path or PATH."""

    if requested_path is not None:
        executable = requested_path.expanduser().resolve()
    else:
        discovered = shutil.which("clang-tidy")

        if discovered is None:
            raise StaticAnalysisError(
                "clang-tidy was not supplied and was not found on PATH."
            )

        executable = Path(discovered).resolve()

    if not executable.is_file():
        raise StaticAnalysisError(
            f"clang-tidy executable does not exist: {executable}"
        )

    return executable


def verify_repository(repo_root: Path) -> None:
    """Confirm that the selected directory is the Git repository root."""

    result = run_command(
        ("git", "rev-parse", "--show-toplevel"),
        cwd=repo_root,
    )

    if result.returncode != 0:
        diagnostic = (result.stderr or result.stdout).strip()

        raise StaticAnalysisError(
            f"Unable to identify the Git repository root: {diagnostic}"
        )

    discovered_root = Path(result.stdout.strip()).resolve()

    if discovered_root != repo_root:
        raise StaticAnalysisError(
            "Selected repository root does not match Git: "
            f"selected={repo_root}, git={discovered_root}"
        )


def verify_clang_tidy_version(
    clang_tidy: Path,
    repo_root: Path,
) -> str:
    """Require the exact controlled Clang-Tidy release."""

    result = run_command(
        (str(clang_tidy), "--version"),
        cwd=repo_root,
    )

    version_output = "\n".join(
        part.strip()
        for part in (result.stdout, result.stderr)
        if part.strip()
    )

    if result.returncode != 0:
        raise StaticAnalysisError(
            f"Unable to query clang-tidy version: {version_output}"
        )

    version_pattern = re.compile(
        rf"\b(?:LLVM|clang-tidy) version "
        rf"{re.escape(EXPECTED_CLANG_TIDY_VERSION)}\b"
    )

    if version_pattern.search(version_output) is None:
        raise StaticAnalysisError(
            "Unexpected clang-tidy version: "
            f"expected={EXPECTED_CLANG_TIDY_VERSION}, "
            f"actual='{version_output}'"
        )

    return version_output


def verify_configuration(
    clang_tidy: Path,
    config_path: Path,
    repo_root: Path,
) -> None:
    """Verify every configured Clang-Tidy option and check name."""

    if not config_path.is_file():
        raise StaticAnalysisError(
            f"Clang-Tidy configuration does not exist: {config_path}"
        )

    result = run_command(
        (
            str(clang_tidy),
            f"--config-file={config_path}",
            "--verify-config",
        ),
        cwd=repo_root,
    )

    diagnostic = "\n".join(
        part.strip()
        for part in (result.stdout, result.stderr)
        if part.strip()
    )

    if result.returncode != 0:
        raise StaticAnalysisError(
            "Clang-Tidy configuration verification failed: "
            f"{diagnostic}"
        )

    if diagnostic:
        print(diagnostic)


def resolve_compilation_database(
    requested_path: Path,
) -> tuple[Path, Path]:
    """Resolve a compilation-database argument to its file and directory."""

    resolved_path = requested_path.expanduser().resolve()

    if resolved_path.is_dir():
        database_directory = resolved_path
        database_file = resolved_path / "compile_commands.json"
    else:
        database_file = resolved_path
        database_directory = resolved_path.parent

    if not database_file.is_file():
        raise StaticAnalysisError(
            f"Compilation database does not exist: {database_file}"
        )

    if database_file.name != "compile_commands.json":
        raise StaticAnalysisError(
            "Compilation-database file must be named "
            f"'compile_commands.json': {database_file}"
        )

    return database_file, database_directory


def is_repository_source(
    source_path: Path,
    repo_root: Path,
) -> bool:
    """Return whether a file is a repository-owned C/C++ source."""

    try:
        relative_path = source_path.relative_to(repo_root)
    except ValueError:
        return False

    if not relative_path.parts:
        return False

    if relative_path.parts[0] not in SOURCE_ROOTS:
        return False

    if relative_path.suffix.lower() not in SOURCE_SUFFIXES:
        return False

    return source_path.is_file()


def load_compilation_entries(
    database_file: Path,
    database_directory: Path,
    repo_root: Path,
) -> dict[Path, Path]:
    """Load repository-owned translation units from a compilation database."""

    try:
        raw_database = database_file.read_text(encoding="utf-8")
        entries = json.loads(raw_database)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise StaticAnalysisError(
            f"Unable to read compilation database '{database_file}': {error}"
        ) from error

    if not isinstance(entries, list):
        raise StaticAnalysisError(
            f"Compilation database is not a JSON array: {database_file}"
        )

    translation_units: dict[Path, Path] = {}

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        file_value = entry.get("file")
        directory_value = entry.get("directory")

        if not isinstance(file_value, str):
            continue

        if isinstance(directory_value, str):
            working_directory = Path(directory_value)

            if not working_directory.is_absolute():
                working_directory = (
                    database_directory / working_directory
                )

            working_directory = working_directory.resolve()
        else:
            working_directory = database_directory

        source_path = Path(file_value)

        if not source_path.is_absolute():
            source_path = working_directory / source_path

        source_path = source_path.resolve()

        if is_repository_source(source_path, repo_root):
            translation_units.setdefault(
                source_path,
                database_directory,
            )

    return translation_units


def collect_translation_units(
    requested_databases: Sequence[Path],
    repo_root: Path,
) -> dict[Path, Path]:
    """Collect translation units from one or more compilation databases."""

    translation_units: dict[Path, Path] = {}

    for requested_database in requested_databases:
        database_file, database_directory = (
            resolve_compilation_database(requested_database)
        )

        database_entries = load_compilation_entries(
            database_file,
            database_directory,
            repo_root,
        )

        for source_path, source_database_directory in database_entries.items():
            translation_units.setdefault(
                source_path,
                source_database_directory,
            )

    if not translation_units:
        raise StaticAnalysisError(
            "No repository-owned C/C++ translation units were found "
            "in the supplied compilation databases."
        )

    return translation_units


def analyze_translation_unit(
    clang_tidy: Path,
    config_path: Path,
    repo_root: Path,
    source_path: Path,
    database_directory: Path,
) -> tuple[bool, str]:
    """Run Clang-Tidy for one translation unit."""

    result = run_command(
        (
            str(clang_tidy),
            f"--config-file={config_path}",
            "--quiet",
            f"-p={database_directory}",
            str(source_path),
        ),
        cwd=repo_root,
    )

    diagnostic = "\n".join(
        part.rstrip()
        for part in (result.stdout, result.stderr)
        if part.strip()
    )

    return result.returncode == 0, diagnostic


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""

    default_repo_root = Path(__file__).resolve().parents[2]

    parser = argparse.ArgumentParser(
        description=(
            "Verify the controlled Clang-Tidy configuration and run "
            "static analysis using one or more compilation databases."
        )
    )

    parser.add_argument(
        "--repo-root",
        type=Path,
        default=default_repo_root,
        help="Repository root. Defaults to the root containing this script.",
    )

    parser.add_argument(
        "--clang-tidy",
        type=Path,
        default=None,
        help="Explicit path to the controlled clang-tidy executable.",
    )

    parser.add_argument(
        "--config-file",
        type=Path,
        default=None,
        help="Clang-Tidy configuration. Defaults to <repo>/.clang-tidy.",
    )

    parser.add_argument(
        "--compile-commands",
        type=Path,
        action="append",
        default=[],
        help=(
            "Directory containing compile_commands.json, or the file "
            "itself. May be supplied multiple times."
        ),
    )

    parser.add_argument(
        "--config-only",
        action="store_true",
        help=(
            "Validate the executable version and configuration without "
            "requiring a compilation database."
        ),
    )

    return parser.parse_args()


def main() -> int:
    """Execute the static-analysis gate."""

    arguments = parse_arguments()
    repo_root = arguments.repo_root.expanduser().resolve()

    try:
        if not repo_root.is_dir():
            raise StaticAnalysisError(
                f"Repository root does not exist: {repo_root}"
            )

        verify_repository(repo_root)

        clang_tidy = resolve_executable(arguments.clang_tidy)

        if arguments.config_file is None:
            config_path = repo_root / ".clang-tidy"
        else:
            config_path = arguments.config_file.expanduser().resolve()

        version_output = verify_clang_tidy_version(
            clang_tidy,
            repo_root,
        )

        print("B4.1 Clang-Tidy check")
        print(f"Repository: {repo_root}")
        print("Analyzer:")

        for version_line in version_output.splitlines():
            print(f"  {version_line}")

        verify_configuration(
            clang_tidy,
            config_path,
            repo_root,
        )

        print(f"Configuration: {config_path}")
        print("Configuration verification: PASS")

        if arguments.config_only:
            if arguments.compile_commands:
                raise StaticAnalysisError(
                    "--config-only cannot be combined with "
                    "--compile-commands."
                )

            print("")
            print(
                "PASS: Clang-Tidy executable and configuration "
                "contract validated."
            )

            return 0

        if not arguments.compile_commands:
            raise StaticAnalysisError(
                "At least one --compile-commands argument is required "
                "unless --config-only is used."
            )

        translation_units = collect_translation_units(
            arguments.compile_commands,
            repo_root,
        )

        ordered_units = sorted(
            translation_units.items(),
            key=lambda item: item[0].relative_to(repo_root).as_posix(),
        )

        print(f"Translation units: {len(ordered_units)}")
        print("")

        failures: list[tuple[Path, str]] = []

        for source_path, database_directory in ordered_units:
            relative_path = source_path.relative_to(repo_root)

            passed, diagnostic = analyze_translation_unit(
                clang_tidy,
                config_path,
                repo_root,
                source_path,
                database_directory,
            )

            status = "PASS" if passed else "FAIL"

            print(f"[{status}] {relative_path.as_posix()}")

            if not passed:
                failures.append(
                    (
                        relative_path,
                        diagnostic,
                    )
                )

        if failures:
            print("")
            print(
                "Static-analysis violations detected:",
                file=sys.stderr,
            )

            for relative_path, diagnostic in failures:
                print(
                    f"\n--- {relative_path.as_posix()} ---",
                    file=sys.stderr,
                )

                if diagnostic:
                    print(diagnostic, file=sys.stderr)
                else:
                    print(
                        "clang-tidy returned a non-zero exit code.",
                        file=sys.stderr,
                    )

            return 1

        print("")
        print(
            "PASS: All supplied translation units passed Clang-Tidy."
        )

        return 0

    except StaticAnalysisError as error:
        print(
            f"ERROR: {error}",
            file=sys.stderr,
        )

        return 2


if __name__ == "__main__":
    sys.exit(main())
