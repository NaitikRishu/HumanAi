import argparse, csv, hashlib, json, re, ssl, urllib.request
from datetime import datetime

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse


class TEXTExtracter(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_title = False
        self.skip = 0
        self.title = []
        
        self.body = []

    def start(self, tag, attrs):
        t = tag.lower()
        if t == "title":
            self.in_title = True
        elif t in ("script", "style", "noscript"):
            self.skip += 1
            
            
        elif self.skip == 0 and t in ("p", "div", "li", "br", "h1", "h2", "h3"):
            self.body.append("\n")

    def end(self, tag):
        t = tag.lower()
        if t == "title":
            self.in_title = False
        elif t in ("script", "style", "noscript") and self.skip > 0:
            self.skip -= 1

    def datahandle(self, data):
        if self.in_title:
            self.title.append(data)
        elif self.skip == 0:
            self.body.append(data)


def clean(s):
    s = s.replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{2,}", "\n", s)
    return s.strip()


def fetch_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": "foa-mvp/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20, context=ssl.create_default_context()) as r:
            html = r.read().decode("utf-8", errors="replace")
    except Exception:
        return ""
    p = TEXTExtracter()
    p.feed(html)
    p.close()
    return clean(clean(" ".join(p.title)) + "\n" + clean(" ".join(p.body)))


def main():
    import sys

    sys.argv = [a.replace("–", "--").replace("—", "--") for a in sys.argv]
    ap = argparse.ArgumentParser()
    
    ap.add_argument("--url", required=True)
    ap.add_argument("--out_dir", required=True)
    args = ap.parse_args()

    text = fetch_text(args.url)
    if not text:
        text = "Funding Opportunity Announcement\nProgram Description: unavailable in offline environment\nEligibility: see source URL"

    host = urlparse(args.url).netloc.lower()
    agency = "Nation Science Foundation" if "nsf.gov" in host else ("Grants.gov" if "grants.gov" in host else (host or "Unknown"))

    lines = [x.strip() for x in text.split("\n") if x.strip()]
    title = next((x for x in lines if 8 < len(x) < 160), f"FOA from {host}")

    foa_id = "GEN-" + hashlib.sha1(args.url.encode()).hexdigest()[:10]
    for line in lines[:200]:
        low = line.lower()
        if any(k in low for k in ("foa", "opportunity number", "solicitation", "nsf")):
            for token in re.split(r"[^A-Za-z0-9.-]+", line):
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
                token = " ".join(words[i:i+n]).strip(".,;()[]")
                for fmt in ("%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
                    try:
                        iso = datetime.strptime(token, fmt).date().isoformat()
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

    eligibility, description = "", ""
    for i, line in enumerate(lines):
        low = line.lower()
        if not eligibility and "eligibility" in low:
            eligibility = clean(" ".join(lines[i:i+5]))[:700]
        if not description and any(k in low for k in ("program description", "synopsis", "summary")):
            description = clean(" ".join(lines[i:i+8]))[:1000]
    if not eligibility:
        eligibility = "Eligibility: see source URL"
    if not description:
        description = clean(" ".join(lines[:40]))[:1000]

    award_range = ""
    for line in lines[:350]:
        low = line.lower()
        if line.count("$") >= 2 and any(k in low for k in ("award", "range", "funding", "budget", "to", "-")):
            award_range = clean(line)
            break

    low_blob = (title + "\n" + description + "\n" + eligibility + "\n" + text[:1200]).lower()
    research_domains = []
    sponsor_themes = []
    if any(k in low_blob for k in ("health", "clinical", "biomedical")):
        research_domains.append("health")
    if any(k in low_blob for k in ("artificial intelligence", "machine learning")):
        research_domains.append("ai_ml")
    if any(k in low_blob for k in ("climate", "environment")):
        research_domains.append("climate")
    if any(k in low_blob for k in ("workforce", "training")):
        sponsor_themes.append("workforce")
    if any(k in low_blob for k in ("innovation", "transformative")):
        sponsor_themes.append("innovation")

    record = {
        "foa_id": foa_id,
        "title": title,
        "agency": agency,
        "open_date": open_date,
        "close_date": close_date,
        "eligibility_text": eligibility,
        "program_description": description,
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
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        w.writeheader()
        w.writerow(row)

    print(f"Writte {out_dir / 'foa.json'}")
    print(f"Wrote {out_dir / 'foa.csv'}")


if __name__ == "__main__":
    main()
