from imapclient import IMAPClient
import ssl
import email
from email.header import decode_header
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone, timedelta
import requests
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
import shutil
import time

# ------------------- CONFIGURATION ------------------- #
UTC_PLUS_9 = timezone(timedelta(hours=9))
IMAP_SERVER = 'mail.bps.go.id'
SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.set_ciphers('DEFAULT@SECLEVEL=1')
WHATSAPP_API = "http://localhost:4000/"
LAST_TIME_FILE = Path("last_time.json")

# ------------------- LOGGING FUNCTION ------------------- #
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "email_checker.log"
LOG_DIR.mkdir(exist_ok=True)

ATTACHMENTS_DIR = Path("attachments")
ATTACHMENTS_DIR.mkdir(exist_ok=True)

def write_log(message: str):
    timestamp = datetime.now(UTC_PLUS_9).strftime("%Y-%m-%d %H:%M:%S")
    full_msg = f"[{timestamp}] {message}"
    print(full_msg)
    with open(LOG_FILE, "a", encoding="utf-8") as logf:
        logf.write(full_msg + "\n")

# ------------------- LOAD CONFIG ------------------- #
with open('config.json', 'r') as f:
    accounts = json.load(f)

from threading import Lock
last_time_lock = Lock()

if LAST_TIME_FILE.exists():
    with last_time_lock:  # 🛡️ Tambahkan Lock di sini
        with open(LAST_TIME_FILE, 'r') as f:
            last_time = json.load(f)
else:
    last_time = {}

def save_last_time():
    temp_file = LAST_TIME_FILE.with_suffix(".tmp")
    with open(temp_file, 'w') as f:
        json.dump(last_time, f, indent=4)
    shutil.move(temp_file, LAST_TIME_FILE)

def get_last_key(email, folder):
    return f"{email}|{folder}"

def send_whatsapp(group_id, message):
    payload = {
        "chatId": group_id,
        "message": message
    }
    try:
        # Benar: arahkan ke endpoint sesuai backend
        response = requests.post(f"{WHATSAPP_API.rstrip('/')}/send", json=payload)
        write_log(f"✅ WhatsApp Response: {response.status_code} - {response.text}")
    except Exception as e:
        write_log(f"❌ WhatsApp send failed: {e}")

def save_attachment(part, uid):
    filename_raw = part.get_filename()
    if not filename_raw:
        return None

    filename_raw, enc = decode_header(filename_raw)[0]
    filename = filename_raw.decode(enc or "utf-8") if isinstance(filename_raw, bytes) else filename_raw
    timestamp = datetime.now(UTC_PLUS_9).strftime("%Y%m%d%H%M%S")
    filename = f"{timestamp}_UID{uid}_{filename}"

    payload = part.get_payload(decode=True)
    if isinstance(payload, bytes):
        filepath = ATTACHMENTS_DIR / filename
        with open(filepath, "wb") as f:
            f.write(payload)
        return str(filepath)
    else:
        write_log(f"⚠️ Attachment payload for {filename} is not bytes, skipped.")
        return None

def process_folder(server, account, folder, target_type):

    try:
        server.select_folder(folder, readonly=True)
    except Exception as e:
        write_log(f"⚠️ Cannot access folder '{folder}' on {account['email']}: {e}")
        return

    # 🔧 Taruh di sini: ambil last_dt dari last_time.json
    key = get_last_key(account['email'], folder)
    with last_time_lock:
        last_dt_str = last_time.get(key, "2000-01-01 00:00:00")
    last_dt = datetime.strptime(last_dt_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC_PLUS_9)

    try:
        messages = server.search(['SINCE', last_dt.date()])
        write_log(f"📌 {len(messages)} messages SINCE {last_dt.date()} in '{folder}'")
    except Exception as e:
        write_log(f"⚠️ Search failed in '{folder}': {e}")
        return

    for uid in messages:
        try:
            raw = server.fetch([uid], ['BODY.PEEK[]'])
            raw_msg = raw[uid].get(b'BODY.PEEK[]') or raw[uid].get(b'BODY[]')
            if not isinstance(raw_msg, (bytes, bytearray)):
                continue

            msg = email.message_from_bytes(raw_msg)
            subject_parts = decode_header(msg.get("Subject") or "")
            subject = ""
            for part, enc in subject_parts:
                if isinstance(part, bytes):
                    part = part.decode(enc or "utf-8", errors="ignore")
                subject += part

            from_ = msg.get("From")
            date_raw = msg.get("Date")
            if not date_raw:
                write_log(f"⚠️ Email has no Date header, skipping UID {uid}")
                continue

            date_tuple = parsedate_to_datetime(date_raw)
            if date_tuple.tzinfo is None:
                date_tuple = date_tuple.replace(tzinfo=UTC_PLUS_9)

            key = get_last_key(account['email'], folder)
            last_dt_str = last_time.get(key, "2000-01-01 00:00:00")
            last_dt = datetime.strptime(last_dt_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC_PLUS_9)
            write_log(f"🕒 Email UID {uid} Date: {date_tuple}, Last time: {last_dt}")
            if date_tuple <= last_dt:
                continue

            body = ""
            attachments_info = []
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    disp = str(part.get("Content-Disposition"))
                    if "attachment" in disp:
                        saved_file = save_attachment(part, uid)
                        if saved_file:
                            attachments_info.append(saved_file)

                    if content_type == "text/plain" and "attachment" not in disp:
                        body_bytes = part.get_payload(decode=True)
                        if isinstance(body_bytes, bytes):
                            body = body_bytes.decode(errors='ignore').strip()
            else:
                body_bytes = msg.get_payload(decode=True)
                if isinstance(body_bytes, bytes):
                    body = body_bytes.decode(errors='ignore').strip()

            body_clean = "\n".join([line.strip() for line in body.splitlines() if line.strip()])
            if len(body_clean) > 1000:
                body_clean = body_clean[:1000] + "..."
            if not body_clean:
                body_clean = "[No Text Content]"

            attachment_text = "\n📎 *Attachments:* " + ", ".join(attachments_info) if attachments_info else ""
            wa_message = f"""📩 *New Email Received!*
📁 *Folder:* {folder}      

📥 *From:* {from_}
📝 *Subject:* {subject}
📅 *Date:* {date_tuple.astimezone(UTC_PLUS_9).strftime('%Y-%m-%d %H:%M:%S')}{attachment_text}
📰 *Message:*
{body_clean}
"""

            write_log(f"📲 Sending WhatsApp:\n{wa_message}")
            target_chat_id = account['personal_id'] if target_type == "personal" else account['group_id']
            send_whatsapp(target_chat_id, wa_message)
            # Kirim file satu per satu ke WhatsApp
            for file_path in attachments_info:
                try:
                    with open(file_path, "rb") as f:
                        files = {"file": f}
                        data = {"chatId": target_chat_id}
                        response = requests.post(f"{WHATSAPP_API}/file", data=data, files=files)
                        write_log(f"📎 Sent file {file_path}: {response.status_code} - {response.text}")
                except Exception as e:
                    write_log(f"❌ Failed to send file {file_path}: {e}")
                try:
                    os.remove(file_path)
                    write_log(f"🗑️ Deleted local file: {file_path}")
                except Exception as e:
                    write_log(f"⚠️ Failed to delete {file_path}: {e}")
            with last_time_lock:
                last_time[key] = date_tuple.astimezone(UTC_PLUS_9).strftime("%Y-%m-%d %H:%M:%S")
                write_log(f"🕓 Updated last_time[{key}] = {last_time[key]}")
                save_last_time()

        except Exception as e:
            write_log(f"❌ Error reading message {uid} in {folder}: {e}")

def process_email(account):
    write_log(f"📧 Connecting to {account['email']}")
    retries = 0
    heartbeat_timer = time.time()  # ⬅️ STEP 3: Heartbeat init

    while True:
        try:
            with IMAPClient(IMAP_SERVER, ssl=True, ssl_context=SSL_CONTEXT) as server:
                server.login(account['email'], account['password'])
                write_log(f"✅ Logged in: {account['email']}")
                retries = 0

                while True:
                    for folder_config in account.get("folders", []):
                        folder = folder_config["name"]
                        target_type = folder_config.get("target", "group")

                        write_log(f"📂 [START] Checking folder '{folder}' for {account['email']}")  # ⬅️ STEP 1

                        try:
                            server.select_folder(folder, readonly=True)
                            process_folder(server, account, folder, target_type)

                            write_log(f"🕓 Entering IDLE for '{folder}' on {account['email']}")  # ⬅️ STEP 2
                            try:
                                server.idle()
                                try:
                                    responses = server.idle_check(timeout=60)
                                except Exception as e:
                                    write_log(f"⚠️ IDLE check failed in '{folder}': {e}")
                                    try: server.idle_done()
                                    except Exception: pass
                                    raise e
                                try: server.idle_done()
                                except Exception: pass

                                if not responses:  # ⬅️ STEP 2
                                    write_log(f"💤 No activity detected during IDLE for '{folder}' on {account['email']}")
                                    
                                write_log(f"🔍 IDLE response for '{folder}': {responses}")
                                if responses:
                                    process_folder(server, account, folder, target_type)

                            except Exception as e:
                                write_log(f"⚠️ IDLE failed in '{folder}': {e}")
                                if 'SSL' in str(e) or 'EOF' in str(e) or 'socket' in str(e).lower():
                                    raise e
                                continue

                            time.sleep(1.5)

                        except Exception as e:
                            write_log(f"⚠️ IDLE error in folder '{folder}': {e}")
                            if 'SSL' in str(e) or 'EOF' in str(e) or 'socket' in str(e).lower():
                                raise e
                            continue

                        write_log(f"📂 [END] Finished folder '{folder}' for {account['email']}")  # ⬅️ STEP 1

                    # ⬅️ STEP 3: Heartbeat setiap 5 menit
                    if time.time() - heartbeat_timer > 300:
                        write_log(f"❤️ Heartbeat: {account['email']} still active and looping")
                        heartbeat_timer = time.time()

        except Exception as e:
            retries += 1
            wait_time = max(90, min(600, 20 * retries))
            write_log(f"❌ Error on {account['email']}, reconnecting in {wait_time}s: {e}")
            time.sleep(wait_time)

# ------------------- MAIN EXECUTION ------------------- #
if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=len(accounts)) as executor:
        for account in accounts:
            executor.submit(process_email, account)
