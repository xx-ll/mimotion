# -*- coding: utf-8 -*-
"""企业微信智能机器人 - 获取单聊 userid 调试工具

用法：
  1. 在 .env 中配置 WECOM_SMART_BOT_ID / WECOM_SMART_BOT_SECRET
     （机器人创建者需为超级管理员，才能拿到明文 userid）
  2. 运行：python wecom_get_userids.py
  3. 让目标用户在企业微信中给该机器人发一条消息
  4. 脚本会打印该消息中的 from.userid，将其填入 WECOM_SMART_BOT_CHAT_ID 即可
  （多个 userid 可用 # 分隔，脚本会持续监听，按 Ctrl+C 退出）
"""
import json
import os
import time

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"), override=True)
except ImportError:
    pass

from util.push_util import WeComSmartBot


def main():
    bot_id = os.environ.get("WECOM_SMART_BOT_ID", "").strip()
    secret = os.environ.get("WECOM_SMART_BOT_SECRET", "").strip()
    if not (bot_id and secret):
        print("未配置 WECOM_SMART_BOT_ID / WECOM_SMART_BOT_SECRET，请先在 .env 中填写后重试")
        return

    bot = WeComSmartBot(bot_id, secret)
    try:
        bot.connect()
        print("长连接已建立，等待消息回调...")
        print("提示：请让目标用户给该机器人发一条消息，脚本将打印其 userid，按 Ctrl+C 退出")
    except Exception as e:
        print(f"连接异常: {e}")
        return

    last_ping = time.time()
    try:
        while True:
            # 每 30 秒发送一次心跳保活
            if time.time() - last_ping >= 30:
                bot.ping()
                last_ping = time.time()

            raw = bot.recv(timeout=5)
            if not raw:
                continue
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            cmd = msg.get("cmd", "")
            body = msg.get("body", {}) or {}
            if cmd == "aibot_msg_callback":
                from_info = body.get("from", {}) or {}
                userid = from_info.get("userid", "")
                chatid = body.get("chatid", "")
                print(f"[{time.strftime('%H:%M:%S')}] 收到消息 -> userid: {userid} | chatid: {chatid}")
                if userid:
                    print(f"  可将该 userid 填入 WECOM_SMART_BOT_CHAT_ID（WECOM_SMART_BOT_CHAT_TYPE=1 单聊推送）")
            elif cmd == "aibot_event_callback":
                print(f"[{time.strftime('%H:%M:%S')}] 事件回调: {msg}")
            else:
                print(f"[{time.strftime('%H:%M:%S')}] 其他消息: {msg}")
    except KeyboardInterrupt:
        print("\n已停止监听")
    finally:
        bot.close()


if __name__ == "__main__":
    main()
