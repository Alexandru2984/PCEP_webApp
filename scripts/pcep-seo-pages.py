#!/usr/bin/env python3
"""Render crawlable practice pages for pcep.micutu.com.

Why this exists
---------------
The quiz is a React SPA: nginx serves a 4 KB shell and every question is
fetched from the API and rendered client-side.  Search Console showed ~144
impressions across fourteen PCEP queries ("pcep exam questions", "pcep practice
test", …) and **zero clicks**, at an average position around 30.  The title and
meta description are already well targeted, so the metadata is not the problem:
there is simply nothing in the HTML for Google to rank.  Meanwhile the database
holds 301 questions that no crawler can see. Correct answers stay behind submission.

This script reads those questions and writes plain, self-contained HTML — one
page per syllabus module plus a hub — so the content exists server-side.  The
SPA is untouched; these pages live beside it under /practice/ and link back to
it, because the interactive parts (instant feedback, the in-browser Python
runner, progress tracking) are still the reason to use the app.

It runs on the host rather than inside the container so the backend image does
not need rebuilding for a presentation change.  A systemd timer re-runs it, so
newly added questions appear without anyone remembering to regenerate.
"""

from __future__ import annotations

import html
import json
import pathlib
import subprocess
import sys

OUT_ROOT = pathlib.Path("/var/www/pcep/seo")
SITE = "https://pcep.micutu.com"
CONTAINER = "pcep_backend"

# Slugs carry the words people actually search for, not "module3".
MODULES: list[tuple[str, str, str, str]] = [
    ("module1", "module-1-fundamentals", "Module 1 — Fundamentals",
     "Python basics: literals, operators, variables, comments and the print() function."),
    ("module2", "module-2-control-flow", "Module 2 — Control Flow",
     "Conditionals, loops, logical and bitwise operators, and controlling execution order."),
    ("module3", "module-3-data-collections", "Module 3 — Data Collections",
     "Lists, tuples, dictionaries and strings, including slicing, methods and mutability."),
    ("module4", "module-4-functions-exceptions", "Module 4 — Functions & Exceptions",
     "Defining and calling functions, scopes, argument passing, and handling exceptions."),
]

# Extracted inside the container: it owns the ORM, the settings and the DB
# credentials, so nothing here needs to know about Postgres.
EXTRACT = r"""
import json
from quiz.models import Question
from quiz.serializers import QuestionSerializer
out = []
for q in Question.objects.prefetch_related("choices").order_by("id"):
    public = dict(QuestionSerializer(q).data)
    public["updated"] = q.updated_at.date().isoformat()
    public["code"] = public.pop("code_snippet")
    out.append(public)
print("---JSON-START---")
print(json.dumps(out))
"""

CSS = """\
:root{--bg:#f8fafc;--panel:#fff;--ink:#0f172a;--muted:#64748b;--line:#e2e8f0;
--accent:#2563eb;--ok:#15803d;--code:#f1f5f9}
@media(prefers-color-scheme:dark){:root{--bg:#0f172a;--panel:#161e2e;--ink:#e2e8f0;
--muted:#94a3b8;--line:#263349;--accent:#60a5fa;--ok:#4ade80;--code:#1c2536}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.65 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
-webkit-font-smoothing:antialiased}
.wrap{max-width:820px;margin:0 auto;padding:44px 20px 72px}
a{color:var(--accent)}
nav.crumbs{font-size:.88rem;color:var(--muted);margin-bottom:18px}
nav.crumbs a{text-decoration:none}
h1{font-size:2rem;line-height:1.2;letter-spacing:-.02em;margin:0 0 12px}
.lede{font-size:1.08rem;color:var(--muted);margin:0 0 26px}
h2{font-size:1.2rem;margin:34px 0 12px}
.cta{display:inline-block;background:var(--accent);color:#fff;text-decoration:none;
padding:11px 20px;border-radius:9px;font-weight:550;margin:6px 8px 6px 0}
.cta.ghost{background:transparent;color:var(--ink);border:1px solid var(--line)}
.mods{list-style:none;padding:0;margin:0}
.mods li{background:var(--panel);border:1px solid var(--line);border-radius:12px;
padding:16px 18px;margin:0 0 12px}
.mods a{font-weight:600;text-decoration:none;font-size:1.05rem}
.mods p{margin:6px 0 0;color:var(--muted);font-size:.95rem}
.q{background:var(--panel);border:1px solid var(--line);border-radius:12px;
padding:20px 22px;margin:0 0 16px}
.qh{display:flex;justify-content:space-between;gap:12px;align-items:baseline;
font-size:.8rem;color:var(--muted);margin-bottom:8px;
font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.qt{font-weight:600;margin:0 0 12px}
pre{background:var(--code);border:1px solid var(--line);border-radius:8px;
padding:12px 14px;overflow-x:auto;margin:0 0 14px;
font:13px/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
ol.ch{margin:0;padding-left:22px}
ol.ch li{margin:0 0 12px}
footer{margin-top:44px;padding-top:20px;border-top:1px solid var(--line);
font-size:.9rem;color:var(--muted)}
@media(max-width:520px){.wrap{padding:30px 16px 56px}h1{font-size:1.55rem}}
"""

E = html.escape


def page(title: str, description: str, canonical: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(title)}</title>
<meta name="description" content="{E(description)}">
<link rel="canonical" href="{E(canonical)}">
<link rel="stylesheet" href="/practice/style.css">
</head>
<body>
<div class="wrap">
{body}
<footer>
  Practice questions written for the PCEP-30-02 syllabus. Not affiliated with the
  Python Institute, and not exam material — these are original questions for
  study. Part of <a href="https://micutu.com/">micutu.com</a>.
</footer>
</div>
</body>
</html>
"""


def render_question(n: int, q: dict) -> str:
    parts = [
        '<article class="q">',
        f'<div class="qh"><span>Question {n}</span><span>{E(q["difficulty"])}</span></div>',
        f'<p class="qt">{E(q["text"])}</p>',
    ]
    if q["code"].strip():
        parts.append(f"<pre><code>{E(q['code'])}</code></pre>")
    parts.append('<ol class="ch">')
    for c in q["choices"]:
        # Render only public option text, even if a caller supplies extra fields.
        parts.append(f"<li>{E(c['text'])}")
        parts.append("</li>")
    parts.append("</ol></article>")
    return "\n".join(parts)


def main() -> int:
    raw = subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "python", "manage.py", "shell", "-c", EXTRACT],
        capture_output=True, text=True, timeout=180,
    )
    if raw.returncode != 0:
        print(f"[pcep-seo] extragere esuata: {raw.stderr[:400]}", file=sys.stderr)
        return 1
    if "---JSON-START---" not in raw.stdout:
        print("[pcep-seo] marcatorul JSON lipseste din iesire", file=sys.stderr)
        return 1

    questions = json.loads(raw.stdout.split("---JSON-START---", 1)[1].strip())
    if len(questions) < 50:
        # A partial read would silently publish a thin page, which is worse for
        # ranking than publishing nothing. Fail instead.
        print(f"[pcep-seo] doar {len(questions)} intrebari - refuz sa scriu", file=sys.stderr)
        return 1

    by_module: dict[str, list[dict]] = {}
    for q in questions:
        by_module.setdefault(q["module"], []).append(q)

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUT_ROOT / "practice").mkdir(exist_ok=True)
    (OUT_ROOT / "practice" / "style.css").write_text(CSS, encoding="utf-8")

    urls = [f"{SITE}/practice/"]

    for key, slug, label, blurb in MODULES:
        qs = by_module.get(key, [])
        if not qs:
            continue
        body = [
            f'<nav class="crumbs"><a href="/">PCEP Quiz</a> › '
            f'<a href="/practice/">Practice questions</a> › {E(label)}</nav>',
            f"<h1>{E(label)} — PCEP practice questions</h1>",
            f'<p class="lede">{E(blurb)} {len(qs)} practice questions. '
            "Submit answers in the interactive quiz to receive explanations.</p>",
            '<p><a class="cta" href="/">Take this module as a timed quiz</a>'
            '<a class="cta ghost" href="/practice/">All modules</a></p>',
            "<h2>Questions</h2>",
        ]
        body += [render_question(i, q) for i, q in enumerate(qs, 1)]
        body.append(
            '<p style="margin-top:28px"><a class="cta" href="/">Practice interactively '
            "— instant feedback and a built-in Python runner</a></p>"
        )
        out = OUT_ROOT / "practice" / slug
        out.mkdir(exist_ok=True)
        (out / "index.html").write_text(
            page(
                f"{label} — PCEP Practice Questions",
                f"{len(qs)} free PCEP practice questions on {label.split('—')[1].strip().lower()}, "
                "with interactive answer submission and detailed feedback.",
                f"{SITE}/practice/{slug}/",
                "\n".join(body),
            ),
            encoding="utf-8",
        )
        urls.append(f"{SITE}/practice/{slug}/")

    total = sum(len(by_module.get(k, [])) for k, _, _, _ in MODULES)
    with_code = sum(1 for q in questions if q["code"].strip())
    diff: dict[str, int] = {}
    for q in questions:
        diff[q["difficulty"]] = diff.get(q["difficulty"], 0) + 1

    # Never publish answer keys or explanations in static pages.
    # Everything stated here is derived from the question set itself. Exam
    # trivia (question counts, time limits, pass marks) is deliberately left
    # out: it changes between syllabus revisions, and a page that states it
    # wrongly is worse than one that stays quiet about it.
    hub = [
        '<nav class="crumbs"><a href="/">PCEP Quiz</a> › Practice questions</nav>',
        "<h1>PCEP practice questions</h1>",
        f'<p class="lede">{total} free practice questions for the PCEP-30-02 syllabus '
        "(Certified Entry-Level Python Programmer), grouped by module. Every question "
        "keeps answers private until you submit in the interactive quiz.</p>",
        '<p><a class="cta" href="/">Start a timed practice quiz</a></p>',
        "<h2>Browse by module</h2>",
        '<ul class="mods">',
    ]
    for key, slug, label, blurb in MODULES:
        n = len(by_module.get(key, []))
        if not n:
            continue
        hub.append(
            f'<li><a href="/practice/{slug}/">{E(label)}</a> — {n} questions'
            f"<p>{E(blurb)}</p></li>"
        )
    hub.append("</ul>")

    order = [("easy", "Easy"), ("medium", "Medium"), ("hard", "Hard")]
    spread = ", ".join(f"{diff[k]} {lbl.lower()}" for k, lbl in order if diff.get(k))
    hub += [
        "<h2>What these questions look like</h2>",
        f"<p>The set spans three difficulty levels — {E(spread)} — so the same "
        "topic appears both as a direct recall question and as a trickier case "
        f"with an edge condition. {with_code} of the {total} questions include a "
        "Python snippet you have to read and evaluate, which is how most of the "
        "harder syllabus points are actually tested: not &ldquo;what does this "
        "keyword mean&rdquo; but &ldquo;what does this program print&rdquo;.</p>",
        "<p>Each option carries its own explanation rather than a single note on "
        "the correct answer. Knowing why the three wrong options are wrong is what "
        "separates recognising an answer from understanding it — and the wrong "
        "options here are built from the mistakes people actually make: integer "
        "versus true division, off-by-one slicing, mutable default arguments, "
        "shadowed built-ins.</p>",
        "<h2>How to use them</h2>",
        "<p>Read a module page to preview the topics and consider each option. "
        "To submit your answers and review explanations, switch to the "
        '<a href="/">interactive quiz</a>: it draws questions at random, times '
        "you, tracks which ones you keep getting wrong, and includes a Python "
        "runner so you can change a snippet and see what happens instead of "
        "taking the explanation on trust.</p>",
    ]
    (OUT_ROOT / "practice" / "index.html").write_text(
        page(
            "PCEP Practice Questions — all four modules",
            f"{total} free PCEP practice questions with interactive feedback, "
            "covering all four modules of the PCEP-30-02 syllabus.",
            f"{SITE}/practice/",
            "\n".join(hub),
        ),
        encoding="utf-8",
    )

    # A real sitemap: /sitemap.xml currently falls through to the SPA shell, so
    # a crawler asking for it gets HTML and learns nothing.
    #
    # lastmod comes from the newest Question.updated_at behind each page, never
    # from the generation date. This script re-runs weekly whether or not any
    # question changed; stamping "today" every time would teach crawlers the
    # dates mean nothing, at which point they stop being read at all.
    def newest(qs: list[dict]) -> str:
        return max(q["updated"] for q in qs)

    site_mod = newest(questions)
    lastmods = {f"{SITE}/": site_mod, f"{SITE}/practice/": site_mod}
    for key, slug, _, _ in MODULES:
        qs = by_module.get(key, [])
        if qs:
            lastmods[f"{SITE}/practice/{slug}/"] = newest(qs)

    entries = "\n".join(
        f"  <url><loc>{u}</loc><lastmod>{lastmods[u]}</lastmod></url>"
        for u in [f"{SITE}/"] + urls
    )
    (OUT_ROOT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{entries}\n</urlset>\n",
        encoding="utf-8",
    )
    (OUT_ROOT / "robots.txt").write_text(
        "User-agent: *\nAllow: /\n\n" f"Sitemap: {SITE}/sitemap.xml\n", encoding="utf-8"
    )

    print(f"[pcep-seo] scris {total} intrebari in {len(urls)} pagini + sitemap")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
