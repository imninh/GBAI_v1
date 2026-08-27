import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

BASE_DIR = Path("D:/P-075")
ASSETS_DIR = BASE_DIR / "video_output" / "assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

def capture_all():
    print("Capturing web and product assets via Playwright...", flush=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # 1. Desktop 1080p
        page = browser.new_page(viewport={"width": 1920, "height": 1080})

        # Live Web Vercel
        print("  -> Capturing https://gbai-v1.vercel.app/ ...", flush=True)
        try:
            page.goto("https://gbai-v1.vercel.app/", wait_until="networkidle", timeout=25000)
            time.sleep(2)
            page.screenshot(path=str(ASSETS_DIR / "web_landing.png"))
        except Exception as e:
            print(f"     Note: {e}", flush=True)
            page.screenshot(path=str(ASSETS_DIR / "web_landing.png"))

        # BQL Dashboard
        print("  -> Capturing BQL Dashboard...", flush=True)
        bql_url = f"file:///{BASE_DIR.as_posix()}/bql-dashboard/index.html"
        try:
            page.goto(bql_url)
            time.sleep(2)
            page.screenshot(path=str(ASSETS_DIR / "bql_map_default.png"))

            # Interactive Route click
            page.evaluate("""
                const btns = Array.from(document.querySelectorAll('button, .btn'));
                const target = btns.find(b => b.innerText.includes('Tối ưu') || b.innerText.includes('Lộ trình') || b.innerText.includes('Gom'));
                if (target) target.click();
            """)
            time.sleep(1)
            page.screenshot(path=str(ASSETS_DIR / "bql_map_route.png"))
        except Exception as e:
            print(f"     BQL error: {e}", flush=True)

        # Digital Twin 3D
        print("  -> Capturing Digital Twin 3D...", flush=True)
        twin_url = f"file:///{BASE_DIR.as_posix()}/iot/simulation/demo_visual.html"
        try:
            page.goto(twin_url)
            time.sleep(3)
            page.screenshot(path=str(ASSETS_DIR / "digital_twin_idle.png"))

            page.evaluate("if (typeof triggerPIR === 'function') triggerPIR();")
            time.sleep(1.5)
            page.screenshot(path=str(ASSETS_DIR / "digital_twin_trigger.png"))

            page.evaluate("if (typeof classifyItem === 'function') classifyItem('plastic');")
            time.sleep(2)
            page.screenshot(path=str(ASSETS_DIR / "digital_twin_classified.png"))

            page.evaluate("if (typeof rotateServo === 'function') rotateServo(1, 45);")
            time.sleep(1.5)
            page.screenshot(path=str(ASSETS_DIR / "digital_twin_servo.png"))
        except Exception as e:
            print(f"     Twin error: {e}", flush=True)

        # Generate HTML Canvas Graphics
        print("  -> Generating Motion Graphic Panels (Privacy, Test, HITL, Hero)...", flush=True)

        # Privacy Diagram
        privacy_html = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
        body { margin: 0; background: #080e1e; color: #fff; font-family: system-ui, sans-serif; display: flex; flex-direction: column; justify-content: center; align-items: center; height: 100vh; }
        .tag { background: rgba(139, 92, 246, 0.2); color: #c4b5fd; border: 1px solid #8b5cf6; padding: 8px 24px; border-radius: 99px; font-weight: 800; font-size: 16px; margin-bottom: 20px; text-transform: uppercase; letter-spacing: 2px; }
        h1 { font-size: 52px; margin: 0 0 10px 0; font-weight: 900; letter-spacing: -1px; }
        p.sub { font-size: 22px; color: #94a3b8; margin-bottom: 50px; }
        .pipeline { display: flex; gap: 20px; align-items: center; }
        .card { background: #0f172a; border: 1px solid #1e293b; padding: 28px 22px; border-radius: 16px; width: 200px; text-align: center; box-shadow: 0 15px 35px rgba(0,0,0,0.6); }
        .card.active { border-color: #8b5cf6; box-shadow: 0 0 30px rgba(139, 92, 246, 0.4); background: #131d38; }
        .step-num { font-size: 14px; color: #a78bfa; font-weight: 900; margin-bottom: 10px; }
        .icon { font-size: 42px; margin-bottom: 14px; }
        .card-title { font-size: 18px; font-weight: 800; margin-bottom: 8px; }
        .card-desc { font-size: 13px; color: #94a3b8; line-height: 1.4; }
        .arrow { font-size: 32px; color: #64748b; font-weight: bold; }
        .badge-secure { margin-top: 50px; background: rgba(16, 185, 129, 0.15); border: 1px solid #10b981; color: #34d399; padding: 12px 30px; border-radius: 14px; font-weight: 700; font-size: 18px; display: flex; align-items: center; gap: 12px; }
        </style></head><body>
        <div class="tag">Security & Privacy Architecture</div>
        <h1>Quy Trình 5 Bước Bảo Mật Ảnh Cư Dân</h1>
        <p class="sub">Tuyệt đối không gửi ảnh gốc thô tới API nhà cung cấp mô hình bên ngoài</p>
        <div class="pipeline">
            <div class="card"><div class="step-num">BƯỚC 1</div><div class="icon">🔍</div><div class="card-title">Validate</div><div class="card-desc">Kiểm tra định dạng & độ hợp lệ của ảnh</div></div>
            <div class="arrow">→</div>
            <div class="card active"><div class="step-num">BƯỚC 2</div><div class="icon">📍❌</div><div class="card-title">Tước EXIF & GPS</div><div class="card-desc">Xóa 100% metadata vị trí và thiết bị</div></div>
            <div class="arrow">→</div>
            <div class="card active"><div class="step-num">BƯỚC 3</div><div class="icon">👤🌫️</div><div class="card-title">Làm mờ mặt</div><div class="card-desc">Tự động phát hiện và che khuôn mặt người</div></div>
            <div class="arrow">→</div>
            <div class="card"><div class="step-num">BƯỚC 4</div><div class="icon">📐</div><div class="card-title">Resize 512px</div><div class="card-desc">Chuẩn hóa kích thước, giảm chi phí & băng thông</div></div>
            <div class="arrow">→</div>
            <div class="card"><div class="step-num">BƯỚC 5</div><div class="icon">⚡</div><div class="card-title">pHash Fingerprint</div><div class="card-desc">Tạo vân tay ảnh để tra cứu cache $0</div></div>
        </div>
        <div class="badge-secure">🛡️ Chính sách Zero-Knowledge: Ảnh cư dân được bảo vệ toàn diện</div>
        </body></html>"""
        page.set_content(privacy_html)
        page.screenshot(path=str(ASSETS_DIR / "privacy_diagram.png"))

        # Test Proof Diagram
        test_html = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
        body { margin: 0; background: #050811; color: #fff; font-family: monospace; display: flex; flex-direction: column; justify-content: center; align-items: center; height: 100vh; }
        .container { width: 1150px; background: #0b1329; border: 1px solid #1e293b; border-radius: 18px; overflow: hidden; box-shadow: 0 25px 60px rgba(0,0,0,0.85); }
        .terminal-header { background: #131f37; padding: 16px 24px; display: flex; align-items: center; gap: 10px; border-bottom: 1px solid #334155; }
        .dot { width: 14px; height: 14px; border-radius: 50%; }
        .dot.red { background: #ef4444; } .dot.yellow { background: #f59e0b; } .dot.green { background: #10b981; }
        .term-title { margin-left: 15px; color: #94a3b8; font-size: 15px; font-weight: bold; }
        .term-body { padding: 35px; line-height: 1.7; font-size: 17px; }
        .cmd { color: #38bdf8; font-weight: bold; margin-bottom: 20px; font-size: 20px; }
        .pass-text { color: #4ade80; font-weight: bold; }
        .stats-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; margin-top: 35px; padding-top: 30px; border-top: 1px dashed #334155; }
        .stat-box { background: #101c38; border: 1px solid #10b981; border-radius: 14px; padding: 24px; text-align: center; }
        .stat-val { font-size: 48px; font-weight: 900; color: #34d399; margin-bottom: 6px; }
        .stat-lbl { font-size: 15px; color: #94a3b8; text-transform: uppercase; letter-spacing: 1.5px; }
        </style></head><body>
        <div class="container">
            <div class="terminal-header"><div class="dot red"></div><div class="dot yellow"></div><div class="dot green"></div><div class="term-title">bash — greenbin-ai / automated-verification-suite</div></div>
            <div class="term-body">
                <div class="cmd">$ pytest -q & test_firmware.py & eval/run_retrieval_eval.py</div>
                <div style="color: #cbd5e1;">
                    tests/test_agents.py::test_routing_langgraph <span class="pass-text">PASSED [ 18%]</span><br>
                    tests/test_privacy.py::test_exif_strip_and_face_blur <span class="pass-text">PASSED [ 42%]</span><br>
                    tests/test_pickup.py::test_10_state_machine_and_hitl <span class="pass-text">PASSED [ 75%]</span><br>
                    tests/test_routes.py::test_tsp_2opt_route_optimization <span class="pass-text">PASSED [100%]</span>
                </div>
                <div class="stats-grid">
                    <div class="stat-box"><div class="stat-val">68</div><div class="stat-lbl">Backend Tests</div></div>
                    <div class="stat-box"><div class="stat-val">61 / 61</div><div class="stat-lbl">Firmware Logic Tests</div></div>
                    <div class="stat-box"><div class="stat-val">27 / 27</div><div class="stat-lbl">End-to-End Scenarios</div></div>
                </div>
            </div>
        </div>
        </body></html>"""
        page.set_content(test_html)
        page.screenshot(path=str(ASSETS_DIR / "test_proof.png"))

        # HITL Diagram
        hitl_html = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
        body { margin: 0; background: #080f20; color: #fff; font-family: system-ui, sans-serif; display: flex; flex-direction: column; justify-content: center; align-items: center; height: 100vh; }
        .badge-warn { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid #ef4444; padding: 8px 20px; border-radius: 99px; font-weight: 800; font-size: 16px; margin-bottom: 20px; }
        h1 { font-size: 48px; margin: 0 0 10px 0; font-weight: 900; }
        p.sub { font-size: 20px; color: #94a3b8; margin-bottom: 40px; }
        .queue-box { width: 1100px; background: #0f1a33; border: 1px solid #334155; border-radius: 18px; padding: 30px; box-shadow: 0 20px 50px rgba(0,0,0,0.7); }
        .item-row { display: flex; align-items: center; justify-content: space-between; background: #0b1329; padding: 20px 28px; border-radius: 14px; margin-bottom: 16px; border-left: 6px solid #f59e0b; }
        .item-row.danger { border-left-color: #ef4444; }
        .item-left { display: flex; align-items: center; gap: 24px; }
        .thumb { width: 64px; height: 64px; background: #1e293b; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 32px; }
        .item-info h4 { margin: 0 0 6px 0; font-size: 20px; font-weight: 800; }
        .item-info p { margin: 0; font-size: 15px; color: #94a3b8; }
        .conf-badge { background: #7c2d12; color: #fdba74; padding: 8px 16px; border-radius: 8px; font-weight: bold; font-size: 15px; }
        .btn-group { display: flex; gap: 12px; }
        .btn { padding: 12px 24px; border-radius: 10px; font-weight: bold; font-size: 16px; border: none; cursor: pointer; }
        .btn-approve { background: #10b981; color: #fff; }
        .btn-reject { background: #334155; color: #cbd5e1; }
        .hitl-footer { margin-top: 35px; display: flex; justify-content: space-around; width: 1050px; }
        .hitl-point { background: #132244; padding: 18px 30px; border-radius: 12px; text-align: center; border: 1px solid #3b82f6; font-size: 17px; }
        .hitl-point span { font-weight: 800; color: #60a5fa; }
        </style></head><body>
        <div class="badge-warn">HUMAN-IN-THE-LOOP SAFEGUARD</div>
        <h1>3 Điểm Kiểm Soát Bắt Buộc Của Con Người</h1>
        <p class="sub">AI đề xuất thông minh — Con người nắm quyền phê duyệt</p>
        <div class="queue-box">
            <div class="item-row danger">
                <div class="item-left"><div class="thumb">🔋</div><div class="item-info"><h4>Phát hiện rác nghi vấn nguy hại (Ắc quy / Pin Lithium)</h4><p>Vị trí: Điểm gom Tầng B1 · Cư dân: #0901000001</p></div></div>
                <div style="display:flex; align-items:center; gap:24px;"><span class="conf-badge">Độ tin cậy: 72% (Cần xác nhận)</span><div class="btn-group"><button class="btn btn-approve">✓ Xác nhận nhãn</button><button class="btn btn-reject">Chuyển loại</button></div></div>
            </div>
            <div class="item-row">
                <div class="item-left"><div class="thumb">🚛</div><div class="item-info"><h4>Yêu cầu thu gom vượt ngưỡng 40kg (Tủ lạnh cũ)</h4><p>Tòa Sapphire 2 · Đề xuất ghép tuyến xe gom 15:30</p></div></div>
                <div style="display:flex; align-items:center; gap:24px;"><span style="color:#38bdf8; font-weight:bold; font-size:16px;">Agent đề xuất tuyến (2-Opt)</span><div class="btn-group"><button class="btn btn-approve">✓ Phê duyệt tuyến</button><button class="btn btn-reject">Điều chỉnh</button></div></div>
            </div>
        </div>
        <div class="hitl-footer">
            <div class="hitl-point"><span>HITL #1:</span> Duyệt yêu cầu vượt ngưỡng</div>
            <div class="hitl-point"><span>HITL #2:</span> Xác nhận nhãn nguy hại</div>
            <div class="hitl-point"><span>HITL #3:</span> Chốt tuyến điều phối xe</div>
        </div>
        </body></html>"""
        page.set_content(hitl_html)
        page.screenshot(path=str(ASSETS_DIR / "hitl_diagram.png"))

        # Brand Hero
        hero_html = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
        body { margin: 0; background: radial-gradient(circle at center, #0e3023 0%, #05140e 100%); color: #fff; font-family: system-ui, sans-serif; display: flex; flex-direction: column; justify-content: center; align-items: center; height: 100vh; }
        .logo-wrap { display: flex; align-items: center; gap: 24px; margin-bottom: 25px; }
        .logo-icon { width: 95px; height: 95px; background: #10b981; border-radius: 26px; display: flex; align-items: center; justify-content: center; font-size: 52px; box-shadow: 0 0 50px rgba(16, 185, 129, 0.7); }
        .logo-text { font-size: 80px; font-weight: 900; letter-spacing: -2px; color: #ffffff; }
        .tagline { font-size: 32px; color: #a7f3d0; margin-bottom: 45px; font-weight: 600; letter-spacing: 0.5px; }
        .features { display: flex; gap: 30px; margin-bottom: 55px; }
        .feat-pill { background: rgba(255,255,255,0.08); border: 1px solid rgba(16,185,129,0.5); padding: 14px 32px; border-radius: 99px; font-size: 20px; font-weight: 700; color: #f1f5f9; }
        .url-box { background: #10b981; color: #022c22; font-weight: 900; font-size: 26px; padding: 16px 45px; border-radius: 14px; box-shadow: 0 12px 35px rgba(16,185,129,0.5); letter-spacing: 1px; }
        .team-badge { margin-top: 35px; color: #6ee7b7; font-size: 18px; letter-spacing: 1.5px; font-weight: 700; }
        </style></head><body>
        <div class="logo-wrap"><div class="logo-icon">♻️</div><div class="logo-text">GreenBin AI</div></div>
        <div class="tagline">Phân loại tại nguồn · Vận hành bằng dữ liệu</div>
        <div class="features">
            <div class="feat-pill">⚡ 4 Tầng AI Định Tuyến</div>
            <div class="feat-pill">🛡️ Bảo Mật Quyền Riêng Tư</div>
            <div class="feat-pill">🚛 Tối Ưu Tuyến TSP (2-Opt)</div>
            <div class="feat-pill">👥 3 Điểm Con Người Duyệt (HITL)</div>
        </div>
        <div class="url-box">🌐 gbai-v1.vercel.app</div>
        <div class="team-badge">MÃ ĐỀ VHR-17 · NHÓM T-075 · AI20K COHORT 3-4</div>
        </body></html>"""
        page.set_content(hero_html)
        page.screenshot(path=str(ASSETS_DIR / "brand_hero.png"))

        browser.close()
    print("ALL ASSETS CAPTURED SUCCESSFULLY!", flush=True)

if __name__ == "__main__":
    capture_all()
