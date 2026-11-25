# -*- coding: utf-8 -*-
"""拟人节奏计划：按动作类型随机化停留时间，生成当次投递的等待时间表。

仅用标准库。节奏参数取 profile.json 的 pacing 块（缺省用内置推荐值），
脚本只产出"该等多久"的建议表，真正的等待由宿主执行；不点页面、不改数据。

用法:
    python scripts/pacing_plan.py --greets 20
    python scripts/pacing_plan.py --greets 20 --profile profile.json
    python scripts/pacing_plan.py --greets 20 --profile profile.json --start-time 10:30 --seed 42
    python scripts/pacing_plan.py --action greet      # 查单个动作的推荐停留

输出 JSON（stdout）:
    greets / total_minutes / sessions / schedule / rate_gates / off_hours_jumps / warnings
"""
import argparse
import json
import os
import random

# 动作 -> (最小秒, 最大秒)，单位秒；推荐默认值见 references/pacing.md
DEFAULT_RANGES = {
    "search_input": (1.5, 4.0),
    "scroll": (0.8, 2.5),
    "card_read": (1.5, 4.0),
    "page_turn": (3.0, 8.0),
    "open_detail": (2.0, 5.0),
    "read_jd": (8.0, 20.0),
    "greet_pre": (3.0, 7.0),
    "greet_post": (4.0, 10.0),
    "hover_pre_click": (0.5, 1.5),
    "click_post": (1.0, 2.5),
    "back_to_list": (2.0, 5.0),
    "between_greets": (120.0, 300.0),
    "keyword_switch": (10.0, 30.0),
}
DEFAULT_PACING = {
    "session_minutes": [20, 30],
    "rest_minutes": [8, 15],
    "hourly_greet_cap": 12,
    "active_hours": "09:00-21:30",
    "cards_review_per_greet": 3,
    "page_turn_probability": 0.35,
}

# 档位预设：保守档用于新账号/近期被验证过；标准档用于稳定账号；进取档仅在长期无验证时启用。
PRESETS = {
    "conservative": {
        "between_greets": [120.0, 300.0],
        "hourly_greet_cap": 12,
        "session_minutes": [20, 30],
        "rest_minutes": [8, 15],
    },
    "standard": {
        "between_greets": [60.0, 150.0],
        "hourly_greet_cap": 20,
        "session_minutes": [25, 35],
        "rest_minutes": [6, 12],
    },
    "active": {
        "between_greets": [40.0, 90.0],
        "hourly_greet_cap": 30,
        "session_minutes": [35, 45],
        "rest_minutes": [5, 10],
    },
}


def apply_preset(pacing, ranges, name):
    preset = PRESETS.get(name)
    if not preset:
        return pacing, ranges, False
    for key, value in preset.items():
        if key == "between_greets":
            ranges["between_greets"] = [float(value[0]), float(value[1])]
        else:
            pacing[key] = value
    return pacing, ranges, True


def load_pacing(profile_path, mode_override=""):
    pacing = dict(DEFAULT_PACING)
    ranges = {k: list(v) for k, v in DEFAULT_RANGES.items()}
    profile = {}
    if profile_path and os.path.exists(profile_path):
        with open(profile_path, encoding="utf-8") as f:
            profile = json.load(f)
        block = profile.get("pacing") or {}
        # 先按档位预设打底，再用 profile 顶层的显式值覆盖（个人微调优先）
        pacing, ranges, applied = apply_preset(pacing, ranges, str(block.get("mode", "")))
        for key, value in block.items():
            if key == "action_ranges" and isinstance(value, dict):
                for action, span in value.items():
                    if isinstance(span, (list, tuple)) and len(span) == 2 and span[0] <= span[1]:
                        ranges[action] = [float(span[0]), float(span[1])]
            elif key in DEFAULT_PACING and value is not None:
                pacing[key] = value
    else:
        applied = False
        block = {}

    if mode_override:
        pacing, ranges, applied = apply_preset(pacing, ranges, mode_override)
        if applied:
            block = dict(block, mode=mode_override)

    mode = str(block.get("mode", "")) or ("custom" if not applied else "")
    if not applied and mode_override:
        mode = mode_override
    return pacing, ranges, profile, (mode or "conservative/custom")


def estimate_per_hour(pacing, ranges):
    """按平均停留估算每小时可打招呼条数（用于判断档位是否过慢）。"""
    fixed = ["open_detail", "read_jd", "greet_pre", "greet_post", "click_post", "back_to_list"]
    cycle = sum(sum(ranges.get(a, (1.0, 2.0))) / 2.0 for a in fixed)
    cards = max(1, int(pacing.get("cards_review_per_greet", 3) or 3))
    cycle += cards * (sum(ranges["card_read"]) / 2.0 + sum(ranges["scroll"]) / 2.0)
    cycle += float(pacing.get("page_turn_probability", 0.35) or 0) * sum(ranges["page_turn"]) / 2.0
    cycle += sum(ranges.get("between_greets", (120.0, 300.0))) / 2.0
    return round(3600.0 / cycle, 1) if cycle else 0.0


def parse_hours(text, default=("09:00", "21:30")):
    try:
        start_s, end_s = str(text).split("-")
        return start_s.strip(), end_s.strip()
    except Exception:
        return default


def to_minutes(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def from_minutes(total):
    total = int(total) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def span_seconds(rng, ranges, action):
    lo, hi = ranges.get(action, (1.0, 3.0))
    return round(rng.uniform(lo, hi), 2)


def build_plan(greets, pacing, ranges, start_time, seed, mode="conservative"):
    rng = random.Random(seed) if seed is not None else random.Random()
    window_start, window_end = parse_hours(pacing.get("active_hours", "09:00-22:00"))
    ws, we = to_minutes(window_start), to_minutes(window_end)
    if we <= ws:
        we = ws + 1

    clock = to_minutes(start_time)  # 当日分钟数，可跨天累加
    schedule, warnings = [], []
    rate_gates, off_hours_jumps, sessions = [], [], []
    session_limit = rng.uniform(*pacing["session_minutes"])
    work_in_session = 0.0
    session_index = 1
    session_start = clock
    greet_times = []  # 已打招呼时刻（秒口径用分钟）

    session_size = max(1, int(pacing["hourly_greet_cap"]))
    sessions_planned = (greets + session_size - 1) // session_size

    for n in range(1, greets + 1):
        steps = []
        base_cycle = 0.0

        def add(action):
            nonlocal base_cycle
            sec = span_seconds(rng, ranges, action)
            steps.append({"action": action, "seconds": sec})
            base_cycle += sec
            return sec

        add("hover_pre_click")
        add("open_detail")
        add("read_jd")
        add("greet_pre")

        greet_start = clock + base_cycle / 60.0
        # 时段窗口：窗口外不发起打招呼
        day_offset = int(greet_start // (24 * 60))
        minute_in_day = greet_start % (24 * 60)
        if minute_in_day < ws or minute_in_day >= we:
            wait_min = (day_offset * 24 * 60 + ws) - greet_start if minute_in_day >= we \
                else (day_offset * 24 * 60 + ws) - greet_start
            if wait_min < 0:
                wait_min += 24 * 60
            off_hours_jumps.append({"cycle": n, "wait_minutes": round(wait_min, 1),
                                    "reason": "outside_active_hours"})
            clock += wait_min
            steps.append({"action": "off_hours_wait", "minutes": round(wait_min, 1)})

        # 每小时打招呼上限：超限则等到滚动窗口放行
        greet_times = [t for t in greet_times if greet_start - t < 60]
        if len(greet_times) >= session_size:
            wait_min = 60 - (greet_start - greet_times[0]) + 0.5
            rate_gates.append({"cycle": n, "wait_minutes": round(wait_min, 1),
                               "reason": "hourly_cap"})
            clock += wait_min
            steps.append({"action": "rate_gate_wait", "minutes": round(wait_min, 1)})
            greet_start += wait_min

        add("click_post")
        add("greet_post")
        add("back_to_list")
        cards = int(pacing.get("cards_review_per_greet", 3) or 3)
        for _ in range(max(1, cards)):
            add("card_read")
            add("scroll")
        if rng.random() < float(pacing.get("page_turn_probability", 0.35) or 0):
            add("page_turn")
        # 真人不会一分钟连投三条：两次打招呼之间留出思考/浏览间隙
        if n < greets:
            add("between_greets")

        greet_times.append(greet_start + steps[-1]["seconds"] / 60.0)
        schedule.append({
            "n": n,
            "greet_at": from_minutes(greet_start),
            "steps": steps,
            "cycle_seconds": round(base_cycle, 2),
            "session": session_index,
        })

        work_in_session += base_cycle
        clock += base_cycle / 60.0
        # 休息按"进入本次会话后的实际流逝时间"计（含限速等待与跨时段顺延），
        # 用纯操作时长会把长时间限速误判成没累。
        if (clock - session_start) >= session_limit and n < greets:
            rest = round(rng.uniform(*pacing["rest_minutes"]), 1)
            sessions.append({"session": session_index,
                             "start": from_minutes(session_start),
                             "greets": sum(1 for s in schedule if s["session"] == session_index),
                             "rest_minutes": rest})
            clock += rest
            session_index += 1
            session_start = clock
            session_limit = rng.uniform(*pacing["session_minutes"])
            work_in_session = 0.0

    sessions.append({"session": session_index,
                     "start": from_minutes(session_start),
                     "greets": sum(1 for s in schedule if s["session"] == session_index),
                     "rest_minutes": 0})
    total_minutes = clock - to_minutes(start_time)

    if total_minutes > 8 * 60:
        warnings.append("按当前节奏与每小时上限，总耗时超过 8 小时，建议拆分到多日或提高 pacing.hourly_greet_cap。")
    if rate_gates:
        warnings.append(f"触发 {len(rate_gates)} 次每小时上限等待，属预期限速，不是失败。")
    if off_hours_jumps:
        warnings.append(f"有 {len(off_hours_jumps)} 次落入非活跃时段，已顺延到窗口开启，符合拟人节律。")

    return {
        "mode": mode,
        "greets": greets,
        "start_time": start_time,
        "end_time": from_minutes(clock),
        "total_minutes": round(total_minutes, 1),
        "estimated_per_hour": estimate_per_hour(pacing, ranges),
        "sessions_planned": sessions_planned,
        "hourly_greet_cap": session_size,
        "active_hours": f"{window_start}-{window_end}",
        "sessions": sessions,
        "schedule": schedule,
        "rate_gates": rate_gates,
        "off_hours_jumps": off_hours_jumps,
        "warnings": warnings,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--greets", type=int, default=0, help="计划打招呼份数")
    ap.add_argument("--profile", default="", help="profile.json 路径，读取 pacing 块")
    ap.add_argument("--start-time", default="09:30", help="计划开始时刻 HH:MM，默认 09:30")
    ap.add_argument("--seed", type=int, default=None, help="随机种子，便于复现同一份节奏表")
    ap.add_argument("--action", default="", help="只查单个动作推荐停留区间，如 greet_pre / read_jd")
    ap.add_argument("--mode", default="", choices=["", "conservative", "standard", "active"],
                    help="节奏档位：conservative(12/时)/standard(20/时)/active(30/时)，覆盖 profile 设置")
    a = ap.parse_args()

    pacing, ranges, _, mode = load_pacing(a.profile, a.mode)

    if a.action:
        lo, hi = ranges.get(a.action, (None, None))
        if lo is None:
            print(json.dumps({"error": f"未知动作 {a.action}",
                              "known_actions": sorted(ranges)}, ensure_ascii=False, indent=2))
            return
        print(json.dumps({"action": a.action, "min_seconds": lo, "max_seconds": hi,
                          "mode": mode,
                          "note": "每次从区间内随机取值，不要固定常量。"},
                         ensure_ascii=False, indent=2))
        return

    if a.greets <= 0:
        print(json.dumps({"error": "请用 --greets 指定份数，或 --action 查单动作区间。"},
                         ensure_ascii=False, indent=2))
        return

    print(json.dumps(build_plan(a.greets, pacing, ranges, a.start_time, a.seed, mode),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
