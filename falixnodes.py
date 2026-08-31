import json
import os
import re
import time
import traceback
from typing import Optional, Tuple

import requests
from seleniumbase import SB

# ============================================================
# FalixNodes timer renewal - stable / verified-result edition
# Based on the Aug 22 workflow shape, but rewritten to fix the
# false-success problem after clicking Add Time.
# ============================================================

# Keep the GitHub Actions / xvfb-run behavior: do not overwrite an
# existing DISPLAY provided by xvfb-run.
if "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":1"

if "XAUTHORITY" not in os.environ:
    candidate = "/home/headless/.Xauthority"
    if os.path.exists(candidate):
        os.environ["XAUTHORITY"] = candidate

PROXY_URL = os.getenv("PROXY", "").strip()
NUM = (os.getenv("NUM") or "").strip()
TG_TOKEN = (os.getenv("TG_TOKEN") or "").strip()
TG_CHAT_ID = (os.getenv("TG_CHAT_ID") or "").strip()

if not NUM:
    raise RuntimeError("Missing environment variable: NUM")

TARGET = f"https://client.falixnodes.net/timer?id={NUM}"

# Whole-flow attempts. A failed backend renewal must start over so that
# the page receives a fresh Turnstile state/token.
MAX_FLOW_ATTEMPTS = 3

# Turnstile waiting behavior.
TURNSTILE_TIMEOUT = 70
TURNSTILE_CLICK_INTERVAL = 5

# After a click we keep observing the page before doing a hard reload.
POST_CLICK_OBSERVE_SECONDS = 25
FINAL_RELOAD_WAIT_SECONDS = 7

# A successful Falix renewal normally resets the timer close to one hour.
# We do not require an exact 60:00 because seconds elapse while checking.
SUCCESS_MIN_GAIN_SECONDS = 120
SUCCESS_NEAR_ONE_HOUR_SECONDS = 55 * 60


def parse_timer_seconds(text: str) -> Optional[int]:
    """Parse strings such as '59 minutes 40 seconds' into seconds."""
    if not text:
        return None

    value = text.strip().lower()

    # Support English timer text used by Falix.
    hour_match = re.search(r"(\d+)\s*(?:hour|hours|hr|hrs)", value)
    minute_match = re.search(r"(\d+)\s*(?:minute|minutes|min|mins)", value)
    second_match = re.search(r"(\d+)\s*(?:second|seconds|sec|secs)", value)

    if hour_match or minute_match or second_match:
        hours = int(hour_match.group(1)) if hour_match else 0
        minutes = int(minute_match.group(1)) if minute_match else 0
        seconds = int(second_match.group(1)) if second_match else 0
        return hours * 3600 + minutes * 60 + seconds

    # Fallback for HH:MM:SS / MM:SS.
    colon = re.search(r"\b(\d{1,3}):(\d{2})(?::(\d{2}))?\b", value)
    if colon:
        if colon.group(3) is not None:
            return int(colon.group(1)) * 3600 + int(colon.group(2)) * 60 + int(colon.group(3))
        return int(colon.group(1)) * 60 + int(colon.group(2))

    return None


def timer_increased_enough(before_text: str, after_text: str) -> Tuple[bool, Optional[int], Optional[int]]:
    """Return whether the server-side timer really increased."""
    before = parse_timer_seconds(before_text)
    after = parse_timer_seconds(after_text)

    if before is None or after is None:
        return False, before, after

    # Normal success: timer jumps upward by a meaningful amount.
    if after >= before + SUCCESS_MIN_GAIN_SECONDS:
        return True, before, after

    # Extra tolerance for a renewal that lands near 60 minutes.
    # This also handles some cases where the pre-read happened late.
    if before < SUCCESS_NEAR_ONE_HOUR_SECONDS and after >= SUCCESS_NEAR_ONE_HOUR_SECONDS:
        return True, before, after

    return False, before, after


def turnstile_token_value(sb) -> str:
    """Read only the real cf-turnstile-response token.

    Do not use a generic '#success' element as proof; that can create a
    false positive while the Add Time button is still legitimately disabled.
    """
    try:
        token = sb.execute_script(
            """
            const el = document.querySelector('input[name="cf-turnstile-response"]');
            return el ? (el.value || '') : '';
            """
        )
        return (token or "").strip()
    except Exception:
        return ""


def turnstile_ready(sb) -> bool:
    return len(turnstile_token_value(sb)) > 20


def wait_turnstile(sb, timeout: int = TURNSTILE_TIMEOUT) -> bool:
    """Keep the old Aug-22 style UC interaction, but accept success only
    when a real Turnstile response token exists.
    """
    print("[INFO] Waiting for Cloudflare Turnstile to become ready...", flush=True)

    try:
        sb.execute_script(
            """
            const el = document.querySelector('.cf-turnstile') ||
                       document.querySelector('iframe[src*="challenges.cloudflare"]');
            if (el) el.scrollIntoView({block: 'center', inline: 'center'});
            """
        )
    except Exception:
        pass

    start = time.time()
    last_click = 0.0

    while time.time() - start < timeout:
        if turnstile_ready(sb):
            print("[INFO] Turnstile token confirmed.", flush=True)
            return True

        now = time.time()
        if now - last_click >= TURNSTILE_CLICK_INTERVAL:
            try:
                sb.uc_gui_click_captcha()
            except Exception:
                pass
            last_click = now

        time.sleep(1)

    return turnstile_ready(sb)


def get_timer_text(sb, timeout: int = 15) -> str:
    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            text = sb.execute_script(
                """
                const el = document.querySelector('#timer-page-countdown');
                return el ? ((el.innerText || el.textContent || '').trim()) : '';
                """
            )
            if text and parse_timer_seconds(text) is not None:
                return text.strip()
        except Exception:
            pass
        time.sleep(1)

    return "unknown"


def current_url(sb) -> str:
    try:
        return (sb.get_current_url() or "").strip()
    except Exception:
        return ""


def bad_redirect(url: str) -> bool:
    value = (url or "").lower()
    return "/auth/login" in value or "google_vignette" in value


def add_button_state(sb) -> dict:
    """Return the real browser state of #timer-page-btn."""
    try:
        state = sb.execute_script(
            """
            const btn = document.querySelector('#timer-page-btn');
            if (!btn) return {exists:false};
            const st = window.getComputedStyle(btn);
            const r = btn.getBoundingClientRect();
            return {
                exists: true,
                disabled: !!btn.disabled || btn.hasAttribute('disabled'),
                ariaDisabled: (btn.getAttribute('aria-disabled') || '').toLowerCase() === 'true',
                visible: st.display !== 'none' && st.visibility !== 'hidden' &&
                         Number(st.opacity || '1') > 0 && r.width > 0 && r.height > 0,
                text: (btn.innerText || btn.textContent || '').trim()
            };
            """
        )
        return state if isinstance(state, dict) else {"exists": False}
    except Exception:
        return {"exists": False}


def wait_add_button_ready(sb, timeout: int = 20) -> bool:
    """Wait until the page itself enables Add Time.

    Important: never remove the disabled attribute. If the page still has the
    button disabled, that means the frontend/backend state is not ready.
    """
    deadline = time.time() + timeout

    while time.time() < deadline:
        if bad_redirect(current_url(sb)):
            return False

        # The token must still be present at the moment we click.
        if not turnstile_ready(sb):
            time.sleep(1)
            continue

        state = add_button_state(sb)
        if (
            state.get("exists")
            and state.get("visible")
            and not state.get("disabled")
            and not state.get("ariaDisabled")
        ):
            return True

        time.sleep(1)

    return False


class FalixNodesRenewal:
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.artifact_dir = os.path.join(self.base_dir, "artifacts")
        os.makedirs(self.artifact_dir, exist_ok=True)

    def log(self, message: str):
        stamp = time.strftime("%H:%M:%S")
        print(f"[{stamp}] {message}", flush=True)

    def shot(self, sb, name: str) -> str:
        path = os.path.join(self.artifact_dir, name)
        try:
            sb.save_screenshot(path)
        except Exception:
            pass
        return path

    def send_telegram(self, message: str, photo_path: Optional[str] = None):
        if not TG_TOKEN or not TG_CHAT_ID:
            self.log("[WARN] Telegram is not configured; notification skipped.")
            return

        try:
            if photo_path and os.path.exists(photo_path):
                endpoint = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
                with open(photo_path, "rb") as fh:
                    response = requests.post(
                        endpoint,
                        data={"chat_id": TG_CHAT_ID, "caption": message},
                        files={"photo": fh},
                        timeout=20,
                    )
            else:
                endpoint = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
                response = requests.post(
                    endpoint,
                    data={"chat_id": TG_CHAT_ID, "text": message},
                    timeout=20,
                )

            if 200 <= response.status_code < 300:
                self.log("[OK] Telegram notification sent.")
            else:
                self.log(f"[WARN] Telegram HTTP {response.status_code}: {response.text[:200]}")
        except Exception as exc:
            self.log(f"[WARN] Telegram notification failed: {exc}")

    def open_target(self, sb, reconnect_time: int = 25, settle: int = 7):
        self.log(f"[URL] Opening target: {TARGET}")
        sb.uc_open_with_reconnect(TARGET, reconnect_time=reconnect_time)
        time.sleep(settle)

    def detect_ip(self, sb):
        self.log("[NET] Detecting egress IP...")
        try:
            sb.open("https://api.ipify.org?format=json")
            body = sb.get_text("body")
            data_match = re.search(r"\{.*\}", body, flags=re.S)
            ip_value = json.loads(data_match.group(0)).get("ip", "unknown") if data_match else "unknown"
            parts = ip_value.split(".")
            if len(parts) == 4:
                masked = f"{parts[0]}.{parts[1]}.***.{parts[-1]}"
            else:
                masked = ip_value
            self.log(f"[OK] Egress IP: {masked}")
        except Exception as exc:
            self.log(f"[WARN] Egress IP detection skipped: {exc}")

    def observe_after_click(self, sb, before_text: str) -> Tuple[bool, str]:
        """Watch for a real timer jump without immediately reloading the page."""
        deadline = time.time() + POST_CLICK_OBSERVE_SECONDS
        last_text = "unknown"

        while time.time() < deadline:
            url = current_url(sb)

            # Some successful flows redirect away. Give the request a moment,
            # then re-open the timer page and verify server-side state.
            if bad_redirect(url):
                self.log(f"[INFO] Redirect detected after click: {url}")
                time.sleep(3)
                break

            now_text = get_timer_text(sb, timeout=2)
            if now_text != "unknown":
                last_text = now_text
                ok, before_sec, after_sec = timer_increased_enough(before_text, now_text)
                if ok:
                    gain = (after_sec - before_sec) if before_sec is not None and after_sec is not None else 0
                    self.log(f"[OK] Timer increased in-page by about {gain} seconds.")
                    return True, now_text

            time.sleep(2)

        # Final authoritative check: reload the public timer page and read the
        # server-side value. This is the key false-success guard.
        self.log("[CHECK] Reloading timer page to verify server-side result...")
        try:
            sb.uc_open_with_reconnect(TARGET, reconnect_time=25)
            time.sleep(FINAL_RELOAD_WAIT_SECONDS)
        except Exception as exc:
            self.log(f"[WARN] Final reload raised: {exc}")

        after_text = get_timer_text(sb, timeout=15)
        ok, before_sec, after_sec = timer_increased_enough(before_text, after_text)

        if ok:
            gain = (after_sec - before_sec) if before_sec is not None and after_sec is not None else 0
            self.log(f"[OK] Server-side renewal confirmed; gain is about {gain} seconds.")
            return True, after_text

        self.log(
            f"[FAIL] Server-side timer did not increase. before={before_text!r}, after={after_text!r}"
        )
        return False, after_text

    def run_one_flow(self, sb, flow_no: int) -> Tuple[bool, str, str, str]:
        """Return (success, reason, before, after)."""
        self.log("")
        self.log(f"[FLOW] Starting full renewal attempt {flow_no}/{MAX_FLOW_ATTEMPTS}")

        self.open_target(sb)

        url = current_url(sb)
        if bad_redirect(url):
            return False, f"redirect_before_timer:{url}", "unknown", "unknown"

        # Confirm timer exists before doing anything else.
        before = get_timer_text(sb, timeout=15)
        if before == "unknown":
            try:
                body_text = sb.get_text("body").lower()
            except Exception:
                body_text = ""

            if (
                "no active timer" in body_text
                or "back to dashboard" in body_text
                or "no active server" in body_text
            ):
                return False, "server_inactive", "unknown", "unknown"

            return False, "timer_not_found", "unknown", "unknown"

        self.log(f"[TIME] Before renewal: {before}")

        # Wait for a real CF token. No '#success' fallback is accepted.
        self.log("[CF] Waiting for Turnstile...")
        if not wait_turnstile(sb, timeout=TURNSTILE_TIMEOUT):
            return False, "turnstile_token_missing", before, "unknown"

        # The page may redirect after token processing.
        time.sleep(2)
        url = current_url(sb)
        if bad_redirect(url):
            return False, f"redirect_after_turnstile:{url}", before, "unknown"

        # Do not force-enable the button. Wait until the site itself says the
        # button is ready; otherwise a DOM click can be a no-op server-side.
        self.log("[BTN] Waiting for Add Time button to become legitimately enabled...")
        if not wait_add_button_ready(sb, timeout=20):
            state = add_button_state(sb)
            self.log(f"[FAIL] Add Time button never became ready: {state}")
            return False, "add_button_not_ready", before, "unknown"

        # Use a normal Selenium click rather than JS btn.click() and never
        # remove the disabled attribute.
        self.log("[CLICK] Clicking Add Time...")
        try:
            sb.execute_script(
                """
                const btn = document.querySelector('#timer-page-btn');
                if (btn) btn.scrollIntoView({block:'center', inline:'center'});
                """
            )
            time.sleep(1)
            sb.click("#timer-page-btn", timeout=10)
        except Exception as exc:
            return False, f"native_click_failed:{exc}", before, "unknown"

        self.log("[CLICK] Browser click completed; now verifying backend result...")

        success, after = self.observe_after_click(sb, before)
        if success:
            return True, "confirmed", before, after

        return False, "timer_not_increased", before, after

    def run(self):
        self.log("=" * 56)
        self.log("FalixNodes - Aug22 stable flow + verified renewal result")
        self.log("=" * 56)

        with SB(
            uc=True,
            test=True,
            headed=True,
            headless=False,
            xvfb=False,
            chromium_arg=(
                "--no-sandbox,--disable-dev-shm-usage,--disable-gpu,"
                "--window-position=0,0,--start-maximized"
            ),
            proxy=PROXY_URL if PROXY_URL else None,
        ) as sb:
            try:
                self.log("[OK] Browser started.")
                self.detect_ip(sb)

                last_reason = "unknown"
                last_before = "unknown"
                last_after = "unknown"

                for flow_no in range(1, MAX_FLOW_ATTEMPTS + 1):
                    success, reason, before, after = self.run_one_flow(sb, flow_no)
                    last_reason = reason
                    last_before = before
                    last_after = after

                    if success:
                        finish = self.shot(sb, "finish.png")
                        self.log("[DONE] Renewal is confirmed by timer increase.")
                        self.send_telegram(
                            "🎉 FalixNodes 保活程序\n"
                            f"🖥️编号: {NUM}\n"
                            f"🕒保活前剩余时间: {before}\n"
                            f"🚀保活后剩余时间: {after}\n"
                            "✅状态: 已确认服务器端时间增加",
                            finish,
                        )
                        return

                    fail_shot = self.shot(sb, f"attempt_{flow_no}_failed.png")
                    self.log(f"[RETRY] Attempt {flow_no} failed: {reason}")

                    if reason == "server_inactive":
                        self.send_telegram(
                            "⚠️ FalixNodes 保活程序\n"
                            f"🖥️编号: {NUM}\n"
                            "❌续费失败: 当前没有活动计时器/服务器可能已停止",
                            fail_shot,
                        )
                        return

                    if flow_no < MAX_FLOW_ATTEMPTS:
                        self.log("[RETRY] Starting over from the timer page with a fresh page state...")
                        time.sleep(5)

                final_shot = self.shot(sb, "renew_failed.png")
                self.log("[FAIL] All renewal attempts exhausted.")
                self.send_telegram(
                    "🚨 FalixNodes 保活程序\n"
                    f"🖥️编号: {NUM}\n"
                    f"❌续费失败原因: {last_reason}\n"
                    f"🕒最后一次保活前: {last_before}\n"
                    f"🕒最后一次检查后: {last_after}\n"
                    "⚠️ 未检测到服务器端时间增加，已停止误报成功",
                    final_shot,
                )

            except Exception as exc:
                self.log(f"[ERROR] Unexpected exception: {exc}")
                traceback.print_exc()
                error_shot = self.shot(sb, "error.png")
                self.send_telegram(
                    "🚨 FalixNodes 保活程序\n"
                    f"🖥️编号: {NUM}\n"
                    f"❌运行异常: {exc}",
                    error_shot,
                )


if __name__ == "__main__":
    FalixNodesRenewal().run()
