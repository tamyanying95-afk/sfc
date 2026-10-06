#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render the SFC batch result JSON into a single HTML report + Excel.

Ordering follows the user's original company list. Entities that were typed on
one line (Citadel / Polymer / Fidelity) are merged into a single row whose
"unique people" figure is de-duplicated by CE No. across the merged entities.
"""

import html
import json
import os
import re
from collections import OrderedDict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE_DIR, "output")
data = json.load(open(os.path.join(OUT, "sfc_result.json"), encoding="utf-8"))
s = data["summary"]
companies = data["companies"]          # already in user list order
people = sorted(data["people"], key=lambda p: (p["name"] or "").upper())

# ---------------------------------------------------------------- grouping ---
# Order = the user's original list. A group whose members were written on one
# line is merged (de-duped across its members).
GROUPS = [
    ["MILLENNIUM CAPITAL MANAGEMENT (HONG KONG) LIMITED"],
    ["Point72 Hong Kong Limited"],
    ["Citadel Asia Limited", "Citadel Securities (Hong Kong) Limited"],
    ["MARSHALL WACE ASIA LIMITED"],
    ["Polymer Capital Management (HK) Limited", "POLYMER WEALTH MANAGEMENT COMPANY LIMITED"],
    ["Balyasny Asset Management (Hong Kong) Limited"],
    ["Dymon Asia Capital (HK) Limited"],
    ["Schonfeld Strategic Advisors (Hong Kong) Limited"],
    ["GREENWOODS ASSET MANAGEMENT HONG KONG LIMITED"],
    ["North Rock Capital Management (HK) Limited"],
    ["Aspex Management (HK) Limited"],
    ["Jane Street Asia Pacific Limited"],
    ["BlackRock Asset Management North Asia Limited"],
    ["Wellington Management Hong Kong Limited"],
    ["Fidelity Management & Research (Hong Kong) Limited",
     "First Fidelity Capital (International) Limited"],
    ["T. Rowe Price Hong Kong Limited"],
    ["E FUND MANAGEMENT (HONG KONG) CO., LIMITED"],
    ["INVESCO HONG KONG LIMITED"],
    ["SCHRODER INVESTMENT MANAGEMENT (HONG KONG) LIMITED"],
]


def norm(s):
    s = (s or "").upper().replace("&", " AND ")
    s = re.sub(r"[.,()'’\-/]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


by_input = {norm(c["input"]): c for c in companies}

groups = OrderedDict()
used = set()
for members in GROUPS:
    gname = " + ".join(members) if len(members) > 1 else members[0]
    ents = []
    for m in members:
        c = by_input.get(norm(m))
        if c:
            ents.append(c)
            used.add(c["ceref"])
    if ents:
        groups[gname] = ents
# anything not covered by GROUPS keeps its own row, in list order
for c in companies:
    if c["ceref"] not in used:
        groups[c["input"]] = [c]

# people lookup per company CE
people_by_company = {}
for c in companies:
    people_by_company[c["ceref"]] = c
ce_to_group = {}
for gname, ents in groups.items():
    for e in ents:
        ce_to_group[e["ceref"]] = gname

name_to_ce = {c["sfc_name"]: c["ceref"] for c in companies if c.get("sfc_name")}


def groups_of_person(p):
    ces = [name_to_ce[n] for n in p["companies"] if n in name_to_ce]
    return sorted(set(ce_to_group.get(ce, "") for ce in ces if ce_to_group.get(ce)))


group_rows = []
grand_ro = grand_rep = grand_unique = 0
for gname, ents in groups.items():
    if len(ents) == 1:
        c = ents[0]
        ro, rep, uniq = c["ro"], c["rep"], c["unique"]
        cerefs = c["ceref"]
        sfc_names = c["sfc_name"] or c["input"]
    else:
        ro = sum(e["ro"] for e in ents)
        rep = sum(e["rep"] for e in ents)
        ce_sets = []
        for e in ents:
            ce_sets.append(set())
        # recompute merged unique using the global people map
        ces = set()
        for p in people:
            if gname in groups_of_person(p):
                ces.add(p["ceRef"])
        uniq = len(ces)
        cerefs = " + ".join(e["ceref"] for e in ents)
        sfc_names = "<br>".join(html.escape(e["sfc_name"] or e["input"]) for e in ents)
    grand_ro += ro
    grand_rep += rep
    grand_unique += uniq
    group_rows.append({
        "group": gname, "cerefs": cerefs, "sfc_names": sfc_names,
        "ro": ro, "rep": rep, "unique": uniq, "merged": len(ents) > 1,
    })

rows = []
for g in group_rows:
    links = []
    for part in g["cerefs"].split(" + "):
        links.append("<a href='https://apps.sfc.hk/publicregWeb/corp/%s/details?locale=en' target='_blank'>%s</a>"
                     % (part, part))
    merged_tag = " <span class='tag'>合并去重</span>" if g["merged"] else ""
    rows.append(
        "<tr><td>%s%s</td><td class='sfc'>%s</td><td>%s</td><td class='num'>%s</td>"
        "<td class='num'>%s</td><td class='num strong'>%s</td></tr>"
        % (html.escape(g["group"]), merged_tag, g["sfc_names"], " + ".join(links),
           g["ro"], g["rep"], g["unique"]))

prows = []
for p in people:
    roles = "+".join(p["roles"])
    badge = "both" if len(p["roles"]) > 1 else ("ro" if "RO" in p["roles"] else "rep")
    grp = groups_of_person(p)
    prows.append(
        "<tr><td>%s</td><td>%s</td><td>%s</td><td><span class='badge %s'>%s</span></td><td>%s</td><td>%s</td></tr>"
        % (html.escape(p["ceRef"] or ""), html.escape(p["name"] or ""),
           html.escape(p["nameChi"] or ""), badge, roles,
           html.escape("; ".join(grp)), html.escape("; ".join(p["companies"]))))

html_out = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SFC 持牌人统计报告</title>
<style>
 :root{--bg:#f6f7f9;--card:#fff;--line:#e5e7eb;--text:#111827;--muted:#6b7280;--accent:#1d4ed8;}
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--text);font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;}
 .wrap{max-width:1240px;margin:0 auto;padding:32px 20px 64px}
 h1{font-size:26px;margin:0 0 6px}
 .sub{color:var(--muted);font-size:13px;margin-bottom:24px}
 .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin-bottom:28px}
 .card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px}
 .card .k{font-size:12px;color:var(--muted);letter-spacing:.02em}
 .card .v{font-size:28px;font-weight:650;margin-top:4px}
 .card .h{font-size:12px;color:var(--muted);margin-top:2px}
 table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}
 caption{text-align:left;font-size:17px;font-weight:650;padding:0 0 12px}
 th,td{padding:9px 12px;border-bottom:1px solid var(--line);text-align:left;font-size:14px;vertical-align:top}
 th{background:#f0f2f5;font-weight:600;font-size:13px;color:#374151}
 tr:last-child td{border-bottom:none}
 td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
 td.strong{font-weight:650}
 td.sfc{font-size:13px;color:#374151}
 tfoot td{background:#f0f2f5;font-weight:650}
 .tag{display:inline-block;padding:0 7px;border-radius:6px;font-size:11px;background:#eef2ff;border:1px solid #c7d2fe;color:#4338ca;vertical-align:1px}
 .badge{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;border:1px solid var(--line);background:#f3f4f6;color:#374151}
 .badge.both{background:#fef3c7;border-color:#fde68a;color:#92400e}
 .badge.ro{background:#dbeafe;border-color:#bfdbfe;color:#1e40af}
 .badge.rep{background:#ecfdf5;border-color:#a7f3d0;color:#065f46}
 .note{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:8px;padding:12px 16px;margin:22px 0;font-size:13.5px;color:#374151}
 .note b{color:var(--accent)}
 .muted{color:var(--muted)}
 .scroll{max-height:640px;overflow:auto;border:1px solid var(--line);border-radius:12px}
 .scroll table{border:none;border-radius:0}
 a{color:var(--accent);text-decoration:none}
 a:hover{text-decoration:underline}
</style></head><body><div class="wrap">
<h1>SFC 持牌代表及负责人员（RO）统计 · Buy-side</h1>
<div class="sub">数据源：香港证监会公众纪录册（Public Register of Licensed Persons and Registered Institutions）· licstatus = Active · SFO licence and/or AMLO licence · 抓取日期 __DATE__</div>

<div class="cards">
  <div class="card"><div class="k">公司 / 集团数量</div><div class="v">__NG__</div><div class="h">按你给的名单顺序</div></div>
  <div class="card"><div class="k">合计独立人数（按 CE No. 去重）</div><div class="v">__UNIQ__</div><div class="h">你要的最终数字</div></div>
  <div class="card"><div class="k">Representatives 记录数</div><div class="v">__REP__</div><div class="h">含与 RO 重复者</div></div>
  <div class="card"><div class="k">Responsible Officers 记录数</div><div class="v">__RO__</div><div class="h">同一人可兼任 Rep</div></div>
</div>

<div class="note"><b>计算口径：</b>同一 CE No. 只算一个人 —— 无论其同时是 Representative 与 RO，还是出现在名单中多家公司。
Citadel、Polymer、Fidelity 三组的去重人数是在<b>组内合并去重</b>后得出的（组间不再有重叠）。</div>

<table>
  <caption>按公司汇总（顺序＝你提供的名单）</caption>
  <thead><tr><th>公司 / 集团</th><th>SFC 登记名称</th><th>CE No.</th><th class="num">ROs</th><th class="num">Representatives</th><th class="num">独立人数（去重）</th></tr></thead>
  <tbody>__ROWS__</tbody>
  <tfoot><tr><td>合计 __NG__ 组</td><td></td><td></td><td class="num">__RO__</td><td class="num">__REP__</td><td class="num">__UNIQ__</td></tr></tfoot>
</table>

<div style="height:28px"></div>

<div class="scroll">
<table>
  <caption>去重后人员明细（__PEOPLE__ 人）</caption>
  <thead><tr><th>CE No.</th><th>Name</th><th>中文名</th><th>角色</th><th>所属集团</th><th>所属公司</th></tr></thead>
  <tbody>__PROWS__</tbody>
</table>
</div>

<div class="note"><b>说明：</b>名单由你提供的公司名称解析而成；重复出现的 MARSHALL WACE ASIA LIMITED 只计一次。
部分 SFC 登记名称带 “(trading as …)” 后缀，已按原样保留。CSV 版本见同目录 sfc_company_summary.csv 与 sfc_people_unique.csv。</div>
</div></body></html>
"""

import datetime
html_out = (html_out
            .replace("__DATE__", datetime.date.today().strftime("%Y-%m-%d"))
            .replace("__NG__", str(len(group_rows)))
            .replace("__UNIQ__", str(grand_unique))
            .replace("__REP__", str(grand_rep))
            .replace("__RO__", str(grand_ro))
            .replace("__PEOPLE__", str(len(people)))
            .replace("__ROWS__", "\n".join(rows))
            .replace("__PROWS__", "\n".join(prows)))

with open(os.path.join(OUT, "sfc_report.html"), "w", encoding="utf-8") as f:
    f.write(html_out)

# ------------------------------------------------------------------ Excel ---
try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment
    from openpyxl.utils import get_column_letter
except ImportError:
    raise SystemExit("openpyxl missing")

wb = Workbook()
ws = wb.active
ws.title = "Company summary"
ws.append(["#", "公司 / 集团（按名单顺序）", "SFC 登记名称", "CE No.", "Licence status",
           "ROs", "Representatives", "独立人数（CE No. 去重）", "备注"])
for i, g in enumerate(group_rows, 1):
    ents = groups[g["group"]]
    sfc = " / ".join(e["sfc_name"] or e["input"] for e in ents)
    status = " / ".join(e["status"] for e in ents)
    note = "组内合并去重" if g["merged"] else ""
    ws.append([i, g["group"], sfc, g["cerefs"], status, g["ro"], g["rep"], g["unique"], note])
ws.append(["", "TOTAL", "", "", "", grand_ro, grand_rep, grand_unique, ""])
for cell in ws[1]:
    cell.font = Font(bold=True)
for cell in ws[ws.max_row]:
    cell.font = Font(bold=True)
for col, w in zip("ABCDEFGHI", [5, 46, 60, 18, 14, 8, 16, 22, 14]):
    ws.column_dimensions[col].width = w
for row in ws.iter_rows(min_row=2):
    for cell in row:
        cell.alignment = Alignment(vertical="top", wrap_text=True)

ws2 = wb.create_sheet("People (CE dedupe)")
ws2.append(["CE No.", "Name", "Chinese name", "Roles", "所属集团", "所属公司"])
for p in people:
    grp = groups_of_person(p)
    ws2.append([p["ceRef"], p["name"], p["nameChi"], "+".join(p["roles"]),
                "; ".join(grp), "; ".join(p["companies"])])
for cell in ws2[1]:
    cell.font = Font(bold=True)
for col, w in zip("ABCDEF", [12, 34, 14, 10, 40, 46]):
    ws2.column_dimensions[col].width = w
wb.save(os.path.join(OUT, "sfc_headcount.xlsx"))
print("xlsx + html written; groups=%d unique=%d ro=%d rep=%d" % (len(group_rows), grand_unique, grand_ro, grand_rep))
