"""Health inequalities analysis: deprivation gaps, regression, London spotlight, clustering.
Reads data/processed/, writes charts/*.png plus summary tables and key_findings.json."""
import json, pathlib, sqlite3
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import statsmodels.api as sm
from statsmodels.stats.outliers_influence import variance_inflation_factor
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score

ROOT = pathlib.Path(__file__).resolve().parents[1]
P, C = ROOT / "data" / "processed", ROOT / "charts"
C.mkdir(exist_ok=True)
plt.rcParams.update({"figure.dpi": 110, "axes.spines.top": False, "axes.spines.right": False, "font.size": 10})
NAVY, RED, GREY = "#1f3b73", "#c0392b", "#9aa5b1"
F = {}

la = pd.read_csv(P / "la_indicators.csv")
periods = json.loads((P / "indicator_periods.json").read_text())
dec = pd.read_csv(P / "england_deciles.csv")
ts = pd.read_csv(P / "la_le_timeseries.csv")
newham = la[la.area_name == "Newham"].iloc[0]

def save(fig, name):
    fig.tight_layout(); fig.savefig(C / name, bbox_inches="tight"); plt.close(fig)

# 1. England: life expectancy and healthy life expectancy by deprivation decile (latest period)
latest = {m: dec[dec.measure == m].period.iloc[-1] for m in dec.measure.unique()}
fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), sharey=True)
for ax, sex in zip(axes, ["Male", "Female"]):
    for m, col, lab in [("life_expectancy", NAVY, "Life expectancy"), ("healthy_life_expectancy", RED, "Healthy life expectancy")]:
        d = dec[(dec.measure == m) & (dec.sex == sex) & (dec.period == latest[m])].sort_values("decile_no")
        ax.plot(d.decile_no, d.value, "o-", color=col, label=f"{lab} ({latest[m]})")
        g = d.value.iloc[-1] - d.value.iloc[0]
        F[f"{m}_{sex.lower()}_most_deprived"] = round(d.value.iloc[0], 1)
        F[f"{m}_{sex.lower()}_least_deprived"] = round(d.value.iloc[-1], 1)
        F[f"{m}_{sex.lower()}_gap"] = round(g, 1)
    ax.set_title(f"{sex}s, England"); ax.set_xticks(range(1, 11))
    ax.set_xlabel("Deprivation decile of neighbourhood (1 = most deprived, 10 = least)"); ax.legend(frameon=False)
axes[0].set_ylabel("Years")
fig.suptitle("Life expectancy and healthy life expectancy rise steadily with every step down in deprivation")
save(fig, "01_england_deciles.png")
F["le_period"], F["hle_period"] = latest["life_expectancy"], latest["healthy_life_expectancy"]

# 2. Trend in the gap between most and least deprived deciles
g = dec[dec.decile_no.isin([1, 10])].pivot_table(index=["measure", "sex", "period"], columns="decile_no", values="value").reset_index()
g["gap"] = g[10] - g[1]
g["start_year"] = g.period.str[:4].astype(int)
g = g.sort_values(["measure", "sex", "start_year"])
g.to_csv(P / "decile_gap_trend.csv", index=False)
fig, ax = plt.subplots(figsize=(11, 4.5))
for (m, sex), d in g.groupby(["measure", "sex"]):
    ax.plot(d.start_year, d.gap, "o-" if m == "life_expectancy" else "s--", color=NAVY if sex == "Male" else RED,
            label=f"{'LE' if m == 'life_expectancy' else 'HLE'} {sex.lower()}")
ax.set_ylabel("Gap in years (least minus most deprived decile)"); ax.legend(frameon=False, ncol=4)
yrs = sorted(g.start_year.unique()); ax.set_xticks(yrs, [f"{y}-{str(y + 2)[2:]}" for y in yrs], rotation=45, ha="right")
ax.set_title("The deprivation gap between England's most and least deprived 10% of neighbourhoods (3-year pooled periods)")
save(fig, "02_gap_trend.png")
for (m, sex), d in g.groupby(["measure", "sex"]):
    F[f"{m}_{sex.lower()}_gap_first"] = [d.period.iloc[0], round(d.gap.iloc[0], 1)]
    F[f"{m}_{sex.lower()}_gap_peak"] = [d.period.iloc[d.gap.values.argmax()], round(d.gap.max(), 1)]

# 3. Local authorities: deprivation vs life expectancy
x = la.dropna(subset=["le_persons_avg"])
r = x[["imd_2025", "le_persons_avg"]].corr().iloc[0, 1]
slope, icpt = np.polyfit(x.imd_2025, x.le_persons_avg, 1)
F["la_corr_imd_le"] = round(r, 2); F["la_le_per_10_imd_points"] = round(10 * slope, 2)
fig, ax = plt.subplots(figsize=(10, 6))
ax.scatter(x.imd_2025, x.le_persons_avg, c=np.where(x.london, RED, GREY), s=28, alpha=.8)
xx = np.linspace(x.imd_2025.min(), x.imd_2025.max(), 50); ax.plot(xx, icpt + slope * xx, color=NAVY)
for _, row in pd.concat([x.nlargest(4, "imd_2025"), x.nsmallest(3, "imd_2025"), x[x.area_name.isin(["Newham", "Westminster", "Kensington and Chelsea"])]]).drop_duplicates().iterrows():
    ax.annotate(row.area_name, (row.imd_2025, row.le_persons_avg), fontsize=8, xytext=(4, 2), textcoords="offset points")
ax.set_xlabel("IMD 2025 average deprivation score (higher = more deprived)")
ax.set_ylabel(f"Life expectancy at birth, avg of male & female ({periods['le_male']})")
ax.set_title(f"153 English upper-tier local authorities: r = {r:.2f}  (red = London boroughs)")
save(fig, "03_imd_vs_life_expectancy.png")

# 4. Quintiles of local authorities
q = la.groupby("imd_quintile", observed=True)[["le_male", "le_female", "hle_male", "hle_female", "smoking_pct",
                                               "adult_overweight_pct", "inactive_pct", "u75_preventable"]].mean().round(1)
q.to_csv(P / "imd_quintile_summary.csv")
fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
q[["le_male", "le_female", "hle_male", "hle_female"]].plot.bar(ax=axes[0], color=[NAVY, "#5b7bb5", RED, "#e08a7e"], rot=20)
axes[0].set_ylim(50, 90); axes[0].set_ylabel("Years"); axes[0].set_title("Life expectancy & healthy LE by LA deprivation quintile")
q[["u75_preventable"]].plot.bar(ax=axes[1], color=RED, rot=20, legend=False)
axes[1].set_title("Preventable deaths under 75 per 100,000"); axes[1].set_xlabel("")
save(fig, "04_quintiles.png")
for k in ["hle_male", "hle_female", "u75_preventable", "smoking_pct"]:
    F[f"q_{k}"] = [float(q[k].iloc[0]), float(q[k].iloc[-1])]

# 5. Correlation matrix
cols = ["imd_2025", "le_persons_avg", "hle_persons_avg", "u75_preventable", "smoking_pct", "adult_overweight_pct",
        "inactive_pct", "y6_overweight_pct", "air_pollution_pct"]
labels = ["IMD 2025", "Life exp.", "Healthy LE", "Preventable <75", "Smoking", "Adult overweight", "Inactive", "Yr6 overweight", "Air pollution"]
cm = la[cols].corr()
cm.round(3).to_csv(P / "correlations.csv")
fig, ax = plt.subplots(figsize=(8.5, 7))
im = ax.imshow(cm, cmap="RdBu_r", vmin=-1, vmax=1)
ax.set_xticks(range(len(cols)), labels, rotation=45, ha="right"); ax.set_yticks(range(len(cols)), labels)
for i in range(len(cols)):
    for j in range(len(cols)):
        ax.text(j, i, f"{cm.iloc[i, j]:.2f}", ha="center", va="center", fontsize=8, color="white" if abs(cm.iloc[i, j]) > .6 else "black")
fig.colorbar(im, shrink=.8); ax.set_title("Pearson correlations across 153 local authorities")
save(fig, "05_correlations.png")
F["corr_le"] = {l: round(cm.loc["le_persons_avg", c], 2) for c, l in zip(cols, labels) if c != "le_persons_avg"}

# 6. Regression of life expectancy on deprivation and risk factors (standardised coefficients)
X_cols = ["imd_2025", "smoking_pct", "adult_overweight_pct", "inactive_pct", "air_pollution_pct"]
d = la.dropna(subset=X_cols + ["le_persons_avg"])
Z = (d[X_cols] - d[X_cols].mean()) / d[X_cols].std()
Xc = sm.add_constant(Z)
m_full = sm.OLS(d.le_persons_avg, Xc).fit(cov_type="HC3")
m_imd = sm.OLS(d.le_persons_avg, sm.add_constant(Z[["imd_2025"]])).fit(cov_type="HC3")
vif = {c: round(variance_inflation_factor(Z.values, i), 2) for i, c in enumerate(X_cols)}
reg = pd.DataFrame({"coef_years_per_sd": m_full.params, "ci_low": m_full.conf_int()[0], "ci_high": m_full.conf_int()[1],
                    "p_value": m_full.pvalues}).drop("const").round(3)
reg["vif"] = reg.index.map(vif); reg.to_csv(P / "regression_le.csv")
(P / "regression_summary.txt").write_text(str(m_full.summary()))
F["reg_n"] = int(m_full.nobs); F["reg_r2_imd_only"] = round(m_imd.rsquared, 3); F["reg_r2_full"] = round(m_full.rsquared, 3)
F["reg_coefs"] = reg[["coef_years_per_sd", "p_value"]].round(3).to_dict(orient="index")
names = {"imd_2025": "Deprivation (IMD 2025)", "smoking_pct": "Adult smoking %", "adult_overweight_pct": "Adult overweight %",
         "inactive_pct": "Physically inactive %", "air_pollution_pct": "PM2.5 attributable mortality %"}
fig, ax = plt.subplots(figsize=(9, 4))
rr = reg.sort_values("coef_years_per_sd")
ax.errorbar(rr.coef_years_per_sd, [names[i] for i in rr.index], xerr=[rr.coef_years_per_sd - rr.ci_low, rr.ci_high - rr.coef_years_per_sd],
            fmt="o", color=NAVY, capsize=4)
ax.axvline(0, color="grey", lw=1)
ax.set_xlabel("Change in life expectancy (years) per 1 standard deviation, holding others fixed (95% CI, HC3)")
ax.set_title(f"OLS: life expectancy ~ deprivation + risk factors (n={int(m_full.nobs)}, R² = {m_full.rsquared:.2f}; deprivation alone R² = {m_imd.rsquared:.2f})")
save(fig, "06_regression.png")

# 7. London spotlight (incl. Newham)
lon = la[la.london].dropna(subset=["le_persons_avg"]).sort_values("le_persons_avg")
fig, ax = plt.subplots(figsize=(10, 9))
y = np.arange(len(lon))
ax.barh(y, lon.le_persons_avg, color=[RED if n == "Newham" else "#5b7bb5" for n in lon.area_name], label="Life expectancy")
ax.barh(y, lon.hle_persons_avg, color=[("#7b1d14" if n == "Newham" else NAVY) for n in lon.area_name], label="Healthy life expectancy")
ax.set_yticks(y, lon.area_name); ax.set_xlim(50, 88); ax.set_xlabel("Years (average of male and female)")
ax.set_title(f"London boroughs: life expectancy ({periods['le_male']}) and healthy life expectancy ({periods['hle_male']})")
ax.legend(frameon=True, loc="upper left", bbox_to_anchor=(1.0, 1.0))
save(fig, "07_london_boroughs.png")
lon.to_csv(P / "london_boroughs.csv", index=False)
l2 = la[la.london].copy()
for k, asc in [("imd_2025", False), ("le_persons_avg", False), ("hle_persons_avg", False), ("u75_preventable", False), ("smoking_pct", False), ("inactive_pct", False)]:
    F[f"newham_{k}"] = round(float(newham[k]), 1)
    F[f"newham_rank_london_{k}"] = int(l2[k].rank(ascending=asc, method="min")[l2.area_name == "Newham"].iloc[0])
F["london_boroughs_n"] = int(l2.le_persons_avg.notna().sum())
F["newham_rank_england_imd"] = int(la.imd_2025.rank(ascending=False, method="min")[la.area_name == "Newham"].iloc[0])
F["newham_hle_male"], F["newham_hle_female"] = float(newham.hle_male), float(newham.hle_female)
F["newham_le_male"], F["newham_le_female"] = float(newham.le_male), float(newham.le_female)
F["london_best_le"] = [lon.area_name.iloc[-1], round(lon.le_persons_avg.iloc[-1], 1)]
F["london_worst_le"] = [lon.area_name.iloc[0], round(lon.le_persons_avg.iloc[0], 1)]
F["london_best_hle"] = [l2.loc[l2.hle_persons_avg.idxmax(), "area_name"], round(l2.hle_persons_avg.max(), 1)]
F["london_worst_hle"] = [l2.loc[l2.hle_persons_avg.idxmin(), "area_name"], round(l2.hle_persons_avg.min(), 1)]

# Newham life expectancy trend vs England
t = ts[ts.area_name.isin(["Newham", "England"])].copy()
t["start"] = t.period.str[:4].astype(int); t = t.sort_values("start")
fig, ax = plt.subplots(figsize=(10, 4.5))
for (a, s), d in t.groupby(["area_name", "sex"]):
    ax.plot(d.period, d.life_exp, ("-" if a == "Newham" else "--"), color=NAVY if s == "Male" else RED, label=f"{a} {s.lower()}")
ax.set_ylabel("Life expectancy at birth (years)"); ax.legend(frameon=False, ncol=2)
ax.set_title("Newham vs England life expectancy, 3-year pooled"); plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
save(fig, "08_newham_trend.png")
nt = t[t.area_name == "Newham"].sort_values("start")
F["newham_le_first"] = {s: [d.period.iloc[0], float(d.life_exp.iloc[0])] for s, d in nt.groupby("sex")}

# 8. Clustering local authorities on their health profile
K_cols = ["le_persons_avg", "hle_persons_avg", "u75_preventable", "smoking_pct", "adult_overweight_pct",
          "inactive_pct", "y6_overweight_pct", "air_pollution_pct", "imd_2025"]
k_df = la.dropna(subset=K_cols).copy()
Zk = StandardScaler().fit_transform(k_df[K_cols])
sil = {k: silhouette_score(Zk, KMeans(k, n_init=20, random_state=42).fit_predict(Zk)) for k in range(3, 7)}
k_best = max(sil, key=sil.get)
km = KMeans(k_best, n_init=20, random_state=42).fit(Zk)
k_df["cluster"] = km.labels_
order = k_df.groupby("cluster").le_persons_avg.mean().sort_values(ascending=False).index
k_df["cluster"] = k_df.cluster.map({c: i + 1 for i, c in enumerate(order)})
prof = k_df.groupby("cluster")[K_cols].mean().round(1); prof["n_areas"] = k_df.groupby("cluster").size()
prof["london_areas"] = k_df.groupby("cluster").london.sum()
prof["example_areas"] = k_df.groupby("cluster").area_name.apply(lambda s: ", ".join(s.head(6)))
prof.to_csv(P / "cluster_profiles.csv")
k_df[["area_code", "area_name", "region", "cluster"]].to_csv(P / "la_clusters.csv", index=False)
pca = PCA(2).fit(Zk); pc = pca.transform(Zk)
F["k_clusters"] = int(k_best); F["silhouette"] = {int(k): round(v, 3) for k, v in sil.items()}
F["pca_var_explained"] = [round(v, 3) for v in pca.explained_variance_ratio_]
F["clusters"] = {int(c): {"n": int(r.n_areas), "le": float(r.le_persons_avg), "hle": float(r.hle_persons_avg), "imd": float(r.imd_2025),
                          "london": int(r.london_areas)} for c, r in prof.iterrows()}
F["newham_cluster"] = int(k_df.loc[k_df.area_name == "Newham", "cluster"].iloc[0])
fig, ax = plt.subplots(figsize=(10, 6.5))
cmap = plt.get_cmap("tab10")
for c in sorted(k_df.cluster.unique()):
    m = (k_df.cluster == c).values
    r = prof.loc[c]
    ax.scatter(pc[m, 0], pc[m, 1], s=30, color=cmap(c - 1), label=f"Cluster {c} (n={r.n_areas}, LE {r.le_persons_avg}, IMD {r.imd_2025})")
for i, n in enumerate(k_df.area_name):
    if n in ["Newham", "Blackpool", "Wokingham", "Kensington and Chelsea", "Tower Hamlets", "Hartlepool", "Rutland", "Manchester"]:
        ax.annotate(n, pc[i], fontsize=8, xytext=(4, 2), textcoords="offset points")
ax.set_xlabel(f"PC1 ({pca.explained_variance_ratio_[0]:.0%} of variance)"); ax.set_ylabel(f"PC2 ({pca.explained_variance_ratio_[1]:.0%})")
ax.set_title(f"K-means clusters of local authority health profiles (k={k_best}, chosen by silhouette)"); ax.legend(frameon=False, fontsize=8)
save(fig, "09_clusters.png")

# 9. Regional summary with SQL (SQLite)
con = sqlite3.connect(":memory:"); la.to_sql("la", con, index=False)
reg_sql = pd.read_sql("""
    SELECT region, COUNT(*) AS areas,
           ROUND(AVG(imd_2025), 1) AS avg_imd, ROUND(AVG(le_persons_avg), 1) AS avg_le,
           ROUND(AVG(hle_persons_avg), 1) AS avg_hle, ROUND(MAX(le_persons_avg) - MIN(le_persons_avg), 1) AS le_range,
           ROUND(AVG(smoking_pct), 1) AS avg_smoking
    FROM la WHERE le_persons_avg IS NOT NULL GROUP BY region ORDER BY avg_le DESC""", con)
reg_sql.to_csv(P / "region_summary.csv", index=False)
F["region_summary"] = reg_sql.to_dict(orient="records")

# Extremes across England
x = la.dropna(subset=["le_persons_avg"])
F["la_best_le"] = [x.loc[x.le_persons_avg.idxmax(), "area_name"], round(x.le_persons_avg.max(), 1)]
F["la_worst_le"] = [x.loc[x.le_persons_avg.idxmin(), "area_name"], round(x.le_persons_avg.min(), 1)]
F["la_best_hle"] = [x.loc[x.hle_persons_avg.idxmax(), "area_name"], round(x.hle_persons_avg.max(), 1)]
F["la_worst_hle"] = [x.loc[x.hle_persons_avg.idxmin(), "area_name"], round(x.hle_persons_avg.min(), 1)]
F["la_male_le_range"] = [x.loc[x.le_male.idxmin(), "area_name"], float(x.le_male.min()), x.loc[x.le_male.idxmax(), "area_name"], float(x.le_male.max())]
F["periods"] = {k: v for k, v in periods.items() if k != "england_values"}
F["england"] = periods["england_values"]
(P / "key_findings.json").write_text(json.dumps(F, indent=2, default=str))
print(json.dumps(F, indent=1, default=str))
