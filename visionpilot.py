import cv2
from ultralytics import YOLO
from datetime import datetime, timezone, timedelta
import os
import time
import threading
from supabase import create_client

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIG
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SUPABASE_URL = "https://wgbwtlhmsuxfwhgcdrhg.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6IndnYnd0bGhtc3V4ZndoZ2NkcmhnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODQxOTUzMTIsImV4cCI6MjA5OTc3MTMxMn0.79cTkeuKYB3jJ9gkme97rBC2J-llZUU3y7ILqcHYXVc"

IST = timezone(timedelta(hours=5, minutes=30))
ALERT_COOLDOWN = 30
SNAPSHOT_FOLDER = "snapshots"

DVR_IP = "192.168.29.108"
DVR_USER = "GAURAV"
DVR_PASS = "Gaurav1234"

CAMERAS = [
    {"id": "CAM1", "channel": 1},
    {"id": "CAM2", "channel": 2},
    {"id": "CAM3", "channel": 3},
    {"id": "CAM4", "channel": 4},
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SETUP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
os.makedirs(SNAPSHOT_FOLDER, exist_ok=True)
model = YOLO('yolov8n.pt')
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

    print(f"📷 {cam_id} — Connecting...")
    cap = cv2.VideoCapture(rtsp_url)

    if not cap.isOpened():
        print(f"❌ {cam_id} — Failed to connect!")
        return

    print(f"✅ {cam_id} — Connected!")

    while True:
        ret, frame = cap.read()

        if not ret:
            print(f"⚠️ {cam_id} — Lost connection, reconnecting...")
            cap.release()
            time.sleep(5)
            cap = cv2.VideoCapture(rtsp_url)
            continue

        # Detection
        results = model(frame, classes=[0], verbose=False)
        count = len(results[0].boxes)
        current_time = time.time()

        if count > 0 and (current_time - last_alert_time) > ALERT_COOLDOWN:
            now_ist = datetime.now(IST)
            timestamp = now_ist.strftime("%Y%m%d_%H%M%S")

            # Snapshot save
            filename = f"{SNAPSHOT_FOLDER}/{cam_id}_alert_{timestamp}.jpg"
            cv2.imwrite(filename, frame)

            # Supabase push
            try:
                data = {
                    "camera_id": cam_id,
                    "alert_type": "person_detected",
                    "person_count": count,
                    "timestamp": now_ist.isoformat()
                }
                supabase.table("alerts").insert(data).execute()
                print(f"🚨 {cam_id} | Person: {count} | {now_ist.strftime('%d %b %I:%M %p IST')} | ✅ Saved!")
            except Exception as e:
                print(f"❌ {cam_id} Supabase error: {e}")

            last_alert_time = current_time

        # Live window
        cv2.imshow(f"VisionPilot - {cam_id}", frame)

    cap.release()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print("🔥 VisionPilot Starting...")
print(f"📹 {len(CAMERAS)} Cameras configured")
print("━━━━━━━━━━━━━━━━━━━━━━━━")

# Har camera ke liye alag thread
threads = []
for cam in CAMERAS:
    t = threading.Thread(target=process_camera, args=(cam,))
    t.daemon = True
    t.start()
    threads.append(t)
    time.sleep(2)  # Cameras ek ek start ho

# Live windows ke liye
while True:
    if cv2.waitKey(1) & 0xFF == ord('q'):
        print("👋 VisionPilot Stopped!")
        break

cv2.destroyAllWindows()