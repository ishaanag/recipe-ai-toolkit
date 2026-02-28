from __future__ import annotations

import argparse
from pathlib import Path

from .core import SITE_PRESETS, scrape


def _read_urls_file(path: str | None) -> list[str]:
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        return []
    return [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.strip().startswith("#")]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="recipe-scrape")
    p.add_argument("--output-dir", "-o", default="export", help="Directory to write markdown files")
    p.add_argument("--url", action="append", default=[], help="Recipe URL to scrape (repeatable)")
    p.add_argument("--urls-file", help="Path to newline-delimited recipe URLs")
    p.add_argument("--index-url", action="append", default=[], help="Index/list page URL to discover recipe links from")
    p.add_argument("--include-pattern", action="append", default=[], help="Regex pattern that link paths must match during discovery")
    p.add_argument("--base-url", help="Base URL used to resolve relative links in index pages")
    p.add_argument("--tag", action="append", default=[], help="Frontmatter tag to add (repeatable)")
    p.add_argument("--preset", choices=sorted(SITE_PRESETS.keys()), help="Use a built-in site preset")
    p.add_argument("--delay-seconds", type=float, default=1.0, help="Delay between requests")
    p.add_argument("--timeout", type=int, default=25, help="HTTP timeout in seconds")
    p.add_argument("--max-links", type=int, default=0, help="Limit number of discovered links (0 = no limit)")
    p.add_argument("--dry-run", action="store_true", help="Discover links only; do not fetch/save recipes")
    return p


def main() -> None:
    args = build_parser().parse_args()

    urls = list(args.url)
    urls.extend(_read_urls_file(args.urls_file))

    index_urls = list(args.index_url)
    include_patterns = list(args.include_pattern)
    tags = list(args.tag)
    base_url = args.base_url

    if args.preset:
        preset = SITE_PRESETS[args.preset]
        if not index_urls:
            index_urls = list(preset.get("index_urls", []))
        if not include_patterns:
            include_patterns = list(preset.get("include_patterns", []))
        if not base_url:
            base_url = preset.get("base_url")
        if not tags:
            tags = list(preset.get("tags", []))

    scrape(
        output_dir=args.output_dir,
        urls=urls,
        index_urls=index_urls,
        include_patterns=include_patterns,
        base_url=base_url,
        tags=tags,
        delay_seconds=args.delay_seconds,
        timeout=args.timeout,
        max_links=args.max_links,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
