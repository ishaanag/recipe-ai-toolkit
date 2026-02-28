from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from recipe_scrapers import scrape_me


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    )
}

SITE_PRESETS = {
    "cookwell": {
        "index_urls": ["https://www.cookwell.com/discover/collection/all-recipes"],
        "include_patterns": [r"/recipe/"],
        "base_url": "https://www.cookwell.com",
        "tags": ["recipe", "cookwell"],
    },
    "atk": {
        "index_urls": ["https://www.americastestkitchen.com/recipes/all?s=everest_search_popularity_desc&p=10"],
        "include_patterns": [r"/recipes/"],
        "base_url": "https://www.americastestkitchen.com",
        "tags": ["recipe", "atk"],
    },
}


@dataclass
class RecipeData:
    title: str
    source_url: str
    image: str | None
    ingredients: list[str]
    instructions: list[str]
    total_time: str | None
    yields: str | None


@dataclass
class ScrapeStats:
    discovered_links: int = 0
    processed: int = 0
    saved: int = 0
    failed: int = 0


def sanitize_filename(name: str) -> str:
    cleaned = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_", "(", ")")).strip()
    return cleaned or "untitled-recipe"


def normalize_url(href: str, base_url: str | None) -> str | None:
    if not href:
        return None
    href = href.strip()
    if href.startswith("javascript:") or href.startswith("mailto:"):
        return None
    if href.startswith("http://") or href.startswith("https://"):
        return href.split("#")[0]
    if base_url:
        return urljoin(base_url, href).split("#")[0]
    return None


def discover_links(index_url: str, include_patterns: list[str], base_url: str | None, timeout: int) -> list[str]:
    resp = requests.get(index_url, headers=DEFAULT_HEADERS, timeout=timeout)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    patterns = [re.compile(p) for p in include_patterns]
    links: set[str] = set()
    for a in soup.find_all("a", href=True):
        full = normalize_url(a["href"], base_url or index_url)
        if not full:
            continue
        path = urlparse(full).path
        if any(p.search(path) for p in patterns):
            links.add(full.split("?")[0])
    return sorted(links)


def parse_json_ld_recipe(html: str, source_url: str) -> RecipeData:
    soup = BeautifulSoup(html, "html.parser")
    scripts = soup.find_all("script", type="application/ld+json")

    for s in scripts:
        raw = s.string or s.get_text() or ""
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw)
        except Exception:
            continue

        candidates = obj if isinstance(obj, list) else [obj]
        for c in candidates:
            if not isinstance(c, dict):
                continue
            t = c.get("@type")
            types = t if isinstance(t, list) else [t]
            types = [str(x).lower() for x in types if x]
            if "recipe" not in types:
                continue

            title = c.get("name") or c.get("headline") or "Untitled"
            image = c.get("image")
            if isinstance(image, list):
                image = image[0] if image else None
            ingredients = c.get("recipeIngredient") or c.get("ingredients") or []

            instructions: list[str] = []
            raw_inst = c.get("recipeInstructions") or []
            for step in raw_inst:
                if isinstance(step, str):
                    instructions.append(step.strip())
                elif isinstance(step, dict):
                    txt = step.get("text") or step.get("name")
                    if txt:
                        instructions.append(str(txt).strip())

            total_time = c.get("totalTime") or c.get("cookTime")
            yields = c.get("recipeYield")

            return RecipeData(
                title=str(title).strip(),
                source_url=source_url,
                image=str(image).strip() if image else None,
                ingredients=[str(i).strip() for i in ingredients if str(i).strip()],
                instructions=[i for i in instructions if i],
                total_time=str(total_time).strip() if total_time else None,
                yields=str(yields).strip() if yields else None,
            )

    raise ValueError("No Recipe JSON-LD found")


def extract_recipe_from_html(html: str, source_url: str) -> RecipeData:
    # Use recipe-scrapers first via temporary file URL for reliability with SSL-protected sites.
    with NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as tf:
        tf.write(html)
        tmp_path = tf.name

    try:
        sc = scrape_me(f"file://{tmp_path}")
        title = (sc.title() or "").strip()
        ingredients = [str(i).strip() for i in (sc.ingredients() or []) if str(i).strip()]
        instructions = [str(i).strip() for i in (sc.instructions_list() or []) if str(i).strip()]
        if not title:
            raise ValueError("Empty title from recipe-scrapers")

        image = None
        try:
            image = sc.image()
        except Exception:
            image = None

        total_time = None
        try:
            total_time = sc.total_time()
        except Exception:
            total_time = None

        yields = None
        try:
            yields = sc.yields()
        except Exception:
            yields = None

        return RecipeData(
            title=title,
            source_url=source_url,
            image=str(image).strip() if image else None,
            ingredients=ingredients,
            instructions=instructions,
            total_time=str(total_time).strip() if total_time else None,
            yields=str(yields).strip() if yields else None,
        )
    except Exception:
        return parse_json_ld_recipe(html, source_url)
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass


def write_markdown(recipe: RecipeData, output_dir: Path, tags: list[str]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    filepath = output_dir / f"{sanitize_filename(recipe.title)}.md"

    with filepath.open("w", encoding="utf-8") as f:
        f.write("---\n")
        f.write(f"tags: [{', '.join(tags)}]\n")
        f.write(f"source: {recipe.source_url}\n")
        if recipe.total_time:
            f.write(f"time: {recipe.total_time}\n")
        if recipe.yields:
            f.write(f"yields: {recipe.yields}\n")
        f.write("---\n\n")

        f.write(f"# {recipe.title}\n\n")
        if recipe.image:
            f.write(f"![Image]({recipe.image})\n\n")

        f.write("## Ingredients\n")
        if recipe.ingredients:
            for i in recipe.ingredients:
                f.write(f"- [ ] {i}\n")
        else:
            f.write("*No ingredients extracted*\n")
        f.write("\n")

        f.write("## Instructions\n")
        if recipe.instructions:
            for idx, step in enumerate(recipe.instructions, start=1):
                f.write(f"{idx}. {step}\n\n")
        else:
            f.write("*No instructions extracted*\n")

    return filepath


def scrape(
    output_dir: str,
    urls: list[str] | None = None,
    index_urls: list[str] | None = None,
    include_patterns: list[str] | None = None,
    base_url: str | None = None,
    tags: list[str] | None = None,
    delay_seconds: float = 1.0,
    timeout: int = 25,
    max_links: int = 0,
    dry_run: bool = False,
) -> ScrapeStats:
    urls = list(urls or [])
    include_patterns = include_patterns or [r"/recipe/", r"/recipes/"]
    tags = tags or ["recipe", "imported"]

    stats = ScrapeStats()

    for idx in index_urls or []:
        try:
            found = discover_links(idx, include_patterns=include_patterns, base_url=base_url or idx, timeout=timeout)
            urls.extend(found)
        except Exception as e:
            print(f"WARN: Could not discover links from {idx}: {e}")

    # de-dup while preserving order
    deduped: list[str] = []
    seen: set[str] = set()
    for u in urls:
        if u and u not in seen:
            seen.add(u)
            deduped.append(u)

    if max_links > 0:
        deduped = deduped[:max_links]

    stats.discovered_links = len(deduped)
    print(f"Discovered {stats.discovered_links} recipe links")

    if dry_run:
        sample = deduped[: min(10, len(deduped))]
        if sample:
            print("Sample links:")
            for u in sample:
                print("-", u)
        return stats

    out_dir = Path(output_dir)

    for i, link in enumerate(deduped, start=1):
        print(f"[{i}/{len(deduped)}] {link}")
        stats.processed += 1
        try:
            resp = requests.get(link, headers=DEFAULT_HEADERS, timeout=timeout)
            resp.raise_for_status()
            recipe = extract_recipe_from_html(resp.text, link)
            path = write_markdown(recipe, out_dir, tags=tags)
            stats.saved += 1
            print(f"✅ Saved: {path.name}")
        except Exception as e:
            stats.failed += 1
            print(f"❌ Failed: {link} ({e})")

        if delay_seconds > 0:
            time.sleep(delay_seconds)

    print(
        "Done.",
        f"discovered_links={stats.discovered_links}",
        f"processed={stats.processed}",
        f"saved={stats.saved}",
        f"failed={stats.failed}",
    )
    return stats
