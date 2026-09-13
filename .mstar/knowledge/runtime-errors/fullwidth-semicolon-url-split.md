---
module: check-source-links
date: 2026-08-25
problem_type: runtime_error
category: runtime-errors
severity: high
plan_id: audit-baseline-refresh
applies_when:
  - "Editing scripts/check-source-links.py extraction or probing"
  - "Adding source URLs to course pages (sources.md / syllabus.md / index.md)"
tags:
  - url-extraction
  - fullwidth-semicolon
  - unicode
  - probe
symptoms:
  - "check-source-links.py --update-baseline aborts with UnicodeEncodeError: 'ascii' codec can't encode character '\\uff1b'"
  - "--offline extraction prints one merged URL (…html；…pdf) instead of two URLs"
  - "Baseline keeps the merged URL as inconclusive indefinitely"
root_cause: "BARE_URL_RE did not exclude the fullwidth semicolon（；U+FF1B）from the URL character class, so two URLs separated by it in a markdown table were extracted as one string; urllib then failed to ASCII-encode the request line, and probe() had no except clause for UnicodeEncodeError, aborting the whole run."
resolution_type: code_fix
---

# Fullwidth semicolon merges two bare URLs and crashes the link probe

## Problem

A markdown table cell in `content/jiangsu/courses/04751/sources.md` listed two official URLs
joined by a **fullwidth semicolon** （`；` U+FF1B）:

```markdown
| 考纲 | https://www.jseea.cn/webfile/.../7397162260776357888.html；https://www.jseea.cn/webfile/upload/.../14-59-1607281034810553.pdf | ... |
```

`BARE_URL_RE = re.compile(r"(?<![(\[])\bhttps?://[^\s)\]<>`\"']+")` treated `；` as part of the URL
(it is not in the excluded character class), so the two URLs were extracted as **one** merged string.
During probing, Python's `urllib` request layer encoded the request line in ASCII and raised
`UnicodeEncodeError` — which `probe()` did not catch (its except clauses cover
a URLError / OSError / socket timeout / SSL error), aborting the **entire** run
instead of recording the URL as `inconclusive`.

## Symptoms

- Running `scripts/check-source-links.py` with `--update-baseline` crashed with
  `UnicodeEncodeError: 'ascii' codec can't encode character '\uff1b'` (position 65).
- `--offline` extraction printed the merged URL `...html；...pdf` as a single entry.
- The stale baseline carried the merged URL as `inconclusive` forever.

## What Didn't Work

- Stripping `；` only in `normalize_url()` (`.rstrip(".,;:。，、)）]】>")`) — rstrip only trims
  the **tail**; a separator in the **middle** of the matched span is untouched.
- Catching the error only in `probe()` — it prevents the crash but leaves the merged
  URL as a bogus baseline entry; the split must happen at extraction time.

## Solution

1. **Split at extraction**: add `；` to the `BARE_URL_RE` excluded character class
   (`[^\s)\]<>`"';；]`) so the regex stops at the CJK separator and yields two URLs.
2. **Keep the tail-strip** for the fullwidth semicolon in `normalize_url()` (defense in depth
   for a trailing separator).
3. **Defensive probe**: add `UnicodeEncodeError` to the `probe()` retry/except tuple so any
   future non-ASCII URL degrades to `inconclusive` instead of aborting the run.
4. Regression tests: `test_normalize_url_fullwidth_semicolon`,
   `test_bare_url_split_on_fullwidth_semicolon` in `tests/test_check_source_links.py`.

## Why This Works

The excluded-char-class fix makes extraction treat `；` as a separator by construction, so
URLs are split before any probe happens. The defensive except guarantees the monitor keeps
running even if a URL with an unusual character slips through.

## Prevention

- When writing course pages, separate multiple URLs with **ASCII** punctuation (space or `,`),
  never fullwidth punctuation.
- Any change to `BARE_URL_RE` should keep the CJK separators（`，`、`；`、`、`）excluded.
- The monitor run should be re-verified after adding any new official URL row
  (a `scripts/check-source-links.py` smoke run with `--offline`).
