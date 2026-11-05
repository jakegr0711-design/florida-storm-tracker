// Vercel serverless function: POST /api/feedback
// Visitors rate an assistant answer ("helpful" or "problem"). Each rating is written to the
// project's Vercel runtime logs as one line starting with FEEDBACK, so the team can review
// flagged answers (Vercel dashboard > Logs, search "FEEDBACK"). Nothing is stored elsewhere.

const hits = new Map();
const clip = (v, n) => (typeof v === "string" ? v.replace(/\s+/g, " ").trim().slice(0, n) : "");

module.exports = async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  if (req.method !== "POST") return res.status(405).json({ error: "Use POST." });
  const origin = req.headers.origin || "", host = req.headers["x-forwarded-host"] || req.headers.host || "";
  let originHost = ""; try { originHost = new URL(origin).host; } catch (e) {}
  if (!originHost || originHost !== host) return res.status(403).json({ error: "Requests are only accepted from this website." });

  const ip = String(req.headers["x-forwarded-for"] || "unknown").split(",")[0].trim(), now = Date.now();
  const recent = (hits.get(ip) || []).filter(t => now - t < 3600e3);
  if (recent.length >= 30) return res.status(429).json({ error: "Too many ratings. Try again later." });
  recent.push(now); hits.set(ip, recent); if (hits.size > 5000) hits.clear();

  let b = req.body; if (typeof b === "string") { try { b = JSON.parse(b); } catch (e) { b = null; } }
  if (!b || (b.rating !== "helpful" && b.rating !== "problem")) return res.status(400).json({ error: "Missing rating." });
  console.log("FEEDBACK " + JSON.stringify({
    at: new Date().toISOString(), rating: b.rating, reason: clip(b.reason, 60),
    question: clip(b.question, 600), answer: clip(b.answer, 1500), basis: clip(b.basis, 200), profile: clip(b.profile, 200),
  }));
  return res.status(200).json({ ok: true });
};
