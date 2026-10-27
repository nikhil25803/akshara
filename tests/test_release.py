from pathlib import Path

import pytest

from akshara.helpers.release import validate_release


def release_files(root: Path, changelog_section: str) -> None:
    (root / "src/akshara").mkdir(parents=True)
    (root / "pyproject.toml").write_text('[project]\nversion = "0.0.1"\n')
    (root / "src/akshara/__init__.py").write_text('__version__ = "0.0.1"\n')
    (root / "CHANGELOG.md").write_text(
        f"# Changelog\n\n{changelog_section}\n\n[0.0.1]: https://example.test/v0.0.1\n"
    )


def test_release_metadata_and_notes_are_extracted(tmp_path: Path) -> None:
    release_files(tmp_path, "## [0.0.1] - 2026-10-27\n\n### Added\n\n- OCR")

    version, notes = validate_release(tmp_path, "v0.0.1")

    assert version == "0.0.1"
    assert notes == "### Added\n\n- OCR"


def test_release_tag_must_match_project_version(tmp_path: Path) -> None:
    release_files(tmp_path, "## [0.0.1] - 2026-10-27\n\n- OCR")

    with pytest.raises(ValueError, match="versions must match"):
        validate_release(tmp_path, "v0.0.2")


@pytest.mark.parametrize(
    "section",
    [
        "## [0.0.1] - not-a-date\n\n- OCR",
        "## [0.0.1] - 2026-10-27",
    ],
)
def test_release_requires_dated_nonempty_changelog_section(
    tmp_path: Path, section: str
) -> None:
    release_files(tmp_path, section)

    with pytest.raises(ValueError, match="CHANGELOG.md"):
        validate_release(tmp_path, "v0.0.1")
