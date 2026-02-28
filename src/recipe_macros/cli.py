from __future__ import annotations

import argparse

from .core import DEFAULT_MODEL_NAME, run


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="recipe-macros")
    p.add_argument("--input", "-i", default="recipes", help="Input folder with recipe markdown files")
    p.add_argument("--out", "-o", default="recipes_with_macros", help="Output folder for macros JSON")
    p.add_argument("--pattern", default="**/*.md", help="Glob pattern for recipe files")
    p.add_argument("--model", default=DEFAULT_MODEL_NAME, help=f"Gemini model name (default: {DEFAULT_MODEL_NAME})")
    p.add_argument("--start-index", type=int, default=1, help="1-based index in sorted files to start from")
    p.add_argument("--limit", type=int, default=0, help="Process only first N files after start-index (0 = no limit)")
    p.add_argument("--skip-existing", action="store_true", help="Skip files with valid existing output JSON")
    p.add_argument("--skip-if-frontmatter-present", action="store_true", help="Skip files that already have calories/protein/carbs/fat in frontmatter")
    p.add_argument("--dry-run", action="store_true", help="Do everything except call Gemini")
    p.add_argument("--sleep-seconds", type=float, default=0.5, help="Sleep between API calls")
    return p


def main() -> None:
    args = build_parser().parse_args()
    run(
        input_dir=args.input,
        out_dir=args.out,
        pattern=args.pattern,
        model_name=args.model,
        start_index=args.start_index,
        limit=args.limit,
        skip_existing=args.skip_existing,
        skip_if_frontmatter_present=args.skip_if_frontmatter_present,
        dry_run=args.dry_run,
        sleep_seconds=args.sleep_seconds,
    )


if __name__ == "__main__":
    main()
