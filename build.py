#!/usr/bin/env python3
"""Build the website and the CVA (FECYT/AEI format) from the files in data/.

    python build.py            -> writes everything to _site/
    python build.py --no-pdf   -> skip the CVA PDF (faster, no WeasyPrint needed)

GitHub runs this automatically on every push (see .github/workflows/deploy.yml),
so editing a file in data/ updates both the web pages and the downloadable CVA.
"""
import datetime as dt
import re
import shutil
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

ROOT = Path(__file__).parent
DATA = ROOT / "data"
OUT = ROOT / "_site"
CVA_MAX_ITEMS = 10        # AEI: max. 10 contributions per Part C section
CVA_MAX_SUMMARY = 5000    # AEI: Part B max. 5000 characters incl. spaces
CVA_MAX_PAGES = 4         # AEI: Parts A+B+C max. 4 pages

warnings = []


def load(name, default=None):
    path = DATA / f"{name}.yml"
    if not path.exists():
        return default
    return yaml.safe_load(path.read_text(encoding="utf-8")) or default


def find_todos(obj, where):
    """Collect every value still starting with 'TODO' so we can list them."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            find_todos(v, f"{where}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            find_todos(v, f"{where}[{i}]")
    elif isinstance(obj, str) and "TODO" in obj:
        warnings.append(f"placeholder still to fill: {where}")


# ---------------------------------------------------------------- filters
def todo(value):
    """Show 'TODO ...' placeholders highlighted in yellow."""
    if value is None or value == "":
        return Markup("")
    s = str(escape(str(value)))
    # highlight from "TODO" to the end of that sentence
    return Markup(re.sub(r"TODO[^.\n]*\.?", lambda m: f'<span class="todo">{m.group(0)}</span>', s))


def author_list(pub, me, cva=False):
    """Format authors. In CVA mode apply the AEI rule for more than 8 authors:
    first three, last, corresponding author(s) (AC), total number and own position."""
    authors = pub["authors"]
    n = pub.get("n_authors", len(authors))
    corr = set(pub.get("corresponding", []))

    def fmt(a):
        s = escape(a)
        if a == me:
            s = Markup(f"<strong>{s}</strong>")
        if cva and a in corr and n > 8:
            s = Markup(f"{s} (AC)")
        return s

    if cva and n > 8:
        pos = authors.index(me) + 1 if me in authors else pub.get("position")
        last = pub.get("last_author", authors[-1])
        shown = list(authors[:3])
        extra = [a for a in sorted(corr) if a not in shown and a != last]
        parts = [fmt(a) for a in shown] + ["…"] + [fmt(a) for a in extra] + [fmt(last)]
        txt = Markup("; ").join(parts)
        return Markup(f"{txt} ({pos}/{n})")

    if not cva and n > len(authors):           # truncated list on the website
        return Markup(", ").join(fmt(a) for a in authors) + Markup(", et al.")
    if cva or len(authors) == 1:
        return Markup(", ").join(fmt(a) for a in authors)
    if len(authors) == 1:
        return fmt(authors[0])
    return Markup(", ").join(fmt(a) for a in authors[:-1]) + Markup(" and ") + fmt(authors[-1])


def source(pub, cva=False):
    s = escape(pub["journal"])
    if pub.get("volume"):
        s += Markup(", ") + escape(pub["volume"])
        if pub.get("pages"):
            s += Markup(":" if cva else ", ") + escape(pub["pages"])
    if pub.get("status"):
        s += Markup(f" ({escape(pub['status'])})")
    return s


def select_for_cva(items, label):
    chosen = [x for x in items if x.get("cva")]
    if not chosen:
        chosen = items[:CVA_MAX_ITEMS]
    if len(chosen) > CVA_MAX_ITEMS:
        warnings.append(f"{label}: {len(chosen)} items marked 'cva: true', only the first {CVA_MAX_ITEMS} are used")
        chosen = chosen[:CVA_MAX_ITEMS]
    return chosen


def main():
    make_pdf = "--no-pdf" not in sys.argv
    profile = load("profile", {})
    pubs = load("publications", [])
    news = load("news", [])
    talks = load("congresos", [])
    projects = load("proyectos", [])
    transfer = load("transferencia", [])

    for name, obj in [("profile", profile), ("congresos", talks),
                      ("proyectos", projects), ("transferencia", transfer)]:
        find_todos(obj, name)

    # newest first, whatever order they were typed in
    pubs.sort(key=lambda p: p["year"], reverse=True)
    news.sort(key=lambda n: str(n["date"]), reverse=True)
    talks.sort(key=lambda t: str(t.get("date", "")), reverse=True)

    me = profile["cva_name"]
    today = dt.date.today()
    env = Environment(loader=FileSystemLoader(ROOT / "templates"),
                      autoescape=select_autoescape(["html"]))
    env.filters["todo"] = todo
    env.globals.update(
        profile=profile, me=me, today=today,
        authors=author_list, source=source,
        cva_file=profile.get("cva_filename", "CVA.pdf"),
        has_talks=bool(talks), has_projects=bool(projects),
    )

    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(ROOT / "static", OUT)

    years = sorted({p["year"] for p in pubs}, reverse=True)
    pages = {
        "index.html": dict(page="home", pubs=pubs, news=news[:3]),
        "publications.html": dict(page="publications", pubs=pubs, years=years),
        "news.html": dict(page="news", news=news),
    }
    if talks:
        pages["talks.html"] = dict(page="talks", talks=talks)
    if projects:
        pages["projects.html"] = dict(page="projects", projects=projects)
    for name, ctx in pages.items():
        (OUT / name).write_text(env.get_template(name).render(**ctx), encoding="utf-8")

    # ------------------------------------------------------------ CVA
    summary = profile.get("cva_summary", "")
    n_chars = len(" ".join(summary.split()))
    if n_chars > CVA_MAX_SUMMARY:
        warnings.append(f"CVA Part B has {n_chars} characters (max. {CVA_MAX_SUMMARY})")
    cva_html = env.get_template("cva.html").render(
        c1=select_for_cva(pubs, "publications"),
        c2=select_for_cva(talks, "congresos"),
        c3=select_for_cva(projects, "proyectos"),
        c4=select_for_cva(transfer, "transferencia"),
        summary_paragraphs=[p.strip() for p in summary.split("\n\n") if p.strip()],
        summary_chars=n_chars,
    )
    (OUT / "cva.html").write_text(cva_html, encoding="utf-8")

    if make_pdf:
        from weasyprint import HTML
        doc = HTML(string=cva_html, base_url=str(OUT)).render()
        npages = len(doc.pages)
        doc.write_pdf(OUT / env.globals["cva_file"])
        print(f"CVA: {npages} page(s), Part B {n_chars} characters")
        if npages > CVA_MAX_PAGES:
            warnings.append(f"CVA is {npages} pages long (AEI max. {CVA_MAX_PAGES}); "
                            "mark fewer items with 'cva: true' or shorten Part B")

    print(f"Website written to {OUT}/ ({len(pages)} pages)")
    for w in warnings:
        print("  warning:", w)


if __name__ == "__main__":
    main()
