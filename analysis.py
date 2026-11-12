"""
NY Disabled Veterans Outreach Gap Map -- data rebuild script
=============================================================

Run it with:   python3 analysis.py

What it does, in plain terms:
  1. Downloads disabled-veteran counts for every NY county from the US Census
     (American Community Survey 5-year estimates, table S2101).
  2. Reads what the NY State Comptroller's audit (2025-S-10) published about
     the Access to Home for Heroes/Veterans program in each county.
  3. Downloads the county boundary shapes for the map.
  4. Combines everything, scores each county's "outreach gap", and writes:
       data/acs_s2101_ny_counties.csv   (step 1, cleaned)
       data/program_presence.csv        (step 2, one row per county, with sources)
       data/ny_counties.geojson         (step 3)
       data/county_gap_scores.csv       (the final table the page shows)
     ...and copies the final numbers into index.html so the page works offline.

It uses only Python's built-in libraries -- nothing to install.
You need a free Census API key (https://api.census.gov/data/key_signup.html)
saved in a file named `.census_key` next to this script, or in the
environment variable CENSUS_API_KEY.

This is a proof of concept built from public data only. It is NOT an HCR
product and uses none of HCR's internal records.
"""

import csv
import json
import os
import sys
import urllib.parse
import urllib.request
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
RAW = os.path.join(DATA, "raw")

# ---------------------------------------------------------------------------
# Settings you might change
# ---------------------------------------------------------------------------
ACS_YEAR = "2024"  # ACS 5-year release covering 2020-2024 (latest as of Nov 2026)
STATE_FIPS = "36"  # New York

# Census variable IDs, checked against
# https://api.census.gov/data/2024/acs/acs5/subject/groups/S2101.json
ACS_VARS = {
    "S2101_C01_001E": "adults_18plus",            # Total civilian population 18+
    "S2101_C03_001E": "veterans",                 # Veterans, civilian pop 18+
    "S2101_C03_039E": "disabled_veterans",        # Veterans "With any disability"
    "S2101_C03_039M": "disabled_veterans_moe",    # ...its margin of error (90%)
}

BOUNDARY_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/Generalized_ACS2024/"
    "State_County/MapServer/11/query"  # layer 11 = "Counties 500K" cartographic boundaries
)

OSC_MAP_SOURCE = (
    "NYS Comptroller audit 2025-S-10 interactive map "
    "(data.osc.ny.gov/views/DisabledVeteranPopulation/Dashboard1), read Nov 12 2026"
)
OSC_REPORT = "NYS Comptroller audit 2025-S-10, Exhibit B (p.25)"


def fetch(url):
    """Download a URL and return its text."""
    req = urllib.request.Request(url, headers={"User-Agent": "ny-veterans-gap-map/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        final_url = resp.geturl()
        body = resp.read().decode("utf-8")
    if "missing_key" in final_url or "invalid_key" in final_url:
        sys.exit("Census rejected the API key. Check the .census_key file.")
    return body


def write_csv(path, rows, columns):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in columns})
    print("  wrote", os.path.relpath(path, HERE), f"({len(rows)} rows)")


def county_short(name):
    """'St. Lawrence County, New York' -> 'St. Lawrence'."""
    return name.split(",")[0].replace(" County", "").strip()


# ---------------------------------------------------------------------------
# Step 1: Census need data
# ---------------------------------------------------------------------------
def load_census_key():
    key = os.environ.get("CENSUS_API_KEY", "").strip()
    path = os.path.join(HERE, ".census_key")
    if not key and os.path.exists(path):
        key = open(path).read().strip()
    if not key:
        sys.exit(
            "No Census API key found. Get one free at "
            "https://api.census.gov/data/key_signup.html and save it in .census_key"
        )
    return key


def step1_census():
    print("Step 1: downloading ACS", ACS_YEAR, "5-year table S2101 for NY counties...")
    params = {
        "get": "NAME," + ",".join(ACS_VARS),
        "for": "county:*",
        "in": "state:" + STATE_FIPS,
        "key": load_census_key(),
    }
    url = f"https://api.census.gov/data/{ACS_YEAR}/acs/acs5/subject?" + urllib.parse.urlencode(params)
    table = json.loads(fetch(url))  # first row = column headers, rest = counties
    header, rows = table[0], table[1:]

    out = []
    for r in rows:
        rec = dict(zip(header, r))
        row = {
            "fips": rec["state"] + rec["county"],
            "county": county_short(rec["NAME"]),
        }
        for var, nice in ACS_VARS.items():
            row[nice] = int(float(rec[var]))
        out.append(row)
    out.sort(key=lambda r: r["county"])
    if len(out) != 62:
        sys.exit(f"Expected 62 NY counties from Census, got {len(out)}")

    write_csv(
        os.path.join(DATA, "acs_s2101_ny_counties.csv"),
        out,
        ["fips", "county", "adults_18plus", "veterans", "disabled_veterans", "disabled_veterans_moe"],
    )
    return {r["county"]: r for r in out}


# ---------------------------------------------------------------------------
# Step 2: Program presence (from the Comptroller's audit)
# ---------------------------------------------------------------------------
def step2_program():
    """
    Two hand-captured inputs in data/raw/ (see README for how they were captured):
      osc_audit_map_county.csv -- one row per county from the audit's map. The
          last column is either "No Applicants", "Not Awarded" (applied, not
          funded), or the number of veteran households served (April 2021 -
          October 2025) in a county that had a funded LPA.
      lpa_contracts.csv -- the contracts listed in the audit's Exhibit B.

    Funding by county: following the audit's own map method, a multi-county
    contract's amount is split equally among its counties. Only the 10 sampled
    contracts in Exhibit B have published amounts; counties covered only by
    the 5 unsampled contracts are marked "unknown".
    """
    print("Step 2: building program presence from the Comptroller's audit...")
    osc = {}
    with open(os.path.join(RAW, "osc_audit_map_county.csv")) as f:
        for r in csv.DictReader(f):
            osc[r["county"]] = r

    funding = defaultdict(float)
    lpas = defaultdict(set)
    unknown_funding = set()
    with open(os.path.join(RAW, "lpa_contracts.csv")) as f:
        for c in csv.DictReader(f):
            counties = c["service_area_counties"].split(";")
            for cty in counties:
                lpas[cty].add(c["lpa"])
            if c["contract_amount"] == "unknown":
                unknown_funding.update(counties)
            else:
                for cty in counties:
                    funding[cty] += float(c["contract_amount"]) / len(counties)

    rows = []
    for county, r in sorted(osc.items()):
        status_raw = r["osc_households_served_or_status"]
        if status_raw == "No Applicants":
            status, has_lpa, served = "No applicants", "no", 0
        elif status_raw == "Not Awarded":
            status, has_lpa, served = "Applied, not funded", "no", 0
        else:
            served = int(status_raw)
            has_lpa = "yes"
            status = "Funded, households served" if served > 0 else "Funded, none served yet"

        if has_lpa == "no":
            fund = "0"
            fund_note = "no award to this county per audit map"
        elif county in funding and county not in unknown_funding:
            fund = f"{funding[county]:.0f}"
            fund_note = "equal share of Exhibit B contract amounts, FY2022-FY2024"
        elif county in funding:
            fund = f"{funding[county]:.0f}+"
            fund_note = "Exhibit B share plus unpublished amount from unsampled contract"
        else:
            fund = "unknown"
            fund_note = "covered only by contracts the audit did not sample"

        rows.append({
            "county": county,
            "program_status": status,
            "has_lpa": has_lpa,
            "projects_completed": served,
            "funding_awarded": fund,
            "lpas": "; ".join(sorted(lpas.get(county, []))) or ("unknown (not in Exhibit B)" if has_lpa == "yes" else ""),
            "osc_disabled_veterans_2019_2023": int(r["osc_disabled_veterans"]),
            "osc_disabled_vet_pct_2019_2023": float(r["osc_disabled_vet_pct"]),
            "source": f"Status & households served: {OSC_MAP_SOURCE}. Funding/LPA: {OSC_REPORT}. Funding note: {fund_note}",
        })

    # Sanity checks against figures printed in the audit itself.
    funded = [r for r in rows if r["has_lpa"] == "yes"]
    served = [r for r in rows if r["projects_completed"] > 0]
    total_served = sum(r["projects_completed"] for r in rows)
    print(f"  check: {len(funded)} funded counties (audit: 26), "
          f"{len(served)} with projects (audit: 15), {total_served} projects (audit: 81)")

    write_csv(
        os.path.join(DATA, "program_presence.csv"),
        rows,
        ["county", "program_status", "has_lpa", "projects_completed", "funding_awarded", "lpas",
         "osc_disabled_veterans_2019_2023", "osc_disabled_vet_pct_2019_2023", "source"],
    )
    return {r["county"]: r for r in rows}


# ---------------------------------------------------------------------------
# Step 3: County boundaries
# ---------------------------------------------------------------------------
def step3_boundaries():
    print("Step 3: downloading NY county boundaries from Census TIGERweb...")
    params = {
        "where": f"STATE='{STATE_FIPS}'",
        "outFields": "GEOID,NAME",
        "maxAllowableOffset": "0.005",  # simplify shapes a bit so the page loads fast
        "geometryPrecision": "4",
        "outSR": "4326",
        "f": "geojson",
    }
    gj = json.loads(fetch(BOUNDARY_URL + "?" + urllib.parse.urlencode(params)))
    if len(gj["features"]) != 62:
        sys.exit(f"Expected 62 county shapes, got {len(gj['features'])}")
    with open(os.path.join(DATA, "ny_counties.geojson"), "w") as f:
        json.dump(gj, f, separators=(",", ":"))
    print("  wrote data/ny_counties.geojson (62 shapes)")
    return gj


# ---------------------------------------------------------------------------
# Step 4: Combine and score
# ---------------------------------------------------------------------------
def step4_score(acs, prog):
    """
    Gap ranking (higher rank = bigger outreach gap):
      A. Counties with ZERO completed projects come first, ordered by how many
         disabled veterans live there (most first). A county with 13,000
         disabled veterans and no projects is a bigger gap than one with 300.
      B. Then counties that did have projects, ordered by projects per 1,000
         disabled veterans (fewest first).
    The gap score (0-100) just turns the rank into a number for map shading:
    rank 1 = 100, rank 62 = 0.

    Audit flag: the audit's rule was "over 5,000 disabled veterans OR over 30%
    of veterans have a disability", using 2019-2023 Census data. We apply that
    rule to the same 2019-2023 numbers the audit's map shows.
    """
    print("Step 4: combining and scoring...")
    rows = []
    for county, a in acs.items():
        p = prog[county]
        dv = a["disabled_veterans"]
        projects = p["projects_completed"]
        rows.append({
            "fips": a["fips"],
            "county": county,
            "disabled_veterans": dv,
            "disabled_veterans_moe": a["disabled_veterans_moe"],
            "veterans": a["veterans"],
            "adults_18plus": a["adults_18plus"],
            "dv_per_1000_adults": round(1000 * dv / a["adults_18plus"], 1),
            "pct_veterans_disabled": round(100 * dv / a["veterans"], 1) if a["veterans"] else "",
            "program_status": p["program_status"],
            "has_lpa": p["has_lpa"],
            "projects_completed": projects,
            "projects_per_1000_dv": round(1000 * projects / dv, 2) if dv else "",
            "funding_awarded": p["funding_awarded"],
            "lpas": p["lpas"],
            "audit_high_need": "yes" if (p["osc_disabled_veterans_2019_2023"] > 5000
                                         or p["osc_disabled_vet_pct_2019_2023"] > 30) else "no",
        })

    for r in rows:
        r["audit_high_need_no_applicants"] = (
            "yes" if r["audit_high_need"] == "yes" and r["program_status"] == "No applicants" else "no"
        )

    zero = sorted([r for r in rows if r["projects_completed"] == 0],
                  key=lambda r: -r["disabled_veterans"])
    some = sorted([r for r in rows if r["projects_completed"] > 0],
                  key=lambda r: (r["projects_per_1000_dv"], -r["disabled_veterans"]))
    ranked = zero + some
    n = len(ranked)
    for i, r in enumerate(ranked, start=1):
        r["gap_rank"] = i
        r["gap_score"] = round(100 * (n - i) / (n - 1))

    flagged = [r for r in rows if r["audit_high_need_no_applicants"] == "yes"]
    print(f"  check: {sum(r['audit_high_need'] == 'yes' for r in rows)} audit high-need counties "
          f"(audit: 35), {len(flagged)} of them with no applicants (audit: 19 -- see README)")

    cols = ["gap_rank", "gap_score", "fips", "county", "disabled_veterans", "disabled_veterans_moe",
            "veterans", "adults_18plus", "dv_per_1000_adults", "pct_veterans_disabled",
            "program_status", "has_lpa", "projects_completed", "projects_per_1000_dv",
            "funding_awarded", "lpas", "audit_high_need", "audit_high_need_no_applicants"]
    write_csv(os.path.join(DATA, "county_gap_scores.csv"), ranked, cols)
    return ranked


# ---------------------------------------------------------------------------
# Step 5: Put the data inside index.html so it is one self-contained file
# ---------------------------------------------------------------------------
def step5_embed(ranked, geojson):
    print("Step 5: embedding data into index.html...")
    path = os.path.join(HERE, "index.html")
    html = open(path).read()
    start, end = "/*DATA_START*/", "/*DATA_END*/"
    i, j = html.index(start) + len(start), html.index(end)
    payload = (
        "\nconst ACS_YEARS = " + json.dumps(f"{int(ACS_YEAR) - 4}-{ACS_YEAR}") + ";"
        "\nconst COUNTIES = " + json.dumps(ranked, separators=(",", ":")) + ";"
        "\nconst GEO = " + json.dumps(geojson, separators=(",", ":")) + ";\n"
    )
    with open(path, "w") as f:
        f.write(html[:i] + payload + html[j:])
    print("  updated index.html")


if __name__ == "__main__":
    os.makedirs(DATA, exist_ok=True)
    acs = step1_census()
    prog = step2_program()
    geo = step3_boundaries()
    ranked = step4_score(acs, prog)
    step5_embed(ranked, geo)
    print("\nDone. Open index.html in a browser.")
