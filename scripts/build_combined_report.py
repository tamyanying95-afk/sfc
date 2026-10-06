#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Combine the buy-side and sell-side SFC extracts into one master report.

Each group reports two figures:
  A = 实体去重数字加总  (sum of each legal entity's own CE-deduped headcount)
  B = 集团内全局去重    (CE-deduped across all entities inside the group)
"""

import csv
import datetime
import html
import json
import os
import re
from collections import OrderedDict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE_DIR, "output")

buy = json.load(open(os.path.join(OUT, "sfc_result.json"), encoding="utf-8"))
sell = json.load(open(os.path.join(OUT, "sfc_sellside_result.json"), encoding="utf-8"))


def norm(s):
    s = (s or "").upper().replace("&", " AND ")
    s = re.sub(r"[.,()'’\-/]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# ------------------------------------------------------------ buy-side groups
# (short display name, category, [member entities as typed by the user])
BUY_GROUPS = [
    ("Millennium", "Hedge Funds", ["MILLENNIUM CAPITAL MANAGEMENT (HONG KONG) LIMITED"]),
    ("Point72", "Hedge Funds", ["Point72 Hong Kong Limited"]),
    ("Citadel", "Hedge Funds",
     ["Citadel Asia Limited", "Citadel Securities (Hong Kong) Limited"]),
    ("Marshall Wace", "Hedge Funds", ["MARSHALL WACE ASIA LIMITED"]),
    ("Polymer", "Hedge Funds",
     ["Polymer Capital Management (HK) Limited", "POLYMER WEALTH MANAGEMENT COMPANY LIMITED"]),
    ("Balyasny", "Hedge Funds", ["Balyasny Asset Management (Hong Kong) Limited"]),
    ("Dymon", "Hedge Funds", ["Dymon Asia Capital (HK) Limited"]),
    ("Schonfeld", "Hedge Funds", ["Schonfeld Strategic Advisors (Hong Kong) Limited"]),
    ("Greenwoods", "Hedge Funds", ["GREENWOODS ASSET MANAGEMENT HONG KONG LIMITED"]),
    ("North Rock", "Hedge Funds", ["North Rock Capital Management (HK) Limited"]),
    ("Aspex", "Hedge Funds", ["Aspex Management (HK) Limited"]),
    ("Jane Street", "Quant Trading", ["Jane Street Asia Pacific Limited"]),
    ("BlackRock", "Long Only", ["BlackRock Asset Management North Asia Limited"]),
    ("Wellington", "Long Only", ["Wellington Management Hong Kong Limited"]),
    ("Fidelity", "Long Only",
     ["Fidelity Management & Research (Hong Kong) Limited",
      "First Fidelity Capital (International) Limited"]),
    ("T. Rowe Price", "Long Only", ["T. Rowe Price Hong Kong Limited"]),
    ("E Fund", "Long Only", ["E FUND MANAGEMENT (HONG KONG) CO., LIMITED"]),
    ("Invesco", "Long Only", ["INVESCO HONG KONG LIMITED"]),
    ("Schroder", "Long Only", ["SCHRODER INVESTMENT MANAGEMENT (HONG KONG) LIMITED"]),
]
BUY_CATEGORY_OF = {short: cat for short, cat, _ in BUY_GROUPS}

by_input = {norm(c["input"]): c for c in buy["companies"]}
buy_people = buy["people"]
buy_name2ce = {c["sfc_name"]: c["ceref"] for c in buy["companies"] if c.get("sfc_name")}
buy_ce2g = {}

buy_groups = []          # (group_name, [entity dicts])
for gname, cat, members in BUY_GROUPS:
    ents = [by_input[norm(m)] for m in members if by_input.get(norm(m))]
    if not ents:
        continue
    for e in ents:
        buy_ce2g[e["ceref"]] = gname
    buy_groups.append((gname, ents))
used = {e["ceref"] for _, es in buy_groups for e in es}
for c in buy["companies"]:
    if c["ceref"] not in used:
        buy_ce2g[c["ceref"]] = c["input"]
        buy_groups.append((c["input"], [c]))


def buy_gset(p):
    return {buy_ce2g[buy_name2ce[n]] for n in p["companies"]
            if n in buy_name2ce and buy_ce2g.get(buy_name2ce[n])}


# ----------------------------------------------------------- sell-side groups
sell_people = sell["people"]
sell_ce2g = {}
sell_groups = []
for g in sell["groups"]:
    for e in g["entities"]:
        if e.get("ceref"):
            sell_ce2g[e["ceref"]] = g["group"]
    sell_groups.append((g["group"], g["entities"]))
sell_name2ce = {c["sfc_name"]: c["ceref"] for c in sell["companies"] if c.get("sfc_name")}


def sell_gset(p):
    return {sell_ce2g[sell_name2ce[n]] for n in p["companies"]
            if n in sell_name2ce and sell_ce2g.get(sell_name2ce[n])}


# ------------------------------------------------------------------ assemble
rows = []          # side, group, entities(list), ro, rep, sum_entity, group_unique


def build_row(side, gname, ents, people, gset_fn, category=""):
    ro = sum(e.get("ro", 0) for e in ents)
    rep = sum(e.get("rep", 0) for e in ents)
    sum_entity = sum(e.get("unique", 0) for e in ents)
    if len(ents) == 1:
        uniq = ents[0].get("unique", 0)
    else:
        uniq = len({p["ceRef"] for p in people if gname in gset_fn(p)})
    return {"side": side, "category": category, "group": gname, "entities": ents,
            "ro": ro, "rep": rep, "sum_entity": sum_entity, "unique": uniq}


for gname, ents in buy_groups:
    rows.append(build_row("Buy-side", gname, ents, buy_people, buy_gset,
                          BUY_CATEGORY_OF.get(gname, "")))
for gname, ents in sell_groups:
    rows.append(build_row("Sell-side", gname, ents, sell_people, sell_gset, "Sell-side"))

# ------------------------------------------------- combined people master list
people_map = OrderedDict()
for p in buy_people:
    rec = people_map.setdefault(p["ceRef"], {"name": p["name"], "nameChi": p.get("nameChi"),
                                             "roles": set(), "groups": [], "companies": set(),
                                             "sides": set()})
    rec["roles"].update(p["roles"])
    rec["groups"] += sorted(buy_gset(p))
    rec["companies"].update(p["companies"])
    rec["sides"].add("Buy-side")
for p in sell_people:
    rec = people_map.setdefault(p["ceRef"], {"name": p["name"], "nameChi": p.get("nameChi"),
                                             "roles": set(), "groups": [], "companies": set(),
                                             "sides": set()})
    rec["roles"].update(p["roles"])
    rec["groups"] += sorted(sell_gset(p))
    rec["companies"].update(p["companies"])
    rec["sides"].add("Sell-side")
for ce, rec in people_map.items():
    rec["groups"] = sorted(set(rec["groups"]))
    rec["sides"] = sorted(rec["sides"])
people_list = sorted(({"ceRef": ce, **r} for ce, r in people_map.items()),
                     key=lambda x: (x["name"] or "").upper())

# ------------------------------------------------------------------- totals
def agg(sel):
    sub = [r for r in rows if r["side"] == sel]
    return {"n": len(sub), "ent": sum(len(r["entities"]) for r in sub),
            "ro": sum(r["ro"] for r in sub), "rep": sum(r["rep"] for r in sub),
            "sum_entity": sum(r["sum_entity"] for r in sub),
            "unique": sum(r["unique"] for r in sub),
            "dup": sum(r["sum_entity"] - r["unique"] for r in sub)}


def agg_cat(cat):
    sub = [r for r in rows if r["category"] == cat]
    return {"n": len(sub), "ent": sum(len(r["entities"]) for r in sub),
            "ro": sum(r["ro"] for r in sub), "rep": sum(r["rep"] for r in sub),
            "sum_entity": sum(r["sum_entity"] for r in sub),
            "unique": sum(r["unique"] for r in sub),
            "dup": sum(r["sum_entity"] - r["unique"] for r in sub)}


tb, ts = agg("Buy-side"), agg("Sell-side")
tg = {"n": tb["n"] + ts["n"], "ent": tb["ent"] + ts["ent"], "ro": tb["ro"] + ts["ro"],
      "rep": tb["rep"] + ts["rep"], "sum_entity": tb["sum_entity"] + ts["sum_entity"],
      "unique": tb["unique"] + ts["unique"], "dup": tb["dup"] + ts["dup"]}
global_unique = len(people_map)
cross_group_dup = tg["unique"] - global_unique

fmt = lambda n: "{:,}".format(n)

# ------------------------------------------------------------------- HTML ---
def ceref_links(ents):
    out = []
    for e in ents:
        c = e.get("ceref")
        if not c:
            continue
        out.append("<a href='https://apps.sfc.hk/publicregWeb/corp/%s/details?locale=en' "
                   "target='_blank'>%s</a>" % (c, c))
    return " ".join(out)


def side_badge(side):
    cls = "buy" if side == "Buy-side" else "sell"
    return "<span class='side %s'>%s</span>" % (cls, side)


CAT_CLS = {"Hedge Funds": "hf", "Quant Trading": "qt", "Long Only": "lo", "Sell-side": "ss"}


def cat_cell(cat):
    if not cat:
        return ""
    return "<span class='cat %s'>%s</span>" % (CAT_CLS.get(cat, "ss"), html.escape(cat))


def tf_row(label, d, span=5):
    return ("<tr><td colspan='%d'>%s</td><td class='num'>%d</td><td class='num'>%s</td>"
            "<td class='num'>%s</td><td class='num'>%s</td><td class='num'>%s</td></tr>"
            % (span, label, d["ent"], fmt(d["ro"]), fmt(d["rep"]),
               fmt(d["sum_entity"]), fmt(d["unique"])))


body_rows = []
idx = 0
prev_side = None
for r in rows:
    idx += 1
    ents = r["entities"]
    def ent_cell(e):
        ce = e.get("ceref") or ""
        nm = html.escape(e.get("sfc_name") or e.get("input") or "")
        if ce:
            return ("<a class='ce' href='https://apps.sfc.hk/publicregWeb/corp/%s/details?locale=en' "
                    "target='_blank' rel='noopener'>%s</a>" % (ce, html.escape(ce)))
        return nm

    names = "<br>".join(ent_cell(e) for e in ents)
    tag = " <span class='tag'>合并</span>" if len(ents) > 1 else ""
    cls = " class='sep'" if prev_side and r["side"] != prev_side else ""
    prev_side = r["side"]
    body_rows.append(
        "<tr%s><td class='num muted'>%d</td><td>%s</td><td>%s</td><td>%s%s</td><td class='sfc'>%s</td>"
        "<td class='num'>%d</td><td class='num'>%d</td><td class='num'>%d</td>"
        "<td class='num'>%s</td><td class='num'>%s</td></tr>"
        % (cls, idx, side_badge(r["side"]), cat_cell(r["category"]),
           html.escape(r["group"]), tag, names,
           len(ents), r["ro"], r["rep"], fmt(r["sum_entity"]), fmt(r["unique"])))


prows = []
for p in people_list:
    roles = "+".join(sorted(p["roles"]))
    badge = "both" if len(p["roles"]) > 1 else ("ro" if "RO" in p["roles"] else "rep")
    prows.append(
        "<tr><td>%s</td><td>%s</td><td>%s</td><td><span class='badge %s'>%s</span></td>"
        "<td>%s</td><td>%s</td><td class='sfc'>%s</td></tr>"
        % (html.escape(p["ceRef"] or ""), html.escape(p["name"] or ""),
           html.escape(p["nameChi"] or ""), badge, roles,
           html.escape("/".join(p["sides"])), html.escape("; ".join(p["groups"])),
           html.escape("; ".join(sorted(p["companies"])))))

TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SFC 持牌人统计总表 · Buy-side + Sell-side</title>
<style>
 :root{--bg:#f6f7f9;--card:#fff;--line:#e5e7eb;--text:#111827;--muted:#6b7280;--accent:#1d4ed8;}
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--text);font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;}
 .wrap{max-width:1400px;margin:0 auto;padding:32px 20px 64px}
 h1{font-size:26px;margin:0 0 6px}
 .sub{color:var(--muted);font-size:13px;margin-bottom:24px}
 .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px;margin-bottom:26px}
 .card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px}
 .card .k{font-size:12px;color:var(--muted)}
 .card .v{font-size:27px;font-weight:650;margin-top:4px;font-variant-numeric:tabular-nums}
 .card .h{font-size:12px;color:var(--muted);margin-top:2px}
 .card.hl{background:#eff6ff;border-color:#bfdbfe}
 table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}
 caption{text-align:left;font-size:17px;font-weight:650;padding:0 0 12px}
 th,td{padding:8px 11px;border-bottom:1px solid var(--line);text-align:left;font-size:13.5px;vertical-align:top}
 th{background:#f0f2f5;font-weight:600;font-size:12.5px;color:#374151}
 tr:last-child td{border-bottom:none}
 tr.sep td{border-top:2px solid #cbd5e1}
 td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
 td.strong{font-weight:650}
 td.sfc{font-size:12px;color:#4b5563;line-height:1.45}
 tfoot td{background:#f0f2f5;font-weight:600}
 .side{display:inline-block;padding:1px 8px;border-radius:6px;font-size:11.5px;white-space:nowrap}
 .side.buy{background:#ecfdf5;border:1px solid #a7f3d0;color:#065f46}
 .side.sell{background:#fef3c7;border:1px solid #fde68a;color:#92400e}
 .cat{display:inline-block;padding:1px 8px;border-radius:6px;font-size:11.5px;white-space:nowrap}
 .cat.hf{background:#fee2e2;border:1px solid #fecaca;color:#991b1b}
 .cat.qt{background:#ede9fe;border:1px solid #ddd6fe;color:#5b21b6}
 .cat.lo{background:#dbeafe;border:1px solid #bfdbfe;color:#1e40af}
 .cat.ss{background:#f3f4f6;border:1px solid var(--line);color:#4b5563}
 .tag{display:inline-block;padding:0 7px;border-radius:6px;font-size:11px;background:#eef2ff;border:1px solid #c7d2fe;color:#4338ca;vertical-align:1px}
 .badge{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;border:1px solid var(--line);background:#f3f4f6;color:#374151}
 .badge.both{background:#fef3c7;border-color:#fde68a;color:#92400e}
 .badge.ro{background:#dbeafe;border-color:#bfdbfe;color:#1e40af}
 .badge.rep{background:#ecfdf5;border-color:#a7f3d0;color:#065f46}
 .note{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:8px;padding:12px 16px;margin:22px 0;font-size:13.5px;color:#374151}
 .note b{color:var(--accent)}
 .warn{border-left-color:#d97706}
 .warn b{color:#b45309}
 .muted{color:var(--muted)}
 .scroll{max-height:660px;overflow:auto;border:1px solid var(--line);border-radius:12px}
 .scroll table{border:none;border-radius:0}
 .scroll thead th{position:sticky;top:0;z-index:2}
 a{color:var(--accent);text-decoration:none}
 a:hover{text-decoration:underline}
 a.ce{font-weight:650;white-space:nowrap}
 td.sfc{white-space:normal}
</style></head><body><div class="wrap">
<h1>SFC 持牌代表及负责人员（RO）统计 · 总表</h1>
<div class="sub">Buy-side __NB__ 组 + Sell-side __NS__ 组 · 数据源：香港证监会公众纪录册 · licstatus = Active · SFO licence and/or AMLO licence · 抓取日期 __DATE__</div>
<div class="sub"><a class="ce" href="output/sfc___STAMP__.xlsx">下载 Excel（output/sfc___STAMP__.xlsx · 总表 / 实体明细 / 人员明细）</a></div>

<div class="cards">
  <div class="card"><div class="k">集团 / 公司数</div><div class="v">__NG__</div><div class="h">法人实体 __NE__ 家</div></div>
  <div class="card"><div class="k">A · 实体去重数字加总</div><div class="v">__A__</div><div class="h">各实体各自去重后相加</div></div>
  <div class="card"><div class="k">B · 集团内全局去重</div><div class="v">__B__</div><div class="h">集团内跨实体再去重</div></div>
  <div class="card"><div class="k">C · 全局去重（37 组合并）</div><div class="v">__C__</div><div class="h">跨集团重复 __XD__ 人</div></div>
</div>

<div class="note"><b>两个数字的区别：</b><br>
<b>A · 实体去重数字加总</b>＝每个法人实体先各自按 CE No. 去重，再把实体数字直接相加（同一人在同一集团的两家实体挂名会被重复计算）。<br>
<b>B · 集团内全局去重</b>＝把集团下所有实体的人员合并，再按 CE No. 去重一次（同一人只算一个）。</div>

<table>
  <caption>总表</caption>
  <thead><tr>
    <th class="num">#</th><th>阵营</th><th>类别</th><th>集团 / 公司</th><th>SFC CE No.（点击查册）</th>
    <th class="num">实体</th><th class="num">ROs</th><th class="num">Reps</th>
    <th class="num">A 实体去重加总</th><th class="num">B 集团全局去重</th>
  </tr></thead>
  <tbody>__ROWS__</tbody>
  <tfoot>
    __TFHF____TFQT____TFLO____TFB____TFS____TFT__
  </tfoot>
</table>

<div class="note warn"><b>跨集团重复：</b>CITIC 与 CLSA 之间有 <b>970</b> 人属同一批（同一 CE No. 同时受聘两边，抽查状态均为 Active）。
因此 B 的合计 __B__ 再全局去重后为 <b>__C__</b> 人（差 __XD__，全部来自 CITIC / CLSA，其余集团之间零重叠）。
若把 CITIC + CLSA 视作一个体系，合并后为 <b>1,918</b> 人。</div>

</div></body></html>
"""

out = (TEMPLATE
       .replace("__DATE__", datetime.date.today().strftime("%Y-%m-%d"))
       .replace("__STAMP__", datetime.date.today().strftime("%Y%m%d"))
       .replace("__NB__", str(tb["n"])).replace("__NS__", str(ts["n"]))
       .replace("__NG__", str(tg["n"])).replace("__NE__", str(tg["ent"]))
       .replace("__A__", fmt(tg["sum_entity"])).replace("__B__", fmt(tg["unique"]))
       .replace("__C__", fmt(global_unique)).replace("__XD__", fmt(cross_group_dup))
       .replace("__PEOPLE__", fmt(len(people_list)))
       .replace("__ROWS__", "\n".join(body_rows))
       .replace("__TFB__", tf_row("Buy-side 小计（%d 组）" % tb["n"], tb))
       .replace("__TFHF__", tf_row("&nbsp;&nbsp;Hedge Funds 小计（%d 组）" % agg_cat("Hedge Funds")["n"],
                                   agg_cat("Hedge Funds")))
       .replace("__TFQT__", tf_row("&nbsp;&nbsp;Quant Trading 小计（%d 组）" % agg_cat("Quant Trading")["n"],
                                   agg_cat("Quant Trading")))
       .replace("__TFLO__", tf_row("&nbsp;&nbsp;Long Only 小计（%d 组）" % agg_cat("Long Only")["n"],
                                   agg_cat("Long Only")))
       .replace("__TFS__", tf_row("Sell-side 小计（%d 组）" % ts["n"], ts))
       .replace("__TFT__", tf_row("合计（%d 组）" % tg["n"], tg))
       .replace("__PROWS__", "\n".join(prows)))

with open(os.path.join(OUT, "sfc_combined_report.html"), "w", encoding="utf-8") as f:
    f.write(out)

# ------------------------------------------------------------------- CSV ----
with open(os.path.join(OUT, "sfc_combined_group_summary.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["#", "阵营", "类别", "集团 / 公司", "实体数", "CE No.", "SFC 登记名称",
                "ROs", "Representatives", "A 实体去重加总", "B 集团全局去重"])
    for i, r in enumerate(rows, 1):
        w.writerow([i, r["side"], r["category"], r["group"], len(r["entities"]),
                    " + ".join(e.get("ceref") or "" for e in r["entities"]),
                    " / ".join(e.get("sfc_name") or e.get("input") or "" for e in r["entities"]),
                    r["ro"], r["rep"], r["sum_entity"], r["unique"]])
    w.writerow([])
    for lbl, d in (("Hedge Funds 小计", agg_cat("Hedge Funds")),
                   ("Quant Trading 小计", agg_cat("Quant Trading")),
                   ("Long Only 小计", agg_cat("Long Only")),
                   ("Buy-side 小计", tb), ("Sell-side 小计", ts), ("合计", tg)):
        w.writerow(["", lbl, "", "", d["ent"], "", "", d["ro"], d["rep"],
                    d["sum_entity"], d["unique"]])
    w.writerow(["", "全局去重（跨集团）", "", "", tg["ent"], "", "", "", "", global_unique])

with open(os.path.join(OUT, "sfc_combined_entity_detail.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["阵营", "类别", "集团 / 公司", "实体名称（输入）", "SFC 登记名称", "CE No.",
                "Licence status", "ROs", "Representatives", "实体去重人数"])
    for r in rows:
        for e in r["entities"]:
            w.writerow([r["side"], r["category"], r["group"], e.get("input") or "",
                        e.get("sfc_name") or "", e.get("ceref") or "", e.get("status") or "",
                        e.get("ro", 0), e.get("rep", 0), e.get("unique", 0)])

with open(os.path.join(OUT, "sfc_combined_people_unique.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["CE No.", "Name", "中文名", "Roles", "阵营", "所属集团", "所属公司"])
    for p in people_list:
        w.writerow([p["ceRef"], p["name"], p["nameChi"] or "", "+".join(sorted(p["roles"])),
                    "/".join(p["sides"]), "; ".join(p["groups"]), "; ".join(sorted(p["companies"]))])

# ----------------------------------------------------------------- Excel ----
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill

wb = Workbook()
ws = wb.active
ws.title = "总表"
ws.append(["#", "阵营", "类别", "集团 / 公司", "实体数", "CE No.", "SFC 登记名称", "Licence status",
           "ROs", "Representatives", "A 实体去重加总", "B 集团全局去重"])
for i, r in enumerate(rows, 1):
    ws.append([i, r["side"], r["category"], r["group"], len(r["entities"]),
               " + ".join(e.get("ceref") or "" for e in r["entities"]),
               "\n".join(e.get("sfc_name") or e.get("input") or "" for e in r["entities"]),
               " / ".join(e.get("status") or "" for e in r["entities"]),
               r["ro"], r["rep"], r["sum_entity"], r["unique"]])
for lbl, d in (("  Hedge Funds 小计", agg_cat("Hedge Funds")),
               ("  Quant Trading 小计", agg_cat("Quant Trading")),
               ("  Long Only 小计", agg_cat("Long Only")),
               ("Buy-side 小计（%d 组）" % tb["n"], tb),
               ("Sell-side 小计（%d 组）" % ts["n"], ts),
               ("合计（%d 组）" % tg["n"], tg)):
    ws.append(["", lbl, "", "", d["ent"], "", "", "", d["ro"], d["rep"],
               d["sum_entity"], d["unique"]])
ws.append(["", "全局去重（跨集团再合并）", "", "", tg["ent"], "", "", "", "", "",
           "", global_unique])
n = len(rows)
bold_rows = {1, n + 2, n + 3, n + 4, n + 5, n + 6, n + 7, n + 8}
for rn in bold_rows:
    for cell in ws[rn]:
        cell.font = Font(bold=True)
fill = PatternFill("solid", fgColor="FEF3C7")
for cell in ws[ws.max_row]:
    cell.fill = fill
for col, width in zip("ABCDEFGHIJKL", [5, 11, 14, 30, 7, 20, 62, 14, 8, 15, 16, 16]):
    ws.column_dimensions[col].width = width
for row in ws.iter_rows(min_row=2):
    for cell in row:
        cell.alignment = Alignment(vertical="top", wrap_text=True)
ws.freeze_panes = "A2"

ws2 = wb.create_sheet("实体明细")
ws2.append(["阵营", "类别", "集团 / 公司", "实体名称（输入）", "SFC 登记名称", "CE No.",
            "Licence status", "ROs", "Representatives", "实体去重人数"])
for r in rows:
    for e in r["entities"]:
        ws2.append([r["side"], r["category"], r["group"], e.get("input") or "",
                    e.get("sfc_name") or "", e.get("ceref") or "", e.get("status") or "",
                    e.get("ro", 0), e.get("rep", 0), e.get("unique", 0)])
for cell in ws2[1]:
    cell.font = Font(bold=True)
for col, width in zip("ABCDEFGHIJ", [11, 14, 26, 58, 58, 10, 14, 8, 15, 14]):
    ws2.column_dimensions[col].width = width
ws2.freeze_panes = "A2"

ws3 = wb.create_sheet("人员明细(去重)")
ws3.append(["CE No.", "Name", "中文名", "Roles", "阵营", "所属集团", "所属公司"])
for p in people_list:
    ws3.append([p["ceRef"], p["name"], p["nameChi"] or "", "+".join(sorted(p["roles"])),
                "/".join(p["sides"]), "; ".join(p["groups"]), "; ".join(sorted(p["companies"]))])
for cell in ws3[1]:
    cell.font = Font(bold=True)
for col, width in zip("ABCDEFG", [12, 34, 14, 10, 12, 40, 60]):
    ws3.column_dimensions[col].width = width
ws3.freeze_panes = "A2"
wb.save(os.path.join(OUT, "sfc_combined.xlsx"))

print("A(实体加总)=%d  B(集团去重)=%d  C(全局去重)=%d  跨集团重复=%d  人数=%d  实体=%d"
      % (tg["sum_entity"], tg["unique"], global_unique, cross_group_dup, len(people_list), tg["ent"]))
print("buy: n=%d ent=%d A=%d B=%d | sell: n=%d ent=%d A=%d B=%d"
      % (tb["n"], tb["ent"], tb["sum_entity"], tb["unique"],
         ts["n"], ts["ent"], ts["sum_entity"], ts["unique"]))
