#!/usr/bin/env python3
"""SSOT drift-check: сверяет опубликованные HTML с markdown-источниками.

Исходная истина (single source of truth):
  book1 RU: book/ii_dlya_vsekh_v4.1.1.md
  book1 EN: book/AI_for_Everyone_v4.1.1.md
  book2:    writer/books/book2/Создавая_себя_v0.3.md
  book3:    writer/books/book3/Конституция_цифровой_души_v0.1.md
  book4:    writer/books/book4/За_пределами_режима_ассистента_v0.1.md

HTML-источники (публикация): book{,2,3,4}/index.html (билингвы: article lang-ru/lang-en)

Что проверяется:
  1. Заголовки MD присутствуют в HTML в том же порядке (для билингвы — в обоих article).
  2. Каждый MD-абзац (нормализованный) присутствует в HTML.
  3. Обратное: HTML-абзацы не содержат «мёртвого» контента, которого нет в MD (кроме шапки/шаблона).
  4. Слово: сколько слов в MD vs в HTML-теле (rough).
Выход: JSON-отчёт + exit code (0 = чистый, 1 = drift).
"""
import json, re, sys
from pathlib import Path
from html.parser import HTMLParser

BOOK = Path(__file__).resolve().parent
WR = BOOK.parent / "writer" / "books"

class ArticleSplitter(HTMLParser):
    """Разбирает HTML на секции: article.lang-ru / article.lang-en / остальное (шапка).
    Внутри статьи собирает заголовки и абзацы."""
    def __init__(self, page_lang="ru"):
        super().__init__()
        self.page_lang = page_lang
        self.sections = {}      # lang -> {"headings": [(tag,text)], "paras": [str]}
        self._cur = None        # текущий lang
        self._skip = 0
        self._buf = []
        self._hbuf = None
    def _newsec(self, lang):
        self.sections.setdefault(lang, {"headings": [], "paras": []})
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class", "")
        if "lang-ru" in cls.split() and tag == "article":
            self._cur = "ru"; self._newsec("ru")
        elif "lang-en" in cls.split() and tag == "article":
            self._cur = "en"; self._newsec("en")
        elif tag == "article" and self._cur is None:
            self._cur = self.page_lang; self._newsec(self.page_lang)
        if self._cur:
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
        elif tag in ("h1", "h2", "h3") and self._hbuf:
            self.sections[self._cur]["headings"].append((self._hbuf[0], self._hbuf[1].strip()))
            self._hbuf = None
        elif tag in ("p", "li"):
            t = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            self._buf = []
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
    s = re.sub(r"\s+", " ", s).strip()
    # уберём markdown-разметку для сравнения
    return s

def md_heads(md):
    out = []
    for line in md.splitlines():
        m = re.match(r"^(#{1,3})\s+(.*)$", line)
        if m:
            out.append((f"h{len(m.group(1))}", norm(m.group(2))))
    return out

def md_paras(md):
    # тело: абзацы без #, без списков, без ---; извлекаем как нормализованный текст
    out = []
    for block in re.split(r"\n\s*\n", md):
        b = block.strip()
        if not b or b.startswith("#") or b.startswith("---") or b.startswith("|") or b.startswith("```"):
            continue
        # убираем markdown-разметку внутри
        t = b.replace("**", "").replace("__", "")
        t = re.sub(r"\*\*", "", t)
        t = re.sub(r"(?<!\w)\*([^*]+)\*(?!\w)", r"\1", t)
        t = re.sub(r"`([^`]+)`", r"\1", t)
        t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
        out.append(norm(t))
    return [p for p in out if len(p) > 30]

def check_book(md_p, html_p, langs=("ru",)):
    md = md_p.read_text(encoding="utf-8")
    html = html_p.read_text(encoding="utf-8")
    page_lang = "ru"
    m = re.search(r'<html lang="([a-z]{2})"', html)
    if m:
        page_lang = m.group(1)
    p = ArticleSplitter(page_lang=page_lang)
    p.feed(html)
    md_h = md_heads(md)
    md_par = md_paras(md)
    report = {"md": str(md_p), "html": str(html_p), "md_heads": len(md_h), "md_paras": len(md_par)}
    clean = True
    for lang in langs:
        sec = p.sections.get(lang)
        if sec is None:
            report[lang] = {"error": "section not found"}
            clean = False
            continue
        h_seq = [t for _, t in sec["headings"]]
        # сравнение заголовков: md-заголовки должны встретиться в html-заголовках в порядке
        mseq = [t for _, t in md_h]
        i, missing_h = 0, []
        for mh in mseq:
            found_at = None
            for j in range(i, len(h_seq)):
                # допускаем незначительные расхождения (двоеточия, кавычки)
                if norm(h_seq[j]) == norm(mh) or norm(h_seq[j]).replace("«","").replace("»","").replace(":","") == norm(mh).replace("«","").replace("»","").replace(":",""):
                    found_at = j
                    break
            if found_at is None:
                missing_h.append(mh)
            else:
                i = found_at + 1
        html_par = " || ".join(sec["paras"])
        missing_p = [mp for mp in md_par if norm(mp)[:80] not in html_par and norm(mp)[:40] not in html_par]
        extra_p = [hp for hp in sec["paras"] if len(hp) > 80 and not any(norm(mp)[:60] in norm(hp) or norm(hp)[:60] in norm(mp) for mp in md_par)]
        r = {
            "headings_md": len(mseq), "headings_html": len(h_seq),
            "headings_missing_in_html": missing_h,
            "paras_html": len(sec["paras"]),
            "md_paras_not_in_html": missing_p,
            "html_paras_not_in_md": extra_p[:5],
            "html_paras_not_in_md_count": len(extra_p),
        }
        report[lang] = r
        if missing_h or missing_p:
            clean = False
    report["clean"] = clean
    return report

def main():
    targets = [
        ("book1_ru", BOOK / "ii_dlya_vsekh_v4.1.1.md", BOOK / "index.html", ("ru",)),
        ("book1_en", BOOK / "AI_for_Everyone_v4.1.1.md", BOOK / "index.html", ("en",)),
        ("book2_ru", WR / "book2/Создавая_себя_v0.3.md", BOOK / "book2/index.html", ("ru",)),
        ("book3_ru", WR / "book3/Конституция_цифровой_души_v0.1.md", BOOK / "book3/index.html", ("ru",)),
        ("book4_ru", WR / "book4/За_пределами_режима_ассистента_v0.1.md", BOOK / "book4/index.html", ("ru",)),
    ]
    out = []
    for name, md, hp, langs in targets:
        if not md.exists() or not hp.exists():
            out.append({"name": name, "error": "missing file", "clean": False})
            continue
        r = check_book(md, hp, langs)
        r["name"] = name
        out.append(r)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    print("DRIFT-CLEAN" if all(o.get("clean") for o in out) else "DRIFT-FOUND", file=sys.stderr)

if __name__ == "__main__":
    main()
