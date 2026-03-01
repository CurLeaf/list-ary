# Windsurf 上报体系升级方案

## 一、现状分析

### 1.1 当前架构

```
项目/.windsurf/
  report.py              # 上报脚本（拷贝自 list-ary）
  report_config.json     # 项目名 + 看板地址
  session_id             # 当前会话 ID
  reports/               # 本地 JSON 历史
  workflows/
    task-done.md         # /task-done 手动触发
    checkpoint.md        # /checkpoint 手动触发
```

### 1.2 当前流程

```
用户输入需求 → Cascade 执行 → 用户手动键入 /task-done
→ report.py POST 到看板 → 长轮询等待回复 → stdout 输出回复 → Cascade 继续
```

### 1.3 痛点

| 痛点 | 说明 |
|------|------|
| **全靠手动触发** | 必须用户记得键入 `/task-done`，忘了就断链 |
| **缺少自动 Hook** | 没有利用 `.windsurf/rules` 实现自动上报 |
| **Workflow 模板硬编码** | `{task}` `{status}` 占位符需要 Cascade 自行替换，容易出错 |
| **无上下文同步** | 新会话无法自动拉取上次会话的上下文 |
| **单一上报模式** | 只有"完成"和"确认"两种，缺少"进度汇报""错误上报"等 |
| **缺少 rules 全局指令** | 没有告诉 Cascade "每完成一个任务必须上报" |

---

## 二、Windsurf 可用 Hook 机制

### 2.1 `.windsurf/rules`（全局规则 — 最强 Hook）

这是 **最关键的升级点**。Windsurf 会在每次对话开始时自动加载 `.windsurf/rules` 文件内容作为 Cascade 的系统指令。

**效果：** 无需用户手动输入 `/task-done`，Cascade 会自动在任务完成时执行上报。

```markdown
# .windsurf/rules

## 上报规则
- 每完成一个独立任务后，必须调用 /task-done 上报
- 遇到需要用户确认的决策时，调用 /checkpoint 等待指令
- 遇到无法解决的错误时，调用 /error-report 上报错误
- 新对话开始时，如果存在 .windsurf/session_id，调用 /sync-context 同步上下文
```

### 2.2 `.windsurf/workflows/*.md`（Slash Commands）

| 命令 | 用途 | 触发方式 |
|------|------|----------|
| `/task-done` | 任务完成上报 | 自动（rules 驱动）或手动 |
| `/checkpoint` | 需确认时暂停 | 自动或手动 |
| `/sync-context` | 拉取上次会话上下文 | 新会话自动 |
| `/error-report` | 错误/阻塞上报 | 自动 |
| `/status` | 查看当前会话状态 | 手动 |
| `/handoff` | 会话交接摘要 | 手动 |

### 2.3 `// turbo` 注解

Workflow 步骤上方加 `// turbo` 可以让 Cascade **自动执行该命令行步骤**，无需用户批准。这是实现无感上报的关键。

---

## 三、升级方案

### 3.1 新增 `.windsurf/rules` — 自动 Hook

```markdown
## 自动上报规则
1. 每完成一个用户请求的独立任务后，自动执行 /task-done 上报
2. 遇到需要用户决策的问题时，执行 /checkpoint 暂停等待
3. 遇到无法自行解决的错误或阻塞时，执行 /error-report
4. 新对话开始时，如果 .windsurf/session_id 文件存在，先执行 /sync-context
5. 上报时 --task 参数用一句话概括当前完成的工作，--questions 列出疑问
6. 收到看板回复后，严格按回复内容继续执行
```

**这是从"手动触发"到"自动触发"的核心改变。**

### 3.2 升级 Workflow 模板

#### `/task-done`（升级版）
```markdown
---
description: 任务完成后自动上报看板并等待下一步指令
---
1. 总结当前完成的任务为一句话描述
2. 执行上报：
// turbo
   python .windsurf/report.py --task "<一句话任务描述>" --status completed
3. 等待看板回复，收到后按回复内容继续执行
```

#### `/checkpoint`（升级版）
```markdown
---
description: 遇到需要确认的问题时暂停等待指令
---
1. 整理当前疑问点
2. 执行上报：
// turbo
   python .windsurf/report.py --task "<当前任务描述>" --status need_confirm --questions "<疑问1|疑问2>"
3. 等待看板回复，按回复内容调整方案继续
```

#### `/error-report`（新增）
```markdown
---
description: 遇到无法解决的错误时上报
---
1. 整理错误信息和已尝试的方案
2. 执行上报：
// turbo
   python .windsurf/report.py --task "<错误描述及已尝试方案>" --status blocked --questions "<需要的帮助>"
3. 等待看板回复获取解决方案
```

#### `/sync-context`（新增）
```markdown
---
description: 新会话开始时同步上次会话上下文
---
1. 读取上次会话上下文：
// turbo
   python .windsurf/report.py --sync
2. 将输出的上下文信息作为当前会话的背景知识
3. 告知用户已同步上次会话状态，询问下一步需求
```

#### `/status`（新增）
```markdown
---
description: 查看当前会话在看板上的状态
---
1. 查询状态：
// turbo
   python .windsurf/report.py --check-status
2. 向用户展示当前会话状态
```

#### `/handoff`（新增）
```markdown
---
description: 生成会话交接摘要供下次会话使用
---
1. 总结当前会话的所有完成工作、待办事项、关键决策
2. 执行上报：
// turbo
   python .windsurf/report.py --task "<会话总结>" --status completed --questions "会话交接"
3. 告知用户交接摘要已保存
```

### 3.3 升级 `report.py` — 新增命令

| 新增参数 | 功能 |
|---------|------|
| `--sync` | 读取本地最新 report JSON + 从看板拉取 session context，输出到 stdout |
| `--check-status` | 查询当前 session 在看板的状态，输出到 stdout |
| `--auto` | 自动模式：不等待回复，仅上报后立即返回 |
| `--context "..."` | 附加上下文信息（如错误日志片段） |

### 3.4 升级 `windsurf_setup.py` — 注入新文件

Setup 时注入的文件清单：

```
.windsurf/
  rules                  # 【新增】全局自动上报规则
  report.py              # 上报脚本（升级版）
  report_config.json     # 配置
  workflows/
    task-done.md         # 升级版
    checkpoint.md        # 升级版
    error-report.md      # 【新增】
    sync-context.md      # 【新增】
    status.md            # 【新增】
    handoff.md           # 【新增】
```

---

## 四、升级前后对比

### 4.1 流程对比

**升级前：**
```
用户输入需求 → Cascade 执行 → (用户记得手动输入 /task-done) → 上报 → 等回复
                              ↑ 经常忘记，断链
```

**升级后：**
```
用户输入需求 → Cascade 执行 → [rules 自动驱动] → 自动上报 → 等回复 → 自动继续
                                    ↑ 无需人工干预
新会话开始 → [rules 自动驱动] → /sync-context 拉取上下文 → 无缝衔接
遇到问题 → [rules 自动驱动] → /checkpoint 或 /error-report → 等回复
```

### 4.2 能力对比

| 能力 | 升级前 | 升级后 |
|------|--------|--------|
| 任务完成上报 | 手动 `/task-done` | rules 自动触发 |
| 问题确认 | 手动 `/checkpoint` | rules 自动触发 |
| 错误上报 | 无 | `/error-report` 自动触发 |
| 上下文同步 | 无 | `/sync-context` 新会话自动 |
| 会话交接 | 无 | `/handoff` 手动 |
| 状态查询 | 无 | `/status` 手动 |
| 无感运行 | 否（需用户记得） | 是（rules 驱动） |

---

## 五、实施步骤

| 步骤 | 任务 | 改动文件 |
|------|------|----------|
| 1 | 升级 `report.py`，新增 `--sync` `--check-status` `--auto` `--context` | `report/report.py` |
| 2 | 编写 `.windsurf/rules` 模板 | `windsurf_setup.py` 新增常量 |
| 3 | 新增 3 个 workflow 模板 (error-report, sync-context, status, handoff) | `windsurf_setup.py` |
| 4 | 升级 `inject_to_project()` 注入新文件 | `windsurf_setup.py` |
| 5 | 面板 UI 增加"重新注入"按钮（已配置项目可一键更新 workflows） | `server.py` + `panel.html` |
| 6 | 打包测试 | `listary_tools.spec` |

---

## 六、风险评估

| 风险 | 等级 | 缓解 |
|------|------|------|
| rules 指令被 Cascade 忽略 | 中 | 指令措辞要简洁明确，避免歧义 |
| `// turbo` 自动执行安全性 | 低 | report.py 只做 HTTP POST，无破坏性 |
| 旧项目需重新注入 | 低 | 面板提供"更新 Workflows"按钮 |
| report.py 依赖 httpx | 低 | 已有，无新增依赖 |
