# -*- coding: utf-8 -*-
"""把 hold 池生成人工拍板表 xlsx（完整 JD 在内），供导入飞书表格后本人标注。

输入 hold.json:
  [{"eid","company","title","salary","exp","edu","city","reason","url","jd"}, ...]
输出 decision_sheet.xlsx，最后一列「你的决定（可投/不投）」留空。

用法:
    python build_decision_sheet.py --input hold.json [--out decision_sheet.xlsx]
"""
import argparse, json, os
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

HEADERS = ["序号", "公司", "岗位", "薪资", "经验", "学历", "地点",
           "待定原因", "岗位链接", "完整JD", "你的决定（可投/不投）"]
WIDTHS = [6, 22, 32, 14, 10, 8, 10, 50, 44, 70, 20]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="hold.json")
    ap.add_argument("--out", default="decision_sheet.xlsx")
    a = ap.parse_args()

    rows = json.load(open(a.input, encoding="utf-8"))
    wb = Workbook()
    ws = wb.active
    ws.title = "拍板表"
    ws.append(HEADERS)
    hfill = PatternFill("solid", fgColor="4472C4")
    hfont = Font(bold=True, color="FFFFFF", size=11)
    thin = Border(*[Side(style="thin", color="D9D9D9")] * 4)
    for c in ws[1]:
        c.fill = hfill; c.font = hfont
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = thin

    for i, x in enumerate(rows, 1):
        ws.append([i, x.get("company", ""), x.get("title", ""), x.get("salary", ""),
                   x.get("exp", ""), x.get("edu", ""), x.get("city", ""),
                   x.get("reason", ""), x.get("url", ""), x.get("jd", ""), ""])
        for c in ws[i + 1]:
            c.alignment = Alignment(vertical="top", wrap_text=True)
            c.border = thin
        ws.cell(row=i + 1, column=1).alignment = Alignment(horizontal="center", vertical="top")
        ws.row_dimensions[i + 1].height = 140

    for j, w in enumerate(WIDTHS, 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.row_dimensions[1].height = 28
    ws.freeze_panes = "A2"
    wb.save(a.out)
    print(f"rows: {len(rows)} -> {a.out}")


if __name__ == "__main__":
    main()
