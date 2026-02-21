# agent/tools/edgar.py
import requests
HEADERS = {"User-Agent": "youremail@example.com"}  # SEC asks for contact UA
def latest_filings(args):
    cik = args.get("cik")  # or map from ticker to CIK separately
    url = f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"
    j = requests.get(url, headers=HEADERS, timeout=30).json()
    filings = j.get("filings", {}).get("recent", {})
    out = [{"form": f, "date": d, "accession": a}
           for f,d,a in zip(filings.get("form",[]), filings.get("filingDate",[]), filings.get("accessionNumber",[]))]
    return {"cik": cik, "recent": out[:20]}
