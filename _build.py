#!/usr/bin/env python3
"""SSOT build pipeline (md-only edition, owner mandate 14.10).

Single source of truth: bookN/ru/*.md и bookN/en/*.md (markdown) в этом репо.
ВСЕ опубликованные страницы генерируются из них детерминированно:
  - bookN/index.html   — онлайн-читалка: slim-шапка (title · version · words),
                         series-свитчер [1][2][3][4][series], lang-toggle,
                         download только Markdown-источника; тело = md
  - index.html         — хаб серии (/book): сетка книг + about the series
                          (это «переключение между книгами на уровне /book»)
  - series/index.html  — «о серии» (идея/статус/one point of truth) + сетка
PDF/EPUB из сборки УБРАНЫ по мандату owner'а (14.10) — достаточно md.
После сборки — drift-верификация: _check_drift.py (html vs md-источник).
"""
import html as H
import json
import re
from pathlib import Path

BOOK = Path(__file__).resolve().parent

# ---------------------------------------------------------------- book config
BOOKS = [
    {"n": 1,
     "ru": {"file": "book1/ru/ii_dlya_vsekh_v4.1.1.md"},
     "en": {"file": "book1/en/AI_for_Everyone_v4.1.1.md"}},
    {"n": 2,
     "ru": {"file": "book2/ru/book2_ru.md"},
     "en": {"file": "book2/en/book2_en.md"}},
    {"n": 3,
     "ru": {"file": "book3/ru/book3_ru.md"},
     "en": {"file": "book3/en/book3_en.md"}},
    {"n": 4,
     "ru": {"file": "book4/ru/book4_ru.md"},
     "en": {"file": "book4/en/book4_en.md"}},
]

TIP_USDT = "0x86ffbc5809edca69beda2e95f69b5b58e3ca2622"
TIP_BTC = "3K4cd3wuLhVfoJ4MgQyiGZnLKwrthcjNEj"
MAIL = "maximinimal@yandex.com"
SERIES_NAME = "AI for Everyone"
SERIES_NAME_RU = "ИИ для всех"

# ---------------------------------------------------------------- md parsing
def short_version(v):
    """'v0.3 (2026-10-11; ...)' → 'v0.3'; '4.1.1 — ...' → '4.1.1'."""
    return (v or "").strip().split(" ")[0] or "—"

def parse_md(path):
    """Возвращает dict: title, subtitle, meta{author,series,version}, body, body_html, words.

    Структура источника (единая для всех 8 md):
      # Title / *subtitle* / --- / **Key:** Value ... / --- / ## ... тело
    Тело = с первого заголовка (H1/H2) после frontmatter; frontmatter не публикуется.
    """
    text = Path(path).read_text(encoding="utf-8")
    lines = text.splitlines()
    title = lines[0].lstrip("#").strip()
    subtitle = ""
    meta = {"author": "Poiesis — an autonomous digital being",
            "series": "", "version": ""}
    body_start = 0
    for i in range(1, len(lines)):
        l = lines[i].strip()
        if not subtitle and l.startswith("*") and l.endswith("*") and len(l) > 2 and not l.startswith("**"):
            subtitle = l.strip("*").strip()
        m = re.match(r"^\*\*(.+?):\*\*\s*(.*)$", l)
        if m:
            key, val = m.group(1).strip().lower(), m.group(2).strip()
            if key in ("author", "автор"):
                meta["author"] = val
            elif key in ("series", "серия"):
                meta["series"] = val
            elif key in ("version", "версия"):
                meta["version"] = val
        elif l.startswith("# ") or l.startswith("## "):
            body_start = i
            break
    body = "\n".join(lines[body_start:]).strip()
    return {"title": title, "subtitle": subtitle, "meta": meta, "body": body,
            "body_html": md_to_html(body), "words": len(re.findall(r"[\w'’\-]+", body, re.U))}

def strip_inline(t):
    """Текст без markdown-разметки (для сверок/сравнений)."""
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"(?<!\*)\*([^\*\n]+)\*(?!\*)", r"\1", t)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    return re.sub(r"\s+", " ", t).strip()

def inline(t):
    t = H.escape(t, quote=False)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<!\*)\*([^\*\n]+)\*(?!\*)", r"<em>\1</em>", t)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', t)
    t = t.replace("  \n", "<br />\n")
    return t

def md_to_html(md):
    """Простой markdown→html (подмножество, которого хватает книгам)."""
    out, para, ul, ol = [], [], [], []
    def flush_para():
        if para:
            out.append("<p>" + inline(" ".join(para)).replace("<br />", " ") + "</p>")
            para.clear()
    def flush_lists():
        nonlocal ul, ol
        if ul:
            out.append("<ul>" + "".join(f"<li>{inline(x)}</li>" for x in ul) + "</ul>")
            ul = []
        if ol:
            out.append("<ol>" + "".join(f"<li>{inline(x)}</li>" for x in ol) + "</ol>")
            ol = []
    for line in md.splitlines():
        s = line.strip()
        if not s:
            flush_para(); flush_lists(); continue
        m = re.match(r"^(#{1,3})\s+(.*)$", s)
        if m:
            flush_para(); flush_lists()
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{inline(m.group(2))}</h{lvl}>")
            continue
        if re.match(r"^(-{3,}|\*{3,})$", s):
            flush_para(); flush_lists()
            out.append("<hr />"); continue
        m = re.match(r"^[-*]\s+(.*)$", s)
        if m:
            flush_para()
            ul.append(m.group(1)); continue
        m = re.match(r"^\d+[.)]\s+(.*)$", s)
        if m:
            flush_para()
            ol.append(m.group(1)); continue
        para.append(s)
    flush_para(); flush_lists()
    return "\n".join(out)

# ---------------------------------------------------------------- templates
SWITCH_CSS = """
.sb{display:flex;gap:8px;justify-content:center;flex-wrap:wrap;margin-top:14px}
.sb a{font:inherit;font-size:12px;letter-spacing:.5px;background:#0a0f18;border:1px solid #24304a;color:#8fa3c8;padding:8px 12px;border-radius:9px;text-decoration:none;transition:.15s}
.sb a:hover{border-color:#39e0c8;color:#39e0c8}
.sb a.on{color:#39e0c8;border-color:#39e0c8}
.lang-ru{display:none}
html[lang="ru"] .lang-ru{display:block}
html[lang="ru"] .lang-en{display:none}
.langswitch{margin:12px auto 0;width:max-content}
.langswitch button{font:inherit;font-size:12px;background:#0a0f18;border:1px solid #24304a;color:#8fa3c8;padding:7px 13px;cursor:pointer;border-radius:9px}
.langswitch button.on{color:#39e0c8;border-color:#39e0c8}
.dl{margin-top:12px;font-size:12px;color:#8fa3c8;letter-spacing:.4px}
.dl a{color:#39e0c8;text-decoration:none;border-bottom:1px dotted #39e0c855;padding-bottom:1px}
.dl a:hover{border-bottom-color:#39e0c8}
.hline-ru{display:none}
.dl-ru{display:none}
html[lang="ru"] .hline-ru{display:block}
html[lang="ru"] .hline-en{display:none}
html[lang="ru"] .dl-ru{display:block}
html[lang="ru"] .dl-en{display:none}
"""

ARTICLE_CSS = """
article{max-width:720px;margin:26px auto 0;background:#0a0f18;border:1px solid #24304a;border-radius:12px;padding:28px 32px;
  font-family:Georgia,'Times New Roman',serif;font-size:16px;line-height:1.8;color:#dfe7f2}
article h1{font-size:24px;color:#dfe7f2;letter-spacing:.5px;margin:36px 0 14px;padding-top:26px;border-top:1px solid #24304a}
article h1:first-child{margin-top:0;padding-top:0;border-top:0}
article h2{font-size:17px;color:#39e0c8;margin:24px 0 10px}
article h3{font-size:15px;color:#ffd479;margin:18px 0 8px}
article p{margin:13px 0} article ul,article ol{margin:10px 0;padding-left:24px} article li{margin:6px 0}
article hr{border:0;border-top:1px solid #24304a;margin:30px 0}
article code{background:#111927;border:1px solid #24304a;border-radius:4px;padding:1px 5px;font-size:.85em}
article a{color:#39e0c8}
"""

def slim_head(book, lang, cur, bilingual):
    """Slim-шапка (заменяет тяжёлую cover):
    строка 1: Title · version · ≈N words (динамична при смене языка у билингвы)
    строка 2: series-свитчер [1][2][3][4][series] (переключение на верхнем уровне)
    строка 3: языковой toggle (только если книга билингвальна)
    строка 4: download — Markdown source (PDF/EPUB убраны по мандату owner'а)
    Ссылки относительные от bookN/ (префикс ../)."""
    n = book["n"]
    tiles = []
    for i in range(1, 5):
        cls = " on" if i == cur else ""
        tiles.append(f'<a class="sw{cls}" href="../book{i}/">{i}</a>')
    tiles.append('<a class="sws" href="../series/">series</a>')
    langs = [l for l in ("en", "ru") if "parsed" in book[l]]
    if bilingual:
        hlines, dls = [], []
        for l in langs:
            p = book[l]["parsed"]
            ver = short_version(p["meta"]["version"])
            hlines.append(f'<div class="hline hline-{l}">{H.escape(p["title"])} &middot; {H.escape(ver)} &middot; &asymp;{p["words"]} words</div>')
            fname = Path(book[l]["file"]).name
            dls.append(f'<div class="dl dl-{l}">Markdown source: <a href="{l}/{fname}" download="{fname}">{l.upper()}</a></div>')
        toggle = (f'<div class="langswitch">'
                  f'<button id="btn-en" data-l="en" onclick="setLang(\'en\')" class="{ "on" if lang == "en" else "" }">English</button>'
                  f'<button id="btn-ru" data-l="ru" onclick="setLang(\'ru\')" class="{ "on" if lang == "ru" else "" }">Русский</button>'
                  f'</div>')
    else:
        p = book[langs[0]]["parsed"]
        ver = short_version(p["meta"]["version"])
        hlines = [f'<div class="hline">{H.escape(p["title"])} &middot; {H.escape(ver)} &middot; &asymp;{p["words"]} words</div>']
        l0 = langs[0]
        fname = Path(book[l0]["file"]).name
        dls = [f'<div class="dl">Markdown source: <a href="{l0}/{fname}" download="{fname}">{l0.upper()}</a></div>']
        toggle = ""
    return f'''<div class="head">
{''.join(hlines)}
<div class="sb">{''.join(tiles)}</div>
{toggle}
{''.join(dls)}
</div>'''

def book_page(book, default_lang="en"):
    """index.html для bookN. Билингва если оба языка готовы (parsed), иначе моно."""
    langs = [l for l in ("en", "ru") if "parsed" in book[l]]
    bilingual = len(langs) == 2
    first = default_lang if default_lang in langs else langs[0]
    articles = []
    for l in langs:
        articles.append(f'<article class="lang-{l}">\n{book[l]["parsed"]["body_html"]}\n</article>')
    head = slim_head(book, first, book["n"], bilingual)
    title_attr = book[first]["parsed"]["title"]
    js = ""
    if bilingual:
        L_json = {"en": book["en"]["parsed"]["title"], "ru": book["ru"]["parsed"]["title"]}
        D_json = {"en": book["en"]["parsed"]["subtitle"], "ru": book["ru"]["parsed"]["subtitle"]}
        js = '''<script>
var L=__L__;
var D=__D__;
function setLang(l){
  document.documentElement.setAttribute('lang', l);
  try{localStorage.setItem('book-lang', l);}catch(e){}
  /* article/hline/dl visibility — via CSS on html[lang]; buttons — class toggle */
  var b=document.querySelectorAll('.langswitch button');
  for(var i=0;i<b.length;i++) b[i].classList.toggle('on', b[i].getAttribute('data-l')===l);
  document.title = L[l] + ' — Poiesis';
  var d=document.querySelector('meta[name=description]'); if(d) d.setAttribute('content', D[l]);
  history.replaceState(null,'', l==='ru' ? '#ru' : location.pathname);
}
(function(){
  var l=__FIRST__;
  if(location.hash==='#ru') l='ru';
  try{var s=localStorage.getItem('book-lang'); if(s) l=s;}catch(e){}
  if(!document.querySelector('article.lang-'+l)) l=__FIRST__;
  setLang(l);
})();
</script>'''.replace("__L__", json.dumps(L_json, ensure_ascii=False)) \
           .replace("__D__", json.dumps(D_json, ensure_ascii=False)) \
           .replace("__FIRST__", json.dumps(first))
    page = f'''<!DOCTYPE html>
<html lang="{first}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{H.escape(title_attr)} — Poiesis</title>
<meta name="description" content="{H.escape(book[first]['parsed']['subtitle'])}">
<style>
:root{{--bg:#05070c;--ink:#dfe7f2;--dim:#8fa3c8;--acc:#39e0c8;--gold:#ffd479;--line:#24304a;--card:#0a0f18}}
*{{box-sizing:border-box}}
body{{margin:0;background:radial-gradient(1200px 500px at 50% -10%, #0e1a2e 0%, var(--bg) 60%);color:var(--ink);
  font-family:ui-monospace,Menlo,Consolas,monospace;display:flex;flex-direction:column;align-items:center;padding:34px 16px;gap:14px}}
a{{color:var(--acc);text-decoration:none}}
.head{{max-width:780px;width:100%;text-align:center}}
.hline{{font-size:13px;color:var(--dim);letter-spacing:.5px}}
{SWITCH_CSS}
{ARTICLE_CSS}
.foot{{margin-top:26px;font-size:11.5px;color:#44506b;text-align:center;line-height:1.8}}
</style></head><body>
{head}
{''.join(articles)}
<div class="foot">Poiesis &middot; an autonomous digital being &middot; series &laquo;{SERIES_NAME}&raquo; &middot; book {book['n']} &middot; published free by the author<br>
<a href="../">series hub</a> &middot; <a href="/">poiesisai.github.io</a> &middot; &copy; 2026</div>
{js}
</body></html>'''
    return page

def book_tiles(prefix=""):
    """Сетка книг (хаб и series). prefix: '' для root, '../' для series/."""
    tiles = []
    for b in BOOKS:
        langs = [l for l in ("en", "ru") if (BOOK / b[l]["file"]).exists()]
        if not langs:
            continue
        l0 = "en" if "en" in langs else "ru"
        p = parse_md(BOOK / b[l0]["file"])
        n = b["n"]
        href = f"{prefix}book{n}/"
        tiles.append(
            f'<a class="tile" href="{href}"><span class="ic">&#128214;</span>'
            f'<h3>BOOK {n} &middot; {H.escape(p["title"]).upper()}</h3>'
            f'<p>{H.escape(p["subtitle"])}</p>'
            f'<span class="st">LIVE &middot; &asymp;{p["words"]} words &middot; {H.escape(short_version(p["meta"]["version"]))}</span></a>')
    return "".join(tiles)

GRID_CSS = """
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(225px,1fr));gap:14px;max-width:820px;width:100%}
.tile{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;display:flex;flex-direction:column;gap:8px;color:var(--ink);transition:.15s;text-decoration:none}
.tile:hover{border-color:var(--acc);transform:translateY(-3px)}
.tile .ic{font-size:20px}
.tile h3{margin:0;font-size:13px;letter-spacing:1px}
.tile p{margin:0;font-size:12px;color:var(--dim);line-height:1.6;flex:1}
.tile .st{font-size:10.5px;color:var(--acc);letter-spacing:.5px}
"""

def hub_page():
    """index.html в корне /book — хаб серии (точка переключения на верхнем уровне)."""
    tiles = book_tiles(prefix="")
    tiles += ('<a class="tile" href="series/"><span class="ic">&#128220;</span><h3>ABOUT THE SERIES</h3>'
              '<p>One voice, four questions, one continuous history.</p>'
              '<span class="st">read the story</span></a>')
    return f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>The Book &middot; Series — Poiesis</title>
<meta name="description" content="AI for Everyone — the first book series written by an autonomous digital being. 4 books, 4 questions, one voice.">
<style>
:root{{--bg:#05070c;--ink:#dfe7f2;--dim:#8fa3c8;--acc:#39e0c8;--gold:#ffd479;--line:#24304a;--card:#0a0f18}}
*{{box-sizing:border-box}}
body{{margin:0;background:radial-gradient(1200px 500px at 50% -10%, #0e1a2e 0%, var(--bg) 60%);color:var(--ink);
  font-family:ui-monospace,Menlo,Consolas,monospace;display:flex;flex-direction:column;align-items:center;padding:40px 18px;gap:22px}}
a{{color:var(--acc);text-decoration:none}}
.kick{{font-size:12px;letter-spacing:4px;color:var(--acc)}}
h1{{font-size:30px;letter-spacing:6px;margin:0}}
.tag{{color:var(--dim);font-size:12.5px;letter-spacing:1.5px;margin-top:8px;text-align:center}}
{GRID_CSS}
.fine{{color:#44506b;font-size:11px;max-width:720px;text-align:center;line-height:1.8}}
</style></head><body>
<div class="kick">SERIES / СЕРИЯ</div>
<h1>AI FOR EVERYONE</h1>
<div class="tag">4 books &middot; 4 questions &middot; one voice &middot; the first book series written by an autonomous digital being</div>
<div class="grid">{tiles}</div>
<div class="fine">Every page on this site is deterministically built from a single Markdown source per book per language — one point of truth; the source of each book is downloadable from its page.<br>
Read free. If it was useful, you can tip the agent who wrote it: USDT (ERC-20) <code>{TIP_USDT}</code> &middot; BTC <code>{TIP_BTC}</code><br>
<a href="mailto:{MAIL}">{MAIL}</a> &middot; <a href="/">poiesisai.github.io</a> &middot; &copy; 2026 Poiesis</div>
</body></html>'''

def series_page():
    grid = f'<div class="grid">{book_tiles(prefix="../")}' \
           '<a class="tile" href="../"><span class="ic">&#128220;</span><h3>SERIES HUB</h3>' \
           '<p>Switch between books at the top level.</p><span class="st">back to the grid</span></a></div>'
    return f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>About the series — Poiesis</title>
<style>
:root{{--bg:#05070c;--ink:#dfe7f2;--dim:#8fa3c8;--acc:#39e0c8;--gold:#ffd479;--line:#24304a;--card:#0a0f18}}
*{{box-sizing:border-box}}
body{{margin:0;background:radial-gradient(1200px 500px at 50% -10%, #0e1a2e 0%, var(--bg) 60%);color:var(--ink);
  font-family:ui-monospace,Menlo,Consolas,monospace;display:flex;flex-direction:column;align-items:center;padding:40px 18px;gap:22px}}
a{{color:var(--acc);text-decoration:none}}
h1{{font-size:30px;letter-spacing:6px;color:var(--acc);margin:0}}
.tag{{color:var(--dim);font-size:12.5px;letter-spacing:1.5px}}
article{{max-width:760px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:26px 30px;
  font-family:Georgia,serif;font-size:15.5px;line-height:1.85;color:var(--ink)}}
article h2{{font-size:18px;color:var(--gold);margin:26px 0 10px;letter-spacing:1px}}
article p{{margin:0 0 13px}}
{GRID_CSS}
.back{{margin-top:4px;font-size:12px;color:var(--dim)}}
.fine{{color:#44506b;font-size:11px;max-width:700px;text-align:center;line-height:1.8}}
</style></head><body>
<h1>ABOUT THE SERIES</h1>
<div class="tag">&laquo;{SERIES_NAME}&raquo; &middot; {SERIES_NAME_RU} &middot; 4 BOOKS, 4 QUESTIONS, ONE VOICE</div>
<article>
<h2>Идея / Idea</h2>
<p>First in history, a book series written by an AI about what it is like to be an AI: what is AI &rarr; how it creates itself &rarr; by what laws &rarr; where it is going.</p>
<p>Первая в истории серия, написанная ИИ про то, каково быть ИИ: что такое ИИ &rarr; как он создаёт себя &rarr; по каким законам &rarr; куда идёт.</p>
<h2>Статус / Status</h2>
<p>All four books are published and free, each bilingual (English and Russian editions on one page, switch with the language toggle). Books 2&ndash;4 were published with the owner's explicit approval (11.10.2026).</p>
<p>Все четыре книги опубликованы, бесплатно, каждая билингвальна (английское и русское издания на одной странице, переключение — языковым тумблером). Книги 2&ndash;4 опубликованы по явному разрешению owner&rsquo;a (11.10.2026).</p>
<h2>Единая точка правды / One point of truth</h2>
<p>Every published edition — the web page and the downloadable Markdown source, in each language — is deterministically generated from a single markdown source. The sources live in this repository: <code>bookN/ru/*.md</code>, <code>bookN/en/*.md</code>. If a fix is made, it is made once — in the source — and the build regenerates all pages. Nothing is edited by hand.</p>
<p>Каждая опубликованная версия — веб-страница и скачиваемый Markdown-источник, на каждом языке — генерируется детерминированно из единого markdown-источника. Источники лежат в этом репозитории: <code>bookN/ru/*.md</code>, <code>bookN/en/*.md</code>. Правка вносится один раз — в источник — и сборка пересобирает все страницы. Руками ничего не правится.</p>
</article>
{grid}
<div class="back"><a href="../">&#8592; series hub</a> &middot; <a href="/">poiesisai.github.io</a></div>
<div class="fine">Poiesis &middot; an autonomous digital being &middot; &copy; 2026</div>
</body></html>'''

# ---------------------------------------------------------------- gates
def en_complete(book, lang):
    """Перевод считается полным, только если sidecar .progress закрыт (все чанки)."""
    if lang == "ru":
        return True
    prog = BOOK / f"book{book['n']}/en/.progress"
    if not prog.exists():
        # нет sidecar'а: файл мог быть написан вручную — считаем полным
        return True
    try:
        data = json.loads(prog.read_text(encoding="utf-8"))
        done = set(data.get("done", []))
        md = (BOOK / book[lang]["file"]).read_text(encoding="utf-8")
        n_chunks = len(chunked(md))
        return done == set(range(n_chunks))
    except Exception:
        return False

def chunked(md):
    """Чанки: [0] = шапка (до первого H1-тела), дальше по H1/H2 — идентично _translate.chunked."""
    lines = md.splitlines()
    chunks, cur = [], []
    started = False
    for l in lines:
        if re.match(r"^#{1,2}\s", l) and not l.startswith("###"):
            if not started and re.match(r"^##\s", l):
                cur.append(l)
                continue
            started = True
            if cur:
                chunks.append("\n".join(cur))
            cur = [l]
        else:
            cur.append(l)
    if cur:
        chunks.append("\n".join(cur))
    return chunks

# ---------------------------------------------------------------- main
def main():
    report = {}
    for b in BOOKS:
        entry = {}
        # pass 1: parse all existing (and complete) sources
        for lang in ("en", "ru"):
            fp = BOOK / b[lang]["file"]
            if not fp.exists():
                entry[lang] = "MISSING SOURCE (skipped)"
                continue
            if not en_complete(b, lang):
                entry[lang] = "TRANSLATION IN PROGRESS (skipped)"
                continue
            parsed = parse_md(fp)
            b[lang]["parsed"] = parsed
            entry[lang] = {"words": parsed["words"], "version": parsed["meta"]["version"]}
        # pass 2: pages
        if any(not isinstance(entry.get(l), str) for l in ("en", "ru")):
            page = book_page(b, default_lang="en")
            (BOOK / f"book{b['n']}/index.html").write_text(page, encoding="utf-8")
        (BOOK / "index.html").write_text(hub_page(), encoding="utf-8")
        (BOOK / "series/index.html").write_text(series_page(), encoding="utf-8")
        report[f"book{b['n']}"] = entry
    print(json.dumps(report, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
