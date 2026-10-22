"""Download public health indicators for English local authorities from the OHID Fingertips API.

Source: Office for Health Improvement and Disparities (OHID), Fingertips public health data,
https://fingertips.phe.org.uk  (API docs: https://fingertips.phe.org.uk/api).
Contains public sector information licensed under the Open Government Licence v3.0.

Each indicator is saved as data/raw/<indicator_id>.csv for upper tier local authorities
(counties and unitary authorities, post April 2023 boundaries, area type 502) plus England.
"""
import pathlib, time, requests

RAW = pathlib.Path(__file__).resolve().parents[1] / "data" / "raw"
API = "https://fingertips.phe.org.uk/api/all_data/csv/by_indicator_id"
AREA_TYPE = 502  # Upper tier local authorities (post 4/23)

INDICATORS = {
    90366: "Life expectancy at birth",
    90362: "Healthy life expectancy at birth",
    92901: "Inequality in life expectancy at birth (slope index, within LA)",
    93721: "Under 75 mortality rate from causes considered preventable",
    92443: "Smoking prevalence in adults (18+), current smokers (APS)",
    93088: "Overweight (including obesity) prevalence in adults",
    93015: "Percentage of physically inactive adults",
    20602: "Year 6 prevalence of overweight (including obesity)",
    93861: "Fraction of mortality attributable to particulate air pollution",
    94240: "Deprivation score (IMD 2025)",
}

def main():
    RAW.mkdir(parents=True, exist_ok=True)
    for iid, name in INDICATORS.items():
        out = RAW / f"{iid}.csv"
        if out.exists() and out.stat().st_size > 1000:
            print("Cached", iid, name); continue
        print("Downloading", iid, name)
        for attempt in range(3):
            try:
                r = requests.get(API, params={"indicator_ids": iid, "child_area_type_id": AREA_TYPE,
                                              "parent_area_type_id": 15}, timeout=300)
                r.raise_for_status(); out.write_bytes(r.content); break
            except requests.RequestException as e:
                print("  retry after error:", e); time.sleep(5 * (attempt + 1))
        else:
            raise SystemExit(f"Failed to download indicator {iid}")
    # Lookup of upper tier local authorities to their region (Government Office Region)
    base = "https://fingertips.phe.org.uk/api/"
    (RAW / "region_lookup.json").write_text(requests.get(base + "parent_to_child_areas", params={
        "child_area_type_id": AREA_TYPE, "parent_area_type_id": 6}, timeout=120).text)
    (RAW / "regions.json").write_text(requests.get(base + "areas/by_area_type", params={"area_type_id": 6}, timeout=120).text)
    print("Done:", sorted(p.name for p in RAW.iterdir()))

if __name__ == "__main__":
    main()
