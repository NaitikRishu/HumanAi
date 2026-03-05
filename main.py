
import re
import ssl
import urllib.request

import argparse
import csv
import hashlib
import json

from datetime import datetime
from pathlib import Path

from urllib.parse import urlparse


def main():
    
    import sys

    sys.argv = [a.replace("–", "--").replace("—", "--") for a in sys.argv]
    

    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--out_dir", required=True)
    args = parser.parse_args()

    
    request = urllib.request.Request(args.url, headers={"User-Agent": "foa-mvp/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=20, context=ssl.create_default_context()) as response:
            html = response.read().decode("utf-8", errors="replace")
    except Exception:
        html = ""

    
    if html:
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
        title_text = title_match.group(1).strip() if title_match else ""
        html = re.sub(r"<script[\\s\\S]*?</script>", " ", html, flags=re.IGNORECASE)
        html = re.sub(r"<style[\\s\\S]*?</style>", " ", html, flags=re.IGNORECASE)
        body_text = re.sub(r"<[^>]+>", "\n", html)
        text = title_text + "\n" + body_text
        text = text.replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{2,}", "\n", text).strip()
    else:
        text = "Funding Opportunity Announcement\nProgram Description: unavailable in offline environment\nEligibility: see source URL"

    lines = [x.strip() for x in text.split("\n") if x.strip()]

    
    host = urlparse(args.url).netloc.lower()
    title = next((x for x in lines if 8 < len(x) < 160), f"FOA from {host}")
    if "nsf.gov" in host:
        agency = "National Science Foundation"
    elif "grants.gov" in host:
        agency = "Grants.gov"
    else:
        agency = host or "Unknown"

    
    foa_id = "GEN-" + hashlib.sha1(args.url.encode()).hexdigest()[:10]
    for line in lines[:200]:
        low = line.lower()
        if any(k in low for k in ("foa", "opportunity number", "solicitation", "nsf")):
            tokens = re.split(r"[^A-Za-z0-9.-]+", line)
            for token in tokens:
                if len(token) >= 4 and any(c.isalpha() for c in token) and any(c.isdigit() for c in token):
                    foa_id = token
                    break

    
    open_date, close_date = "", ""
    for line in lines[:250]:
        low = line.lower()
        words = line.split()
        iso = ""
        for i in range(len(words)):
            for n in (3, 2, 1):
                chunk = " ".join(words[i : i + n]).strip(".,;()[]")
                for fmt in ("%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
                    try:
                        iso = datetime.strptime(chunk, fmt).date().isoformat()
                        break
                    except Exception:
                        pass
                if iso:
                    break
            if iso:
                break
        if not iso:
            continue
        if not open_date and any(k in low for k in ("open", "posted", "release")):
            open_date = iso
        if not close_date and any(k in low for k in ("close", "due", "deadline")):
            close_date = iso

    
    eligibility_text = ""
    program_description = ""
    for i, line in enumerate(lines):
        low = line.lower()
        if not eligibility_text and "eligibility" in low:
            eligibility_text = " ".join(lines[i : i + 5])
            eligibility_text = re.sub(r"[ \t]+", " ", eligibility_text)[:700]
        if not program_description and any(k in low for k in ("program description", "synopsis", "summary")):
            program_description = " ".join(lines[i : i + 8])
            program_description = re.sub(r"[ \t]+", " ", program_description)[:1000]

    if not eligibility_text:
        eligibility_text = "Eligibility: see source URL"
    if not program_description:
        program_description = " ".join(lines[:40])[:1000]

   
    award_range = ""
    for line in lines[:350]:
        low = line.lower()
        if line.count("$") >= 2 and any(k in low for k in ("award", "range", "funding", "budget", "to", "-")):
            award_range = re.sub(r"[ \t]+", " ", line).strip()
            break

    
    blob = (title + "\n" + eligibility_text + "\n" + program_description + "\n" + text[:1200]).lower()
    research_domains = []
    sponsor_themes = []

    if any(k in blob for k in ("health", "clinical", "biomedical")):
        research_domains.append("health")
    if any(k in blob for k in ("artificial intelligence", "machine learning")):
        research_domains.append("ai_ml")
    if any(k in blob for k in ("climate", "environment")):
        research_domains.append("climate")

    if any(k in blob for k in ("workforce", "training")):
        sponsor_themes.append("workforce")
    if any(k in blob for k in ("innovation", "transformative")):
        sponsor_themes.append("innovation")

    record = {
        "foa_id": foa_id,
        "title": title,
        "agency": agency,
        "open_date": open_date,
        "close_date": close_date,
        "eligibility_text": eligibility_text,
        "program_description": program_description,
        "award_range": award_range,
        "source_url": args.url,
        "tags": {
            "research_domains": sorted(set(research_domains)),
            "sponsor_themes": sorted(set(sponsor_themes)),
        },
    }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "foa.json").write_text(json.dumps(record, indent=2), encoding="utf-8")

    row = {
        "foa_id": record["foa_id"],
        "title": record["title"],
        "agency": record["agency"],
        "open_date": record["open_date"],
        "close_date": record["close_date"],
        "eligibility_text": record["eligibility_text"],
        "program_description": record["program_description"],
        "award_range": record["award_range"],
        "source_url": record["source_url"],
        "research_domains": ";".join(record["tags"]["research_domains"]),
        "sponsor_themes": ";".join(record["tags"]["sponsor_themes"]),
    }

    with (out_dir / "foa.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        writer.writeheader()
        writer.writerow(row)

    print(f"Wrote {out_dir / 'foa.json'}")
    print(f"Wrote {out_dir / 'foa.csv'}")


if __name__ == "__main__":
    main()
