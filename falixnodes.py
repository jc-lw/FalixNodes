import json
import os
import re
import time
import traceback

import requests
from seleniumbase import SB


# ============================================================
# 配置
# ============================================================

PROXY_URL = os.getenv("PROXY", "").strip()
NUM = os.getenv("NUM", "").strip()

TG_TOKEN = os.getenv("TG_TOKEN", "").strip()
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "").strip()

# 等待真实 Turnstile 验证的最长时间
TURNSTILE_WAIT_SECONDS = int(
    os.getenv("TURNSTILE_WAIT_SECONDS", "180")
)

if not NUM:
    raise RuntimeError("未配置 NUM")

TARGET = f"https://client.falixnodes.net/timer?id={NUM}"


# GitHub Actions 的 xvfb-run 会自动设置 DISPLAY
if "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":1"

if "XAUTHORITY" not in os.environ:
    default_xauthority = "/home/headless/.Xauthority"

    if os.path.exists(default_xauthority):
        os.environ["XAUTHORITY"] = default_xauthority


print(
    f"[DEBUG] Env DISPLAY: {os.environ.get('DISPLAY')}",
    flush=True,
)

print(
    f"[DEBUG] Env XAUTHORITY: {os.environ.get('XAUTHORITY')}",
    flush=True,
)


# ============================================================
# 主程序
# ============================================================

class FalixNodesRenewal:

    def __init__(self):
        self.base_dir = os.path.dirname(
            os.path.abspath(__file__)
        )

        self.screenshot_dir = os.path.join(
            self.base_dir,
            "artifacts",
        )

        os.makedirs(
            self.screenshot_dir,
            exist_ok=True,
        )

    # --------------------------------------------------------
    # 日志
    # --------------------------------------------------------

    def log(self, message):
        timestamp = time.strftime("%H:%M:%S")

        print(
            f"[{timestamp}] [INFO] {message}",
            flush=True,
        )

    # --------------------------------------------------------
    # Telegram
    # --------------------------------------------------------

    def send_telegram_notify(
        self,
        message,
        photo_path=None,
    ):

        if not TG_TOKEN or not TG_CHAT_ID:
            self.log(
                "⚠️ 未配置 TG_TOKEN / TG_CHAT_ID，跳过 Telegram"
            )
            return

        try:

            if (
                photo_path
                and os.path.exists(photo_path)
            ):

                url = (
                    f"https://api.telegram.org/"
                    f"bot{TG_TOKEN}/sendPhoto"
                )

                with open(photo_path, "rb") as file:

                    response = requests.post(
                        url,
                        data={
                            "chat_id": TG_CHAT_ID,
                            "caption": message,
                        },
                        files={
                            "photo": file,
                        },
                        timeout=20,
                    )

            else:

                url = (
                    f"https://api.telegram.org/"
                    f"bot{TG_TOKEN}/sendMessage"
                )

                response = requests.post(
                    url,
                    data={
                        "chat_id": TG_CHAT_ID,
                        "text": message,
                    },
                    timeout=20,
                )

            response.raise_for_status()

            self.log("✅ Telegram 推送完成")

        except Exception as error:

            self.log(
                f"⚠️ Telegram 推送失败: {error}"
            )

    # --------------------------------------------------------
    # 获取 IP
    # --------------------------------------------------------

    def check_ip(self, sb):

        self.log("🌍 正在检测出口 IP...")

        try:

            sb.open(
                "https://api.ipify.org?format=json"
            )

            text = sb.get_text("body")

            match = re.search(
                r"\{.*\}",
                text,
                re.DOTALL,
            )

            if not match:
                raise RuntimeError(
                    "无法读取 IP API"
                )

            ip = json.loads(
                match.group(0)
            ).get(
                "ip",
                "Unknown",
            )

            parts = ip.split(".")

            if len(parts) == 4:

                masked = (
                    f"{parts[0]}."
                    f"{parts[1]}."
                    f"***."
                    f"{parts[-1]}"
                )

            else:
                masked = ip

            self.log(
                f"✅ 当前出口 IP: {masked}"
            )

        except Exception as error:

            self.log(
                f"⚠️ IP 检测失败，继续运行: {error}"
            )

    # --------------------------------------------------------
    # 获取倒计时
    # --------------------------------------------------------

    def get_countdown(
        self,
        sb,
        timeout=15,
    ):

        selector = "#timer-page-countdown"

        try:

            sb.wait_for_element_visible(
                selector,
                timeout=timeout,
            )

            text = sb.get_text(
                selector
            ).strip()

            return text

        except Exception:

            return None

    # --------------------------------------------------------
    # Turnstile Token
    #
    # 这里只检测正常验证产生的 token。
    # 不点击、不模拟、不绕过验证码。
    # --------------------------------------------------------

    def get_turnstile_token(self, sb):

        try:

            token = sb.execute_script(
                """
                const el =
                    document.querySelector(
                        'input[name="cf-turnstile-response"]'
                    );

                return el ? (el.value || '') : '';
                """
            )

            return token or ""

        except Exception:

            return ""

    def wait_for_turnstile(self, sb):

        token = self.get_turnstile_token(sb)

        if token:

            self.log(
                "✅ Turnstile 已完成"
            )

            return token

        screenshot = os.path.join(
            self.screenshot_dir,
            "waiting_turnstile.png",
        )

        sb.save_screenshot(
            screenshot
        )

        self.log(
            "⏳ 等待真实 Turnstile 验证..."
        )

        self.send_telegram_notify(
            (
                "⏳ FalixNodes 等待真人验证\n"
                f"🖥️ 编号: {NUM}"
            ),
            screenshot,
        )

        start = time.time()

        while (
            time.time() - start
            < TURNSTILE_WAIT_SECONDS
        ):

            token = self.get_turnstile_token(
                sb
            )

            if token:

                self.log(
                    "✅ 检测到有效 Turnstile Token"
                )

                self.log(
                    f"Token length={len(token)}"
                )

                return token

            time.sleep(2)

        raise RuntimeError(
            (
                "等待 Turnstile 验证超时："
                f"{TURNSTILE_WAIT_SECONDS}s"
            )
        )

    # --------------------------------------------------------
    # 输出当前可点击元素
    #
    # 用于页面再次改版时排查 selector。
    # 不输出 Cookie / Token / HTML。
    # --------------------------------------------------------

    def dump_clickables(self, sb):

        try:

            items = sb.execute_script(
                """
                const nodes = Array.from(
                    document.querySelectorAll(
                        [
                            'button',
                            'input[type="submit"]',
                            'input[type="button"]',
                            '[role="button"]'
                        ].join(',')
                    )
                );

                return nodes.slice(0, 50).map(el => {

                    const text = (
                        el.innerText ||
                        el.value ||
                        el.getAttribute('aria-label') ||
                        ''
                    )
                    .trim()
                    .slice(0, 100);

                    return {
                        tag: el.tagName,
                        id: el.id || '',
                        type: el.type || '',
                        text: text,
                        disabled:
                            !!el.disabled,
                        visible:
                            !!(
                                el.offsetWidth ||
                                el.offsetHeight ||
                                el.getClientRects().length
                            )
                    };
                });
                """
            )

            for item in items or []:

                self.log(
                    f"🔎 CLICKABLE: {item}"
                )

        except Exception as error:

            self.log(
                f"⚠️ 无法获取按钮列表: {error}"
            )

    # --------------------------------------------------------
    # 自动寻找 Add Time
    #
    # 优先旧 ID，失败后按照按钮文字寻找。
    # --------------------------------------------------------

    def click_add_time(self, sb):

        self.log(
            "🖱️ 正在查找 Add Time 按钮..."
        )

        # 验证完成后给页面几秒更新 UI
        time.sleep(3)

        result = sb.execute_script(
            """
            function visible(el) {

                if (!el) {
                    return false;
                }

                const style =
                    window.getComputedStyle(el);

                const rect =
                    el.getBoundingClientRect();

                return (
                    style.display !== 'none' &&
                    style.visibility !== 'hidden' &&
                    rect.width > 0 &&
                    rect.height > 0
                );
            }


            function getLabel(el) {

                return (
                    el.innerText ||
                    el.value ||
                    el.getAttribute('aria-label') ||
                    el.getAttribute('title') ||
                    ''
                ).trim();
            }


            // ----------------------------------------
            // 1. 兼容旧 Falix selector
            // ----------------------------------------

            const oldButton =
                document.querySelector(
                    '#timer-page-btn'
                );

            if (
                oldButton &&
                visible(oldButton) &&
                !oldButton.disabled
            ) {

                oldButton.scrollIntoView({
                    block: 'center'
                });

                oldButton.click();

                return {
                    clicked: true,
                    method:
                        '#timer-page-btn',
                    text:
                        getLabel(oldButton)
                };
            }


            // ----------------------------------------
            // 2. 查找真正的 clickable 元素
            // ----------------------------------------

            const elements =
                Array.from(
                    document.querySelectorAll(
                        [
                            'button',
                            'input[type="submit"]',
                            'input[type="button"]',
                            '[role="button"]',
                            'a'
                        ].join(',')
                    )
                );


            const button =
                elements.find(el => {

                    if (
                        !visible(el) ||
                        el.disabled
                    ) {
                        return false;
                    }

                    const label =
                        getLabel(el)
                            .replace(
                                /\\s+/g,
                                ' '
                            )
                            .trim();

                    return /^add\\s*time$/i.test(
                        label
                    );

                }) ||

                elements.find(el => {

                    if (
                        !visible(el) ||
                        el.disabled
                    ) {
                        return false;
                    }

                    const label =
                        getLabel(el)
                            .replace(
                                /\\s+/g,
                                ' '
                            )
                            .trim();

                    return /add\\s*time/i.test(
                        label
                    );
                });


            if (!button) {

                return {
                    clicked: false
                };
            }


            button.scrollIntoView({
                block: 'center'
            });

            button.click();


            return {
                clicked: true,
                method:
                    'text-search',
                tag:
                    button.tagName,
                id:
                    button.id || '',
                text:
                    getLabel(button)
            };
            """
        )

        if (
            isinstance(result, dict)
            and result.get("clicked")
        ):

            self.log(
                (
                    "✅ 已点击 Add Time "
                    f"{result}"
                )
            )

            return True

        self.log(
            "❌ 没有找到 Add Time"
        )

        self.dump_clickables(sb)

        screenshot = os.path.join(
            self.screenshot_dir,
            "addtime_not_found.png",
        )

        sb.save_screenshot(
            screenshot
        )

        self.send_telegram_notify(
            (
                "❌ FalixNodes 未找到 Add Time\n"
                f"🖥️ 编号: {NUM}"
            ),
            screenshot,
        )

        raise RuntimeError(
            "Add Time button not found"
        )

    # --------------------------------------------------------
    # Watch Ad
    # --------------------------------------------------------

    def handle_watch_ad(self, sb):

        self.log(
            "🖱️ 检查 Watch Ad..."
        )

        time.sleep(2)

        try:

            if sb.is_element_visible(
                "#watchAdBtn"
            ):

                self.log(
                    "📺 检测到 Watch Ad"
                )

                sb.click(
                    "#watchAdBtn"
                )

                time.sleep(15)

                self.log(
                    "✅ Watch Ad 已处理"
                )

                return

        except Exception as error:

            self.log(
                f"⚠️ Watch Ad 检查异常: {error}"
            )

        self.log(
            "✅ 页面没有 Watch Ad"
        )

    # --------------------------------------------------------
    # 主流程
    # --------------------------------------------------------

    def run(self):

        self.log("=" * 50)
        self.log(
            "🚀 FalixNodes - 保活流程"
        )
        self.log("=" * 50)

        self.log(
            "🎯 正在启动 Chrome..."
        )

        with SB(
            test=True,

            headed=True,
            headless=False,

            # 外部使用 xvfb-run
            xvfb=False,

            chromium_arg=(
                "--no-sandbox,"
                "--disable-dev-shm-usage,"
                "--disable-gpu,"
                "--window-position=0,0,"
                "--start-maximized"
            ),

            proxy=(
                PROXY_URL
                if PROXY_URL
                else None
            ),

        ) as sb:

            try:

                self.log(
                    "✅ Chrome 已启动"
                )

                # ------------------------------------
                # IP
                # ------------------------------------

                self.check_ip(sb)

                # ------------------------------------
                # 访问 Falix
                # ------------------------------------

                self.log(
                    f"🔗 访问 Timer 页面: {NUM}"
                )

                sb.open(
                    TARGET
                )

                time.sleep(5)

                # ------------------------------------
                # 获取续时前倒计时
                # ------------------------------------

                before = self.get_countdown(
                    sb,
                    timeout=15,
                )

                if not before:

                    screenshot = os.path.join(
                        self.screenshot_dir,
                        "timer_not_found.png",
                    )

                    sb.save_screenshot(
                        screenshot
                    )

                    self.send_telegram_notify(
                        (
                            "❌ FalixNodes 未检测到 Timer\n"
                            f"🖥️ 编号: {NUM}\n"
                            "服务器可能关闭或 Timer 未启动"
                        ),
                        screenshot,
                    )

                    raise RuntimeError(
                        "Timer countdown not found"
                    )

                self.log(
                    f"🕒 保活前: {before}"
                )

                # ------------------------------------
                # 正常 Turnstile 验证
                # ------------------------------------

                self.log(
                    "⏳ 检查 Turnstile..."
                )

                self.wait_for_turnstile(
                    sb
                )

                verified_screenshot = os.path.join(
                    self.screenshot_dir,
                    "verified.png",
                )

                sb.save_screenshot(
                    verified_screenshot
                )

                # ------------------------------------
                # Add Time
                # ------------------------------------

                self.click_add_time(
                    sb
                )

                time.sleep(3)

                # ------------------------------------
                # Watch Ad（如果有）
                # ------------------------------------

                self.handle_watch_ad(
                    sb
                )

                # ------------------------------------
                # 重新访问页面确认
                # ------------------------------------

                self.log(
                    "🔄 重新读取 Timer..."
                )

                sb.open(
                    TARGET
                )

                time.sleep(5)

                after = self.get_countdown(
                    sb,
                    timeout=15,
                )

                if not after:

                    raise RuntimeError(
                        (
                            "Add Time 后无法读取"
                            "新的倒计时"
                        )
                    )

                self.log(
                    f"🕒 保活后: {after}"
                )

                # ------------------------------------
                # 成功
                # ------------------------------------

                finish_screenshot = os.path.join(
                    self.screenshot_dir,
                    "finish.png",
                )

                sb.save_screenshot(
                    finish_screenshot
                )

                message = (
                    "🎉 FalixNodes 保活完成\n"
                    f"🖥️ 编号: {NUM}\n"
                    f"🕒 保活前: {before}\n"
                    f"🚀 保活后: {after}"
                )

                self.send_telegram_notify(
                    message,
                    finish_screenshot,
                )

                self.log(
                    "✅ 全部流程执行完毕"
                )

            except Exception as error:

                self.log(
                    f"❌ 运行异常: {error}"
                )

                traceback.print_exc()

                error_screenshot = os.path.join(
                    self.screenshot_dir,
                    "error.png",
                )

                try:
                    sb.save_screenshot(
                        error_screenshot
                    )
                except Exception:
                    pass

                self.send_telegram_notify(
                    (
                        "❌ FalixNodes 运行失败\n"
                        f"🖥️ 编号: {NUM}\n"
                        f"错误: {error}"
                    ),
                    error_screenshot,
                )

                # 非常重要：
                # 重新抛出异常，让 GitHub Action 变成红色失败
                raise


# ============================================================
# Entry
# ============================================================

if __name__ == "__main__":
    FalixNodesRenewal().run()
