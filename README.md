# JD Job Finder

Search the web for job postings that match your job descriptions (JDs), then export **company names** and **job links** to a CSV.

Supports batch input from CSV or text files. Results are pulled from job boards and company career pages such as LinkedIn, Indeed, Greenhouse, Lever, Naukri, Shine, and Wellfound.

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
  --max-results 5 \
  --delay 1.5
```

| Flag | Description | Default |
|------|-------------|---------|
| `-o`, `--output` | Output CSV path | `job_search_results.csv` |
| `--max-results` | Max job links per JD | `5` |
| `--delay` | Seconds between searches | `1.5` |

## Output

The CSV includes:

| Column | Description |
|--------|-------------|
| `input_id` | Row ID from your input file |
| `job_description` | Original job description |
| `company_name` | Company that posted the job |
| `job_link` | Direct link to the posting |
| `source` | Job board or careers site (e.g. LinkedIn, Indeed) |
| `result_title` | Title from the search result |
| `search_engine` | Search backend used |

## Optional: Google search via SerpAPI

By default, the tool uses web search (DuckDuckGo-backed via the `ddgs` package). For Google results, set a [SerpAPI](https://serpapi.com/) key:

```bash
export SERPAPI_KEY="your_api_key_here"
python jd_job_finder.py your_jobs.csv -o results.csv
```

## Example

```bash
source .venv/bin/activate
python jd_job_finder.py sample_input.csv -o results.csv --max-results 5
```

Sample output:

```csv
input_id,job_description,company_name,job_link,source,result_title,search_engine
1,"Senior Python Developer...",Gloify,https://in.linkedin.com/jobs/view/...,LinkedIn,Gloify hiring Senior Python Django Developer...,web_search
```

## Notes

- Results are **similar matches**, not guaranteed exact duplicates of your JD.
- Listing/search pages are filtered out when possible; direct job posting links are preferred.
- Use a small `--delay` between batch runs to reduce rate limiting from search providers.

## License

MIT
