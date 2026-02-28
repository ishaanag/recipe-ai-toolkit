from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

try:
    import yaml
except Exception:
    yaml = None

DEFAULT_MODEL_NAME = "gemini-3-flash-preview"
API_ENV_VARS = ("GEMINI_API_KEY", "GOOGLE_API_KEY")
MAX_OUTPUT_TOKENS = 512
MODEL_FALLBACKS = {
    "gemini-3-flash-preview": "gemini-2.5-flash",
}


@dataclass
class RunStats:
    total: int = 0
    ok: int = 0
    parse_failed: int = 0
    errors: int = 0
    skipped_no_api: int = 0
    skipped_no_ingredients: int = 0


def read_markdown_frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    m = re.search(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return {}
    raw = m.group(1)
    if yaml:
        try:
            return yaml.safe_load(raw) or {}
        except Exception:
            pass

    out: dict[str, Any] = {}
    cur_k = None
    for line in raw.splitlines():
        if not line.strip():
            continue
        if re.match(r"^\s+-\s+", line):
            if cur_k:
                out.setdefault(cur_k, []).append(line.strip().lstrip("- ").strip())
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            cur_k = k.strip()
            val = v.strip()
            out[cur_k] = [] if val == "" else val
    return out


def normalize_servings(raw_servings: Any) -> str:
    if raw_servings is None:
        return "1"
    if isinstance(raw_servings, list) and raw_servings:
        raw_servings = raw_servings[0]
    text = str(raw_servings).strip()
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    if m:
        return m.group(1)
    return text or "1"


def clean_ingredient_line(line: str) -> str:
    line = line.strip()
    line = re.sub(r"^[-*]\s*", "", line)
    line = re.sub(r"^\[\s?[xX]?\s?\]\s*", "", line)
    line = re.sub(r"\s+", " ", line).strip()
    return line


def extract_ingredients(front: dict[str, Any], text: str) -> list[str]:
    if "ingredients" in front and isinstance(front["ingredients"], (list, tuple)):
        return [clean_ingredient_line(str(x)) for x in front["ingredients"] if str(x).strip()]

    headings = ("Ingredients", "Ingredient", "What you need")
    for h in headings:
        m = re.search(rf"(^|\n)#+?\s*{re.escape(h)}\s*\n(.*?)(\n#|\Z)", text, re.S | re.I)
        if m:
            block = m.group(2)
            items = [clean_ingredient_line(ln) for ln in block.splitlines() if ln.strip()]
            items = [x for x in items if x]
            if items:
                return items
    return []


def build_prompt(servings: str, ingredients: list[str]) -> str:
    return (
        "You are a nutrition assistant. Estimate macros per serving from ingredients only. "
        "Return JSON only with keys calories, protein_g, carbs_g, fat_g. "
        "Use calories as integer; macros to 1 decimal place. "
        "No markdown, no prose."
        f"\nServings: {servings}"
        "\nIngredients:\n" + "\n".join(f"- {i}" for i in ingredients)
    )


def out_json_path(src_md_path: Path, input_root: Path, out_dir: Path) -> Path:
    try:
        rel = src_md_path.relative_to(input_root)
        out_path = out_dir / rel.parent / (rel.stem + ".macros.json")
    except Exception:
        out_path = out_dir / (src_md_path.stem + ".macros.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    return out_path


def call_gemini_via_rest(prompt: str, model_name: str, api_key: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0,
            "maxOutputTokens": MAX_OUTPUT_TOKENS,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    try:
        resp = requests.post(url, json=payload, timeout=90)
        body = resp.text
        if resp.status_code >= 400:
            raise RuntimeError(f"Gemini HTTP {resp.status_code}: {body}")
    except requests.RequestException as e:
        raise RuntimeError(f"Gemini request failed: {e}") from e

    data = json.loads(body)
    candidates = data.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"No candidates in Gemini response: {json.dumps(data)[:400]}")

    texts: list[str] = []
    for cand in candidates:
        content = cand.get("content") or {}
        for part in content.get("parts") or []:
            t = part.get("text") if isinstance(part, dict) else None
            if t:
                texts.append(t)

    if texts:
        return "\n".join(texts).strip()
    return json.dumps(data)


def call_gemini(prompt: str, model_name: str, api_key: str) -> str:
    try:
        return call_gemini_via_rest(prompt, model_name, api_key)
    except Exception as e:
        fallback = MODEL_FALLBACKS.get(model_name)
        if fallback and ("not found" in str(e).lower() or "404" in str(e)):
            print(f"WARN: model {model_name} unavailable; retrying with {fallback}")
            return call_gemini_via_rest(prompt, fallback, api_key)
        raise


def extract_json_from_text(text: str) -> dict[str, Any] | None:
    if not text:
        return None

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S | re.I)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except Exception:
            pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        block = text[start : end + 1]
        try:
            return json.loads(block)
        except Exception:
            pass

    try:
        return json.loads(text)
    except Exception:
        pass

    def _num(pattern: str):
        m = re.search(pattern, text, re.I)
        return m.group(1) if m else None

    cal = _num(r"calories\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)")
    protein = _num(r"protein(?:_g)?\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)")
    carbs = _num(r"carbs?(?:_g)?\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)")
    fat = _num(r"fat(?:_g)?\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)")

    if all(v is not None for v in (cal, protein, carbs, fat)):
        return {
            "calories": float(cal),
            "protein_g": float(protein),
            "carbs_g": float(carbs),
            "fat_g": float(fat),
        }
    return None


def normalize_macros(parsed: dict[str, Any] | None) -> dict[str, Any] | None:
    try:
        if not isinstance(parsed, dict):
            return None
        cal = parsed.get("calories")
        protein = parsed.get("protein_g", parsed.get("protein"))
        carbs = parsed.get("carbs_g", parsed.get("carbs"))
        fat = parsed.get("fat_g", parsed.get("fat"))
        if any(v is None for v in (cal, protein, carbs, fat)):
            return None
        return {
            "calories": int(round(float(cal))),
            "protein_g": round(float(protein), 1),
            "carbs_g": round(float(carbs), 1),
            "fat_g": round(float(fat), 1),
        }
    except Exception:
        return None


def output_has_valid_macros(out_path: Path) -> bool:
    if not out_path.exists():
        return False
    try:
        obj = json.loads(out_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return normalize_macros(obj.get("macros")) is not None


def inject_frontmatter_macros(md_path: Path, macros: dict[str, Any]) -> None:
    text = md_path.read_text(encoding="utf-8")
    m = re.search(r"^---\n(.*?)\n---\n", text, re.S)
    macro_lines = []
    if "calories" in macros:
        macro_lines.append(f"calories: {macros['calories']}")
    if "protein" in macros:
        macro_lines.append(f"protein: {macros['protein']}")
    if "carbs" in macros:
        macro_lines.append(f"carbs: {macros['carbs']}")
    if "fat" in macros:
        macro_lines.append(f"fat: {macros['fat']}")

    inject_block = "\n".join(macro_lines) + "\n"
    if m:
        front = m.group(1)
        front_clean = re.sub(r"^\s*(calories|protein|carbs|fat):[^\n]*(?:\n|$)", "", front, flags=re.M)
        new_front = front_clean.rstrip() + "\n" + inject_block
        new_text = re.sub(r"^---\n(.*?)\n---\n", f"---\n{new_front}---\n", text, flags=re.S, count=1)
    else:
        new_front = "---\n" + inject_block + "---\n\n"
        new_text = new_front + text

    md_path.write_text(new_text, encoding="utf-8")


def process_file(path: Path, api_key: str | None, out_dir: Path, input_root: Path, model_name: str, dry_run: bool = False) -> tuple[str, Path]:
    front = read_markdown_frontmatter(path)
    text = path.read_text(encoding="utf-8")
    ingredients = extract_ingredients(front, text)
    title = front.get("title") or front.get("Title") or path.stem
    servings_raw = front.get("servings") or front.get("yield") or front.get("yields") or front.get("YIELDS")
    servings = normalize_servings(servings_raw)

    result: dict[str, Any] = {
        "title": title,
        "source_file": str(path),
        "servings": servings,
        "ingredients": ingredients,
        "model": model_name,
    }
    out_path = out_json_path(path, input_root, out_dir)

    if not api_key:
        result["note"] = "No API key provided; set GEMINI_API_KEY or GOOGLE_API_KEY to call Gemini."
        out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return "skipped_no_api", out_path

    if dry_run:
        result["note"] = "Dry run; not calling API."
        out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return "dry", out_path

    if not ingredients:
        result["note"] = "No ingredients found; skipped API call to reduce cost."
        out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return "skipped_no_ingredients", out_path

    prompt = build_prompt(servings, ingredients)
    try:
        raw = call_gemini(prompt, model_name, api_key)
        parsed = extract_json_from_text(raw)
        macros_norm = normalize_macros(parsed)

        if not macros_norm:
            retry_prompt = prompt + "\nReturn only a single JSON object with keys calories, protein_g, carbs_g, fat_g."
            raw_retry = call_gemini(retry_prompt, model_name, api_key)
            parsed = extract_json_from_text(raw_retry)
            macros_norm = normalize_macros(parsed)
            if not macros_norm:
                raw = raw_retry

        if macros_norm:
            result["macros"] = macros_norm
            fm = {
                "calories": macros_norm["calories"],
                "protein": macros_norm["protein_g"],
                "carbs": macros_norm["carbs_g"],
                "fat": macros_norm["fat_g"],
            }
            inject_frontmatter_macros(path, fm)
            status = "ok"
        else:
            result["raw"] = raw
            status = "parse_failed"

        out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return status, out_path
    except Exception as e:
        result["error"] = str(e)
        out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return "error", out_path


def run(
    input_dir: str,
    out_dir: str,
    pattern: str = "**/*.md",
    model_name: str = DEFAULT_MODEL_NAME,
    start_index: int = 1,
    limit: int = 0,
    skip_existing: bool = False,
    skip_if_frontmatter_present: bool = False,
    dry_run: bool = False,
    sleep_seconds: float = 0.5,
) -> RunStats:
    api_key = None
    for ev in API_ENV_VARS:
        api_key = os.environ.get(ev)
        if api_key:
            break

    inp = Path(input_dir)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    if "**" in pattern:
        import glob as _glob

        files = sorted(Path(p) for p in _glob.glob(os.path.join(str(inp), pattern), recursive=True))
    else:
        files = sorted(inp.glob(pattern))

    if not files:
        print(f"No recipe files found in {inp}")
        return RunStats()

    start = max(start_index, 1)
    if start > len(files):
        print(f"No files to process: start-index {start} is greater than total files {len(files)}")
        return RunStats()

    files = files[start - 1 :]
    if limit and limit > 0:
        files = files[:limit]

    if skip_existing:
        before = len(files)
        files = [f for f in files if not output_has_valid_macros(out_json_path(f, inp, out))]
        skipped = before - len(files)
        if skipped:
            print(f"Skipping {skipped} files with existing valid outputs in {out}")

    if skip_if_frontmatter_present:
        before = len(files)
        kept = []
        for f in files:
            txt = f.read_text(encoding="utf-8")
            has_macros = all(re.search(rf"^\s*{k}:\s*", txt, re.M) for k in ("calories", "protein", "carbs", "fat"))
            if not has_macros:
                kept.append(f)
        files = kept
        skipped = before - len(files)
        if skipped:
            print(f"Skipping {skipped} files with macros already in frontmatter")

    if not files:
        print("No files to process after applying filters")
        return RunStats()

    print(f"Found {len(files)} files; output -> {out}; model={model_name}; api_key_set={bool(api_key)}")
    stats = RunStats(total=len(files))

    for f in files:
        if not f.is_file():
            continue
        status, _ = process_file(f, api_key, out, inp, model_name, dry_run=dry_run)
        if status == "ok":
            stats.ok += 1
            print(f"OK: {f.name}")
            print(f"Injected macros into {f.name}")
        elif status == "parse_failed":
            stats.parse_failed += 1
            print(f"PARSE_FAILED: {f.name}")
        elif status == "error":
            stats.errors += 1
            print(f"ERROR: {f.name}")
        elif status == "skipped_no_api":
            stats.skipped_no_api += 1
            print(f"SKIPPED (no API key): {f.name}")
        elif status == "skipped_no_ingredients":
            stats.skipped_no_ingredients += 1
            print(f"SKIPPED (no ingredients): {f.name}")

        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    print(
        "Done.",
        f"total={stats.total}",
        f"ok={stats.ok}",
        f"parse_failed={stats.parse_failed}",
        f"errors={stats.errors}",
        f"skipped_no_api={stats.skipped_no_api}",
        f"skipped_no_ingredients={stats.skipped_no_ingredients}",
    )
    return stats
