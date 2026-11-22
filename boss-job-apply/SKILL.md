---
name: boss-job-apply
description: BOSS直聘岗位检索、筛选、打招呼投递与人工拍板闭环。用于按本人画像多关键词搜岗位、滚动翻页遍历、进详情页读薪资/JD复核、给明确对口岗位发默认招呼语、把不确定/边缘岗位收集成含完整JD的拍板表交人工标注后执行、台账去重与每日复盘。触发场景：BOSS直聘/直聘、打招呼、投递、筛岗、找工作、后端/前端/AI应用/数据等技术岗位、每日投递任务、拍板表标注学习。
metadata:
  display_name: boss姥爷
---

# BOSS 直聘投递助手（boss姥爷）

## 概述

按个人画像在 BOSS 直聘网页端检索并筛选岗位：明确对口的发默认招呼语；不确定/边缘岗位挂起生成拍板表，人工标注后再执行；全程台账去重、当日复盘，标注结论回写画像规则。

## 安装与宿主适配

本技能与宿主 AI 工具解耦：一份指令文件（`SKILL.md`）+ 一组 Python CLI 脚本 + 规则参考 + 画像模板。宿主只需具备三项能力：浏览器自动化、终端命令执行、本地文件读写。

1. **保持整目录**：`boss-job-apply/` 原样复制，`scripts/`、`references/`、`assets/` 之间的相对引用不能拆散；文件夹名与 frontmatter `name` 一致（`boss-job-apply`）。
2. **按宿主工具放置**（常见约定，具体路径以宿主官方文档为准）：
   - 豆包工作区：`.user_skills/boss-job-apply/`（与内置 `.skills` 平级）；
   - Claude Code：`~/.claude/skills/boss-job-apply/`；
   - Cursor：把本指令放入项目 `.cursor/rules/`，脚本与模板随项目固定目录存放；
   - Codex / OpenAI 类：在 `AGENTS.md` 中引用本 `SKILL.md`，脚本随仓库存放；
   - Windsurf：放入 `.windsurf/rules/`；
   - 其他工具：把 `SKILL.md` 作为全局或项目指令加载，同目录保留 `scripts/`、`references/`、`assets/`。
3. **依赖**：Python 3；脚本仅用标准库；拍板表生成/解析需要 `openpyxl`（未安装时 `pip install openpyxl`）。
4. **首次配置**：复制 `assets/profile.example.json` 为工作目录 `profile.json`，初始化规则见 §0.1。
5. **触发方式**：在宿主对话中描述 BOSS 直聘/打招呼/投递/筛岗等任务时加载本指令；也可直接说「按 boss-job-apply 流程跑今日投递」。
6. **浏览器环境**：使用宿主提供的浏览器自动化能力（内置浏览器、Playwright、浏览器 MCP 等均可）操作网页端；需保持 BOSS 网页登录态，离线或未登录先交本人扫码登录。

## 技能结构

```text
boss-job-apply/
├── SKILL.md                        # 主流程、安装说明、技能结构（触发后必读）
├── assets/
│   └── profile.example.json        # 画像配置模板，复制为 profile.json 后按本人简历填写
├── references/
│   └── filters.md                  # 薪资口径、纳入原则、硬排除清单、复核清单、拍板协议、行动边界、打分启发式
└── scripts/
    ├── salary_match.py             # 单条薪资串与目标带是否有交集判定
    ├── rank_candidates.py           # 台账去重、标题/主体/活跃度预筛、打分排序、切批次
    ├── ledger.py                    # 台账初始化、已投/已跳过追加、去重、统计
    ├── build_decision_sheet.py      # 待定池 → 含完整 JD 的拍板表 xlsx
    └── parse_annotation.py          # 解析标注表，拆 apply / exclude / blank
```

## 前置准备

1. `profile.json` 初始化见 §0.1；登录核验见 §0，登录态失效、验证码、扫码一律交本人接管，不绕过。
2. 工作目录产物：`candidates.json`（采集卡片）、`ranked.json`/`batch.json`（排序批次）、`details.jsonl`（详情复核行）、`hold.json`（待定池）、`ledger.json`（台账）。

## 工作流

### 0. 打开浏览器与登录核验

- 用宿主工具的浏览器自动化能力打开岗位页，导航到 BOSS 直聘求职者岗位页：
  `https://www.zhipin.com/web/geek/jobs?city=<城市码>&query=<关键词>`（城市码填 `profile.json` 的 `city_code`；未知时从页面城市选择器读取）。
- 登录核验：页面显示本人账号头像/昵称即为已登录；若跳到登录页、出现扫码、滑块或设备验证，停下手头操作交本人接管，不绕过、不尝试自动登录。
- 登录成功后回到岗位列表页，再开始后续流程；全程保持该浏览器标签会话，不另开爬虫或未公开接口。

### 0.1 初始化 profile.json（首次使用）

1. **复制模板**：把技能目录 `assets/profile.example.json` 复制到本次工作目录为 `profile.json`（技能目录路径以当前环境已安装技能的位置为准）。
2. **必填字段**：城市与城市码、薪资带、方向关键词、主/副栈、弱点、排除词表、活跃度标签。
3. **信息采集与录入顺序**：
   - 先在已登录的本人 BOSS 会话中，直接打开本人主页/在线简历，采集页面可见的城市、工作年限、学历、技术栈、期望薪资、求职状态等信息回填 `profile.json`；只读取本人账号可见内容，不改写 BOSS 简历，不采集未公开信息；
   - 登录成功后同步读取**在线简历与附件简历**中的「个人优势」「项目经历」（角色、职责、所用技术栈、可量化成果），提炼成画像条目写入 `profile.json`；附件简历需本人同意打开后再读，不绕过简历查看限制；
   - 简历表述模糊、读不懂、或与本人当前情况存疑的字段，**不要不懂装懂、不要按常识推测**，及时向求职者澄清反问，逐项确认后再录入；本人当场补充的信息直接采用；
   - 禁止臆造年限、学历、技术栈、薪资、优势、项目经历、弱点等事实；本人不愿提供的字段按第 4 条降级处理。
4. **本人明确拒绝填写的字段**：保留模板占位符，对应岗位在详情复核时降级为人工判断，不按默认值擅自放行。
5. `profile.json` 仅存本地工作目录，不写入技能文件、不提交任何仓库。

### 1. 复盘昨日样本

打开 BOSS 消息列表，采集昨日已沟通岗位与招聘方回复；统计方向/薪资/年限/学历分布，校准当日筛选口径。用 `ledger.py status` 查看台账累计。

### 2. 浏览器检索并采集卡片

- 用浏览器自动化逐个跑 `profile.json` 的方向关键词；不写 Python 爬虫、不调用未公开接口。
- **城市筛选**：搜索前把城市固定为 `profile.json` 目标城市（URL `city` 参数与页面城市选择器双重确认），外地 base 岗位不采集。
- **单页加载**：进入关键词结果页后，列表反复滚动到底，直到卡片数量不再增长——首屏约 15 张、懒加载，必须把当页卡片全部露出。
- **逐页翻遍**：点「下一页」进入下一页，重复滚动加载；直到末页、「下一页」按钮消失或置灰为止。每个关键词都要遍历全部页，禁止只看当前一页或第一屏。
- **顺序采集**：按 BOSS 列表从上到下的顺序逐张采集，不跳页、不漏页；记录招聘者活跃标签（刚刚活跃/今日活跃/3日内活跃/本周活跃/本月活跃等）。
- 卡片薪资加密，列表层只采集标题/公司/链接/活跃标签；真实薪资与完整 JD 留到详情页读。
- 多关键词结果合并、按 eid 去重后汇总为 `candidates.json`：`[{"eid","title","company","salary","active","url"}]`，eid 取链接 `job_detail/` 末段（去掉 `.html`）。

### 3. 预筛与排序

```bash
python scripts/rank_candidates.py --input candidates.json --profile profile.json \
  --ledger ledger.json --out ranked.json --batch 12
```

台账去重（已投/已跳过）、标题与主体硬排除、活跃度僵尸岗剔除、薪资无交集剔除；剩余按关键词打分排序，高分优先进详情复核。被剔除项落在 `ranked.json.dropped`，原因可追溯。

### 4. 详情页逐条复核

- 逐条打开岗位详情，读取真实薪资、学历、经验、地点、完整 JD。
- 判定依据 `references/filters.md`：先过 §1 薪资口径，再过 §3 硬排除清单与 §4 复核清单（含招聘者活跃度 ≤3 天、岗位未过期）。
- 三分类：
  - **apply**：复核清单全部通过，进打招呼；
  - **exclude**：命中硬排除，记台账 skipped 并写原因；
  - **hold**：经验深度、主体性质、方向边界、硬门槛存疑，进 `hold.json`；不自行放行，也不自行排除。
- 复核行写入 `details.jsonl`：`{eid, title, company, salary, exp, edu, city, jd, full}`。

### 5. 打招呼（仅限 apply）

- 点「立即沟通」，发送账号默认招呼语；不附附件简历、不发在线简历；已显示「继续沟通」的职位不重复点。
- 每条结果回写台账：

```bash
python scripts/ledger.py applied-append --eid EID --company C --title T --salary S --match "命中方向"
python scripts/ledger.py skip-append --eid EID --reason "排除原因" [--company C --title T --salary S]
```

- 不主动回复招聘方；猎头弹层提示「主动联系后简历可见」时取消，不计新增；同公司同职责重复链接审慎去重。

### 6. 待定拍板闭环

1. 攒批把 hold 池生成拍板表（附**完整 JD**，不是截断要点）：

```bash
python scripts/build_decision_sheet.py --input hold.json --out decision_sheet.xlsx
```

   生成的 xlsx 导入任意在线表格或本地 Excel/CSV，交本人标注「可投 / 不投」。

2. 标注回表后解析分组：

```bash
python scripts/parse_annotation.py --sheet decision_sheet.xlsx --out annotation_result.json
```

3. `apply` 组按 §5 补打招呼；`exclude` 组记台账 skipped；`blank` 继续挂起。
4. 把标注结论沉淀回写：新增排除类别、放行口径更新到 `profile.json` 词表与 `filters.md` 对应小节，形成学习闭环。

### 7. 当日复盘

统计 applied/skipped 数量、方向与薪资分布、回复/被拒情况；对照画像找偏差。未达当日目标时，仅在硬排除项全部保留的前提下扩大可选方向，不放行硬排除类别。

## 脚本命令参考

| 脚本 | 典型命令 |
| --- | --- |
| `scripts/salary_match.py` | `python scripts/salary_match.py "20-25K" --lo 18 --hi 25` |
| `scripts/rank_candidates.py` | `python scripts/rank_candidates.py --input candidates.json --profile profile.json --ledger ledger.json --out ranked.json --batch 12` |
| `scripts/ledger.py` | `python scripts/ledger.py status` / `applied-append` / `skip-append` / `done` |
| `scripts/build_decision_sheet.py` | `python scripts/build_decision_sheet.py --input hold.json --out decision_sheet.xlsx` |
| `scripts/parse_annotation.py` | `python scripts/parse_annotation.py --sheet decision_sheet.xlsx --out annotation_result.json` |

## 参考

- `references/filters.md`：薪资口径、纳入原则、硬排除清单、复核清单、拍板协议、行动边界、打分启发式。
- `assets/profile.example.json`：画像配置模板，复制为 `profile.json` 后按本人简历填写。

## 边界

- 网站信息采集走浏览器自动化；Python 只做本地去重、排序、台账、制表等后处理。
- 遇到验证码、扫码、设备验证、登录态失效：停下手头操作，交本人接管。
- 个人信息（姓名、联系方式、简历项目）只进本地 `profile.json` 工作目录，不写入技能文件。
