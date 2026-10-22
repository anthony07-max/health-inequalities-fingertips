"""Tidy the raw Fingertips downloads into analysis-ready tables in data/processed/.

Outputs
- la_indicators.csv        one row per upper tier local authority, latest period of each indicator
- indicator_periods.json   which time period each indicator column refers to
- england_deciles.csv      England life expectancy / healthy life expectancy by LSOA deprivation decile over time
- la_le_timeseries.csv     life expectancy (3-year pooled) for every local authority over time
"""
import json, pathlib
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW, OUT = ROOT / "data" / "raw", ROOT / "data" / "processed"

# column name -> (indicator id, sex, age filter or None, period length filter or None)
SPEC = {
    "imd_2025":            (94240, "Persons", "All ages", None),
    "le_male":             (90366, "Male",    "All ages", "3y"),
    "le_female":           (90366, "Female",  "All ages", "3y"),
    "hle_male":            (90362, "Male",    "All ages", None),
    "hle_female":          (90362, "Female",  "All ages", None),
    "le_gap_within_male":  (92901, "Male",    "All ages", None),
    "le_gap_within_female":(92901, "Female",  "All ages", None),
    "u75_preventable":     (93721, "Persons", "<75 yrs", None),
    "smoking_pct":         (92443, "Persons", "18+ yrs", None),
    "adult_overweight_pct":(93088, "Persons", "18+ yrs", None),
    "inactive_pct":        (93015, "Persons", "19+ yrs", None),
    "y6_overweight_pct":   (20602, "Persons", "10-11 yrs", None),
    "air_pollution_pct":   (93861, "Persons", "30+ yrs", None),
}

def load(iid):
    d = pd.read_csv(RAW / f"{iid}.csv", low_memory=False).drop_duplicates()
    d["Category Type"] = d["Category Type"].astype("string").str.strip()
    return d

def latest(iid, sex, age, rng):
    d = load(iid)
    d = d[d["Category Type"].isna() & (d["Sex"] == sex)]
    if age: d = d[d["Age"] == age]
    if rng: d = d[d["Time period range"] == rng]
    d = d[d["Value"].notna()]
    period = d.loc[d["Time period Sortable"].idxmax(), "Time period"]
    d = d[d["Time period"] == period].drop_duplicates("Area Code")  # England appears twice (with/without parent)
    return d.set_index("Area Code")["Value"], d.set_index("Area Code")["Area Name"], period

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cols, names, periods = {}, {}, {}
    for col, (iid, sex, age, rng) in SPEC.items():
        v, n, p = latest(iid, sex, age, rng)
        cols[col], periods[col] = v, str(p)
        names.update(n.to_dict())
    df = pd.DataFrame(cols)
    eng = df.loc["E92000001"].to_dict()
    df = df.drop(index="E92000001")
    df.insert(0, "area_name", df.index.map(names))
    lookup = json.loads((RAW / "region_lookup.json").read_text())
    reg_names = {r["Code"]: r["Short"] for r in json.loads((RAW / "regions.json").read_text())}
    to_region = {c: reg_names[r] for r, cs in lookup.items() for c in cs}
    df.insert(1, "region", df.index.map(to_region))
    df.insert(2, "london", df["region"] == "London")
    df["le_persons_avg"] = df[["le_male", "le_female"]].mean(axis=1)
    df["hle_persons_avg"] = df[["hle_male", "hle_female"]].mean(axis=1)
    df["imd_quintile"] = pd.qcut(df["imd_2025"], 5, labels=["Q1 least deprived", "Q2", "Q3", "Q4", "Q5 most deprived"])
    df.index.name = "area_code"
    df.round(3).to_csv(OUT / "la_indicators.csv")
    periods["england_values"] = {k: (round(float(v), 3) if pd.notna(v) else None) for k, v in eng.items()}
    (OUT / "indicator_periods.json").write_text(json.dumps(periods, indent=2))

    # England, by LSOA 2021 deprivation decile (national deciles), 3-year pooled
    rows = []
    for iid, name in [(90366, "life_expectancy"), (90362, "healthy_life_expectancy")]:
        d = load(iid)
        d = d[(d["Area Type"] == "England") & d["Category Type"].str.startswith("LSOA21", na=False)]
        d = d.drop_duplicates(["Sex", "Time period", "Category"])
        rows.append(d.assign(measure=name)[["measure", "Sex", "Time period", "Time period Sortable", "Category", "Value"]])
    dec = pd.concat(rows).rename(columns={"Sex": "sex", "Time period": "period", "Time period Sortable": "sort",
                                           "Category": "decile", "Value": "value"})
    order = ["Most deprived decile", "Second most deprived decile", "Third more deprived decile",
             "Fourth more deprived decile", "Fifth more deprived decile", "Fifth less deprived decile",
             "Fourth less deprived decile", "Third less deprived decile", "Second least deprived decile",
             "Least deprived decile"]
    dec["decile_no"] = dec["decile"].map({c: i + 1 for i, c in enumerate(order)})  # 1 = most deprived
    dec.sort_values(["measure", "sex", "sort", "decile_no"]).drop(columns="sort").to_csv(OUT / "england_deciles.csv", index=False)

    # LA life expectancy time series (3-year pooled)
    d = load(90366)
    d = d[d["Category Type"].isna() & (d["Time period range"] == "3y")]
    d = d.drop_duplicates(["Area Code", "Sex", "Time period"])
    ts = d[["Area Code", "Area Name", "Sex", "Time period", "Value"]].rename(columns={
        "Area Code": "area_code", "Area Name": "area_name", "Sex": "sex", "Time period": "period", "Value": "life_exp"})
    ts.to_csv(OUT / "la_le_timeseries.csv", index=False)
    print(df.shape, "local authorities;", periods)

if __name__ == "__main__":
    main()
