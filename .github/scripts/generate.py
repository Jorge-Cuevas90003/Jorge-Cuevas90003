"""
generate.py — Auto-generates dynamic Brutalist Swiss SVGs for the GitHub profile.

SVGs generated:
  - stack.svg       : Top languages by actual bytes across all repos
  - projects.svg    : Last 2 updated non-fork repos
  - stats.svg       : Repos count, total stars, top language, last push date
  - last_commit.svg : Last commit message + repo + date
"""

import os
import sys
import requests
from datetime import datetime, timezone

# ─── Config ──────────────────────────────────────────────────────────────────
USERNAME = os.environ.get("GITHUB_USERNAME", "Jorge-Cuevas90003")
TOKEN    = os.environ.get("GITHUB_TOKEN", "")

HEADERS = {"Accept": "application/vnd.github.v3+json"}
if TOKEN:
    HEADERS["Authorization"] = f"token {TOKEN}"

# ─── API helpers ─────────────────────────────────────────────────────────────
def get(url, params=None):
    r = requests.get(url, headers=HEADERS, params=params, timeout=10)
    if r.status_code in (401, 403):
        # No token locally — return empty so script doesn't crash
        return {} if params is None else []
    r.raise_for_status()
    return r.json()

def get_user():
    return get(f"https://api.github.com/users/{USERNAME}")

def get_repos():
    """Fetch all non-fork public repos."""
    repos, page = [], 1
    while True:
        data = get(f"https://api.github.com/users/{USERNAME}/repos",
                   params={"per_page": 100, "page": page, "sort": "updated"})
        if not data:
            break
        repos.extend(data)
        if len(data) < 100:
            break
        page += 1
    return [r for r in repos if not r.get("fork", False)]

def get_languages(repo_name):
    try:
        return get(f"https://api.github.com/repos/{USERNAME}/{repo_name}/languages")
    except Exception:
        return {}

def get_last_commit():
    try:
        events = get(f"https://api.github.com/users/{USERNAME}/events/public",
                     params={"per_page": 15})
        for event in events:
            if event.get("type") == "PushEvent":
                commits = event.get("payload", {}).get("commits", [])
                if commits:
                    msg = commits[-1].get("message", "").split("\n")[0]
                    msg = (msg[:55] + "…") if len(msg) > 55 else msg
                    repo = event["repo"]["name"].split("/")[-1]
                    date = event["created_at"][:10]
                    return {"message": msg, "repo": repo, "date": date}
    except Exception:
        pass
    return {"message": "no public commits found", "repo": "—", "date": "—"}

# ─── Language aggregation ────────────────────────────────────────────────────
def aggregate_languages(repos):
    totals = {}
    for repo in repos:
        langs = get_languages(repo["name"])
        for lang, bytes_count in langs.items():
            totals[lang] = totals.get(lang, 0) + bytes_count
    total_bytes = sum(totals.values()) or 1
    ranked = sorted(totals.items(), key=lambda x: x[1], reverse=True)
    return [(lang, round(bytes_ / total_bytes * 100, 1)) for lang, bytes_ in ranked]

# ─── SVG: stack.svg ──────────────────────────────────────────────────────────
def make_stack_svg(lang_data):
    top = lang_data[:7]
    # Normalise to 100% among top langs
    top_total = sum(p for _, p in top) or 1
    top = [(l, round(p / top_total * 100, 1)) for l, p in top]

    BAR_X, BAR_Y   = 30, 70
    BAR_TOTAL_W    = 840
    BAR_H          = 28
    LABEL_Y        = 58

    segments = []
    label_parts = []
    cursor = BAR_X
    for i, (lang, pct) in enumerate(top):
        w = max(int(BAR_TOTAL_W * pct / 100), 2)
        if i == 0:
            segments.append(f'<rect x="{cursor}" y="{BAR_Y}" width="{w}" height="{BAR_H}" fill="#F5E642"/>')
        elif pct >= 8:
            segments.append(f'<rect x="{cursor}" y="{BAR_Y}" width="{w}" height="{BAR_H}" fill="none" stroke="#F5E642" stroke-width="1.5"/>')
        else:
            segments.append(f'<rect x="{cursor}" y="{BAR_Y}" width="{w}" height="{BAR_H}" fill="none" stroke="#444444" stroke-width="1"/>')

        fill_color = "#111111" if i == 0 else ("#F5E642" if pct >= 8 else "#555555")
        mid = cursor + w // 2
        label_parts.append(f'<text x="{mid}" y="{BAR_Y + 19}" font-size="9" font-weight="700" fill="{fill_color}" text-anchor="middle">{lang.upper()[:6]}</text>')
        cursor += w

    # pct labels below bar
    cursor = BAR_X
    pct_labels = []
    for i, (lang, pct) in enumerate(top):
        w = max(int(BAR_TOTAL_W * pct / 100), 2)
        mid = cursor + w // 2
        col = "#F5E642" if pct >= 8 else "#555555"
        pct_labels.append(f'<text x="{mid}" y="{BAR_Y + 46}" font-size="8" fill="{col}" text-anchor="middle">{pct}%</text>')
        cursor += w

    segs_str   = "\n  ".join(segments)
    labels_str = "\n  ".join(label_parts)
    pcts_str   = "\n  ".join(pct_labels)
    today      = datetime.now(timezone.utc).strftime("%b %d, %Y")

    return f'''<svg width="900" height="130" viewBox="0 0 900 130" xmlns="http://www.w3.org/2000/svg" font-family="'Arial Black', Arial, sans-serif">
  <rect width="900" height="130" fill="#111111"/>
  <rect x="0" y="0" width="900" height="4" fill="#F5E642"/>
  <text x="30" y="30" font-size="9" font-weight="700" fill="#F5E642" letter-spacing="8">TECH STACK // SORTED BY ACTUAL USAGE</text>
  <rect x="30" y="36" width="840" height="1" fill="#F5E642" opacity="0.3"/>
  <text x="820" y="30" font-size="8" fill="#444444" text-anchor="end">updated {today}</text>
  {segs_str}
  {labels_str}
  {pcts_str}
</svg>'''

# ─── SVG: projects.svg ───────────────────────────────────────────────────────
def make_projects_svg(repos):
    recent = sorted(repos, key=lambda r: r.get("pushed_at", ""), reverse=True)[:2]

    def fmt_date(iso):
        try:
            return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%b %d, %Y")
        except Exception:
            return "—"

    def card(repo, x_offset, num):
        name = repo.get("name", "—")
        desc = repo.get("description") or "No description."
        if len(desc) > 52:
            desc = desc[:52] + "…"
        lang = (repo.get("language") or "—").upper()
        date = fmt_date(repo.get("pushed_at", ""))
        stars = repo.get("stargazers_count", 0)

        return f'''
  <rect x="{x_offset}" y="52" width="3" height="90" fill="#F5E642"/>
  <text x="{x_offset + 14}" y="70" font-size="10" font-weight="700" fill="#F5E642" letter-spacing="5">0{num} — {name[:22].upper()}</text>
  <text x="{x_offset + 14}" y="88" font-size="11" font-weight="400" fill="#CCCCCC">{lang} · ★ {stars}</text>
  <text x="{x_offset + 14}" y="106" font-size="10" font-weight="400" fill="#888888">{desc}</text>
  <text x="{x_offset + 14}" y="130" font-size="9" fill="#555555">pushed {date}</text>'''

    c1 = card(recent[0], 30, 1) if len(recent) > 0 else ""
    c2 = card(recent[1], 476, 2) if len(recent) > 1 else ""
    today = datetime.now(timezone.utc).strftime("%b %d, %Y")

    return f'''<svg width="900" height="160" viewBox="0 0 900 160" xmlns="http://www.w3.org/2000/svg" font-family="'Arial', sans-serif">
  <rect width="900" height="160" fill="#111111"/>
  <rect x="0" y="0" width="900" height="4" fill="#F5E642"/>
  <text x="30" y="30" font-size="9" font-weight="700" fill="#F5E642" letter-spacing="8">LAST UPDATES // TWO MOST RECENT REPOS</text>
  <rect x="30" y="36" width="840" height="1" fill="#F5E642" opacity="0.3"/>
  <text x="870" y="30" font-size="8" fill="#444444" text-anchor="end">updated {today}</text>
  <rect x="464" y="52" width="1" height="90" fill="#333333"/>
  {c1}
  {c2}
</svg>'''

# ─── SVG: stats.svg ──────────────────────────────────────────────────────────
def make_stats_svg(user, repos, top_lang):
    pub_repos = user.get("public_repos", 0)
    stars = sum(r.get("stargazers_count", 0) for r in repos)
    followers = user.get("followers", 0)
    today = datetime.now(timezone.utc).strftime("%b %d, %Y")

    def box(x, label, value, filled=False):
        bg    = '#F5E642' if filled else 'none'
        stk   = '' if filled else ' stroke="#F5E642" stroke-width="1.5"'
        tcol  = '#111111' if filled else '#F5E642'
        scol  = '#111111' if filled else '#888888'
        return f'''
  <rect x="{x}" y="50" width="190" height="68" fill="{bg}"{stk}/>
  <text x="{x + 95}" y="78" font-size="22" font-weight="900" fill="{tcol}" text-anchor="middle">{value}</text>
  <text x="{x + 95}" y="100" font-size="9" font-weight="700" fill="{scol}" text-anchor="middle" letter-spacing="3">{label}</text>'''

    b1 = box(30,  "PUBLIC REPOS",  pub_repos, filled=True)
    b2 = box(232, "TOTAL STARS",   stars)
    b3 = box(434, "TOP LANGUAGE",  top_lang[:8].upper() if top_lang else "—")
    b4 = box(636, "FOLLOWERS",     followers)

    return f'''<svg width="900" height="140" viewBox="0 0 900 140" xmlns="http://www.w3.org/2000/svg" font-family="'Arial Black', Arial, sans-serif">
  <rect width="900" height="140" fill="#111111"/>
  <rect x="0" y="0" width="900" height="4" fill="#F5E642"/>
  <text x="30" y="30" font-size="9" font-weight="700" fill="#F5E642" letter-spacing="8">SYSTEM METRICS // LIVE STATS</text>
  <rect x="30" y="36" width="840" height="1" fill="#F5E642" opacity="0.3"/>
  <text x="870" y="30" font-size="8" fill="#444444" text-anchor="end">updated {today}</text>
  {b1}{b2}{b3}{b4}
</svg>'''

# ─── SVG: last_commit.svg ────────────────────────────────────────────────────
def make_last_commit_svg(commit):
    msg  = commit["message"]
    repo = commit["repo"]
    date = commit["date"]
    return f'''<svg width="900" height="64" viewBox="0 0 900 64" xmlns="http://www.w3.org/2000/svg" font-family="'Arial', sans-serif">
  <rect width="900" height="64" fill="#111111"/>
  <rect x="0" y="0" width="4" height="64" fill="#F5E642"/>
  <rect x="0" y="60" width="900" height="4" fill="#F5E642"/>
  <text x="20" y="22" font-size="9" font-weight="700" fill="#F5E642" letter-spacing="6">LAST COMMIT</text>
  <text x="20" y="44" font-size="12" font-weight="400" fill="#CCCCCC">"{msg}"</text>
  <text x="870" y="44" font-size="10" fill="#555555" text-anchor="end">{repo} · {date}</text>
</svg>'''

# ─── Main ────────────────────────────────────────────────────────────────────
def main():
    print("Fetching GitHub data…")
    user   = get_user()
    repos  = get_repos()
    langs  = aggregate_languages(repos)
    commit = get_last_commit()

    top_lang = langs[0][0] if langs else "—"
    print(f"  User:      {user.get('login')}")
    print(f"  Repos:     {len(repos)}")
    print(f"  Top lang:  {top_lang}")
    print(f"  Last commit: {commit['message'][:40]}")

    files = {
        "stack.svg":       make_stack_svg(langs),
        "projects.svg":    make_projects_svg(repos),
        "stats.svg":       make_stats_svg(user, repos, top_lang),
        "last_commit.svg": make_last_commit_svg(commit),
    }

    for filename, content in files.items():
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  ✓ {filename} written")

    print("Done.")

if __name__ == "__main__":
    main()
