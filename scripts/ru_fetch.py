#!/usr/bin/env python3
"""Fetch current consolidated texts of Russian federal legislation from the
official legal information portal (pravo.gov.ru), via the JSON API behind
http://actual.pravo.gov.ru/ ("Тексты правовых актов с внесенными изменениями").

API (as used by the site's own JavaScript, see actual.pravo.gov.ru/js/*.js):
  GET http://actual.pravo.gov.ru:8000/api/ebpi/attrsearch/?bpa=ebpi&q=<json>   list/search
  GET .../redactions/?bpa=ebpi&t={"hash":..,"ttl":3}                           редакции of an act
  GET .../redtext?bpa=ebpi&t=<redid>&ttl=0                                     HTML text of a редакция

Everything is cached under _raw/ru/ (lists/ and docs/<hash>.json) so re-runs
only download what is missing. Usage:
  python ru_fetch.py [--raw DIR] [--workers N] [--kinds 100,70,108,107,...]
"""
import argparse
import json
import os
import sys
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

API = "http://actual.pravo.gov.ru:8000/api/ebpi"
UA = "LawCodex/1.0 (+https://github.com/LawCodex)"
DEFAULT_RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "_raw", "ru")

# Kinds (glossary "kinds") collected, in the scope of the repository.
KINDS = {
    100: "Конституция Российской Федерации",
    735: "Закон Российской Федерации о поправке к Конституции Российской Федерации",
    108: "Федеральный конституционный закон",
    70: "Кодекс Российской Федерации",
    107: "Федеральный закон",
    53: "Закон Российской Федерации",
    7: "Закон РСФСР",
    90: "Основы законодательства Российской Федерации",
}
# docstates: 1 = Не вступил в силу, 2 = Действует без изменений, 3 = Действует с изменениями,
# 4 = Утратил силу, 5 = Отменен, 6 = Не действует, 7 = Не применяется
WANTED_STATES = {"Не вступил в силу", "Действует без изменений", "Действует с изменениями"}

_local = threading.local()


def session():
    s = getattr(_local, "s", None)
    if s is None:
        s = requests.Session()
        s.headers["User-Agent"] = UA
        s.trust_env = True
        _local.s = s
    return s


def api_get(path, timeout=300):
    url = API + path
    for attempt in range(6):
        try:
            r = session().get(url, timeout=timeout)
            if r.status_code == 200:
                d = r.json()
                return d
            err = "HTTP %s" % r.status_code
        except Exception as e:  # noqa
            err = repr(e)
        wait = 5 * (2 ** attempt)
        print("  retry %d %s: %s (sleep %ds)" % (attempt + 1, path[:120], err, wait), file=sys.stderr)
        time.sleep(wait)
    raise RuntimeError("giving up on " + url)


def q(obj):
    return urllib.parse.quote(json.dumps(obj, ensure_ascii=False))


def list_kind(kind, raw, limit=500):
    path = os.path.join(raw, "lists", "kind-%d.json" % kind)
    if os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))
    docs = []
    page = 1
    while True:
        query = [
            {"AttrId": 4, "AttrMode": 1, "IDParams": [{"Id": kind, "Param": 0}]},
            # sort attr: AttrMode = page; Words = [limit, sort, ACTUAL_START_DATE, INCLUDE_FUTURE, RESTRICT_VID]
            {"AttrId": 999, "AttrMode": page, "Words": [limit, "date", "", 0, 0]},
        ]
        d = api_get("/attrsearch/?bpa=ebpi&q=" + q(query))
        docs.extend(d["docs"])
        print("kind %d page %d: %d/%d" % (kind, page, len(docs), d["docscount"]), file=sys.stderr)
        if not d["docs"] or len(docs) >= d["docscount"]:
            break
        page += 1
        time.sleep(1)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(docs, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    return docs


def choose_redaction(reds):
    """Pick the currently applicable редакция ('актуальная'); for acts not yet
    in force, the earliest future one; else the most recent one."""
    if not reds:
        return None
    act = [r for r in reds if r.get("actual")]
    if act:
        return act[0]
    fut = [r for r in reds if r.get("redstatus") == "не вступившая"]
    if fut:
        return sorted(fut, key=lambda r: r["reddate"])[0]
    return sorted(reds, key=lambda r: (r["reddate"], r["redid"]))[-1]


def is_placeholder(html):
    i = html.find("<body")
    return i < 0 or len(html) - i < 300


def fetch_doc(doc, kind, raw):
    h = doc["dochash"]
    out = os.path.join(raw, "docs", h[:2], h + ".json")
    if os.path.exists(out):
        return "cached"
    reds = api_get("/redactions/?bpa=ebpi&t=" + q({"hash": h, "ttl": 3}))
    red = choose_redaction(reds.get("redactions") or [])
    if red is None:
        return "nored"
    txt = api_get("/redtext?bpa=ebpi&t=%d&ttl=0" % red["redid"])
    if txt.get("error"):
        print("  error text %s: %s" % (h, txt["error"]), file=sys.stderr)
    not_ready = None
    if is_placeholder(txt.get("redtext") or ""):
        # the current редакция is flagged "текст не готов" (consolidation not finished):
        # fall back to the most recent earlier редакция whose text is complete
        not_ready = red
        earlier = sorted([r for r in reds["redactions"] if r.get("redcompleted") and r["reddate"] <= red["reddate"]
                          and r["redid"] != red["redid"]], key=lambda r: (r["reddate"], r["redid"]))
        if earlier:
            red = earlier[-1]
            txt = api_get("/redtext?bpa=ebpi&t=%d&ttl=0" % red["redid"])
    rec = {
        "kind": kind,
        "doc": doc,
        "redactions": reds.get("redactions"),
        "redaction": red,
        "not_ready": not_ready,
        "serverdate": reds.get("serverdate"),
        "retrieved": time.strftime("%Y-%m-%d"),
        "html": txt.get("redtext") or "",
    }
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out + ".tmp"
    json.dump(rec, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
    os.replace(tmp, out)
    time.sleep(0.3)
    return "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=DEFAULT_RAW)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--kinds", default="100,735,108,70,53,7,90,107")
    args = ap.parse_args()
    raw = os.path.abspath(args.raw)
    for kind in [int(k) for k in args.kinds.split(",")]:
        docs = list_kind(kind, raw)
        todo = [d for d in docs if d.get("docstate") in WANTED_STATES]
        print("kind %d (%s): %d listed, %d in force / pending" % (kind, KINDS.get(kind), len(docs), len(todo)),
              file=sys.stderr)
        n = 0
        with ThreadPoolExecutor(max_workers=min(args.workers, 4)) as ex:
            futs = {ex.submit(fetch_doc, d, kind, raw): d for d in todo}
            for f in as_completed(futs):
                n += 1
                try:
                    res = f.result()
                except Exception as e:  # noqa
                    res = "FAIL %r" % e
                if res != "cached" or n % 500 == 0:
                    if res != "ok" or n % 100 == 0:
                        print("  [%d/%d] %s %s" % (n, len(todo), futs[f]["docpassing"], res), file=sys.stderr)


if __name__ == "__main__":
    main()
