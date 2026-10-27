import argparse
import os
import re
import tomllib
from pathlib import Path


def validate_release(root: Path, tag: str | None = None) -> tuple[str, str]:
    project = tomllib.loads((root / "pyproject.toml").read_text())
    project_version = project["project"]["version"]
    tag = tag or f"v{project_version}"

    tag_match = re.fullmatch(r"v(\d+\.\d+\.\d+)", tag)
    if not tag_match:
        raise ValueError(f"Release tag must be vMAJOR.MINOR.PATCH, got {tag}")
    release_version = tag_match.group(1)

    package_text = (root / "src/akshara/__init__.py").read_text()
    package_match = re.search(r'^__version__ = "([^"]+)"$', package_text, re.MULTILINE)
    package_version = package_match.group(1) if package_match else None
    if project_version != release_version or package_version != release_version:
        raise ValueError(
            "Tag, pyproject.toml, and package versions must match: "
            f"{tag=}, {project_version=}, {package_version=}"
        )

    changelog = (root / "CHANGELOG.md").read_text()
    heading = re.search(
        rf"^## \[{re.escape(release_version)}\] - \d{{4}}-\d{{2}}-\d{{2}}$",
        changelog,
        re.MULTILINE,
    )
    if not heading:
        raise ValueError(f"CHANGELOG.md needs a dated [{release_version}] section")
    boundary = re.search(
        r"^(?:## |\[[^]]+\]:)", changelog[heading.end() :], re.MULTILINE
    )
    end = heading.end() + boundary.start() if boundary else len(changelog)
    notes = changelog[heading.end() : end].strip()
    if not notes:
        raise ValueError(f"CHANGELOG.md section [{release_version}] is empty")
    return release_version, notes


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Akshara release metadata")
    parser.add_argument("--tag", help="Git tag; defaults to v<project version>")
    parser.add_argument("--notes-file", type=Path)
    args = parser.parse_args()

    try:
        version, notes = validate_release(Path.cwd(), args.tag)
    except (OSError, KeyError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    if args.notes_file:
        args.notes_file.write_text(notes + "\n")
    if github_output := os.environ.get("GITHUB_OUTPUT"):
        with Path(github_output).open("a") as output:
            output.write(f"version={version}\n")
    print(f"Release metadata valid for v{version}")


if __name__ == "__main__":
    main()
