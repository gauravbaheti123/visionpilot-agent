import cv2
from ultralytics import YOLO
from datetime import datetime, timezone, timedelta
import os
import time
import threading
import urllib.request
from supabase import create_client
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIG.TXT SE READ KARO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def read_config():
    config = {}
    config_path = "C:\\VisionPilot\\config.txt"
    if not os.path.exists(config_path):
        print("❌ config.txt nahi mila!")
        input("Press Enter to exit...")
        exit()
    with open(config_path, "r") as f:
        for line in f:
            if "=" in line:
                key, value = line.strip().split("=", 1)
                config[key.strip()] = value.strip()
    return config

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AUTO UPDATER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def check_update():
    try:
        print("🔄 Checking for updates...")
        url = "https://raw.githubusercontent.com/gauravbaheti123/visionpilot-agent/refs/heads/main/visionpilot.py"
        temp_path = "C:\\VisionPilot\\visionpilot_new.py"
        urllib.request.urlretrieve(url, temp_path)
        current_size = os.path.getsize("C:\\VisionPilot\\visionpilot.py")
        new_size = os.path.getsize(temp_path)
        if new_size != current_size:
            print("✅ Update mila! Applying...")
            os.replace(temp_path, "C:\\VisionPilot\\visionpilot.py")
            print("✅ Updated! Restarting...")
            os.startfile("C:\\VisionPilot\\visionpilot.py")
            exit()
        else:
            os.remove(temp_path)
            print("✅ Already latest version!")
    except Exception as e:
        print(f"⚠️ Update check failed: {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GOOGLE DRIVE FUNCTIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CREDENTIALS_FILE = "C:\\VisionPilot\\credentials.json"

def get_drive_service():
    creds = service_account.Credentials.from_service_account_file(
        CREDENTIALS_FILE,
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=creds)

def upload_to_drive(filepath, filename, folder_id):
    try:
        service = get_drive_service()
        file_metadata = {
            "name": filename,
            "parents": [folder_id]
        }
        media = MediaFileUpload(filepath, mimetype="image/jpeg")
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id"
        ).execute()
        file_id = file.get("id")

        # Public access
        service.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"}
        ).execute()

        public_url = f"https://drive.google.com/uc?id={file_id}"
        print(f"📸 Drive upload: {public_url}")
        return public_url

    except Exception as e:
        print(f"❌ Drive upload error: {e}")
        return None

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SETUP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print("🔥 VisionPilot Starting...")
check_update()

config = read_config()
DVR_IP = config.get("DVR_IP", "")
DVR_USER = config.get("DVR_USER", "")
DVR_PASS = config.get("DVR_PASS", "")
CAMERAS_STR = config.get("CAMERAS", "1,2,3,4")
SUPABASE_URL = config.get("SUPABASE_URL", "")
SUPABASE_KEY = config.get("SUPABASE_KEY", "")
DRIVE_FOLDER_ID = config.get("DRIVE_FOLDER_ID", "")

print(f"📍 DVR: {DVR_IP}")
print(f"📹 Cameras: {CAMERAS_STR}")
print(f"📁 Drive Folder: {DRIVE_FOLDER_ID}")

CAMERAS = [
    {"id": f"CAM{c.strip()}", "channel": int(c.strip())}
    for c in CAMERAS_STR.split(",")
]

IST = timezone(timedelta(hours=5, minutes=30))
ALERT_COOLDOWN = 30
SNAPSHOT_FOLDER = "C:\\VisionPilot\\snapshots"

os.makedirs(SNAPSHOT_FOLDER, exist_ok=True)
model = YOLO("yolov8n.pt")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_rtsp(channel):
    return f"rtsp://{DVR_USER}:{DVR_PASS}@{DVR_IP}:554/cam/realmonitor?channel={channel}&subtype=1"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CAMERA THREAD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def process_camera(cam):
    cam_id = cam["id"]
    channel = cam["channel"]
    rtsp_url = get_rtsp(channel)
    last_alert_time = 0

    print(f"📷 {cam_id} Connecting...")
    cap = cv2.VideoCapture(rtsp_url)

    if not cap.isOpened():
        print(f"❌ {cam_id} Failed to connect!")
        return

    print(f"✅ {cam_id} Connected!")

    while True:
        ret, frame = cap.read()
        if not ret:
            print(f"⚠️ {cam_id} Reconnecting...")
            cap.release()
            time.sleep(5)
            cap = cv2.VideoCapture(rtsp_url)
            continue

        results = model(frame, classes=[0], verbose=False)
        count = len(results[0].boxes)
        current_time = time.time()

        if count > 0 and (current_time - last_alert_time) > ALERT_COOLDOWN:
            now_utc = datetime.now(timezone.utc)
            now_ist = now_utc.astimezone(IST)
            timestamp = now_ist.strftime("%Y%m%d_%H%M%S")

            # Snapshot locally save
            filename = f"{cam_id}_alert_{timestamp}.jpg"
            filepath = f"{SNAPSHOT_FOLDER}\\{filename}"
            cv2.imwrite(filepath, frame)

            # Drive pe upload
            drive_url = None
            if DRIVE_FOLDER_ID:
                drive_url = upload_to_drive(filepath, filename, DRIVE_FOLDER_ID)

            # Supabase mein save
            try:
                data = {
                    "camera_id": cam_id,
                    "alert_type": "person_detected",
                    "person_count": count,
                    "timestamp": now_utc.isoformat(),
                    "snapshot_url": drive_url
                }
                supabase.table("alerts").insert(data).execute()
                print(f"🚨 {cam_id} | {count} person | {now_ist.strftime('%d %b %I:%M %p IST')} | ✅ Saved!")
            except Exception as e:
                print(f"❌ Supabase error: {e}")

            last_alert_time = current_time

        cv2.imshow(f"VisionPilot - {cam_id}", frame)

    cap.release()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print(f"📹 {len(CAMERAS)} cameras starting...")

threads = []
for cam in CAMERAS:
    t = threading.Thread(target=process_camera, args=(cam,))
    t.daemon = True
    t.start()
    threads.append(t)
    time.sleep(2)

while True:
    if cv2.waitKey(1) & 0xFF == ord('q'):
        print("👋 VisionPilot Stopped!")
        break

cv2.destroyAllWindows()
