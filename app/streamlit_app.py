"""Streamlit dashboard: health inequalities across English local authorities.
Run: streamlit run app/streamlit_app.py"""
import json, pathlib
import pandas as pd, plotly.express as px, streamlit as st

P = pathlib.Path(__file__).resolve().parents[1] / "data" / "processed"
st.set_page_config(page_title="Health inequalities in England", layout="wide")

@st.cache_data
def load():
    return (pd.read_csv(P / "la_indicators.csv"), pd.read_csv(P / "england_deciles.csv"),
            pd.read_csv(P / "la_le_timeseries.csv"), pd.read_csv(P / "la_clusters.csv"),
            json.loads((P / "key_findings.json").read_text()))
la, dec, ts, cl, F = load()
la = la.merge(cl[["area_code", "cluster"]], on="area_code", how="left")
LABELS = {"imd_2025": "IMD 2025 deprivation score", "le_persons_avg": "Life expectancy (avg M/F)",
          "hle_persons_avg": "Healthy life expectancy (avg M/F)", "le_male": "Life expectancy, male",
          "le_female": "Life expectancy, female", "hle_male": "Healthy LE, male", "hle_female": "Healthy LE, female",
          "u75_preventable": "Preventable deaths <75 per 100k", "smoking_pct": "Adult smoking %",
          "adult_overweight_pct": "Adult overweight %", "inactive_pct": "Physically inactive %",
          "y6_overweight_pct": "Year 6 overweight %", "air_pollution_pct": "PM2.5 attributable mortality %",
          "le_gap_within_male": "Within-area LE gap, male (SII)", "le_gap_within_female": "Within-area LE gap, female (SII)"}

st.title("Health inequalities across English local authorities")
st.caption("OHID Fingertips public health data (Open Government Licence v3.0). "
           "Built by Anthony Adusei-Poku (github.com/anthony07-max).")
c = st.columns(4)
c[0].metric("Male LE gap, most vs least deprived 10%", f"{F['life_expectancy_male_gap']} yrs", F["le_period"], delta_color="off")
c[1].metric("Female LE gap", f"{F['life_expectancy_female_gap']} yrs", F["le_period"], delta_color="off")
c[2].metric("Healthy LE gap (female)", f"{F['healthy_life_expectancy_female_gap']} yrs", F["hle_period"], delta_color="off")
c[3].metric("Correlation: LA deprivation vs LE", F["la_corr_imd_le"], f"{F['reg_n']} areas", delta_color="off")

t1, t2, t3, t4, t5 = st.tabs(["England by deprivation", "Explore areas", "London & Newham", "Clusters", "Area profile"])
with t1:
    m = st.radio("Measure", ["life_expectancy", "healthy_life_expectancy"], horizontal=True)
    d = dec[dec.measure == m]
    period = st.select_slider("Period", sorted(d.period.unique()), value=sorted(d.period.unique())[-1])
    st.plotly_chart(px.line(d[d.period == period], x="decile_no", y="value", color="sex", markers=True,
                            labels={"decile_no": "Deprivation decile (1 = most deprived)", "value": "Years"}), width="stretch")
    g = d[d.decile_no.isin([1, 10])].pivot_table(index=["sex", "period"], columns="decile_no", values="value").reset_index()
    g["gap"] = g[10] - g[1]
    st.plotly_chart(px.line(g, x="period", y="gap", color="sex", markers=True, title="Gap: least minus most deprived decile (years)"), width="stretch")
with t2:
    a, b = st.columns(2)
    xv = a.selectbox("X axis", list(LABELS), index=0, format_func=LABELS.get)
    yv = b.selectbox("Y axis", list(LABELS), index=1, format_func=LABELS.get)
    regions = st.multiselect("Regions", sorted(la.region.dropna().unique()), default=sorted(la.region.dropna().unique()))
    d = la[la.region.isin(regions)]
    st.plotly_chart(px.scatter(d, x=xv, y=yv, color="region", hover_name="area_name", trendline="ols",
                               trendline_scope="overall", labels=LABELS, height=600), width="stretch")
    st.write(f"Pearson r = {d[[xv, yv]].corr().iloc[0, 1]:.2f} across {d[[xv, yv]].dropna().shape[0]} areas")
with t3:
    lon = la[la.london].sort_values("le_persons_avg")
    st.plotly_chart(px.bar(lon, x=["hle_persons_avg", "le_persons_avg"], y="area_name", orientation="h", barmode="overlay",
                           height=850, labels={"value": "Years", "area_name": ""}, title="London boroughs: healthy LE vs LE"), width="stretch")
    n = ts[ts.area_name.isin(["Newham", "England"])].copy()
    n["start"] = n.period.str[:4].astype(int)
    st.plotly_chart(px.line(n.sort_values("start"), x="period", y="life_exp", color="area_name", line_dash="sex",
                            title="Newham vs England life expectancy"), width="stretch")
with t4:
    st.dataframe(pd.read_csv(P / "cluster_profiles.csv"), width="stretch", hide_index=True)
    st.plotly_chart(px.scatter(la.dropna(subset=["cluster"]), x="imd_2025", y="hle_persons_avg", color=la.dropna(subset=["cluster"]).cluster.astype(int).astype(str),
                               hover_name="area_name", labels=LABELS | {"color": "cluster"}), width="stretch")
with t5:
    area = st.selectbox("Local authority", sorted(la.area_name), index=sorted(la.area_name).index("Newham"))
    row = la[la.area_name == area].iloc[0]
    eng = F["england"]
    tab = pd.DataFrame([{"Indicator": LABELS[k], "Area": row[k], "England": eng.get(k),
                         "Rank of 153 (1 = highest)": int(la[k].rank(ascending=False, method="min")[la.area_name == area].iloc[0]) if pd.notna(row[k]) else None}
                        for k in LABELS if k in eng])
    st.write(f"**{area}** ({row.region}), IMD 2025 quintile: {row.imd_quintile}")
    st.dataframe(tab, width="stretch", hide_index=True)
    st.plotly_chart(px.line(ts[ts.area_name == area].assign(start=lambda x: x.period.str[:4].astype(int)).sort_values("start"),
                            x="period", y="life_exp", color="sex", title=f"{area}: life expectancy over time"), width="stretch")
