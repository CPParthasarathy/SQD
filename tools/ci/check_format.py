#!/usr/bin/env python3
"""Verify repository-owned C and C++ files using pinned clang-format."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence


EXPECTED_CLANG_FORMAT_VERSION = "clang-format version 22.1.8"

SOURCE_ROOTS = (
    "components",
    "main",
    "verification",
)

SOURCE_SUFFIXES = frozenset(
    {
        ".c",
        ".cc",
        ".cpp",
        ".cxx",
        ".h",
        ".hh",
        ".hpp",
        ".hxx",
    }
)


class FormatCheckError(RuntimeError):
    """Raised when the formatting gate cannot execute reliably."""


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
        raise FormatCheckError(
            f"Unable to execute command '{arguments[0]}': {error}"
        ) from error


def resolve_formatter(requested_path: Path | None) -> Path:
    """Resolve clang-format from an explicit path or PATH."""

    if requested_path is not None:
        formatter = requested_path.expanduser().resolve()
    else:
        discovered = shutil.which("clang-format")

        if discovered is None:
            raise FormatCheckError(
                "clang-format was not supplied and was not found on PATH."
            )

        formatter = Path(discovered).resolve()

    if not formatter.is_file():
        raise FormatCheckError(
            f"clang-format executable does not exist: {formatter}"
        )

    return formatter


def verify_repository(repo_root: Path) -> None:
    """Confirm that the selected directory is the Git repository root."""

    result = run_command(
        ("git", "rev-parse", "--show-toplevel"),
        cwd=repo_root,
    )

    if result.returncode != 0:
        diagnostic = (result.stderr or result.stdout).strip()

        raise FormatCheckError(
            f"Unable to identify the Git repository root: {diagnostic}"
        )

    discovered_root = Path(result.stdout.strip()).resolve()

    if discovered_root != repo_root:
        raise FormatCheckError(
            "Selected repository root does not match Git: "
            f"selected={repo_root}, git={discovered_root}"
        )


def discover_source_files(repo_root: Path) -> list[Path]:
    """Return tracked and non-ignored untracked C/C++ source paths."""

    result = subprocess.run(
        [
            "git",
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
            "--",
            *SOURCE_ROOTS,
        ],
        cwd=repo_root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if result.returncode != 0:
        diagnostic = result.stderr.decode(
            "utf-8",
            errors="replace",
        ).strip()

        raise FormatCheckError(
            f"Unable to enumerate repository source files: {diagnostic}"
        )

    relative_paths = []

    for encoded_path in result.stdout.split(b"\0"):
        if not encoded_path:
            continue

        relative_path = Path(encoded_path.decode("utf-8"))

        if relative_path.suffix.lower() not in SOURCE_SUFFIXES:
            continue

        absolute_path = repo_root / relative_path

        if not absolute_path.is_file():
            raise FormatCheckError(
                f"Enumerated source file does not exist: {relative_path}"
            )

        relative_paths.append(relative_path)

    source_files = sorted(
        set(relative_paths),
        key=lambda path: path.as_posix(),
    )

    if not source_files:
        raise FormatCheckError(
            "No repository-owned C or C++ source files were found."
        )

    return source_files


def verify_formatter_version(
    formatter: Path,
    repo_root: Path,
) -> str:
    """Require the exact controlled clang-format release."""

    result = run_command(
        (str(formatter), "--version"),
        cwd=repo_root,
    )

    version = (result.stdout or result.stderr).strip()

    if result.returncode != 0:
        raise FormatCheckError(
            f"Unable to query clang-format version: {version}"
        )

    if version != EXPECTED_CLANG_FORMAT_VERSION:
        raise FormatCheckError(
            "Unexpected clang-format version: "
            f"expected='{EXPECTED_CLANG_FORMAT_VERSION}', "
            f"actual='{version}'"
        )

    return version


def check_file(
    formatter: Path,
    repo_root: Path,
    relative_path: Path,
) -> tuple[bool, str]:
    """Run clang-format in non-modifying verification mode."""

    absolute_path = repo_root / relative_path

    result = run_command(
        (
            str(formatter),
            "--dry-run",
            "--Werror",
            "--style=file",
            "--fallback-style=none",
            str(absolute_path),
        ),
        cwd=repo_root,
    )

    diagnostic = "\n".join(
        part.strip()
        for part in (result.stdout, result.stderr)
        if part.strip()
    )

    return result.returncode == 0, diagnostic


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""

    default_repo_root = Path(__file__).resolve().parents[2]

    parser = argparse.ArgumentParser(
        description=(
            "Fail when repository-owned C/C++ files differ from the "
            "controlled .clang-format contract."
        )
    )

    parser.add_argument(
        "--repo-root",
        type=Path,
        default=default_repo_root,
        help="Repository root. Defaults to the root containing this script.",
    )

    parser.add_argument(
        "--clang-format",
        type=Path,
        default=None,
        help="Explicit path to the controlled clang-format executable.",
    )

    return parser.parse_args()


def main() -> int:
    """Execute the formatting gate."""

    arguments = parse_arguments()
    repo_root = arguments.repo_root.expanduser().resolve()

    try:
        if not repo_root.is_dir():
            raise FormatCheckError(
                f"Repository root does not exist: {repo_root}"
            )

        verify_repository(repo_root)

        formatter = resolve_formatter(arguments.clang_format)
        formatter_version = verify_formatter_version(
            formatter,
            repo_root,
        )

        source_files = discover_source_files(repo_root)

        print("B4.1 formatting check")
        print(f"Repository: {repo_root}")
        print(f"Formatter:  {formatter_version}")
        print(f"Files:      {len(source_files)}")
        print("")

        failures: list[tuple[Path, str]] = []

        for relative_path in source_files:
            passed, diagnostic = check_file(
                formatter,
                repo_root,
                relative_path,
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
            print("Formatting violations detected:", file=sys.stderr)

            for relative_path, diagnostic in failures:
                print(
                    f"\n--- {relative_path.as_posix()} ---",
                    file=sys.stderr,
                )

                if diagnostic:
                    print(diagnostic, file=sys.stderr)
                else:
                    print(
                        "clang-format returned a non-zero exit code.",
                        file=sys.stderr,
                    )

            print(
                "\nRun clang-format 22.1.8 with --style=file "
                "on the reported files.",
                file=sys.stderr,
            )

            return 1

        print("")
        print("PASS: All repository-owned C/C++ files are formatted.")

        return 0

    except FormatCheckError as error:
        print(
            f"ERROR: {error}",
            file=sys.stderr,
        )

        return 2


if __name__ == "__main__":
    sys.exit(main())
