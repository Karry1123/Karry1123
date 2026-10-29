"""Generate profile cards (rated stats, top languages, open-source PRs) as SVG.

The rank uses the same formula as github-readme-stats (MIT licensed):
weighted CDFs of commits, PRs, issues, reviews, stars and followers.
"""
import json, math, os, sys, urllib.request
from collections import defaultdict
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


def gql(after=None, pr_after=None):
    body = json.dumps({"query": Q, "variables": {"login": USER, "after": after, "prAfter": pr_after}}).encode()
    req = urllib.request.Request("https://api.github.com/graphql", body,
                                 {"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"})
    data = json.load(urllib.request.urlopen(req))
    if "errors" in data:
        raise SystemExit(data["errors"])
    return data["data"]["user"]


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

# ---- open-source contributions (PRs to other people's public repos) ----
ext = defaultdict(lambda: {"total": 0, "merged": 0, "stars": 0})
for p in public_prs:
    repo = p["repository"]
    if repo["owner"]["login"].lower() == USER.lower():
        continue
    e = ext[repo["nameWithOwner"]]
    e["total"] += 1
    e["merged"] += p["state"] == "MERGED"
    e["stars"] = repo["stargazerCount"]
top_ext = sorted(ext.items(), key=lambda kv: (-kv[1]["stars"], -kv[1]["merged"], -kv[1]["total"]))[:6]


def kfmt(n):
    return f"{n/1000:.1f}k" if n >= 1000 else str(n)


h = 72 + 26 * max(len(top_ext), 1)
inner = (txt(24, 58, "Repository", MUTED, 12) + txt(330, 58, "Stars", MUTED, 12, anchor="end")
         + txt(426, 58, "PRs (merged)", MUTED, 12, anchor="end"))
for i, (name, e) in enumerate(top_ext):
    y = 86 + i * 26
    inner += (f'<circle cx="30" cy="{y-5}" r="3" fill="{GOLD}"/>' + txt(44, y, name, size=13)
              + txt(330, y, "★ " + kfmt(e["stars"]), GOLD if e["stars"] >= 1000 else MUTED, 13, anchor="end")
              + txt(426, y, f'{e["total"]} ({e["merged"]})', TEXT, 13, 600, anchor="end"))
if not top_ext:
    inner += txt(24, 86, "No external pull requests yet", MUTED, 13)
oss_svg = frame(450, h, "Open-source Contributions", inner)

os.makedirs(OUT, exist_ok=True)
for fn, svg in (("stats.svg", stats_svg), ("top-langs.svg", langs_svg), ("oss.svg", oss_svg)):
    with open(os.path.join(OUT, fn), "w", encoding="utf-8", newline="\n") as f:
        f.write(svg)
print(s, f"rank={level} top {percentile:.1f}%", [(n, dict(e)) for n, e in top_ext])
