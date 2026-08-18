import json
import time
import uuid

import requests
from datetime import datetime
import pytz


def get_beijing_time():
    """获取北京时间"""
    target_timezone = pytz.timezone('Asia/Shanghai')
    return datetime.now().astimezone(target_timezone)


def format_now():
    """格式化当前时间"""
    return get_beijing_time().strftime("%Y-%m-%d %H:%M:%S")


class PushConfig:
    """推送配置类"""

    def __init__(self,
                 push_plus_token=None,
                 push_plus_hour=None,
                 push_plus_max=30,
                 push_wechat_webhook_key=None,
                 telegram_bot_token=None,
                 telegram_chat_id=None,
                 wecom_smart_bot_id=None,
                 wecom_smart_bot_secret=None,
                 wecom_smart_bot_chat_id=None,
                 wecom_smart_bot_chat_type=0):
        self.push_plus_token = push_plus_token
        self.push_plus_hour = push_plus_hour
        self.push_plus_max = int(push_plus_max) if push_plus_max else 30
        self.push_wechat_webhook_key = push_wechat_webhook_key
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id
        self.wecom_smart_bot_id = wecom_smart_bot_id
        self.wecom_smart_bot_secret = wecom_smart_bot_secret
        self.wecom_smart_bot_chat_id = wecom_smart_bot_chat_id
        self.wecom_smart_bot_chat_type = int(wecom_smart_bot_chat_type) if wecom_smart_bot_chat_type else 0


def push_plus(token, title, content):
    """
    推送消息类型为html 需要在外部组装html代码的content
    :param token: PUSHPLUS 的token
    :param title: 推送标题
    :param content: 推送内容
    :return: none
    """
    requestUrl = f"http://www.pushplus.plus/send"
    data = {
        "token": token,
        "title": title,
        "content": content,
        "template": "html",
        "channel": "wechat"
    }
    try:
        response = requests.post(requestUrl, data=data)
        if response.status_code == 200:
            json_res = response.json()
            print(f"pushplus推送完毕：{json_res['code']}-{json_res['msg']}")
        else:
            print("pushplus推送失败")
    except requests.exceptions.RequestException as e:
        print(f"pushplus推送网络异常: {e}")
    except Exception as e:
        print(f"pushplus推送未知异常: {e}")


def push_wechat_webhook(key, title, content):
    """
    推送企业微信通知，WebHook方式，需要注册企业微信并配置机器人到对应的推送群。然后提取对应的key

    :param key: WebHook机器人的key
    :param title: 推送标题
    :param content: 推送内容，虽然支持markdown，但是在使用微信插件时，消息不能被完整展示，直接使用纯文本效果会更好
    :return:
    """

    requestUrl = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={key}"

    payload = {
        "msgtype": "markdown_v2",
        "markdown_v2": {
            "content": buildWeChatContent(title, content)
        }
    }

    try:
        response = requests.post(requestUrl, json=payload)
        if response.status_code == 200:
            json_res = response.json()
            if json_res.get('errcode') == 0:
                print(f"企业微信推送完毕：{json_res['errmsg']}")
            else:
                print(f"企业微信推送失败：{json_res.get('errmsg', '未知错误')}")
        else:
            print("企业微信推送失败")
    except requests.exceptions.RequestException as e:
        print(f"企业微信推送异常: {e}")
    except Exception as e:
        print(f"企业微信推送发生未知异常: {e}")


def buildWeChatContent(title, content) -> str:
    return f"""# {title}\n{content}"""


class WeComSmartBot:
    """企业微信智能机器人（长连接）主动推送客户端

    文档：https://open.work.weixin.qq.com/help2/pc/cat?doc_id=21661
    流程：建立 WebSocket 长连接 -> aibot_subscribe 订阅认证 -> aibot_send_msg 主动推送消息
    注意：需用户先在该会话中给机器人发送过至少一条消息，后续才能主动推送。
    """

    WS_URL = "wss://openws.work.weixin.qq.com"

    def __init__(self, bot_id, secret, chat_id=None, chat_type=0):
        """
        :param bot_id: 智能机器人 BotID
        :param secret: 智能机器人 Secret
        :param chat_id: 推送目标会话，单聊填用户 userid，群聊填群聊 chatid
        :param chat_type: 会话类型，1 单聊 / 2 群聊 / 0 兼容模式（默认，优先按群聊发送）
        """
        self.bot_id = bot_id
        self.secret = secret
        self.chat_id = chat_id
        self.chat_type = chat_type
        self.ws = None

    def connect(self):
        """建立长连接并完成订阅认证，校验服务端响应"""
        try:
            from websocket import create_connection
        except ImportError:
            raise RuntimeError("缺少 websocket-client 依赖，请先执行 pip install -e .")
        self.ws = create_connection(self.WS_URL, timeout=15)
        req_id = self._send_command("aibot_subscribe", {
            "bot_id": self.bot_id,
            "secret": self.secret
        })
        resp = self._recv_response(req_id, timeout=10)
        if resp.get("errcode") != 0:
            raise RuntimeError(f"订阅认证失败: errcode={resp.get('errcode')} errmsg={resp.get('errmsg')}")

    def _send_command(self, cmd, body):
        if not self.ws:
            raise RuntimeError("尚未建立长连接，请先调用 connect()")
        req_id = str(uuid.uuid4())
        payload = {
            "cmd": cmd,
            "headers": {"req_id": req_id},
            "body": body
        }
        self.ws.send(json.dumps(payload))
        return req_id

    def _recv_response(self, req_id, timeout=5):
        """接收与 req_id 匹配的服务端响应帧，超时返回 {}"""
        if not self.ws:
            return {}
        self.ws.settimeout(timeout)
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                raw = self.ws.recv()
            except Exception:
                return {}
            try:
                msg = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            if msg.get("headers", {}).get("req_id") == req_id:
                return msg
        return {}

    def send_markdown(self, content, chat_id=None):
        """主动推送 markdown 消息，校验服务端响应

        :param content: markdown 内容
        :param chat_id: 推送目标会话，单聊填用户 userid，群聊填群聊 chatid；不传则使用构造时的 chat_id
        :raises RuntimeError: 服务端返回 errcode != 0 或超时未收到响应
        """
        target = chat_id or self.chat_id
        req_id = self._send_command("aibot_send_msg", {
            "chatid": target,
            "chat_type": self.chat_type,
            "msgtype": "markdown",
            "markdown": {"content": content}
        })
        resp = self._recv_response(req_id, timeout=10)
        if not resp:
            raise RuntimeError(f"发送消息超时未收到响应 (chatid={target})")
        if resp.get("errcode") != 0:
            raise RuntimeError(f"发送消息失败 (chatid={target}): errcode={resp.get('errcode')} errmsg={resp.get('errmsg')}")

    def ping(self):
        """发送心跳保活"""
        self._send_command("ping", {})

    def recv(self, timeout=5):
        """接收一条长连接消息，超时返回 None（用于监听回调/调试）"""
        if not self.ws:
            raise RuntimeError("尚未建立长连接，请先调用 connect()")
        try:
            self.ws.settimeout(timeout)
            raw = self.ws.recv()
            return raw
        except Exception:
            return None

    def close(self):
        """关闭长连接"""
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
            self.ws = None


def push_to_wecom_smart_bot(exec_results, summary, config: PushConfig):
    """推送到企业微信智能机器人（长连接方式）"""
    if not (config.wecom_smart_bot_id and config.wecom_smart_bot_secret and config.wecom_smart_bot_chat_id):
        print("未配置 WECOM_SMART_BOT_ID/SECRET/CHAT_ID 跳过企业微信智能机器人推送")
        return

    # 支持多个单聊 userid / 群聊 chatid，用 # 分隔逐条推送
    chat_ids = [c.strip() for c in str(config.wecom_smart_bot_chat_id).split('#') if c.strip()]
    if not chat_ids:
        print("未配置有效的 WECOM_SMART_BOT_CHAT_ID 跳过企业微信智能机器人推送")
        return

    content = f'## {summary}'
    if len(exec_results) >= config.push_plus_max:
        content += '\n- 账号数量过多，详细情况请前往github actions中查看'
    else:
        for exec_result in exec_results:
            success = exec_result['success']
            if success is not None and success is True:
                content += f'\n- 账号：{exec_result["user"]}刷步数成功，接口返回：{exec_result["msg"]}'
            else:
                content += f'\n- 账号：{exec_result["user"]}刷步数失败，失败原因：{exec_result["msg"]}'

    bot = WeComSmartBot(config.wecom_smart_bot_id, config.wecom_smart_bot_secret,
                        chat_id=chat_ids[0], chat_type=config.wecom_smart_bot_chat_type)
    msg = buildWeChatContent(f"{format_now()} 刷步数通知", content)
    try:
        bot.connect()
        print(f"企业微信智能机器人订阅成功，chat_type={config.wecom_smart_bot_chat_type}")
        success_cnt = 0
        for cid in chat_ids:
            try:
                bot.send_markdown(msg, chat_id=cid)
                success_cnt += 1
            except Exception as e:
                print(f"企业微信智能机器人推送失败 ({cid}): {e}")
        print(f"企业微信智能机器人推送完毕，成功 {success_cnt}/{len(chat_ids)} 个会话")
    except Exception as e:
        print(f"企业微信智能机器人推送异常: {e}")
    finally:
        bot.close()


def push_telegram_bot(bot_token, chat_id, content):
    """
    推送消息类型为html 需要在外部组装html content
    :param bot_token: telegram bot token
    :param chat_id: telegram bot chat_id
    :param content: 推送内容
    :return: none
    """
    requestUrl = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    payload = {
        "chat_id": int(chat_id),
        "text": content,
        "parse_mode": "HTML"
    }
    print(f"post to url: {requestUrl}")
    print(f"payload: {json.dumps(payload)}")
    try:
        response = requests.post(requestUrl, json=payload)
        if response.status_code == 200:
            json_res = response.json()
            if json_res.get('ok') is True:
                print(f"telegram bot推送完毕：{json_res['result']['message_id']}")
            else:
                print(f"telegram bot推送失败: {json.dumps(json_res)}")
        else:
            print(f"telegram bot推送失败: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"telegram bot推送异常: {e}")
    except Exception as e:
        print(f"telegram bot推送发生未知异常: {e}")


def push_results(exec_results, summary, config: PushConfig):
    """推送所有结果"""
    if not_in_push_time_range(config):
        return
    push_to_push_plus(exec_results, summary, config)
    push_to_wechat_webhook(exec_results, summary, config)
    push_to_wecom_smart_bot(exec_results, summary, config)
    push_to_telegram_bot(exec_results, summary, config)


def not_in_push_time_range(config: PushConfig) -> bool:
    """检查是否在推送时间范围内"""
    if not config.push_plus_hour:
        return False  # 如果没有设置推送时间，则总是推送

    time_bj = get_beijing_time()

    # 首先根据时间判断，如果匹配 直接返回
    if config.push_plus_hour.isdigit():
        if time_bj.hour == int(config.push_plus_hour):
            print(f"当前设置推送整点为：{config.push_plus_hour}, 当前整点为：{time_bj.hour}，执行推送")
            return False

    # 如果时间不匹配，检查cron_change_time文件中的记录
    # 读取cron_change_time文件中的最后一行数据：“next exec time: UTC(7:35) 北京时间(15:35)” 中的整点数
    # 然后用来对比是否当前时间，避免因为Actions执行延迟导致推送失效
    try:
        with open('cron_change_time', 'r') as f:
            lines = f.readlines()
            if lines:
                last_line = lines[-1].strip()
                # 提取北京时间的小时数
                import re
                match = re.search(r'北京时间\(0?(\d+):\d+\)', last_line)
                if match:
                    cron_hour = int(match.group(1))
                    if int(config.push_plus_hour) == cron_hour:
                        print(
                            f"当前设置推送整点为：{config.push_plus_hour}, 根据执行记录，本次执行整点为：{cron_hour}，执行推送")
                        return False
    except Exception as e:
        print(f"读取cron_change_time文件出错: {e}")
    print(f"当前整点时间为：{time_bj}，不在配置的推送时间，不执行推送")
    return True


def push_to_push_plus(exec_results, summary, config: PushConfig):
    """推送到PushPlus"""
    # 判断是否需要pushplus推送
    if config.push_plus_token and config.push_plus_token != '' and config.push_plus_token != 'NO':
        html = f'<div>{summary}</div>'
        if len(exec_results) >= config.push_plus_max:
            html += '<div>账号数量过多，详细情况请前往github actions中查看</div>'
        else:
            html += '<ul>'
            for exec_result in exec_results:
                success = exec_result['success']
                if success is not None and success is True:
                    html += f'<li><span>账号：{exec_result["user"]}</span>刷步数成功，接口返回：{exec_result["msg"]}</li>'
                else:
                    html += f'<li><span>账号：{exec_result["user"]}</span>刷步数失败，失败原因：{exec_result["msg"]}</li>'
            html += '</ul>'
        push_plus(config.push_plus_token, f"{format_now()} 刷步数通知", html)
    else:
        print("未配置 PUSH_PLUS_TOKEN 跳过PUSHPLUS推送")


def push_to_wechat_webhook(exec_results, summary, config: PushConfig):
    """推送到企业微信"""
    # 判断是否需要微信推送
    if config.push_wechat_webhook_key and config.push_wechat_webhook_key != '' and config.push_wechat_webhook_key != 'NO':

        content = f'## {summary}'
        if len(exec_results) >= config.push_plus_max:
            content += '\n- 账号数量过多，详细情况请前往github actions中查看'
        else:
            for exec_result in exec_results:
                success = exec_result['success']
                if success is not None and success is True:
                    content += f'\n- 账号：{exec_result["user"]}刷步数成功，接口返回：{exec_result["msg"]}'
                else:
                    content += f'\n- 账号：{exec_result["user"]}刷步数失败，失败原因：{exec_result["msg"]}'
        push_wechat_webhook(config.push_wechat_webhook_key, f"{format_now()} 刷步数通知", content)
    else:
        print("未配置 WECHAT_WEBHOOK_KEY 跳过微信推送")


def push_to_telegram_bot(exec_results, summary, config: PushConfig):
    """推送到Telegram"""
    # 判断是否需要telegram推送
    if (config.telegram_bot_token and config.telegram_bot_token != '' and config.telegram_bot_token != 'NO' and
            config.telegram_chat_id and config.telegram_chat_id != ''):
        html = f'<b>{summary}</b>'
        if len(exec_results) >= config.push_plus_max:
            html += '<blockquote>账号数量过多，详细情况请前往github actions中查看</blockquote>'
        else:
            for exec_result in exec_results:
                success = exec_result['success']
                if success is not None and success is True:
                    html += f'<pre><blockquote>账号：{exec_result["user"]}</blockquote>刷步数成功，接口返回：<b>{exec_result["msg"]}</b></pre>'
                else:
                    html += f'<pre><blockquote>账号：{exec_result["user"]}</blockquote>刷步数失败，失败原因：<b>{exec_result["msg"]}</b></pre>'
        push_telegram_bot(config.telegram_bot_token, config.telegram_chat_id, html)
    else:
        print("未配置 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID 跳过telegram推送")
