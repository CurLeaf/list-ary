#!/usr/bin/env python3
"""
Windsurf 上报脚本 — 放入各项目的 .windsurf/ 目录下使用

功能：
  1. 读取 report_config.json（项目名、中台地址）
  2. 读取 reports/ 下最新一条 JSON，自动填充 previous_request
  3. 组装上报数据，写入本地 reports/ 目录
  4. POST 到中台 /api/report
  5. 长轮询等待用户回复
  6. 收到回复后写回本地 JSON，stdout 输出回复内容

用法：
  python report.py --task "完成了登录模块" --status completed --questions "重试次数设3次OK吗?"
  python report.py --task "做到一半" --status need_confirm --questions "要用OAuth吗?"
  python report.py --task "..." --status completed --offline
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta


def get_script_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def load_config(script_dir: str) -> dict:
    config_path = os.path.join(script_dir, "report_config.json")
    if not os.path.exists(config_path):
        print(f"[ERROR] 配置文件不存在: {config_path}", file=sys.stderr)
        sys.exit(1)
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_reports_dir(script_dir: str) -> str:
    reports_dir = os.path.join(script_dir, "reports")
    os.makedirs(reports_dir, exist_ok=True)
    return reports_dir


def get_session_id(script_dir: str) -> str | None:
    sid_path = os.path.join(script_dir, "session_id")
    if os.path.exists(sid_path):
        with open(sid_path, "r", encoding="utf-8") as f:
            return f.read().strip() or None
    return None


def save_session_id(script_dir: str, session_id: str):
    sid_path = os.path.join(script_dir, "session_id")
    with open(sid_path, "w", encoding="utf-8") as f:
        f.write(session_id)


def get_latest_report(reports_dir: str) -> dict | None:
    if not os.path.exists(reports_dir):
        return None
    files = sorted([f for f in os.listdir(reports_dir) if f.endswith(".json")])
    if not files:
        return None
    latest = os.path.join(reports_dir, files[-1])
    with open(latest, "r", encoding="utf-8") as f:
        return json.load(f)


def get_next_report_id(reports_dir: str) -> int:
    if not os.path.exists(reports_dir):
        return 1
    files = [f for f in os.listdir(reports_dir) if f.endswith(".json")]
    if not files:
        return 1
    ids = []
    for f in files:
        match = re.match(r"^(\d+)_", f)
        if match:
            ids.append(int(match.group(1)))
    return max(ids) + 1 if ids else 1


def sanitize_filename(text: str, max_len: int = 30) -> str:
    text = re.sub(r'[\\/:*?"<>|\n\r]', '', text)
    return text[:max_len].strip()


def save_local_report(reports_dir: str, report_data: dict) -> str:
    report_id = report_data["id"]
    date_str = datetime.now().strftime("%Y-%m-%d")
    task_short = sanitize_filename(report_data["task"])
    filename = f"{report_id:03d}_{date_str}_{task_short}.json"
    filepath = os.path.join(reports_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)
    return filepath


def update_local_report(filepath: str, reply: str, reply_timestamp: str):
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["reply"] = reply
    data["reply_timestamp"] = reply_timestamp
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat()


def post_report(dashboard_url: str, payload: dict) -> dict:
    import httpx
    url = f"{dashboard_url.rstrip('/')}/api/report"
    try:
        resp = httpx.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        print(f"[ERROR] 无法连接中台: {url}", file=sys.stderr)
        print("[INFO] 本地 JSON 已保存，中台未提交。", file=sys.stderr)
        return {}
    except Exception as e:
        print(f"[ERROR] 上报失败: {e}", file=sys.stderr)
        return {}


def poll_reply(dashboard_url: str, session_id: str, timeout: int = 30) -> str | None:
    import httpx
    url = f"{dashboard_url.rstrip('/')}/api/poll/{session_id}?timeout={timeout}"
    try:
        resp = httpx.get(url, timeout=timeout + 5)
        resp.raise_for_status()
        data = resp.json()
        if data.get("has_reply"):
            return data["reply"]
    except httpx.ReadTimeout:
        pass
    except httpx.ConnectError:
        print("[WARN] 中台连接断开，等待重连...", file=sys.stderr)
        time.sleep(5)
    except Exception as e:
        print(f"[WARN] 轮询异常: {e}", file=sys.stderr)
        time.sleep(3)
    return None


def cmd_sync(script_dir: str, config: dict):
    """--sync: 输出上次会话上下文供新会话使用"""
    reports_dir = ensure_reports_dir(script_dir)
    session_id = get_session_id(script_dir)
    latest = get_latest_report(reports_dir)
    dashboard_url = config.get("dashboard_url", "http://localhost:9000")

    lines = [f"\u9879\u76ee: {config['project_name']}"]
    if session_id:
        lines.append(f"\u4f1a\u8bdd: {session_id}")
        # 尝试从中台拉取上下文
        try:
            import httpx
            resp = httpx.get(f"{dashboard_url.rstrip('/')}/api/sessions/{session_id}/context", timeout=5)
            if resp.status_code == 200:
                lines.append(resp.json().get("context", ""))
        except Exception:
            pass
    if latest:
        lines.append(f"\u4e0a\u6b21\u4efb\u52a1: {latest.get('task', '')}")
        lines.append(f"\u72b6\u6001: {latest.get('status', '')}")
        if latest.get("reply"):
            lines.append(f"\u56de\u590d: {latest['reply']}")
        if latest.get("questions"):
            qs = latest["questions"]
            if isinstance(qs, list):
                qs = "; ".join(qs)
            lines.append(f"\u7591\u95ee: {qs}")
    if len(lines) <= 1:
        print("[INFO] \u65e0\u5386\u53f2\u4f1a\u8bdd")
        return
    print("\n".join(lines))


def cmd_check_status(script_dir: str, config: dict):
    """--check-status: 查询当前会\u8bdd\u72b6\u6001"""
    session_id = get_session_id(script_dir)
    if not session_id:
        print("[INFO] \u65e0\u6d3b\u8dc3\u4f1a\u8bdd")
        return
    dashboard_url = config.get("dashboard_url", "http://localhost:9000")
    try:
        import httpx
        resp = httpx.get(f"{dashboard_url.rstrip('/')}/api/sessions", timeout=5)
        if resp.status_code == 200:
            for s in resp.json():
                if s.get("session_id") == session_id:
                    print(f"\u4f1a\u8bdd: {session_id}")
                    print(f"\u72b6\u6001: {s.get('status', 'unknown')}")
                    print(f"\u4efb\u52a1: {s.get('task', '')}")
                    if s.get("reply"):
                        print(f"\u56de\u590d: {s['reply']}")
                    return
        print(f"[INFO] \u4f1a\u8bdd {session_id} \u5728\u4e2d\u53f0\u672a\u627e\u5230")
    except Exception as e:
        print(f"[ERROR] \u67e5\u8be2\u5931\u8d25: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Windsurf \u4e0a\u62a5\u811a\u672c")
    parser.add_argument("--task", default="", help="\u4efb\u52a1\u63cf\u8ff0")
    parser.add_argument("--status", default="completed", help="\u72b6\u6001: completed|partial|blocked|need_confirm")
    parser.add_argument("--questions", default="", help="\u7591\u95ee\u70b9\uff0c\u591a\u4e2a\u7528 | \u5206\u9694")
    parser.add_argument("--offline", action="store_true", help="\u79bb\u7ebf\u6a21\u5f0f\uff0c\u53ea\u5b58\u672c\u5730\u4e0d\u63d0\u4ea4\u4e2d\u53f0")
    parser.add_argument("--max-wait", type=int, default=3600, help="\u6700\u5927\u7b49\u5f85\u56de\u590d\u79d2\u6570\uff08\u9ed8\u8ba4 3600\uff09")
    parser.add_argument("--sync", action="store_true", help="\u540c\u6b65\u4e0a\u6b21\u4f1a\u8bdd\u4e0a\u4e0b\u6587")
    parser.add_argument("--check-status", action="store_true", help="\u67e5\u8be2\u5f53\u524d\u4f1a\u8bdd\u72b6\u6001")
    parser.add_argument("--auto", action="store_true", help="\u81ea\u52a8\u6a21\u5f0f\uff1a\u4e0a\u62a5\u540e\u4e0d\u7b49\u5f85\u56de\u590d")
    parser.add_argument("--context", default="", help="\u9644\u52a0\u4e0a\u4e0b\u6587\u4fe1\u606f")
    args = parser.parse_args()

    script_dir = get_script_dir()
    config = load_config(script_dir)

    # \u5b50\u547d\u4ee4\u5206\u53d1
    if args.sync:
        cmd_sync(script_dir, config)
        return
    if args.check_status:
        cmd_check_status(script_dir, config)
        return
    if not args.task:
        parser.error("--task is required (unless using --sync or --check-status)")

    reports_dir = ensure_reports_dir(script_dir)

    project_name = config["project_name"]
    dashboard_url = config.get("dashboard_url", "http://localhost:9000")
    session_id = get_session_id(script_dir)

    # 读取上一条记录，自动填充 previous_request
    latest = get_latest_report(reports_dir)
    previous_request = latest["task"] if latest else ""

    # 解析 questions
    questions = [q.strip() for q in args.questions.split("|") if q.strip()] if args.questions else []

    # 组装本地数据
    report_id = get_next_report_id(reports_dir)
    timestamp = now_iso()

    task_text = args.task
    if args.context:
        task_text = f"{args.task}\n---\n{args.context}"

    report_data = {
        "id": report_id,
        "session_id": session_id or "",
        "project": project_name,
        "task": task_text,
        "previous_request": previous_request,
        "status": args.status,
        "questions": questions,
        "timestamp": timestamp,
        "reply": None,
        "reply_timestamp": None,
    }

    # ③ 写入本地 JSON
    filepath = save_local_report(reports_dir, report_data)
    print(f"[INFO] 本地已保存: {filepath}", file=sys.stderr)

    if args.offline:
        print(f"[INFO] 离线模式，不提交中台。", file=sys.stderr)
        print(json.dumps({"status": "saved_offline", "file": filepath}, ensure_ascii=False))
        return

    # ④ POST 到中台
    payload = {
        "session_id": session_id,
        "project": project_name,
        "task": task_text,
        "previous_request": previous_request,
        "status": args.status,
        "questions": questions,
        "timestamp": timestamp,
    }
    result = post_report(dashboard_url, payload)
    if not result:
        print(json.dumps({"status": "submit_failed", "file": filepath}, ensure_ascii=False))
        return

    # 更新 session_id
    new_session_id = result.get("session_id", session_id)
    if new_session_id:
        save_session_id(script_dir, new_session_id)
        report_data["session_id"] = new_session_id
        # 重新保存本地 JSON 带上 session_id
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)

    print(f"[INFO] 已提交中台, session={new_session_id}, task_id={result.get('task_id')}", file=sys.stderr)

    if args.auto:
        print(json.dumps({"status": "reported", "session_id": new_session_id}, ensure_ascii=False))
        return

    # ⑤ 长轮询等待回复
    print(f"[INFO] 等待用户回复（最长 {args.max_wait}s）...", file=sys.stderr)
    wait_start = time.time()
    while True:
        if time.time() - wait_start > args.max_wait:
            print(f"[WARN] 等待超时 {args.max_wait}s，自动继续", file=sys.stderr)
            print("[TIMEOUT]")
            return
        reply = poll_reply(dashboard_url, new_session_id)
        if reply is not None:
            # ⑥ 收到回复
            reply_timestamp = now_iso()
            update_local_report(filepath, reply, reply_timestamp)
            print(f"[INFO] 收到回复，已写入本地。", file=sys.stderr)
            # stdout 输出回复内容给 Windsurf 读取
            print(reply)
            return


if __name__ == "__main__":
    main()
