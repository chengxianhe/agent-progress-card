"""Current-session mode: durable incoming text -> same thread; card -> WeChat."""
import sqlite3
import threading
import time

from agent_progress_card.choice import (choice_lock, complete_choice_unlocked, read_choice, read_choice_result,
                                        recent_choice_result, record_uncertain_choice_unlocked)
from .current_session import CurrentSession, SessionUnavailable
from .files import save_json
from .ilink import Client, LinkError
from .local_socket import RpcError, TransportError
from .relay_mirror import check_binding, choice_text, command_reply, mirror, snapshot
from .relay_store import RelayStore
from .notification_delivery import send_outgoing
from .approval_prompt import is_approval_text, numbered_reply
from .approval_service import run_approvals
from .approval_state import ApprovalState


def selected_message(text, choice):
    if not choice or not text.isdigit() or len(text) > 2:
        return text
    index = int(text)
    if 1 <= index <= len(choice["options"]):
        return "我选择第 " + text + " 项：" + choice["options"][index - 1]
    return text


def seed_previous_connection(store, directory, owner):
    """Reuse only this owner's last reply context/cursor; never replay old tasks."""
    path = directory / "bridge.sqlite3"
    if not path.exists() or store.get("legacy_seeded"):
        return
    old = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        saved = old.execute("SELECT value FROM meta WHERE key='owner'").fetchone()
        if not saved or saved[0] != owner:
            raise ValueError("微信绑定与旧记录不一致")
        context = old.execute("SELECT context FROM tasks ORDER BY created DESC LIMIT 1").fetchone()
        cursor = old.execute("SELECT value FROM meta WHERE key='cursor'").fetchone()
        with store.lock, store.db:
            if context:
                store.db.execute("INSERT OR IGNORE INTO meta VALUES ('context',?)", (context[0],))
            if cursor:
                store.db.execute("INSERT OR IGNORE INTO meta VALUES ('cursor',?)", (cursor[0],))
            store.db.execute("INSERT OR REPLACE INTO meta VALUES ('legacy_seeded','1')")
    finally:
        old.close()


def deliver(store, session, message, directory, approvals=None):
    """Only mark sending immediately before the mutating RPC; uncertainty is terminal."""
    check_binding(directory, session.thread_id)
    if approvals is not None and numbered_reply(message["text"]) and approvals.has_recent_prompt():
        with choice_lock(directory):
            if numbered_reply(message["text"])[1] is None and read_choice(directory, session.thread_id):
                store.mark(message["id"], "local", reply="同时有普通选项和命令审批，请回复「选项号 A审批编号」处理审批；普通选项请在小看板点击。")
            else:
                approvals.handle(message)
        return
    if is_approval_text(message["text"]):
        if approvals is None:
            store.mark(message["id"], "local", reply="微信审批未启用，请在电脑端确认。")
        else:
            approvals.handle(message)
        return
    if message["text"] in ("选项", "/choice"):
        with choice_lock(directory):
            choice = read_choice(directory, session.thread_id)
            result = read_choice_result(directory, session.thread_id)
            blocked = choice and result and result["choice_id"] == choice["id"] and result["status"] == "uncertain"
            if choice:
                with store.lock, store.db:
                    store.db.execute("DELETE FROM outbox WHERE id=? AND delivered=0", ("choice:" + choice["id"],))
            reply = "上次选择的投递结果不确定，请先在桌面核对。" if blocked else (
                choice_text(choice) if choice else "当前没有待选问题。")
            if not choice:
                try:
                    state, feed = snapshot(directory, session.thread_id)
                    reply = command_reply(message["text"], state, feed)
                except (OSError, ValueError, KeyError, TypeError):
                    reply = "当前没有看板选项；客户端提问记录暂不可读，请在原客户端核对。"
            store.mark(message["id"], "local", reply=reply)
        return
    if message["text"] in ("帮助", "/help", "进度", "/status", "结果", "/result"):
        state, feed = snapshot(directory, session.thread_id)
        store.mark(message["id"], "local", reply=command_reply(message["text"], state, feed))
        return
    if message["text"].isdigit() and len(message["text"]) <= 2:
        with choice_lock(directory):
            choice = read_choice(directory, session.thread_id)
            index = int(message["text"])
            result = read_choice_result(directory, session.thread_id)
            if choice and result and result["choice_id"] == choice["id"] and result["status"] == "uncertain":
                store.mark(message["id"], "local", reply="上次选择的投递结果不确定，请先在桌面核对。")
                return
            if not choice and recent_choice_result(directory, session.thread_id, index):
                store.mark(message["id"], "local", reply="这项选择已经收到，无需重复发送。")
                return
            if not choice:
                try:
                    _, feed = snapshot(directory, session.thread_id)
                except (OSError, ValueError, KeyError, TypeError):
                    feed = {}
                question = feed.get("latest_question")
                if question and 0 <= time.time() - question.get("time", 0) <= 86400:
                    store.mark(message["id"], "local", reply="最近的问题来自客户端原生表单；请在原客户端选择。这个编号没有代答表单，也没有作为新任务发送。")
                    return
            return deliver_text(store, session, message, directory, choice)
    return deliver_text(store, session, message, directory)


def deliver_text(store, session, message, directory, choice=None):
    text = selected_message(message["text"], choice)
    chosen_index = int(message["text"]) if choice and text != message["text"] else None
    connection = session.open()
    try:
        method, params = session.prepare(connection, text, message["id"])
        store.mark(message["id"], "sending")
        try:
            result = connection.call(method, params)
            turn = result.get("turnId") if method == "turn/steer" else result.get("turn", {}).get("id")
            if not isinstance(turn, str) or not turn:
                raise TransportError("缺少投递回执")
        except RpcError:
            store.mark(message["id"], "rejected", reply="当前会话拒绝了这次投递；没有转发成功，请稍后重发。")
        except Exception:
            if chosen_index is not None:
                record_uncertain_choice_unlocked(directory, session.thread_id, choice["id"], chosen_index)
            store.mark(message["id"], "uncertain", reply="消息投递回执丢失，可能已进入当前会话。为避免重复执行，不会自动重发，请先在桌面核对。")
        else:
            if chosen_index is not None:
                complete_choice_unlocked(directory, session.thread_id, choice["id"], chosen_index, "wechat")
            receipt = ("已收到第 " + str(chosen_index) + " 项，送入当前会话。") if chosen_index is not None else (
                "已送入当前会话。" if method == "turn/start" else "已补充到当前正在执行的任务。")
            store.mark(message["id"], "delivered", turn, receipt)
    finally:
        connection.close()


def run_relay(directory, credentials, thread_id, socket_path, card_directory, stop, remote_approvals=None):
    store = RelayStore(directory, credentials["owner"], thread_id)
    seed_previous_connection(store, directory, credentials["owner"])
    session = CurrentSession(socket_path, thread_id)
    client = Client(credentials)
    health, health_lock = {}, threading.RLock()
    auth_expired = threading.Event()
    if remote_approvals is not None:
        store.put("remote_approvals_enabled", "1" if remote_approvals else "0")
    enabled = store.get("remote_approvals_enabled") == "1"
    approval_state = ApprovalState(store, thread_id)
    approvals = approval_state if enabled else None

    def health_update(component, problem=""):
        with health_lock:
            health[component] = problem

    def publish():
        with health_lock:
            problems = [p for p in health.values() if p]
        if store.summary()["unsent"] and time.time() < float(store.get("send_paused_until", "0")):
            problems.append("后台仍在运行；微信暂时拒收回复，5 分钟内重试；可发“进度”刷新回信")
        save_json(directory / "connection.json", {"mode": "current_session", "thread_id": thread_id,
                  "status": "retrying" if problems else "connected", "message": "；".join(problems) if problems else
                  ("已连接当前会话；本人微信单次命令审批已启用，发送“审批”查看。" if approvals else
                   "已连接当前会话。微信文字会送入这段聊天，小看板进度会回传。"), **store.summary()})

    def poller():
        while not stop.is_set():
            try:
                batch = client.updates(store.get("cursor"))
                if stop.is_set():
                    break
                store.ingest(batch)
                health_update("wechat")
                stop.wait(.5)
            except LinkError as error:
                health_update("wechat", str(error))
                if error.expired:
                    auth_expired.set()
                    stop.set()
                else:
                    stop.wait(5)

    def sender():
        while not stop.is_set():
            try:
                if not send_outgoing(store, client):
                    stop.wait(.5)
                    continue
                health_update("send")
                stop.wait(1)
            except LinkError as error:
                if error.stale_context:
                    health_update("send", "微信暂时拒收回复（-2）；通知已保留，后台仍在接收消息和重试")
                else:
                    health_update("send", str(error) + "，回复保留并退避重试")
                if error.expired:
                    auth_expired.set()
                    stop.set()

    def guarded(target):
        try:
            target()
        except Exception:
            health_update(target.__name__, "转发服务异常，已停止；本机记录保留")
            stop.set()

    threads = [threading.Thread(target=guarded, args=(poller,)), threading.Thread(target=guarded, args=(sender,))]
    if approvals is not None:
        threads.append(threading.Thread(target=run_approvals,
            args=(store, session, card_directory, stop, health_update, approvals)))
    for thread in threads:
        thread.start()
    next_probe = 0
    try:
        while not stop.is_set():
            try:
                check_binding(card_directory, thread_id)
            except (OSError, ValueError, KeyError):
                health_update("binding", "小看板绑定变化，转发已停止")
                stop.set()
                break
            try:
                message = store.next_message()
                if message:
                    deliver(store, session, message, card_directory, approvals)
                    health_update("codex")
                    next_probe = time.monotonic() + 10
                elif time.monotonic() >= next_probe:
                    connection = session.open()
                    try:
                        thread = session.inspect(connection)
                        flags = thread["status"].get("activeFlags", [])
                        waiting = ("当前任务等待授权；微信发送“审批”查看，未支持的类型仍需电脑确认" if approvals else
                                   "当前任务等待你在原客户端确认")
                        health_update("codex", waiting if "waitingOnApproval" in flags else "")
                    finally:
                        connection.close()
                    next_probe = time.monotonic() + 10
            except (OSError, ValueError, KeyError, TransportError, RpcError, SessionUnavailable):
                health_update("codex", "当前会话暂不可投递；消息保留排队，请检查桌面会话")
                stop.wait(2)
            try:
                state, feed = snapshot(card_directory, thread_id)
                mirror(store, state, feed)
                health_update("card")
            except (OSError, ValueError, KeyError, TypeError):
                health_update("card", "当前会话的看板进度暂不可读")
            publish()
            stop.wait(.5)
    finally:
        stop.set()
        for thread in threads:
            thread.join(timeout=40)
        publish()
        with health_lock:
            problems = [p for p in health.values() if p]
        save_json(directory / "connection.json", {"mode": "current_session", "thread_id": thread_id,
            "status": "expired" if auth_expired.is_set() else "stopped",
            "message": ("微信登录已失效，请在小看板重新扫码；" if auth_expired.is_set() else "转发已停止；")
            + ("；".join(problems) if problems else "当前 Codex 任务不受影响"),
            **store.summary()})
        store.db.close()
