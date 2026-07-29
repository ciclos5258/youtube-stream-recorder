import subprocess
import time
import requests
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from html import escape
import os

load_dotenv()

CHAT_ID = os.getenv("CHAT_ID")
CHANNEL_URL = os.getenv("CHANNEL_URL")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

RECORDINGS_DIR = Path("records")
CHECK_INTERVAL = 50
YTDLP_PATH = "/root/.local/bin/yt-dlp"

if not all([CHAT_ID, CHANNEL_URL, TELEGRAM_BOT_TOKEN]):
    raise RuntimeError("Missing .env variables")

RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

recording_process = None
is_recording = False
current_title = ""
offline_checks = 0


def send_telegram(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:
        r = requests.post(url, json=payload, timeout=10)

        if not r.ok:
            print(r.text)

    except Exception as e:
        print(f"[TG Error] {e}")


def get_live_info() -> dict | None:
    cmd = [
        YTDLP_PATH,
        "--print",
        "%(is_live)s|||%(id)s|||%(title)s|||%(webpage_url)s",
        "--no-warnings",
        "--no-playlist",
        "--skip-download",
        CHANNEL_URL
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            return None

        parts = result.stdout.strip().split("|||")

        if len(parts) != 4:
            return None

        if parts[0] != "True":
            return None

        return {
            "is_live": True,
            "id": parts[1],
            "title": parts[2],
            "url": parts[3]
        }

    except Exception as e:
        print(f"[Check Error] {e}")
        return None


def start_recording(info: dict):
    global recording_process, is_recording, current_title

    current_title = info["title"]

    output_template = str(
        RECORDINGS_DIR /
        "%(uploader)s" /
        "%(upload_date)s - %(title)s [%(id)s].%(ext)s"
    )

    cmd = [
        YTDLP_PATH,
        "--live-from-start",
        "--embed-metadata",
        "--write-info-json",
        "-f",
        "bestvideo+bestaudio/best",
        "--merge-output-format",
        "mkv",
        "--retries",
        "infinite",
        "--fragment-retries",
        "infinite",
        "--no-playlist",
        "--continue",
        "--no-part",
        "-o",
        output_template,
        info["url"]
    ]

    print(f"[{datetime.now()}] Starting recording: {info['title']}")

    recording_process = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT
    )

    is_recording = True

    send_telegram(
        f"🔴 <b>Стрим начался</b>\n\n"
        f"<b>{escape(info['title'])}</b>\n"
        f"{info['url']}\n\n"
        f"Запись запущена."
    )


def stop_recording():
    global recording_process, is_recording, current_title

    if recording_process and recording_process.poll() is None:
        recording_process.terminate()

        try:
            recording_process.wait(timeout=15)

        except subprocess.TimeoutExpired:
            recording_process.kill()

    send_telegram(
        f"✅ <b>Стрим закончился</b>\n\n"
        f"<b>{escape(current_title)}</b>\n"
        f"Запись сохранена."
    )

    recording_process = None
    is_recording = False
    current_title = ""

    print(f"[{datetime.now()}] Recording stopped")


def main():
    global offline_checks
    global is_recording
    global recording_process
    global current_title

    print(f"[{datetime.now()}] Monitor started for {CHANNEL_URL}")

    send_telegram("🟢 Мониторинг запущен")

    while True:
        try:
            if is_recording and recording_process.poll() is not None:
                send_telegram(
                    f"⚠️ <b>Ошибка записи</b>\n\n"
                    f"<b>{escape(current_title)}</b>\n"
                    "Процесс yt-dlp завершился."
                )

                is_recording = False
                recording_process = None
                current_title = ""

            info = get_live_info()

            if info and info["is_live"]:
                offline_checks = 0

                if not is_recording:
                    start_recording(info)

            else:
                if is_recording:
                    offline_checks += 1

                    print(
                        f"Offline check: {offline_checks}/3"
                    )

                    if offline_checks >= 3:
                        stop_recording()
                        offline_checks = 0

        except Exception as e:
            print(f"[Main Error] {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        if is_recording:
            stop_recording()

        print("\nStopped by user")