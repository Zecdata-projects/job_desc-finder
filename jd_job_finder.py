#!/usr/bin/env python3
"""Find job posting links and company names from batch job descriptions."""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

JOB_POSTING_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"linkedin\.com/jobs/view/", re.I), "LinkedIn"),
    (re.compile(r"indeed\.com/(viewjob|rc/clk|pagead|job/)", re.I), "Indeed"),
    (re.compile(r"glassdoor\.[^/]+/job-listing/", re.I), "Glassdoor"),
    (re.compile(r"boards\.greenhouse\.io/.+/jobs/\d+", re.I), "Greenhouse"),
    (re.compile(r"jobs\.lever\.co/[^/]+/[a-f0-9-]{10,}", re.I), "Lever"),
    (re.compile(r"myworkdayjobs\.com/.+/job/", re.I), "Workday"),
    (re.compile(r"naukri\.com/job-listings-", re.I), "Naukri"),
    (re.compile(r"shine\.com/jobs/", re.I), "Shine"),
    (re.compile(r"instahyre\.com/j/", re.I), "Instahyre"),
    (re.compile(r"wellfound\.com/jobs/", re.I), "Wellfound"),
    (re.compile(r"smartrecruiters\.com/.+/[^/]+$", re.I), "SmartRecruiters"),
    (re.compile(r"ashbyhq\.com/.+/application", re.I), "Ashby"),
    (re.compile(r"/careers?/.+/job/", re.I), "Company Careers"),
    (re.compile(r"/en/job/[A-Z0-9-]+/", re.I), "Company Careers"),
]

LISTING_PAGE_RULES: list[re.Pattern[str]] = [
    re.compile(r"indeed\.com/q-", re.I),
    re.compile(r"glassdoor\.[^/]+/Job/.+-jobs-", re.I),
    re.compile(r"ziprecruiter\.com/Jobs/", re.I),
    re.compile(r"linkedin\.com/jobs/search", re.I),
    re.compile(r"/jobs/[a-z-]+/?$", re.I),
    re.compile(r"bebee\.com/.+/jobs/", re.I),
]

JD_COLUMN_CANDIDATES = (
    "job_description",
    "jd",
    "description",
    "job_desc",
    "text",
)


@dataclass
class JobRecord:
    input_id: str
    job_description: str
    company_name: str
    job_link: str
    source: str
    result_title: str
    search_engine: str


@dataclass
class SearchHit:
    title: str
    url: str
    snippet: str
    source: str


def read_job_descriptions(path: Path) -> list[tuple[str, str]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return _read_csv(path)
    if suffix in {".txt", ".md"}:
        return _read_text_blocks(path)
    raise ValueError(f"Unsupported input format: {path.suffix}. Use .csv or .txt")


def _read_csv(path: Path) -> list[tuple[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"No headers found in {path}")

        jd_column = _pick_jd_column(reader.fieldnames)
        id_column = "id" if "id" in reader.fieldnames else None
        rows: list[tuple[str, str]] = []

        for index, row in enumerate(reader, start=1):
            jd = (row.get(jd_column) or "").strip()
            if not jd:
                continue
            row_id = (row.get(id_column) or str(index)).strip() if id_column else str(index)
            rows.append((row_id, jd))

    if not rows:
        raise ValueError(f"No job descriptions found in {path}")
    return rows


def _pick_jd_column(fieldnames: list[str]) -> str:
    lowered = {name.lower(): name for name in fieldnames}
    for candidate in JD_COLUMN_CANDIDATES:
        if candidate in lowered:
            return lowered[candidate]
    if len(fieldnames) == 1:
        return fieldnames[0]
    raise ValueError(
        "Could not find a job description column. "
        f"Use one of {', '.join(JD_COLUMN_CANDIDATES)} or provide a single-column CSV."
    )


def _read_text_blocks(path: Path) -> list[tuple[str, str]]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"{path} is empty")

    blocks = [block.strip() for block in re.split(r"\n\s*---+\s*\n", text) if block.strip()]
    if len(blocks) == 1:
        blocks = [block.strip() for block in re.split(r"\n\s*\n\s*\n", text) if block.strip()]
    if len(blocks) == 1:
        blocks = [line.strip() for line in text.splitlines() if line.strip()]

    return [(str(index), block) for index, block in enumerate(blocks, start=1)]


def build_search_queries(job_description: str) -> list[str]:
    cleaned = " ".join(job_description.split())
    role_hint = _extract_role_hint(cleaned)
    return [
        f"{role_hint} hiring job opening",
        f"{role_hint} site:linkedin.com/jobs/view",
        f"{role_hint} site:indeed.com/viewjob OR site:greenhouse.io OR site:jobs.lever.co",
    ]


def _extract_role_hint(text: str) -> str:
    first_sentence = re.split(r"[.!?\n]", text, maxsplit=1)[0].strip()
    words = first_sentence.split()
    if len(words) > 12:
        return " ".join(words[:12])
    if len(text) <= 140:
        return text
    return " ".join(text.split()[:18])


def is_listing_page(url: str) -> bool:
    return any(pattern.search(url) for pattern in LISTING_PAGE_RULES)


def classify_source(url: str) -> str | None:
    if is_listing_page(url):
        return None
    for pattern, source in JOB_POSTING_RULES:
        if pattern.search(url):
            return source
    return None


def extract_company_name(title: str, url: str, snippet: str) -> str:
    host = urlparse(url).netloc.lower()

    if "linkedin.com" in host:
        linkedin_match = re.match(r"^(.+?)\s+hiring\s+", title, re.I)
        if linkedin_match:
            return linkedin_match.group(1).strip()

        slug_match = re.search(r"/jobs/view/[^/]+-at-([a-z0-9-]+)-\d+", url, re.I)
        if slug_match:
            return _slug_to_name(slug_match.group(1))

    if "indeed.com" in host:
        parts = [part.strip() for part in title.split(" - ") if part.strip()]
        if len(parts) >= 2:
            return parts[1]

    lever_match = re.search(r"jobs\.lever\.co/([^/?#]+)", url, re.I)
    if lever_match:
        return _slug_to_name(lever_match.group(1))

    greenhouse_match = re.search(r"boards\.greenhouse\.io/([^/?#]+)", url, re.I)
    if greenhouse_match:
        return _slug_to_name(greenhouse_match.group(1))

    workday_match = re.search(r"([^.]+)\.wd\d+\.myworkdayjobs\.com", url, re.I)
    if workday_match:
        return _slug_to_name(workday_match.group(1))

    for text in (snippet, title):
        at_match = re.search(
            r"\bat\s+([A-Z0-9][A-Za-z0-9&.\- ]{1,60}?)(?:\s*[|,.\-]|\s+(?:in|for|is|with)\b)",
            text,
        )
        if at_match:
            return at_match.group(1).strip()

    domain = host.removeprefix("www.")
    if domain.endswith(".linkedin.com") or domain == "linkedin.com":
        return "Unknown"

    if domain and domain not in {"indeed.com", "glassdoor.com"}:
        company_part = domain.split(".")[0]
        if company_part not in {"jobs", "careers", "apply"}:
            return _slug_to_name(company_part)

    return "Unknown"


def _slug_to_name(value: str) -> str:
    return value.replace("-", " ").replace("_", " ").strip().title()


def search_with_serpapi(query: str, max_results: int) -> tuple[list[SearchHit], str]:
    api_key = os.getenv("SERPAPI_KEY")
    if not api_key:
        return [], "serpapi"

    try:
        from serpapi import GoogleSearch
    except ImportError:
        return [], "serpapi"

    payload = GoogleSearch({"q": query, "api_key": api_key, "num": max_results}).get_dict()
    hits: list[SearchHit] = []

    for item in payload.get("organic_results", [])[:max_results]:
        url = item.get("link") or ""
        if not url:
            continue
        source = classify_source(url)
        if not source:
            continue
        hits.append(
            SearchHit(
                title=item.get("title") or "",
                url=url,
                snippet=item.get("snippet") or "",
                source=source,
            )
        )

    return hits, "google_via_serpapi"


def search_with_ddgs(queries: list[str], max_results: int) -> tuple[list[SearchHit], str]:
    try:
        from ddgs import DDGS
    except ImportError as exc:
        raise RuntimeError("Install dependencies with: pip install -r requirements.txt") from exc

    hits: list[SearchHit] = []
    seen_urls: set[str] = set()

    with DDGS() as ddgs:
        for query in queries:
            for item in ddgs.text(query, max_results=max(max_results * 4, 12)):
                url = item.get("href") or item.get("url") or ""
                if not url or url in seen_urls:
                    continue

                source = classify_source(url)
                if not source:
                    continue

                seen_urls.add(url)
                hits.append(
                    SearchHit(
                        title=item.get("title") or "",
                        url=url,
                        snippet=item.get("body") or "",
                        source=source,
                    )
                )
                if len(hits) >= max_results:
                    return hits, "web_search"

    return hits, "web_search"


def search_job_postings(queries: list[str], max_results: int) -> tuple[list[SearchHit], str]:
    if os.getenv("SERPAPI_KEY"):
        hits, engine = search_with_serpapi(queries[0], max_results)
        if hits:
            return hits, engine

    return search_with_ddgs(queries, max_results)


def find_jobs_for_description(
    input_id: str,
    job_description: str,
    max_results: int,
) -> list[JobRecord]:
    queries = build_search_queries(job_description)
    hits, engine = search_job_postings(queries, max_results)

    if not hits:
        return [
            JobRecord(
                input_id=input_id,
                job_description=job_description,
                company_name="Not found",
                job_link="",
                source="",
                result_title="",
                search_engine=engine,
            )
        ]

    records: list[JobRecord] = []
    for hit in hits:
        records.append(
            JobRecord(
                input_id=input_id,
                job_description=job_description,
                company_name=extract_company_name(hit.title, hit.url, hit.snippet),
                job_link=hit.url,
                source=hit.source,
                result_title=hit.title,
                search_engine=engine,
            )
        )
    return records


def write_results(path: Path, records: Iterable[JobRecord]) -> None:
    fieldnames = [
        "input_id",
        "job_description",
        "company_name",
        "job_link",
        "source",
        "result_title",
        "search_engine",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "input_id": record.input_id,
                    "job_description": record.job_description,
                    "company_name": record.company_name,
                    "job_link": record.job_link,
                    "source": record.source,
                    "result_title": record.result_title,
                    "search_engine": record.search_engine,
                }
            )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search the web for job postings that match batch job descriptions."
    )
    parser.add_argument(
        "input_file",
        type=Path,
        help="CSV or text file containing job descriptions",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("job_search_results.csv"),
        help="Output CSV path (default: job_search_results.csv)",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=5,
        help="Maximum job links to save per job description (default: 5)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="Seconds to wait between searches (default: 1.5)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])

    if not args.input_file.exists():
        print(f"Input file not found: {args.input_file}", file=sys.stderr)
        return 1

    try:
        descriptions = read_job_descriptions(args.input_file)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    all_records: list[JobRecord] = []
    total = len(descriptions)

    for index, (input_id, job_description) in enumerate(descriptions, start=1):
        print(f"[{index}/{total}] Searching jobs for input_id={input_id}...")
        records = find_jobs_for_description(input_id, job_description, args.max_results)
        all_records.extend(records)

        found = sum(1 for record in records if record.job_link)
        print(f"  Found {found} job link(s) using {records[0].search_engine}")

        if index < total and args.delay > 0:
            time.sleep(args.delay)

    write_results(args.output, all_records)
    print(f"Saved {len(all_records)} row(s) to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
