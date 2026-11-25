# -*- coding: utf-8 -*-
"""薪资区间与目标带是否有交集判定。

用法:
    python salary_match.py "20-25K·13薪" --lo 18 --hi 25
    python salary_match.py "面议"            # 无法解析，返回 unknown

输出 JSON: {"raw", "lo", "hi", "overlap": bool|null, "reason"}
exit code: 0=有交集, 1=无交集, 2=未知/面议
"""
import argparse, json, re, sys

NUM = re.compile(r"(\d+(?:\.\d+)?)")


def parse(raw: str):
    if not raw or ("面议" in raw):
        return None, None
    # 取 K/千 之前的区间段，排除 ·13薪 等后缀数字
    head = re.split(r"[Kk千]", raw)[0]
    nums = [float(x) for x in NUM.findall(head)]
    if not nums:
        nums = [float(x) for x in NUM.findall(raw)]
        nums = [n for n in nums if n < 100]  # 排除薪数后缀
    if not nums:
        return None, None
    if len(nums) == 1:
        return nums[0], nums[0]
    lo, hi = min(nums[:2]), max(nums[:2])
    return lo, hi


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("salary")
    ap.add_argument("--lo", type=float, default=18)
    ap.add_argument("--hi", type=float, default=25)
    ap.add_argument("--max-hi", type=float, default=35,
                    help="薪资上限硬线：岗位上限超过该值一律不投（默认 35K）；传 0 关闭")
    a = ap.parse_args()

    lo, hi = parse(a.salary)
    if lo is None:
        out = {"raw": a.salary, "lo": None, "hi": None, "overlap": None,
               "reason": "薪资未注明/面议，需进详情页或人工复核"}
        print(json.dumps(out, ensure_ascii=False))
        sys.exit(2)

    overlap = lo <= a.hi and hi >= a.lo
    if a.max_hi and hi > a.max_hi:
        overlap = False
        reason = f"上限 {hi:g}K > {a.max_hi:g}K 硬线，不投"
    elif overlap:
        reason = f"区间 {lo:g}-{hi:g}K 与 {a.lo:g}-{a.hi:g}K 有交集"
    elif hi < a.lo:
        reason = f"上限 {hi:g}K < {a.lo:g}K，无交集"
    else:
        reason = f"下限 {lo:g}K > {a.hi:g}K，无交集"
    out = {"raw": a.salary, "lo": lo, "hi": hi, "overlap": overlap, "reason": reason}
    print(json.dumps(out, ensure_ascii=False))
    sys.exit(0 if overlap else 1)


if __name__ == "__main__":
    main()
