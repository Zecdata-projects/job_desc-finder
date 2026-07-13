#!/usr/bin/env python3
"""Find job posting links and company names from batch job descriptions using JobSpy."""

from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

JD_COLUMN_CANDIDATES = (
    "job_description",
    "jd",
    "description",
    "job_desc",
    "text",
)

DEFAULT_SITES = ("linkedin", "indeed", "google", "naukri")

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is",
    "it", "of", "on", "or", "that", "the", "to", "with", "will", "you", "your",
    "we", "our", "this", "have", "has", "had", "can", "should", "must", "may",
    "such", "than", "their", "them", "they", "who", "which", "when", "where",
    "years", "year", "experience", "hand", "hands", "on", "role", "work", "job",
    "using", "use", "used", "including", "including", "other", "similar", "like",
    "demonstrate", "ability", "skills", "strong", "focus", "including",
}


@dataclass
class JobRecord:
    input_id: str
    job_description: str
    company_name: str
    job_link: str
    source: str
    result_title: str
    location: str
    is_remote: str
    match_score: str
    search_term: str


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


def extract_search_term(job_description: str) -> str:
    """Build a keyword search query from a full job description."""
    cleaned = " ".join(job_description.split())

    role_match = re.search(
        r"(?:^|\n)\s*(?:title\s*[:\-]\s*)?"
        r"([A-Z][A-Za-z0-9 /\-]+(?:Engineer|Developer|Analyst|Architect|Manager|Scientist|Lead|Consultant))",
        cleaned,
        re.I,
    )
    if role_match:
        role = role_match.group(1).strip()
    else:
        first_sentence = re.split(r"[.!?\n]", cleaned, maxsplit=1)[0].strip()
        words = first_sentence.split()
        role = " ".join(words[:10]) if len(words) > 10 else first_sentence

    tech_terms = re.findall(
        r"\b(?:Python|Java|JavaScript|TypeScript|React|Node\.?js|Django|Flask|FastAPI|"
        r"TensorFlow|PyTorch|AWS|Azure|GCP|Docker|Kubernetes|SQL|PostgreSQL|MongoDB|"
        r"Machine Learning|ML|AI|LLM|GenAI|Databricks|Spark|Tableau|Power BI|"
        r"REST|API|DevOps|CI/CD|Snowflake|Fabric)\b",
        cleaned,
        re.I,
    )
    unique_terms: list[str] = []
    seen: set[str] = set()
    for term in tech_terms:
        key = term.lower()
        if key not in seen:
            seen.add(key)
            unique_terms.append(term)

    if unique_terms:
        return f"{role} {' '.join(unique_terms[:4])}".strip()
    return role[:120].strip()


def tokenize(text: str) -> set[str]:
    words = set(re.findall(r"[a-z0-9+#.]+", text.lower()))
    return {word for word in words if len(word) > 2 and word not in STOPWORDS}


def compute_match_score(job_description: str, title: str, description: str) -> float:
    jd_tokens = tokenize(job_description)
    if not jd_tokens:
        return 0.0
    result_tokens = tokenize(f"{title} {description}")
    overlap = len(jd_tokens & result_tokens)
    return round(overlap / len(jd_tokens) * 100, 1)


def format_site_name(site: str) -> str:
    mapping = {
        "linkedin": "LinkedIn",
        "indeed": "Indeed",
        "google": "Google Jobs",
        "naukri": "Naukri",
        "glassdoor": "Glassdoor",
        "zip_recruiter": "ZipRecruiter",
        "bayt": "Bayt",
        "bdjobs": "BDJobs",
    }
    return mapping.get(site.lower(), site.title())


def scrape_with_jobspy(
    search_term: str,
    max_results: int,
    sites: list[str],
    location: str | None,
    country: str | None,
    fetch_descriptions: bool,
    is_remote: bool | None,
) -> list[dict]:
    from jobspy import scrape_jobs

    kwargs: dict = {
        "site_name": sites,
        "search_term": search_term,
        "results_wanted": max_results,
        "verbose": 0,
        "linkedin_fetch_description": fetch_descriptions,
    }
    if location:
        kwargs["location"] = location
    if country:
        kwargs["country_indeed"] = country
    if is_remote is not None:
        kwargs["is_remote"] = is_remote

    if "google" in sites:
        google_query = search_term
        if location:
            google_query = f"{search_term} jobs near {location}"
        kwargs["google_search_term"] = google_query

    jobs_df = scrape_jobs(**kwargs)
    if jobs_df is None or jobs_df.empty:
        return []

    records: list[dict] = []
    for row in jobs_df.to_dict("records"):
        job_url = _clean_value(row.get("job_url_direct")) or _clean_value(row.get("job_url")) or ""
        company = _clean_value(row.get("company")) or "Unknown"
        records.append(
            {
                "title": _clean_value(row.get("title")) or "",
                "company": company,
                "job_url": job_url,
                "site": _clean_value(row.get("site")) or "",
                "location": _clean_value(row.get("location")) or "",
                "is_remote": row.get("is_remote"),
                "description": _clean_value(row.get("description")) or "",
            }
        )
    return [hit for hit in records if hit["job_url"]]


def _clean_value(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    return text


def find_jobs_for_description(
    input_id: str,
    job_description: str,
    max_results: int,
    sites: list[str],
    location: str | None,
    country: str | None,
    fetch_descriptions: bool,
    is_remote: bool | None,
) -> list[JobRecord]:
    search_term = extract_search_term(job_description)

    try:
        hits = scrape_with_jobspy(
            search_term=search_term,
            max_results=max_results,
            sites=sites,
            location=location,
            country=country,
            fetch_descriptions=fetch_descriptions,
            is_remote=is_remote,
        )
    except Exception as exc:
        print(f"  JobSpy error: {exc}", file=sys.stderr)
        hits = []

    if not hits:
        return [
            JobRecord(
                input_id=input_id,
                job_description=job_description,
                company_name="Not found",
                job_link="",
                source="",
                result_title="",
                location="",
                is_remote="",
                match_score="",
                search_term=search_term,
            )
        ]

    records: list[JobRecord] = []
    for hit in hits:
        score = compute_match_score(job_description, hit["title"], hit["description"])
        records.append(
            JobRecord(
                input_id=input_id,
                job_description=job_description,
                company_name=hit["company"],
                job_link=hit["job_url"],
                source=format_site_name(hit["site"]),
                result_title=hit["title"],
                location=hit["location"],
                is_remote=str(hit["is_remote"]) if hit["is_remote"] is not None else "",
                match_score=str(score),
                search_term=search_term,
            )
        )

    records.sort(key=lambda record: float(record.match_score or 0), reverse=True)
    return records


def write_results(path: Path, records: Iterable[JobRecord]) -> None:
    fieldnames = [
        "input_id",
        "job_description",
        "company_name",
        "job_link",
        "source",
        "result_title",
        "location",
        "is_remote",
        "match_score",
        "search_term",
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
                    "location": record.location,
                    "is_remote": record.is_remote,
                    "match_score": record.match_score,
                    "search_term": record.search_term,
                }
            )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search job boards for postings that match batch job descriptions (via JobSpy)."
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
        default=10,
        help="Maximum job links to save per job description (default: 10)",
    )
    parser.add_argument(
        "--sites",
        nargs="+",
        default=list(DEFAULT_SITES),
        choices=["linkedin", "indeed", "google", "naukri", "glassdoor", "zip_recruiter", "bayt", "bdjobs"],
        help="Job boards to search (default: linkedin indeed google naukri)",
    )
    parser.add_argument(
        "--location",
        default="",
        help="Location filter, e.g. 'Bangalore' or 'Remote'",
    )
    parser.add_argument(
        "--country",
        default="India",
        help="Country for Indeed/Glassdoor filter (default: India)",
    )
    parser.add_argument(
        "--remote",
        action="store_true",
        help="Only return remote jobs",
    )
    parser.add_argument(
        "--fetch-descriptions",
        action="store_true",
        help="Fetch full LinkedIn descriptions (slower, better match scores)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Seconds to wait between job descriptions (default: 2.0)",
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

    location = args.location.strip() or None
    country = args.country.strip() or None
    is_remote = True if args.remote else None

    all_records: list[JobRecord] = []
    total = len(descriptions)

    print(f"Searching sites: {', '.join(args.sites)}")

    for index, (input_id, job_description) in enumerate(descriptions, start=1):
        search_term = extract_search_term(job_description)
        print(f"[{index}/{total}] Searching for input_id={input_id}...")
        print(f"  Query: {search_term}")

        records = find_jobs_for_description(
            input_id=input_id,
            job_description=job_description,
            max_results=args.max_results,
            sites=args.sites,
            location=location,
            country=country,
            fetch_descriptions=args.fetch_descriptions,
            is_remote=is_remote,
        )
        all_records.extend(records)

        found = sum(1 for record in records if record.job_link)
        print(f"  Found {found} job(s)")

        if index < total and args.delay > 0:
            time.sleep(args.delay)

    write_results(args.output, all_records)
    print(f"Saved {len(all_records)} row(s) to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
