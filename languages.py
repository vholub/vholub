import json
import os
import sys
import time
import urllib.request
from html import escape

API = "https://api.github.com/graphql"
QUERY = """
query($cursor: String) {
  viewer {
    repositories(first: 50, after: $cursor, ownerAffiliations: OWNER, isFork: false) {
      pageInfo { hasNextPage endCursor }
      nodes {
        name
        nameWithOwner
        languages(first: 20, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""


def split_env(key):
    return {x.strip().lower() for x in os.environ.get(key, "").split(",") if x.strip()}


def fetch(cursor):
    body = json.dumps({"query": QUERY, "variables": {"cursor": cursor}}).encode()
    request = urllib.request.Request(
        API,
        data=body,
        headers={
            "Authorization": "Bearer " + os.environ["GH_TOKEN"],
            "Content-Type": "application/json",
        },
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = json.load(response)
            break
        except Exception:
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))
    if "errors" in data:
        sys.exit("GraphQL errors: " + ", ".join(str(e.get("type")) for e in data["errors"]))
    return data["data"]["viewer"]["repositories"]


def collect():
    excluded_repos = split_env("EXCLUDE_REPOS")
    excluded_languages = split_env("EXCLUDE_LANGUAGES")
    totals = {}
    colors = {}
    cursor = None
    while True:
        page = fetch(cursor)
        for repo in page["nodes"]:
            if repo["name"].lower() in excluded_repos or repo["nameWithOwner"].lower() in excluded_repos:
                continue
            for edge in repo["languages"]["edges"]:
                name = edge["node"]["name"]
                if name.lower() in excluded_languages:
                    continue
                totals[name] = totals.get(name, 0) + edge["size"]
                colors[name] = edge["node"]["color"] or "#8b949e"
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    return totals, colors


def render(totals, colors, limit):
    grand_total = sum(totals.values())
    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    items = ranked[:limit]
    rest = sum(size for _, size in ranked[limit:])
    if rest:
        items.append(("Other", rest))
        colors["Other"] = "#8b949e"

    width = 495
    pad = 25
    bar_width = width - 2 * pad
    column_width = bar_width / 2
    rows = (len(items) + 1) // 2
    height = 100 + rows * 24 + 10

    segments = []
    x = pad
    for name, size in items:
        segment = bar_width * size / grand_total
        segments.append(
            f'<rect x="{x:.2f}" y="55" width="{segment:.2f}" height="8" fill="{escape(colors[name])}"/>'
        )
        x += segment

    legend = []
    for index, (name, size) in enumerate(items):
        column = index % 2
        row = index // 2
        left = pad + column * column_width
        y = 100 + row * 24
        percent = f"{size / grand_total * 100:.1f}%"
        legend.append(
            f'<circle cx="{left + 5:.2f}" cy="{y - 4}" r="5" fill="{escape(colors[name])}"/>'
            f'<text x="{left + 18:.2f}" y="{y}" class="label">{escape(name)}</text>'
            f'<text x="{left + column_width - 20:.2f}" y="{y}" class="muted" text-anchor="end">{percent}</text>'
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<style>
:root{{--bg:#ffffff;--fg:#1f2328;--muted:#59636e;--border:#d1d9e0}}
@media (prefers-color-scheme: dark){{:root{{--bg:#0d1117;--fg:#f0f6fc;--muted:#9198a1;--border:#3d444d}}}}
text{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;font-size:13px}}
.title{{font-size:16px;font-weight:600;fill:var(--fg)}}
.label{{fill:var(--fg)}}
.muted{{fill:var(--muted)}}
</style>
<defs><clipPath id="bar"><rect x="{pad}" y="55" width="{bar_width}" height="8" rx="4"/></clipPath></defs>
<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="6" fill="var(--bg)" stroke="var(--border)"/>
<text x="{pad}" y="35" class="title">Most used languages</text>
<g clip-path="url(#bar)">{"".join(segments)}</g>
{"".join(legend)}
</svg>
"""


def main():
    totals, colors = collect()
    if not totals:
        sys.exit("No language data")
    limit = int(os.environ.get("LIMIT", "8"))
    with open(os.environ.get("OUTPUT", "languages.svg"), "w", encoding="utf-8") as file:
        file.write(render(totals, colors, limit))


main()
