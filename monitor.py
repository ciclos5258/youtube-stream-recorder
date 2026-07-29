import subprocess
import time
import requests
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import os

load_dotenv()

# ====================== КОНФИГ ======================
CHANNEL_URL = os.getenv("CHANNEL_URL")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
RECORDINGS_DIR = Path("/records/")            # куда сохранять
CHECK_INTERVAL = 50                                     # секунд между проверками
YTDLP_PATH = "yt-dlp"                                   # или полный путь
# ====================================================

RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
recording_process = None
is_recording = False
current_title = ""

def send_telegram(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "text": text,
        "disable_web_page_preview": True
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"[TG Error] {e}")

def get_live_info() -> dict | None:
    """Возвращает информацию о стриме или None, если не live"""
    cmd = [
        YTDLP_PATH,
        "--print", "%(is_live)s|||%(id)s|||%(title)s|||%(webpage_url)s",
        "--no-warnings",
        "--skip-download",
        CHANNEL_URL
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return None
        
        line = result.stdout.strip()
        if not line or "True" not in line:
            return None
            
        parts = line.split("|||")
        if len(parts) < 4:
            return None
            
        return {
            "is_live": parts[0] == "True",
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
    output_template = str(RECORDINGS_DIR / "%(uploader)s" / "%(upload_date)s - %(title)s [%(id)s].%(ext)s")
    
    cmd = [
        YTDLP_PATH,
        "--live-from-start",
        "-f", "bestvideo+bestaudio/best",
        "--merge-output-format", "mkv",
        "--retries", "infinite",
        "--fragment-retries", "infinite",
        "--continue",
        "--no-part",
        "-o", output_template,
        info["url"]
    ]
    
    print(f"[{datetime.now()}] Starting recording: {info['title']}")
    recording_process = subprocess.Popen(cmd)
    is_recording = True
    
    send_telegram(
        f"🔴 <b>Стрим начался</b>\n\n"
        f"<b>{info['title']}</b>\n"
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
    
    is_recording = False
    send_telegram(
        f"✅ <b>Стрим закончился</b>\n\n"
        f"<b>{current_title}</b>\n"
        f"Запись сохранена."
    )
    current_title = ""
    print(f"[{datetime.now()}] Recording stopped")

def main():
    print(f"[{datetime.now()}] Monitor started for {CHANNEL_URL}")
    send_telegram("🟢 Мониторинг запущен")
    
    while True:
        try:
            info = get_live_info()
            
            if info and info["is_live"]:
                if not is_recording:
                    start_recording(info)
            else:
                if is_recording:
                    # Проверяем, жив ли ещё процесс записи
                    if recording_process and recording_process.poll() is not None:
                        # yt-dlp сам завершился
                        stop_recording()
                    else:
                        # Стрим пропал, но процесс ещё работает — даём ему время
                        pass
                        
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