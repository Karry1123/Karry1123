"""Generate profile cards (rated stats, top languages, streak) as SVG.

The rank uses the same formula as github-readme-stats (MIT licensed):
weighted CDFs of commits, PRs, issues, reviews, stars and followers.
"""
import json, math, os, sys, urllib.request
from datetime import date, datetime, timedelta, timezone
from html import escape

USER = os.environ.get("GH_USER", "Karry1123")
TOKEN = os.environ["GH_TOKEN"]
OUT = sys.argv[1] if len(sys.argv) > 1 else "assets"

BG, BORDER, GOLD, TEXT, MUTED, TRACK = "#0f172a", "#1e3a5f", "#c7a555", "#e2e8f0", "#94a3b8", "#243049"
FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', sans-serif"

Q = """query($login:String!,$after:String,$prAfter:String){
  user(login:$login){
    followers{ totalCount }
    issues{ totalCount }
    contributionsCollection{ totalCommitContributions restrictedContributionsCount
      totalPullRequestReviewContributions }
    repositoriesContributedTo(first:1, contributionTypes:[COMMIT,PULL_REQUEST,ISSUE,REPOSITORY]){ totalCount }
    pullRequests(first:100, after:$prAfter){
      pageInfo{ hasNextPage endCursor }
      nodes{ state repository{ nameWithOwner isPrivate stargazerCount owner{ login } } } }
    repositories(first:100, after:$after, ownerAffiliations:OWNER, isFork:false, privacy:PUBLIC){
      pageInfo{ hasNextPage endCursor }
      nodes{ stargazerCount
        languages(first:10, orderBy:{field:SIZE, direction:DESC}){
          edges{ size node{ name color } } } } } } }"""


def post(query, variables):
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request("https://api.github.com/graphql", body,
                                 {"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"})
    data = json.load(urllib.request.urlopen(req))
    if "errors" in data:
        raise SystemExit(data["errors"])
    return data["data"]["user"]


def gql(after=None, pr_after=None):
    return post(Q, {"login": USER, "after": after, "prAfter": pr_after})


u = gql()
repos, prs = list(u["repositories"]["nodes"]), list(u["pullRequests"]["nodes"])
rp, pp = u["repositories"]["pageInfo"], u["pullRequests"]["pageInfo"]
while rp["hasNextPage"] or pp["hasNextPage"]:
    nxt = gql(rp["endCursor"] if rp["hasNextPage"] else None,
              pp["endCursor"] if pp["hasNextPage"] else None)
    if rp["hasNextPage"]:
        repos += nxt["repositories"]["nodes"]
        rp = nxt["repositories"]["pageInfo"]
    if pp["hasNextPage"]:
        prs += nxt["pullRequests"]["nodes"]
        pp = nxt["pullRequests"]["pageInfo"]

cc = u["contributionsCollection"]
public_prs = [p for p in prs if not p["repository"]["isPrivate"]]
s = {
    "stars": sum(r["stargazerCount"] for r in repos),
    "commits": cc["totalCommitContributions"] + cc["restrictedContributionsCount"],
    "prs": len(public_prs),
    "merged": sum(p["state"] == "MERGED" for p in public_prs),
    "reviews": cc["totalPullRequestReviewContributions"],
    "issues": u["issues"]["totalCount"],
    "contrib": u["repositoriesContributedTo"]["totalCount"],
    "followers": u["followers"]["totalCount"],
}


# ---- rank (github-readme-stats formula) ----
def exp_cdf(x):
    return 1 - 2 ** -x


def lognorm_cdf(x):
    return x / (1 + x)


W = dict(commits=2, prs=3, issues=1, reviews=1, stars=4, followers=1)
score = (W["commits"] * exp_cdf(s["commits"] / 250) + W["prs"] * exp_cdf(s["prs"] / 50)
         + W["issues"] * exp_cdf(s["issues"] / 25) + W["reviews"] * exp_cdf(s["reviews"] / 2)
         + W["stars"] * lognorm_cdf(s["stars"] / 50) + W["followers"] * lognorm_cdf(s["followers"] / 10))
percentile = 100 * (1 - score / sum(W.values()))
LEVELS = ["S", "A+", "A", "A-", "B+", "B", "B-", "C+", "C"]
THRESH = [1, 12.5, 25, 37.5, 50, 62.5, 75, 87.5, 100]
level = LEVELS[next(i for i, t in enumerate(THRESH) if percentile <= t)]


def frame(w, h, title, inner):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="8" fill="{BG}" stroke="{BORDER}"/>'
            f'<text x="24" y="36" fill="{GOLD}" font-family="{FONT}" font-size="17" font-weight="600">{escape(title)}</text>'
            f'{inner}</svg>')


def txt(x, y, t, fill=TEXT, size=14, weight=400, anchor="start"):
    return (f'<text x="{x}" y="{y}" fill="{fill}" font-family="{FONT}" font-size="{size}" '
            f'font-weight="{weight}" text-anchor="{anchor}">{escape(str(t))}</text>')


# ---- rated stats card ----
rows_data = [
    ("Total stars earned", s["stars"]),
    ("Commits (last year)", s["commits"]),
    ("Pull requests", s["prs"]),
    ("Merged pull requests", s["merged"]),
    ("Issues", s["issues"]),
    ("Contributed to (last year)", s["contrib"]),
]
rows = ""
for i, (k, v) in enumerate(rows_data):
    y = 66 + i * 23
    rows += f'<circle cx="30" cy="{y-5}" r="3" fill="{GOLD}"/>' + txt(44, y, k) + txt(270, y, v, weight=600, anchor="end")
R, cx, cy = 42, 372, 106
circ = 2 * math.pi * R
fill_len = circ * (100 - percentile) / 100
ring = (f'<circle cx="{cx}" cy="{cy}" r="{R}" fill="none" stroke="{TRACK}" stroke-width="7"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{R}" fill="none" stroke="{GOLD}" stroke-width="7" stroke-linecap="round" '
        f'stroke-dasharray="{fill_len:.1f} {circ:.1f}" transform="rotate(-90 {cx} {cy})"/>'
        + txt(cx, cy + 9, level, fill=TEXT, size=26, weight=700, anchor="middle")
        + txt(cx, cy + R + 24, f"Top {percentile:.1f}%", fill=MUTED, size=12, anchor="middle"))
stats_svg = frame(450, 200, "Karry's GitHub Stats", rows + ring)

# ---- top languages ----
langs = {}
for r in repos:
    for e in r["languages"]["edges"]:
        n = e["node"]["name"]
        size = langs.get(n, (0, None))[0]
        langs[n] = (size + e["size"], e["node"]["color"] or "#888888")
top = sorted(langs.items(), key=lambda kv: -kv[1][0])[:6]
total = sum(v for _, (v, _) in top) or 1
bar, x, BW = "", 24.0, 302.0
for name, (v, color) in top:
    w = BW * v / total
    bar += f'<rect x="{x:.2f}" y="54" width="{w:.2f}" height="8" fill="{color}"/>'
    x += w
bar = (f'<clipPath id="c"><rect x="24" y="54" width="{BW}" height="8" rx="4"/></clipPath>'
       f'<g clip-path="url(#c)">{bar}</g>')
legend = ""
for i, (name, (v, color)) in enumerate(top):
    lx, ly = 24 + (i % 2) * 155, 94 + (i // 2) * 34
    legend += (f'<circle cx="{lx+5}" cy="{ly-4}" r="5" fill="{color}"/>'
               f'<text x="{lx+16}" y="{ly}" fill="{TEXT}" font-family="{FONT}" font-size="13">'
               f'{escape(name)} <tspan fill="{MUTED}">{100*v/total:.1f}%</tspan></text>')
langs_svg = frame(350, 200, "Most Used Languages", bar + legend)

# ---- contribution streak ----
Q_YEARS = "query($login:String!){ user(login:$login){ contributionsCollection{ contributionYears } } }"
Q_CAL = """query($login:String!,$from:DateTime!,$to:DateTime!){ user(login:$login){
  contributionsCollection(from:$from, to:$to){ contributionCalendar{
    weeks{ contributionDays{ date contributionCount } } } } } }"""

now = datetime.now(timezone.utc)
counts = {}
for year in post(Q_YEARS, {"login": USER})["contributionsCollection"]["contributionYears"]:
    end = min(datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc), now)
    cal = post(Q_CAL, {"login": USER, "from": f"{year}-01-01T00:00:00Z",
                       "to": end.strftime("%Y-%m-%dT%H:%M:%SZ")})
    for week in cal["contributionsCollection"]["contributionCalendar"]["weeks"]:
        for d in week["contributionDays"]:
            counts[date.fromisoformat(d["date"])] = d["contributionCount"]

days = sorted(counts)
total_contrib = sum(counts.values())
first_active = next((d for d in days if counts[d]), None)

longest, longest_end, run = 0, None, 0
for d in days:
    run = run + 1 if counts[d] else 0
    if run > longest:
        longest, longest_end = run, d

# A day without contributions yet today does not break the current streak.
current, cur = 0, days[-1] if days else None
if cur is not None and not counts[cur]:
    cur -= timedelta(days=1)
current_end = cur
while cur is not None and counts.get(cur, 0):
    current += 1
    cur -= timedelta(days=1)


def fmt_day(d):
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def fmt_range(n, end):
    if not n:
        return "No active streak"
    start = end - timedelta(days=n - 1)
    return fmt_day(end) if n == 1 else f"{fmt_day(start)} - {fmt_day(end)}"


SW, SH = 724, 150
cols = [SW / 6, SW / 2, SW * 5 / 6]
R2, ry = 36, 64
circ2 = 2 * math.pi * R2
ratio = current / longest if longest else 0
streak_inner = (
    f'<rect x="0.5" y="0.5" width="{SW-1}" height="{SH-1}" rx="8" fill="{BG}" stroke="{BORDER}"/>'
    f'<line x1="{SW/3:.1f}" y1="24" x2="{SW/3:.1f}" y2="{SH-24}" stroke="{BORDER}"/>'
    f'<line x1="{SW*2/3:.1f}" y1="24" x2="{SW*2/3:.1f}" y2="{SH-24}" stroke="{BORDER}"/>'
    + txt(cols[0], 62, total_contrib, TEXT, 28, 700, "middle")
    + txt(cols[0], 90, "Total Contributions", GOLD, 14, 600, "middle")
    + txt(cols[0], 112, f"Since {fmt_day(first_active)}" if first_active else "", MUTED, 12, 400, "middle")
    + f'<circle cx="{cols[1]}" cy="{ry}" r="{R2}" fill="none" stroke="{TRACK}" stroke-width="6"/>'
    + f'<circle cx="{cols[1]}" cy="{ry}" r="{R2}" fill="none" stroke="{GOLD}" stroke-width="6" stroke-linecap="round" '
      f'stroke-dasharray="{circ2*ratio:.1f} {circ2:.1f}" transform="rotate(-90 {cols[1]} {ry})"/>'
    + txt(cols[1], ry + 9, current, TEXT, 26, 700, "middle")
    + txt(cols[1], 122, "Current Streak", GOLD, 14, 600, "middle")
    + txt(cols[1], 140, fmt_range(current, current_end), MUTED, 12, 400, "middle")
    + txt(cols[2], 62, longest, TEXT, 28, 700, "middle")
    + txt(cols[2], 90, "Longest Streak", GOLD, 14, 600, "middle")
    + txt(cols[2], 112, fmt_range(longest, longest_end), MUTED, 12, 400, "middle")
)
streak_svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{SW}" height="{SH}" '
              f'viewBox="0 0 {SW} {SH}">{streak_inner}</svg>')

os.makedirs(OUT, exist_ok=True)
for fn, svg in (("stats.svg", stats_svg), ("top-langs.svg", langs_svg), ("streak.svg", streak_svg)):
    with open(os.path.join(OUT, fn), "w", encoding="utf-8", newline="\n") as f:
        f.write(svg)
print(s, f"rank={level} top {percentile:.1f}%", f"total={total_contrib} current={current} longest={longest}")
