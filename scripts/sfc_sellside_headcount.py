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
ICBC UBS Asset Management (International) Company Limited
UBS Asset Management (Hong Kong) Limited
UBS SECURITIES ASIA LIMITED
UBS SECURITIES HONG KONG LIMITED
GOLDMAN SACHS (ASIA) L.L.C.
GOLDMAN SACHS (ASIA) SECURITIES LIMITED
Goldman Sachs Asset Management (Hong Kong) Limited
HSBC BROKING FOREX (ASIA) LIMITED
HSBC BROKING FUTURES (ASIA) LIMITED
HSBC BROKING FUTURES (HONG KONG) LIMITED
HSBC BROKING SECURITIES (ASIA) LIMITED
HSBC BROKING SECURITIES (HONG KONG) LIMITED
HSBC Corporate Finance (Hong Kong) Limited
HSBC Global Asset Management (Hong Kong) Limited
HSBC Global Asset Management Holdings (Bahamas) Limited
HSBC INSTITUTIONAL TRUST SERVICES (ASIA) LIMITED
HSBC INVESTMENT FUNDS (HONG KONG) LIMITED
HSBC SECURITIES BROKERS (ASIA) LIMITED
J.P. MORGAN BROKING (HONG KONG) LIMITED
J.P. MORGAN SECURITIES (FAR EAST) LIMITED
JPMorgan Asset Management (Asia Pacific) Limited
JPMorgan Asset Management Real Assets (Asia) Limited
JPMorgan Funds (Asia) Limited
Morgan Stanley Asia Limited
Morgan Stanley Hong Kong Securities Limited
CITIGROUP FIRST INVESTMENT MANAGEMENT LIMITED
Citigroup Global Markets Asia Limited
Merrill Lynch (Asia Pacific) Limited
Merrill Lynch Far East Limited
Macquarie Asia Securities Limited
MACQUARIE CAPITAL LIMITED
MACQUARIE FUNDS MANAGEMENT HONG KONG LIMITED
Macquarie Markets Trading Limited
BARCLAYS CAPITAL ASIA LIMITED
BNP PARIBAS ASSET MANAGEMENT ASIA LIMITED
BNP PARIBAS SECURITIES (ASIA) LIMITED
DBS ASIA CAPITAL LIMITED
DBS VICKERS (HONG KONG) LIMITED
CITIC CLSA Capital Partners HK Limited
CLSA LIMITED
CITIC CFI Asset Management Company Limited
CITIC CFI Securities Company Limited
CITIC Futures International Company Limited
CITIC Securities (Hong Kong) Limited
CITIC Securities Asset Management (HK) Limited
CITIC Securities Brokerage (HK) Limited
CITIC Securities Futures (HK) Limited
CITIC Securities International Global Markets Limited
Huatai (Hong Kong) Futures Limited
HUATAI FINANCIAL HOLDINGS (HONG KONG) LIMITED
CHINA INTERNATIONAL CAPITAL CORPORATION HONG KONG ASSET MANAGEMENT LIMITED
CHINA INTERNATIONAL CAPITAL CORPORATION HONG KONG FUTURES LIMITED
CHINA INTERNATIONAL CAPITAL CORPORATION HONG KONG SECURITIES LIMITED
HAITONG INTERNATIONAL ASSET MANAGEMENT (HK) LIMITED
HAITONG INTERNATIONAL ASSET MANAGEMENT LIMITED
HAITONG INTERNATIONAL CAPITAL LIMITED
HAITONG INTERNATIONAL FUTURES LIMITED
HAITONG INTERNATIONAL INVESTMENT MANAGERS LIMITED
HAITONG INTERNATIONAL RESEARCH LIMITED
HAITONG INTERNATIONAL SECURITIES COMPANY LIMITED
CMB International Asset Management Limited
CMB International Capital Limited
CMB INTERNATIONAL FUTURES LIMITED
CMB International Global Markets Limited
CMB International Securities Limited
China Securities (International) Asset Management Company Limited
China Securities (International) Brokerage Company Limited
China Securities (International) Corporate Finance Company Limited
"""

# Sell-side groups: every entity under one bank is summed and de-duplicated by CE No.
GROUPS_RAW = [
    ("UBS", ["ICBC UBS Asset Management (International) Company Limited",
             "UBS Asset Management (Hong Kong) Limited",
             "UBS SECURITIES ASIA LIMITED",
             "UBS SECURITIES HONG KONG LIMITED"]),
    ("Goldman Sachs", ["GOLDMAN SACHS (ASIA) L.L.C.",
                       "GOLDMAN SACHS (ASIA) SECURITIES LIMITED",
                       "Goldman Sachs Asset Management (Hong Kong) Limited"]),
    ("HSBC", ["HSBC BROKING FOREX (ASIA) LIMITED",
              "HSBC BROKING FUTURES (ASIA) LIMITED",
              "HSBC BROKING FUTURES (HONG KONG) LIMITED",
              "HSBC BROKING SECURITIES (ASIA) LIMITED",
              "HSBC BROKING SECURITIES (HONG KONG) LIMITED",
              "HSBC Corporate Finance (Hong Kong) Limited",
              "HSBC Global Asset Management (Hong Kong) Limited",
              "HSBC Global Asset Management Holdings (Bahamas) Limited",
              "HSBC INSTITUTIONAL TRUST SERVICES (ASIA) LIMITED",
              "HSBC INVESTMENT FUNDS (HONG KONG) LIMITED",
              "HSBC SECURITIES BROKERS (ASIA) LIMITED"]),
    ("J.P. Morgan", ["J.P. MORGAN BROKING (HONG KONG) LIMITED",
                     "J.P. MORGAN SECURITIES (FAR EAST) LIMITED",
                     "JPMorgan Asset Management (Asia Pacific) Limited",
                     "JPMorgan Asset Management Real Assets (Asia) Limited",
                     "JPMorgan Funds (Asia) Limited"]),
    ("Morgan Stanley", ["Morgan Stanley Asia Limited",
                        "Morgan Stanley Hong Kong Securities Limited"]),
    ("Citi", ["CITIGROUP FIRST INVESTMENT MANAGEMENT LIMITED",
              "Citigroup Global Markets Asia Limited"]),
    ("Merrill Lynch", ["Merrill Lynch (Asia Pacific) Limited",
                       "Merrill Lynch Far East Limited"]),
    ("Macquarie", ["Macquarie Asia Securities Limited",
                   "MACQUARIE CAPITAL LIMITED",
                   "MACQUARIE FUNDS MANAGEMENT HONG KONG LIMITED",
                   "Macquarie Markets Trading Limited"]),
    ("Barclays", ["BARCLAYS CAPITAL ASIA LIMITED"]),
    ("BNP Paribas", ["BNP PARIBAS ASSET MANAGEMENT ASIA LIMITED",
                     "BNP PARIBAS SECURITIES (ASIA) LIMITED"]),
    ("DBS", ["DBS ASIA CAPITAL LIMITED",
             "DBS VICKERS (HONG KONG) LIMITED"]),
    ("CLSA", ["CITIC CLSA Capital Partners HK Limited",
              "CLSA LIMITED"]),
    ("CITIC", ["CITIC CFI Asset Management Company Limited",
               "CITIC CFI Securities Company Limited",
               "CITIC Futures International Company Limited",
               "CITIC Securities (Hong Kong) Limited",
               "CITIC Securities Asset Management (HK) Limited",
               "CITIC Securities Brokerage (HK) Limited",
               "CITIC Securities Futures (HK) Limited",
               "CITIC Securities International Global Markets Limited"]),
    ("Huatai", ["Huatai (Hong Kong) Futures Limited",
                "HUATAI FINANCIAL HOLDINGS (HONG KONG) LIMITED"]),
    ("CICC", ["CHINA INTERNATIONAL CAPITAL CORPORATION HONG KONG ASSET MANAGEMENT LIMITED",
              "CHINA INTERNATIONAL CAPITAL CORPORATION HONG KONG FUTURES LIMITED",
              "CHINA INTERNATIONAL CAPITAL CORPORATION HONG KONG SECURITIES LIMITED"]),
    ("Haitong", ["HAITONG INTERNATIONAL ASSET MANAGEMENT (HK) LIMITED",
                 "HAITONG INTERNATIONAL ASSET MANAGEMENT LIMITED",
                 "HAITONG INTERNATIONAL CAPITAL LIMITED",
                 "HAITONG INTERNATIONAL FUTURES LIMITED",
                 "HAITONG INTERNATIONAL INVESTMENT MANAGERS LIMITED",
                 "HAITONG INTERNATIONAL RESEARCH LIMITED",
                 "HAITONG INTERNATIONAL SECURITIES COMPANY LIMITED"]),
    ("CMB International", ["CMB International Asset Management Limited",
                           "CMB International Capital Limited",
                           "CMB INTERNATIONAL FUTURES LIMITED",
                           "CMB International Global Markets Limited",
                           "CMB International Securities Limited"]),
    ("CSC (中信建投)", ["China Securities (International) Asset Management Company Limited",
                        "China Securities (International) Brokerage Company Limited",
                        "China Securities (International) Corporate Finance Company Limited"]),
]


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


ABBREV = [
    (r"\bCOMPANY LIMITED\b", "CO LTD"),
    (r"\bL\s+L\s+C\b", "LLC"),
    (r"\bL\s+L\s+P\b", "LLP"),
    (r"\bINTERNATIONAL\b", "INTL"),
    (r"\bMANAGEMENT\b", "MGT"),
    (r"\bSECURITIES\b", "SECS"),
    (r"\bHOLDINGS\b", "HLDGS"),
    (r"\bCORPORATION\b", "CORP"),
    (r"\bBROKERAGE\b", "BKG"),
    (r"\bASSET\b", "ASSET"),
]


def norm(s):
    s = (s or "").upper()
    s = s.replace("&", " AND ")
    s = re.sub(r"[.,()'’\-/]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    for pat, rep in ABBREV:
        s = re.sub(pat, rep, s)
    return re.sub(r"\s+", " ", s).strip()


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


STOP = {"LIMITED", "LTD", "THE", "CO", "COMPANY", "HK", "LLC", "LLP"}


def tokens(s):
    return [t for t in norm(s).split() if t not in STOP]


def clean_name(s):
    """Drop '(trading as ...)' / '(formerly ...)' suffixes before comparing."""
    s = (s or "").strip()
    s = re.sub(r"\((?:trading as|formerly)[^)]*\)", " ", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def cand_name(it):
    return clean_name(it.get("entityName") or it.get("name") or "")


def score(candidate, target):
    ct, tt = tokens(clean_name(candidate)), tokens(clean_name(target))
    if not ct or not tt:
        return 0
    cs, ts = set(ct), set(tt)
    inter = len(cs & ts)
    union = len(cs | ts)
    j = inter / union if union else 0
    bonus = 0.15 if norm(candidate) == norm(target) else 0
    return j + bonus


def pick(name, items):
    """Pick the right record from a result set; strict before loose."""
    tn = norm(clean_name(name))
    tset = set(tokens(name))
    for it in items:
        if norm(cand_name(it)) == tn:
            return it, 1.0, "exact"
    for it in items:
        cn = norm(cand_name(it))
        if cn.startswith(tn + " ") or cn.endswith(" " + tn) or (" " + tn + " ") in (" " + cn + " "):
            return it, 0.95, "contains"
    if len(items) == 1:
        return items[0], score(cand_name(items[0]), name), "only-candidate"
    best = max(items, key=lambda it: score(cand_name(it), name))
    s = score(cand_name(best), name)
    if tset <= set(tokens(cand_name(best))) and len(tokens(cand_name(best))) <= len(tset) + 4 and s >= 0.6:
        return best, s, "subset"
    return None, s, "ambiguous"


def resolve(name):
    """Return (record, score, how, tried_queries) for one input name.

    Strategy: try the most distinctive queries first (full name, then name with
    its Hong Kong / Asia qualifier), and only accept a record that matches the
    input name. Anything unclear is flagged instead of guessed.
    """
    tried = []
    tk = tokens(name)
    queries = dedupe([name, " ".join(tk[:6]), " ".join(tk[:5]), " ".join(tk[:4]),
                      " ".join(tk[:3]), " ".join(tk[:2]), tk[0] if tk else ""])
    extra = [t for t in ("HONG", "KONG", "ASIA") if t in tk]
    if extra:
        for head_n in (4, 3, 2):
            if len(tk) >= head_n:
                queries.insert(1, " ".join(tk[:head_n] + extra))
    fallback_items = None
    for q in queries:
        if not q:
            continue
        tried.append(q)
        res = search(q)
        items = [it for it in res.get("items", []) if it.get("isCorp")]
        if not items:
            continue
        items.sort(key=lambda it: (-score(cand_name(it), name), it.get("ceref") or ""))
        it, s, how = pick(name, items)
        if it and (how in ("exact", "contains") or s >= 0.8):
            return it, s, how, tried
    if fallback_items:
        best = max(fallback_items, key=lambda it: score(cand_name(it), name))
        return best, score(cand_name(best), name), "AMBIGUOUS", tried
    # last resort: look in the "active and inactive" register
    for q in queries:
        if not q:
            continue
        res = search(q, licstatus="all")
        items = [it for it in res.get("items", []) if it.get("isCorp")]
        if not items:
            continue
        items.sort(key=lambda it: (-score(cand_name(it), name), it.get("ceref") or ""))
        it, s, how = pick(name, items)
        if it:
            return it, s, "inactive:" + how, tried
    return None, 0, "not-found", tried


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
    print("entities: %d" % len(names), file=sys.stderr)

    # map each input entity -> group label
    input_to_group = {}
    for gname, members in GROUPS_RAW:
        for m in members:
            input_to_group[norm(m)] = gname

    results = []
    for name in names:
        it, s, how, tried = resolve(name)
        if not it:
            results.append({"input": name, "group": input_to_group.get(norm(name), name),
                            "ceref": None, "sfc_name": None, "status": "NOT FOUND",
                            "match": how, "note": "queries tried: " + " | ".join(tried)})
            print("NOT FOUND: %s" % name, file=sys.stderr)
            continue
        ceref = it.get("ceref")
        sfc_name = it.get("entityName") or it.get("name")
        note = "" if how in ("exact", "contains") else "match=%s score=%.2f queries=%s" % (how, s, " | ".join(tried))
        active = "Y" if it.get("hasActiveLicence") == "Y" else "N"
        results.append({"input": name, "group": input_to_group.get(norm(name), name),
                        "ceref": ceref, "sfc_name": sfc_name,
                        "status": "active" if active == "Y" else "inactive",
                        "match": how, "note": note})
        print("%-62s -> %-8s %-58s [%s %.2f]" % (name[:62], ceref, (sfc_name or "")[:58], how, s), file=sys.stderr)

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

    # ---- group aggregation: sum entities per group, de-duped by CE No. ----
    name_to_group = {}
    for gname, members in GROUPS_RAW:
        for m in members:
            name_to_group[norm(m)] = gname
    ce_to_group = {}
    for r in per_company:
        if r["ceref"]:
            ce_to_group[r["ceref"]] = r.get("group") or name_to_group.get(norm(r["input"]), r["input"])
    sfc_to_ce = {r["sfc_name"]: r["ceref"] for r in per_company if r["ceref"]}

    order = [g[0] for g in GROUPS_RAW]
    buckets = OrderedDict((g, []) for g in order)
    for r in per_company:
        g = ce_to_group.get(r["ceref"]) if r["ceref"] else name_to_group.get(norm(r["input"]))
        if g in buckets:
            buckets[g].append(r)
        elif r["ceref"]:
            buckets.setdefault(r["input"], []).append(r)

    groups = []
    for gname, ents in buckets.items():
        if not ents:
            continue
        resolved = [e for e in ents if e["ceref"]]
        ce_set = set()
        for p in people.values():
            for cn in p["companies"]:
                ce = sfc_to_ce.get(cn)
                if ce and ce_to_group.get(ce) == gname:
                    ce_set.add(p["ceRef"])
                    break
        groups.append({"group": gname, "ents": ents,
                       "ro": sum(e["ro"] for e in ents),
                       "rep": sum(e["rep"] for e in ents),
                       "unique": len(ce_set)})
    print("\n--- groups ---", file=sys.stderr)
    for g in groups:
        print("%-22s entities=%2d RO=%3d Rep=%4d unique=%4d" %
              (g["group"], len(g["ents"]), g["ro"], g["rep"], g["unique"]), file=sys.stderr)

    # entity-level CSV
    with open(os.path.join(OUT_DIR, "sfc_sellside_entity_detail.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Group", "Input name", "CE No.", "SFC registered name", "Licence status",
                    "Match", "ROs", "Representatives", "Unique people (entity)", "Note"])
        for p in per_company:
            w.writerow([p.get("group", ""), p["input"], p["ceref"] or "", p["sfc_name"] or "", p["status"],
                        p.get("match", ""), p["ro"], p["rep"], p["unique"], p.get("note", "")])

    # group-level CSV
    with open(os.path.join(OUT_DIR, "sfc_sellside_group_summary.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["#", "集团", "实体数", "ROs", "Representatives", "独立人数（集团内按 CE No. 去重）"])
        for i, g in enumerate(groups, 1):
            w.writerow([i, g["group"], len(g["ents"]), g["ro"], g["rep"], g["unique"]])
        w.writerow(["", "TOTAL", sum(len(g["ents"]) for g in groups),
                    sum(g["ro"] for g in groups), sum(g["rep"] for g in groups),
                    sum(g["unique"] for g in groups)])

    # people CSV
    with open(os.path.join(OUT_DIR, "sfc_sellside_people_unique.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["CE No.", "Name", "Chinese name", "Roles", "集团", "所属公司"])
        for ce, rec in sorted(people.items(), key=lambda kv: (kv[1]["name"] or "").upper()):
            grp = sorted(set(ce_to_group.get(sfc_to_ce.get(cn, ""), "")
                             for cn in rec["companies"] if sfc_to_ce.get(cn)))
            w.writerow([ce, rec["name"], rec["nameChi"] or "", "+".join(sorted(rec["roles"])),
                        "; ".join([g for g in grp if g]), "; ".join(sorted(set(rec["companies"])))])

    summary = {
        "entities_input": len(names),
        "entities_resolved": sum(1 for p in per_company if p["ceref"]),
        "groups": len(groups),
        "sum_of_entity_unique": sum_unique,
        "sum_of_group_unique": sum(g["unique"] for g in groups),
        "global_unique_people": unique_total,
        "cross_entity_duplicates_removed": overlap,
        "total_ro_rows": sum(p["ro"] for p in per_company),
        "total_rep_rows": sum(p["rep"] for p in per_company),
    }
    with open(os.path.join(OUT_DIR, "sfc_sellside_result.json"), "w", encoding="utf-8") as f:
        json.dump({"summary": summary,
                   "groups": [{"group": g["group"],
                               "entities": [{k: v for k, v in e.items()} for e in g["ents"]],
                               "ro": g["ro"], "rep": g["rep"], "unique": g["unique"]} for g in groups],
                   "companies": per_company,
                   "people": [{"ceRef": ce, "name": r["name"], "nameChi": r["nameChi"],
                               "roles": sorted(r["roles"]), "companies": sorted(set(r["companies"]))}
                              for ce, r in people.items()]},
                  f, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
