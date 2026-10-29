"""Exercise real Markdown parsing and isolated repository path resolution."""

from pathlib import Path

from domus_tooling.docs import validate_links


def write(root: Path, relative: str, content: str = "") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_empty_repository_reports_missing_readme(tmp_path: Path) -> None:
    assert validate_links(tmp_path) == ("Missing document: README.md",)


def test_relative_rooted_encoded_and_directory_links(tmp_path: Path) -> None:
    write(tmp_path, "README.md", "[Guide](docs/guide.md#section) [Image](docs/with%20space.png)")
    write(
        tmp_path, "docs/guide.md", "[Home](/README.md) [Folder](../docs/) ![Art](with%20space.png)"
    )
    write(tmp_path, "docs/with space.png")
    assert validate_links(tmp_path) == ()


def test_external_links_anchors_and_code_do_not_become_local_paths(tmp_path: Path) -> None:
    write(
        tmp_path,
        "README.md",
        """[Web](https://example.invalid/x)
[Mail](mailto:person@example.invalid) [Network](//example.invalid/path) [Here](#section)
`[Inline](absent-inline.md)`
```markdown
[Code](absent-code.md)
```
""",
    )
    assert validate_links(tmp_path) == ()


def test_missing_targets_are_reported_for_docs_and_specs(tmp_path: Path) -> None:
    write(tmp_path, "README.md", "[Missing](missing.md)")
    write(tmp_path, "docs/nested/guide.md", "![Missing](image.png)")
    write(tmp_path, "specs/capability.md", "[Missing](missing.md?view=raw)")
    assert validate_links(tmp_path) == (
        "README.md: missing target: missing.md",
        "docs/nested/guide.md: missing target: image.png",
        "specs/capability.md: missing target: missing.md",
    )


def test_reference_template_placeholders_are_excluded_explicitly(tmp_path: Path) -> None:
    write(tmp_path, "README.md")
    write(tmp_path, "specs/_template.md", "[Placeholder](does-not-exist.md)")
    assert validate_links(tmp_path) == ()


def test_link_cannot_escape_repository(tmp_path: Path) -> None:
    write(tmp_path, "README.md", "[Outside](../outside.md)")
    assert validate_links(tmp_path) == ("README.md: link leaves repository: ../outside.md",)
