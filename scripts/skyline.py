#!/usr/bin/env python3
"""Render a 3D "skyline" of a GitHub user's contribution calendar (last 12 months)
as two animated SVG cards, light and dark, styled like GitHub itself.

Runs daily in GitHub Actions with the standard library only:
    GITHUB_TOKEN=... python scripts/skyline.py --user AnkushBL6 --out dist
Local preview without network:
    python scripts/skyline.py --sample --out dist
"""
import argparse
import datetime as dt
import html
import json
import math
import os
import pathlib
import random
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
FONTS_CSS = (HERE / "skyline_fonts.css").read_text()

PALETTES = {
    "dark": dict(BG="#0d1117", PANEL="#151b23", LINE="#30363d", LINE2="#3d444d", TEXT="#f0f6fc", MUTED="#9198a1",
                 DIM="#656c76", GREEN="#3fb950",
                 LEVELS=["#1c232c", "#033a16", "#196c2e", "#2ea043", "#56d364"]),
    "light": dict(BG="#ffffff", PANEL="#f6f8fa", LINE="#d1d9e0", LINE2="#c8d1da", TEXT="#1f2328", MUTED="#59636e",
                  DIM="#818b98", GREEN="#1a7f37",
                  LEVELS=["#eff2f5", "#aceebb", "#4ac26b", "#2da44e", "#116329"]),
}
LEVEL = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}
FONT = {
    "sans": "'gSans','Mona Sans',-apple-system,'Segoe UI',Helvetica,Arial,sans-serif",
    "display": "'gDisplay','gSans','Mona Sans',-apple-system,'Segoe UI',Helvetica,Arial,sans-serif",
    "mono": "'gMono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace",
}
QUERY = """query($login:String!){user(login:$login){contributionsCollection{contributionCalendar{
  totalContributions weeks{contributionDays{date contributionCount contributionLevel}}}}}}"""


# ------------------------------------------------------------------ data
def fetch(user, token):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": user}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json",
                 "User-Agent": "profile-skyline"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = json.load(r)
    if body.get("errors"):
        raise SystemExit(f"GraphQL error: {body['errors']}")
    cal = body["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    weeks = [[(d["date"], d["contributionCount"], LEVEL[d["contributionLevel"]]) for d in w["contributionDays"]]
             for w in cal["weeks"]]
    return cal["totalContributions"], weeks


def sample():
    rnd = random.Random(42)
    today = dt.date(2026, 11, 14)
    start = today - dt.timedelta(days=today.isoweekday() % 7 + 52 * 7)
    weeks, cur, week = [], start, []
    while cur <= today:
        busy = 0.55 + 0.45 * math.sin(cur.toordinal() / 23)
        n = 0 if rnd.random() < 0.28 else int(rnd.expovariate(1 / (6 * busy + 1)))
        week.append((cur.isoformat(), n, 0))
        if len(week) == 7:
            weeks.append(week)
            week = []
        cur += dt.timedelta(days=1)
    if week:
        weeks.append(week)
    mx = max(c for w in weeks for _, c, _ in w) or 1
    weeks = [[(d, c, 0 if c == 0 else min(4, 1 + int(4 * c / (mx + 1)))) for d, c, _ in w] for w in weeks]
    return sum(c for w in weeks for _, c, _ in w), weeks


def stats(weeks):
    days = [d for w in weeks for d in w]
    longest = run = 0
    for _, c, _ in days:
        run = run + 1 if c > 0 else 0
        longest = max(longest, run)
    current = 0
    tail = days[:-1] if days and days[-1][1] == 0 else days  # today may still be empty
    for _, c, _ in reversed(tail):
        if c == 0:
            break
        current += 1
    best = max(days, key=lambda d: d[1]) if days else ("", 0, 0)
    by_wd = [0] * 7
    for d, c, _ in days:
        by_wd[dt.date.fromisoformat(d).weekday()] += c
    wd = ["Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays", "Sundays"][by_wd.index(max(by_wd))]
    return longest, current, best, wd


# ------------------------------------------------------------------ drawing
def shade(hex_, k):
    r, g, b = (int(hex_[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(v * k))) for v in (r, g, b))


def esc(s):
    return html.escape(s, quote=True)


def text(x, y, s, fam, wt, size, fill, anchor="start", extra=""):
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    return (f'<text xml:space="preserve" x="{x:g}" y="{y:g}" font-family="{FONT[fam]}" font-weight="{wt}" '
            f'font-size="{size:g}" fill="{fill}"{a} {extra}>{esc(s)}</text>')


def render(total, weeks, mode, updated):
    P = PALETTES[mode]
    Wd, H = 840, 312
    ux, uy, vx, vy = 10.2, 2.35, -5.6, 4.5
    ox, oy, g = 268, 128, 0.12
    mx = max([c for w in weeks for _, c, _ in w] + [1])

    def pt(a, b, h=0.0):
        return ox + a * ux + b * vx, oy + a * uy + b * vy - h

    def poly(points, fill):
        return '<polygon points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in points) + f'" fill="{fill}"/>'

    cells = []
    for wi, wk in enumerate(weeks):
        for date, c, lv in wk:
            di = (dt.date.fromisoformat(date).isoweekday() % 7)  # Sunday = 0, like GitHub
            cells.append((wi, di, date, c, lv))
    cells.sort(key=lambda q: (q[0] * uy + q[1] * vy, q[0]))

    body, css = [], []
    css.append("@keyframes rise{from{transform:scaleY(0)}to{transform:scaleY(1)}}"
               "@keyframes fadein{from{opacity:0}to{opacity:1}}"
               "text{white-space:pre;font-variant-ligatures:none}"
               "@media (prefers-reduced-motion: reduce){*{animation:none!important}}")
    last_date = max(c[2] for c in cells) if cells else ""
    today_pt = None
    for wi, di, date, c, lv in cells:
        w0, w1, d0, d1 = wi + g, wi + 1 - g, di + g, di + 1 - g
        A, B, Cc, D = pt(w0, d0), pt(w1, d0), pt(w1, d1), pt(w0, d1)
        col = P["LEVELS"][lv]
        if c == 0:
            body.append(poly([A, B, Cc, D], col))
            continue
        h = 4 + 50 * (c / mx) ** 0.55
        up = lambda p: (p[0], p[1] - h)
        left = poly([D, Cc, up(Cc), up(D)], shade(col, 0.72))
        right = poly([B, Cc, up(Cc), up(B)], shade(col, 0.86))
        top = poly([up(A), up(B), up(Cc), up(D)], col)
        delay = 0.15 + wi * 0.018 + di * 0.02
        body.append(f'<g style="transform-origin:{Cc[0]:.1f}px {Cc[1]:.1f}px;'
                    f'animation:rise .9s cubic-bezier(.2,.8,.2,1) {delay:.2f}s both">{left}{right}{top}</g>')
        if date == last_date:
            today_pt = ((up(A)[0] + up(Cc)[0]) / 2, (up(A)[1] + up(Cc)[1]) / 2)

    # month labels along the front edge
    seen = set()
    for wi, wk in enumerate(weeks):
        d0 = dt.date.fromisoformat(wk[0][0])
        if d0.day <= 7 and (d0.year, d0.month) not in seen and 0 < wi < len(weeks) - 1:
            seen.add((d0.year, d0.month))
            x, y = pt(wi + 0.5, 7.6)
            body.append(text(x, y + 9, d0.strftime("%b"), "sans", 400, 9.5, P["DIM"], "middle"))
    if today_pt:
        x, y = today_pt
        body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{P["GREEN"]}"/>'
                    f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" stroke="{P["GREEN"]}" fill="none">'
                    f'<animate attributeName="r" values="3;12" dur="1.8s" repeatCount="indefinite"/>'
                    f'<animate attributeName="opacity" values=".8;0" dur="1.8s" repeatCount="indefinite"/></circle>')

    longest, current, best, wd = stats(weeks)
    # left column: total with a count-up, then stats
    frames, steps = [], 14
    num = []
    for k in range(steps + 1):
        v = round(total * (1 - (1 - k / steps) ** 3))
        num.append(f"{v:,}")
    kts = ";".join(f"{k / steps * 0.6:.3f}" for k in range(steps + 1)) + ";1"
    for k, s_ in enumerate(num):
        vals = ";".join("1" if j == k else "0" for j in range(steps + 1)) + (";1" if k == steps else ";0")
        frames.append(f'<g opacity="{1 if k == steps else 0}"><animate attributeName="opacity" calcMode="discrete" '
                      f'dur="2s" fill="freeze" keyTimes="{kts}" values="{vals}"/>'
                      + text(28, 104, s_, "display", 900, 34, P["TEXT"]) + "</g>")
    left = frames + [text(28, 126, "contributions in the last year", "sans", 400, 13, P["MUTED"])]
    rows = [("Longest streak", f"{longest} day{'s' if longest != 1 else ''}"),
            ("Current streak", f"{current} day{'s' if current != 1 else ''}"),
            ("Busiest day", f"{dt.date.fromisoformat(best[0]).strftime('%b %d').replace(' 0', ' ')} · {best[1]}"
             if best[0] else "—"),
            ("Most active on", wd)]
    for k, (lab, val) in enumerate(rows):
        y = 166 + k * 30
        left.append(f'<line x1="28" y1="{y - 18}" x2="196" y2="{y - 18}" stroke="{P["LINE"]}"/>')
        left.append(text(28, y, lab, "sans", 400, 12, P["MUTED"]))
        left.append(text(196, y, val, "sans", 600, 12.5, P["TEXT"], "end"))

    # legend
    lx, ly = 776, 58
    leg = [text(lx - 5 * 14 - 8, ly + 9, "Less", "sans", 400, 10.5, P["DIM"], "end")]
    for k in range(5):
        leg.append(f'<rect x="{lx - (5 - k) * 14:.0f}" y="{ly}" width="10" height="10" rx="2" fill="{P["LEVELS"][k]}"/>')
    leg.append(text(lx + 4, ly + 9, "More", "sans", 400, 10.5, P["DIM"]))

    strip = (f'<path d="M0.5 40 V12.5 A12 12 0 0 1 12.5 0.5 H{Wd-12.5} A12 12 0 0 1 {Wd-0.5} 12.5 V40 Z" fill="{P["PANEL"]}"/>'
             f'<line x1="0.5" y1="40" x2="{Wd-0.5}" y2="40" stroke="{P["LINE"]}"/>'
             + "".join(f'<rect x="{17 + c*5}" y="{13 + r*5}" width="4" height="4" rx="1" fill="{P["MUTED"]}" opacity="{o}"/>'
                       for r in range(3) for c, o in enumerate([.35, .65, 1] if r % 2 else [1, .5, .8]))
             + text(40, 25, "contributions", "mono", 500, 12.5, P["TEXT"])
             + text(Wd - 18, 25, f"last 12 months · updated {updated}", "mono", 500, 11.5, P["DIM"], "end"))
    desc = (f"{total} contributions in the last year, drawn as a 3D skyline. Longest streak {longest} days, "
            f"current streak {current} days, most active on {wd}.")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{Wd}" height="{H}" viewBox="0 0 {Wd} {H}" fill="none" '
            f'role="img" aria-labelledby="t d"><title id="t">Contributions</title><desc id="d">{esc(desc)}</desc>'
            f'<style>{FONTS_CSS}{"".join(css)}</style>'
            f'<rect x="0.5" y="0.5" width="{Wd-1}" height="{H-1}" rx="12" fill="{P["BG"]}" stroke="{P["LINE"]}"/>'
            + strip + f'<rect x="0.5" y="0.5" width="{Wd-1}" height="{H-1}" rx="12" fill="none" stroke="{P["LINE"]}"/>'
            + "".join(left) + "".join(body) + "".join(leg) + "</svg>\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user")
    ap.add_argument("--out", default="dist")
    ap.add_argument("--sample", action="store_true", help="render made-up data (no network)")
    a = ap.parse_args()
    if a.sample:
        total, weeks = sample()
        updated = "sample data"
    else:
        token = os.environ.get("GITHUB_TOKEN")
        if not (a.user and token):
            raise SystemExit("--user and GITHUB_TOKEN are required (or use --sample)")
        total, weeks = fetch(a.user, token)
        updated = dt.date.today().isoformat()
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for mode in ("dark", "light"):
        (out / f"skyline-{mode}.svg").write_text(render(total, weeks, mode, updated))
    print(f"wrote skyline-dark.svg and skyline-light.svg to {out} ({total} contributions)")


if __name__ == "__main__":
    main()
