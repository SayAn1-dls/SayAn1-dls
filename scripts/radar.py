#!/usr/bin/env python3
"""radar.py - render a spider/radar chart as standalone SVG. Stdlib only."""
from __future__ import annotations
import argparse, json, math, os, sys, urllib.error, urllib.request
from pathlib import Path

THEMES = {
    "dark": {"grid":"#30363d","spoke":"#21262d","label":"#c9d1d9","value":"#8b949e",
             "title":"#e6edf3","fill":"#39d353","stroke":"#3fb950","vertex":"#7ee787","bg":"none"},
    "light": {"grid":"#d0d7de","spoke":"#e6eaef","label":"#1f2328","value":"#57606a",
              "title":"#1f2328","fill":"#2da44e","stroke":"#1a7f37","vertex":"#116329","bg":"none"},
}
UA = {"User-Agent": "radar.py"}
FONT = "ui-sans-serif,-apple-system,Segoe UI,Helvetica,Arial,sans-serif"
LBL, VAL, TTL = 13, 11, 15

def esc(s): return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")
def ring(radius, n, start=-math.pi/2):
    return [(radius*math.cos(start+i*2*math.pi/n), radius*math.sin(start+i*2*math.pi/n)) for i in range(n)]
def text_width(s, fs): return len(s)*fs*0.62

def from_json(path):
    d = json.loads(path.read_text(encoding="utf-8"))
    return d.get("title","Skill Radar"), [(a["label"],float(a["value"])) for a in d["axes"]]

def _api(url, token):
    req = urllib.request.Request(url, headers=dict(UA))
    if token: req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r: return json.loads(r.read().decode())

def from_github(user, token, limit, exclude, curve):
    totals = {}
    page = 1
    while True:
        repos = _api(f"https://api.github.com/users/{user}/repos?per_page=100&page={page}&type=owner&sort=pushed", token)
        if not repos: break
        for repo in repos:
            if repo.get("fork") or repo.get("archived"): continue
            try:
                langs = _api(repo["languages_url"], token)
            except: continue
            for name, count in langs.items():
                if name.lower() in exclude: continue
                totals[name] = totals.get(name,0) + count
        if len(repos) < 100: break
        page += 1
    if not totals: sys.exit(f"no language data for '{user}'")
    top = sorted(totals.items(), key=lambda kv:-kv[1])[:limit]
    peak = top[0][1]
    return f"{user} \u00b7 language mix", [(n, round(100*(c/peak)**curve,1)) for n,c in top]

def render(title, axes, theme, size=420, rings=5, show_values=True, animate=True):
    c = THEMES[theme]
    n = len(axes)
    r = size/2 - 8
    gap = 20
    vals = [max(0.0,min(100.0,v)) for _,v in axes]
    outer = ring(r, n)
    labels = []
    for i,(label,_) in enumerate(axes):
        ang = -math.pi/2 + i*2*math.pi/n
        cosv, sinv = math.cos(ang), math.sin(ang)
        lx, ly = (r+gap)*cosv, (r+gap)*sinv
        anchor = "middle" if abs(cosv)<0.25 else ("start" if cosv>0 else "end")
        dy = 4 if abs(sinv)<0.25 else (14 if sinv>0 else -5)
        labels.append((lx, ly+dy, anchor, label, vals[i]))
    minx, maxx, miny, maxy = -r, r, -r, r
    for lx,ly,anchor,label,v in labels:
        w = max(text_width(label,LBL), text_width(f"{v:g}",VAL) if show_values else 0.0)
        x0,x1 = (lx,lx+w) if anchor=="start" else ((lx-w,lx) if anchor=="end" else (lx-w/2,lx+w/2))
        minx,maxx = min(minx,x0),max(maxx,x1)
        miny,maxy = min(miny,ly-LBL),max(maxy,ly+4+(VAL+4 if show_values else 0))
    pad=10; title_h=TTL+14 if title else 0
    W=round((maxx-minx)+2*pad); H=round((maxy-miny)+2*pad+title_h)
    ox,oy = -minx+pad,-miny+pad+title_h
    if title:
        need=round(text_width(title,TTL)+2*pad)
        if need>W: ox+=(need-W)/2; W=need
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="{esc(title) or "radar"}" font-family="{FONT}">']
    if c["bg"]!="none": parts.append(f'<rect width="100%" height="100%" fill="{c["bg"]}"/>')
    if title: parts.append(f'<text x="{W/2:.1f}" y="{pad+TTL:.0f}" text-anchor="middle" font-size="{TTL}" font-weight="700" fill="{c["title"]}">{esc(title)}</text>')
    parts.append(f'<g transform="translate({ox:.1f},{oy:.1f})">')
    for k in range(rings,0,-1):
        d=" ".join(f"{x:.1f},{y:.1f}" for x,y in ring(r*k/rings,n))
        parts.append(f'<polygon points="{d}" fill="none" stroke="{c["grid"]}" stroke-width="1" opacity="{0.35+0.5*k/rings:.2f}"/>')
    for x,y in outer:
        parts.append(f'<line x1="0" y1="0" x2="{x:.1f}" y2="{y:.1f}" stroke="{c["spoke"]}" stroke-width="1"/>')
    shape=[(px*v/100,py*v/100) for (px,py),v in zip(outer,vals)]
    d=" ".join(f"{x:.1f},{y:.1f}" for x,y in shape)
    anim = ('<animateTransform attributeName="transform" type="scale" values="0.04;1" dur="1.1s" calcMode="spline" keySplines="0.22 1 0.36 1" fill="freeze"/>'
            if animate else "")
    parts.append(f'<g>{anim}<polygon points="{d}" fill="{c["fill"]}" fill-opacity="0.18" stroke="{c["stroke"]}" stroke-width="2" stroke-linejoin="round"/></g>')
    for (px,py),v in zip(outer,vals):
        vx,vy=px*v/100,py*v/100
        parts.append(f'<circle cx="{vx:.1f}" cy="{vy:.1f}" r="3.5" fill="{c["vertex"]}" stroke="{c["bg"] if c["bg"]!="none" else "#0d1117"}" stroke-width="1.5"/>')
    for lx,ly,anchor,label,v in labels:
        parts.append(f'<text x="{lx:.1f}" y="{ly:.0f}" font-size="{LBL}" text-anchor="{anchor}" fill="{c["label"]}" font-weight="600">{esc(label)}</text>')
        if show_values:
            parts.append(f'<text x="{lx:.1f}" y="{ly+VAL+2:.0f}" font-size="{VAL}" text-anchor="{anchor}" fill="{c["value"]}">{v:g}</text>')
    parts.append("</g></svg>")
    return "".join(parts)

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--data",type=Path)
    p.add_argument("--github")
    p.add_argument("-o","--out",type=Path,default=Path("assets/radar"))
    p.add_argument("--size",type=int,default=420)
    p.add_argument("--rings",type=int,default=5)
    p.add_argument("--limit",type=int,default=8)
    p.add_argument("--exclude",default="html,css,scss,dockerfile,makefile,shell,batchfile,powershell,tex,rich text format")
    p.add_argument("--curve",type=float,default=0.5)
    p.add_argument("--no-values",action="store_true")
    p.add_argument("--no-animate",action="store_true")
    args=p.parse_args(argv)
    token=os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if args.github:
        title,axes=from_github(args.github,token,args.limit,set(args.exclude.lower().split(",")),args.curve)
    elif args.data:
        title,axes=from_json(args.data)
    else:
        sys.exit("need --data or --github")
    args.out.parent.mkdir(parents=True,exist_ok=True)
    for theme in ("dark","light"):
        svg=render(title,axes,theme,args.size,args.rings,not args.no_values,not args.no_animate)
        dest=args.out.with_name(f"{args.out.name}-{theme}.svg")
        dest.write_text(svg,encoding="utf-8")
        print(f"wrote {dest}")

if __name__=="__main__":
    main()
