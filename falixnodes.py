import time
import os
import json
import re
import random
import requests

# 智能环境配置：仅在未设置时才应用默认值
# 这样兼容 GitHub Actions 的 xvfb-run (会自动设置 DISPLAY) 和 Docker 环境
if "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":1"
    
if "XAUTHORITY" not in os.environ:
    # 仅当路径存在时才设置，避免在 GitHub Runner (home/runner) 中报错
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
        """随机模拟人类等待时间"""
        time.sleep(random.uniform(min_s, max_s))

    def move_mouse_human(self, sb):
        """模拟人类鼠标晃动预热"""
        try:
            # 在页面不同位置“晃悠”一下鼠标，打破机器人直线模式
            for _ in range(3):
                x = random.randint(100, 800)
                y = random.randint(100, 600)
                sb.slow_click(f"body", force=True) # 借用 slow_click 的移动特性，或者直接用 move_to
                time.sleep(random.uniform(0.5, 1.2))
        except: pass

    def send_telegram_notify(self, message, photo_path=None):
        """发送 Telegram 通知 (带图片)"""
        if not TG_TOKEN or not TG_CHAT_ID:
            self.log("⚠️ 未配置 TG_TOKEN 或 TG_CHAT_ID，跳过推送。")
            return
        
        try:
            if photo_path and os.path.exists(photo_path):
                url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
                with open(photo_path, 'rb') as f:
                    # caption 参数用于发送带文字的图片
                    requests.post(url, data={'chat_id': TG_CHAT_ID, 'caption': message}, files={'photo': f})
            else:
                url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
                requests.post(url, data={'chat_id': TG_CHAT_ID, 'text': message})
            
            self.log("✅ TG 推送已发送")
        except Exception as e:
            self.log(f"❌ TG 推送失败: {e}")

    def run(self):
        self.log("=" * 40)
        self.log("🚀 FalixNodes - 保活流程")
        self.log("=" * 40)
        self.log("🎯 正在启动 Chrome 浏览器...")
        
        # 使用 headed=True 强制有头模式渲染到 VNC
        with SB(
            uc=True,            # 启用反检测模式
            test=True, 
            headed=True,        # 关键：强制有头模式
            headless=False,     # 明确禁用 headless
            xvfb=False,         # 禁用内部虚拟显示器，使用系统 DISPLAY
            chromium_arg="--no-sandbox,--disable-dev-shm-usage,--disable-gpu,--window-position=0,0,--start-maximized",
            proxy=PROXY_URL if PROXY_URL else None
        ) as sb:
            try:
                self.log("✅ 浏览器已启动！")
                
                # ... (省略中间步骤，保持原有逻辑不变) ...
                
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
                    before = sb.get_text("#timer-page-countdown") # Renew前剩余时间
                else:
                    check_screenshot = f"{self.screenshot_dir}/check.png"
                    sb.save_screenshot(check_screenshot)
                    self.send_telegram_notify("🎉FalixNodes 保活程序\n🖥️编号: {NUM}\n❌未检测到服务器运行剩余时间,服务器可能被关闭或正在重新启动", check_screenshot)
                    return

                # 3. 验证Cloudflare,目前要过cf需要家宽ip
                self.log("⏳ 开始Turnstile验证")
                token = None
                for i in range(2):
                    self.log(f"第 {i+1} 次尝试")
                    self.move_mouse_human(sb)
                    sb.uc_gui_click_captcha()
                    # 等待token
                    for _ in range(15):
                        time.sleep(10)
                        token = sb.get_attribute('input[name="cf-turnstile-response"]',"value")
                        if token:
                            break
                    if token:
                        self.log("✅ Cloudflare Turnstile验证成功")
                        print(f"Token length={len(token)}")
                        break
                    self.log("⚠️ click后没有token，尝试handle")
                    self.move_mouse_human(sb)
                    sb.uc_gui_handle_captcha()
                    time.sleep(10)
                    # handle后再次检查
                    token = sb.get_attribute('input[name="cf-turnstile-response"]',"value")
                    if token:
                        self.log("✅ handle后获取Token")
                        break
                if not token:
                    self.log("❌ Cloudflare验证失败")
                    cf_screenshot = f"{self.screenshot_dir}/cf_failed.png"
                    sb.save_screenshot(cf_screenshot)
                    self.send_telegram_notify("CF失败", cf_screenshot)
                    return
                self.log("🎉 CF验证完成")

                #taget_screenshot = f"{self.screenshot_dir}/taget.png"
                #sb.save_screenshot(taget_screenshot)
                #self.send_telegram_notify("✅访问保活页面并通过Cloudflare认证", taget_screenshot)
                
                # 4. 点击各种按钮
                self.log("🖱️ 开始处理点击各种按钮")

                self.log("🖱️ 点击添加时间/Addtime")
                sb.wait_for_element_visible("#timer-page-btn", timeout=10)
                sb.click("#timer-page-btn")
                time.sleep(1)
                self.log("✅ 点击添加时间/Addtime完毕")
                time.sleep(3)

                #addtime_screenshot = f"{self.screenshot_dir}/addtime.png"
                #sb.save_screenshot(addtime_screenshot)
                #self.send_telegram_notify("✅已点击addtime", addtime_screenshot)                

                self.log("🖱️ 点击观看广告/WatchAD")
                if sb.is_element_visible("#watchAdBtn"):
                    sb.click("#watchAdBtn")
                else:
                    self.log("✅ 无需观看广告/WatchAD")
                time.sleep(15)
                self.log("✅ 点击观看广告/WatchAD完毕")

                #watchad_screenshot = f"{self.screenshot_dir}/watchad.png"
                #sb.save_screenshot(watchad_screenshot)
                #self.send_telegram_notify("✅已点击watchad", addtime_screenshot)               

                # 通常成功后会返回服务器面板登录页面,因为没有cookies

                # 5. 再次访问目标页面
                self.log("🔗 再次访问目标页面...")
                sb.uc_open_with_reconnect(TAGET, reconnect_time=25)
                time.sleep(5)
                after = sb.get_text("#timer-page-countdown") # Renew前剩余时间

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
