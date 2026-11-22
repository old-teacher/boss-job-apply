# -*- coding: utf-8 -*-
"""读取本人标注后的拍板表，拆出 apply / exclude / blank 三组。

支持 .xlsx（openpyxl）与 .csv。决策列含「不投」→ exclude；含「可投」且不含「不投」→ apply；
空值 → blank（继续挂起）。eid 从岗位链接末段提取。

用法:
    python parse_annotation.py --sheet decision_sheet.xlsx [--out annotation_result.json]
"""
import argparse, csv, json, os, re, sys


def eid_from_url(url: str):
    m = re.search(r"job_detail/([^/?#]+)", url or "")
    eid = m.group(1) if m else ""
    return re.sub(r"\.html$", "", eid)


def rows_from(path: str):
    if path.lower().endswith(".csv"):
        with open(path, encoding="utf-8-sig", newline="") as f:
            return list(csv.reader(f))
    from openpyxl import load_workbook
    ws = load_workbook(path, read_only=True).active
    return [[("" if c is None else str(c)) for c in row] for row in ws.iter_rows(values_only=True)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", required=True)
    ap.add_argument("--out", default="annotation_result.json")
    a = ap.parse_args()

    rows = rows_from(a.sheet)
    header = rows[0]
    # 定位列：按表头名兜底，默认 公司2/岗位3/链接9/末列决策
    def col(name, default):
        for i, h in enumerate(header):
            if name in h:
                return i
        return default

    ci_co, ci_ti, ci_url, ci_dec = col("公司", 1), col("岗位", 2), col("链接", 8), len(header) - 1

    apply_ids, exclude, blank, detail = [], [], [], []
    for r in rows[1:]:
        if len(r) <= max(ci_co, ci_ti, ci_url, ci_dec):
            continue
        if not r[ci_co].strip() and not r[ci_ti].strip():
            continue
        eid = eid_from_url(r[ci_url])
        dec = r[ci_dec].strip()
        if "不投" in dec:
            verdict = "exclude"
            exclude.append({"eid": eid, "reason": f"本人标注：{dec}"})
        elif "可投" in dec:
            verdict = "apply"
            apply_ids.append(eid)
        else:
            verdict = "blank"
            blank.append(eid)
        detail.append({"eid": eid, "company": r[ci_co], "title": r[ci_ti],
                       "decision": dec, "verdict": verdict})

    out = {"apply": apply_ids, "exclude": exclude, "blank": blank, "rows": detail}
    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"apply: {len(apply_ids)} | exclude: {len(exclude)} | blank: {len(blank)} -> {a.out}")


if __name__ == "__main__":
    main()
