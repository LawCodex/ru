#!/usr/bin/env python3
"""Convert the cached pravo.gov.ru (actual.pravo.gov.ru) редакции fetched by
ru_fetch.py into LawCodex Markdown files.

Usage: python ru_convert.py [--raw _raw/ru] [--out <repo dir>]
"""
import argparse
import datetime
import glob
import json
import os
import re
import sys
from collections import defaultdict

import yaml
from lxml import html as LH

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RAW = os.path.join(HERE, "..", "..", "_raw", "ru")
DEFAULT_OUT = os.path.join(HERE, "..")
SRC_URL = "http://actual.pravo.gov.ru/content/content.html#hash=%s"

# ---------------------------------------------------------------- transliteration
TR = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z",
    "и": "i", "й": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh",
    "щ": "shch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def translit(s):
    return "".join(TR.get(c, c) for c in s.lower())


def slugify(s, maxlen=100):
    s = translit(s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if len(s) > maxlen:
        s = s[:maxlen].rsplit("-", 1)[0]
    return s


ROMAN = {"I": "1", "II": "2"}


def number_slug(num):
    # "152-ФЗ" -> "152", "2300-I" -> "2300-1", "1-ФКЗ" -> "1"
    n = re.sub(r"-(ФКЗ|ФЗ)$", "", num.strip())
    n = re.sub(r"-(I{1,2})$", lambda m: "-" + ROMAN[m.group(1)], n)
    return slugify(n, 40)


# Short, stable names for the codes (by number of the adopting act).
CODE_NAMES = {
    "51-ФЗ": "gk-1-grazhdanskii-kodeks-chast-pervaya",
    "14-ФЗ": "gk-2-grazhdanskii-kodeks-chast-vtoraya",
    "146-ФЗ/2001": "gk-3-grazhdanskii-kodeks-chast-tretya",
    "230-ФЗ": "gk-4-grazhdanskii-kodeks-chast-chetvertaya",
    "63-ФЗ": "uk-ugolovnyi-kodeks",
    "174-ФЗ": "upk-ugolovno-protsessualnyi-kodeks",
    "1-ФЗ": "uik-ugolovno-ispolnitelnyi-kodeks",
    "138-ФЗ": "gpk-grazhdanskii-protsessualnyi-kodeks",
    "95-ФЗ": "apk-arbitrazhnyi-protsessualnyi-kodeks",
    "21-ФЗ": "kas-kodeks-administrativnogo-sudoproizvodstva",
    "195-ФЗ": "koap-kodeks-ob-administrativnykh-pravonarusheniyakh",
    "146-ФЗ/1998": "nk-1-nalogovyi-kodeks-chast-pervaya",
    "117-ФЗ": "nk-2-nalogovyi-kodeks-chast-vtoraya",
    "145-ФЗ": "bk-byudzhetnyi-kodeks",
    "197-ФЗ": "tk-trudovoi-kodeks",
    "223-ФЗ": "sk-semeinyi-kodeks",
    "188-ФЗ": "zhk-zhilishchnyi-kodeks",
    "136-ФЗ": "zk-zemelnyi-kodeks",
    "190-ФЗ": "grk-gradostroitelnyi-kodeks",
    "74-ФЗ": "vk-vodnyi-kodeks",
    "200-ФЗ": "lk-lesnoi-kodeks",
    "60-ФЗ": "vozk-vozdushnyi-kodeks",
    "81-ФЗ": "ktm-kodeks-torgovogo-moreplavaniya",
    "24-ФЗ": "kvvt-kodeks-vnutrennego-vodnogo-transporta",
    "5221-I": "tamk-1993-tamozhennyi-kodeks",
}

# ---------------------------------------------------------------- structure
HEAD_RES = [
    (1, re.compile(r"^(ЧАСТЬ|Часть)\s+(ПЕРВАЯ|ВТОРАЯ|ТРЕТЬЯ|ЧЕТВЕРТАЯ|ЧЕТВЁРТАЯ|ПЯТАЯ|ОБЩАЯ|ОСОБЕННАЯ|"
                   r"первая|вторая|третья|четвертая|пятая|общая|особенная|[IVX\d]+\b)")),
    (2, re.compile(r"^(РАЗДЕЛ|Раздел)\s")),
    (3, re.compile(r"^(ПОДРАЗДЕЛ|Подраздел)\s")),
    (4, re.compile(r"^(ГЛАВА|Глава)\s")),
    (5, re.compile(r"^(§|ПАРАГРАФ|Параграф)\s*\d")),
    (7, re.compile(r"^(СТАТЬЯ|Статья)\s*\d")),
]


def heading_rank(text):
    for rank, rx in HEAD_RES:
        if rx.match(text):
            return rank
    return None


INLINE_FMT = {
    "W2": ("*", "*"), "W3": ("*", "*"), "W4": ("**", "**"), "W5": ("**", "**"),
    "W6": ("***", "***"), "W7": ("***", "***"), "W8": ("<sub>", "</sub>"), "W9": ("<sup>", "</sup>"),
}

MD_ESC = re.compile(r"([\\`*_\[\]<>|])")


def esc(t):
    return MD_ESC.sub(r"\\\1", t)


def norm_ws(t):
    t = t.replace("\r", "").replace("\t", " ")
    return t


def inline(el, plain=False):
    """Render inline content of element `el` to Markdown text."""
    out = []
    if el.text:
        out.append(el.text if plain else esc(el.text))
    for ch in el:
        tag = ch.tag if isinstance(ch.tag, str) else ""
        cls = ch.get("class", "")
        if tag == "br":
            out.append("<br>")
        elif tag == "img":
            src = ch.get("src", "")
            out.append("![изображение](%s)" % src if src else "")
        elif tag in ("input", "label", "script", "style"):
            pass
        elif tag in ("sup",):
            out.append("<sup>%s</sup>" % inline(ch, plain))
        elif tag in ("sub",):
            out.append("<sub>%s</sub>" % inline(ch, plain))
        elif tag in ("b", "strong"):
            inner = inline(ch, plain)
            out.append("**%s**" % inner if inner.strip() and not plain else inner)
        elif tag in ("i", "em"):
            inner = inline(ch, plain)
            out.append("*%s*" % inner if inner.strip() and not plain else inner)
        elif tag:
            inner = inline(ch, plain)
            fmt = None
            for c in cls.split():
                if c in INLINE_FMT:
                    fmt = INLINE_FMT[c]
            if fmt and inner.strip() and (not plain or fmt[0].startswith("<")):
                lead = len(inner) - len(inner.lstrip())
                trail = len(inner) - len(inner.rstrip())
                core = inner.strip()
                out.append(inner[:lead] + fmt[0] + core + fmt[1] + (inner[len(inner) - trail:] if trail else ""))
            else:
                out.append(inner)
        if ch.tail:
            out.append(ch.tail if plain else esc(ch.tail))
    return "".join(out)


def clean_line(t):
    t = norm_ws(t).replace("\xa0", " ")
    t = re.sub(r"[ ]{2,}", " ", t)
    return t.strip()


def cell_text(td):
    parts = []
    ps = td.findall(".//p")
    if ps:
        for p in ps:
            s = clean_line(inline(p))
            if s:
                parts.append(s)
    else:
        s = clean_line(inline(td))
        if s:
            parts.append(s)
    return "<br>".join(parts)


def table_md(tbl):
    rows = tbl.xpath(".//tr")
    complex_ = bool(tbl.xpath(".//td[@rowspan or @colspan] | .//th[@rowspan or @colspan] | .//table//table"))
    if not complex_ and rows:
        grid = [[cell_text(td).replace("|", "\\|") for td in tr.xpath("./td|./th")] for tr in rows]
        width = max(len(r) for r in grid)
        if width == 0:
            return ""
        grid = [r + [""] * (width - len(r)) for r in grid]
        lines = ["| " + " | ".join(grid[0]) + " |", "|" + "---|" * width]
        for r in grid[1:]:
            lines.append("| " + " | ".join(r) + " |")
        return "\n".join(lines)
    # complex table: keep simplified HTML
    out = ["<table>"]
    for tr in rows:
        cells = []
        for td in tr.xpath("./td|./th"):
            attrs = ""
            for a in ("rowspan", "colspan"):
                if td.get(a) and td.get(a) != "1":
                    attrs += ' %s="%s"' % (a, td.get(a))
            cells.append("<td%s>%s</td>" % (attrs, cell_text(td)))
        out.append("<tr>" + "".join(cells) + "</tr>")
    out.append("</table>")
    return "\n".join(out)


def convert_body(body_html):
    doc = LH.fromstring(body_html)
    body = doc.find(".//body")
    if body is None:
        body = doc
    blocks = []  # (kind, cls, text) kinds: p, table, pre

    def walk(container):
        for el in container:
            tag = el.tag if isinstance(el.tag, str) else ""
            if tag == "p":
                cls = (el.get("class") or "").strip()
                if cls == "M":
                    blocks.append(("pre", cls, norm_ws(inline(el, plain=True)).replace("\xa0", " ").rstrip()))
                else:
                    blocks.append(("p", cls, clean_line(inline(el))))
            elif tag == "table":
                blocks.append(("table", "", table_md(el)))
            elif tag in ("div", "center", "section", "span", "font", "blockquote"):
                walk(el)
            elif tag in ("input", "label", "script", "style", "br"):
                continue
            elif tag:
                s = clean_line(inline(el))
                if s:
                    blocks.append(("p", "", s))
    walk(body)

    # heading detection
    items = []  # dicts: type heading/para/table/pre
    for i, (k, cls, text) in enumerate(blocks):
        if k == "p" and not text:
            items.append({"type": "blank"})
            continue
        if k == "p":
            plain = re.sub(r"<su[pb]>|</su[pb]>|\*", "", text)
            plain = plain.replace("\\", "")
            rank = heading_rank(plain) if cls in ("T", "H", "C", "Z") else None
            if rank and len(plain) > 600:
                rank = None
            if rank:
                items.append({"type": "heading", "rank": rank, "text": text, "cls": cls})
            else:
                items.append({"type": "para", "text": text, "cls": cls})
        else:
            items.append({"type": k, "text": text})

    # merge a structural heading with the following title-only T/H paragraph
    # (e.g. Constitution: "ГЛАВА 1" + "ОСНОВЫ КОНСТИТУЦИОННОГО СТРОЯ"; "Статья 1" alone stays)
    merged = []
    i = 0
    while i < len(items):
        it = items[i]
        if it["type"] == "heading" and it["rank"] < 7 and re.fullmatch(
                r"(ЧАСТЬ|Часть|РАЗДЕЛ|Раздел|ПОДРАЗДЕЛ|Подраздел|ГЛАВА|Глава|§|ПАРАГРАФ|Параграф)\s*[\wIVXА-Яа-я.<>/]*\.?",
                re.sub(r"\s+", " ", it["text"]).strip()):
            j = i + 1
            while j < len(items) and items[j]["type"] == "blank":
                j += 1
            if j < len(items) and items[j]["type"] == "para" and items[j]["cls"] in ("T", "H", "Z") \
                    and heading_rank(items[j]["text"]) is None:
                it = dict(it)
                it["text"] = it["text"].rstrip(".") + ". " + items[j]["text"]
                merged.append(it)
                i = j + 1
                continue
        merged.append(it)
        i += 1
    items = merged

    ranks = sorted({it["rank"] for it in items if it["type"] == "heading"})
    level = {r: min(2 + n, 7) for n, r in enumerate(ranks)}

    out = []
    seen_heading = False
    pre_buf = []

    def flush_pre():
        if pre_buf:
            out.append("```\n" + "\n".join(pre_buf) + "\n```")
            pre_buf.clear()

    for it in items:
        t = it["type"]
        if t == "pre":
            pre_buf.append(it["text"])
            continue
        flush_pre()
        if t == "blank":
            continue
        if t == "heading":
            seen_heading = True
            lv = level[it["rank"]]
            txt = re.sub(r"\s+", " ", it["text"])
            if lv <= 6:
                out.append("#" * lv + " " + txt)
            else:
                out.append("**" + txt + "**")
        elif t == "para":
            txt = it["text"]
            if it["cls"] in ("T", "Z") and not txt.startswith("*"):
                txt = "**" + txt + "**"
            # avoid accidental Markdown heading / quote / list markers at line start
            if re.match(r"^[#>+\-=]", txt):
                txt = "\\" + txt
            out.append(txt)
        elif t == "table":
            if it["text"]:
                out.append(it["text"])
    flush_pre()
    return "\n\n".join(out) + "\n"


# ---------------------------------------------------------------- metadata & paths
def parse_date(s):
    m = re.match(r"(\d{4})(\d{2})(\d{2})", s or "")
    if not m:
        return None
    try:
        return datetime.date(*map(int, m.groups()))
    except ValueError:
        return None


STATUS = {
    "Действует с изменениями": "in_force",
    "Действует без изменений": "in_force",
    "Не вступил в силу": "not_yet_in_force",
}

TYPE = {100: "constitution", 735: "constitutional_amendment", 108: "federal_constitutional_law", 70: "code",
        107: "federal_law", 53: "law", 7: "law", 90: "law"}


def rel_path(rec):
    kind = rec["kind"]
    d = rec["doc"]
    num = (d.get("docpass0number") or "").strip()
    date = d.get("docpass0date") or ""
    year = date[:4] or "0000"
    title = d.get("docnames") or ""
    tslug = slugify(title, 70)
    if kind == 100:
        return "konstitutsiya/konstitutsiya-rossiiskoi-federatsii.md"
    if kind == 735:
        return "konstitutsiya/popravki/zakon-o-popravke-%s-%s-fkz-%s.md" % (year, number_slug(num), tslug)
    if kind == 70:
        key = num
        if num == "146-ФЗ":
            key = "146-ФЗ/" + year
        name = CODE_NAMES.get(key) or slugify(title, 90)
        return "kodeksy/%s.md" % name
    if kind == 108:
        return "fkz/%s/fkz-%s-%s-%s.md" % (year, year, number_slug(num), tslug)
    if kind == 107:
        return "fz/%s/fz-%s-%s-%s.md" % (year, year, number_slug(num), tslug)
    prefix = {53: "zakon-rf", 7: "zakon-rsfsr", 90: "osnovy"}[kind]
    return "zakony-rf/%s-%s-%s-%s.md" % (prefix, year, number_slug(num), tslug)


def front_matter(rec, retrieved):
    d = rec["doc"]
    red = rec["redaction"]
    title = (d.get("docnames") or "").strip() or (d.get("docpassing") or "").strip()
    fm = {
        "title": title,
        "identifier": (d.get("docpass0number") or "").strip() or None,
        "type": TYPE[rec["kind"]],
        "kind": (d.get("docpassing") or "").strip(),
        "jurisdiction": "ru",
        "language": "ru",
        "date": parse_date(d.get("docpass0date")),
        "last_amended": parse_date(red.get("reddate")),
        "redaction": (red.get("redcaption") or "").strip(),
        "note": ("Актуальная редакция «%s» на портале ещё не подготовлена (текст не готов); "
                 "приведена предыдущая редакция." % rec["not_ready"]["redcaption"].strip()) if rec.get("not_ready") else None,
        "status": STATUS.get(d.get("docstate"), "unknown"),
        "state": d.get("docstate"),
        "publications": d.get("publications") or [],
        "source": SRC_URL % d["dochash"],
        "retrieved": parse_date((retrieved or "").replace("-", "")) or retrieved,
    }
    fm = {k: v for k, v in fm.items() if v not in (None, "", [])}
    return "---\n" + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, width=1000) + "---\n"


def convert_record(rec):
    h = rec["html"]
    i = h.find("<body")
    if i < 0:
        return None
    body = h[i:]
    md = convert_body("<html>" + body)
    d = rec["doc"]
    title = (d.get("docnames") or "").strip() or (d.get("docpassing") or "").strip()
    h1 = title
    if rec["kind"] not in (100,) and d.get("docpassing"):
        h1 = "%s (%s)" % (title, d["docpassing"].strip()) if title != d["docpassing"].strip() else title
    return front_matter(rec, rec.get("retrieved")) + "\n# " + h1 + "\n\n" + md


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=DEFAULT_RAW)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--only", help="comma-separated directory prefixes to (re)write, e.g. kodeksy,fkz")
    args = ap.parse_args()
    raw, out = os.path.abspath(args.raw), os.path.abspath(args.out)
    files = sorted(glob.glob(os.path.join(raw, "docs", "*", "*.json")))
    paths = defaultdict(list)
    recs = []
    for f in files:
        rec = json.load(open(f, encoding="utf-8"))
        rec.pop("html", None)
        recs.append((f, rec))
        paths[rel_path(rec)].append(f)
    # disambiguate duplicate paths with the internal document id
    final = {}
    for p, fs in paths.items():
        if len(fs) == 1:
            final[fs[0]] = p
        else:
            for f in fs:
                rec = next(r for ff, r in recs if ff == f)
                final[f] = p[:-3] + "-%s.md" % rec["doc"]["docid"]
    only = tuple(args.only.split(",")) if args.only else None
    counts = defaultdict(int)
    for f, _ in recs:
        p = final[f]
        if only and not p.startswith(only):
            continue
        rec = json.load(open(f, encoding="utf-8"))
        md = convert_record(rec)
        if md is None:
            print("no body:", f, file=sys.stderr)
            continue
        dest = os.path.join(out, p)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(md)
        counts[p.split("/")[0]] += 1
    print(dict(counts), file=sys.stderr)


if __name__ == "__main__":
    main()
