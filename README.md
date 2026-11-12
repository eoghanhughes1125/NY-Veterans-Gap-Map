# NY Disabled Veterans Outreach Gap Map

**Live site:** https://eoghanhughes1125.github.io/NY-Veterans-Gap-Map/

An interactive map and ranked table of New York's 62 counties. It shows where many disabled
veterans live but the **NY Access to Home for Heroes/Veterans Program** (run by NYS Homes and
Community Renewal's Office of Community Renewal) has done little or nothing.

> **Proof of concept, public data only.** This is not an HCR product. It uses none of HCR's
> internal records. Every number comes from the US Census or the NYS Comptroller's published audit.

## Files

| File | What it is |
|---|---|
| `index.html` | The page: map, county details, sortable table, About / Sources / Limitations. Everything is built in, so it opens offline by double-clicking. |
| `analysis.py` | Rebuilds all the data from scratch and refreshes `index.html`. Uses only Python's built-in libraries. |
| `data/acs_s2101_ny_counties.csv` | Census need data per county (cleaned). |
| `data/program_presence.csv` | Program status, projects, funding and LPA per county, with a source on each row. |
| `data/county_gap_scores.csv` | The final ranked table shown on the page. |
| `data/ny_counties.geojson` | County shapes. |
| `data/raw/osc_audit_map_county.csv` | Per-county values read from the Comptroller's interactive audit map. |
| `data/raw/lpa_contracts.csv` | The contracts listed in the audit's Exhibit B. |

## How to rebuild

1. Get a free Census API key at <https://api.census.gov/data/key_signup.html>.
2. Save it in a file named `.census_key` in this folder.
3. Run `python3 analysis.py`.
4. Open `index.html`.

## Data sources

**Need: US Census Bureau, ACS 5-year estimates (2020–2024), table S2101 "Veteran Status".**
Variable IDs were checked against the
[S2101 variable list](https://api.census.gov/data/2024/acs/acs5/subject/groups/S2101.json):

| Variable | Meaning |
|---|---|
| `S2101_C01_001E` | Civilian population 18 and over (adults) |
| `S2101_C03_001E` | Veterans, civilian population 18 and over |
| `S2101_C03_039E` | Veterans "With any disability" |
| `S2101_C03_039M` | Margin of error for the line above |

**Program presence: NYS Comptroller audit 2025-S-10 (issued July 27, 2026).**
- [Interactive audit map](https://www.osc.ny.gov/state-agencies/audits/interactive-maps-homes-and-community-renewal-access-home-heroesveterans-2025-s-10).
  For every county it shows one of three states: "No Applicants", "Not Awarded" (an LPA applied
  but wasn't funded), or the number of veteran households served from April 2021 to October 2025
  in a county with a funded LPA. These values were read from the map's Tableau data on
  Nov 12, 2026 and saved to `data/raw/osc_audit_map_county.csv`. The map has no download button,
  so this file is a hand capture. To refresh it, re-read the map.
- [Full audit report (PDF)](https://www.osc.ny.gov/files/state-agencies/audits/pdf/sga-2026-25s10.pdf),
  Exhibit B (p. 25): LPA names, service-area counties and contract amounts for the 10 contracts
  the auditors sampled.
- [Press release](https://www.osc.ny.gov/press/releases/2026/07/dinapoli-audit-finds-administrative-delays-housing-program-veterans-disabilities).

**County shapes:** Census TIGERweb, Generalized ACS 2024, "Counties 500K" cartographic boundaries.

### Checks against the audit's own figures

The captured map data reproduces the audit's published totals:

| Check | Map data | Audit says |
|---|---|---|
| Counties with a funded LPA | 26 | 26 |
| Counties with at least one project | 15 | 15 of 62 |
| Total projects (households served) | 81 | 81 |
| Disabled veterans statewide (2019–2023) | 173,012 | ~173,000 |
| High-need counties (audit's rule) | 35 | 35 |
| High-need counties with no applicants | **18** (27.4% of disabled veterans) | **19** (28%) |

The one mismatch is the last row. The likely cause is that the audit counted a county added to
an LPA's service area mid-contract, probably Columbia or Sullivan (both high-need, both added to
BRIDGES' area after it was awarded). Adding either one gives 19 counties and 28%. This is a
plausible explanation, not a confirmed one, so the page flags only the 18 that match exactly.

## Method

For each county:

- **Disabled veterans** = `S2101_C03_039E`
- **Disabled veterans per 1,000 adults** = disabled veterans ÷ adults × 1,000
- **Share of veterans disabled** = disabled veterans ÷ veterans
- **Projects** = veteran households served (audit map, Apr 2021 – Oct 2025)
- **Projects per 1,000 disabled veterans** = projects ÷ disabled veterans × 1,000
- **Funding awarded (estimate)**: each Exhibit B contract is split equally across its counties,
  the same way the audit's map splits multi-county awards. This covers fiscal years 2022–2024.

### Gap rank and score

1. **Counties with zero projects come first**, sorted by number of disabled veterans, most first.
   (Zero projects can mean no applicants, applied but not funded, or funded with nothing done yet.)
2. **Then counties with projects**, sorted by projects per 1,000 disabled veterans, fewest first.
3. **Gap score** = the rank restated on a 0–100 scale for map shading: rank 1 → 100, rank 62 → 0.

Why it's done this way: a county with 13,000 disabled veterans and zero projects is a bigger
outreach gap than a county with 300. Among counties with some activity, the fairest comparison
is activity relative to the number of people who could use it.

### Audit flag

The audit defined high-need counties as **over 5,000 disabled veterans, or over 30% of veterans
with a disability**, using 2019–2023 Census data. The flag applies that rule to the same
2019–2023 numbers the audit's map shows, so it matches the audit's list rather than the newer
Census release used for the ranking. A county is flagged when it meets that rule and had
**no applicants**.

## Limitations

- **Projects aren't HCR's own count.** "Projects" are the households served shown on the audit
  map. HCR's internal records may differ.
- **Funding is an estimate.** Equal splitting is an assumption. Five unsampled contracts
  (covering Chautauqua, Clinton, Fulton, Herkimer, Jefferson and Oneida) have no published
  amounts. Those counties show "unknown". The audit's map shows awards by county and fiscal year,
  but only in hover pop-ups that couldn't be read reliably, so they aren't used.
- **Survey error.** ACS figures are estimates with margins of error, shown on the page. In small
  counties these can be large compared with the estimate.
- **Different years.** The ranking uses 2020–2024 Census data. The audit flag uses the audit's
  2019–2023 data on purpose.
- **Outcomes, not effort.** Zero projects doesn't prove that no outreach happened.
- **Hand-captured input.** `data/raw/osc_audit_map_county.csv` was read from the audit map once.
  It will not update by itself if the Comptroller changes the map.
