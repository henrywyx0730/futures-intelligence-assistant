"""Fetch and validate a basic RSS feed from the command line."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from urllib.error import URLError
from urllib.request import urlopen
from xml.etree import ElementTree


def main(argv: Sequence[str] | None = None) -> int:
    """Fetch an RSS URL and print a concise feed summary."""
    parser = argparse.ArgumentParser(description="Validate an RSS feed URL.")
    parser.add_argument("url", help="RSS feed URL to validate")
    args = parser.parse_args(argv)

    try:
        with urlopen(args.url, timeout=10.0) as response:
            feed_content = response.read()
    except (OSError, URLError) as error:
        print(f"Network error: {error}")
        return 1

    try:
        root = ElementTree.fromstring(feed_content)
    except ElementTree.ParseError as error:
        print(f"Invalid XML: {error}")
        return 1

    channel = root.find("channel")
    if channel is None:
        print("Invalid RSS feed: channel element not found")
        return 1

    title = _text(channel.find("title")) or "(untitled feed)"
    items = channel.findall("item")
    print(f"Feed title: {title}")
    print(f"Number of items: {len(items)}")
    for item in items[:3]:
        print(f"- {_text(item.find('title')) or '(untitled item)'}")
    return 0


def _text(element: ElementTree.Element | None) -> str | None:
    """Return stripped element text when present."""
    if element is None or element.text is None:
        return None
    return element.text.strip() or None


if __name__ == "__main__":
    raise SystemExit(main())
