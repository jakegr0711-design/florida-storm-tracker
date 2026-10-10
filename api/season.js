// Vercel serverless function: GET /api/season
// Current Atlantic season totals from NHC best-track files, plus NOAA's current El Nino/La Nina status.
// Cached at Vercel's edge for an hour, so NOAA is asked at most about once an hour.

async function getText(url, ms) {
  const ctl = new AbortController(), t = setTimeout(() => ctl.abort(), ms);
  try { const r = await fetch(url, { signal: ctl.signal, headers: { "User-Agent": "florida-storm-tracker (student project)" } }); if (!r.ok) throw new Error("HTTP " + r.status); return await r.text(); }
  finally { clearTimeout(t); }
}
const decode = s => s.replace(/<[^>]+>/g, " ").replace(/&ntilde;/g, "ñ").replace(/&#37;/g, "%").replace(/&nbsp;/g, " ").replace(/&amp;/g, "&").replace(/&#39;/g, "'").replace(/&quot;/g, '"').replace(/\s+/g, " ").trim();

async function season(year) {
  const listing = await getText("https://ftp.nhc.noaa.gov/atcf/btk/", 8000);
  const nums = [...new Set([...listing.matchAll(new RegExp(`bal(\\d{2})${year}\\.dat`, "g"))].map(m => m[1]))].filter(n => +n < 50).sort();
  const storms = await Promise.all(nums.map(async n => {
    try {
      const rows = (await getText(`https://ftp.nhc.noaa.gov/atcf/btk/bal${n}${year}.dat`, 8000)).split("\n").map(l => l.split(",").map(x => x.trim())).filter(p => p.length > 10 && p[4] === "BEST");
      let maxKt = 0, named = false, hurricane = false, major = false, name = "";
      for (const p of rows) {
        const kt = +p[8] || 0, st = p[10];
        if (kt > maxKt) maxKt = kt;
        if (["TS", "HU", "SS"].includes(st)) { named = true; if (p[27]) name = p[27]; }
        if (st === "HU") { hurricane = true; if (kt >= 96) major = true; }
      }
      if (!name) name = (rows.length && rows[rows.length - 1][27]) || `Storm ${+n}`;
      return { number: +n, name: name.charAt(0) + name.slice(1).toLowerCase(), maxKt, named, hurricane, major };
    } catch (e) { return null; }
  }));
  const ok = storms.filter(Boolean);
  return { year, named: ok.filter(s => s.named).length, hurricanes: ok.filter(s => s.hurricane).length, majors: ok.filter(s => s.major).length,
    storms: ok.filter(s => s.named).map(({ number, name, maxKt, hurricane, major }) => ({ number, name, maxKt, hurricane, major })), complete: ok.length === storms.length };
}

async function enso() {
  const html = await getText("https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.shtml", 8000);
  const status = (html.match(/ENSO Alert System Status:([\s\S]{0,800}?)<\/strong>/i) || [])[1];
  const synopsis = (html.match(/Synopsis:([\s\S]{0,1200}?)<\/strong>/i) || [])[1];
  const issued = (html.match(/\b\d{1,2} (?:January|February|March|April|May|June|July|August|September|October|November|December) 20\d{2}\b/) || [])[0];
  return { status: status ? decode(status) : null, synopsis: synopsis ? decode(synopsis) : null, issued: issued || null };
}

module.exports = async function handler(req, res) {
  const year = new Date().getUTCFullYear();
  const [s, e] = await Promise.allSettled([season(year), enso()]);
  const body = { updated: new Date().toISOString(), season: s.status === "fulfilled" ? s.value : null, enso: e.status === "fulfilled" ? e.value : null };
  res.setHeader("Cache-Control", body.season && body.enso ? "public, s-maxage=3600, stale-while-revalidate=86400" : "public, s-maxage=300");
  res.status(200).json(body);
};
