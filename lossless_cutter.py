import cv2
import numpy as np
import subprocess
import os
import sys
import math
import uuid
import glob
import multiprocessing
import shutil
import time
import random
import traceback
import argparse
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED

# ================= НАСТРОЙКИ ЯДРА =================
PERCENTILE = 98              
PAD_START = 0.5              
PAD_END = 0.5                
MIN_DURATION_SEC = 1.5       
RESIZE_WIDTH = 426           
RESIZE_HEIGHT = 240          
BATCH_SIZE = 150             
SCENE_CUT_THRESHOLD = 30.0
# ==================================================

def get_ffmpeg_path():
    if shutil.which("ffmpeg"): return "ffmpeg"
    elif os.path.exists("ffmpeg.exe"): return "ffmpeg.exe"
    return None

def get_ffprobe_path():
    if shutil.which("ffprobe"): return "ffprobe"
    elif os.path.exists("ffprobe.exe"): return "ffprobe.exe"
    return None

def format_duration(sec):
    if sec <= 0: return "0m"
    h = int(sec // 3600)
    m = int(round((sec % 3600) / 60))
    if m == 60:
        h += 1
        m = 0
    if h > 0: return f"{h}h{m}m"
    else: return f"{max(1, m)}m"

def apply_blur(img, blur_amount):
    if blur_amount <= 0: return img
    k = int(blur_amount) * 2 + 1
    return cv2.GaussianBlur(img, (k, k), 0)

def add_watermark(img):
    """Накладывает 18.png в Левый-Верхний угол с увеличенным масштабом"""
    wm_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "18.png")
    if not os.path.exists(wm_path): return img
    
    try:
        wm = cv2.imread(wm_path, cv2.IMREAD_UNCHANGED)
        if wm is None or wm.shape[2] != 4: return img
        
        bg_h, bg_w = img.shape[:2]
        wm_h, wm_w = wm.shape[:2]
        
        # Увеличил размер: теперь 12% от ширины видео (было 8%)
        t_w = max(10, int(bg_w * 0.12)) 
        t_h = int(wm_h * (t_w / wm_w))
        wm_resized = cv2.resize(wm, (t_w, t_h), interpolation=cv2.INTER_AREA)
        
        pad_x = max(10, int(bg_w * 0.02))
        pad_y = max(10, int(bg_h * 0.02))
        
        # Левый верхний угол
        y1, y2 = pad_y, pad_y + t_h
        x1, x2 = pad_x, pad_x + t_w
        
        alpha_wm = wm_resized[:, :, 3] / 255.0
        alpha_bg = 1.0 - alpha_wm
        
        for c in range(0, 3):
            img[y1:y2, x1:x2, c] = (alpha_wm * wm_resized[:, :, c] + alpha_bg * img[y1:y2, x1:x2, c])
            
    except Exception: pass
        
    return img

def run_ffmpeg_cmd(cmd):
    try:
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if res.returncode != 0:
            err_msg = res.stderr.decode('utf-8', errors='ignore').strip().split('\n')[-3:]
            print(f"\n    [X] ВНУТРЕННЯЯ ОШИБКА FFMPEG:\n    {err_msg}")
        return res.returncode == 0
    except Exception as e:
        print(f"\n    [X] ОШИБКА ВЫЗОВА: {e}")
        return False

# ----------------- УТИЛИТА МЕТАДАННЫХ -----------------
def wipe_metadata(video_path, ffmpeg_exe):
    print(f"\n[>] Очистка метаданных: {os.path.basename(video_path)}")
    temp_file = video_path + f".temp_{uuid.uuid4().hex}.mp4"
    cmd = [ffmpeg_exe, "-y", "-i", video_path, "-map_metadata", "-1", "-c", "copy", temp_file]
    if run_ffmpeg_cmd(cmd):
        try:
            shutil.move(temp_file, video_path)
            print(f"    [✓] Метаданные успешно стерты (In-place).")
        except Exception as e:
            print(f"    [X] Ошибка перезаписи файла: {e}")
            if os.path.exists(temp_file): os.remove(temp_file)
    else:
        if os.path.exists(temp_file): os.remove(temp_file)

# ----------------- АВТО-ДЕТЕКТ KEYFRAMES -----------------
def get_keyframe_interval(video_path, ffprobe_exe):
    if not ffprobe_exe: return 2.0
    cmd = [
        ffprobe_exe, "-v", "error", "-skip_frame", "nokey", 
        "-select_streams", "v:0", "-show_entries", "frame=pkt_dts_time", 
        "-of", "csv=p=0", video_path
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        times = []
        for line in res.stdout.split('\n'):
            line = line.strip()
            if line and line != 'N/A':
                try: times.append(float(line))
                except: pass
                
        if len(times) > 1:
            diffs = [times[i] - times[i-1] for i in range(1, min(15, len(times)))]
            if diffs:
                avg_gap = sum(diffs) / len(diffs)
                return max(2.0, avg_gap + 0.5)
    except: pass
    return 2.0

# ----------------- БЛОК НАРЕЗКИ -----------------
def process_frame_batch(batch_data, speed_threshold, ui_threshold, area_threshold):
    active_frames = []
    WHITE_THRESHOLD = 245 
    
    for prev_gray, gray, frame_idx in batch_data:
        if ui_threshold > 0:
            white_percent = (np.count_nonzero(gray >= WHITE_THRESHOLD) / gray.size) * 100.0
            if white_percent > ui_threshold: continue

        diff = cv2.absdiff(prev_gray, gray)
        if np.mean(diff) > SCENE_CUT_THRESHOLD: continue
            
        if area_threshold > 0:
            _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
            changed_percent = (np.count_nonzero(thresh) / thresh.size) * 100.0
            if changed_percent < area_threshold: continue 
            
        if speed_threshold == 0.0:
            active_frames.append(frame_idx)
            continue
            
        flow = cv2.calcOpticalFlowFarneback(prev_gray, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
        mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
        if np.percentile(mag, PERCENTILE) >= speed_threshold:
            active_frames.append(frame_idx)
            
    return active_frames

def get_active_intervals(video_path, sensitivity, ui_threshold, area_threshold, safe_merge_gap, ffmpeg_exe):
    print(f"\n[>] Анализ: {os.path.basename(video_path)}")
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    
    if total_frames == 0 or fps == 0: return []

    speed_thresh = 0.0 if sensitivity <= 0 else (sensitivity / 100.0) * 20.0
    num_workers = max(1, multiprocessing.cpu_count() - 2)
    
    cmd = [
        ffmpeg_exe, "-hwaccel", "auto", "-i", video_path, 
        "-f", "image2pipe", "-pix_fmt", "gray", "-vcodec", "rawvideo", 
        "-s", f"{RESIZE_WIDTH}x{RESIZE_HEIGHT}", "-"
    ]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=10**8)
    
    frame_bytes = RESIZE_WIDTH * RESIZE_HEIGHT
    active_frames = []
    batch = []
    prev_frame = None
    frame_idx = 1
    frames_processed = 0
    max_futures = num_workers * 2
    futures = set()

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        while True:
            while len(futures) >= max_futures:
                done, futures = wait(futures, return_when=FIRST_COMPLETED)
                for f in done:
                    active_frames.extend(f.result())
                    frames_processed += BATCH_SIZE
                    pc = int((min(1.0, frames_processed / total_frames)) * 100)
                    print(f"\r    [Прогресс поиска]: {pc}%", end="", flush=True)
            
            raw_data = process.stdout.read(frame_bytes)
            if not raw_data or len(raw_data) != frame_bytes: break
                
            gray_frame = np.frombuffer(raw_data, dtype=np.uint8).reshape((RESIZE_HEIGHT, RESIZE_WIDTH))
            if prev_frame is not None:
                batch.append((prev_frame, gray_frame, frame_idx))
            prev_frame = gray_frame
            frame_idx += 1
            
            if len(batch) >= BATCH_SIZE:
                futures.add(executor.submit(process_frame_batch, batch, speed_thresh, ui_threshold, area_threshold))
                batch = []
                
        if batch: futures.add(executor.submit(process_frame_batch, batch, speed_thresh, ui_threshold, area_threshold))
        if futures:
            done, _ = wait(futures)
            for f in done: active_frames.extend(f.result())

    process.stdout.close()
    process.wait()
    print() 
    
    if not active_frames: return []

    active_frames = sorted(list(active_frames))
    raw_intervals = []
    cluster = [active_frames[0]]
    min_frames = int(MIN_DURATION_SEC * fps)

    for f in active_frames[1:]:
        if f - cluster[-1] <= (1.0 * fps): 
            cluster.append(f)
        else:
            if len(cluster) >= min_frames:
                raw_intervals.append([max(0, cluster[0]/fps - PAD_START), cluster[-1]/fps + PAD_END])
            cluster = [f]
            
    if len(cluster) >= min_frames:
        raw_intervals.append([max(0, cluster[0]/fps - PAD_START), cluster[-1]/fps + PAD_END])

    if not raw_intervals: return []

    merged = [raw_intervals[0]]
    for current in raw_intervals[1:]:
        previous = merged[-1]
        if current[0] <= previous[1] + safe_merge_gap:
            previous[1] = max(previous[1], current[1])
        else:
            merged.append(current)

    return merged

def process_video_cut(video_path, sensitivity, ui_threshold, area_threshold, size_limit_gb, safe_gap, out_dir, ffmpeg_exe, b_name, is_renamed):
    intervals = get_active_intervals(video_path, sensitivity, ui_threshold, area_threshold, safe_gap, ffmpeg_exe)
    if not intervals:
        print("    [-] Видео отсеяно (недостаточно движения/много интерфейса).")
        return []

    print(f"    [+] Найдено {len(intervals)} сцен. Собираем...")
    ext = os.path.splitext(video_path)[1]
    valid_temp = []
    
    for i, (st, en) in enumerate(intervals):
        dur = en - st
        if dur <= 0: continue
        t_file = os.path.join(out_dir, f"tmp_{uuid.uuid4().hex}{ext}")
        cmd = [ffmpeg_exe, "-y", "-ss", str(st), "-i", video_path, "-t", str(dur), "-map_metadata", "-1", "-c", "copy", "-avoid_negative_ts", "make_zero", t_file]
        run_ffmpeg_cmd(cmd)
        if os.path.exists(t_file) and os.path.getsize(t_file) > 1024:
            valid_temp.append((t_file, os.path.getsize(t_file), dur))
            
    if not valid_temp: return []
        
    def _concat(b_files, out_p):
        l_file = os.path.join(out_dir, f"lst_{uuid.uuid4().hex}.txt")
        with open(l_file, "w", encoding="utf-8") as f:
            for tf in b_files: f.write(f"file '{tf.replace('\\', '/')}'\n")
        
        cmd = [ffmpeg_exe, "-y", "-f", "concat", "-safe", "0", "-i", l_file, "-map_metadata", "-1", "-c", "copy", "-fflags", "+genpts", out_p]
        run_ffmpeg_cmd(cmd)
        if os.path.exists(l_file): os.remove(l_file)
        return out_p if os.path.exists(out_p) else None

    out_paths = []
    sz_limit = size_limit_gb * (1024 ** 3) if size_limit_gb > 0 else float('inf')
    cur_b, cur_sz, cur_dur, p_idx = [], 0, 0.0, 1
    
    for tf, sz, d in valid_temp:
        if cur_sz + sz > sz_limit and cur_b:
            dur_str = format_duration(cur_dur)
            out_n = f"{b_name}_pt{p_idx}_{dur_str}{ext}" if is_renamed else f"{b_name}_cut_pt{p_idx}_{dur_str}{ext}"
            p = os.path.join(out_dir, out_n)
            if _concat(cur_b, p): out_paths.append(p)
            cur_b, cur_sz, cur_dur, p_idx = [], 0, 0.0, p_idx + 1
        cur_b.append(tf)
        cur_sz += sz
        cur_dur += d

    if cur_b:
        dur_str = format_duration(cur_dur)
        if is_renamed:
            out_n = f"{b_name}_pt{p_idx}_{dur_str}{ext}" if (size_limit_gb > 0 and p_idx > 1) else f"{b_name}_{dur_str}{ext}"
        else:
            out_n = f"{b_name}_cut_pt{p_idx}_{dur_str}{ext}" if (size_limit_gb > 0 and p_idx > 1) else f"{b_name}_cut_{dur_str}{ext}"
            
        p = os.path.join(out_dir, out_n)
        if _concat(cur_b, p): out_paths.append(p)

    for tf, sz, d in valid_temp:
        if os.path.exists(tf): os.remove(tf)
        
    for p in out_paths: print(f"    [✓] Сохранено: {os.path.basename(p)}")
    return out_paths

def split_video_by_size(video_path, size_limit_gb, out_dir, ffmpeg_exe, b_name, is_renamed):
    size_limit_bytes = size_limit_gb * (1024 ** 3)
    file_size = os.path.getsize(video_path)
    if file_size <= size_limit_bytes: return None
        
    print(f"    [i] Файл превышает лимит ({(file_size/(1024**3)):.2f} GB > {size_limit_gb} GB). Быстрое разделение...")
    ext = os.path.splitext(video_path)[1]
    
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    cap.release()
    
    if fps == 0 or total_frames == 0: return None
    total_dur = total_frames / fps
    part_dur = total_dur * (size_limit_bytes / file_size) * 0.95
    
    out_paths = []
    current_start = 0.0
    part_idx = 1
    
    while current_start < total_dur:
        dur_left = total_dur - current_start
        dur = min(part_dur, dur_left)
        if dur < 2.0 and part_idx > 1: break
            
        dur_str = format_duration(dur)
        out_n = f"{b_name}_pt{part_idx}_{dur_str}{ext}" if is_renamed else f"{b_name}_split_pt{part_idx}_{dur_str}{ext}"
        p = os.path.join(out_dir, out_n)
        
        cmd = [ffmpeg_exe, "-y", "-ss", str(current_start), "-i", video_path, "-t", str(dur), "-map_metadata", "-1", "-c", "copy", "-avoid_negative_ts", "make_zero", p]
        run_ffmpeg_cmd(cmd)
        
        if os.path.exists(p):
            out_paths.append(p)
            print(f"    [✓] Сохранена часть {part_idx}: {os.path.basename(p)}")
            
        current_start += dur
        part_idx += 1
        
    return out_paths

# ----------------- БЛОК ИЗОБРАЖЕНИЙ И ПРЕВЬЮ -----------------
def make_video_preview(video_path, out_dir, duration_sec, ffmpeg_exe):
    print(f"\n[>] Превью ({duration_sec}с): {os.path.basename(video_path)}")
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    out_path = os.path.join(out_dir, f"{base_name}_preview.mp4")
    
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if total_frames == 0 or fps == 0: return

    target_count = duration_sec * 30
    step = total_frames / max(1, target_count)

    cmd = [
        ffmpeg_exe, "-y", "-v", "error", 
        "-f", "rawvideo", "-vcodec", "rawvideo", "-s", f"{w}x{h}", "-pix_fmt", "bgr24", "-r", "30", 
        "-i", "-", "-map_metadata", "-1", "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p", out_path
    ]
    
    log_file = os.path.join(out_dir, f"ffmpeg_err_{uuid.uuid4().hex}.log")
    with open(log_file, "w") as err_out:
        process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=err_out)
        try:
            for i in range(target_count):
                cap.set(cv2.CAP_PROP_POS_FRAMES, min(int(i * step), total_frames - 2))
                ret, frame = cap.read()
                if ret:
                    process.stdin.write(frame.tobytes())
                    print(f"\r    [Прогресс]: {int(((i+1) / target_count) * 100)}%", end="")
        except Exception: pass
        process.stdin.close()
        process.wait()
        
    cap.release()
    if process.returncode == 0:
        print(f"\n    [✓] Готово: {os.path.basename(out_path)}")
    if os.path.exists(log_file): os.remove(log_file)

def put_text_outline(img, text, pos, scale, thick):
    cv2.putText(img, text, pos, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thick + 2, cv2.LINE_AA)
    cv2.putText(img, text, pos, cv2.FONT_HERSHEY_SIMPLEX, scale, (255, 255, 255), thick, cv2.LINE_AA)

def make_screenlist(video_path, out_dir, count, blur_amount):
    print(f"\n[>] Скринлист ({count}шт): {os.path.basename(video_path)}")
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    out_clean = os.path.join(out_dir, f"{base_name}_screenlist.jpg")
    out_blur = os.path.join(out_dir, f"{base_name}_screenlist_blur.jpg")
    
    W, H, f_scale, f_thick = 3840, 2160, 1.5, 3
    cols = int(math.ceil(math.sqrt(count)))
    rows = int(math.ceil(count / cols))
    cw, ch = W // cols, H // rows
    
    canvas_clean = np.zeros((H, W, 3), dtype=np.uint8)
    if blur_amount > 0: canvas_blur = np.zeros((H, W, 3), dtype=np.uint8)

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames == 0 or fps == 0: return

    for i in range(count):
        cap.set(cv2.CAP_PROP_POS_FRAMES, min(int((i + 0.5) * (total_frames / count)), total_frames - 2))
        ret, frame = cap.read()
        if not ret: continue
            
        timecode = time.strftime('%H:%M:%S', time.gmtime(int(cap.get(cv2.CAP_PROP_POS_MSEC)/1000)))
        y, x = (i // cols) * ch, (i % cols) * cw
        
        res_clean = cv2.resize(frame, (cw, ch), interpolation=cv2.INTER_AREA)
        put_text_outline(res_clean, timecode, (int(cw * 0.05), int(ch * 0.90)), f_scale, f_thick)
        canvas_clean[y:y+ch, x:x+cw] = res_clean
        
        if blur_amount > 0:
            res_blur = cv2.resize(frame, (cw, ch), interpolation=cv2.INTER_AREA)
            res_blur = apply_blur(res_blur, blur_amount)
            put_text_outline(res_blur, timecode, (int(cw * 0.05), int(ch * 0.90)), f_scale, f_thick)
            canvas_blur[y:y+ch, x:x+cw] = res_blur

        print(f"\r    [Прогресс]: {i+1}/{count}", end="")

    cap.release()
    cv2.imwrite(out_clean, canvas_clean)
    print(f"\n    [✓] {os.path.basename(out_clean)}")
    if blur_amount > 0:
        canvas_blur = add_watermark(canvas_blur)
        cv2.imwrite(out_blur, canvas_blur)
        print(f"    [✓] {os.path.basename(out_blur)}")

def extract_random(video_path, out_dir, count, blur_amount):
    print(f"\n[>] Скриншоты ({count}шт): {os.path.basename(video_path)}")
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 10: 
        cap.release()
        return

    base_name = os.path.splitext(os.path.basename(video_path))[0]
    for i in range(count):
        cap.set(cv2.CAP_PROP_POS_FRAMES, random.randint(10, max(10, total_frames - 10)))
        ret, frame = cap.read()
        if ret:
            name_c = f"{base_name}_rand{i+1}.jpg"
            cv2.imwrite(os.path.join(out_dir, name_c), frame)
            print(f"    [✓] {name_c}")
            
            if blur_amount > 0:
                frame_blur = apply_blur(frame, blur_amount)
                frame_blur = add_watermark(frame_blur)
                name_b = f"{base_name}_rand{i+1}_blur.jpg"
                cv2.imwrite(os.path.join(out_dir, name_b), frame_blur)
                print(f"    [✓] {name_b}")
    cap.release()

# ----------------- БЛОК УТИЛИТ -----------------
def trim_video(video_path, out_dir, start_sec, end_sec, ffmpeg_exe, b_name, is_renamed):
    print(f"\n[>] Обрезка краев: {os.path.basename(video_path)}")
    ext = os.path.splitext(video_path)[1]
    
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    cap.release()
    
    if fps == 0 or total_frames == 0: return None
    total_dur = total_frames / fps
    new_dur = total_dur - start_sec - end_sec
    if new_dur <= 0:
        print("    [X] Ошибка: Отрезается больше, чем длина видео!")
        return None
        
    dur_str = format_duration(new_dur)
    out_n = f"{b_name}_{dur_str}{ext}" if is_renamed else f"{b_name}_trimmed_{dur_str}{ext}"
    out_path = os.path.join(out_dir, out_n)
        
    cmd = [ffmpeg_exe, "-y", "-ss", str(start_sec), "-i", video_path, "-t", str(new_dur), "-map_metadata", "-1", "-c", "copy", out_path]
    run_ffmpeg_cmd(cmd)
    if os.path.exists(out_path):
        print(f"    [✓] Сохранено: {os.path.basename(out_path)}")
        return out_path
    return None

def split_half(video_path, out_dir, ffmpeg_exe, b_name, is_renamed):
    print(f"\n[>] Разделение: {os.path.basename(video_path)}")
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    if total_frames == 0 or fps == 0: return

    hd = (total_frames / fps) / 2.0
    dur_str = format_duration(hd)
    ext = os.path.splitext(video_path)[1]
    
    n1 = f"{b_name}_1_{dur_str}{ext}" if is_renamed else f"{b_name}_split_1_{dur_str}{ext}"
    n2 = f"{b_name}_2_{dur_str}{ext}" if is_renamed else f"{b_name}_split_2_{dur_str}{ext}"
    
    run_ffmpeg_cmd([ffmpeg_exe, "-y", "-i", video_path, "-t", str(hd), "-map_metadata", "-1", "-c", "copy", os.path.join(out_dir, n1)])
    run_ffmpeg_cmd([ffmpeg_exe, "-y", "-ss", str(hd), "-i", video_path, "-map_metadata", "-1", "-c", "copy", os.path.join(out_dir, n2)])
    print("    [✓] Сохранены части 1 и 2")

def rename_mask(target_dir, genre, models):
    print(f"\n[>] Умное переименование: {target_dir}")
    files = []
    for ext in ("*.mp4", "*.avi", "*.mkv", "*.mov"):
        files.extend(glob.glob(os.path.join(target_dir, ext)))
    files.sort()
    if not files: return
    
    for i, fp in enumerate(files, 1):
        try:
            cap = cv2.VideoCapture(fp)
            if not cap.isOpened(): continue
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps_v = cap.get(cv2.CAP_PROP_FPS)
            tf_v = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            cap.release()
            
            if h >= 2160 or w >= 3840: res = "4k"
            elif h >= 1440 or w >= 2560: res = "1440p"
            elif h >= 1080 or w >= 1920: res = "1080p"
            elif h >= 720 or w >= 1280: res = "720p"
            else: res = f"{h}p"
                
            ext = os.path.splitext(fp)[1]
            fps_s = f"{int(round(fps_v))}fps" if fps_v > 0 else "30fps"
            dur_str = format_duration(tf_v / fps_v if fps_v > 0 else 0)
            
            nn = f"{i:03d}_{genre}_{res}_{fps_s}_{models}_{dur_str}{ext}"
            os.rename(fp, os.path.join(target_dir, nn))
            print(f"    [✓] {os.path.basename(fp)} -> {nn}")
        except Exception: pass

# ----------------- РОУТЕР -----------------
def execute_pipeline(args, video_path, ffmpeg_exe, ffprobe_exe, file_id=1):
    out_dir = os.path.join(os.path.dirname(video_path), "Processed")
    os.makedirs(out_dir, exist_ok=True)
    
    orig_base = os.path.splitext(os.path.basename(video_path))[0]
    ext = os.path.splitext(video_path)[1]
    
    is_renamed = False
    mask_name = orig_base
    if args.do_rename == 1 and args.genre != "none":
        cap = cv2.VideoCapture(video_path)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps_val = cap.get(cv2.CAP_PROP_FPS)
        cap.release()
        
        if h >= 2160 or w >= 3840: res = "4k"
        elif h >= 1440 or w >= 2560: res = "1440p"
        elif h >= 1080 or w >= 1920: res = "1080p"
        elif h >= 720 or w >= 1280: res = "720p"
        else: res = f"{h}p"
        
        fps_str = f"{int(round(fps_val))}fps" if fps_val > 0 else "30fps"
        mask_name = f"{file_id:03d}_{args.genre}_{res}_{fps_str}_{args.models}"
        is_renamed = True

    current_targets = [video_path]

    # 1. ОБРЕЗКА КРАЕВ (TRIM)
    if args.do_trim == 1 and (args.t_start > 0 or args.t_end > 0):
        trimmed = []
        for t in current_targets:
            b_name = mask_name if is_renamed else os.path.splitext(os.path.basename(t))[0]
            res = trim_video(t, out_dir, args.t_start, args.t_end, ffmpeg_exe, b_name, is_renamed)
            if res: trimmed.append(res)
        current_targets = trimmed if trimmed else current_targets

    # 2. УМНАЯ НАРЕЗКА ИЛИ РАЗДЕЛЕНИЕ ПО РАЗМЕРУ
    needs_processing = (args.do_cut == 1 and (args.sens > 0 or args.area > 0 or args.ui > 0))
    needs_split = (args.size > 0)

    if needs_processing:
        cutted = []
        for t in current_targets:
            b_name = mask_name if is_renamed else os.path.splitext(os.path.basename(t))[0]
            print(f"\n{'='*50}\nОБРАБОТКА (НАРЕЗКА): {os.path.basename(t)}\n{'='*50}")
            kf_gap = get_keyframe_interval(t, ffprobe_exe)
            print(f"    [i] Авто-детект GOP (интервал склейки): {kf_gap:.1f} сек")
            
            c = process_video_cut(t, args.sens, args.ui, args.area, args.size, kf_gap, out_dir, ffmpeg_exe, b_name, is_renamed)
            if c: cutted.extend(c)
        if not cutted:
            print("    [!] Видео полностью отсеяно. Пропуск следующих шагов.")
            return
        current_targets = cutted

    elif needs_split:
        sized = []
        for t in current_targets:
            b_name = mask_name if is_renamed else os.path.splitext(os.path.basename(t))[0]
            s_res = split_video_by_size(t, args.size, out_dir, ffmpeg_exe, b_name, is_renamed)
            if s_res:
                sized.extend(s_res)
            else:
                if is_renamed:
                    cap = cv2.VideoCapture(t)
                    fps_v = cap.get(cv2.CAP_PROP_FPS)
                    tf_v = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                    cap.release()
                    dur_str = format_duration(tf_v / fps_v if fps_v > 0 else 0)
                    
                    np_path = os.path.join(out_dir, f"{mask_name}_{dur_str}{ext}")
                    if os.path.dirname(t) == out_dir: os.rename(t, np_path)
                    else: shutil.copy2(t, np_path)
                    sized.append(np_path)
                else:
                    sized.append(t)
        current_targets = sized

    else:
        # Просто переименование
        if is_renamed:
            renamed = []
            for t in current_targets:
                cap = cv2.VideoCapture(t)
                fps_v = cap.get(cv2.CAP_PROP_FPS)
                tf_v = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                cap.release()
                dur_str = format_duration(tf_v / fps_v if fps_v > 0 else 0)
                
                np_path = os.path.join(out_dir, f"{mask_name}_{dur_str}{ext}")
                if os.path.dirname(t) == out_dir: os.rename(t, np_path)
                else: shutil.copy2(t, np_path)
                renamed.append(np_path)
            current_targets = renamed

    # 3. РАЗДЕЛЕНИЕ ПОПОЛАМ
    if args.do_split == 1:
        for t in current_targets:
            b_name = mask_name if is_renamed else os.path.splitext(os.path.basename(t))[0]
            split_half(t, out_dir, ffmpeg_exe, b_name, is_renamed)
            
    # 4. ИЗОБРАЖЕНИЯ И ПРЕВЬЮ
    for t in current_targets:
        if args.do_img == 1:
            if args.grid > 0: make_screenlist(t, out_dir, args.grid, args.blur)
            if args.screens > 0: extract_random(t, out_dir, args.screens, args.blur)
        
        if args.do_prev == 1:
            if args.prev > 0: make_video_preview(t, out_dir, args.prev, ffmpeg_exe)

if __name__ == "__main__":
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser()
    parser.add_argument("--do_trim", type=int, default=0)
    parser.add_argument("--t_start", type=float, default=0)
    parser.add_argument("--t_end", type=float, default=0)
    parser.add_argument("--do_split", type=int, default=0)
    parser.add_argument("--do_cut", type=int, default=0)
    parser.add_argument("--sens", type=int, default=30)
    parser.add_argument("--area", type=float, default=5.0)
    parser.add_argument("--ui", type=float, default=50.0)
    parser.add_argument("--size", type=float, default=0.0)
    parser.add_argument("--do_img", type=int, default=0)
    parser.add_argument("--grid", type=int, default=16)
    parser.add_argument("--screens", type=int, default=2)
    parser.add_argument("--blur", type=int, default=0)
    parser.add_argument("--do_prev", type=int, default=0)
    parser.add_argument("--prev", type=int, default=10)
    parser.add_argument("--do_rename", type=int, default=0)
    parser.add_argument("--genre", type=str, default="none")
    parser.add_argument("--models", type=str, default="none")
    parser.add_argument("--do_wipe", type=int, default=0)
    parser.add_argument("--mode", required=True)
    parser.add_argument("--target", required=True)
    args = parser.parse_args()
    
    try:
        ffmpeg_exe = get_ffmpeg_path()
        ffprobe_exe = get_ffprobe_path()
        
        if not ffmpeg_exe and args.do_rename == 0:
            print("[X] ОШИБКА: ffmpeg.exe не найден!")
            sys.exit(1)

        target_clean = args.target if os.path.isdir(args.target) else os.path.dirname(args.target)
        
        if args.do_rename == 1 and args.do_trim == 0 and args.do_cut == 0 and args.do_split == 0 and args.do_img == 0 and args.do_prev == 0:
            rename_mask(target_clean, args.genre, args.models)
            sys.exit(0)
            
        if args.do_wipe == 1:
            if args.mode == "single" and os.path.isfile(args.target):
                wipe_metadata(args.target, ffmpeg_exe)
            elif args.mode == "batch" and os.path.isdir(args.target):
                for ext in ["*.mp4", "*.avi", "*.mkv", "*.mov"]:
                    for v in glob.glob(os.path.join(args.target, ext)): wipe_metadata(v, ffmpeg_exe)
            sys.exit(0)

        if args.mode == "single" and os.path.isfile(args.target):
            execute_pipeline(args, args.target, ffmpeg_exe, ffprobe_exe, file_id=1)
        elif args.mode == "batch" and os.path.isdir(args.target):
            files = []
            for ext in ["*.mp4", "*.avi", "*.mkv", "*.mov"]:
                files.extend(glob.glob(os.path.join(args.target, ext)))
            files.sort()
            for i, v in enumerate(files, 1):
                execute_pipeline(args, v, ffmpeg_exe, ffprobe_exe, file_id=i)
        else:
            print("[X] Файл или папка не найдены. Проверьте путь.")

    except Exception as e:
        print(f"\n[КРИТИЧЕСКАЯ ОШИБКА PYTHON]")
        traceback.print_exc()
        sys.exit(1)
