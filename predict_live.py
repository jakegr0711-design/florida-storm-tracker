"""
Run our CLIPER-style model on a storm that is active right now, and compare it with
the National Hurricane Center's official forecast for the same moment.

    python predict_live.py                 # every active Atlantic storm (reads nhc.noaa.gov)
    python predict_live.py al092026        # one storm by NHC id
    python predict_live.py --bdeck FILE [--adeck FILE]   # offline: use saved NHC files

Data comes from NHC's public ATCF files:
  best track (where the storm has been):  https://ftp.nhc.noaa.gov/atcf/btk/bal092026.dat
  forecasts (incl. NHC official "OFCL"):  https://ftp.nhc.noaa.gov/atcf/aid_public/aal092026.dat.gz

THIS IS A CLASS EXERCISE, NOT A FORECAST. Our model averages about 384 nautical miles of error
at 72 hours; NHC averaged 67 in 2024. For any real decision use https://www.nhc.noaa.gov
"""
import sys, json, gzip, io, math, datetime as dt, urllib.request, os

HERE = os.path.dirname(os.path.abspath(__file__))
M = json.load(open(os.path.join(HERE, "model_params.json")))
HORIZONS = [12, 24, 48, 72]


def get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        data = r.read()
    return gzip.decompress(data).decode() if url.endswith(".gz") else data.decode()


def latlon(lat, lon):
    lat, lon = lat.strip(), lon.strip()
    la = int(lat[:-1]) / 10 * (1 if lat[-1] == "N" else -1)
    lo = int(lon[:-1]) / 10 * (-1 if lon[-1] == "W" else 1)
    return la, lo


def parse_bdeck(text):
    """One fix per synoptic time (b-decks repeat each time for 34/50/64-kt wind radii)."""
    fixes = {}
    for line in text.splitlines():
        p = [x.strip() for x in line.split(",")]
        if len(p) < 9 or p[4] != "BEST":
            continue
        t = dt.datetime.strptime(p[2], "%Y%m%d%H")
        if t.hour % 6:
            continue
        la, lo = latlon(p[6], p[7])
        fixes.setdefault(t, (la, lo, int(p[8])))
    return dict(sorted(fixes.items()))


def parse_ofcl(text, cycle):
    out = {}
    for line in text.splitlines():
        p = [x.strip() for x in line.split(",")]
        if len(p) < 9 or p[4] != "OFCL" or p[2] != cycle.strftime("%Y%m%d%H"):
            continue
        tau = int(p[5])
        out.setdefault(tau, latlon(p[6], p[7]) + (int(p[8]),))
    return out


def predict(h, x):
    """Exact re-implementation of StandardScaler -> PolynomialFeatures(2) -> Ridge."""
    P = M["params"][str(h)]
    z = [(v - m) / s for v, m, s in zip(x, P["mean"], P["scale"])]
    f = [math.prod(zi ** e for zi, e in zip(z, pw)) for pw in P["powers"]]
    return [b + sum(c * fj for c, fj in zip(row, f)) for b, row in zip(P["intercept"], P["coef"])]


def nmi(a, b, c, d):
    r = math.pi / 180
    s = math.sin((c - a) * r / 2) ** 2 + math.cos(a * r) * math.cos(c * r) * math.sin((d - b) * r / 2) ** 2
    return 2 * math.asin(math.sqrt(min(1, s))) * 3440.065


def forecast(fixes):
    times = list(fixes)
    t0 = times[-1]
    need = [t0 - dt.timedelta(hours=6), t0 - dt.timedelta(hours=12)]
    if any(t not in fixes for t in need):
        raise SystemExit("Need positions 6 and 12 hours before the latest fix; the storm is too new. Try again later.")
    (la, lo, w), (la6, lo6, _), (la12, lo12, _) = fixes[t0], fixes[need[0]], fixes[need[1]]
    doy = t0.timetuple().tm_yday
    x = [la, lo, w, lo - lo12, la - la12, lo - lo6, la - la6,
         math.sin(2 * math.pi * doy / 365.25), math.cos(2 * math.pi * doy / 365.25)]
    fc = {}
    for h in HORIZONS:
        dlat, dlon = predict(h, x)
        fc[h] = (la + dlat, lo + dlon)
    return t0, (la, lo, w), fc


def report(name, bdeck_text, adeck_text=None, png=None):
    fixes = parse_bdeck(bdeck_text)
    t0, (la, lo, w), fc = forecast(fixes)
    ofcl = parse_ofcl(adeck_text, t0) if adeck_text else {}
    print(f"\n{name}: latest NHC best-track fix {t0:%Y-%m-%d %H}Z  {la:.1f}N {abs(lo):.1f}W  {w} kt")
    print("CLASS EXERCISE ONLY. Use the National Hurricane Center for real decisions.\n")
    print(f"{'Lead':>5}  {'Our model':>16}  {'NHC official':>16}  {'Gap (n mi)':>10}")
    for h in HORIZONS:
        a, b = fc[h]
        o = ofcl.get(h)
        oc = f"{o[0]:.1f}N {abs(o[1]):.1f}W" if o else "n/a"
        gap = f"{nmi(a, b, o[0], o[1]):.0f}" if o else "-"
        print(f"{h:>4}h  {a:>5.1f}N {abs(b):>5.1f}W   {oc:>16}  {gap:>10}")
    print("\nCheck back after each lead time: compare both columns with where the storm actually went.")
    if png:
        draw(name, fixes, t0, fc, ofcl, png)
        print(f"Map saved: {png}")


def draw(name, fixes, t0, fc, ofcl, png):
    try:
        import numpy as np, matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from global_land_mask import globe
    except ImportError:
        print("(pip install numpy matplotlib global-land-mask for a map)"); return
    lats = [v[0] for v in fixes.values()] + [p[0] for p in fc.values()]
    lons = [v[1] for v in fixes.values()] + [p[1] for p in fc.values()]
    lat0, lat1 = min(lats) - 4, max(lats) + 4
    lon0, lon1 = min(lons) - 5, max(lons) + 5
    LON, LAT = np.meshgrid(np.arange(lon0, lon1, 0.04), np.arange(lat0, lat1, 0.04))
    land = globe.is_land(LAT, LON)
    fig, ax = plt.subplots(figsize=(9, 8), dpi=140)
    ax.set_facecolor("#dbe9f4")
    ax.contourf(LON, LAT, land, levels=[0.5, 1.5], colors=["#e8e4d8"])
    ax.contour(LON, LAT, land, levels=[0.5], colors="#6b6b6b", linewidths=0.6)
    ax.plot([v[1] for v in fixes.values()], [v[0] for v in fixes.values()], "k.-", lw=2, label="Where it has been (NHC best track)")
    la, lo, _ = fixes[t0]
    ax.plot([lo] + [fc[h][1] for h in HORIZONS], [la] + [fc[h][0] for h in HORIZONS], "o-", color="#d95f02", lw=2.2, label="Our model (class exercise)")
    if ofcl:
        ks = sorted(k for k in ofcl if k <= 72)
        ax.plot([ofcl[k][1] for k in ks], [ofcl[k][0] for k in ks], "D-", color="black", lw=1.5, mfc="white", label="NHC official forecast")
    for h in HORIZONS:
        ax.annotate(f"{h}h", (fc[h][1], fc[h][0]), xytext=(5, 4), textcoords="offset points", fontsize=8, color="#d95f02")
    ax.set_xlim(lon0, lon1); ax.set_ylim(lat0, lat1); ax.set_aspect(1 / math.cos(math.radians((lat0 + lat1) / 2)))
    ax.set_title(f"{name}: forecast from {t0:%b %d %H}Z\nNOT AN OFFICIAL FORECAST. See nhc.noaa.gov", fontsize=11)
    ax.legend(loc="lower left", fontsize=8); ax.grid(alpha=0.25)
    fig.tight_layout(); fig.savefig(png); plt.close(fig)


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--bdeck" in args:
        b = open(args[args.index("--bdeck") + 1]).read()
        a = open(args[args.index("--adeck") + 1]).read() if "--adeck" in args else None
        report(os.path.basename(args[args.index("--bdeck") + 1]), b, a, png="live_forecast.png")
        sys.exit()
    if args:
        ids = [(args[0].lower(), args[0].upper())]
    else:
        cur = json.loads(get("https://www.nhc.noaa.gov/CurrentStorms.json"))["activeStorms"]
        ids = [(s["id"], s["name"]) for s in cur if s["id"].startswith("al")]
        if not ids:
            sys.exit("No active Atlantic storms right now.")
    for sid, name in ids:
        b = get(f"https://ftp.nhc.noaa.gov/atcf/btk/b{sid}.dat")
        try:
            a = get(f"https://ftp.nhc.noaa.gov/atcf/aid_public/a{sid}.dat.gz")
        except Exception:
            a = None
        report(f"{name} ({sid})", b, a, png=f"live_{sid}.png")
