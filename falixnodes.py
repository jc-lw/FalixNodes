import time
import os
import json
import re
import random
import requests

# 智能环境配置
if "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":1"
    
if "XAUTHORITY" not in os.environ:
    if os.path.exists("/home/headless/.Xauthority"):
        os.environ["XAUTHORITY"] = "/home/headless/.Xauthority"

from seleniumbase import SB

# ================= 配置区域 =================
PROXY_URL = os.getenv("PROXY", "")
NUM = os.getenv("NUM")
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")

# 死磕的唯一目标链接
TAGET = f"https://client.falixnodes.net/timer?id={NUM}"
# ===========================================

class FalixNodesRenewal:
    def __init__(self):
        self.BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        self.screenshot_dir = os.path.join(self.BASE_DIR, "artifacts")
        if not os.path.exists(self.screenshot_dir):
            os.makedirs(self.screenshot_dir)

    def log(self, msg):
        timestamp = time.strftime('%H:%M:%S')
        print(f"[{timestamp}] [INFO] {msg}", flush=True)

    def send_telegram_notify(self, message, photo_path=None):
        if not TG_TOKEN or not TG_CHAT_ID:
            self.log("⚠️ 未配置 TG_TOKEN，跳过推送喵。")
            return
        try:
            if photo_path and os.path.exists(photo_path):
                url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
                with open(photo_path, 'rb') as f:
                    requests.post(url, data={'chat_id': TG_CHAT_ID, 'caption': message}, files={'photo': f})
            else:
                url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
                requests.post(url, data={'chat_id': TG_CHAT_ID, 'text': message})
            self.log("✅ TG 推送已发送")
        except Exception as e:
            self.log(f"❌ TG 推送失败: {e}")

    def is_cf_passed(self, sb) -> bool:
        """严格检查页面上是否真的生成了有效 Token"""
        try:
            # 获取所有 CF response 框，只要有一个有值就算通过
            elements = sb.find_elements('input[name="cf-turnstile-response"]')
            for el in elements:
                val = el.get_attribute("value")
                if val and len(val) > 20:
                    return True
        except: pass
        return False

    def run(self):
        self.log("=" * 40)
        self.log("🚀 FalixNodes - 终极死磕链接版 (反广告遮挡+严格打勾)喵")
        self.log("=" * 40)
        
        with SB(
            uc=True,
            test=True, 
            headed=True,
            headless=False,
            xvfb=False,
            chromium_arg="--no-sandbox,--disable-dev-shm-usage,--disable-gpu,--window-position=0,0,--start-maximized",
            proxy=PROXY_URL if PROXY_URL else None
        ) as sb:
            try:
                self.log("✅ 浏览器已启动！")
                
                # 1. IP 检测
                self.log("🌍 正在检测出口 IP...")
                try:
                    sb.open("https://api.ipify.org?format=json")
                    ip_val = json.loads(re.search(r'\{.*\}', sb.get_text("body")).group(0)).get('ip', 'Unknown')
                    parts = ip_val.split('.')
                    self.log(f"✅ 当前出口 IP: {parts[0]}.{parts[1]}.***.{parts[-1]}")
                except:
                    self.log("⚠️ IP 检测跳过...")
                
                # 2. 强制访问配置的链接
                self.log(f"🔗 强制访问唯一目标链接: {TAGET}")
                sb.uc_open_with_reconnect(TAGET, reconnect_time=25)
                time.sleep(6)
                
                # 🚨 核心风控拦截检测 🚨
                current_url = sb.get_current_url()
                if "login" in current_url:
                    self.log("❌ 糟糕！FalixNodes 把我们强制踢到登录页了！")
                    login_screenshot = f"{self.screenshot_dir}/login_redirect.png"
                    sb.save_screenshot(login_screenshot)
                    self.send_telegram_notify(
                        f"🚨 FalixNodes 保活程序\n🖥️ 编号: {NUM}\n❌ 续费失败：当前代理 IP 被官方风控，强制要求登录！建议更换 Github Action 节点或代理 IP 喵！", 
                        login_screenshot
                    )
                    return # 立刻停止，绝不执行登录逻辑

                # 3. 死磕 Cloudflare 验证码
                self.log("⏳ 正在死磕 Cloudflare 验证码喵...")
                for attempt in range(15): # 增加等待轮次，最长等45秒
                    if self.is_cf_passed(sb):
                        self.log("✅ 确认无误：CF 已经真实绿勾通过啦！")
                        break
                    
                    # 尝试点击
                    try:
                        sb.slow_click(f"body", force=True) # 晃晃鼠标
                        sb.uc_gui_click_captcha()
                    except: pass
                    
                    time.sleep(3)
                
                if not self.is_cf_passed(sb):
                    self.log("❌ CF 验证码一直过不去（可能没加载出来或被盾了）喵！")
                    fail_screenshot = f"{self.screenshot_dir}/cf_fail.png"
                    sb.save_screenshot(fail_screenshot)
                    self.send_telegram_notify(f"🚨 FalixNodes 保活程序\n🖥️ 编号: {NUM}\n❌ 续费失败：Cloudflare 打勾超时！", fail_screenshot)
                    return

                # 4. 获取当前时间
                if sb.is_element_present("#timer-page-countdown"):
                    before = sb.get_text("#timer-page-countdown") 
                    self.log(f"🕒 当前剩余时间: {before}")
                else:
                    self.log("⚠️ 找不到时间标签喵？")
                    before = "未知"

                # 5. 纯净 JS 点击加时按钮 (无视任何广告遮挡)
                self.log("🖱️ 准备点击添加时间 (Addtime)...")
                try:
                    # 使用 execute_script 强制点击，就算上面有一万个广告也能点到！
                    sb.execute_script("""
                        var btn = document.querySelector("#timer-page-btn");
                        if(btn) { btn.click(); }
                    """)
                    self.log("✅ 成功穿透广告，执行加时点击喵！")
                except Exception as e:
                    self.log(f"⚠️ 点击添加时间失败: {e}")
                
                # 6. 等待服务端处理加时请求
                self.log("⏳ 正在等待服务器后台加上时间...")
                time.sleep(12) 

                # 7. 再次刷新目标链接获取最终结果
                self.log("🔗 再次刷新页面核对最新时间...")
                sb.uc_open_with_reconnect(TAGET, reconnect_time=25)
                time.sleep(6)
                after = sb.get_text("#timer-page-countdown") if sb.is_element_present("#timer-page-countdown") else "未知"

                self.log("✅ 全部流程执行完毕")
                finish_screenshot = f"{self.screenshot_dir}/finish.png"
                sb.save_screenshot(finish_screenshot)
                self.send_telegram_notify(f"🎉FalixNodes 保活程序\n🖥️编号: {NUM}\n🕒保活前剩余时间: {before}\n🚀保活后剩余时间: {after}", finish_screenshot)
            
            except Exception as e:
                self.log(f"❌ 运行异常: {e}")
                sb.save_screenshot(f"{self.screenshot_dir}/error.png")

if __name__ == "__main__":
    FalixNodesRenewal().run()
