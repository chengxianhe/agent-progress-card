"""Current-session mode: durable incoming text -> same thread; card -> WeChat."""
import sqlite3
import os
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
from .approval_prompt import is_approval_text, numbered_reply, label_reply
from .approval_service import run_approvals
from .approval_state import ApprovalState
from .selection_text import numbered_selection, card_code, approval_syntax
from .inbound_dispatch import take, release


def clean_progress(reply, problem):
    from agent_progress_card.sanitize import clean_text
    return clean_text(reply, 1800) + '\n\n' + problem


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
                from .delivery_policy import pause
                pause(store.db)
            if cursor:
                store.db.execute("INSERT OR IGNORE INTO meta VALUES ('cursor',?)", (cursor[0],))
            store.db.execute("INSERT OR REPLACE INTO meta VALUES ('legacy_seeded','1')")
    finally:
        old.close()


def deliver(store, session, message, directory, approvals=None, diagnostics=None):
    """Only mark sending immediately before the mutating RPC; uncertainty is terminal."""
    check_binding(directory, session.thread_id)
    from .remote_health import COMMANDS
    if message['text'] in COMMANDS:
        reply = diagnostics(False) if diagnostics else '诊断尚未初始化；没有向任务会话发送新指令。'
        store.mark(message['id'], 'local', reply=reply)
        return
    from .chat_form import deliver_form
    if deliver_form(store, session, message, directory):
        return
    ordinary = numbered_selection(message["text"], "C", bare=False)
    if ordinary:
        with choice_lock(directory):
            choice = read_choice(directory, session.thread_id)
            index, code = ordinary
            result = read_choice_result(directory, session.thread_id)
            if (not choice or card_code(choice) != code or not 1 <= index <= len(choice["options"])
                    or message.get("created", 0) < choice["created_at"]):
                store.mark(message["id"], "local", reply="这个看板 C 编号已结束或不匹配；没有回答系统请求，也没有作为新任务发送。")
                return
            if result and result["choice_id"] == choice["id"] and result["status"] == "uncertain":
                store.mark(message["id"], "local", reply="这项看板选择的上次投递回执不确定，不会重发。")
                return
            return deliver_text(store, session, {**message, "text": str(index)}, directory, choice)
    if approval_syntax(message["text"], "C"):
        store.mark(message["id"], "local", reply="看板回复格式或选项无效，请按通知示例回复“数字 C编号”；没有作为新任务发送。")
        return
    selected = numbered_reply(message["text"]) or label_reply(message["text"])
    if (selected is None and message["text"].isdigit() and len(message["text"]) <= 2
            and approvals is not None and approvals.has_recent_prompt(pending_only=True)):
        store.mark(message["id"], "local", reply="这个数字不在系统请求的可选范围内；请按最新通知回复，没有作为新任务发送。")
        return
    if approvals is not None and selected and approvals.has_recent_prompt():
        with choice_lock(directory):
            choice = read_choice(directory, session.thread_id)
            if selected[1] is None and choice and approvals.has_recent_prompt(pending_only=True):
                store.mark(message["id"], "local", reply="同时有看板选项和系统请求。看板回复“数字 " + card_code(choice)
                           + "”；系统请求请复制 A 编号通知里的完整回复示例，不能只回数字。")
            elif selected[1] is None and choice and numbered_reply(message["text"]):
                result = read_choice_result(directory, session.thread_id)
                if result and result["choice_id"] == choice["id"] and result["status"] == "uncertain":
                    store.mark(message["id"], "local", reply="这项看板选择的上次投递回执不确定，不会重发。")
                    return
                return deliver_text(store, session, {**message, "text": str(selected[0])}, directory, choice)
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
                    if not blocked:
                        from .choice_notice import publish
                        publish(store, choice, refresh=True)
                        store.mark(message['id'], 'local')
                        return
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
        reply = command_reply(message["text"], state, feed)
        if diagnostics and message['text'] in ('进度', '/status'):
            problem = diagnostics(True)
            if problem:
                reply = clean_progress(reply, problem)
        store.mark(message["id"], "local", reply=reply)
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
    if choice:
        from .choice_notice import incomplete
        if incomplete(store, choice):
            store.mark(message['id'], 'local', reply='当前问题详情尚未完整送达；发送“选项”重新获取，没有提交回答。')
            return
    text = selected_message(message["text"], choice)
    chosen_index = int(message["text"]) if choice and text != message["text"] else None
    if choice and message["text"].isdigit():
        if not 1 <= int(message["text"]) <= len(choice["options"]):
            store.mark(message["id"], "local", reply="这个数字不在当前看板选项范围内，没有作为新任务发送。")
            return
        if message.get("created", 0) < choice["created_at"]:
            store.mark(message["id"], "local", reply="这条回复早于当前看板问题，没有选择新问题；请核对最新 C 编号。")
            return
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
    health, health_lock = {'codex': '正在检查绑定会话；微信收件不依赖任务会话'}, threading.RLock()
    workers = {'main', 'poller', 'sender', 'control'}
    progress = {name: time.monotonic() for name in workers}
    auth_expired = threading.Event()
    if remote_approvals is not None:
        store.put("remote_approvals_enabled", "1" if remote_approvals else "0")
    enabled = store.get("remote_approvals_enabled") == "1"
    approval_state = ApprovalState(store, thread_id)
    approvals = approval_state if enabled else None
    if approvals:
        progress['approvals'] = time.monotonic()

    def beat(component):
        with health_lock:
            progress[component] = time.monotonic()

    def diagnostics(compact=False):
        from .remote_health import describe
        with health_lock:
            observed = dict(health)
        with store.lock:
            return describe(store, card_directory, observed, compact)

    def health_update(component, problem=""):
        with health_lock:
            health[component] = problem

    def publish():
        with health_lock:
            problems = [p for key, p in health.items() if key != 'approval_waiting' and p]
        if store.summary()['send_paused']:
            problems.append("微信推送已暂停；所有历史通知停止积累，恢复后只发当前摘要；有效审批按需查询")
        elif store.summary()["unsent"] and time.time() < float(store.get("send_paused_until", "0")):
            problems.append("微信推送暂时退避；发“进度”刷新回信")
        save_json(directory / "connection.json", {"mode": "current_session", "thread_id": thread_id,
                  "status": "retrying" if problems else "connected", "message": "；".join(problems) if problems else
                  ("已连接当前会话；手机授权和表单回复已启用，发送“审批”查看。" if approvals else
                   "已连接当前会话。微信文字会送入这段聊天，小看板进度会回传。"), **store.summary()})

    def poller():
        while not stop.is_set():
            beat('poller')
            try:
                batch = client.updates(store.get("cursor"))
                if stop.is_set():
                    break
                store.ingest(batch)
                health_update("wechat")
                stop.wait(.5)
            except LinkError as error:
                store.put("send_requires_context", "1")
                health_update("wechat", str(error))
                if error.expired:
                    auth_expired.set()
                    stop.set()
                else:
                    stop.wait(5)

    def sender():
        while not stop.is_set():
            beat('sender')
            try:
                if not send_outgoing(store, client):
                    stop.wait(.5)
                    continue
                health_update("send")
                stop.wait(1)
            except LinkError as error:
                if error.stale_context:
                    health_update("send", "微信暂时拒收回复（-2）；推送暂停，后台仍在接收新消息")
                else:
                    health_update("send", str(error) + "，推送暂停，等待新消息恢复")
                if error.expired:
                    auth_expired.set()
                    stop.set()

    def guarded(target):
        try:
            target()
        except Exception:
            health_update(target.__name__, "转发服务异常，已停止；本机记录保留")
            stop.set()

    def control_worker():
        while not stop.is_set():
            beat('control')
            message = take(store, True)
            if message:
                try:
                    deliver(store, session, message, card_directory, approvals, diagnostics)
                except (OSError, ValueError, KeyError, TransportError, RpcError, SessionUnavailable):
                    store.mark(message['id'], 'local', reply='当前状态暂不可读取；没有提交决定。\n' + diagnostics())
            stop.wait(.1)

    def watchdog():
        from .worker_watchdog import publish as heartbeat
        last_tick, wake_grace = time.time(), 0
        while not stop.is_set():
            now = time.time()
            if abs(now - last_tick) > 30:
                wake_grace = now + 20
            last_tick = now
            with health_lock:
                ages = {key: time.monotonic() - at for key, at in progress.items()}
            if heartbeat(directory, thread_id, ages, wake_grace):
                health_update('watchdog', '内部工作线程长期没有进展，桥接将受控重启；不会重做回执不确定的动作')
                stop.set()
                break
            stop.wait(3)

    threads = [threading.Thread(target=guarded, args=(target,), daemon=True)
               for target in (poller, sender, control_worker, watchdog)]
    if approvals is not None:
        threads.append(threading.Thread(target=run_approvals,
            args=(store, session, card_directory, stop, health_update, approvals, beat), daemon=True))
    for thread in threads:
        thread.start()
    next_probe = 0
    try:
        while not stop.is_set():
            beat('main')
            try:
                check_binding(card_directory, thread_id)
            except (OSError, ValueError, KeyError):
                health_update("binding", "小看板绑定变化，转发已停止")
                stop.set()
                break
            message = None
            try:
                message = take(store, False)
                if message:
                    deliver(store, session, message, card_directory, approvals)
                    health_update("codex")
                    next_probe = time.monotonic() + 10
                elif time.monotonic() >= next_probe:
                    connection = session.open()
                    try:
                        thread = session.inspect(connection)
                        flags = thread["status"].get("activeFlags", [])
                        health_update('approval_waiting', '1' if 'waitingOnApproval' in flags else '')
                        waiting = ("当前任务等待授权；微信发送“审批”查看，未支持的类型仍需电脑确认" if approvals else
                                   "当前任务等待你在原客户端确认")
                        health_update("codex", waiting if "waitingOnApproval" in flags else "")
                    finally:
                        connection.close()
                    next_probe = time.monotonic() + 10
            except (OSError, ValueError, KeyError, TransportError, RpcError, SessionUnavailable):
                release(store, message)
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
        join_deadline = time.monotonic() + 40
        for thread in threads:
            thread.join(timeout=max(0, join_deadline - time.monotonic()))
        publish()
        with health_lock:
            problems = [p for key, p in health.items() if key != 'approval_waiting' and p]
        save_json(directory / "connection.json", {"mode": "current_session", "thread_id": thread_id,
            "status": "expired" if auth_expired.is_set() else "stopped",
            "message": ("微信登录已失效，请在小看板重新扫码；" if auth_expired.is_set() else "转发已停止；")
            + ("；".join(problems) if problems else "当前 Codex 任务不受影响"),
            **store.summary()})
        store.db.close()
