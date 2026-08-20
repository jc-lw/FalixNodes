import time
import os
import json
import re
import random
import requests

# 智能环境配置：仅在未设置时才应用默认值
if "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":1"
    
if "XAUTHORITY" not in os.environ:
    if os.path.exists("/home/headless/.Xauthority"):
        os.environ["XAUTHORITY"] = "/home/headless/.Xauthority"

print(f"[DEBUG] Env DISPLAY: {os.environ.get('DISPLAY')}")
print(f"[DEBUG] Env XAUTHORITY: {os.environ.get('XAUTHORITY')}")

from seleniumbase import SB

# ================= 配置区域 =================
PROXY_URL = os.getenv("PROXY", "")  # 代理
NUM = os.getenv("NUM")  # 服务器编号
TG_TOKEN = os.getenv("TG_TOKEN")  # tg通知token
TG_CHAT_ID = os.getenv("TG_CHAT_ID")  # tg通知chat_id

# 目标 URL
TAGET = f"https://client.falixnodes.net/timer?id={NUM}"
# ===========================================

# --- 喵酱的纯净版 Turnstile 验证模块 ---
def _turnstile_token_ready(sb) -> bool:
    try:
        token_ok = sb.execute_script("""
            var inp = document.querySelector("input[name='cf-turnstile-response']");
            return inp && inp.value && inp.value.length > 20;
        """)
        if token_ok: return True
    except: pass
    try:
        success_visible = sb.execute_script("""
            var s = document.getElementById('success');
            if (!s) return false;
            var style = window.getComputedStyle(s);
            return style.display !== 'none' && style.visibility !== 'hidden';
        """)
        if success_visible: return True
    except: pass
    return False

def _try_click_turnstile(sb) -> bool:
    try:
        sb.uc_gui_click_captcha()
        return True
    except: pass
    try:
        sb.switch_to_frame("iframe[src*='challenges.cloudflare']")
        sb.click("input[type='checkbox'], .cb-lb", timeout=3)
        sb.switch_to_default_content()
        return True
    except:
        try: sb.switch_to_default_content()
        except: pass
    try:
        sb.execute_script("var ts = document.querySelector('.cf-turnstile'); if (ts) ts.click();")
        return True
    except: pass
    return False

def wait_turnstile(sb, timeout: int = 90) -> bool:
    try:
        has_ts = sb.execute_script("""
            return !!(document.querySelector('.cf-turnstile') ||
                      document.querySelector('iframe[src*="challenges.cloudflare"]') ||
                      document.querySelector('input[name="cf-turnstile-response"]'));
        """)
    except:
        has_ts = False

    if not has_ts:
        print("[INFO] 无 Turnstile 组件，直接跳过喵")
        return True

    try:
        sb.execute_script("var ts = document.querySelector('.cf-turnstile'); if (ts) ts.scrollIntoView({block:'center'});")
    except: pass

    start = time.time()
    last_click = 0

    while time.time() - start < timeout:
        if _turnstile_token_ready(sb):
            time.sleep(0.5)
            return True
        now = time.time()
        if now - last_click >= 3:
            _try_click_turnstile(sb)
            last_click = now
        time.sleep(1)

    if _turnstile_token_ready(sb): return True
    return False
# ---------------------------------------

class FalixNodesRenewal:
    def __init__(self):
        self.BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        self.screenshot_dir = os.path.join(self.BASE_DIR, "artifacts")
        if not os.path.exists(self.screenshot_dir):
            os.makedirs(self.screenshot_dir)

    def log(self, msg):
        timestamp = time.strftime('%H:%M:%S')
        print(f"[{timestamp}] [INFO] {msg}", flush=True)

    def human_wait(self, min_s=6, max_s=10):
        time.sleep(random.uniform(min_s, max_s))

    def move_mouse_human(self, sb):
        try:
            for _ in range(3):
                sb.slow_click(f"body", force=True)
                time.sleep(random.uniform(0.5, 1.2))
        except: pass

    def send_telegram_notify(self, message, photo_path=None):
        if not TG_TOKEN or not TG_CHAT_ID:
            self.log("⚠️ 未配置 TG_TOKEN 或 TG_CHAT_ID，跳过推送。")
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
        self.log("🚀 FalixNodes - 纯净保活流程 (No Ads)喵")
        self.log("=" * 40)
        self.log("🎯 正在启动 Chrome 浏览器...")
        
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

                # 2. 访问目标页面
                self.log("🔗 访问目标页面...")
                sb.uc_open_with_reconnect(TAGET, reconnect_time=25)
                time.sleep(5)

                if sb.is_element_present("#timer-page-countdown"):
                    before = sb.get_text("#timer-page-countdown") 
                else:
                    check_screenshot = f"{self.screenshot_dir}/check.png"
                    sb.save_screenshot(check_screenshot)
                    self.send_telegram_notify(f"🎉FalixNodes 保活程序\n🖥️编号: {NUM}\n❌未检测到服务器运行剩余时间,服务器可能被关闭或正在重新启动", check_screenshot)
                    return

                # 3. 验证Cloudflare (融合 oyz8 纯净逻辑)
                self.log("⏳ 开始 Turnstile 验证喵...")
                self.move_mouse_human(sb)
                
                if wait_turnstile(sb, timeout=90):
                    self.log("✅ Cloudflare Turnstile 验证成功！")
                else:
                    self.log("❌ Cloudflare 验证失败")
                    cf_screenshot = f"{self.screenshot_dir}/cf_failed.png"
                    sb.save_screenshot(cf_screenshot)
                    self.send_telegram_notify("❌ CF验证失败", cf_screenshot)
                    return
                
                # 4. 纯净点击添加时间 (抛弃所有看广告逻辑)
                self.log("🖱️ 开始处理加时按钮...")
                try:
                    sb.wait_for_element_visible("#timer-page-btn", timeout=10)
                    sb.click("#timer-page-btn")
                    self.log("✅ 成功点击添加时间 (Addtime) 完毕喵！")
                except Exception as e:
                    self.log(f"⚠️ 点击添加时间失败: {e}")
                
                time.sleep(5) # 给后端一点时间处理加时请求

                # 5. 再次访问目标页面核对新时间
                self.log("🔗 再次访问目标页面核对时间...")
                sb.uc_open_with_reconnect(TAGET, reconnect_time=25)
                time.sleep(5)
                after = sb.get_text("#timer-page-countdown") if sb.is_element_present("#timer-page-countdown") else "未知"

                self.log("✅ 全部流程执行完毕")
                finish_screenshot = f"{self.screenshot_dir}/finish.png"
                sb.save_screenshot(finish_screenshot)
                self.send_telegram_notify(f"🎉FalixNodes 保活程序\n🖥️编号: {NUM}\n🕒保活前剩余运行时间: {before}\n🚀保活后剩余运行时间: {after}", finish_screenshot)
            
            except Exception as e:
                self.log(f"❌ 运行异常: {e}")
                import traceback
                traceback.print_exc()
                sb.save_screenshot(f"{self.screenshot_dir}/error.png")

if __name__ == "__main__":
    FalixNodesRenewal().run()
