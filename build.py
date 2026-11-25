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

import markdown
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

ROOT = Path(__file__).parent
DATA = ROOT / "data"
OUT = ROOT / "_site"
PRIVATE = ROOT / "private"
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
        if cva and a in corr:
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
    if cva:
        pos = authors.index(me) + 1 if me in authors else pub.get("position", "?")
        return Markup(", ").join(fmt(a) for a in authors) + Markup(f" ({pos}/{n})")
    if len(authors) == 1:
        return fmt(authors[0])
    return Markup(", ").join(fmt(a) for a in authors[:-1]) + Markup(" and ") + fmt(authors[-1])


def source(pub, cva=False):
    s = escape(pub["journal"])
    if pub.get("volume"):
        s += Markup(", ") + escape(pub["volume"])
        if pub.get("pages"):
            s += Markup(":" if cva else ", ") + escape(pub["pages"])
    if pub.get("isbn"):
        s += Markup(f". ISBN {escape(pub['isbn'])}")
    if pub.get("status"):
        s += Markup(f" ({escape(pub['status'])})")
    return s


def select_for_cva(items, label, limit):
    chosen = [x for x in items if x.get("cva")]
    if not chosen:
        chosen = items[:limit]
    if len(chosen) > limit:
        warnings.append(f"{label}: {len(chosen)} items marked 'cva: true', only the first {limit} are used")
        chosen = chosen[:limit]
    return chosen


def summary_blocks(text):
    """Split Part B into paragraphs and bullet lists ("- " lines)."""
    blocks = []
    for chunk in [c.strip() for c in text.split("\n\n") if c.strip()]:
        lines = chunk.splitlines()
        if all(l.startswith("- ") for l in lines):
            blocks.append(("ul", [l[2:] for l in lines]))
        else:
            blocks.append(("p", " ".join(lines)))
    return blocks


def prepare_photos(profile):
    """Make web copies of photos/photo*.jpg in static/files/photos/.

    photos/ stays on your computer only (it is in .gitignore). The copies are rotated
    upright, cropped to 4:5 around the face, resized and stripped of metadata (GPS etc.).
    Runs only where photos/ exists, i.e. locally; GitHub uses the committed copies.
    """
    src = ROOT / "photos"
    if not src.is_dir():
        return
    from PIL import Image, ImageOps
    dst = ROOT / "static" / "files" / "photos"
    dst.mkdir(parents=True, exist_ok=True)
    focus = profile.get("photo_focus", {})
    wanted = sorted(src.glob("photo*.jp*g"))
    for old in dst.glob("*.jpg"):                     # photo deleted in photos/ -> remove copy
        if not any(old.stem == w.stem for w in wanted):
            old.unlink()
    for f in wanted:
        out = dst / (f.stem + ".jpg")
        if out.exists() and out.stat().st_mtime >= f.stat().st_mtime \
                and (ROOT / "data" / "profile.yml").stat().st_mtime <= out.stat().st_mtime:
            continue
        im = ImageOps.exif_transpose(Image.open(f)).convert("RGB")
        fx, fy = focus.get(f.name, (0.5, 0.4))         # face position as fraction of width/height
        w, h = im.size
        cw, ch = (w, int(w * 5 / 4)) if w * 5 / 4 <= h else (int(h * 4 / 5), h)
        left = min(max(int(fx * w - cw / 2), 0), w - cw)
        top = min(max(int(fy * h - ch / 2), 0), h - ch)
        im = im.crop((left, top, left + cw, top + ch)).resize((480, 600), Image.LANCZOS)
        im.save(out, "JPEG", quality=82, optimize=True)   # saved without EXIF metadata
        print(f"photo: {f.name} -> static/files/photos/{out.name}")


def load_posts():
    """Blog posts: one Markdown file per post in blog/, named YYYY-MM-DD-some-title.md,
    starting with a small header between --- lines (title, optional image and link)."""
    posts = []
    for f in sorted((ROOT / "blog").glob("*.md")):
        if f.name.startswith("_"):
            continue
        text = f.read_text(encoding="utf-8")
        meta, body = {}, text
        if text.startswith("---"):
            _, head, body = text.split("---", 2)
            meta = yaml.safe_load(head) or {}
        m = re.match(r"(\d{4}-\d{2}-\d{2})-(.+)", f.stem)
        date = dt.date.fromisoformat(str(meta.get("date") or m.group(1)))
        html = markdown.markdown(body, extensions=["extra", "sane_lists"])
        first_p = re.search(r"<p>(.*?)</p>", html, re.S)
        excerpt = re.sub(r"<[^>]+>", "", first_p.group(1)) if first_p else ""
        posts.append(dict(meta, date=date, slug=f.stem, html=Markup(html),
                          excerpt=excerpt, url=f"blog/{f.stem}.html"))
    posts.sort(key=lambda p: p["date"], reverse=True)
    return posts


def main():
    make_pdf = "--no-pdf" not in sys.argv
    profile = load("profile", {})
    pubs = load("publications", [])
    posts = load_posts()
    talks = load("congresos", [])
    projects = load("proyectos", [])
    transfer = load("transferencia", [])
    training = load("formacion", {})
    limit = profile.get("cva_max_items", CVA_MAX_ITEMS)

    for name, obj in [("profile", profile), ("congresos", talks),
                      ("proyectos", projects), ("transferencia", transfer),
                      ("formacion", training)]:
        find_todos(obj, name)

    # newest first, whatever order they were typed in
    pubs.sort(key=lambda p: p["year"], reverse=True)
    talks.sort(key=lambda t: str(t.get("date", "")), reverse=True)

    prepare_photos(profile)
    photos = sorted(p.name for p in (ROOT / "static" / "files" / "photos").glob("*.jpg"))

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
        has_theses=bool(training.get("tesis") or training.get("en_curso")), root="",
        giscus=profile.get("giscus"),
    )

    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(ROOT / "static", OUT)

    years = sorted({p["year"] for p in pubs}, reverse=True)
    pages = {
        "index.html": dict(page="home", pubs=pubs, posts=posts[:3], photos=photos),
        "publications.html": dict(page="publications", pubs=pubs, years=years),
        "blog.html": dict(page="blog", posts=posts),
        "news.html": dict(page="blog"),                 # old address, redirects to blog.html
    }
    if talks:
        pages["talks.html"] = dict(page="talks", talks=talks)
    if training.get("tesis") or training.get("en_curso"):
        pages["theses.html"] = dict(page="theses", theses=training.get("tesis", []),
                                    ongoing=training.get("en_curso", []))
    if projects:
        pages["projects.html"] = dict(page="projects", projects=projects)
    for name, ctx in pages.items():
        (OUT / name).write_text(env.get_template(name).render(**ctx), encoding="utf-8")

    # blog posts in _site/blog/, plus any images placed next to them in blog/
    (OUT / "blog").mkdir(exist_ok=True)
    for f in (ROOT / "blog").iterdir():
        if f.name.startswith("_"):
            continue
        if f.is_file() and f.suffix != ".md":
            shutil.copy(f, OUT / "blog" / f.name)
        elif f.is_dir():
            shutil.copytree(f, OUT / "blog" / f.name, dirs_exist_ok=True)
    post_tpl = env.get_template("post.html")
    for post in posts:
        (OUT / post["url"]).write_text(post_tpl.render(page="blog", post=post, root="../"),
                                       encoding="utf-8")

    # ------------------------------------------------------------ CVA
    summary = profile.get("cva_summary", "")
    n_chars = len(" ".join(summary.split()))
    if n_chars > CVA_MAX_SUMMARY:
        warnings.append(f"CVA Part B has {n_chars} characters (max. {CVA_MAX_SUMMARY})")
    cva_ctx = dict(
        c1=select_for_cva(pubs, "publications", limit),
        c2=select_for_cva(talks, "congresos", limit),
        c3=select_for_cva(projects, "proyectos", limit),
        c4=select_for_cva(transfer, "transferencia", limit),
        c5=training.get("tesis", []),
        c6=training.get("otra", []),
        en_curso=training.get("en_curso", []),
        summary_blocks=summary_blocks(summary),
        summary_chars=n_chars,
    )
    cva_html = env.get_template("cva.html").render(private={}, **cva_ctx)
    (OUT / "cva.html").write_text(cva_html, encoding="utf-8")

    if make_pdf:
        from weasyprint import HTML
        # Private full copy (DNI, birth date, phone) from data/private.yml, which is in
        # .gitignore: built only on your computer, into private/, never published.
        private = load("private", {}) or {}
        if any(private.values()):
            full = env.get_template("cva.html").render(private=private, **cva_ctx)
            PRIVATE.mkdir(exist_ok=True)
            HTML(string=full, base_url=str(OUT)).write_pdf(PRIVATE / env.globals["cva_file"].replace(".pdf", "_completo.pdf"))
            print(f"Private full CVA written to {PRIVATE}/ (not published)")
        doc = HTML(string=cva_html, base_url=str(OUT)).render()
        npages = len(doc.pages)
        doc.write_pdf(OUT / env.globals["cva_file"])
        print(f"CVA: {npages} page(s), Part B {n_chars} characters")
        if npages > CVA_MAX_PAGES:
            warnings.append(f"CVA is {npages} pages long (AEI max. {CVA_MAX_PAGES}); "
                            "mark fewer items with 'cva: true' or shorten Part B")

    print(f"Website written to {OUT}/ ({len(pages)} pages, {len(posts)} blog posts)")
    for w in warnings:
        print("  warning:", w)


if __name__ == "__main__":
    main()
