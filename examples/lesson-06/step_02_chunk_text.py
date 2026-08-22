"""Step 2: Split policy Markdown into paragraph-sized chunks."""

from __future__ import annotations

import argparse
from pathlib import Path


POLICY_DIR = Path(__file__).parents[2] / "policies"


def chunk_text(markdown: str) -> list[str]:
    """Return non-empty Markdown paragraphs without the document title."""
    return [
        paragraph.replace("\n", " ").strip()
        for paragraph in markdown.split("\n\n")
        if paragraph.strip() and not paragraph.lstrip().startswith("# ")
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Show how one policy is split into chunks.")
    parser.add_argument("policy_id", nargs="?", default="annual-leave-policy")
    args = parser.parse_args()

    path = POLICY_DIR / f"{args.policy_id}.md"
    if not path.is_file():
        raise RuntimeError(f"Unknown policy: {args.policy_id}")

    for index, chunk in enumerate(chunk_text(path.read_text(encoding="utf-8")), start=1):
        print(f"Chunk {index}")
        print(chunk)
        print()


if __name__ == "__main__":
    main()
