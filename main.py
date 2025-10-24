# -*- coding: utf-8 -*-
import time
import sys
import traceback
from wxauto import WeChat
from cozepy import Coze, TokenAuth, Message, ChatEventType
from cozepy import COZE_CN_BASE_URL
from cozepy.auth import JWTOAuthApp
import json
import os

# ==================== 1. 配置文件路径 ====================
OAUTH_CONFIG_PATH = "coze_oauth_config.json"
COZE_BOT_ID = 'git'
COZE_BASE_URL = COZE_CN_BASE_URL


# ==================== 2. 加载 OAuth App 并动态获取 token ====================
from cozepy import load_oauth_app_from_config

def load_coze_oauth_app(config_path: str) -> JWTOAuthApp:
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    return load_oauth_app_from_config(config)

oauth_app = None
current_auth = None
coze_client = None


def ensure_valid_token():
    global current_auth, coze_client, oauth_app
    try:
        if oauth_app is None:
            print("🔐 正在加载 Coze OAuth 配置...")
            oauth_app = load_coze_oauth_app(OAUTH_CONFIG_PATH)

        token_resp = oauth_app.get_access_token()
        access_token = token_resp.access_token
        current_auth = TokenAuth(token=access_token)
        coze_client = Coze(auth=current_auth, base_url="https://api.coze.cn")
        print("✅ 成功获取新的 Coze access_token")

    except Exception as e:
        print(f"❌ 获取 Coze token 失败: {e}")
        raise


# ==================== 3. 微信监听与人工审核回复 ====================
def start_wechat_bot():
    wx = WeChat()
    print("✅ 微信AI客服机器人已启动（人工审核模式）")
    print("💡 收到新消息时，会显示 Coze 的参考答案，您可以人工确认发送。")

    handled_msgs = set()

    while True:
        try:
            msgs = wx.GetAllMessage()
        except Exception as e:
            print(f"⚠️ 无法读取微信消息：{e}")
            time.sleep(2)
            continue

        if not msgs:
            time.sleep(1)
            continue

        try:
            if not msgs:
                time.sleep(1)
                continue

            last_msg = msgs[-1]
            sender = last_msg.sender
            content = last_msg.content.strip()
        except Exception:
            time.sleep(1)
            continue

        # 消息过滤逻辑
        if (
            sender == "self"
            or not content
            or len(content) < 2
            or is_system_message(last_msg)
        ):
            time.sleep(1)
            continue

        msg_key = (sender, content)
        if msg_key in handled_msgs:
            time.sleep(1)
            continue
        handled_msgs.add(msg_key)

        if len(handled_msgs) > 300:
            handled_msgs = set(list(handled_msgs)[-200:])

        print(f"\n{'=' * 80}")
        print(f"[📩 收到消息] 来自 {sender}: {content}")
        print(f"{'=' * 80}")

        reply_content = ""
        user_id = f"wechat_{hash(sender) % 1000000}"

        try:
            ensure_valid_token()
            print("🤖 正在调用 Coze 智能体生成参考答案...")

            for event in coze_client.chat.stream(
                bot_id=COZE_BOT_ID,
                user_id=user_id,
                additional_messages=[Message.build_user_question_text(content)],
            ):
                if event.event == ChatEventType.CONVERSATION_MESSAGE_DELTA:
                    if event.message and getattr(event.message, "content", None):
                        reply_content += event.message.content

            reply_content = reply_content.strip() or "您好，我暂时无法回答这个问题，请稍后再试。"
            final_reply = reply_content[:800]

            print(f"\n🧠 [Coze 参考回复]：\n{final_reply}")

            # ======== 人工审核操作 ========
            while True:
                print("\n请选择操作：")
                print("1. ✅ 发送参考回复")
                print("2. ✏️ 修改并发送")
                print("3. 🚫 忽略此消息")
                print("4. 🧱 退出程序")

                choice = input("请输入选项 (1-4): ").strip()

                if choice == "1":
                    wx.SendMsg(final_reply, sender)
                    print(f"[📤 已发送回复] {sender}: {final_reply}")
                    break
                elif choice == "2":
                    custom_reply = input("请输入自定义回复内容 (直接回车取消): ").strip()
                    if custom_reply:
                        wx.SendMsg(custom_reply[:800], sender)
                        print(f"[📤 已发送自定义回复] {sender}: {custom_reply}")
                    else:
                        print("✓ 已取消发送")
                    break
                elif choice == "3":
                    print("✓ 已忽略此消息")
                    break
                elif choice == "4":
                    print("👋 正在退出程序...")
                    sys.exit(0)
                else:
                    print("❌ 无效选项，请重新输入")

        except Exception as e:
            print(f"⚠️ 调用 Coze 失败: {e}")
            traceback.print_exc()
            handle_error_manually(wx, sender)

        print(f"{'-' * 80}")
        print("⌛ 继续监听新消息...\n")
        time.sleep(1)


# ==================== 错误处理兜底 ====================
def handle_error_manually(wx, sender):
    """统一错误兜底逻辑，支持人工修正和安全回复"""
    for _ in range(3):
        try:
            print("\n请选择错误处理操作：")
            print("1. ⚠️ 发送默认错误提示")
            print("2. ✏️ 自定义回复")
            print("3. 🚫 忽略此消息")
            print("4. 🧱 退出程序")

            choice = input("请输入选项 (1-4): ").strip()

            if choice == "1":
                wx.SendMsg("您好，当前AI服务暂时不可用，请稍后再试。", sender)
                print("[📤 已发送错误提示]")
                return
            elif choice == "2":
                custom_reply = input("请输入自定义回复内容 (直接回车取消): ").strip()
                if custom_reply:
                    wx.SendMsg(custom_reply[:800], sender)
                    print("[📤 已发送自定义回复]")
                else:
                    print("✓ 已取消发送")
                return
            elif choice == "3":
                print("✓ 已忽略此消息")
                return
            elif choice == "4":
                print("👋 程序退出")
                sys.exit(0)
            else:
                print("❌ 无效选项，请重新输入")
        except Exception as e:
            print(f"❌ 处理错误时发生异常: {e}")
            traceback.print_exc()
            time.sleep(2)

    # 连续错误三次后的安全兜底
    try:
        wx.SendMsg("抱歉，系统出现异常，稍后再试。", sender)
        print("⚠️ 已自动发送兜底错误提示。")
    except Exception as e:
        print(f"❌ 兜底发送失败: {e}")


# ==================== 判断是否为系统消息 ====================
def is_system_message(msg):
    system_keywords = [
        "系统通知", "安全提示", "账号安全性", "风险提示", "异常行为",
        "微信团队", "官方提醒", "功能升级", "服务调整"
    ]
    content = getattr(msg, "content", "")
    return any(keyword in content for keyword in system_keywords)


# ==================== 启动入口 ====================
if __name__ == "__main__":
    print("💡 正在启动微信机器人（Coze 智能体 + 人工审核版）...")
    print("🔹 请确认配置文件 coze_oauth_config_temple.json 存在且有效")
    print("🔹 请确认 Coze Bot 已启用并可访问")
    time.sleep(2)

    if not os.path.exists(OAUTH_CONFIG_PATH):
        print(f"❌ 错误：找不到配置文件 {OAUTH_CONFIG_PATH}")
        sys.exit(1)

    start_wechat_bot()
