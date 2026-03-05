

## Run

Run this on your terminal :)
python main.py --url "https://www.nsf.gov/funding/opportunities" --out_dir ./out


## Output

- `out/foa.json`
- `out/foa.csv`

## Extracted fields

- `foa_id` (generated if missing)
- `title`
- `agency`
- `open_date`, `close_date` (ISO if found)
- `eligibility_text`
- `program_description`
- `award_range`
- `source_url`
- deterministic tags (`research_domains`, `sponsor_themes`)

## Note

If the environment is offline, the script still writes valid fallback output.
