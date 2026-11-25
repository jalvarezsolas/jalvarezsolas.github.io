# Personal website + CVA — Jorge Alvarez-Solas

One set of data files feeds both the website and the downloadable CVA
(Currículum Vitae Abreviado, FECYT/AEI format). Edit the data, push to GitHub,
and both are rebuilt and published automatically.

## Where things live

| Edit this… | …to change |
|---|---|
| `data/publications.yml` | Publications page **and** CVA C.1 (`cva: true` = included, max. 10) |
| `data/congresos.yml` | Talks page **and** CVA C.2 |
| `data/proyectos.yml` | Projects page **and** CVA C.3 |
| `data/transferencia.yml` | CVA C.4 |
| `blog/*.md` | Blog posts, one file per post (see `blog/_HOW-TO-WRITE-A-POST.txt`); comments via giscus |
| `data/profile.yml` | Contact details, ORCID etc., CVA Part A and Part B (summary) |
| `templates/index.html` | Text of the Home page |
| `static/style.css` | Colours and layout |
| `photos/photo*.jpg` | Rotating profile photos (this folder stays private; run `build.py` locally to refresh the web copies in `static/files/photos/`) |
| `data/formacion.yml` | Theses page **and** CVA C.5 (defended theses) and C.6 (ongoing theses, other training) |
| `data/private.yml` | Private only (never uploaded): DNI, birth date, phone for `private/CVA_…_completo.pdf` |

`build.py` turns all of this into the finished site in `_site/` (never edit `_site/`,
it is regenerated every time). Values starting with `TODO` appear highlighted in yellow
and the build lists them, so you can see what is still missing.

The CVA follows the AEI instructions: Arial 11 pt, 2.5 cm side margins and 1.5 cm top and bottom,
Parts A, B and C, max. 10 items per Part C section, and the rule for papers with more than 8 authors
(first three, last, AC, total number and your position). The build warns if the CVA exceeds 4 pages
or Part B exceeds 5000 characters. Your DNI and date of birth are **not** in the public PDF: add them
by hand to the copy you submit.

## Adding a new paper (typical update)

Open `data/publications.yml`, copy an existing entry to the top and change it:

```yaml
- year: 2027
  title: "My new paper"
  authors: ["Alvarez-Solas, J.", "Montoya, M.", "Robinson, A."]
  journal: "The Cryosphere"
  volume: "21"
  pages: "1–20"
  doi: 10.5194/tc-21-1-2027
  cva: true
```

Then push (see below). A minute or two later the Publications page and the CVA PDF are updated.

## Preview on your own computer (optional)

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

```bash
.venv/bin/python build.py && python3 -m http.server 8000 --directory _site
```

Then open <http://localhost:8000>.

## Publishing on GitHub (one-time setup)

1. Create a GitHub account and a **public** repository named `jalvarezsolas.github.io`.
2. In the repository: **Settings → Pages → Build and deployment → Source: GitHub Actions**.
3. Push this folder to it (git commands below). The **Actions** tab shows the build; when it
   turns green the site is live at `https://jalvarezsolas.github.io`.

```bash
git add -A && git commit -m "Update website" && git push
```
