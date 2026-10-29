"""Generate profile stat cards as SVG from the GitHub GraphQL API."""
import json, os, sys, urllib.request
from html import escape

USER = os.environ.get("GH_USER", "Karry1123")
TOKEN = os.environ["GH_TOKEN"]
OUT = sys.argv[1] if len(sys.argv) > 1 else "assets"

BG, BORDER, GOLD, TEXT, MUTED = "#0f172a", "#1e3a5f", "#c7a555", "#e2e8f0", "#94a3b8"
FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', sans-serif"

Q = """query($login:String!,$after:String){
  user(login:$login){
    name
    contributionsCollection{ totalCommitContributions restrictedContributionsCount
      totalPullRequestContributions totalIssueContributions }
    repositories(first:100, after:$after, ownerAffiliations:OWNER, isFork:false, privacy:PUBLIC){
      pageInfo{ hasNextPage endCursor }
      nodes{ stargazerCount
        languages(first:10, orderBy:{field:SIZE, direction:DESC}){
          edges{ size node{ name color } } } } } } }"""

def gql(after=None):
    body = json.dumps({"query": Q, "variables": {"login": USER, "after": after}}).encode()
    req = urllib.request.Request("https://api.github.com/graphql", body,
        {"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"})
    data = json.load(urllib.request.urlopen(req))
    if "errors" in data:
        raise SystemExit(data["errors"])
    return data["data"]["user"]

repos, after = [], None
while True:
    u = gql(after)
    repos += u["repositories"]["nodes"]
    pi = u["repositories"]["pageInfo"]
    if not pi["hasNextPage"]:
        break
    after = pi["endCursor"]
cc = u["contributionsCollection"]

stars = sum(r["stargazerCount"] for r in repos)
langs = {}
for r in repos:
    for e in r["languages"]["edges"]:
        n = e["node"]["name"]
        size, color = langs.get(n, (0, None))
        langs[n] = (size + e["size"], e["node"]["color"] or "#888888")

stats = [
    ("Commits (last year)", cc["totalCommitContributions"] + cc["restrictedContributionsCount"]),
    ("Pull requests", cc["totalPullRequestContributions"]),
    ("Issues", cc["totalIssueContributions"]),
    ("Public repos", len(repos)),
    ("Stars earned", stars),
]

def frame(w, h, title, inner):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="8" fill="{BG}" stroke="{BORDER}"/>'
            f'<text x="24" y="36" fill="{GOLD}" font-family="{FONT}" font-size="17" font-weight="600">{escape(title)}</text>'
            f'{inner}</svg>')

# Stats card
rows = ""
for i, (k, v) in enumerate(stats):
    y = 70 + i * 24
    rows += (f'<circle cx="30" cy="{y-5}" r="3" fill="{GOLD}"/>'
             f'<text x="44" y="{y}" fill="{TEXT}" font-family="{FONT}" font-size="14">{escape(k)}</text>'
             f'<text x="326" y="{y}" fill="{TEXT}" font-family="{FONT}" font-size="14" font-weight="600" text-anchor="end">{v}</text>')
stats_svg = frame(350, 185, "Karry's GitHub Stats", rows)

# Top languages card
top = sorted(langs.items(), key=lambda kv: -kv[1][0])[:6]
total = sum(s for _, (s, _) in top) or 1
bar, x, W = "", 24.0, 302.0
for name, (s, color) in top:
    w = W * s / total
    bar += f'<rect x="{x:.2f}" y="54" width="{w:.2f}" height="8" fill="{color}"/>'
    x += w
bar = (f'<clipPath id="c"><rect x="24" y="54" width="{W}" height="8" rx="4"/></clipPath>'
       f'<g clip-path="url(#c)">{bar}</g>')
legend = ""
for i, (name, (s, color)) in enumerate(top):
    cx, cy = 24 + (i % 2) * 155, 90 + (i // 2) * 26
    legend += (f'<circle cx="{cx+5}" cy="{cy-4}" r="5" fill="{color}"/>'
               f'<text x="{cx+16}" y="{cy}" fill="{TEXT}" font-family="{FONT}" font-size="13">'
               f'{escape(name)} <tspan fill="{MUTED}">{100*s/total:.1f}%</tspan></text>')
langs_svg = frame(350, 185, "Most Used Languages", bar + legend)

os.makedirs(OUT, exist_ok=True)
for fn, svg in (("stats.svg", stats_svg), ("top-langs.svg", langs_svg)):
    with open(os.path.join(OUT, fn), "w", encoding="utf-8", newline="\n") as f:
        f.write(svg)
print("stats:", stats, "langs:", [n for n, _ in top])
