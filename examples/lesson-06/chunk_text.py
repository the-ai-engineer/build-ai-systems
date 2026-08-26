"""Split policy Markdown into paragraph-sized chunks."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path


POLICY_DIR = Path(__file__).parents[2] / "policies"
DEFAULT_POLICY_ID = "annual-leave-policy"


def chunk_text(markdown: str) -> list[str]:
    """Return non-empty Markdown paragraphs without the document title."""
    return [
        paragraph.replace("\n", " ").strip()
        for paragraph in markdown.split("\n\n")
        if paragraph.strip() and not paragraph.lstrip().startswith("# ")
    ]


def show_chunks(policy_id: str = DEFAULT_POLICY_ID) -> None:
    """Print the chunks for one policy."""
    path = POLICY_DIR / f"{policy_id}.md"
    if not path.is_file():
        raise RuntimeError(f"Unknown policy: {policy_id}")

    for index, chunk in enumerate(chunk_text(path.read_text(encoding="utf-8")), start=1):
        print(f"Chunk {index}")
        print(chunk)
        print()


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Show how one policy is split into chunks.")
    parser.add_argument("policy_id", nargs="?", default=DEFAULT_POLICY_ID)
    args = parser.parse_args(argv)
    show_chunks(args.policy_id)


if __name__ == "__main__":
    main([] if Path(sys.argv[0]).stem == "ipykernel_launcher" else None)
