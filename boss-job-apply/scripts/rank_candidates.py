# -*- coding: utf-8 -*-
"""候选池去重 + 标题/薪资预筛 + 打分排序，输出 ranked.json 与可选 batch.json。

输入 candidates.json: [{"eid","text","company","title","salary","active","url"}, ...]
profile.json 见 assets/profile.example.json；ledger.json 为台账（可选，用于去重）。
打分词表与权重读 profile.json 的 scoring.bonus / scoring.penalty；未配置时用内置默认启发式。

用法:
    python rank_candidates.py --input candidates.json --profile profile.json \
        [--ledger ledger.json] [--out ranked.json] [--batch 12] [--offset 0]
"""
import argparse, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from salary_match import parse  # noqa: E402


def load_json(p, default):
    if p and os.path.exists(p):
        return json.load(open(p, encoding="utf-8"))
    return default


def default_rules():
    """内置通用启发式；不含任何个人栈或公司名，可被 profile.scoring 覆盖。"""
    return {
        "bonus": [
            {"words": ["后端", "服务端"], "points": 15},
            {"words": ["全栈"], "points": 8},
            {"words": ["资深", "高级", "专家"], "points": 3},
        ],
        "penalty": [
            {"words": ["项目制", "外派", "驻场", "派遣"], "points": -15},
            {"words": ["组长", "负责人", "leader", "Leader", "总监", "经理"], "points": -5},
            {"words": ["游戏", "Unity", "Cocos", "区块链", "Web3", "催收", "量化", "嵌入式", "物联网", "IoT", "IOT"], "points": -10},
            {"words": ["某大型", "某知名", "某500强", "某中型", "某小型"], "points": -25},
            {"words": ["Harness", "Sandbox", "Runtime", "基础设施", "算力", "数据平台", "运维平台", "工具链", "推理", "模型部署"], "points": -30},
            {"words": ["FDE", "售前", "解决方案", "交付"], "points": -15},
        ],
    }


def make_scorer(profile):
    rules = profile.get("scoring") or default_rules()

    def score(x):
        t = f"{x.get('title', '')} {x.get('text', '')}"
        s = 0
        for group in rules.get("bonus", []):
            for w in group.get("words", []):
                if w and re.search(re.escape(w), t, re.I):
                    s += group.get("points", 0)
                    break
        for group in rules.get("penalty", []):
            for w in group.get("words", []):
                if w and re.search(re.escape(w), t, re.I):
                    s += group.get("points", 0)
                    break
        return s

    return score


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--profile", default="profile.json")
    ap.add_argument("--ledger", default="ledger.json")
    ap.add_argument("--out", default="ranked.json")
    ap.add_argument("--batch", type=int, default=0)
    ap.add_argument("--offset", type=int, default=0)
    a = ap.parse_args()

    profile = load_json(a.profile, {})
    ledger = load_json(a.ledger, {"applied": [], "skipped": []})
    done = {x["eid"] for x in ledger.get("applied", [])} | \
           {x["eid"] for x in ledger.get("skipped", [])}

    band = profile.get("expectation", {}).get("salary_band", {"lo": 18, "hi": 25})
    excl_title = profile.get("expectation", {}).get("exclusion_keywords_title", [])
    excl_comp = profile.get("expectation", {}).get("excluded_companies", [])
    activity = profile.get("expectation", {}).get("activity", {})
    zombie_labels = activity.get("zombie_labels", [])

    cands = json.load(open(a.input, encoding="utf-8"))
    kept, dropped = [], []
    for x in cands:
        eid = x["eid"]
        if eid in done:
            continue
        text = f"{x.get('title','')} {x.get('company','')} {x.get('text','')}"
        # 标题/主体硬排除（列表层可判定的）
        hit = next((k for k in excl_title if re.search(k, text, re.I)), None)
        if hit:
            dropped.append({**x, "reason": f"标题/主体排除词：{hit}"})
            continue
        hit = next((c for c in excl_comp if c in text), None)
        if hit:
            dropped.append({**x, "reason": f"排除主体：{hit}"})
            continue
        if activity and x.get("active"):
            z = next((k for k in zombie_labels if k in x["active"]), None)
            if z:
                dropped.append({**x, "reason": f"招聘者活跃度僵尸：{x['active']}"})
                continue
        # 薪资预筛（无法解析的留到详情页复核）
        lo, hi = parse(x.get("salary", ""))
        if lo is not None:
            if not (lo <= band["hi"] and hi >= band["lo"]):
                dropped.append({**x, "reason": f"薪资无交集：{x.get('salary','')}"})
                continue
        kept.append(x)

    score = make_scorer(profile)
    kept.sort(key=score, reverse=True)
    for x in kept:
        x["score"] = score(x)
    json.dump({"ranked": kept, "dropped": dropped},
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"kept: {len(kept)} | dropped: {len(dropped)} -> {a.out}")
    if a.batch > 0:
        batch = kept[a.offset:a.offset + a.batch]
        json.dump(batch, open("batch.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"batch[{a.offset}:{a.offset + len(batch)}]: {len(batch)} -> batch.json")
        for x in batch:
            print(x["score"], x["eid"][:12], "|", x.get("title", x.get("text", ""))[:60])


if __name__ == "__main__":
    main()
