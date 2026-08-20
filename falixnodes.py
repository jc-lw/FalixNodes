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
TAGET = f"https://client.falixnodes.net/timer?id={NUM}"
# ===========================================

# --- 喵酱的强化版 Turnstile 验证模块 ---
def _turnstile_token_ready(sb) -> bool:
    """检查是否已经获取到有效的 CF Token"""
    try:
        token_ok = sb.execute_script("""
            var inp = document.querySelector("input[name='cf-turnstile-response']");
            return inp && inp.value && inp.value.length > 20;
        """)
        if token_ok: return True
    except: pass
    return False

def wait_and_click_turnstile(sb, timeout: int = 60) -> bool:
    """死磕 Turnstile，直到打上勾"""
    print("[INFO] 正在等待 Turnstile 验证码加载喵...")
    # 强制等 5 秒，让那个慢吞吞的 iframe 彻底加载出来
    time.sleep(5) 
    
    start = time.time()
    last_click = 0

    while time.time() - start < timeout:
        if _turnstile_token_ready(sb):
            return True
            
        now = time.time()
        # 每隔 6 秒尝试一次综合点击法
        if now - last_click >= 6:
            print("[INFO] 尝试戳一下验证码...")
            # 策略 1: SeleniumBase 官方自带的强力点击
            try: sb.uc_gui_click_captcha()
            except: pass
            
            # 策略 2: 切换到 iframe 里硬点
            try:
                sb.switch_to_frame("iframe[src*='challenges.cloudflare']")
                sb.click("input[type='checkbox'], .cb-lb", timeout=2)
                sb.switch_to_default_content()
            except:
                try: sb.switch_to_default_content()
                except: pass
                
            # 策略 3: JS 强制触发
            try: sb.execute_script("var ts = document.querySelector('.cf-turnstile'); if (ts) ts.click();")
            except: pass
            
            last_click = now
            
        time.sleep(1)

    # 循环结束后最后查一次
    return _turnstile_token_ready(sb)
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
        self.log("🚀 FalixNodes - 纯净保活流程 (修复抢跑BUG版)喵")
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
                
                # 1. 访问目标页面
                self.log("🔗 访问目标页面...")
                sb.uc_open_with_reconnect(TAGET, reconnect_time=25)
                time.sleep(5)

                if sb.is_element_present("#timer-page-countdown"):
                    before = sb.get_text("#timer-page-countdown") 
                else:
                    check_screenshot = f"{self.screenshot_dir}/check.png"
                    sb.save_screenshot(check_screenshot)
                    self.send_telegram_notify(f"🎉FalixNodes 保活程序\n🖥️编号: {NUM}\n❌未检测到服务器剩余时间，服务器可能关闭", check_screenshot)
                    return

                # 2. 死磕 Turnstile 验证
                self.log("⏳ 开始死磕 Turnstile 验证喵...")
                self.move_mouse_human(sb)
                
                if wait_and_click_turnstile(sb, timeout=60):
                    self.log("✅ Cloudflare 验证打勾成功！获取到了有效 Token喵！")
                else:
                    self.log("❌ 验证码一直点不上，超时啦！")
                    cf_screenshot = f"{self.screenshot_dir}/cf_failed.png"
                    sb.save_screenshot(cf_screenshot)
                    self.send_telegram_notify("❌ CF验证失败，打勾超时", cf_screenshot)
                    return
                
                # 3. 纯净点击添加时间
                self.log("🖱️ 验证通过，准备点击添加时间 (Addtime)...")
                time.sleep(2) # 留一点反应时间
                try:
                    sb.wait_for_element_visible("#timer-page-btn", timeout=10)
                    sb.click("#timer-page-btn")
                    self.log("✅ 成功点击添加时间完毕喵！")
                except Exception as e:
                    self.log(f"⚠️ 点击添加时间失败: {e}")
                
                # 4. 给后端充分的时间处理请求，防止没续上
                self.log("⏳ 正在等待服务器后台加上时间...")
                time.sleep(10) 

                # 5. 再次访问目标页面核对新时间
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
                import traceback
                traceback.print_exc()
                sb.save_screenshot(f"{self.screenshot_dir}/error.png")

if __name__ == "__main__":
    FalixNodesRenewal().run()
