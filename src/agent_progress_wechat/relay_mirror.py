"""Forward only the already-sanitized card surface belonging to the bound thread."""
import hashlib
import json
import time

from agent_progress_card.sanitize import clean_text
from .files import read_json
from agent_progress_card.choice import read_choice, read_choice_result
from .selection_text import card_code


def check_binding(directory, thread_id):
    if read_json(directory / "activity-source.json").get("thread_id") != thread_id:
        raise ValueError("小看板已切换会话；停止转发，避免串台")


def snapshot(directory, thread_id):
    check_binding(directory, thread_id)
    feed = read_json(directory / "activity.json")
    heartbeat = read_json(directory / "activity-heartbeat.json")
    if (feed.get("thread_id") != thread_id or heartbeat.get("thread_id") != thread_id
            or feed.get("error") or time.time() - heartbeat.get("checked_at", 0) > 20):
        raise ValueError("当前会话的小看板记录尚未就绪")
    state = read_json(directory / "state.json")
    if state.get("source") == "wechat":
        raise ValueError("小看板仍显示旧版独立任务，请切回当前会话")
    feed["choice"] = read_choice(directory, thread_id)
    feed["choice_result"] = read_choice_result(directory, thread_id)
    return state, feed


def choice_text(choice):
    return clean_text("看板选项 " + card_code(choice) + "：" + choice["question"] + "\n"
            + "\n".join(f"{index}. {option}" for index, option in enumerate(choice["options"], 1))
            + "\n回复示例：1 " + card_code(choice) + "（选第1项）；其他项替换开头数字。", 1800)


def overview(state, feed):
    notes = [x for x in feed.get("notes", []) if x.get("kind") == "commentary"]
    explanation = notes[-1].get("text", "") if notes else state.get("detail") or state.get("action")
    pending = feed.get("pending", [])
    tool = "\n当前工具：" + clean_text(pending[-1].get("name"), 120) if pending else ""
    return clean_text("当前任务：" + state.get("title", "当前会话") + "\n"
                      + ("执行中" if feed.get("turn_active") else "等待下一条消息")
                      + "\n" + str(explanation or "暂无新的工作说明") + tool, 1600)


def command_reply(text, state, feed):
    if text in ("帮助", "/help"):
        return ("已连接你指定的桌面会话。普通文字会作为你的消息送入该会话，保留上下文。\n"
                "选项：获取当前待选问题\n进度：查看小看板当前进度\n结果：查看最近公开回复\n"
                "审批：查看手机授权及表单；按通知编号决定，或用“填写 A编号 JSON”提交文字。不自动同意。")
    if text in ("选项", "/choice"):
        if feed.get("choice"):
            return choice_text(feed["choice"])
        question = feed.get("latest_question")
        return ("最近的客户端提问：\n" + question["text"]) if question else "当前没有已记录的选项。"
    if text in ("进度", "/status"):
        if feed.get("choice"):
            if ((feed.get("choice_result") or {}).get("choice_id") == feed["choice"]["id"]
                    and feed["choice_result"]["status"] == "uncertain"):
                return "上次选择的投递结果不确定，请先在桌面核对。"
            return choice_text(feed["choice"])
        return overview(state, feed)
    if text in ("结果", "/result"):
        notes = [x for x in feed.get("notes", []) if x.get("kind") == "final"]
        latest = feed.get("latest_reply") or (notes[-1] if notes else None)
        return "最近公开回复：\n" + (latest["text"] if latest else "当前没有已记录的最终回复。")
    return None


def mirror(store, state, feed):
    """Dedup by public note ID; commentary is throttled, final responses are not."""
    since = float(store.get("since"))
    now = time.time()
    with store.lock, store.db:
        choice = feed.get("choice")
        blocked = (choice and feed.get("choice_result")
                   and feed["choice_result"].get("choice_id") == choice["id"]
                   and feed["choice_result"].get("status") == "uncertain")
        if choice and not blocked:
            store.enqueue("choice:" + choice["id"], choice_text(choice))
        else:
            # A cleared question must not arrive after the user has already answered it on the card.
            store.db.execute("DELETE FROM outbox WHERE id LIKE 'choice:%' AND delivered=0")
        questions = feed.get("question_notices") or [feed.get("latest_question")]
        for question in questions:
            if question and not question.get("replayed") and question.get("time", 0) >= since:
                store.enqueue("prompt:" + question["id"], "客户端提问：\n" + question["text"])
        live_notes = [n for n in feed.get("notes", []) if not n.get("replayed") and n.get("time", 0) >= since]
        commentary = [n for n in live_notes if n.get("kind") == "commentary"]
        finals = [n for n in live_notes if n.get("kind") == "final"]
        candidates = list(finals)
        if commentary and now - float(store.get("last_progress", "0")) >= 20:
            latest = commentary[-1]
            # Don't send a delayed commentary after a later final reply.
            if not finals or latest["time"] > finals[-1]["time"]:
                candidates.append(latest)
        for note in sorted(candidates, key=lambda x: x["time"]):
            key = "note:" + str(note["id"])
            if store.db.execute("SELECT 1 FROM outbox WHERE id=?", (key,)).fetchone():
                continue
            label = "当前会话回复" if note["kind"] == "final" else "当前工作说明"
            store.enqueue(key, label + "\n" + clean_text(note["text"], 1800),
                          "final" if note["kind"] == "final" else "progress")
            if note["kind"] == "commentary":
                store.db.execute("INSERT OR REPLACE INTO meta VALUES ('last_progress',?)", (str(now),))
        # Manual task status is useful even when there is no new assistant note.
        material = {k: state.get(k) for k in ("task_id", "title", "status", "action", "detail")}
        digest = hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()
        if store.get("card_digest") != digest:
            store.enqueue("card:" + digest, overview(state, feed))
            store.db.execute("INSERT OR REPLACE INTO meta VALUES ('card_digest',?)", (digest,))
