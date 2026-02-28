# Recipe AI Toolkit

Two command-line tools:

- `recipe-scrape`: scrape recipe webpages into Markdown files
- `recipe-macros`: estimate per-serving macros from Markdown recipes using Gemini and write results back to frontmatter

## 1) First-time setup (copy/paste)

Open this folder in VS Code, then open a terminal (`Terminal` → `New Terminal`) and run:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
```

Check that commands are installed:

```bash
recipe-scrape --help
recipe-macros --help
```

## 2) Quick start: scrape Cookwell into `sample_scrape`

### Step A: discovery test (safe, no files written)

```bash
recipe-scrape --preset cookwell --dry-run --max-links 10
```

### Step B: actual scrape (writes Markdown files)

```bash
recipe-scrape --preset cookwell --output-dir sample_scrape --max-links 10
```

### Step C: verify output

```bash
ls sample_scrape
find sample_scrape -name "*.md" | head
```

## 3) Add macro estimates to scraped files

Set your Gemini key (required for macro estimation):

```bash
export GEMINI_API_KEY="YOUR_KEY"
```

Run macros on the scraped files:

```bash
recipe-macros --input sample_scrape --out recipes_with_macros
```

What you get:

- JSON outputs in `recipes_with_macros/` (mirrors folder structure)
- Updated Markdown frontmatter with: `calories`, `protein`, `carbs`, `fat`

## 4) Everyday workflow in a new terminal

Each time you reopen VS Code, run:

```bash
source .venv/bin/activate
```

If command not found, re-install editable package:

```bash
python3 -m pip install -e .
```

## 5) Common commands

### Scraper

Single URL:

```bash
recipe-scrape --output-dir sample_scrape --url https://example.com/recipe/foo
```

From URL file (`urls.txt`, one URL per line):

```bash
recipe-scrape --output-dir sample_scrape --urls-file urls.txt
```

ATK preset:

```bash
recipe-scrape --preset atk --output-dir sample_scrape
```

### Macros

Process first 25 files:

```bash
recipe-macros --input sample_scrape --limit 25
```

Resume from file 26:

```bash
recipe-macros --input sample_scrape --start-index 26
```

Skip files with existing JSON output:

```bash
recipe-macros --input sample_scrape --skip-existing
```

Dry-run parsing (no Gemini call):

```bash
recipe-macros --input sample_scrape --dry-run --limit 5
```

## 6) Compatibility launchers

These are equivalent to the installed CLIs:

```bash
python3 run_recipe_scrape.py ...
python3 run_recipe_macros.py ...
```

## 7) Troubleshooting

### `recipe-scrape: command not found`

```bash
source .venv/bin/activate
python3 -m pip install -e .
```

### Macro run says missing API key

```bash
export GEMINI_API_KEY="YOUR_KEY"
```

You can also use `GOOGLE_API_KEY`.

### Keep API key across sessions

For zsh:

```bash
echo 'export GEMINI_API_KEY="YOUR_KEY"' >> ~/.zshrc
source ~/.zshrc
```

## 8) CLI reference

### `recipe-scrape`

```text
recipe-scrape [--output-dir DIR] [--url URL ...] [--urls-file FILE]
			  [--index-url URL ...] [--include-pattern REGEX ...]
			  [--base-url URL] [--tag TAG ...] [--preset atk|cookwell]
			  [--delay-seconds N] [--timeout SEC] [--max-links N] [--dry-run]
```

### `recipe-macros`

```text
recipe-macros [--input DIR] [--out DIR] [--pattern GLOB] [--model NAME]
			  [--start-index N] [--limit N] [--skip-existing]
			  [--skip-if-frontmatter-present] [--dry-run] [--sleep-seconds N]
```
