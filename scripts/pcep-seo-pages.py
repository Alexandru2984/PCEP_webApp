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

from contextlib import contextmanager
import ctypes
from datetime import date
import fcntl
import html
import json
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import tempfile

OUT_ROOT = pathlib.Path("/var/www/pcep/seo")
SITE = "https://pcep.micutu.com"
CONTAINER = "pcep_backend"
DOCKER = "/usr/bin/docker"
MIN_QUESTIONS = 50
MAX_QUESTIONS = 2_000
FORBIDDEN_ANSWER_FIELDS = {
    "answer",
    "correct",
    "correct_choice",
    "explanation",
    "is_correct",
}

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


class SeoPublishError(RuntimeError):
    """Refuse unsafe extraction or publication without changing the live tree."""


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
    objective = q.get("objective")
    metadata = " · ".join(
        value for value in (objective, q["difficulty"]) if value
    )
    parts = [
        '<article class="q">',
        f'<div class="qh"><span>Question {n}</span><span>{E(metadata)}</span></div>',
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


def extract_questions(runner=subprocess.run) -> list[dict]:
    try:
        raw = runner(
            [
                DOCKER,
                "exec",
                "--interactive",
                "--user",
                "appuser",
                CONTAINER,
                "python",
                "manage.py",
                "shell",
                "-c",
                EXTRACT,
            ],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except FileNotFoundError as error:
        raise SeoPublishError(f"docker lipseste: {DOCKER}") from error
    except subprocess.TimeoutExpired as error:
        raise SeoPublishError("extragerea intrebarilor a depasit 180 de secunde") from error
    if raw.returncode != 0:
        detail = raw.stderr.strip()[-400:] or raw.stdout.strip()[-400:]
        raise SeoPublishError(f"extragere esuata: {detail}")
    if "---JSON-START---" not in raw.stdout:
        raise SeoPublishError("marcatorul JSON lipseste din iesire")

    try:
        questions = json.loads(raw.stdout.split("---JSON-START---", 1)[1].strip())
    except json.JSONDecodeError as error:
        raise SeoPublishError("extragerea a returnat JSON invalid") from error
    validate_questions(questions)
    return questions


def validate_questions(questions) -> None:
    if not isinstance(questions, list):
        raise SeoPublishError("setul de intrebari nu este o lista")
    if not MIN_QUESTIONS <= len(questions) <= MAX_QUESTIONS:
        raise SeoPublishError(
            f"numar de intrebari in afara limitelor: {len(questions)} "
            f"(asteptat {MIN_QUESTIONS}-{MAX_QUESTIONS})"
        )

    module_names = {key for key, *_ in MODULES}
    seen_ids = set()
    seen_modules = set()
    for position, question in enumerate(questions, 1):
        if not isinstance(question, dict):
            raise SeoPublishError(f"intrebarea {position} nu este un obiect")
        forbidden = FORBIDDEN_ANSWER_FIELDS.intersection(question)
        if forbidden:
            raise SeoPublishError(
                f"intrebarea {position} contine campuri de raspuns interzise"
            )

        identifier = question.get("id")
        if type(identifier) is not int or identifier <= 0 or identifier in seen_ids:
            raise SeoPublishError(f"intrebarea {position} are un ID invalid sau duplicat")
        seen_ids.add(identifier)

        module = question.get("module")
        if module not in module_names:
            raise SeoPublishError(f"intrebarea {identifier} are un modul invalid")
        seen_modules.add(module)
        if question.get("difficulty") not in {"easy", "medium", "hard"}:
            raise SeoPublishError(f"intrebarea {identifier} are dificultate invalida")

        text = question.get("text")
        if not isinstance(text, str) or not text or len(text) > 10_000:
            raise SeoPublishError(f"intrebarea {identifier} are text invalid")
        code = question.get("code")
        if not isinstance(code, str) or len(code) > 50_000:
            raise SeoPublishError(f"intrebarea {identifier} are cod invalid")
        objective = question.get("objective")
        if objective is not None and (
            not isinstance(objective, str) or len(objective) > 32
        ):
            raise SeoPublishError(f"intrebarea {identifier} are obiectiv invalid")
        updated = question.get("updated")
        if not isinstance(updated, str):
            raise SeoPublishError(f"intrebarea {identifier} nu are data actualizarii")
        try:
            date.fromisoformat(updated)
        except ValueError as error:
            raise SeoPublishError(
                f"intrebarea {identifier} are data actualizarii invalida"
            ) from error

        choices = question.get("choices")
        if not isinstance(choices, list) or len(choices) != 4:
            raise SeoPublishError(f"intrebarea {identifier} nu are exact patru optiuni")
        choice_ids = set()
        for choice in choices:
            if not isinstance(choice, dict):
                raise SeoPublishError(f"intrebarea {identifier} are o optiune invalida")
            if FORBIDDEN_ANSWER_FIELDS.intersection(choice):
                raise SeoPublishError(
                    f"intrebarea {identifier} contine metadate de raspuns interzise"
                )
            choice_id = choice.get("id")
            if type(choice_id) is not int or choice_id <= 0 or choice_id in choice_ids:
                raise SeoPublishError(
                    f"intrebarea {identifier} are un ID de optiune invalid sau duplicat"
                )
            choice_ids.add(choice_id)
            choice_text = choice.get("text")
            if not isinstance(choice_text, str) or not choice_text or len(choice_text) > 10_000:
                raise SeoPublishError(f"intrebarea {identifier} are text de optiune invalid")

    if seen_modules != module_names:
        raise SeoPublishError("setul de intrebari nu acopera toate cele patru module")


def render_release(output_root: pathlib.Path, questions: list[dict]) -> int:
    validate_questions(questions)

    by_module: dict[str, list[dict]] = {}
    for q in questions:
        by_module.setdefault(q["module"], []).append(q)

    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "practice").mkdir(exist_ok=True)
    (output_root / "practice" / "style.css").write_text(CSS, encoding="utf-8")

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
        out = output_root / "practice" / slug
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
    (output_root / "practice" / "index.html").write_text(
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
    (output_root / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{entries}\n</urlset>\n",
        encoding="utf-8",
    )
    (output_root / "robots.txt").write_text(
        "User-agent: *\nAllow: /\n\n" f"Sitemap: {SITE}/sitemap.xml\n", encoding="utf-8"
    )
    return total


def validate_release(root: pathlib.Path) -> None:
    expected = {
        pathlib.Path("robots.txt"),
        pathlib.Path("sitemap.xml"),
        pathlib.Path("practice/index.html"),
        pathlib.Path("practice/style.css"),
        *(
            pathlib.Path("practice") / slug / "index.html"
            for _key, slug, _label, _blurb in MODULES
        ),
    }
    actual = set()
    for entry in root.rglob("*"):
        if entry.is_symlink():
            raise SeoPublishError("release-ul SEO nu poate contine legaturi simbolice")
        if entry.is_file():
            if not entry.stat().st_size:
                raise SeoPublishError(f"fisier SEO gol: {entry.relative_to(root)}")
            actual.add(entry.relative_to(root))
        elif not entry.is_dir():
            raise SeoPublishError(f"intrare SEO nesuportata: {entry.relative_to(root)}")
    if actual != expected:
        raise SeoPublishError("release-ul SEO nu contine exact fisierele asteptate")


def publication_target(target: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    target = pathlib.Path(os.path.abspath(target))
    parent = target.parent
    if parent.is_symlink() or not parent.is_dir() or parent.resolve() != parent:
        raise SeoPublishError("parintele directorului SEO trebuie sa fie un director real")
    parent_stat = parent.stat()
    if parent_stat.st_uid != os.geteuid() or parent_stat.st_mode & 0o022:
        raise SeoPublishError(
            "parintele directorului SEO trebuie sa apartina utilizatorului curent "
            "si sa nu fie editabil de grup sau alti utilizatori"
        )
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise SeoPublishError("directorul SEO live trebuie sa fie un director real")
    return target, parent


@contextmanager
def publication_lock(parent: pathlib.Path):
    lock_path = parent / ".seo-publish.lock"
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as error:
        raise SeoPublishError("nu pot deschide blocarea publicarii SEO") from error
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or metadata.st_mode & 0o077
        ):
            raise SeoPublishError("fisierul de blocare SEO are proprietati nesigure")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise SeoPublishError("o alta publicare SEO este deja activa") from error
        yield
    finally:
        os.close(descriptor)


def exchange_directories(first: pathlib.Path, second: pathlib.Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    rename = getattr(libc, "renameat2", None)
    if rename is None:
        raise SeoPublishError("schimbul atomic de directoare nu este disponibil")
    rename.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    rename.restype = ctypes.c_int
    if rename(-100, os.fsencode(first), -100, os.fsencode(second), 2):
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code))


def normalize_public_modes(root: pathlib.Path) -> None:
    root.chmod(0o755)
    for entry in root.rglob("*"):
        entry.chmod(0o755 if entry.is_dir() else 0o644)


def fsync_regular_file(path: pathlib.Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise SeoPublishError(f"intrarea SEO nu este fisier obisnuit: {path}")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def fsync_directory(path: pathlib.Path) -> None:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
    )
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise SeoPublishError(f"intrarea SEO nu este director: {path}")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def fsync_tree(root: pathlib.Path) -> None:
    directories = []
    for entry in (root, *root.rglob("*")):
        if entry.is_symlink():
            raise SeoPublishError("release-ul SEO s-a schimbat intr-o legatura simbolica")
        if entry.is_dir():
            directories.append(entry)
        elif entry.is_file():
            fsync_regular_file(entry)
        else:
            raise SeoPublishError(f"intrare SEO nesuportata la sincronizare: {entry}")
    for directory in sorted(
        directories,
        key=lambda entry: len(entry.parts),
        reverse=True,
    ):
        fsync_directory(directory)


def remove_tree_durably(path: pathlib.Path, parent: pathlib.Path) -> None:
    """Remove a failed SEO tree and commit its directory entry removal."""
    shutil.rmtree(path)
    fsync_directory(parent)


def publish_questions(questions: list[dict], target: pathlib.Path = OUT_ROOT) -> int:
    target, parent = publication_target(target)
    with publication_lock(parent):
        stage = pathlib.Path(tempfile.mkdtemp(prefix=f".{target.name}.release-", dir=parent))
        published = False
        try:
            total = render_release(stage, questions)
            normalize_public_modes(stage)
            validate_release(stage)
            fsync_tree(stage)
            if target.exists():
                exchange_directories(stage, target)
            else:
                os.replace(stage, target)
            published = True
            fsync_directory(parent)
            try:
                shutil.rmtree(stage)
            except OSError as error:
                print(
                    f"[pcep-seo] avertisment: versiunea precedenta ramane la {stage}: {error}",
                    file=sys.stderr,
                )
            else:
                try:
                    fsync_directory(parent)
                except OSError as error:
                    print(
                        "[pcep-seo] avertisment: stergerea versiunii precedente "
                        f"nu a putut fi sincronizata: {error}",
                        file=sys.stderr,
                    )
            return total
        except BaseException as error:
            if not published and stage.exists():
                try:
                    remove_tree_durably(stage, parent)
                except Exception as cleanup_error:
                    note = (
                        f"curatarea durabila a staging-ului SEO {stage} a esuat: "
                        f"{cleanup_error}"
                    )
                    error.add_note(note)
                    print(f"[pcep-seo] avertisment: {note}", file=sys.stderr)
            raise


def main() -> int:
    try:
        questions = extract_questions()
        total = publish_questions(questions)
    except (OSError, SeoPublishError) as error:
        print(f"[pcep-seo] publicare refuzata: {error}", file=sys.stderr)
        return 1

    print(
        f"[pcep-seo] scris {total} intrebari in {len(MODULES) + 1} pagini + sitemap"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
