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

# ========== 核心 CF 打勾逻辑 ==========
def _turnstile_token_ready(sb) -> bool:
    try:
        token_ok = sb.execute_script("""
            var inp = document.querySelector("input[name='cf-turnstile-response']");
            return inp && inp.value && inp.value.length > 20;
        """)
        if token_ok: return True
    except Exception: pass

    try:
        success_visible = sb.execute_script("""
            var s = document.getElementById('success');
            if (!s) return false;
            var style = window.getComputedStyle(s);
            return style.display !== 'none' && style.visibility !== 'hidden';
        """)
        if success_visible: return True
    except Exception: pass
    return False

def _try_click_turnstile(sb) -> bool:
    try: sb.uc_gui_click_captcha()
    except Exception: pass

    try:
        if sb.is_element_present("iframe[src*='challenges.cloudflare']"):
            sb.switch_to_frame("iframe[src*='challenges.cloudflare']")
            sb.click("input[type='checkbox'], .cb-lb, .mark", timeout=2)
            sb.switch_to_default_content()
            return True
    except Exception:
        try: sb.switch_to_default_content()
        except Exception: pass

    try:
        sb.execute_script("""
            var ts = document.querySelector('.cf-turnstile');
            if (ts) ts.click();
        """)
    except Exception: pass

    return False

def wait_turnstile(sb, timeout: int = 60) -> bool:
    print("[INFO] 正在耐心等待 Cloudflare 验证码完全加载喵...")
    time.sleep(10)
    
    try:
        sb.execute_script("""
            var ts = document.querySelector('.cf-turnstile') || document.querySelector('iframe[src*="challenges.cloudflare"]');
            if (ts) ts.scrollIntoView({block:'center'});
        """)
    except Exception: pass

    start = time.time()
    last_click = 0

    while time.time() - start < timeout:
        if _turnstile_token_ready(sb):
            print("[INFO] ✅ Turnstile 绿勾验证完成喵！")
            time.sleep(3) 
            return True

        now = time.time()
        if now - last_click >= 4:
            print("[INFO] 尝试戳一下中间的框框...")
            _try_click_turnstile(sb)
            last_click = now

        time.sleep(1)

    return _turnstile_token_ready(sb)

# ========== 动态时间捕手 ==========
def get_time_safely(sb, timeout: int = 15) -> str:
    start = time.time()
    while time.time() - start < timeout:
        try:
            raw_text = sb.execute_script("""
                var el = document.querySelector('#timer-page-countdown');
                return el ? (el.innerText || el.textContent).trim() : '';
            """)
            if raw_text and any(char.isdigit() for char in raw_text):
                return raw_text
        except Exception: pass
        time.sleep(1)
    return "未知"
# ==========================================

class FalixNodesRenewal:
    def __init__(self):
        self.BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        self.screenshot_dir = os.path.join(self.BASE_DIR, "artifacts")
        if not os.path.exists(self.screenshot_dir):
            os.makedirs(self.screenshot_dir)

    def log(self, msg):
        timestamp = time.strftime('%H:%M:%S')
        print(f"[{timestamp}] {msg}", flush=True)

    def send_telegram_notify(self, message, photo_path=None):
        if not TG_TOKEN or not TG_CHAT_ID:
            self.log("[⚠️] 未配置 TG_TOKEN，跳过推送喵。")
            return
        try:
            if photo_path and os.path.exists(photo_path):
                url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
                with open(photo_path, 'rb') as f:
                    requests.post(url, data={'chat_id': TG_CHAT_ID, 'caption': message}, files={'photo': f})
            else:
                url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
                requests.post(url, data={'chat_id': TG_CHAT_ID, 'text': message})
            self.log("[✅] TG 推送已发送")
        except Exception as e:
            self.log(f"[❌] TG 推送失败: {e}")

    def run(self):
        self.log("=" * 40)
        self.log("[🚀] FalixNodes - 防假死版 (死盯 Loading)喵")
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
                self.log("[✅] 浏览器已启动！")
                
                self.log("[🌍] 正在检测出口 IP...")
                try:
                    sb.open("https://api.ipify.org?format=json")
                    ip_val = json.loads(re.search(r'\{.*\}', sb.get_text("body")).group(0)).get('ip', 'Unknown')
                    parts = ip_val.split('.')
                    self.log(f"[✅] 当前出口 IP: {parts[0]}.{parts[1]}.***.{parts[-1]}")
                except:
                    self.log("[⚠️] IP 检测跳过...")
                
                self.log(f"[🔗] 强制访问目标链接: {TAGET}")
                sb.uc_open_with_reconnect(TAGET, reconnect_time=25)
                time.sleep(6)
                
                # 1. 登录重定向拦截
                if "login" in sb.get_current_url():
                    login_screenshot = f"{self.screenshot_dir}/login_redirect.png"
                    sb.save_screenshot(login_screenshot)
                    self.send_telegram_notify(f"🚨 FalixNodes 保活程序\n🖥️ 编号: {NUM}\n❌ 被重定向到登录页，IP被风控喵！", login_screenshot)
                    return

                # 2. 停机检测前置防线：防 Loading 假死
                self.log("[🔍] 正在观察服务器运行状态...")
                
                self.log("[⏳] 检查是否卡在 Loading timer 状态...")
                for _ in range(15): # 给它最多 30 秒去拉屎
                    try:
                        body_text = sb.get_text("body").lower()
                        if "loading timer" not in body_text:
                            break # 拉完了，跳出循环
                    except: pass
                    time.sleep(2)

                is_alive = False
                try:
                    sb.wait_for_element_visible("#timer-page-countdown", timeout=10)
                    is_alive = True
                except: pass

                if not is_alive:
                    try:
                        body_text = sb.get_text("body").lower()
                        # 必须是明确没有 Loading，且真的抓到了停机文字
                        if "loading timer" not in body_text and ("no active timer" in body_text or "back to dashboard" in body_text):
                            self.log("[❌] 确认服务器真的停机了喵！")
                            dead_screenshot = f"{self.screenshot_dir}/server_dead.png"
                            sb.save_screenshot(dead_screenshot)
                            self.send_telegram_notify(f"⚠️ FalixNodes 保活程序\n🖥️ 编号: {NUM}\n❌ 续费失败：服务器已停机 (No active timer)，请手动开机喵！", dead_screenshot)
                            return
                        else:
                            self.log("[⚠️] 没看到倒计时，但也没看到停机提示，强闯 CF 试试运气喵...")
                    except: pass
                else:
                    self.log("[✅] 确认看到倒计时啦！服务器存活喵！")

                # 3. CF 破解
                cf_passed = False
                for attempt in range(1, 4):
                    self.log(f"\n[⏳] 第 {attempt} 次尝试破解 Cloudflare 验证码喵...")
                    
                    if wait_turnstile(sb, timeout=60):
                        cf_passed = True
                        break
                    
                    if attempt < 3:
                        self.log(f"[🔄] 验证码过不去，准备按 F5 刷新页面重试喵！")
                        sb.refresh()
                        time.sleep(10)
                
                if not cf_passed:
                    self.log("[❌] 连续 3 次打勾失败，投降了喵...")
                    fail_screenshot = f"{self.screenshot_dir}/cf_fail.png"
                    sb.save_screenshot(fail_screenshot)
                    self.send_telegram_notify(f"🚨 FalixNodes 保活程序\n🖥️ 编号: {NUM}\n❌ 续费失败：Cloudflare 连续 3 次打勾超时！", fail_screenshot)
                    return

                # 4. 获取加时前的时间
                self.log("[🕒] 正在捕获当前剩余时间...")
                before = get_time_safely(sb, timeout=15)
                self.log(f"[🕒] 当前剩余时间: {before}")

                self.log("[⏳] 正在让网页前端消化验证码 Token，强行冷静 3 秒...")
                time.sleep(3)

                # 5. 点击加时按钮
                self.log("[🖱️] 准备点击添加时间 (Addtime)...")
                try:
                    sb.execute_script("""
                        var btn = document.querySelector("#timer-page-btn");
                        if(btn) { 
                            btn.removeAttribute("disabled"); 
                            btn.click(); 
                        }
                    """)
                    self.log("[✅] 成功执行加时点击喵！")
                except Exception as e:
                    self.log(f"[⚠️] 点击添加时间失败: {e}")
                
                # 6. 等待后台处理
                self.log("[⏳] 正在乖乖等待 10 秒钟，让服务器消化加时请求...")
                time.sleep(10) 

                # 7. 刷新获取最新时间
                self.log("[🔗] 时间到！正在刷新页面以获取最新时间...")
                sb.refresh()
                time.sleep(5)
                
                self.log("[🕒] 正在捕获加时后的最新时间...")
                after = get_time_safely(sb, timeout=15)
                self.log(f"[🕒] 最新剩余时间: {after}")

                self.log("[✅] 全部流程执行完毕")
                finish_screenshot = f"{self.screenshot_dir}/finish.png"
                sb.save_screenshot(finish_screenshot)
                self.send_telegram_notify(f"🎉FalixNodes 保活程序\n🖥️编号: {NUM}\n🕒保活前剩余时间: {before}\n🚀保活后剩余时间: {after}", finish_screenshot)
            
            except Exception as e:
                self.log(f"[❌] 运行异常: {e}")
                sb.save_screenshot(f"{self.screenshot_dir}/error.png")

if __name__ == "__main__":
    FalixNodesRenewal().run()
