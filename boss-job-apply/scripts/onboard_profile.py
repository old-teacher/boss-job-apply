# -*- coding: utf-8 -*-
"""首次使用引导：初始化 profile.json、回填本人画像与筛选、就绪检查、确认闸门。

仅用标准库。本脚本不碰网页、不采集账号信息，只做本地 profile.json 的
创建、合并、校验与摘要；网页端的登录核验与简历/JD 读取由宿主浏览器流程完成。

两类输入来源（可单用也可合并，互相覆盖时以本人当场确认为准）：
1. 问卷：本人在对话里口头给出目标方向、薪资、城市、经验/学历/规模等；
2. 首页选择：本人已在 BOSS 首页/筛选面板选好条件，宿主从页面与 URL 参数读取后回填。

回填并经本人确认（--confirm）之前，不检索岗位、不打招呼。

用法:
    python scripts/onboard_profile.py --init
    python scripts/onboard_profile.py --merge-selections selections.json
    python scripts/onboard_profile.py --check
    python scripts/onboard_profile.py --confirm [--date 2026-11-27]
    python scripts/onboard_profile.py --summary

selections.json 示例（只填需要回填的字段，其余保留模板占位符）:
    {
      "owner": "本人姓名",
      "city": {"label": "杭州", "code": "101210100"},
      "positions": ["Java 后端开发", "AI 应用开发"],
      "salary_band": {"lo": 18, "hi": 25, "max_hi": 35},
      "main_stack": ["Java", "Spring Boot", "Python", "Vue3"],
      "daily_goal": 100,
      "search_filters": {
        "city": {"label": "杭州", "url_param": "city=101210100"},
        "salary": {"label": "10-20K", "url_param": "salary=405", "range": [10, 20]},
        "job_type": {"label": "全职", "url_param": "jobType=1901"},
        "experience": {"label": ["3-5年", "5-10年"], "url_param": "experience=105,106"},
        "degree": {"label": ["大专", "本科"], "url_param": "degree=202,203"},
        "scale": {"label": ["20-99人", "100-499人"], "url_param": "scale=302,303"}
      }
    }

输出 JSON（stdout）：动作结果、回填字段、就绪状态、缺失项与给本人看的摘要。
"""
import argparse
import copy
import json
import os
import sys
import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
EXAMPLE = os.path.join(SCRIPT_DIR, "..", "assets", "profile.example.json")
DEFAULT_PROFILE = "profile.json"

# 必须为真实值（非模板占位符）才允许开工的字段；路径相对 profile.json。
REQUIRED_FIELDS = [
    ("meta.owner", "本人姓名"),
    ("meta.city", "目标城市"),
    ("meta.city_code", "城市码（岗位页 URL 的 city 参数）"),
    ("expectation.positions", "目标方向/岗位关键词（至少一个）"),
    ("expectation.salary_band.lo", "期望薪资下限(K)"),
    ("expectation.salary_band.hi", "期望薪资上限(K)"),
    ("expectation.search_filters.city.url_param", "检索城市筛选参数"),
]
REQUIRED_STACK = [
    ("profile.main_stack", "本人可覆盖主栈（至少一个）"),
]


def is_placeholder(value):
    """模板占位符判定：空、None，或尖括号包裹的示例值。"""
    if value is None:
        return True
    if isinstance(value, str):
        v = value.strip()
        return v == "" or v.startswith("<") or v.endswith(">")
    if isinstance(value, list):
        return len(value) == 0 or all(is_placeholder(x) for x in value)
    return False


def get_path(obj, dotted):
    cur = obj
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def set_path(obj, dotted, value):
    parts = dotted.split(".")
    cur = obj
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = value


def load_profile(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_profile(path, profile):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
        f.write("\n")


def init_profile(path):
    if os.path.exists(path):
        return {"initialized": False, "reason": "profile.json 已存在，不覆盖", "path": path}
    if not os.path.exists(EXAMPLE):
        return {"initialized": False, "reason": f"模板不存在：{EXAMPLE}"}
    profile = load_profile(EXAMPLE)
    save_profile(path, profile)
    return {"initialized": True, "reason": "已从模板创建 profile.json，待引导回填", "path": path}


def merge_selections(profile, selections):
    """把问卷/首页选择回填进 profile；只覆盖显式给出的字段，不动其他配置。"""
    merged = []
    skipped = []

    def put(dotted, value):
        if value is None:
            return
        set_path(profile, dotted, value)
        merged.append(dotted)

    if selections.get("owner"):
        put("meta.owner", selections["owner"])
    if selections.get("city"):
        city = selections["city"]
        if isinstance(city, dict):
            if city.get("label"):
                put("meta.city", city["label"])
            if city.get("code"):
                put("meta.city_code", str(city["code"]))
        else:
            put("meta.city", str(city))
    if selections.get("daily_goal") is not None:
        put("meta.daily_goal", selections["daily_goal"])
    if selections.get("positions"):
        put("expectation.positions", selections["positions"])
    if selections.get("salary_band"):
        band = copy.deepcopy(selections["salary_band"])
        existing = profile.get("expectation", {}).get("salary_band", {})
        for k in ("unit", "rule"):
            band.setdefault(k, existing.get(k))
        put("expectation.salary_band", band)
    if selections.get("main_stack"):
        put("profile.main_stack", selections["main_stack"])
    if selections.get("secondary_stack"):
        put("profile.secondary_stack", selections["secondary_stack"])

    filters = selections.get("search_filters") or {}
    for key in ("city", "salary", "job_type", "experience", "degree", "scale"):
        if filters.get(key) is not None:
            existing = profile.setdefault("expectation", {}).setdefault("search_filters", {})
            existing[key] = copy.deepcopy(filters[key])
            merged.append(f"expectation.search_filters.{key}")

    # 记录来源；本人确认前 completed 仍为 false
    onb = profile.setdefault("meta", {}).setdefault("onboarding", {})
    source = selections.get("source")
    if source in ("questionnaire", "homepage_selection", "both"):
        onb["source"] = source
    elif "homepage_selection" in selections:
        onb["source"] = "both"
    else:
        onb["source"] = "questionnaire"
    onb.setdefault("completed", False)

    unknown = [k for k in selections if k not in
               ("owner", "city", "positions", "salary_band", "main_stack",
                "secondary_stack", "daily_goal", "search_filters", "source")]
    skipped = [f"未识别字段: {k}" for k in unknown]
    return {"merged": merged, "skipped": skipped, "profile": profile}


def check_ready(profile, relax_stack=False):
    missing = []
    for dotted, label in REQUIRED_FIELDS:
        if is_placeholder(get_path(profile, dotted)):
            missing.append({"field": dotted, "label": label})
    if not relax_stack:
        for dotted, label in REQUIRED_STACK:
            if is_placeholder(get_path(profile, dotted)):
                missing.append({"field": dotted, "label": label})
    ready = len(missing) == 0
    onb = profile.get("meta", {}).get("onboarding", {})
    if not onb.get("completed"):
        missing.append({"field": "meta.onboarding.completed", "label": "画像尚未经本人确认（--confirm）"})
        ready = False
    return {"ready": ready, "missing": missing}


def summary(profile):
    exp = profile.get("expectation", {})
    band = exp.get("salary_band", {})
    return {
        "owner": profile.get("meta", {}).get("owner"),
        "city": profile.get("meta", {}).get("city"),
        "city_code": profile.get("meta", {}).get("city_code"),
        "daily_goal": profile.get("meta", {}).get("daily_goal"),
        "positions": exp.get("positions"),
        "salary_band": band,
        "main_stack": profile.get("profile", {}).get("main_stack"),
        "search_filters": exp.get("search_filters", {}),
        "onboarding": profile.get("meta", {}).get("onboarding", {}),
    }


def main():
    ap = argparse.ArgumentParser(description="首次引导：初始化/回填/就绪检查/确认 profile.json")
    ap.add_argument("--profile", default=DEFAULT_PROFILE, help="profile.json 路径，默认 ./profile.json")
    ap.add_argument("--init", action="store_true", help="从模板创建 profile.json（已存在不覆盖）")
    ap.add_argument("--merge-selections", default="", help="回填选择项 JSON 文件路径")
    ap.add_argument("--check", action="store_true", help="就绪检查，输出缺失字段")
    ap.add_argument("--relax-stack", action="store_true", help="检查时暂不强制主栈非占位符")
    ap.add_argument("--confirm", action="store_true", help="本人确认画像，置 onboarding.completed=true")
    ap.add_argument("--date", default="", help="确认日期 YYYY-MM-DD，默认当天")
    ap.add_argument("--summary", action="store_true", help="打印已采集画像摘要")
    a = ap.parse_args()

    profile = None
    if os.path.exists(a.profile):
        profile = load_profile(a.profile)

    out = {"profile_path": os.path.abspath(a.profile)}

    if a.init:
        out["init"] = init_profile(a.profile)
        if os.path.exists(a.profile):
            profile = load_profile(a.profile)

    if profile is None and (a.merge_selections or a.check or a.confirm or a.summary):
        out["error"] = "profile.json 不存在，请先 --init 再回填。"
        print(json.dumps(out, ensure_ascii=False, indent=2))
        sys.exit(2)

    if a.merge_selections:
        with open(a.merge_selections, encoding="utf-8") as f:
            selections = json.load(f)
        res = merge_selections(profile, selections)
        out["merge"] = {"merged": res["merged"], "skipped": res["skipped"]}
        save_profile(a.profile, profile)

    if a.confirm:
        onb = profile.setdefault("meta", {}).setdefault("onboarding", {})
        onb["completed"] = True
        onb["captured_at"] = a.date or datetime.date.today().isoformat()
        save_profile(a.profile, profile)
        out["confirm"] = {"completed": True, "captured_at": onb["captured_at"]}

    if a.check:
        out["check"] = check_ready(profile, relax_stack=a.relax_stack)

    if a.summary:
        out["summary"] = summary(profile)

    if not (a.init or a.merge_selections or a.check or a.confirm or a.summary):
        ap.print_help()
        return

    print(json.dumps(out, ensure_ascii=False, indent=2))

    # 就绪检查不通过时退出码非 0，便于宿主在开工前闸门拦截
    if a.check and not out.get("check", {}).get("ready"):
        sys.exit(1)


if __name__ == "__main__":
    main()
