import cv2
from ultralytics import YOLO
from datetime import datetime, timezone, timedelta
import os
import time
import threading
import urllib.request
import warnings
from supabase import create_client
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account

warnings.filterwarnings("ignore")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIG
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
# GOOGLE DRIVE
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
            fields="id",
            supportsAllDrives=True
        ).execute()
        file_id = file.get("id")
        service.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
            supportsAllDrives=True
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
CLIENT_ID = config.get("CLIENT_ID", "")

print(f"📍 DVR: {DVR_IP}")
print(f"📹 Cameras: {CAMERAS_STR}")
print(f"👤 Client: {CLIENT_ID}")

CAMERAS = [
    {"id": f"CAM{c.strip()}", "channel": int(c.strip())}
    for c in CAMERAS_STR.split(",")
]

IST = timezone(timedelta(hours=5, minutes=30))
SNAPSHOT_FOLDER = "C:\\VisionPilot\\snapshots"
os.makedirs(SNAPSHOT_FOLDER, exist_ok=True)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
model = YOLO("yolov8n.pt")  # Detection only

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FEATURES — GLOBAL + LOCK
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
features_lock = threading.Lock()
AFTER_HOURS = False
AFTER_HOURS_START = "21:00:00"
AFTER_HOURS_END = "09:00:00"
UNIQUE_COUNTING = False

def load_features():
    global AFTER_HOURS, AFTER_HOURS_START, AFTER_HOURS_END, UNIQUE_COUNTING
    try:
        result = supabase.table("client_features")\
            .select("*")\
            .eq("client_id", CLIENT_ID)\
            .single()\
            .execute()
        if result.data:
            with features_lock:
                AFTER_HOURS = result.data.get("after_hours", False)
                AFTER_HOURS_START = result.data.get("after_hours_start", "21:00:00")
                AFTER_HOURS_END = result.data.get("after_hours_end", "09:00:00")
                UNIQUE_COUNTING = result.data.get("unique_counting", False)
            print(f"✅ Features loaded!")
            print(f"⏰ After Hours: {AFTER_HOURS} ({AFTER_HOURS_START} - {AFTER_HOURS_END})")
            print(f"👥 Unique Count: {UNIQUE_COUNTING}")
        else:
            print("⚠️ No features found!")
    except Exception as e:
        print(f"❌ Features error: {e}")

def refresh_features():
    while True:
        time.sleep(120)
        try:
            result = supabase.table("client_features")\
                .select("*")\
                .eq("client_id", CLIENT_ID)\
                .single()\
                .execute()
            if result.data:
                global AFTER_HOURS, AFTER_HOURS_START, AFTER_HOURS_END, UNIQUE_COUNTING
                with features_lock:
                    AFTER_HOURS = result.data.get("after_hours", False)
                    AFTER_HOURS_START = result.data.get("after_hours_start", "21:00:00")
                    AFTER_HOURS_END = result.data.get("after_hours_end", "09:00:00")
                    UNIQUE_COUNTING = result.data.get("unique_counting", False)
                print(f"🔄 Features refreshed! "
                      f"After Hours: {AFTER_HOURS} "
                      f"({AFTER_HOURS_START}-{AFTER_HOURS_END})")
        except Exception as e:
            print(f"⚠️ Refresh error: {e}")

load_features()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_rtsp(channel):
    return f"rtsp://{DVR_USER}:{DVR_PASS}@{DVR_IP}:554/cam/realmonitor?channel={channel}&subtype=1"

def is_after_hours():
    with features_lock:
        start_str = AFTER_HOURS_START
        end_str = AFTER_HOURS_END
    now = datetime.now(IST).time()
    start = datetime.strptime(start_str[:5], "%H:%M").time()
    end = datetime.strptime(end_str[:5], "%H:%M").time()
    if start > end:
        return now >= start or now <= end
    return start <= now <= end

def save_alert(cam_id, alert_type, count, snapshot_url):
    try:
        now_utc = datetime.now(timezone.utc)
        now_ist = now_utc.astimezone(IST)
        data = {
            "client_id": CLIENT_ID,
            "camera_id": cam_id,
            "alert_type": alert_type,
            "person_count": count,
            "timestamp": now_utc.isoformat(),
            "snapshot_url": snapshot_url
        }
        supabase.table("alerts").insert(data).execute()
        print(f"🚨 {cam_id} | {alert_type} | "
              f"{now_ist.strftime('%d %b %I:%M %p IST')} | ✅ Saved!")
    except Exception as e:
        print(f"❌ Alert save error: {e}")

def save_unique_count(cam_id, count):
    try:
        now_utc = datetime.now(timezone.utc)
        data = {
            "client_id": CLIENT_ID,
            "camera_id": cam_id,
            "count": count,
            "timestamp": now_utc.isoformat(),
            "date": datetime.now(IST).date().isoformat()
        }
        supabase.table("unique_counts").insert(data).execute()
        print(f"👥 {cam_id} | Unique Count: {count} | ✅ Saved!")
    except Exception as e:
        print(f"❌ Unique count save error: {e}")

def take_snapshot_and_upload(frame, cam_id, alert_type):
    now_ist = datetime.now(IST)
    timestamp = now_ist.strftime("%Y%m%d_%H%M%S")
    filename = f"{cam_id}_{alert_type}_{timestamp}.jpg"
    filepath = f"{SNAPSHOT_FOLDER}\\{filename}"
    cv2.imwrite(filepath, frame)
    drive_url = None
    if DRIVE_FOLDER_ID:
        drive_url = upload_to_drive(filepath, filename, DRIVE_FOLDER_ID)
    return drive_url

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CAMERA THREAD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def process_camera(cam):
    cam_id = cam["id"]
    channel = cam["channel"]
    rtsp_url = get_rtsp(channel)

    # ⭐ Har camera ka APNA tracker model
    cam_tracker = YOLO("yolov8n.pt")

    ALERT_COOLDOWN = 300
    UNIQUE_SAVE_INTERVAL = 60
    last_alert_time = 0
    last_unique_save = time.time()
    unique_ids = set()

    print(f"📷 {cam_id} Connecting...")
    cap = cv2.VideoCapture(rtsp_url)

    if not cap.isOpened():
        print(f"❌ {cam_id} Failed!")
        return

    print(f"✅ {cam_id} Connected!")

    while True:
        ret, frame = cap.read()
        current_time = time.time()

        if not ret:
            cap.release()
            time.sleep(1)
            cap = cv2.VideoCapture(rtsp_url)
            continue

        with features_lock:
            after_hours = AFTER_HOURS
            unique_counting = UNIQUE_COUNTING

        # ━━ DETECTION
        if unique_counting:
            results = cam_tracker.track(
                frame,
                classes=[0],
                persist=True,
                verbose=False
            )
        else:
            results = model(frame, classes=[0], verbose=False)

        count = len(results[0].boxes)

        # ━━ UNIQUE COUNTING
        if unique_counting:
            if results[0].boxes.id is not None:
                track_ids = results[0].boxes.id.int().cpu().tolist()
                for tid in track_ids:
                    unique_ids.add(tid)
                print(f"👁️ {cam_id} | IDs: {track_ids} | "
                      f"Unique: {len(unique_ids)}")
            else:
                print(f"⚠️ {cam_id} | No IDs | People: {count}")

            if (current_time - last_unique_save) > UNIQUE_SAVE_INTERVAL:
                if len(unique_ids) > 0:
                    save_unique_count(cam_id, len(unique_ids))
                else:
                    print(f"⏭️ {cam_id} | Unique 0 — skip")
                last_unique_save = current_time

        # ━━ AFTER HOURS
        if after_hours and is_after_hours():
            if count > 0 and \
               (current_time - last_alert_time) > ALERT_COOLDOWN:
                drive_url = take_snapshot_and_upload(
                    frame, cam_id, "intruder"
                )
                save_alert(
                    cam_id, "after_hours_intruder",
                    count, drive_url
                )
                last_alert_time = current_time

        # ━━ DISPLAY
        cv2.putText(frame, f"{cam_id} | People: {count}",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                    0.8, (0, 255, 0), 2)

        if unique_counting:
            cv2.putText(frame,
                        f"Unique Today: {len(unique_ids)}",
                        (10, 60), cv2.FONT_HERSHEY_SIMPLEX,
                        0.8, (255, 255, 0), 2)

        if after_hours and is_after_hours():
            cv2.putText(frame, "AFTER HOURS MODE",
                        (10, 90), cv2.FONT_HERSHEY_SIMPLEX,
                        0.8, (0, 0, 255), 2)

        cv2.imshow(f"VisionPilot - {cam_id}", frame)

    cap.release()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print(f"📹 {len(CAMERAS)} cameras starting...")
print("━━━━━━━━━━━━━━━━━━━━━━━━")

refresh_thread = threading.Thread(target=refresh_features)
refresh_thread.daemon = True
refresh_thread.start()
print("🔄 Auto refresh: every 2 min")

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
