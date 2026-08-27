import os
import sys
import subprocess
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

BASE_DIR = Path("D:/P-075")
OUT_DIR = BASE_DIR / "video_output"
ASSETS_DIR = OUT_DIR / "assets"
AUDIO_DIR = OUT_DIR / "audio"
SCENES_DIR = OUT_DIR / "scenes"
FINAL_VIDEO = OUT_DIR / "greenbin_ai_product_demo_1080p.mp4"

SCENES_CONFIG = [
    {"id": 1, "asset": "web_landing.png", "min_dur": 5.0},
    {"id": 2, "asset": "web_landing.png", "min_dur": 8.0},
    {"id": 3, "asset": "brand_hero.png", "min_dur": 7.0},
    {"id": 4, "asset": "privacy_diagram.png", "min_dur": 11.0},
    {"id": 5, "asset": "digital_twin_trigger.png", "min_dur": 13.0},
    {"id": 6, "asset": "privacy_diagram.png", "min_dur": 12.0},
    {"id": 7, "asset": "privacy_diagram.png", "min_dur": 12.0},
    {"id": 8, "asset": "digital_twin_classified.png", "min_dur": 12.0},
    {"id": 9, "asset": "digital_twin_servo.png", "min_dur": 10.0},
    {"id": 10, "asset": "digital_twin_idle.png", "min_dur": 11.0},
    {"id": 11, "asset": "bql_map_default.png", "min_dur": 14.0},
    {"id": 12, "asset": "bql_map_route.png", "min_dur": 11.0},
    {"id": 13, "asset": "hitl_diagram.png", "min_dur": 13.0},
    {"id": 14, "asset": "hitl_diagram.png", "min_dur": 9.0},
    {"id": 15, "asset": "test_proof.png", "min_dur": 10.0},
    {"id": 16, "asset": "brand_hero.png", "min_dur": 10.0},
    {"id": 17, "asset": "brand_hero.png", "min_dur": 6.0},
]

def get_audio_duration(audio_path):
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        return float(res.stdout.strip())
    except Exception:
        return 6.0

def build_all_scenes():
    SCENES_DIR.mkdir(parents=True, exist_ok=True)
    rendered_clips = []
    
    print("--- Rendering 17 Video Scene Clips with FFmpeg ---", flush=True)
    for item in SCENES_CONFIG:
        sid = item["id"]
        img_file = ASSETS_DIR / item["asset"]
        if not img_file.exists():
            img_file = ASSETS_DIR / "brand_hero.png"
            
        audio_file = AUDIO_DIR / f"scene_{sid:02d}.mp3"
        out_clip = SCENES_DIR / f"scene_{sid:02d}.mp4"
        
        aud_dur = get_audio_duration(audio_file)
        dur = max(aud_dur + 0.6, item["min_dur"])
        frames = int(dur * 30)
        
        # Smooth Ken Burns zoom effect
        vf = (
            f"scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,"
            f"zoompan=z='min(zoom+0.0004,1.08)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1920x1080:fps=30"
        )
        
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(img_file),
            "-i", str(audio_file),
            "-filter_complex", vf,
            "-c:v", "libx264", "-preset", "fast", "-tune", "stillimage", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-t", str(dur),
            str(out_clip)
        ]
        
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if out_clip.exists() and out_clip.stat().st_size > 50000:
            print(f"  [OK] Rendered Scene {sid:02d} ({dur:.1f}s) -> {out_clip.name}", flush=True)
            rendered_clips.append(out_clip)
        else:
            print(f"  [ERR] Failed rendering Scene {sid:02d}", flush=True)

    print("\n--- Concatenating all scenes into Final 1080p Video ---", flush=True)
    concat_file = OUT_DIR / "concat.txt"
    with open(concat_file, "w", encoding="utf-8") as f:
        for clip in rendered_clips:
            f.write(f"file '{clip.as_posix()}'\n")

    concat_cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c", "copy",
        str(FINAL_VIDEO)
    ]
    subprocess.run(concat_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    if FINAL_VIDEO.exists() and FINAL_VIDEO.stat().st_size > 100000:
        total_size_mb = FINAL_VIDEO.stat().st_size / (1024 * 1024)
        total_dur = get_audio_duration(FINAL_VIDEO)
        print(f"\n=======================================================", flush=True)
        print(f"🎉 VIDEO PRODUCT DEMO ĐÃ ĐƯỢC TẠO THÀNH CÔNG!", flush=True)
        print(f"📁 Video: {FINAL_VIDEO.resolve()}", flush=True)
        print(f"⏱️ Tổng thời lượng: {total_dur:.1f} giây (khoảng {int(total_dur//60)}p{int(total_dur%60):02d}s)", flush=True)
        print(f"📦 Dung lượng: {total_size_mb:.2f} MB", flush=True)
        print(f"=======================================================", flush=True)
    else:
        print("Lỗi khi tạo video hoàn chỉnh.", flush=True)

if __name__ == "__main__":
    build_all_scenes()
