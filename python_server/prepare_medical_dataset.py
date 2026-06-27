import os
import sys
import time
import shutil
import urllib.request
import subprocess
import numpy as np

# 1. Auto-resolve missing dependencies
required_packages = ["selenium", "mediapipe", "opencv-python", "numpy", "undetected-chromedriver"]
for pkg in required_packages:
    import_name = "cv2" if pkg == "opencv-python" else pkg.replace("-", "_")
    try:
        __import__(import_name)
    except ImportError:
        print(f"[!] Installing missing dependency: {pkg}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

import cv2
import mediapipe as mp
import undetected_chromedriver as uc
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

# 2. Vocabulary configurations
MEDICAL_WORDS = [
    "ACCIDENT", "ALLERGY", "AMBULANCE", "APPOINTMENT", "ASTHMA", 
    "BANDAGE", "BLOOD", "BURN", "CANCER", "CAPSULE", 
    "CHECK", "CLINIC", "COLD", "COUGH", "DENTIST", 
    "DIABETES", "DISEASE", "DIZZY", "DOCTOR", "FATHER", 
    "FEVER", "FIRSTAID", "FRACTURE", "HEADACHE", "HEALTH", 
    "HELLO", "HOSPITAL", "I", "INFECTION", "INJECTION", 
    "INSURANCE", "MALARIA", "MEASLES", "MEDICINE", "MOTHER", 
    "NURSE", "OPERATION", "PAIN", "PARALYSIS", "PATIENT", 
    "PHARMACY", "PRESCRIPTION", "PULSE", "SWELLING", "SYMPTOM", 
    "TABLET", "THANKYOU", "TREATMENT", "VACCINE", "YOU"
]

DATA_DIR = "data_sequences"
if not os.path.exists(DATA_DIR) and os.path.exists(os.path.join("python_server", DATA_DIR)):
    DATA_DIR = os.path.join("python_server", DATA_DIR)

HAND_MODEL_PATH = "hand_landmarker.task"
POSE_MODEL_PATH = "pose_landmarker.task"

if not os.path.exists(HAND_MODEL_PATH) and os.path.exists(os.path.join("python_server", HAND_MODEL_PATH)):
    HAND_MODEL_PATH = os.path.join("python_server", HAND_MODEL_PATH)
if not os.path.exists(POSE_MODEL_PATH) and os.path.exists(os.path.join("python_server", POSE_MODEL_PATH)):
    POSE_MODEL_PATH = os.path.join("python_server", POSE_MODEL_PATH)

TEMP_VIDEO_PATH = "temp_downloaded_video.mp4"
if os.path.exists("python_server"):
    TEMP_VIDEO_PATH = os.path.join("python_server", TEMP_VIDEO_PATH)

# Ensure data sequences folder exists
os.makedirs(DATA_DIR, exist_ok=True)


# 3. Spatial Normalization Engine Functions
def forward_fill_sequence(sequence):
    """
    Fills missing coordinate tracking dropouts (represented as zero sub-vectors) 
    using forward-fill (and back-fill for initial empty frames).
    """
    L = len(sequence)
    filled = sequence.copy()
    
    # 138-dimensional vector map:
    # 0 to 12: Pose landmarks (shoulders + elbows)
    # 12 to 75: Left Hand landmarks (21 * 3 = 63 values)
    # 75 to 138: Right Hand landmarks (21 * 3 = 63 values)
    groups = [
        ("pose", 0, 12),
        ("left_hand", 12, 75),
        ("right_hand", 75, 138)
    ]
    
    for name, start, end in groups:
        # Find first valid frame for this joint/limb group
        first_valid_idx = -1
        for i in range(L):
            if np.any(np.abs(filled[i, start:end]) > 1e-5):
                first_valid_idx = i
                break
                
        if first_valid_idx == -1:
            # Entire sequence for this limb is zero (absent limb is kept zero)
            continue
            
        # Back-fill empty frames before the first valid frame
        for i in range(first_valid_idx):
            filled[i, start:end] = filled[first_valid_idx, start:end]
            
        # Forward-fill subsequent empty frames with the last known valid landmarks
        last_valid = filled[first_valid_idx, start:end].copy()
        for i in range(first_valid_idx + 1, L):
            if np.any(np.abs(filled[i, start:end]) > 1e-5):
                last_valid = filled[i, start:end].copy()
            else:
                filled[i, start:end] = last_valid
                
    return filled


def transform_to_relative_skeleton(filled_sequence):
    """
    Applies torso origin subtraction and converts absolute positions into relative direction vectors:
    - Shoulders relative to the shoulder midpoint origin (S_mid).
    - Elbows relative to shoulders.
    - Wrists (landmark 0) relative to elbows.
    - Fingers (landmarks 1 to 20) relative to wrists.
    """
    L = len(filled_sequence)
    transformed = np.zeros_like(filled_sequence)
    
    for f in range(L):
        frame = filled_sequence[f]
        
        # 1. Pose Joints
        s_l = frame[0:3]
        s_r = frame[3:6]
        e_l = frame[6:9]
        e_r = frame[9:12]
        
        # Calculate torso origin midpoint
        s_mid = (s_l + s_r) / 2.0
        
        # Shoulders relative to S_mid
        transformed[f, 0:3] = s_l - s_mid
        transformed[f, 3:6] = s_r - s_mid
        
        # Elbows relative to shoulders
        transformed[f, 6:9] = e_l - s_l
        transformed[f, 9:12] = e_r - s_r
        
        # 2. Left Hand
        left_hand_valid = np.any(np.abs(frame[12:75]) > 1e-5)
        if left_hand_valid:
            w_l = frame[12:15]
            # Wrist relative to left elbow
            transformed[f, 12:15] = w_l - e_l
            # Fingers relative to Wrist
            for i in range(1, 21):
                idx = 12 + i * 3
                transformed[f, idx : idx + 3] = frame[idx : idx + 3] - w_l
        else:
            transformed[f, 12:75] = 0.0
            
        # 3. Right Hand
        right_hand_valid = np.any(np.abs(frame[75:138]) > 1e-5)
        if right_hand_valid:
            w_r = frame[75:78]
            # Wrist relative to right elbow
            transformed[f, 75:78] = w_r - e_r
            # Fingers relative to Wrist
            for i in range(1, 21):
                idx = 75 + i * 3
                transformed[f, idx : idx + 3] = frame[idx : idx + 3] - w_r
        else:
            transformed[f, 75:138] = 0.0
            
    return transformed


def interpolate_sequence(sequence, target_len=45):
    """
    Standardizes sequence frames to target_len (45 frames) using linear interpolation.
    """
    curr_len = len(sequence)
    if curr_len == 0:
        return np.zeros((target_len, 138), dtype=np.float32)
    if curr_len == target_len:
        return np.array(sequence, dtype=np.float32)
        
    sequence = np.array(sequence, dtype=np.float32)
    new_indices = np.linspace(0, curr_len - 1, target_len)
    interpolated = np.zeros((target_len, 138), dtype=np.float32)
    
    for i in range(138):
        interpolated[:, i] = np.interp(new_indices, np.arange(curr_len), sequence[:, i])
        
    return interpolated


# 4. MediaPipe Landmark Extractor
def extract_coordinates(video_path, hand_detector, pose_detector):
    """
    Loads video, flips frames horizontally (domain-matching webcam selfie-view),
    extracts coordinates, and structures them into a list of 138-dimensional vectors.
    """
    cap = cv2.VideoCapture(video_path)
    sequence = []
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
            
        # Mirror horizontally to align with the Flutter application's camera feed
        frame = cv2.flip(frame, 1)
        h, w, c = frame.shape
        
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        
        pose_results = pose_detector.detect(mp_image)
        hand_results = hand_detector.detect(mp_image)
        
        pose_coords = [0.0] * 12
        left_hand_coords = [0.0] * 63
        right_hand_coords = [0.0] * 63
        
        # 1. Pose Joints
        if pose_results.pose_landmarks and len(pose_results.pose_landmarks) > 0:
            landmarks = pose_results.pose_landmarks[0]
            left_shoulder = landmarks[11]
            right_shoulder = landmarks[12]
            left_elbow = landmarks[13]
            right_elbow = landmarks[14]
            
            pose_coords[0:3] = [left_shoulder.x, left_shoulder.y, left_shoulder.z]
            pose_coords[3:6] = [right_shoulder.x, right_shoulder.y, right_shoulder.z]
            pose_coords[6:9] = [left_elbow.x, left_elbow.y, left_elbow.z]
            pose_coords[9:12] = [right_elbow.x, right_elbow.y, right_elbow.z]
            
        # 2. Hand Joints
        if hand_results.hand_landmarks:
            for hand_idx, hand_lms in enumerate(hand_results.hand_landmarks):
                hand_label = hand_results.handedness[hand_idx][0].category_name
                
                hand_coords = []
                for lm in hand_lms:
                    hand_coords.extend([lm.x, lm.y, lm.z])
                    
                if hand_label == "Left":
                    left_hand_coords = hand_coords
                elif hand_label == "Right":
                    right_hand_coords = hand_coords
                    
        frame_features = pose_coords + left_hand_coords + right_hand_coords
        sequence.append(frame_features)
        
    cap.release()
    return sequence


def check_and_wait_for_cloudflare(driver):
    """
    Checks if the page is currently displaying a Cloudflare challenge page 
    (Turnstile or 'Just a moment...') and blocks until it is cleared.
    """
    # Wait a moment for the browser to transition the title state from the previous page
    time.sleep(2)
    
    is_cf = False
    title = ""
    # Try multiple times to read the title in case of redirects
    for _ in range(6):
        try:
            title = driver.title.lower()
            if "just a moment" in title or "cloudflare" in title or "checking your browser" in title:
                is_cf = True
                break
        except Exception:
            pass
        time.sleep(0.5)
 
    if is_cf:
        print("[!] Stuck on Cloudflare verification page. Please click the checkbox / solve Turnstile in Chrome...")
        start_time = time.time()
        while True:
            time.sleep(1)
            try:
                title = driver.title.lower()
                if "just a moment" not in title and "cloudflare" not in title and "checking your browser" not in title:
                    print("[OK] Cloudflare verification bypassed!")
                    # Give it a short moment to finish redirecting
                    time.sleep(3)
                    break
            except Exception:
                pass
            if time.time() - start_time > 60:
                print("[!] Warning: Cloudflare bypass wait timed out (60s). Proceeding anyway...")
                break

# 5. Targeted Web Scraper using Headed Selenium
def scrape_video_url(driver, word):
    """
    Automates search query, parses results, navigates to details, 
    and extracts video source.
    """
    search_url = f"https://indiansignlanguage.org/?s={word.lower()}"
    print(f"[*] Navigating search query: {search_url}")
    driver.get(search_url)
    check_and_wait_for_cloudflare(driver)
    time.sleep(2)
    
    # Locate matching post detail pages
    detail_url = None
    try:
        # Strategy A: Standard post headings
        link_elements = driver.find_elements(By.CSS_SELECTOR, "h2.entry-title a, h1.entry-title a, article h2 a, .post h2 a, h2 a")
        for link in link_elements:
            href = link.get_attribute("href")
            text = link.text.upper().strip()
            if href and text and (word in text or text in word) and "/category/" not in href and "/tag/" not in href:
                detail_url = href
                break
    except Exception:
        pass
        
    if not detail_url:
        # Strategy B: Generic anchor tags matching word text or URL subpath
        try:
            links = driver.find_elements(By.TAG_NAME, "a")
            for link in links:
                href = link.get_attribute("href")
                text = link.text.upper().strip()
                if href and (word in text or (text and text in word) or word.lower() in href.lower()):
                    if any(x in href for x in ["/?s=", "/category/", "/tag/", "/author/", "/page/"]):
                        continue
                    detail_url = href
                    break
        except Exception:
            pass
            
    if not detail_url:
        print(f"[-] No direct search result match found for word: '{word}'")
        return None
        
    print(f"[OK] Found sign detail page: {detail_url}")
    driver.get(detail_url)
    check_and_wait_for_cloudflare(driver)
    time.sleep(2)
    
    video_url = None
    # Strategy A: Native HTML5 <video> elements
    try:
        video_elem = driver.find_element(By.TAG_NAME, "video")
        src = video_elem.get_attribute("src")
        if src and (".mp4" in src.lower() or "uploads" in src.lower()):
            video_url = src
        else:
            sources = video_elem.find_elements(By.TAG_NAME, "source")
            for src_elem in sources:
                src = src_elem.get_attribute("src")
                if src and ".mp4" in src.lower():
                    video_url = src
                    break
    except Exception:
        pass
        
    # Strategy B: Anchor links directly pointing to video assets
    if not video_url:
        try:
            links = driver.find_elements(By.TAG_NAME, "a")
            for link in links:
                href = link.get_attribute("href")
                if href and ".mp4" in href.lower() and "uploads" in href.lower():
                    video_url = href
                    break
        except Exception:
            pass
            
    # Strategy C: embedded iframe players (Youtube fallback)
    if not video_url:
        try:
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            for iframe in iframes:
                src = iframe.get_attribute("src")
                if src and ("youtube.com" in src or "youtu.be" in src):
                    video_url = src
                    break
        except Exception:
            pass
            
    return video_url


def download_file(url, target_path):
    """Downloads files with User-Agent custom headers to bypass forbidden errors."""
    print(f"[*] Downloading file asset from: {url}")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as response, open(target_path, 'wb') as out_file:
        out_file.write(response.read())


# 6. Main Orchestrator
def process_word(word, driver, hand_detector, pose_detector):
    """Scrapes, processes, normalizes and serializes a sign word."""
    word_dir = os.path.join(DATA_DIR, word)
    
    # 1. Scrape video URL
    video_url = scrape_video_url(driver, word)
    if not video_url:
        print(f"[!] Skipping '{word}': Video asset URL could not be resolved.")
        return False
        
    # 2. Download video file
    try:
        if TEMP_VIDEO_PATH and os.path.exists(TEMP_VIDEO_PATH):
            os.remove(TEMP_VIDEO_PATH)
            
        if "youtube.com" in video_url or "youtu.be" in video_url:
            print(f"[*] '{word}' is hosted on YouTube. Downloading via yt-dlp...")
            cmd = [
                sys.executable, "-m", "yt_dlp",
                "-f", "b[ext=mp4]",
                "-o", TEMP_VIDEO_PATH,
                "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
                "--referer", "https://indiansignlanguage.org/",
                video_url
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                print(f"[-] yt-dlp failed to download YouTube video: {res.stderr}")
                return False
        else:
            download_file(video_url, TEMP_VIDEO_PATH)
    except Exception as e:
        print(f"[-] Failed to download video for '{word}': {e}")
        return False
        
    # 3. Extract Raw Coordinates
    print(f"[*] Extracting landmarks using MediaPipe Tasks API...")
    raw_sequence = extract_coordinates(TEMP_VIDEO_PATH, hand_detector, pose_detector)
    
    if len(raw_sequence) == 0:
        print(f"[-] Error: MediaPipe failed to extract any coordinates from video for '{word}'")
        return False
        
    raw_arr = np.array(raw_sequence, dtype=np.float32)
    print(f"  Extracted raw sequence shape: {raw_arr.shape}")
    
    # 4. Spatial Normalization Engine Pipeline
    print(f"[*] Normalizing sequence coordinates...")
    # Step A: Apply forward-fill to fix track drops
    filled_sequence = forward_fill_sequence(raw_arr)
    # Step B: Apply torso centering & joint relative conversion
    normalized_sequence = transform_to_relative_skeleton(filled_sequence)
    # Step C: Standardize sequence frame length to 45
    final_sequence = interpolate_sequence(normalized_sequence, target_len=45)
    
    # 5. Serialize array
    os.makedirs(word_dir, exist_ok=True)
    target_npy_path = os.path.join(word_dir, "sample_0.npy")
    np.save(target_npy_path, final_sequence)
    print(f"[OK] Saved standardized coordinate array to: {target_npy_path} (shape: {final_sequence.shape})")
    
    # Cleanup temp file
    if os.path.exists(TEMP_VIDEO_PATH):
        os.remove(TEMP_VIDEO_PATH)
        
    return True


def run_pipeline(single_word_test=None):
    print("====================================================")
    print("      ISL 50-WORD MEDICAL SIGN PREPARATION PIPELINE ")
    print("====================================================")
    
    # Validate MediaPipe models are present
    if not os.path.exists(HAND_MODEL_PATH) or not os.path.exists(POSE_MODEL_PATH):
        print(f"[-] Error: MediaPipe model files '{HAND_MODEL_PATH}' or '{POSE_MODEL_PATH}' not found.")
        print("[-] Please ensure task models are located in python_server folder.")
        return
        
    # Initialize MediaPipe landmarker options
    print("[*] Initializing MediaPipe landmarker tasks...")
    hand_options = vision.HandLandmarkerOptions(
        base_options=python.BaseOptions(model_asset_path=HAND_MODEL_PATH),
        num_hands=2,
        running_mode=vision.RunningMode.IMAGE
    )
    pose_options = vision.PoseLandmarkerOptions(
        base_options=python.BaseOptions(model_asset_path=POSE_MODEL_PATH),
        running_mode=vision.RunningMode.IMAGE
    )
    hand_detector = vision.HandLandmarker.create_from_options(hand_options)
    pose_detector = vision.PoseLandmarker.create_from_options(pose_options)
    print("[OK] MediaPipe landmarker detectors initialized.")
    
def init_driver(detected_version, chrome_profile_dir):
    """Initializes headed Chrome browser via undetected-chromedriver."""
    print("[*] Launching headed Chrome browser via undetected-chromedriver...")
    chrome_options = uc.ChromeOptions()
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--disable-gpu")
    
    driver = uc.Chrome(
        version_main=detected_version,
        options=chrome_options,
        user_data_dir=chrome_profile_dir
    )
    
    # Open home page to allow human challenge bypass
    print("[*] Opening base dictionary portal...")
    try:
        driver.get("https://indiansignlanguage.org/")
        check_and_wait_for_cloudflare(driver)
    except Exception as e:
        print(f"[-] Warning during portal initialization: {e}")
    return driver


def run_pipeline(single_word_test=None):
    print("====================================================")
    print("      ISL 50-WORD MEDICAL SIGN PREPARATION PIPELINE ")
    print("====================================================")
    
    # Validate MediaPipe models are present
    if not os.path.exists(HAND_MODEL_PATH) or not os.path.exists(POSE_MODEL_PATH):
        print(f"[-] Error: MediaPipe model files '{HAND_MODEL_PATH}' or '{POSE_MODEL_PATH}' not found.")
        print("[-] Please ensure task models are located in python_server folder.")
        return
        
    # Initialize MediaPipe landmarker options
    print("[*] Initializing MediaPipe landmarker tasks...")
    hand_options = vision.HandLandmarkerOptions(
        base_options=python.BaseOptions(model_asset_path=HAND_MODEL_PATH),
        num_hands=2,
        running_mode=vision.RunningMode.IMAGE
    )
    pose_options = vision.PoseLandmarkerOptions(
        base_options=python.BaseOptions(model_asset_path=POSE_MODEL_PATH),
        running_mode=vision.RunningMode.IMAGE
    )
    hand_detector = vision.HandLandmarker.create_from_options(hand_options)
    pose_detector = vision.PoseLandmarker.create_from_options(pose_options)
    print("[OK] MediaPipe landmarker detectors initialized.")
    
    # Detect Chrome Major Version
    import winreg
    detected_version = None
    try:
        paths = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
            r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"
        ]
        for path in paths:
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path)
                val, _ = winreg.QueryValueEx(key, "")
                dir_path = os.path.dirname(val)
                for item in os.listdir(dir_path):
                    if item[0].isdigit() and os.path.isdir(os.path.join(dir_path, item)):
                        detected_version = int(item.split('.')[0])
                        break
                if detected_version:
                    break
            except Exception:
                pass
    except Exception:
        pass

    if detected_version:
        print(f"[OK] Programmatically detected Chrome Major Version: {detected_version}")
    else:
        print("[!] Warning: Could not detect Chrome version. Defaulting to 149.")
        detected_version = 149

    # Setup persistent profile directory
    chrome_profile_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "chrome_profile"))
    os.makedirs(chrome_profile_dir, exist_ok=True)
    print(f"[*] Using persistent Chrome profile: {chrome_profile_dir}")

    driver = init_driver(detected_version, chrome_profile_dir)
        
    # Choose list to process
    words_to_process = [single_word_test.upper()] if single_word_test else MEDICAL_WORDS
    
    success_count = 0
    failed_words = []
    
    try:
        for idx, word in enumerate(words_to_process):
            print(f"\n----------------------------------------------------")
            print(f"Processing word [{idx+1}/{len(words_to_process)}]: '{word}'")
            print(f"----------------------------------------------------")
            
            # 1. Skip if already processed successfully (resumability)
            word_dir = os.path.join(DATA_DIR, word)
            if os.path.exists(os.path.join(word_dir, "sample_0.npy")):
                print(f"[OK] Word '{word}' already processed successfully. Skipping.")
                success_count += 1
                continue
                
            # 2. Session liveness check & recovery
            try:
                _ = driver.current_url
            except Exception:
                print("[!] Browser session lost or closed. Recreating driver session...")
                try:
                    driver.quit()
                except Exception:
                    pass
                driver = init_driver(detected_version, chrome_profile_dir)
                
            # 3. Process the word inside error isolation block
            try:
                success = process_word(word, driver, hand_detector, pose_detector)
            except Exception as e:
                print(f"[-] Unhandled exception processing word '{word}': {e}")
                success = False
                
            if success:
                success_count += 1
            else:
                failed_words.append(word)
                
            # Sleep 3 seconds between requests to prevent server ban/throttling
            time.sleep(3)
    finally:
        try:
            driver.quit()
        except Exception:
            pass
        print("\n====================================================")
        print("                 PIPELINE COMPLETED                 ")
        print("====================================================")
        print(f"Successfully processed: {success_count}/{len(words_to_process)} words.")
        if failed_words:
            print(f"Failed / Skipped words: {failed_words}")
        print("====================================================\n")


if __name__ == "__main__":
    # If a command line argument is provided, run as single word test.
    # E.g. python prepare_medical_dataset.py BANDAGE
    test_word = sys.argv[1] if len(sys.argv) > 1 else None
    run_pipeline(test_word)
