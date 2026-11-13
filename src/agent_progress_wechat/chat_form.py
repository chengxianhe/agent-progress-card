"""Explicit C-form answers are user chat, never app-server permission responses."""
import json
import re

from agent_progress_card.choice import (choice_lock, read_choice, read_choice_result,
                                        complete_choice_unlocked, record_uncertain_choice_unlocked)
from agent_progress_card.question_choice import answer
from .selection_text import card_code
from .local_socket import RpcError, TransportError


def deliver_form(store, session, message, directory):
    text = message['text']
    if not re.match(r'^填写\s+C', text, re.I):
        return False
    with choice_lock(directory):
        match = re.fullmatch(r'填写\s+(C[0-9a-f]{10})\s+(\{.*\})', text, re.I | re.S)
        choice = read_choice(directory, session.thread_id)
        result = read_choice_result(directory, session.thread_id)
        try:
            if (not match or not choice or card_code(choice) != match[1].upper()
                    or message.get('created', 0) < choice['created_at']):
                raise ValueError('问题编号无效或回复早于问题；没有作为新任务发送')
            from .choice_notice import incomplete
            if incomplete(store, choice):
                raise ValueError('当前问题详情尚未完整送达')
            if result and result['choice_id'] == choice['id'] and result['status'] == 'uncertain':
                raise ValueError('上次答复回执不确定，不会重发，请在桌面核对')
            content = answer(choice, json.loads(match[2]))
        except (ValueError, TypeError):
            store.mark(message['id'], 'local', reply='填写格式、字段、编号或问题状态无效；发送“选项”核对，没有提交答复。')
            return True
        connection = session.open()
        try:
            method, params = session.prepare(connection, content, message['id'])
            store.mark(message['id'], 'sending')
            try:
                reply = connection.call(method, params)
                turn = reply.get('turnId') if method == 'turn/steer' else reply.get('turn', {}).get('id')
                if not isinstance(turn, str) or not turn:
                    raise TransportError('缺少回执')
            except RpcError:
                store.mark(message['id'], 'rejected', reply='当前会话拒绝了本次回答，没有投递成功；问题保留，可稍后重试。')
            except Exception:
                record_uncertain_choice_unlocked(directory, session.thread_id, choice['id'], None)
                store.mark(message['id'], 'uncertain', reply='答复回执不确定；不会重发，请在桌面核对。')
            else:
                complete_choice_unlocked(directory, session.thread_id, choice['id'], None, 'wechat')
                store.mark(message['id'], 'delivered', turn, '回答已作为本人聊天送入当前会话。')
        finally:
            connection.close()
    return True
