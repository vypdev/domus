"""Local Markdown link validation without fetching external resources."""

from pathlib import Path
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt


def validate_links(root: Path) -> tuple[str, ...]:
    """Validate links in owned documentation; retain the upstream template unchanged."""
    parser = MarkdownIt()
    documents = [root / "README.md"]
    documents.extend(sorted((root / "docs").rglob("*.md")))
    documents.extend(sorted((root / "specs").glob("*.md")))
    errors = []
    for document in documents:
        if document == root / "specs" / "_template.md":
            continue
        if not document.is_file():
            errors.append(f"Missing document: {document.relative_to(root)}")
            continue
        for token in parser.parse(document.read_text(encoding="utf-8")):
            for child in token.children or []:
                if child.type not in {"link_open", "image"}:
                    continue
                href = str(child.attrGet("href" if child.type == "link_open" else "src") or "")
                parsed = urlsplit(href)
                if parsed.scheme or parsed.netloc or not parsed.path:
                    continue
                relative = unquote(parsed.path)
                target = (
                    (root / relative.lstrip("/"))
                    if relative.startswith("/")
                    else (document.parent / relative)
                )
                resolved = target.resolve()
                if not resolved.is_relative_to(root.resolve()):
                    errors.append(
                        f"{document.relative_to(root)}: link leaves repository: {relative}"
                    )
                elif not resolved.exists():
                    errors.append(f"{document.relative_to(root)}: missing target: {relative}")
    return tuple(errors)
