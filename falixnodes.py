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

# ========== 时间字符串解析工具 ==========
def parse_time_to_seconds(time_str: str) -> int:
    """将获取到的文本时间转换为秒数，便于进行严格的大小比对"""
    if not time_str or time_str == "未知":
        return -1
    total_seconds = 0
    d_match = re.search(r'(\d+)\s*days?', time_str, re.IGNORECASE)
    h_match = re.search(r'(\d+)\s*hours?', time_str, re.IGNORECASE)
    m_match = re.search(r'(\d+)\s*minutes?', time_str, re.IGNORECASE)
    s_match = re.search(r'(\d+)\s*seconds?', time_str, re.IGNORECASE)
    
    if d_match: total_seconds += int(d_match.group(1)) * 86400
    if h_match: total_seconds += int(h_match.group(1)) * 3600
    if m_match: total_seconds += int(m_match.group(1)) * 60
    if s_match: total_seconds += int(s_match.group(1))
    
    return total_seconds

# ========== 核心 CF 打勾逻辑 ==========
def _turnstile_token_ready(sb) -> bool:
    try:
        # 退回最原始稳定的多行提取写法
        token_ok = sb.execute_script("""
            var inp = document.querySelector("input[name='cf-turnstile-response']");
            return inp && inp.value && inp.value.length > 20;
        """)
        if token_ok: return True
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
            print("[INFO] ✅ Turnstile 真正获取到有效 Token 喵！")
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
            # 🚨 还原回您 16:44 成功抓取时间的完美多行代码 🚨
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
        self.log("[🚀] FalixNodes - 大道至简原汁原味版喵")
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
                
                max_loops = 3
                for main_loop in range(1, max_loops + 1):
                    self.log(f"\n[🌟] 开始第 {main_loop} 轮完整保活流程喵...")
                    
                    self.log(f"[🔗] 强制访问目标链接: {TAGET}")
                    sb.uc_open_with_reconnect(TAGET, reconnect_time=25)
                    time.sleep(8)
                    
                    url = sb.get_current_url()
                    if "login" in url or "google_vignette" in url:
                        self.log(f"[⚠️] 警报！一进来网址不对 ({url})！")
                        if main_loop == max_loops:
                            self.send_telegram_notify(f"🚨 FalixNodes 保活程序\n🖥️ 编号: {NUM}\n❌ 连续重定向，IP被风控喵！")
                            return
                        else:
                            continue 

                    self.log("[🔍] 正在观察服务器运行状态...")
                    is_alive = False
                    try:
                        sb.wait_for_element_visible("#timer-page-countdown", timeout=10)
                        is_alive = True
                    except: pass

                    if not is_alive:
                        body_text = sb.get_text("body").lower()
                        if "no active timer" in body_text or "back to dashboard" in body_text or "未找到活动" in body_text:
                            self.log("[❌] 确认服务器真的停机了喵！")
                            self.send_telegram_notify(f"⚠️ FalixNodes 保活程序\n🖥️ 编号: {NUM}\n❌ 续费失败：服务器已停机 (No active timer)，请手动开机喵！")
                            return
                        else:
                            self.log("[⚠️] 没看到倒计时和停机提示，尝试推进...")
                    else:
                        self.log("[✅] 确认看到倒计时啦！")

                    self.log("[🕒] 正在捕获加时前基准时间...")
                    before = get_time_safely(sb, timeout=15)
                    
                    if before == "未知":
                        self.log("[⚠️] 警报！初始时间未能加载出来，尝试原位 F5 抢救喵...")
                        sb.refresh()
                        time.sleep(10)
                        before = get_time_safely(sb, timeout=15)
                        if before == "未知":
                            self.log("[❌] 抢救无效！连初始时间都读不到。放弃本轮大循环！")
                            if main_loop == max_loops:
                                self.send_telegram_notify(f"🚨 FalixNodes 保活程序\n🖥️ 编号: {NUM}\n❌ 续费失败：页面加载严重超时，无法读取时间数据喵！")
                                return
                            continue

                    before_sec = parse_time_to_seconds(before)
                    self.log(f"[🕒] 当前剩余时间: {before} ({before_sec}秒)")

                    cf_passed = False
                    for attempt in range(1, 4):
                        self.log(f"\n[⏳] 第 {attempt} 次尝试破解 Cloudflare 验证码喵...")
                        if wait_turnstile(sb, timeout=60):
                            cf_passed = True
                            break
                        if attempt < 3:
                            self.log(f"[🔄] 验证码未过，刷新页面重试！")
                            sb.refresh()
                            time.sleep(10)
                    
                    if not cf_passed:
                        self.log("[❌] 打勾失败，放弃当前大循环...")
                        if main_loop == max_loops:
                            self.send_telegram_notify(f"🚨 FalixNodes 保活程序\n🖥️ 编号: {NUM}\n❌ 续费失败：Cloudflare 打勾超时！")
                            return
                        continue

                    self.log("[⏳] 正在等待网页前端自然解禁加时按钮 (最长 30 秒)...")
                    btn_ready = False
                    for _ in range(30):
                        try:
                            # 🚨 抛弃单行报错写法，拆成多行安全写法 🚨
                            is_disabled = sb.execute_script("""
                                var btn = document.querySelector('#timer-page-btn');
                                return btn ? btn.hasAttribute('disabled') : true;
                            """)
                            if not is_disabled:
                                btn_ready = True
                                break
                        except Exception: pass
                        time.sleep(1)

                    if not btn_ready:
                        self.log("[⚠️] 按钮未自然解禁，可能是时间充足触发冷却，或者 Token 未被后端接受。放弃暴力强点。")
                    else:
                        self.log("[🖱️] 准备使用原生点击触发 Addtime...")
                        try:
                            sb.click("#timer-page-btn", timeout=5)
                            self.log("[✅] 按钮点击完毕！")
                        except Exception:
                            sb.execute_script("document.querySelector('#timer-page-btn').click();")
                            self.log("[✅] 按钮点击完毕 (JS Fallback)！")

                    self.log("[⏳] 正在等待 10 秒钟，让服务器消化加时请求...")
                    time.sleep(10) 

                    self.log("[🔗] 时间到！重新加载获取后端最新时间...")
                    sb.uc_open_with_reconnect(TAGET, reconnect_time=25)
                    time.sleep(8)
                    
                    self.log("[🕒] 正在捕获加时后的最新时间...")
                    after = get_time_safely(sb, timeout=15)
                    after_sec = parse_time_to_seconds(after)
                    self.log(f"[🕒] 最新剩余时间: {after} ({after_sec}秒)")

                    if after_sec > before_sec and after_sec > 0:
                        self.log(f"[✅] 时间已确认增加 ({before_sec} -> {after_sec})，续费真正成功！")
                        finish_screenshot = f"{self.screenshot_dir}/finish.png"
                        sb.save_screenshot(finish_screenshot)
                        self.send_telegram_notify(f"🎉FalixNodes 保活程序\n🖥️编号: {NUM}\n🕒保活前: {before}\n🚀保活后: {after}", finish_screenshot)
                        break 
                    else:
                        self.log(f"[❌] 虚假成功预警：时间并未增加 ({before} -> {after})！")
                        if main_loop == max_loops:
                            fail_screenshot = f"{self.screenshot_dir}/fail.png"
                            sb.save_screenshot(fail_screenshot)
                            self.send_telegram_notify(f"❌续费失败\n🖥️编号: {NUM}\n⚠️ 未检测到服务器端时间增加，已停止误报成功。\n🕒保活前: {before}\n🚀保活后: {after}", fail_screenshot)
                        else:
                            self.log("[🔄] 准备进入下一轮大循环重试...")

            except Exception as e:
                self.log(f"[❌] 运行异常: {e}")
                sb.save_screenshot(f"{self.screenshot_dir}/error.png")

if __name__ == "__main__":
    FalixNodesRenewal().run()
