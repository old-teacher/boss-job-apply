# -*- coding: utf-8 -*-
"""每日投递台账：初始化、去重追加已投/已跳过、状态统计。

用法:
    python ledger.py init [--ledger ledger.json]
    python ledger.py status [--ledger ledger.json]
    python ledger.py applied-append --eid EID --company C --title T --salary S --match M [--ledger ledger.json]
    python ledger.py skip-append --eid EID --reason R [--company C --title T --salary S] [--ledger ledger.json]
    python ledger.py done [--ledger ledger.json]   # 输出已完成 eid 集合 JSON
"""
import argparse, datetime, json, os, sys


def load(path):
    if os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))
    return {"applied": [], "skipped": []}


def save(path, d):
    json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["init", "status", "applied-append", "skip-append", "done"])
    ap.add_argument("--ledger", default="ledger.json")
    ap.add_argument("--eid")
    ap.add_argument("--company", default="")
    ap.add_argument("--title", default="")
    ap.add_argument("--salary", default="")
    ap.add_argument("--match", default="")
    ap.add_argument("--reason", default="")
    a = ap.parse_args()

    d = load(a.ledger)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    if a.cmd == "init":
        save(a.ledger, d)
        print("ledger initialized:", a.ledger)
        return

    done = {x["eid"] for x in d["applied"]} | {x["eid"] for x in d["skipped"]}

    if a.cmd == "status":
        print(json.dumps({"applied": len(d["applied"]), "skipped": len(d["skipped"]),
                          "total": len(done)}, ensure_ascii=False))
        return

    if a.cmd == "done":
        print(json.dumps(sorted(done), ensure_ascii=False))
        return

    if a.eid in done:
        print(f"already recorded: {a.eid[:12]}")
        return

    if a.cmd == "applied-append":
        d["applied"].append({"eid": a.eid, "company": a.company, "title": a.title,
                             "salary": a.salary, "match": a.match,
                             "note": f"默认招呼语，未附简历；{now}"})
    else:
        d["skipped"].append({"eid": a.eid, "company": a.company, "title": a.title,
                             "salary": a.salary, "reason": a.reason, "time": now})
    save(a.ledger, d)
    print(f"{a.cmd}: applied={len(d['applied'])} skipped={len(d['skipped'])}")


if __name__ == "__main__":
    main()
