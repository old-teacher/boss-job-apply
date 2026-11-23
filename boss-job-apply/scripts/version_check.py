# -*- coding: utf-8 -*-
"""版本自检：对比本地 VERSION 与上游仓库同路径版本，输出升级提示与改动摘要。

仅用标准库；网络不可达时输出 checked=false，不阻断投递流程。不自动覆盖本地技能文件。

用法:
    python version_check.py
    python version_check.py --repo old-teacher/boss-job-apply --branch main
    python version_check.py --raw-base https://your-host/raw  # 自托管源码仓库时覆盖下载前缀

输出 JSON（stdout）:
    checked: bool            # 是否成功连上上游并取到版本号
    local_version / remote_version
    upgrade_available: bool|None
    changes: [{"version", "summary": [str, ...]}]   # 待升级版本的改动条目
    message: str              # 给本人看的一句话提示
"""
import argparse
import json
import os
import re
import sys
import urllib.request

VERSION_FILE = "VERSION"
CHANGELOG_FILE = os.path.join("references", "changelog.md")


def read_version_file(path):
    """解析 VERSION 的 key: value 清单。"""
    meta = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta


def semver_tuple(v):
    """把 '1.1.0' / '1.1.0-beta.1' 转成可比较的数字元组；非法版本返回 None。"""
    if not v:
        return None
    m = re.match(r"(\d+)\.(\d+)\.(\d+)", v.strip())
    if not m:
        return None
    return tuple(int(x) for x in m.groups())


def fetch(url, timeout=8):
    req = urllib.request.Request(url, headers={"User-Agent": "boss-job-apply-version-check"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def parse_changelog(text, after_version, up_to_version):
    """提取 (after_version, up_to_version] 区间内各版本的改动条目。"""
    lo, hi = semver_tuple(after_version), semver_tuple(up_to_version)
    sections = re.split(r"\n##\s+", "\n" + text)
    changes = []
    for sec in sections[1:]:
        head = sec.splitlines()[0].strip()
        m = re.match(r"(\d+\.\d+\.\d+)", head)
        if not m:
            continue
        v = m.group(1)
        t = semver_tuple(v)
        if lo is not None and t <= lo:
            continue
        if hi is not None and t > hi:
            continue
        bullets = [ln.strip()[2:].strip() for ln in sec.splitlines()[1:]
                   if ln.strip().startswith("- ")]
        changes.append({"version": v, "summary": bullets})
    changes.sort(key=lambda c: semver_tuple(c["version"]))
    return changes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="", help="上游 owner/repo，默认取本地 VERSION 的 repo 字段")
    ap.add_argument("--branch", default="", help="上游分支，默认取本地 VERSION 的 branch 字段")
    ap.add_argument("--skill-subdir", default="", help="技能在仓库中的子目录，默认取 VERSION 的 skill_subdir")
    ap.add_argument("--raw-base", default="https://raw.githubusercontent.com",
                    help="源码原始文件下载前缀，可按自托管仓库覆盖")
    ap.add_argument("--version-file", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                             "..", VERSION_FILE))
    a = ap.parse_args()

    local_meta = read_version_file(a.version_file)
    local_version = local_meta.get("version", "0.0.0")
    repo = a.repo or local_meta.get("repo", "")
    branch = a.branch or local_meta.get("branch", "main")
    subdir = a.skill_subdir or local_meta.get("skill_subdir", "boss-job-apply")

    out = {"checked": False, "local_version": local_version, "remote_version": None,
           "upgrade_available": None, "changes": [], "message": ""}

    if not repo:
        out["message"] = "未配置上游仓库 repo，跳过版本自检。"
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    base = f"{a.raw_base.rstrip('/')}/{repo}/{branch}/{subdir}"
    try:
        remote_text = fetch(f"{base}/{VERSION_FILE}")
        remote_meta = read_version_file_from_text(remote_text)
        remote_version = remote_meta.get("version")
        out["remote_version"] = remote_version
        lt, rt = semver_tuple(local_version), semver_tuple(remote_version)

        if lt is None or rt is None:
            out["message"] = f"版本号无法比较：本地 {local_version} / 上游 {remote_version}。"
            print(json.dumps(out, ensure_ascii=False, indent=2))
            return

        if rt > lt:
            out["checked"] = True
            out["upgrade_available"] = True
            changes = []
            try:
                changelog_text = fetch(f"{base}/{CHANGELOG_FILE}")
                changes = parse_changelog(changelog_text, local_version, remote_version)
            except Exception:
                changes = []
            out["changes"] = changes
            bullet = "；".join(changes[0]["summary"][:3]) if changes else "详见上游 changelog。"
            out["message"] = (f"发现新版本 {remote_version}（本地 {local_version}）：{bullet} "
                              f"请按 README「版本与升级」一节确认后更新技能目录；未确认前不自动覆盖本地文件。")
        elif rt < lt:
            out["checked"] = True
            out["upgrade_available"] = False
            out["message"] = f"本地版本 {local_version} 高于上游 {remote_version}，可能为本地定制分支，不自动回退。"
        else:
            out["checked"] = True
            out["upgrade_available"] = False
            out["message"] = f"已是最新版本 {local_version}。"
    except Exception as e:
        out["message"] = f"版本自检未连上上游（{type(e).__name__}），跳过，不阻断投递流程。"

    print(json.dumps(out, ensure_ascii=False, indent=2))


def read_version_file_from_text(text):
    meta = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, v = line.split(":", 1)
        meta[k.strip()] = v.strip()
    return meta


if __name__ == "__main__":
    main()
