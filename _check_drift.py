#!/usr/bin/env python3
"""SSOT drift-check (md-only edition).

Истина (single source of truth): bookN/ru/*.md и bookN/en/*.md в этом репо.
Публикация: bookN/index.html (article lang-ru / lang-en), index.html (хаб),
series/index.html.

Что проверяется (парсер НЕДВИСИМ от _build.py — сверяет md-источник против html):
  1. Тело: заголовки MD == заголовки article (порядок и состав, lenient-нормализация).
  2. Каждый MD-абзац/элемент списка (нормализованный) присутствует в article.
  3. Обратное: в article нет «мёртвого» контента, которого нет в MD.
  4. Slim-шапка: hline несёт title + version + words; свитчер 1-4+series (активная = книга);
     билингва — два article + lang-toggle.
  5. md-only: на любой странице НЕТ ссылок на pdf/epub; dl-ссылки — только на существующие .md.
  6. Хаб: 4 плитки книг + series; series: 4 плитки + хаб + «единая точка правды».
Выход: JSON-отчёт + DRIFT-CLEAN/DRIFT-FOUND, exit 0/1.
"""
import json, re, sys
from pathlib import Path
from html.parser import HTMLParser

BOOK = Path(__file__).resolve().parent

BOOKS = [
    {"n": 1, "ru": "book1/ru/ii_dlya_vsekh_v4.1.1.md", "en": "book1/en/AI_for_Everyone_v4.1.1.md"},
    {"n": 2, "ru": "book2/ru/book2_ru.md", "en": "book2/en/book2_en.md"},
    {"n": 3, "ru": "book3/ru/book3_ru.md", "en": "book3/en/book3_en.md"},
    {"n": 4, "ru": "book4/ru/book4_ru.md", "en": "book4/en/book4_en.md"},
]

# ---------------------------------------------------------------- md side
def md_body(md):
    """Тело = с первого заголовка после title-строки (frontmatter не публикуется)."""
    lines = md.splitlines()
    for i in range(1, len(lines)):
        s = lines[i].strip()
        if s.startswith("#") and re.match(r"^#{1,3}\s", s):
            return "\n".join(lines[i:]).strip()
    return ""

def strip_md(t):
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"(?<!\*)\*([^\*\n]+)\*(?!\*)", r"\1", t)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    return re.sub(r"\s+", " ", t).strip()

def md_heads(body):
    out = []
    for line in body.splitlines():
        m = re.match(r"^(#{1,3})\s+(.*)$", line)
        if m:
            out.append(re.sub(r"[«»:]", "", strip_md(m.group(2))).lower())
    return out

def md_blocks(body):
    """Блоки → абзацы. Обычный блок = 1 абзац. List-блок = по элементу на строку.
    Смешанный блок (вводный абзац, ПРЯМО перед списком, без пустой строки) =
    абзац из строк до первого элемента + сами элементы."""
    out = []
    for block in re.split(r"\n\s*\n", body):
        b = block.strip()
        if not b or b.startswith("#") or b.startswith("---") or b.startswith("|") or b.startswith("```"):
            continue
        lines = b.splitlines()
        pre = []
        first_item = len(lines)
        for i, l in enumerate(lines):
            s = l.strip()
            if re.match(r"^([-*]|\d+[.)])\s", s):
                first_item = i
                break
            if s:
                pre.append(s)
        if pre:
            t = strip_md(" ".join(pre))
            if len(t) > 30:
                out.append(t)
        for l in lines[first_item:]:
            s = l.strip()
            m = re.match(r"^([-*]|\d+[.)])\s+(.*)$", s)
            if m:
                t = strip_md(m.group(2))
                if len(t) > 30:
                    out.append(t)
            elif s:
                t = strip_md(s)
                if len(t) > 30:
                    out.append(t)
    return out

# ---------------------------------------------------------------- html side
class ArticleSplitter(HTMLParser):
    """Разбирает страницу на article.lang-ru / article.lang-en; внутри — h1-h3, p/li-текст."""
    def __init__(self):
        super().__init__()
        self.sections = {}
        self._cur = None
        self._skip = 0
        self._buf = None
        self._hbuf = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class", "").split()
        if tag == "article":
            if "lang-ru" in cls:
                self._cur = "ru"
            elif "lang-en" in cls:
                self._cur = "en"
            else:
                self._cur = "plain"
            self.sections.setdefault(self._cur, {"headings": [], "paras": []})
        if self._cur is not None:
            if tag in ("style", "script"):
                self._skip += 1
            elif tag in ("h1", "h2", "h3"):
                self._hbuf = [tag, ""]
            elif tag in ("p", "li") and self._skip == 0:
                self._buf = []

    def handle_endtag(self, tag):
        if self._cur is None:
            return
        if tag in ("style", "script"):
            self._skip = max(0, self._skip - 1)
        elif tag in ("h1", "h2", "h3") and self._hbuf is not None:
            self.sections[self._cur]["headings"].append(
                re.sub(r"[«»:]", "", self._hbuf[1].strip()).lower())
            self._hbuf = None
        elif tag in ("p", "li") and self._buf is not None:
            t = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            self._buf = None
            if t:
                self.sections[self._cur]["paras"].append(t)

    def handle_data(self, data):
        if self._cur is None or self._skip:
            return
        if self._hbuf is not None:
            self._hbuf[1] += data
        elif self._buf is not None:
            self._buf.append(data)

def norm(s):
    return re.sub(r"\s+", " ", s).strip()

def hline_of(html_text, lang="en"):
    """Текст hline для языка: у билингвы — hline-{lang}, у моно — hline."""
    for pat in (rf'<div class="hline hline-{lang}">(.*?)</div>',
                rf'<div class="hline (?:hline-)?{lang}">(.*?)</div>',
                r'<div class="hline">(.*?)</div>'):
        m = re.search(pat, html_text, re.S)
        if m:
            return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(1)))
    return ""

def word_count(body):
    return len(re.findall(r"[\w'’\-]+", body, re.U))

# ---------------------------------------------------------------- checks
def check_section(md_p, html_p, lang):
    """Сверка md-тела с article.lang-<lang>."""
    md = md_p.read_text(encoding="utf-8")
    html = html_p.read_text(encoding="utf-8")
    body = md_body(md)
    p = ArticleSplitter()
    p.feed(html)
    sec = p.sections.get(lang)
    if sec is None:
        return {"error": f"article.lang-{lang} not found", "clean": False}
    mh, hseq = md_heads(body), sec["headings"]
    heads_ok = mh == hseq
    missing_h = [x for x in mh if x not in set(hseq)]
    mp = md_blocks(body)
    html_par = " || ".join(sec["paras"])
    missing_p = [x for x in mp if norm(x) not in html_par and norm(x)[:80] not in html_par and norm(x)[:40] not in html_par]
    extra_p = [hp for hp in sec["paras"] if len(hp) > 80 and
               not any(norm(x)[:60] in norm(hp) or norm(hp)[:60] in norm(x) for x in mp)]
    r = {
        "heads_md": len(mh), "heads_html": len(hseq),
        "heads_exact_match": heads_ok, "heads_missing": missing_h[:5],
        "paras_md": len(mp), "paras_html": len(sec["paras"]),
        "md_paras_missing": missing_p[:5], "md_paras_missing_count": len(missing_p),
        "html_paras_extra": extra_p[:5], "html_paras_extra_count": len(extra_p),
    }
    r["clean"] = heads_ok and not missing_h and not missing_p
    return r

def check_book(n):
    b = next(x for x in BOOKS if x["n"] == n)
    html_p = BOOK / f"book{n}/index.html"
    html = html_p.read_text(encoding="utf-8")
    rep = {"name": f"book{n}", "issues": []}
    # 5. md-only: никаких pdf/epub на странице
    banned = re.findall(r'href="([^"]+\.(?:pdf|epub|mp3))"', html)
    if banned:
        rep["issues"].append(f"banned format links: {banned}")
    # dl-ссылки — только .md и файлы существуют
    dls = re.findall(r'<div class="dl">.*?</div>', html, re.S)
    dl_hrefs = re.findall(r'href="([^"]+)" download=', html)
    for h in dl_hrefs:
        if not h.endswith(".md"):
            rep["issues"].append(f"dl link not md: {h}")
        if not (BOOK / h).exists():
            rep["issues"].append(f"dl target missing: {h}")
    # 4. slim-шапка: hline
    for lang in ("en", "ru"):
        md_p = BOOK / b[lang]
        if not md_p.exists():
            continue
        body = md_body(md_p.read_text(encoding="utf-8"))
        lines = md_p.read_text(encoding="utf-8").splitlines()
        title = lines[0].lstrip("#").strip()
        ver = ""
        for l in lines[:12]:
            m = re.match(r"^\*\*(?:Version|Версия):\*\*\s*(.*)$", l.strip())
            if m:
                ver = m.group(1).strip().split(" ")[0]
        wl = hline_of(html, lang)
        if title not in wl:
            rep["issues"].append(f"hline missing title ({lang}): {title[:40]}")
        if ver and ver not in wl:
            rep["issues"].append(f"hline missing version {lang}: {ver}")
        if f"{word_count(body)}" not in wl:
            rep["issues"].append(f"hline missing word count {lang}: {word_count(body)}")
    # свитчер: 5 ссылок, активная = книга n
    sw = re.findall(r'<a class="sw( on)?" href="([^"]+)"', html)
    want = {f"../book{i}/" for i in range(1, 5)}
    got = {h for _, h in sw}
    if got != want:
        rep["issues"].append(f"switcher hrefs wrong: {got ^ want}")
    active = [h for on, h in sw if on]
    if active != [f"../book{n}/"]:
        rep["issues"].append(f"active switcher wrong: {active}")
    if 'class="sws" href="../series/"' not in html:
        rep["issues"].append("series switcher link missing")
    # билингва: два article + toggle
    arts = re.findall(r'<article class="lang-(ru|en)"', html)
    if set(arts) != {"en", "ru"}:
        rep["issues"].append(f"expected bilingual articles, got {arts}")
    if "langswitch" not in html or 'data-l="en"' not in html or 'data-l="ru"' not in html:
        rep["issues"].append("lang toggle missing")
    # 1-3. тела
    for lang in ("en", "ru"):
        if lang in arts:
            r = check_section(BOOK / b[lang], html_p, lang)
            rep[lang] = r
            if not r.get("clean"):
                rep["issues"].append(f"body drift ({lang})")
    rep["clean"] = not rep["issues"]
    return rep

def check_hub():
    html = (BOOK / "index.html").read_text(encoding="utf-8")
    issues = []
    if re.findall(r'href="[^"]+\.(?:pdf|epub|mp3)"', html):
        issues.append("banned format links in hub")
    for i in range(1, 5):
        if f'href="book{i}/"' not in html:
            issues.append(f"missing tile book{i}/")
    if 'href="series/"' not in html:
        issues.append("missing series tile")
    return {"name": "hub", "issues": issues, "clean": not issues}

def check_series():
    html = (BOOK / "series/index.html").read_text(encoding="utf-8")
    issues = []
    if re.findall(r'href="[^"]+\.(?:pdf|epub|mp3)"', html):
        issues.append("banned format links in series")
    for i in range(1, 5):
        if f'href="../book{i}/"' not in html:
            issues.append(f"missing tile ../book{i}/")
    if 'href="../"' not in html:
        issues.append("missing hub tile")
    for phrase in ("One point of truth", "Единая точка правды", "bookN/ru", "bookN/en"):
        if phrase not in html:
            issues.append(f"missing phrase: {phrase}")
    return {"name": "series", "issues": issues, "clean": not issues}

def main():
    out = [check_book(n) for n in (1, 2, 3, 4)] + [check_hub(), check_series()]
    print(json.dumps(out, ensure_ascii=False, indent=1))
    clean = all(o.get("clean") for o in out)
    print("DRIFT-CLEAN" if clean else "DRIFT-FOUND", file=sys.stderr)
    sys.exit(0 if clean else 1)

if __name__ == "__main__":
    main()
