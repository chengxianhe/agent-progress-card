"""Truthful feedback about request lifecycle, without guessing permission decisions."""


def blocked_reply(row, message, sent, missing_parts, bare):
    if row is None:
        return "没有找到这个系统请求编号；没有提交决定。发送“审批”查看当前请求。"
    state = row["state"]
    if state != "pending":
        reasons = {
            "resolved": "Codex 已关闭这个请求，当前不再等待它的授权；执行结果请看任务进度。",
            "expired": "这个编号已过期，本条回复没有提交授权；发送“审批”查看仍有效的请求。",
            "queued": "你的选择已收到，正在等待提交；无需重复回复。",
            "sending": "选择已发出，正在等待原生回执；不会重复提交。",
            "uncertain": "上次提交回执不确定，不能判断是否生效；不会自动重发。",
            "native": "这个请求需要尚未适配的原生处理，不能通过数字代答。",
        }
        return reasons.get(state, "这个系统请求当前不可作答；没有提交决定。")
    if message.get("created", 0) < row["created"]:
        return "这条回复早于当前请求；没有提交决定，请核对最新编号。"
    if missing_parts:
        return "完整详情还未全部送达，请等待收到最后的编号选项再回复；没有提交授权。"
    if bare and (not sent or not sent[0]):
        return "尚未确认该请求通知已发送，不能使用单独数字；请核对完整 A 编号。"
    return None
