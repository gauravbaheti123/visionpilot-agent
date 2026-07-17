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
model = YOLO("yolov8n.pt")
model_tracker = YOLO("yolov8n.pt")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FEATURES FROM SUPABASE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_features():
    try:
        result = supabase.table("client_features")\
            .select("*")\
            .eq("client_id", CLIENT_ID)\
            .single()\
            .execute()
        if result.data:
            print(f"✅ Features loaded!")
            return result.data
        else:
            print("⚠️ No features found!")
            return {}
    except Exception as e:
        print(f"❌ Features error: {e}")
        return {}

features = get_features()
print(f"📋 Features: {features}")

AFTER_HOURS = features.get("after_hours", False)
AFTER_HOURS_START = features.get("after_hours_start", "21:00:00")
AFTER_HOURS_END = features.get("after_hours_end", "09:00:00")
LOITERING = features.get("loitering", False)
LOITERING_THRESHOLD = features.get("loitering_threshold", 30)
CAMERA_BLACKOUT = features.get("camera_blackout", False)
UNIQUE_COUNTING = features.get("unique_counting", False)

print(f"⏰ After Hours: {AFTER_HOURS} ({AFTER_HOURS_START} - {AFTER_HOURS_END})")
print(f"🚶 Loitering: {LOITERING} ({LOITERING_THRESHOLD}s)")
print(f"📷 Blackout: {CAMERA_BLACKOUT}")
print(f"👥 Unique Count: {UNIQUE_COUNTING}")

def get_rtsp(channel):
    return f"rtsp://{DVR_USER}:{DVR_PASS}@{DVR_IP}:554/cam/realmonitor?channel={channel}&subtype=1"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPER FUNCTIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def is_after_hours():
    now = datetime.now(IST).time()
    start = datetime.strptime(
        AFTER_HOURS_START[:5], "%H:%M").time()
    end = datetime.strptime(
        AFTER_HOURS_END[:5], "%H:%M").time()
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

def take_snapshot_and_upload(frame, cam_id, alert_type):
    now_ist = datetime.now(IST)
    timestamp = now_ist.strftime("%Y%m%d_%H%M%S")
    filename = f"{cam_id}_{alert_type}_{timestamp}.jpg"
    filepath = f"{SNAPSHOT_FOLDER}\\{filename}"
    cv2.imwrite(filepath, frame)
    drive_url = None
    if DRIVE_FOLDER_ID:
        drive_url = upload_to_drive(
            filepath, filename, DRIVE_FOLDER_ID
        )
    return drive_url

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CAMERA THREAD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def process_camera(cam):
    cam_id = cam["id"]
    channel = cam["channel"]
    rtsp_url = get_rtsp(channel)

    ALERT_COOLDOWN = 30
    BLACKOUT_COOLDOWN = 120
    BLACKOUT_THRESHOLD = 10  # 10 consecutive failures

    last_alert_time = 0
    last_blackout_alert = 0
    blackout_counter = 0
    person_first_seen = {}
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

        # ━━ BLACKOUT — CONNECTION LOST
        if not ret:
            if CAMERA_BLACKOUT:
                blackout_counter += 1
                if blackout_counter >= BLACKOUT_THRESHOLD:
                    if (current_time - last_blackout_alert) > BLACKOUT_COOLDOWN:
                        print(f"⚫ {cam_id} BLACKOUT!")
                        save_alert(
                            cam_id, "camera_blackout", 0, None
                        )
                        last_blackout_alert = current_time
                        blackout_counter = 0
            time.sleep(0.5)
            cap.release()
            cap = cv2.VideoCapture(rtsp_url)
            continue
        else:
            blackout_counter = 0

        # ━━ PERSON DETECTION
        if UNIQUE_COUNTING or LOITERING:
            results = model_tracker.track(
                frame,
                classes=[0],
                persist=True,
                verbose=False
            )
        else:
            results = model(frame, classes=[0], verbose=False)

        count = len(results[0].boxes)

        # ━━ UNIQUE COUNTING
        if UNIQUE_COUNTING and results[0].boxes.id is not None:
            track_ids = results[0].boxes.id.int().cpu().tolist()
            for tid in track_ids:
                unique_ids.add(tid)

        # ━━ AFTER HOURS
        if AFTER_HOURS and is_after_hours():
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

        # ━━ LOITERING
        if LOITERING and results[0].boxes.id is not None:
            track_ids = results[0].boxes.id.int().cpu().tolist()
            for tid in track_ids:
                if tid not in person_first_seen:
                    person_first_seen[tid] = current_time
                else:
                    duration = current_time - person_first_seen[tid]
                    if duration > LOITERING_THRESHOLD:
                        if (current_time - last_alert_time) > ALERT_COOLDOWN:
                            drive_url = take_snapshot_and_upload(
                                frame, cam_id, "loitering"
                            )
                            save_alert(
                                cam_id, "loitering_detected",
                                1, drive_url
                            )
                            last_alert_time = current_time
                            person_first_seen[tid] = current_time

            active_ids = set(
                results[0].boxes.id.int().cpu().tolist()
            ) if results[0].boxes.id is not None else set()
            person_first_seen = {
                k: v for k, v in person_first_seen.items()
                if k in active_ids
            }

        # ━━ DISPLAY
        cv2.putText(
            frame,
            f"{cam_id} | People: {count}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8, (0, 255, 0), 2
        )

        if UNIQUE_COUNTING:
            cv2.putText(
                frame,
                f"Unique Today: {len(unique_ids)}",
                (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8, (255, 255, 0), 2
            )

        if AFTER_HOURS and is_after_hours():
            cv2.putText(
                frame,
                "AFTER HOURS MODE",
                (10, 90),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8, (0, 0, 255), 2
            )

        cv2.imshow(f"VisionPilot - {cam_id}", frame)

    cap.release()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print(f"📹 {len(CAMERAS)} cameras starting...")
print("━━━━━━━━━━━━━━━━━━━━━━━━")

threads = []
for cam in CAMERAS:
    t = threading.Thread(
        target=process_camera, args=(cam,)
    )
    t.daemon = True
    t.start()
    threads.append(t)
    time.sleep(2)

while True:
    if cv2.waitKey(1) & 0xFF == ord('q'):
        print("👋 VisionPilot Stopped!")
        break

cv2.destroyAllWindows()
