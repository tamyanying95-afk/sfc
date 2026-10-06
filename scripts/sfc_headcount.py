#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SFC Public Register batch lookup.

For each corporation name:
  1. resolve CE No. via /publicregWeb/searchByNameJson
  2. fetch /publicregWeb/corp/{ceref}/ro  -> rorawData  (Responsible Officers)
  3. fetch /publicregWeb/corp/{ceref}/rep -> reprawData (Representatives)
  4. dedupe people by CE No. across roles and across companies
"""

import csv
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import OrderedDict

BASE = "https://apps.sfc.hk/publicregWeb"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
CACHE_DIR = os.path.join(OUT_DIR, "cache")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"

RAW_COMPANIES = """
MILLENNIUM CAPITAL MANAGEMENT (HONG KONG) LIMITED
Point72 Hong Kong Limited
Citadel Asia Limited  Citadel Securities (Hong Kong) Limited
MARSHALL WACE ASIA LIMITED
Polymer Capital Management (HK) Limited POLYMER WEALTH MANAGEMENT COMPANY LIMITED
Balyasny Asset Management (Hong Kong) Limited
Dymon Asia Capital (HK) Limited
MARSHALL WACE ASIA LIMITED
Schonfeld Strategic Advisors (Hong Kong) Limited
GREENWOODS ASSET MANAGEMENT HONG KONG LIMITED
North Rock Capital Management (HK) Limited
Aspex Management (HK) Limited
Jane Street Asia Pacific Limited
BlackRock Asset Management North Asia Limited
Wellington Management Hong Kong Limited
Fidelity Management & Research (Hong Kong) Limited First Fidelity Capital (International) Limited
T. Rowe Price Hong Kong Limited
E FUND MANAGEMENT (HONG KONG) CO., LIMITED
INVESCO HONG KONG LIMITED
SCHRODER INVESTMENT MANAGEMENT (HONG KONG) LIMITED
"""


def expand_names(raw):
    """Split lines like 'A Limited B Limited' into two names; drop duplicates."""
    names = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        # split at a boundary: "... LIMITED  ..." (2+ spaces) or "...Limited  ..."
        # where a capital letter starts a new entity name
        rough = re.split(r"\s{2,}", line)
        parts = []
        for chunk in rough:
            parts.extend(re.split(r"(?<=\b[Ll][Ii][Mm][Ii][Tt][Ee][Dd])\s+(?=[A-Z(])", chunk))
        for p in parts:
            p = p.strip()
            if p:
                names.append(p)
    out, seen = [], set()
    for n in names:
        key = norm(n)
        if key and key not in seen:
            seen.add(key)
            out.append(n)
    return out


def norm(s):
    s = (s or "").upper()
    s = s.replace("&", " AND ")
    s = re.sub(r"[.,()'’\-/]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def tokens(s):
    return [t for t in norm(s).split() if t not in {"LIMITED", "LTD", "THE", "CO", "COMPANY"}]


def fetch(url, data=None, cache_key=None, retries=3):
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, (cache_key or re.sub(r"[^A-Za-z0-9]+", "_", url))[:120] + ".txt")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers={
                "User-Agent": UA,
                "Accept": "application/json, text/plain, */*" if data else "text/html",
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Referer": BASE + "/searchByName?locale=en",
            })
            with urllib.request.urlopen(req, timeout=45) as r:
                body = r.read().decode("utf-8", "replace")
            with open(path, "w", encoding="utf-8") as f:
                f.write(body)
            time.sleep(0.5)
            return body
        except Exception as e:  # noqa
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError("fetch failed: %s (%s)" % (url, last))


def search(text, licstatus="active"):
    payload = urllib.parse.urlencode({
        "searchbyoption": "byname",
        "searchtext": text,
        "searchlang": "en",
        "entityType": "corporation",
        "licstatus": licstatus,
        "lictype": "all",
        "page": "1",
        "start": "0",
        "limit": "200",
    }).encode()
    body = fetch(BASE + "/searchByNameJson", data=payload,
                 cache_key="search_%s_%s" % (licstatus, norm(text)))
    try:
        return json.loads(body)
    except Exception:
        return {"totalCount": 0, "items": []}


def score(candidate, target):
    ct, tt = tokens(candidate), tokens(target)
    if not ct or not tt:
        return 0
    cs, ts = set(ct), set(tt)
    inter = len(cs & ts)
    union = len(cs | ts)
    j = inter / union if union else 0
    bonus = 0.15 if norm(candidate) == norm(target) else 0
    return j + bonus


def resolve(name):
    """Return list of matched corporation dicts (best first)."""
    tried = []
    for q in dedupe([name, " ".join(tokens(name)[:3]), " ".join(tokens(name)[:2]), tokens(name)[0]]):
        if not q:
            continue
        tried.append(q)
        res = search(q)
        items = [it for it in res.get("items", []) if it.get("isCorp")]
        if items:
            items.sort(key=lambda it: (-score(it.get("entityName") or it.get("name") or "", name),
                                       it.get("ceref")))
            return items, tried, res.get("totalCount", 0)
    return [], tried, 0


def dedupe(seq):
    out, seen = [], set()
    for s in seq:
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def extract_people(ceref, kind):
    url = "%s/corp/%s/%s?locale=en" % (BASE, ceref, kind)
    body = fetch(url, cache_key="%s_%s" % (ceref, kind))
    m = re.search(r"var\s+(?:ro|rep)rawData\s*=\s*(\[.*?\]);\s*\n", body, re.S)
    if not m:
        m = re.search(r"var\s+\w*rawData\s*=\s*(\[.*?\]);", body, re.S)
    if not m:
        return []
    raw = m.group(1)
    try:
        return json.loads(raw)
    except Exception:
        # fallback: pull ceRef/fullName pairs
        return []


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    names = expand_names(RAW_COMPANIES)
    print("companies after split: %d" % len(names), file=sys.stderr)

    results = []
    for name in names:
        items, tried, total = resolve(name)
        if not items:
            results.append({"input": name, "ceref": None, "sfc_name": None,
                            "status": "NOT FOUND", "note": "queries tried: " + " | ".join(tried)})
            print("NOT FOUND: %s" % name, file=sys.stderr)
            continue
        best = items[0]
        ceref = best.get("ceref")
        sfc_name = best.get("entityName") or best.get("name")
        s = score(sfc_name, name)
        note = ""
        if s < 0.6:
            note = "low match score %.2f; candidates: %s" % (
                s, "; ".join("%s %s" % (i.get("ceref"), i.get("entityName") or i.get("name")) for i in items[:5]))
        active = "Y" if best.get("hasActiveLicence") == "Y" else "N"
        results.append({"input": name, "ceref": ceref, "sfc_name": sfc_name,
                        "status": "active" if active == "Y" else "inactive",
                        "note": note})
        print("%-70s -> %s %s (score %.2f)" % (name[:70], ceref, sfc_name, s), file=sys.stderr)

    people = OrderedDict()   # ceRef -> record
    per_company = []
    for r in results:
        if not r["ceref"]:
            per_company.append({**r, "ro": 0, "rep": 0, "unique": 0})
            continue
        ros = extract_people(r["ceref"], "ro")
        reps = extract_people(r["ceref"], "rep")
        ro_ce = [p.get("ceRef") for p in ros if p.get("ceRef")]
        rep_ce = [p.get("ceRef") for p in reps if p.get("ceRef")]
        for p in ros:
            rec = people.setdefault(p.get("ceRef"), {
                "ceRef": p.get("ceRef"),
                "name": p.get("fullName"),
                "nameChi": p.get("entityNameChi"),
                "companies": [],
                "roles": set(),
            })
            rec["roles"].add("RO")
            rec["companies"].append(r["sfc_name"])
        for p in reps:
            rec = people.setdefault(p.get("ceRef"), {
                "ceRef": p.get("ceRef"),
                "name": p.get("fullName"),
                "nameChi": p.get("entityNameChi"),
                "companies": [],
                "roles": set(),
            })
            rec["roles"].add("Rep")
            rec["companies"].append(r["sfc_name"])
        per_company.append({
            **r,
            "ro": len(set(ro_ce)),
            "rep": len(set(rep_ce)),
            "unique": len(set(ro_ce) | set(rep_ce)),
        })
        print("   %s: RO=%d Rep=%d unique=%d" % (r["ceref"], len(set(ro_ce)), len(set(rep_ce)), len(set(ro_ce) | set(rep_ce))), file=sys.stderr)

    # global dedupe by CE No.
    unique_total = len(people)
    sum_unique = sum(p["unique"] for p in per_company)
    overlap = sum_unique - unique_total

    # write CSV - per company
    with open(os.path.join(OUT_DIR, "sfc_company_summary.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Input name", "CE No.", "SFC registered name", "Licence status",
                    "Responsible Officers", "Representatives", "Unique people (CE dedupe)", "Note"])
        for p in per_company:
            w.writerow([p["input"], p["ceref"] or "", p["sfc_name"] or "", p["status"],
                        p["ro"], p["rep"], p["unique"], p.get("note", "")])

    # write CSV - people
    with open(os.path.join(OUT_DIR, "sfc_people_unique.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["CE No.", "Name", "Chinese name", "Roles", "Companies"])
        for ce, rec in sorted(people.items(), key=lambda kv: (kv[1]["name"] or "")):
            roles = sorted(rec["roles"])
            w.writerow([ce, rec["name"], rec["nameChi"] or "", "+".join(roles),
                        "; ".join(sorted(set(rec["companies"])))])

    summary = {
        "companies_input": len(names),
        "companies_resolved": sum(1 for p in per_company if p["ceref"]),
        "sum_of_per_company_unique": sum_unique,
        "global_unique_people": unique_total,
        "cross_company_duplicates_removed": overlap,
        "total_ro_rows": sum(p["ro"] for p in per_company),
        "total_rep_rows": sum(p["rep"] for p in per_company),
    }
    with open(os.path.join(OUT_DIR, "sfc_result.json"), "w", encoding="utf-8") as f:
        json.dump({"summary": summary,
                   "companies": per_company,
                   "people": [{"ceRef": ce, "name": r["name"], "nameChi": r["nameChi"],
                               "roles": sorted(r["roles"]), "companies": sorted(set(r["companies"]))}
                              for ce, r in people.items()]},
                  f, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
