# SFC 持牌人统计（Buy-side + Sell-side）

统计香港证监会（SFC）公众纪录册上，一批持牌法团的 **Responsible Officers（RO）** 与 **Representatives** 人数，按 **CE No. 去重**。

线上报告：<https://tamyanying95-afk.github.io/sfc/>

---

## 目录结构

```
index.html                 发布页（由 build_combined_report.py 生成）
sfc_20261006.xlsx          数据表，按抓取日期命名 sfc_yyyymmdd.xlsx，每月留存一份
scripts/
  sfc_headcount.py        ① 抓取 buy-side（19 组 / 22 实体）
  sfc_sellside_headcount.py  ② 抓取 sell-side（18 组 / 68 实体）
  build_combined_report.py ③ 合并出总表 + Excel + CSV
  build_report.py          （可选）只出 buy-side 报告
  build_sellside_report.py （可选）只出 sell-side 报告
.github/workflows/refresh.yml  每周一自动刷新 + 手动触发
```

抓取结果写入 `scripts/output/`（`sfc_result.json`、`sfc_sellside_result.json` 及中间 CSV），该文件已 gitignore。

---

## 本地运行

```bash
pip install openpyxl          # 仅生成 Excel 时需要

python scripts/sfc_headcount.py
python scripts/sfc_sellside_headcount.py
python scripts/build_combined_report.py

open scripts/output/sfc_combined_report.html
```

三步顺序不能颠倒：①②抓数，③合并。全流程约 5–10 分钟（90 家实体，逐家请求 SFC）。

---

## 自动更新

`.github/workflows/refresh.yml` **每月最后一天** 10:00（香港时间）自动跑一遍，数据有变就把最新的 `index.html` 和 `sfc_yyyymmdd.xlsx` 提交回仓库，GitHub Pages 自动重新发布。**每月一份 Excel，按日期留存，历史版本不会被覆盖。**

> GitHub cron 不支持「最后一天」写法，所以 cron 设成 28–31 号都触发，再用「明天是不是 1 号」判断是否真的是月末；手动触发不受此限制。

**想立刻更新**：仓库 → **Actions** → 左侧 **Refresh SFC data** → 右上角 **Run workflow** → 选 `main` → 绿色确认按钮。约 5–10 分钟后刷新页面即可。

页面顶部有 Excel 下载链接，指向当期 `sfc_yyyymmdd.xlsx`。

---

## 改公司名单

| 改哪边 | 改哪个文件 | 改哪里 |
|---|---|---|
| Buy-side 抓取名单 | `scripts/sfc_headcount.py` | `RAW_COMPANIES` |
| Buy-side 短名 / 类别 / 分组 | `scripts/build_combined_report.py` | `BUY_GROUPS`（三元组：`(短名, 类别, [成员实体])`） |
| Sell-side 抓取名单与分组 | `scripts/sfc_sellside_headcount.py` | `RAW_COMPANIES` + `GROUPS_RAW` |

⚠️ Buy-side 加点人或改名时，**两个文件都要改**：`sfc_headcount.py` 的 `RAW_COMPANIES` 决定抓哪些公司，`build_combined_report.py` 的 `BUY_GROUPS` 决定它们在总表里怎么显示和归组。

同一集团的多家法人实体写在**同一组**里，脚本会自动合并成一行并在集团内去重。

---

## 数据口径

- 数据源：`https://apps.sfc.hk/publicregWeb`（SFC 公众纪录册）
- 筛选条件：licence status = **Active**，SFO licence and/or AMLO licence
- 三个数字：
  - **A 实体去重加总**＝各法人实体各自按 CE No. 去重后直接相加
  - **B 集团内全局去重**＝集团下所有实体人员合并后再去重一次
  - **C 全局去重**＝所有集团合并后再去重一次

同一 CE No. 无论同时是 RO 还是 Representative、或出现在多家公司，都只算一个人。

---

## 抓取接口备忘（换数据源时可复用）

- 名称搜索：`POST https://apps.sfc.hk/publicregWeb/searchByNameJson`，form 参数 `searchbyoption=byname`、`searchtext=<关键字>`、`searchlang=en`、`entityType=corporation`、`licstatus=active|all`、`lictype=all`；`items[].ceref` 即 CE No.
- 详情页：`/publicregWeb/corp/{ceref}/details?locale=en`
- RO 列表：`/publicregWeb/corp/{ceref}/ro`，数据在内嵌 JS `var rorawData = [...]`
- Representatives：`/publicregWeb/corp/{ceref}/rep`，内嵌 `var reprawData = [...]`
- 个人页校验：`/publicregWeb/indi/{ceref}/details`，内嵌 `var indData = [...]`（`prinCeRef` 主事公司、`accStatus/raStatus` A=active）

长名称搜索常返回 0 条，脚本已实现「逐级缩短关键词 + Hong Kong/Asia 限定词」的重试逻辑。
