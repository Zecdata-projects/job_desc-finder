# JD Job Finder

Search job boards for postings that match your job descriptions (JDs), then export **company names**, **job links**, and **match scores** to a CSV.

Powered by [JobSpy](https://github.com/speedyapply/JobSpy) — scrapes LinkedIn, Indeed, Google Jobs, Naukri, Glassdoor, and more.

## Requirements

- Python 3.10+
- Internet access

## Setup

1. Clone the repository:

```bash
git clone https://github.com/rahuls-zec/jd-job-finder.git
cd jd-job-finder
```

2. Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

## Input format

### CSV (recommended)

Create a CSV with a `job_description` column (also accepts `jd`, `description`, `job_desc`, or `text`):

```csv
id,job_description
1,"Senior Python Developer with Django, REST APIs, and AWS..."
2,"Data Analyst — SQL, Python, Tableau..."
```

See `sample_input.csv` for an example.

### Text file

You can also use a `.txt` file with job descriptions separated by:

- blank lines
- `---` on its own line
- one JD per line

## Usage

Run the script against your input file:

```bash
python jd_job_finder.py sample_input.csv
```

This writes results to `job_search_results.csv` by default.

### Options

```bash
python jd_job_finder.py your_jobs.csv \
  -o results.csv \
  --max-results 10 \
  --sites linkedin indeed naukri google \
  --location "Bangalore" \
  --country India \
  --fetch-descriptions \
  --delay 2
```

| Flag | Description | Default |
|------|-------------|---------|
| `-o`, `--output` | Output CSV path | `job_search_results.csv` |
| `--max-results` | Max jobs per JD | `10` |
| `--sites` | Job boards to search | `linkedin indeed google naukri` |
| `--location` | Location filter | none |
| `--country` | Country for Indeed/Glassdoor | `India` |
| `--remote` | Only remote jobs | off |
| `--fetch-descriptions` | Fetch full LinkedIn descriptions (slower) | off |
| `--delay` | Seconds between JD searches | `2.0` |

### Supported job boards

`linkedin`, `indeed`, `google`, `naukri`, `glassdoor`, `zip_recruiter`, `bayt`, `bdjobs`

## Output

The CSV includes:

| Column | Description |
|--------|-------------|
| `input_id` | Row ID from your input file |
| `job_description` | Original job description |
| `company_name` | Company that posted the job |
| `job_link` | Direct link to the posting |
| `source` | Job board (LinkedIn, Indeed, Naukri, etc.) |
| `result_title` | Job title from the listing |
| `location` | Job location |
| `is_remote` | Whether the job is remote |
| `match_score` | Keyword overlap score (0–100) vs your JD |
| `search_term` | Query extracted from your JD |

Results are sorted by `match_score` (highest first) within each JD.

## Example

```bash
source .venv/bin/activate
python jd_job_finder.py sample_input.csv -o results.csv --max-results 5 --sites linkedin indeed
```

Sample output:

```csv
input_id,job_description,company_name,job_link,source,result_title,location,is_remote,match_score,search_term
1,"Senior Python Developer...",Gloify,https://in.linkedin.com/jobs/view/...,LinkedIn,Senior Python Django Developer,Bengaluru,False,42.5,Senior Python Developer Python Django REST AWS
```

## How it works

1. Extracts a **search query** from each JD (role title + key tech skills)
2. Searches multiple job boards via **JobSpy**
3. Scores each result by **keyword overlap** with your JD
4. Exports structured results to CSV

## Notes

- Results are **similar matches** based on extracted keywords, not exact JD duplicates.
- LinkedIn may rate-limit requests; use `--delay` and `--fetch-descriptions` only when needed.
- For better match scores, pass `--fetch-descriptions` to pull full LinkedIn job text.

## License

MIT
