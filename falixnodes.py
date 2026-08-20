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

    def move_mouse_human(self, sb):
        """模拟人类鼠标晃动预热"""
        try:
            for _ in range(3):
                sb.slow_click(f"body", force=True)
                time.sleep(random.uniform(0.5, 1.2))
        except: pass

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

    def run(self):
        self.log("=" * 40)
        self.log("🚀 FalixNodes - kof96zip死磕链接版 (只过CF,无广告)喵")
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
                
                # 1. IP 检测 (保留 kof96zip 原有功能)
                self.log("🌍 正在检测出口 IP...")
                try:
                    sb.open("https://api.ipify.org?format=json")
                    ip_val = json.loads(re.search(r'\{.*\}', sb.get_text("body")).group(0)).get('ip', 'Unknown')
                    parts = ip_val.split('.')
                    self.log(f"✅ 当前出口 IP: {parts[0]}.{parts[1]}.***.{parts[-1]}")
                except:
                    self.log("⚠️ IP 检测跳过...")
                
                # 2. 强制访问配置的链接
                self.log(f"🔗 强制访问唯一目标链接...")
                sb.uc_open_with_reconnect(TAGET, reconnect_time=25)
                time.sleep(6) # 多等一会，防止网页响应慢

                # 3. 优先寻找并死磕 Cloudflare (完美融入 oyz8 逻辑)
                self.log("⏳ 正在死磕 Cloudflare 验证码喵...")
                for attempt in range(12): # 最多循环等待约 40 秒
                    token_ok = False
                    try:
                        token_ok = sb.execute_script("""
                            var inp = document.querySelector("input[name='cf-turnstile-response']");
                            return inp && inp.value && inp.value.length > 20;
                        """)
                    except: pass
                    
                    if token_ok:
                        self.log("✅ CF 已经绿勾通过啦！")
                        break
                        
                    # 多重点击策略
                    self.move_mouse_human(sb)
                    try: sb.uc_gui_click_captcha()
                    except: pass
                    
                    try:
                        sb.switch_to_frame("iframe[src*='challenges.cloudflare']")
                        sb.click("input[type='checkbox'], .cb-lb", timeout=2)
                        sb.switch_to_default_content()
                    except:
                        try: sb.switch_to_default_content()
                        except: pass
                    
                    time.sleep(3)

                # 4. CF 过完后，再检查时间元素是否在页面上
                if sb.is_element_present("#timer-page-countdown"):
                    before = sb.get_text("#timer-page-countdown") 
                    self.log(f"🕒 当前剩余时间: {before}")
                else:
                    check_screenshot = f"{self.screenshot_dir}/check.png"
                    sb.save_screenshot(check_screenshot)
                    self.send_telegram_notify(f"🎉FalixNodes 保活程序\n🖥️编号: {NUM}\n❌找不到时间！如果截图是登录页，说明你的IP被官方强制重定向了喵！", check_screenshot)
                    return

                # 5. 纯净点击加时按钮
                self.log("🖱️ 准备点击添加时间 (Addtime)...")
                try:
                    sb.wait_for_element_visible("#timer-page-btn", timeout=10)
                    sb.click("#timer-page-btn")
                    self.log("✅ 成功点击添加时间完毕喵！")
                except Exception as e:
                    self.log(f"⚠️ 点击添加时间失败: {e}")
                
                # 6. 等待服务端处理加时请求
                self.log("⏳ 正在等待服务器后台加上时间...")
                time.sleep(10) 

                # 7. 再次刷新目标链接获取最终结果
                self.log("🔗 再次刷新页面核对最新时间...")
                sb.uc_open_with_reconnect(TAGET, reconnect_time=25)
                time.sleep(5)
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
