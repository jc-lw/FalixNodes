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

# ========== 完全复刻 oyz8 的 CF 打勾逻辑 ==========
def _turnstile_token_ready(sb) -> bool:
    try:
        token_ok = sb.execute_script("""
            var inp = document.querySelector("input[name='cf-turnstile-response']");
            return inp && inp.value && inp.value.length > 20;
        """)
        if token_ok:
            return True
    except Exception: pass

    try:
        success_visible = sb.execute_script("""
            var s = document.getElementById('success');
            if (!s) return false;
            var style = window.getComputedStyle(s);
            return style.display !== 'none' && style.visibility !== 'hidden';
        """)
        if success_visible:
            return True
    except Exception: pass

    return False


def _try_click_turnstile(sb) -> bool:
    """尝试多种方式点击 Turnstile (oyz8 原版多重攻击)"""
    try:
        sb.uc_gui_click_captcha()
        print("[INFO] Turnstile: uc_gui_click_captcha 触发喵")
        return True
    except Exception: pass

    try:
        sb.switch_to_frame("iframe[src*='challenges.cloudflare']")
        sb.click("input[type='checkbox'], .cb-lb", timeout=3)
        sb.switch_to_default_content()
        print("[INFO] Turnstile: iframe 内点击成功喵")
        return True
    except Exception:
        try:
            sb.switch_to_default_content()
        except Exception: pass

    try:
        sb.execute_script("""
            var ts = document.querySelector('.cf-turnstile');
            if (ts) ts.click();
        """)
        print("[INFO] Turnstile: JS 点击 .cf-turnstile")
        return True
    except Exception: pass

    return False


def wait_turnstile(sb, timeout: int = 60) -> bool:
    """等待打勾 (oyz8 原版逻辑)"""
    try:
        has = sb.execute_script("""
            return !!(
                document.querySelector('.cf-turnstile') ||
                document.querySelector('iframe[src*="challenges.cloudflare"]') ||
                document.querySelector('input[name="cf-turnstile-response"]')
            );
        """)
    except Exception:
        has = False

    if not has:
        print("[INFO] 无 Turnstile 组件，跳过喵")
        return True

    # 滚动到验证区 (防止被广告遮挡点不到)
    try:
        sb.execute_script("""
            var ts = document.querySelector('.cf-turnstile');
            if (ts) ts.scrollIntoView({block:'center'});
        """)
    except Exception: pass

    start = time.time()
    last_click = 0

    while time.time() - start < timeout:
        if _turnstile_token_ready(sb):
            print("[INFO] ✅ Turnstile 验证完成喵")
            time.sleep(0.5)
            return True

        now = time.time()
        # 每隔 3 秒尝试点击一次
        if now - last_click >= 3:
            _try_click_turnstile(sb)
            last_click = now

        time.sleep(1)

    if _turnstile_token_ready(sb):
        print("[INFO] ✅ Turnstile 超时后仍成功喵")
        return True

    print("[WARN] ⚠️ Turnstile 等待超时，验证未完成喵")
    return False
# ==================================================


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
        self.log("[🚀] FalixNodes - kof96zip (F5刷新 + oyz8原味CF)喵")
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
                
                # 1. IP 检测
                self.log("[🌍] 正在检测出口 IP...")
                try:
                    sb.open("https://api.ipify.org?format=json")
                    ip_val = json.loads(re.search(r'\{.*\}', sb.get_text("body")).group(0)).get('ip', 'Unknown')
                    parts = ip_val.split('.')
                    self.log(f"[✅] 当前出口 IP: {parts[0]}.{parts[1]}.***.{parts[-1]}")
                except:
                    self.log("[⚠️] IP 检测跳过...")
                
                # 2. 访问目标链接
                self.log(f"[🔗] 强制访问目标链接: {TAGET}")
                sb.uc_open_with_reconnect(TAGET, reconnect_time=25)
                time.sleep(6)
                
                # 拦截重定向
                if "login" in sb.get_current_url():
                    login_screenshot = f"{self.screenshot_dir}/login_redirect.png"
                    sb.save_screenshot(login_screenshot)
                    self.send_telegram_notify(f"🚨 FalixNodes 保活程序\n🖥️ 编号: {NUM}\n❌ 被官方重定向到登录页了，代理IP可能被风控喵！", login_screenshot)
                    return

                # 3. 循环 F5 刷新破解验证码 (最多 3 次)
                cf_passed = False
                for attempt in range(1, 4):
                    self.log(f"\n[⏳] 第 {attempt} 次尝试破解 Cloudflare 验证码喵...")
                    
                    if wait_turnstile(sb, timeout=60):
                        cf_passed = True
                        break
                    
                    if attempt < 3:
                        self.log(f"[🔄] 验证码过不去，准备按 F5 刷新页面重试喵！")
                        sb.refresh()
                        time.sleep(8) # 等待刷新完成
                
                # 3次全败
                if not cf_passed:
                    self.log("[❌] 连续 3 次打勾失败，投降了喵...")
                    fail_screenshot = f"{self.screenshot_dir}/cf_fail.png"
                    sb.save_screenshot(fail_screenshot)
                    self.send_telegram_notify(f"🚨 FalixNodes 保活程序\n🖥️ 编号: {NUM}\n❌ 续费失败：Cloudflare 连续 3 次打勾超时！", fail_screenshot)
                    return

                # 4. 获取当前时间
                before = "未知"
                if sb.is_element_present("#timer-page-countdown"):
                    before = sb.get_text("#timer-page-countdown") 
                    self.log(f"[🕒] 当前剩余时间: {before}")

                # 5. 纯净 JS 点击加时按钮 (无视所有广告遮挡)
                self.log("[🖱️] 准备点击添加时间 (Addtime)...")
                try:
                    sb.execute_script("""
                        var btn = document.querySelector("#timer-page-btn");
                        if(btn) { btn.click(); }
                    """)
                    self.log("[✅] 成功执行加时点击喵！")
                except Exception as e:
                    self.log(f"[⚠️] 点击添加时间失败: {e}")
                
                # 6. 等待服务端处理加时请求
                self.log("[⏳] 正在等待服务器后台加上时间...")
                time.sleep(12) 

                # 7. 再次刷新目标链接获取最终结果
                self.log("[🔗] 再次刷新页面核对最新时间...")
                sb.uc_open_with_reconnect(TAGET, reconnect_time=25)
                time.sleep(6)
                after = sb.get_text("#timer-page-countdown") if sb.is_element_present("#timer-page-countdown") else "未知"

                self.log("[✅] 全部流程执行完毕")
                finish_screenshot = f"{self.screenshot_dir}/finish.png"
                sb.save_screenshot(finish_screenshot)
                self.send_telegram_notify(f"🎉FalixNodes 保活程序\n🖥️编号: {NUM}\n🕒保活前剩余时间: {before}\n🚀保活后剩余时间: {after}", finish_screenshot)
            
            except Exception as e:
                self.log(f"[❌] 运行异常: {e}")
                sb.save_screenshot(f"{self.screenshot_dir}/error.png")

if __name__ == "__main__":
    FalixNodesRenewal().run()
