"""
Florida hurricane climatology + a CLIPER-style track model built on NOAA HURDAT2.
Data: hurdat2-1851-2025-092326.txt (NHC), reduced to date,time,recid,status,lat,lon,wind,pres.
"""
import numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from global_land_mask import globe
from sklearn.linear_model import Ridge
from sklearn.preprocessing import PolynomialFeatures, StandardScaler
from sklearn.pipeline import make_pipeline

OUT = "output/"
import os; os.makedirs(OUT, exist_ok=True)

# ---------------------------------------------------------------- parse
rows, sid, name = [], None, None
for line in open("hurdat2_compact.csv"):
    p = line.rstrip("\n").split(",")
    if p[0].startswith("#"):
        sid, name = p[0][1:], p[1]; continue
    lat = float(p[4][:-1]) * (1 if p[4][-1] == "N" else -1)
    lon = float(p[5][:-1]) * (-1 if p[5][-1] == "W" else 1)
    rows.append((sid, name, p[0], p[1], p[2], p[3], lat, lon, int(p[6]), int(p[7])))
df = pd.DataFrame(rows, columns=["sid","name","date","time","recid","status","lat","lon","wind","pres"])
df["t"] = pd.to_datetime(df.date + df.time.str.zfill(4), format="%Y%m%d%H%M")
df["year"] = df.t.dt.year
print(f"HURDAT2 parsed: {df.sid.nunique()} storms, {len(df)} fixes, {df.year.min()}-{df.year.max()}")

def sscat(w):   # Saffir-Simpson from 1-min sustained wind (kt)
    return 0 if w < 64 else 1 if w < 83 else 2 if w < 96 else 3 if w < 113 else 4 if w < 137 else 5
CAT_COL = {0:"#9ecae1", 1:"#ffffb2", 2:"#fecc5c", 3:"#fd8d3c", 4:"#f03b20", 5:"#bd0026"}
CAT_LBL = {0:"Tropical storm / depression", 1:"Category 1", 2:"Category 2", 3:"Category 3", 4:"Category 4", 5:"Category 5"}

def gc_nmi(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2-lat1)/2)**2 + np.cos(lat1)*np.cos(lat2)*np.sin((lon2-lon1)/2)**2
    return 2*np.arcsin(np.sqrt(np.clip(a, 0, 1))) * 3440.065

# ---------------------------------------------------------------- Florida landfall detection
# A storm "hit Florida" if its track (interpolated hourly between 6-h fixes) passes over land
# inside the Florida box. The box is clipped so Alabama/Georgia land is excluded.
def in_florida(lat, lon):
    box = (lat >= 24.4) & (lat <= 31.0) & (lon >= -87.6) & (lon <= -79.8)
    not_al = ~((lon < -87.4) & (lat > 30.3))           # Alabama coast near Mobile
    not_ga = ~((lat > 30.72) & (lon > -82.0))          # Georgia above the FL state line east of the Okefenokee
    return box & not_al & not_ga & globe.is_land(lat, lon)

fl_hits = {}
for sid, g in df.groupby("sid", sort=False):
    g = g.sort_values("t")
    la, lo, w, tt = g.lat.values, g.lon.values, g.wind.values, g.t.values
    best = None
    for i in range(len(g)-1):
        dt = (tt[i+1]-tt[i]) / np.timedelta64(1, "h")
        if dt <= 0 or dt > 24: continue
        n = int(dt)
        f = np.linspace(0, 1, n+1)
        li, oi = la[i]+(la[i+1]-la[i])*f, lo[i]+(lo[i+1]-lo[i])*f
        m = in_florida(li, oi)
        if m.any():
            wmax = max(w[i], w[i+1])
            if best is None or wmax > best: best = wmax
    if len(g) == 1 and in_florida(np.array([la[0]]), np.array([lo[0]]))[0]:
        best = w[0]
    if best is not None: fl_hits[sid] = best
fl = pd.DataFrame({"sid": list(fl_hits), "wind_fl": list(fl_hits.values())})
meta = df.groupby("sid").agg(name=("name","first"), year=("year","first"), first_t=("t","min"), maxwind=("wind","max")).reset_index()
fl = fl.merge(meta, on="sid")
fl["cat_fl"] = fl.wind_fl.apply(sscat)
fl.sort_values("first_t").to_csv(OUT+"florida_storms_1851_2025.csv", index=False)
print(f"Florida-impacting storms: {len(fl)} total; hurricanes at impact: {(fl.cat_fl>=1).sum()}; major (Cat 3+): {(fl.cat_fl>=3).sum()}")
print("Check known storms:", {n: (fl[fl.name==n][["year","cat_fl"]].values.tolist()) for n in ["ANDREW","IRMA","MICHAEL","IAN","MILTON","HELENE","CHARLEY","WILMA"]})

# ---------------------------------------------------------------- map helpers
def coast(ax, lat0, lat1, lon0, lon1, step=0.04):
    lats = np.arange(lat0, lat1, step); lons = np.arange(lon0, lon1, step)
    LON, LAT = np.meshgrid(lons, lats)
    land = globe.is_land(LAT, LON)
    ax.contourf(LON, LAT, land, levels=[0.5, 1.5], colors=["#e8e4d8"], zorder=0)
    ax.contour(LON, LAT, land, levels=[0.5], colors="#6b6b6b", linewidths=0.6, zorder=1)
    ax.set_facecolor("#dbe9f4"); ax.set_xlim(lon0, lon1); ax.set_ylim(lat0, lat1)
    ax.set_aspect(1/np.cos(np.radians((lat0+lat1)/2)))
    ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
    ax.grid(alpha=0.25, linewidth=0.5)

def legend_cats(ax, loc="lower left"):
    h = [Line2D([0],[0], color=CAT_COL[c], lw=2.5, label=CAT_LBL[c]) for c in range(6)]
    ax.legend(handles=h, loc=loc, fontsize=8, framealpha=0.9, title="Strength while over Florida", title_fontsize=8)

# ---------------------------------------------------------------- Map 1: every Florida storm track
sub = df[df.sid.isin(fl.sid)].merge(fl[["sid","cat_fl"]], on="sid")
fig, ax = plt.subplots(figsize=(13, 9), dpi=150)
coast(ax, 5, 50, -100, -40, step=0.08)
for c in range(6):
    for sid, g in sub[sub.cat_fl == c].groupby("sid"):
        g = g.sort_values("t")
        ax.plot(g.lon, g.lat, color=CAT_COL[c], lw=1.6 if c >= 3 else 0.9, alpha=0.95 if c >= 3 else 0.6, zorder=2+c)
ax.plot([-82.32], [29.65], marker="*", color="black", ms=11, zorder=20); ax.annotate("Gainesville", (-82.32, 29.65), xytext=(5, 6), textcoords="offset points", fontsize=9, fontweight="bold", bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.85), zorder=21)
legend_cats(ax)
ax.set_title(f"Every tropical cyclone whose track crossed Florida, 1851-2025  (n = {len(fl)})\n"
             "Color = Saffir-Simpson strength at the time it was over Florida.  Source: NOAA/NHC HURDAT2", fontsize=12)
fig.tight_layout(); fig.savefig(OUT+"map1_florida_tracks_1851_2025.png"); plt.close(fig)

# ---------------------------------------------------------------- Map 2: where Florida hurricanes come from
hur = fl[fl.cat_fl >= 1]
sub_h = df[df.sid.isin(hur.sid)]
fig, axes = plt.subplots(1, 2, figsize=(16, 6.2), dpi=150)
MONTH_COL = {6:"#1b9e77", 7:"#7570b3", 8:"#d95f02", 9:"#e7298a", 10:"#66a61e", 11:"#e6ab02"}
MONTH_LBL = {6:"June", 7:"July", 8:"August", 9:"September", 10:"October", 11:"November"}
# left: genesis points (first fix) of Florida hurricanes, colored by month of Florida impact
ax = axes[0]; coast(ax, 5, 45, -100, -20, step=0.1)
gen = sub_h.sort_values("t").groupby("sid").first().reset_index()
# month of impact: month of the fix closest to Florida land crossing - approximated by first fix inside box
imp_month = {}
for sid, g in sub_h.groupby("sid"):
    g = g.sort_values("t"); m = in_florida(g.lat.values, g.lon.values)
    imp_month[sid] = g.t.iloc[np.argmax(m)].month if m.any() else g.t.iloc[len(g)//2].month
gen["imp_month"] = gen.sid.map(imp_month)
for mth in [6,7,8,9,10,11]:
    gg = gen[gen.imp_month == mth]
    ax.scatter(gg.lon, gg.lat, s=28, color=MONTH_COL[mth], edgecolor="k", linewidth=0.3, label=f"{MONTH_LBL[mth]} ({len(gg)})", zorder=5)
other = gen[~gen.imp_month.isin([6,7,8,9,10,11])]
if len(other): ax.scatter(other.lon, other.lat, s=28, color="grey", edgecolor="k", linewidth=0.3, label=f"Off-season ({len(other)})", zorder=5)
ax.legend(fontsize=8, loc="upper right", title="Month the storm reached Florida", title_fontsize=8)
ax.set_title(f"Where Florida hurricanes were born: first recorded position\nof the {len(hur)} storms that hit Florida at hurricane strength, 1851-2025", fontsize=11)
# right: 2-D histogram of all track points of FL hurricanes 48h before impact
ax = axes[1]; coast(ax, 5, 45, -100, -20, step=0.1)
pts = []
for sid, g in sub_h.groupby("sid"):
    g = g.sort_values("t"); m = in_florida(g.lat.values, g.lon.values)
    if not m.any(): continue
    t_imp = g.t.iloc[np.argmax(m)]
    gg = g[(g.t >= t_imp - pd.Timedelta(hours=72)) & (g.t < t_imp)]
    pts.append(gg[["lat","lon"]])
pts = pd.concat(pts)
H, xe, ye = np.histogram2d(pts.lon, pts.lat, bins=[np.arange(-100, -19, 2), np.arange(5, 46, 2)])
Hm = np.ma.masked_where(H.T == 0, H.T)
pc = ax.pcolormesh(xe, ye, Hm, cmap="YlOrRd", alpha=0.85, zorder=3)
plt.colorbar(pc, ax=ax, fraction=0.03, pad=0.02, label="6-hourly storm positions per 2°x2° cell")
ax.set_title("The 3 days before landfall: where Florida hurricanes were\nduring the 72 hours before reaching the state (all years)", fontsize=11)
fig.suptitle("Where do Florida's hurricanes come from?   Source: NOAA/NHC HURDAT2 (1851-2025)", fontsize=13)
fig.tight_layout(rect=(0,0,1,0.95)); fig.savefig(OUT+"map2_where_florida_hurricanes_come_from.png"); plt.close(fig)

# ---------------------------------------------------------------- Chart: hits per decade + month
fig, axes = plt.subplots(1, 2, figsize=(14, 5), dpi=150)
fl["decade"] = (fl.year // 10) * 10
dec = fl.groupby("decade").agg(all=("sid","count"), hur=("cat_fl", lambda s: (s>=1).sum()), maj=("cat_fl", lambda s: (s>=3).sum())).reindex(range(1850, 2030, 10), fill_value=0)
ax = axes[0]
ax.bar(dec.index, dec["all"], width=8, color="#9ecae1", label="Tropical storm or stronger")
ax.bar(dec.index, dec["hur"], width=8, color="#fd8d3c", label="Hurricane (Cat 1+)")
ax.bar(dec.index, dec["maj"], width=8, color="#bd0026", label="Major hurricane (Cat 3+)")
ax.set_xticks(range(1850, 2030, 20)); ax.set_xticklabels([f"{d}s" for d in range(1850, 2030, 20)], rotation=45)
ax.set_ylabel("Storms crossing Florida"); ax.set_title("Florida storm crossings by decade (2020s = 2020-2025 only)")
ax.legend(fontsize=8); ax.grid(axis="y", alpha=0.3)
ax = axes[1]
fl["imp_month"] = fl.sid.map(lambda s: imp_month.get(s, np.nan))
mon_all = fl.groupby(fl.first_t.dt.month).size().reindex(range(1,13), fill_value=0)
mon_h = fl[fl.cat_fl>=1].groupby(fl[fl.cat_fl>=1].imp_month).size().reindex(range(1,13), fill_value=0)
ax.bar(mon_all.index-0.2, mon_all.values, width=0.4, color="#9ecae1", label="All Florida storms (month formed)")
ax.bar(mon_h.index+0.2, mon_h.values, width=0.4, color="#f03b20", label="Florida hurricanes (month of impact)")
ax.set_xticks(range(1,13)); ax.set_xticklabels(["J","F","M","A","M","J","J","A","S","O","N","D"])
ax.set_title("When Florida gets hit (1851-2025)"); ax.legend(fontsize=8); ax.grid(axis="y", alpha=0.3)
fig.tight_layout(); fig.savefig(OUT+"chart_florida_by_decade_and_month.png"); plt.close(fig)
print("Hurricane impacts by month:", mon_h.to_dict())
print("Per decade:\n", dec.to_string())

# ---------------------------------------------------------------- CLIPER-style model
# Build samples at every synoptic (00/06/12/18Z) fix that has 12 h of history and up to 72 h of future.
HORIZONS = [12, 24, 48, 72]
samples = []
for sid, g in df[df.year >= 1950].groupby("sid", sort=False):
    g = g[g.t.dt.hour.isin([0,6,12,18]) & (g.t.dt.minute == 0)].sort_values("t").drop_duplicates("t")
    if len(g) < 5: continue
    t = g.t.values; la = g.lat.values; lo = g.lon.values; w = g.wind.values
    idx = {tt: i for i, tt in enumerate(t)}
    for i in range(len(g)):
        tm12 = t[i] - np.timedelta64(12, "h"); tm6 = t[i] - np.timedelta64(6, "h")
        if tm12 not in idx or tm6 not in idx: continue
        fut = {}
        for h in HORIZONS:
            tf = t[i] + np.timedelta64(h, "h")
            fut[h] = idx.get(tf)
        if fut[12] is None: continue
        doy = pd.Timestamp(t[i]).dayofyear
        s = dict(sid=sid, year=g.year.iloc[0], t=t[i], lat=la[i], lon=lo[i], wind=w[i],
                 u12=lo[i]-lo[idx[tm12]], v12=la[i]-la[idx[tm12]],   # 12-h motion (deg)
                 u6=lo[i]-lo[idx[tm6]], v6=la[i]-la[idx[tm6]],
                 sdoy=np.sin(2*np.pi*doy/365.25), cdoy=np.cos(2*np.pi*doy/365.25))
        for h in HORIZONS:
            j = fut[h]
            s[f"dlat{h}"] = la[j]-la[i] if j is not None else np.nan
            s[f"dlon{h}"] = lo[j]-lo[i] if j is not None else np.nan
        samples.append(s)
S = pd.DataFrame(samples)
S["fl"] = S.sid.isin(fl.sid)
FEATS = ["lat","lon","wind","u12","v12","u6","v6","sdoy","cdoy"]
train = S[S.year <= 2014]; test = S[S.year >= 2015]
print(f"Model samples: train {len(train)} (1950-2014), test {len(test)} (2015-2025)")

results = []
models = {}
for h in HORIZONS:
    tr = train.dropna(subset=[f"dlat{h}"]); te = test.dropna(subset=[f"dlat{h}"])
    mdl = make_pipeline(StandardScaler(), PolynomialFeatures(2, include_bias=False), Ridge(alpha=3.0))
    mdl.fit(tr[FEATS], tr[[f"dlat{h}", f"dlon{h}"]]); models[h] = mdl
    pred = mdl.predict(te[FEATS])
    err_model = gc_nmi(te.lat + te[f"dlat{h}"], te.lon + te[f"dlon{h}"], te.lat + pred[:,0], te.lon + pred[:,1])
    # persistence: keep the last 12-h motion going
    k = h / 12.0
    err_pers = gc_nmi(te.lat + te[f"dlat{h}"], te.lon + te[f"dlon{h}"], te.lat + k*te.v12, te.lon + k*te.u12)
    # climatology-only: predict mean displacement for the training set (no motion info)
    err_clim = gc_nmi(te.lat + te[f"dlat{h}"], te.lon + te[f"dlon{h}"], te.lat + tr[f"dlat{h}"].mean(), te.lon + tr[f"dlon{h}"].mean())
    flm = te.fl.values
    results.append(dict(horizon_h=h, n_cases=len(te), model_err_nmi=err_model.mean(), persistence_err_nmi=err_pers.mean(),
                        climatology_err_nmi=err_clim.mean(), model_err_FLstorms_nmi=err_model[flm].mean(), n_FL=flm.sum()))
R = pd.DataFrame(results)
# NHC published 2024 numbers (Verification_2024.pdf, Table 2) for comparison
NHC = {12:(19.2, 41.7), 24:(28.0, 88.4), 48:(45.4, 199.0), 72:(66.9, 281.1)}
R["NHC_official_2024_nmi"] = R.horizon_h.map(lambda h: NHC[h][0]); R["NHC_CLIPER5_2024_nmi"] = R.horizon_h.map(lambda h: NHC[h][1])
R = R.round(1); R.to_csv(OUT+"model_results.csv", index=False)
print(R.to_string(index=False))

fig, ax = plt.subplots(figsize=(9, 5.5), dpi=150)
ax.plot(R.horizon_h, R.climatology_err_nmi, "o--", color="grey", label="Climatology only (average motion)")
ax.plot(R.horizon_h, R.persistence_err_nmi, "s--", color="#7570b3", label="Persistence (keep moving the same way)")
ax.plot(R.horizon_h, R.model_err_nmi, "o-", color="#d95f02", lw=2.5, label="Our CLIPER-style model (2015-2025 test)")
ax.plot(R.horizon_h, R.NHC_CLIPER5_2024_nmi, "^:", color="#1b9e77", label="NHC CLIPER5 baseline, 2024 season")
ax.plot(R.horizon_h, R.NHC_official_2024_nmi, "D-", color="black", lw=2.5, label="NHC official forecast, 2024 season")
ax.set_xticks(HORIZONS); ax.set_xlabel("Forecast lead time (hours)"); ax.set_ylabel("Average position error (nautical miles)")
ax.set_title("How far off is each method, on average?\nA statistics-only model vs the National Hurricane Center", fontsize=12)
ax.grid(alpha=0.3); ax.legend(fontsize=9)
for h, e in zip(R.horizon_h, R.model_err_nmi): ax.annotate(f"{e:.0f}", (h, e), xytext=(6, 4), textcoords="offset points", fontsize=8, color="#d95f02")
for h, e in zip(R.horizon_h, R.NHC_official_2024_nmi): ax.annotate(f"{e:.0f}", (h, e), xytext=(6, -12), textcoords="offset points", fontsize=8)
fig.tight_layout(); fig.savefig(OUT+"chart_model_vs_nhc_error.png"); plt.close(fig)

# ---------------------------------------------------------------- Case studies: forecast fans on real Florida storms
def case(sid, label, start_t, ax):
    g = df[(df.sid == sid)].sort_values("t")
    g = g[g.t.dt.hour.isin([0,6,12,18])]
    s = S[(S.sid == sid) & (S.t == np.datetime64(start_t))]
    if s.empty: print("no sample for", label, start_t); return
    s = s.iloc[0]
    coast(ax, 15, 37, -98, -65, step=0.06)
    ax.plot(g.lon, g.lat, color="black", lw=2, label="Actual track (HURDAT2)", zorder=5)
    ax.scatter(g.lon[::4], g.lat[::4], color="black", s=8, zorder=6)
    fl_lon, fl_lat = [s.lon], [s.lat]; pl_lon, pl_lat = [s.lon], [s.lat]
    for h in HORIZONS:
        p = models[h].predict(pd.DataFrame([s[FEATS]]))[0]
        fl_lon.append(s.lon + p[1]); fl_lat.append(s.lat + p[0])
        k = h/12; pl_lon.append(s.lon + k*s.u12); pl_lat.append(s.lat + k*s.v12)
    ax.plot(pl_lon, pl_lat, "s--", color="#7570b3", lw=1.5, ms=5, label="Persistence (straight line)", zorder=7)
    ax.plot(fl_lon, fl_lat, "o-", color="#d95f02", lw=2.2, ms=6, label="Our model: 12/24/48/72 h", zorder=8)
    ax.plot(s.lon, s.lat, marker="*", color="gold", mec="k", ms=16, zorder=9, label=f"Forecast issued {pd.Timestamp(start_t):%b %d %HZ}")
    for h, x, y in zip(HORIZONS, fl_lon[1:], fl_lat[1:]):
        ax.annotate(f"{h}h", (x, y), xytext=(4, 4), textcoords="offset points", fontsize=8, color="#d95f02")
    # actual position at 72h
    t72 = np.datetime64(start_t) + np.timedelta64(72, "h"); a = g[g.t == t72]
    if not a.empty:
        e = gc_nmi(a.lat.iloc[0], a.lon.iloc[0], fl_lat[-1], fl_lon[-1]); ep = gc_nmi(a.lat.iloc[0], a.lon.iloc[0], pl_lat[-1], pl_lon[-1])
        ax.set_title(f"{label}\n72-h error: our model {e:.0f} n mi, persistence {ep:.0f} n mi", fontsize=11)
    else: ax.set_title(label, fontsize=11)
    ax.legend(fontsize=7.5, loc="lower left")

cases = [("AL112017", "Hurricane Irma, 2017", "2017-09-07T12:00"),
         ("AL092022", "Hurricane Ian, 2022", "2022-09-25T12:00"),
         ("AL142024", "Hurricane Milton, 2024", "2024-10-07T00:00"),
         ("AL041992", "Hurricane Andrew, 1992 (in training data)", "1992-08-21T12:00")]
fig, axes = plt.subplots(2, 2, figsize=(15, 11), dpi=150)
for (sid, lab, st), ax in zip(cases, axes.ravel()):
    print(lab, "name check:", df[df.sid == sid].name.iloc[0])
    case(sid, lab, st, ax)
fig.suptitle("Our statistics-only model vs what really happened, 3 days out", fontsize=14)
fig.tight_layout(); fig.savefig(OUT+"case_studies_irma_ian_milton_andrew.png"); plt.close(fig)
print("done")
