import json
import os
import re
import time
import traceback

import requests
from seleniumbase import SB


# ============================================================
# 环境配置
# ============================================================

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
# 用户配置
# ============================================================

PROXY_URL = os.getenv("PROXY", "").strip()
NUM = os.getenv("NUM", "").strip()

TG_TOKEN = os.getenv("TG_TOKEN", "").strip()
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "").strip()

# 如果 Turnstile 自己正常通过，通常很快就会产生 token。
# GitHub Actions 没有真人交互，所以没必要无限等待。
TURNSTILE_WAIT_SECONDS = int(
    os.getenv("TURNSTILE_WAIT_SECONDS", "60")
)

# Add Time 最长等待时间
ADD_TIME_WAIT_SECONDS = int(
    os.getenv("ADD_TIME_WAIT_SECONDS", "45")
)

# 广告处理最长等待
AD_WAIT_SECONDS = int(
    os.getenv("AD_WAIT_SECONDS", "60")
)


if not NUM:
    raise RuntimeError(
        "缺少 GitHub Secret: NUM"
    )


TARGET = (
    "https://client.falixnodes.net/"
    f"timer?id={NUM}"
)


# ============================================================
# Falix 自动化
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

    # ========================================================
    # 日志
    # ========================================================

    def log(self, message):

        timestamp = time.strftime(
            "%H:%M:%S"
        )

        print(
            f"[{timestamp}] [INFO] {message}",
            flush=True,
        )

    # ========================================================
    # 截图
    # ========================================================

    def screenshot(
        self,
        sb,
        name,
    ):

        path = os.path.join(
            self.screenshot_dir,
            name,
        )

        try:

            sb.save_screenshot(
                path
            )

            self.log(
                f"📸 截图已保存: {name}"
            )

        except Exception as error:

            self.log(
                f"⚠️ 截图失败: {error}"
            )

        return path

    # ========================================================
    # Telegram
    # ========================================================

    def telegram(
        self,
        message,
        photo=None,
    ):

        if (
            not TG_TOKEN
            or not TG_CHAT_ID
        ):
            self.log(
                "⚠️ 未设置 TG_TOKEN/TG_CHAT_ID"
            )
            return

        try:

            if (
                photo
                and os.path.isfile(photo)
            ):

                url = (
                    "https://api.telegram.org/"
                    f"bot{TG_TOKEN}/sendPhoto"
                )

                with open(
                    photo,
                    "rb",
                ) as fp:

                    response = requests.post(
                        url,
                        data={
                            "chat_id":
                                TG_CHAT_ID,
                            "caption":
                                message,
                        },
                        files={
                            "photo":
                                fp,
                        },
                        timeout=30,
                    )

            else:

                url = (
                    "https://api.telegram.org/"
                    f"bot{TG_TOKEN}/sendMessage"
                )

                response = requests.post(
                    url,
                    data={
                        "chat_id":
                            TG_CHAT_ID,
                        "text":
                            message,
                    },
                    timeout=30,
                )

            response.raise_for_status()

            self.log(
                "✅ Telegram 推送完成"
            )

        except Exception as error:

            self.log(
                f"⚠️ Telegram 推送失败: {error}"
            )

    # ========================================================
    # IP
    # ========================================================

    def check_ip(
        self,
        sb,
    ):

        self.log(
            "🌍 正在检测出口 IP..."
        )

        try:

            sb.open(
                "https://api.ipify.org?format=json"
            )

            text = sb.get_text(
                "body"
            )

            match = re.search(
                r"\{.*?\}",
                text,
                re.S,
            )

            if not match:
                raise RuntimeError(
                    "无法读取 IP"
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
                    "***."
                    f"{parts[-1]}"
                )

            else:
                masked = ip

            self.log(
                f"✅ 当前出口 IP: {masked}"
            )

        except Exception as error:

            self.log(
                f"⚠️ IP 检测失败: {error}"
            )

    # ========================================================
    # Countdown
    # ========================================================

    def read_countdown(
        self,
        sb,
        timeout=20,
    ):

        selectors = [
            "#timer-page-countdown",
            "[id*='countdown']",
            "[data-countdown]",
        ]

        deadline = (
            time.time() + timeout
        )

        while (
            time.time()
            < deadline
        ):

            for selector in selectors:

                try:

                    if sb.is_element_visible(
                        selector
                    ):

                        text = sb.get_text(
                            selector
                        ).strip()

                        if (
                            text
                            and "--" not in text
                            and "loading" not in
                            text.lower()
                        ):

                            return text

                except Exception:
                    pass

            time.sleep(1)

        return None

    # ========================================================
    # Countdown 转秒数
    # ========================================================

    def countdown_seconds(
        self,
        text,
    ):

        if not text:
            return None

        text = (
            text.lower()
            .replace(",", " ")
        )

        total = 0
        found = False

        patterns = [
            (
                r"(\d+)\s*(?:hours?|小时)",
                3600,
            ),
            (
                r"(\d+)\s*(?:minutes?|分钟)",
                60,
            ),
            (
                r"(\d+)\s*(?:seconds?|秒)",
                1,
            ),
        ]

        for pattern, multiplier in patterns:

            match = re.search(
                pattern,
                text,
                re.I,
            )

            if match:

                total += (
                    int(match.group(1))
                    * multiplier
                )

                found = True

        if found:
            return total

        # HH:MM:SS
        match = re.search(
            r"(\d+):(\d+):(\d+)",
            text,
        )

        if match:

            h = int(
                match.group(1)
            )

            m = int(
                match.group(2)
            )

            s = int(
                match.group(3)
            )

            return (
                h * 3600
                + m * 60
                + s
            )

        # MM:SS
        match = re.search(
            r"(\d+):(\d+)",
            text,
        )

        if match:

            return (
                int(match.group(1))
                * 60
                + int(match.group(2))
            )

        return None

    # ========================================================
    # Turnstile token
    # ========================================================

    def get_turnstile_token(
        self,
        sb,
    ):

        try:

            token = sb.execute_script(
                """
                const el =
                    document.querySelector(
                        'input[name="cf-turnstile-response"]'
                    );

                return el
                    ? (el.value || '')
                    : '';
                """
            )

            if token:
                return str(token)

        except Exception:
            pass

        return ""

    # ========================================================
    # 等待正常 Turnstile 完成
    # ========================================================

    def wait_for_turnstile(
        self,
        sb,
    ):

        self.log(
            "⏳ 检查 Turnstile..."
        )

        token = (
            self.get_turnstile_token(
                sb
            )
        )

        if token:

            self.log(
                "✅ Turnstile 已完成"
            )

            return token

        waiting = self.screenshot(
            sb,
            "turnstile_waiting.png",
        )

        self.telegram(
            (
                "⏳ FalixNodes 等待 Turnstile\n"
                f"🖥️ Server: {NUM}"
            ),
            waiting,
        )

        self.log(
            "⏳ 等待正常 Turnstile 验证..."
        )

        deadline = (
            time.time()
            + TURNSTILE_WAIT_SECONDS
        )

        while (
            time.time()
            < deadline
        ):

            token = (
                self.get_turnstile_token(
                    sb
                )
            )

            if token:

                self.log(
                    "✅ 检测到 Turnstile Token"
                )

                self.log(
                    f"Token length={len(token)}"
                )

                return token

            time.sleep(2)

        failed = self.screenshot(
            sb,
            "turnstile_failed.png",
        )

        self.telegram(
            (
                "❌ FalixNodes Turnstile 未完成\n"
                f"🖥️ Server: {NUM}"
            ),
            failed,
        )

        raise RuntimeError(
            "Turnstile 未正常完成"
        )

    # ========================================================
    # 检测可见遮罩/广告
    # ========================================================

    def visible_dialogs(
        self,
        sb,
    ):

        try:

            return sb.execute_script(
                """
                return Array.from(
                    document.querySelectorAll(
                        [
                            '[role="dialog"]',
                            '.modal',
                            '.popup',
                            '.overlay',
                            '[class*="advert"]',
                            '[class*="interstitial"]'
                        ].join(',')
                    )
                )
                .filter(el => {
                    const r =
                        el.getBoundingClientRect();

                    const s =
                        getComputedStyle(el);

                    return (
                        r.width > 0 &&
                        r.height > 0 &&
                        s.display !== 'none' &&
                        s.visibility !== 'hidden'
                    );
                })
                .map(el => ({
                    tag:
                        el.tagName,
                    id:
                        el.id || '',
                    className:
                        String(
                            el.className || ''
                        ).slice(0, 120)
                }));
                """
            ) or []

        except Exception:

            return []

    # ========================================================
    # 关闭页面允许关闭的弹窗
    #
    # 只点击真正提供出来的关闭/跳过控件。
    # 不删除 DOM、不强制穿透广告。
    # ========================================================

    def close_allowed_overlays(
        self,
        sb,
    ):

        selectors = [
            "[role='dialog'] button[aria-label='Close']",
            "[role='dialog'] button[aria-label='close']",

            ".modal button[aria-label='Close']",
            ".modal .btn-close",

            "[data-bs-dismiss='modal']",

            "button[title='Close']",
            "button[title='close']",
        ]

        closed = False

        for selector in selectors:

            try:

                if sb.is_element_visible(
                    selector
                ):

                    self.log(
                        f"🪟 关闭弹窗: {selector}"
                    )

                    sb.click(
                        selector
                    )

                    time.sleep(1)

                    closed = True

            except Exception:
                pass

        # 再检查具有明确 Close/Skip/关闭/跳过 文本的按钮
        xpath_list = [
            (
                "//div[@role='dialog']"
                "//button["
                "normalize-space(.)='Close'"
                "]"
            ),
            (
                "//div[@role='dialog']"
                "//button["
                "normalize-space(.)='Skip'"
                "]"
            ),
            (
                "//div[@role='dialog']"
                "//button["
                "normalize-space(.)='关闭'"
                "]"
            ),
            (
                "//div[@role='dialog']"
                "//button["
                "normalize-space(.)='跳过'"
                "]"
            ),
        ]

        for xpath in xpath_list:

            try:

                if sb.is_element_visible(
                    xpath
                ):

                    self.log(
                        "🪟 点击页面提供的关闭/跳过按钮"
                    )

                    sb.click(
                        xpath
                    )

                    time.sleep(1)

                    closed = True

            except Exception:
                pass

        return closed

    # ========================================================
    # 打印按钮信息
    #
    # 出错时特别有用。
    # 不输出 token / cookie / HTML。
    # ========================================================

    def dump_buttons(
        self,
        sb,
    ):

        self.log(
            "🔎 当前页面可点击元素："
        )

        try:

            items = sb.execute_script(
                """
                return Array.from(
                    document.querySelectorAll(
                        [
                            'button',
                            'input[type="button"]',
                            'input[type="submit"]',
                            '[role="button"]',
                            'a'
                        ].join(',')
                    )
                )
                .map(el => {

                    const rect =
                        el.getBoundingClientRect();

                    const style =
                        getComputedStyle(el);

                    const text = (
                        el.innerText ||
                        el.value ||
                        el.getAttribute(
                            'aria-label'
                        ) ||
                        ''
                    )
                    .replace(/\\s+/g, ' ')
                    .trim()
                    .slice(0, 100);

                    return {
                        tag:
                            el.tagName,
                        id:
                            el.id || '',
                        text:
                            text,
                        disabled:
                            !!el.disabled,
                        visible:
                            (
                                rect.width > 0 &&
                                rect.height > 0 &&
                                style.display
                                    !== 'none' &&
                                style.visibility
                                    !== 'hidden'
                            )
                    };
                })
                .filter(
                    el => el.visible
                )
                .slice(0, 50);
                """
            )

            for item in items:

                self.log(
                    f"🔎 BUTTON {item}"
                )

        except Exception as error:

            self.log(
                f"⚠️ 读取按钮失败: {error}"
            )

    # ========================================================
    # Add Time selector
    # ========================================================

    def add_time_selectors(
        self,
    ):

        upper = (
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        )

        lower = (
            "abcdefghijklmnopqrstuvwxyz"
        )

        return [
            # 老页面
            "#timer-page-btn",

            # 常见 ID
            "#add-time-btn",
            "#addTimeBtn",

            # 英文 Button
            (
                "//button[contains("
                f"translate(normalize-space(.),"
                f"'{upper}','{lower}'),"
                "'add time')]"
            ),

            # 英文 role=button
            (
                "//*[@role='button' and "
                "contains("
                f"translate(normalize-space(.),"
                f"'{upper}','{lower}'),"
                "'add time')]"
            ),

            # 英文 submit
            (
                "//input[@type='submit' and "
                "contains("
                f"translate(@value,"
                f"'{upper}','{lower}'),"
                "'add time')]"
            ),

            # 中文
            (
                "//button[contains("
                "normalize-space(.),"
                "'添加时间')]"
            ),

            (
                "//*[@role='button' and "
                "contains("
                "normalize-space(.),"
                "'添加时间')]"
            ),

            (
                "//button[contains("
                "normalize-space(.),"
                "'增加时间')]"
            ),
        ]

    # ========================================================
    # 点击 Add Time
    # ========================================================

    def click_add_time(
        self,
        sb,
    ):

        self.log(
            "🖱️ 开始查找添加时间/Add Time"
        )

        deadline = (
            time.time()
            + ADD_TIME_WAIT_SECONDS
        )

        last_overlay_log = 0

        while (
            time.time()
            < deadline
        ):

            # --------------------------------------------
            # 先处理页面允许关闭的弹窗
            # --------------------------------------------

            self.close_allowed_overlays(
                sb
            )

            dialogs = (
                self.visible_dialogs(
                    sb
                )
            )

            if (
                dialogs
                and time.time()
                - last_overlay_log > 5
            ):

                self.log(
                    f"🪟 检测到遮罩/弹窗: {dialogs}"
                )

                last_overlay_log = (
                    time.time()
                )

            # --------------------------------------------
            # 找 Add Time
            # --------------------------------------------

            for selector in (
                self.add_time_selectors()
            ):

                try:

                    if not sb.is_element_visible(
                        selector
                    ):
                        continue

                    self.log(
                        "✅ 找到 Add Time: "
                        f"{selector}"
                    )

                    # Selenium 正常点击，
                    # 不用 JS 强制穿过遮罩
                    sb.scroll_to(
                        selector
                    )

                    time.sleep(0.5)

                    try:

                        sb.click(
                            selector
                        )

                    except Exception as error:

                        self.log(
                            "⚠️ Add Time 点击被阻挡: "
                            f"{error}"
                        )

                        self.close_allowed_overlays(
                            sb
                        )

                        time.sleep(1)

                        sb.click(
                            selector
                        )

                    self.log(
                        "✅ 已点击添加时间/Add Time"
                    )

                    self.screenshot(
                        sb,
                        "after_add_time_click.png",
                    )

                    return

                except Exception:
                    continue

            time.sleep(1)

        self.dump_buttons(
            sb
        )

        screenshot = self.screenshot(
            sb,
            "add_time_not_found.png",
        )

        self.telegram(
            (
                "❌ 找不到 Add Time\n"
                f"🖥️ Server: {NUM}"
            ),
            screenshot,
        )

        raise RuntimeError(
            "Add Time 按钮不存在或持续被页面遮挡"
        )

    # ========================================================
    # Watch Ad
    # ========================================================

    def handle_watch_ad(
        self,
        sb,
    ):

        self.log(
            "📺 检查 Watch Ad..."
        )

        selectors = [
            "#watchAdBtn",
            "#watch-ad-btn",

            (
                "//button[contains("
                "normalize-space(.),"
                "'Watch Ad')]"
            ),

            (
                "//button[contains("
                "normalize-space(.),"
                "'观看广告')]"
            ),
        ]

        found = None

        for selector in selectors:

            try:

                if sb.is_element_visible(
                    selector
                ):

                    found = selector

                    break

            except Exception:
                pass

        if not found:

            self.log(
                "✅ 无需观看广告/Watch Ad"
            )

            return

        self.log(
            f"📺 检测到 Watch Ad: {found}"
        )

        self.screenshot(
            sb,
            "before_watch_ad.png",
        )

        sb.click(
            found
        )

        self.log(
            "📺 已进入广告流程"
        )

        deadline = (
            time.time()
            + AD_WAIT_SECONDS
        )

        while (
            time.time()
            < deadline
        ):

            # 如果网站提供 Close / Skip，
            # 在它真正可用以后关闭
            if self.close_allowed_overlays(
                sb
            ):

                time.sleep(2)

            # Watch Ad 按钮消失，
            # 一般说明已经处理完
            try:

                if not sb.is_element_visible(
                    found
                ):

                    self.log(
                        "✅ Watch Ad 已完成"
                    )

                    return

            except Exception:

                self.log(
                    "✅ Watch Ad 已完成"
                )

                return

            time.sleep(2)

        self.log(
            "⚠️ Watch Ad 等待超时，继续检查续时结果"
        )

    # ========================================================
    # 验证续时结果
    # ========================================================

    def verify_renewal(
        self,
        sb,
        before_text,
    ):

        self.log(
            "🔍 检查续时是否成功..."
        )

        before_seconds = (
            self.countdown_seconds(
                before_text
            )
        )

        deadline = (
            time.time() + 30
        )

        latest_text = None

        while (
            time.time()
            < deadline
        ):

            latest_text = (
                self.read_countdown(
                    sb,
                    timeout=3,
                )
            )

            if latest_text:

                after_seconds = (
                    self.countdown_seconds(
                        latest_text
                    )
                )

                self.log(
                    "🕒 当前倒计时: "
                    f"{latest_text}"
                )

                if (
                    before_seconds
                    is not None
                    and after_seconds
                    is not None
                    and after_seconds
                    > before_seconds + 30
                ):

                    self.log(
                        "✅ 已确认倒计时增加"
                    )

                    return latest_text

            time.sleep(2)

        # --------------------------------------------
        # 当前页面没更新时重新打开一次
        # --------------------------------------------

        self.log(
            "🔄 当前页面未确认，重新读取 Timer..."
        )

        sb.open(
            TARGET
        )

        time.sleep(5)

        latest_text = (
            self.read_countdown(
                sb,
                timeout=20,
            )
        )

        if not latest_text:

            raise RuntimeError(
                "续时后无法读取倒计时"
            )

        after_seconds = (
            self.countdown_seconds(
                latest_text
            )
        )

        self.log(
            f"🕒 重新读取: {latest_text}"
        )

        if (
            before_seconds
            is not None
            and after_seconds
            is not None
            and after_seconds
            > before_seconds + 30
        ):

            self.log(
                "✅ 续时成功"
            )

            return latest_text

        raise RuntimeError(
            (
                "点击 Add Time 后倒计时"
                "没有明显增加："
                f"{before_text} -> "
                f"{latest_text}"
            )
        )

    # ========================================================
    # 主任务
    # ========================================================

    def run(
        self,
    ):

        self.log(
            "=" * 52
        )

        self.log(
            "🚀 FalixNodes - 保活流程"
        )

        self.log(
            "=" * 52
        )

        self.log(
            "🎯 正在启动 Chrome 浏览器..."
        )

        with SB(
            test=True,

            # GitHub Actions 配合 xvfb-run
            headed=True,
            headless=False,
            xvfb=False,

            chromium_arg=(
                "--no-sandbox,"
                "--disable-dev-shm-usage,"
                "--disable-gpu,"
                "--window-position=0,0,"
                "--window-size=1280,900"
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

                # ========================================
                # 1. IP
                # ========================================

                self.check_ip(
                    sb
                )

                # ========================================
                # 2. Timer 页面
                # ========================================

                self.log(
                    f"🔗 访问 Timer 页面: {NUM}"
                )

                sb.open(
                    TARGET
                )

                time.sleep(5)

                initial = self.screenshot(
                    sb,
                    "timer_page.png",
                )

                # ========================================
                # 3. Countdown
                # ========================================

                before = (
                    self.read_countdown(
                        sb,
                        timeout=30,
                    )
                )

                if not before:

                    self.dump_buttons(
                        sb
                    )

                    self.telegram(
                        (
                            "❌ 未检测到服务器倒计时\n"
                            f"🖥️ Server: {NUM}\n"
                            "服务器可能停止运行"
                        ),
                        initial,
                    )

                    raise RuntimeError(
                        "Timer countdown not found"
                    )

                self.log(
                    f"🕒 保活前: {before}"
                )

                # ========================================
                # 4. Turnstile
                # ========================================

                token = (
                    self.wait_for_turnstile(
                        sb
                    )
                )

                self.log(
                    "🎉 Turnstile 验证完成"
                )

                self.log(
                    f"Token length={len(token)}"
                )

                verified = self.screenshot(
                    sb,
                    "turnstile_verified.png",
                )

                # ========================================
                # 5. 处理验证后出现的弹窗/广告遮罩
                # ========================================

                self.log(
                    "🪟 检查验证后的页面遮罩..."
                )

                self.close_allowed_overlays(
                    sb
                )

                time.sleep(2)

                # ========================================
                # 6. Add Time
                # ========================================

                self.log(
                    "🖱️ 开始处理 Add Time"
                )

                self.click_add_time(
                    sb
                )

                time.sleep(3)

                # ========================================
                # 7. Watch Ad
                # ========================================

                self.handle_watch_ad(
                    sb
                )

                # ========================================
                # 8. 验证结果
                # ========================================

                after = (
                    self.verify_renewal(
                        sb,
                        before,
                    )
                )

                # ========================================
                # 9. 完成截图
                # ========================================

                finish = self.screenshot(
                    sb,
                    "finish.png",
                )

                # ========================================
                # 10. TG
                # ========================================

                self.telegram(
                    (
                        "🎉 FalixNodes 保活完成\n"
                        f"🖥️ Server: {NUM}\n"
                        f"🕒 保活前: {before}\n"
                        f"🚀 保活后: {after}"
                    ),
                    finish,
                )

                self.log(
                    "✅ 全部流程执行完毕"
                )

            except Exception as error:

                self.log(
                    f"❌ 运行异常: {error}"
                )

                traceback.print_exc()

                error_image = (
                    self.screenshot(
                        sb,
                        "error.png",
                    )
                )

                self.dump_buttons(
                    sb
                )

                self.telegram(
                    (
                        "❌ FalixNodes 运行失败\n"
                        f"🖥️ Server: {NUM}\n"
                        f"错误: {error}"
                    ),
                    error_image,
                )

                # 必须重新抛异常
                # GitHub Actions 才会显示红色
                raise


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":

    FalixNodesRenewal().run()
