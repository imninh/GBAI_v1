// app.js — Điều khiển logic toàn diện cho mô phỏng 3D MUN™ AI Recycler
// Đồng bộ 2 chiều với Backend FastAPI: Mở phiên qua QR điện thoại & Cập nhật Realtime mức đầy 4 ngăn
(function(){
  "use strict";

  const $ = (id) => document.getElementById(id);
  const logBox = $("log");
  const statePill = $("statePill");
  const sessionPill = $("sessionPill");
  const sessionSecEl = $("sessionSec");

  // Dữ liệu các vật rác mẫu thực tế
  const WASTE_ITEMS = {
    plastic: {
      key: "plastic",
      title: "Chai nước Aquafina 500ml",
      route: "plastic",
      fixture: "fixtures/plastic_bottle.jpg",
      emoji: "🧴",
      expectedLabel: "Chai nhựa (PET)"
    },
    metal: {
      key: "metal",
      title: "Lon Coca-Cola nhôm 330ml",
      route: "metal",
      fixture: "fixtures/aluminum_can.jpg",
      emoji: "🥫",
      expectedLabel: "Lon nhôm (Aluminum)"
    },
    paper: {
      key: "paper",
      title: "Cốc giấy / Bìa carton",
      route: "paper",
      fixture: "fixtures/paper_cardboard.jpg",
      emoji: "📄",
      expectedLabel: "Giấy & Bìa carton"
    },
    other: {
      key: "other",
      title: "Bao bì bim bim / Rác khác",
      route: "other",
      fixture: "fixtures/other_snack_bag.jpg",
      emoji: "🍬",
      expectedLabel: "Bao bì nilon / Vô cơ"
    },
    battery: {
      key: "battery",
      title: "Pin AA Duracell (Nguy hại)",
      route: "hazard",
      fixture: "fixtures/battery_hazard.jpg",
      emoji: "🔋",
      expectedLabel: "Pin / Rác nguy hại"
    }
  };

  let selectedKey = "plastic";
  let isBusy = false;
  let isQrScanned = false;
  let activeSessionId = null;

  // Quản lý Phiên làm việc (Session Inactivity Timeout: 30s)
  const SESSION_TIMEOUT_SEC = 30;
  let sessionRemainingSec = 0;
  let sessionTimer = null;
  let backendSessionPollTimer = null;

  // Đếm số lượng rác thực tế bỏ vào từng ngăn
  const depositedCounts = {
    plastic: 0,
    metal: 0,
    paper: 0,
    other: 0
  };

  function ts(){
    const d = new Date();
    return d.toTimeString().slice(0,8) + "." + String(d.getMilliseconds()).padStart(3,"0");
  }

  function log(tag, msg){
    const line = document.createElement("div");
    line.innerHTML = `<span class="ts">${ts()}</span><span class="tag-${tag}">[${tag}]</span> ${msg}`;
    logBox.appendChild(line);
    logBox.scrollTop = logBox.scrollHeight;
  }

  function setState(name, kind){
    statePill.textContent = name;
    statePill.className = "state-pill " + (kind || "idle");
  }

  setInterval(()=>{ $("clock").textContent = new Date().toLocaleTimeString(); }, 1000);

  // Hook flash hiệu ứng toàn màn hình
  window.appFlashTrigger = function(){
    const flashEl = $("fullscreenFlash");
    if(flashEl){
      flashEl.classList.remove("flash-pop");
      void flashEl.getBoundingClientRect();
      flashEl.classList.add("flash-pop");
      setTimeout(() => { flashEl.classList.remove("flash-pop"); }, 80);
    }
    const svgFlash = $("flashRect");
    if(svgFlash){
      svgFlash.classList.remove("go");
      void svgFlash.getBoundingClientRect();
      svgFlash.classList.add("go");
    }
  };

  // ---------- Cấu hình Backend ----------
  function cfg(){
    return {
      base: $("cfgBase").value.replace(/\/$/,""),
      device: $("cfgDevice").value.trim(),
      key: $("cfgKey").value.trim(),
      binKey: $("cfgBinKey").value.trim(),
      bins: {
        plastic: "BIN-01",
        metal: "BIN-02",
        paper: "BIN-03",
        other: "BIN-04"
      }
    };
  }

  const sleep = (ms) => new Promise(r => setTimeout(r, ms));

  // Mức đầy các ngăn (Sonar HC-SR04)
  const binState = {
    plastic: { fill: 0, lastStatus: "binh_thuong" },
    metal:   { fill: 0, lastStatus: "binh_thuong" },
    paper:   { fill: 0, lastStatus: "binh_thuong" },
    other:   { fill: 0, lastStatus: "binh_thuong" },
  };

  // Cập nhật giao diện sơ đồ cắt lát cơ khí SVG
  function paintBin(key){
    const s = binState[key];
    const pct = Math.round(s.fill);
    const pctEl = $("pct-" + key);
    if(pctEl) pctEl.textContent = pct + "%";

    const fillRect = $("fill-" + key);
    if(fillRect){
      const maxH = 138;
      const h = (pct / 100) * maxH;
      fillRect.setAttribute("height", String(h));
      fillRect.setAttribute("y", String(368 - h));
    }

    const beam = $("beam-" + key);
    if(beam){
      const maxBeam = 130;
      const beamY = 236 + Math.max(0, maxBeam - (pct / 100) * maxBeam);
      beam.setAttribute("y2", String(beamY));
    }

    const badge = $("badge-" + key);
    if(badge) badge.classList.toggle("show", pct >= 80);
  }

  function setServo(el, dir){
    if(!el) return;
    el.classList.remove("left", "right");
    if(dir === "left" || dir === "right") el.classList.add(dir);
  }

  function setDuct(id, active){
    const el = $(id);
    if(el) el.classList.toggle("active", active);
  }

  function clearDucts(){
    ["duct-1L","duct-1R","duct-2plastic","duct-2metal","duct-3paper","duct-3other"].forEach(id => setDuct(id, false));
    setServo($("flap1"), "center");
    setServo($("flap2"), "center");
    setServo($("flap3"), "center");
    const p2 = $("pivot2"), p3 = $("pivot3");
    if(p2) p2.classList.remove("dim");
    if(p3) p3.classList.remove("dim");
  }

  // Tọa độ các điểm mốc cơ khí trên SVG
  const WAY = {
    start:   { x: 166, y: 35  },
    servo1:  { x: 166, y: 104 },
    servo2:  { x: 86,  y: 168 },
    servo3:  { x: 246, y: 168 },
    plastic: { x: 46,  y: 224 },
    metal:   { x: 126, y: 224 },
    paper:   { x: 206, y: 224 },
    other:   { x: 286, y: 224 },
  };

  function moveFallItem(pt){
    const item = $("fallItem");
    if(item) item.setAttribute("transform", `translate(${pt.x}, ${pt.y})`);
  }

  async function animateMechanicalDrop(routeKey, emojiChar){
    const item = $("fallItem");
    const fallEmoji = $("fallEmoji");
    if(fallEmoji) fallEmoji.textContent = emojiChar || "🧴";
    if(!item) return;

    const leftGroup = (routeKey === "plastic" || routeKey === "metal");

    item.style.transition = "none";
    moveFallItem(WAY.start);
    item.style.opacity = "1";
    void item.getBoundingClientRect();
    item.style.transition = "transform 0.45s ease-in-out";

    await sleep(50);
    moveFallItem(WAY.servo1);
    await sleep(480);

    moveFallItem(leftGroup ? WAY.servo2 : WAY.servo3);
    await sleep(480);

    const compTop = WAY[routeKey] || WAY.other;
    moveFallItem(compTop);
    await sleep(380);

    moveFallItem({ x: compTop.x, y: compTop.y + 40 });
    await sleep(300);
    item.style.opacity = "0";

    const box = $("compBox-" + routeKey);
    if(box){
      box.classList.remove("flashGo");
      void box.getBoundingClientRect();
      box.classList.add("flashGo");
    }
  }

  // Vòng lặp báo mức đầy nền HC-SR04 lên Backend Realtime
  let fillLoopTimer = null;
  async function reportOneBin(key){
    const c = cfg();
    const code = c.bins[key];
    const s = binState[key];
    const url = `${c.base}/bins/${encodeURIComponent(code)}/readings`;
    try{
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Device-Key": c.binKey },
        body: JSON.stringify({
          fill_percent: s.fill,
          battery_percent: 100,
          source: "simulator",
          device_id: c.device,
          uptime_s: Math.floor(performance.now() / 1000),
        }),
      });
      if(!res.ok) return;
      const data = await res.json();
      const newStatus = data.status;
      if((newStatus === "can_gom" || s.fill >= 80) && s.lastStatus !== "can_gom"){
        log("BIN", `⚠️ Ngăn ${key.toUpperCase()} đạt mức ${s.fill.toFixed(0)}% → Gửi yêu cầu thu gom (Pickup request) tới xe gom.`);
      }
      s.lastStatus = newStatus;
    }catch(err){
      // Chạy nền im lặng
    }
  }

  function startFillLoop(){
    if(fillLoopTimer) return;
    fillLoopTimer = setInterval(() => {
      Object.keys(binState).forEach(reportOneBin);
    }, 4000);
    Object.keys(binState).forEach(reportOneBin);
  }

  // ---------- Kiểm tra phiên đang mở từ App Cư Dân (QR Scan Sync) ----------
  async function checkBackendActiveSession(){
    if(isBusy) return;
    const c = cfg();
    const binCode = c.bins.plastic || "BIN-01";
    try {
      const res = await fetch(`${c.base}/phien/thung/${encodeURIComponent(binCode)}/hien-tai`);
      if(!res.ok) return;
      const data = await res.json();
      if(data.co_phien && !isQrScanned){
        isQrScanned = true;
        activeSessionId = data.ma_phien;
        log("QR", `📱 Phát hiện Cư Dân vừa quét QR từ điện thoại! Mở phiên: ${data.ma_phien.slice(0,8)}... (${data.user_name})`);
        if(window.Scene3D){
          window.Scene3D.updateQrScreenState("SCANNED", data.user_name || "Đã xác thực tài khoản");
        }
        startSessionTimer();
      }
    } catch(err){
      // Chạy nền im lặng
    }
  }

  function startBackendSessionPolling(){
    if(backendSessionPollTimer) return;
    backendSessionPollTimer = setInterval(checkBackendActiveSession, 1200);
    checkBackendActiveSession();
  }

  function stopBackendSessionPolling(){
    if(backendSessionPollTimer){
      clearInterval(backendSessionPollTimer);
      backendSessionPollTimer = null;
    }
  }

  // ---------- Quản lý Đếm Ngược Phiên 30 Giây ----------
  function startSessionTimer(){
    stopSessionTimer();
    sessionRemainingSec = SESSION_TIMEOUT_SEC;
    if(sessionPill) sessionPill.style.display = "flex";
    if(sessionSecEl) sessionSecEl.textContent = sessionRemainingSec;

    sessionTimer = setInterval(() => {
      sessionRemainingSec--;
      if(sessionSecEl) sessionSecEl.textContent = sessionRemainingSec;

      if(window.Scene3D && !isBusy){
        window.Scene3D.updateQrScreenState(
          isQrScanned ? "SCANNED" : "PRESENCE",
          `⏱️ Hết hạn sau: ${sessionRemainingSec}s`
        );
      }

      if(sessionRemainingSec <= 0){
        onSessionTimeout();
      }
    }, 1000);
  }

  function stopSessionTimer(){
    if(sessionTimer){
      clearInterval(sessionTimer);
      sessionTimer = null;
    }
    if(sessionPill) sessionPill.style.display = "none";
  }

  function onSessionTimeout(){
    stopSessionTimer();
    stopBackendSessionPolling();
    if(isBusy) return;

    log("TIMEOUT", "⏱️ QUÁ 30 GIÂY KHÔNG CÓ THAO TÁC BỎ RÁC → Tự động ngắt phiên (Session Expired)!");
    setState("TIMEOUT", "wait");
    $("depositBtn").disabled = true;
    $("pirStatus").textContent = "Phiên đã hết hạn (30s) · Đang quét lại...";
    $("pirLed").classList.remove("on");

    if(window.Scene3D){
      window.Scene3D.setLedRing(0xd97706, 1.0);
      window.Scene3D.updateQrScreenState("TIMEOUT");
    }

    setTimeout(() => {
      finishCycle(false);
    }, 2200);
  }

  // ---------- Chọn vật rác thực tế ----------
  function selectWasteItem(key){
    selectedKey = key;
    const item = WASTE_ITEMS[key];

    document.querySelectorAll(".waste-card").forEach(c => {
      c.classList.toggle("active", c.dataset.key === key);
    });

    if(window.Scene3D){
      window.Scene3D.setWasteItem(key);
    }

    // Hiển thị ảnh chụp xem trước trên camera box của sơ đồ cơ khí
    const previewImg = $("previewImg");
    const previewPlaceholder = $("previewPlaceholder");
    const camBadge = $("camBadge");
    if(previewImg){
      previewImg.src = item.fixture;
      previewImg.style.display = "block";
      if(previewPlaceholder) previewPlaceholder.style.display = "none";
      if(camBadge) camBadge.textContent = "ảnh mẫu";
    }

    log("STATE", `Người dùng chọn cầm: ${item.title} (${item.emoji})`);
  }

  document.querySelectorAll(".waste-card").forEach(card => {
    card.addEventListener("click", () => {
      selectWasteItem(card.dataset.key);
    });
  });

  // ---------- Quy trình Bỏ rác & Gọi AI ----------
  async function loadFixtureBlob(fixturePath){
    const resp = await fetch(fixturePath);
    return await resp.blob();
  }

  async function executeWasteDeposit(){
    if(isBusy) return;
    isBusy = true;
    stopSessionTimer();

    $("startBtn").disabled = true;
    $("walkBtn").disabled = true;
    $("depositBtn").disabled = true;
    if($("scanQrBtn")) $("scanQrBtn").disabled = true;

    startFillLoop();

    const c = cfg();
    const item = WASTE_ITEMS[selectedKey];

    try {
      // 1. Hoạt ảnh 5 pha trên Three.js
      setState("DEPOSITING", "active");
      log("STATE", `Người dùng đưa ${item.title} vào lỗ nhận rác của MUN™...`);
      
      if(window.Scene3D){
        window.Scene3D.updateKioskScreen({ state: "COUNTDOWN", sec: 3 });
        await window.Scene3D.playInsertAnimation();
      }

      // 2. HC-SR04 xác nhận vật thể rơi vào & Flash ESP32-CAM
      log("HC-SR04", "Cảm biến siêu âm xác nhận vật thể: before=50.0cm after=24.5cm delta=25.5cm -> waste_confirmed ✅");
      log("CAM", `ESP32-CAM chớp đèn flash 📸 — Đã chụp ảnh khung hình độ nét cao của ${item.title}.`);

      const camBadge = $("camBadge");
      if(camBadge) camBadge.textContent = "đã chụp";

      if(window.Scene3D){
        window.Scene3D.setLedRing(0x38bdf8, 1.5);
        window.Scene3D.updateKioskScreen({ state: "ANALYZING", itemTitle: item.title });
      }

      // 3. Gửi ảnh thật lên Backend AI (/api/v1/iot/captures)
      setState("AI_ANALYZING", "wait");
      log("NET", `POST ${c.base}/iot/captures (multipart image, X-Device-Key=sim-test-key)`);
      const imgBlob = await loadFixtureBlob(item.fixture);

      const form = new FormData();
      form.append("image", imgBlob, item.fixture.split("/").pop());
      form.append("device_id", c.device);
      form.append("bin_code", c.bins[item.route] || "BIN-01");
      form.append("event_type", "waste_detected");
      form.append("uptime_s", String(Math.floor(performance.now() / 1000)));

      const t0 = performance.now();
      let resp, data;
      try {
        resp = await fetch(`${c.base}/iot/captures`, {
          method: "POST",
          headers: { "X-Device-Key": c.key },
          body: form
        });
        const elapsed = Math.round(performance.now() - t0);
        if(!resp.ok){
          const errText = await resp.text();
          log("ERR", `HTTP ${resp.status} (${elapsed}ms): ${errText.slice(0, 160)}`);
          setState("ERROR", "err");
          return;
        }
        data = await resp.json();
        log("AI", `Backend phản hồi sau ${elapsed}ms: status=${data.status} label=${data.label} route=${data.route} confidence=${data.confidence}`);
        if(data.ma_phien){
          log("QR", `✨ Backend đã tự động gắn kết quả vào phiên ${data.ma_phien.slice(0,8)}... (Tổng số vật hiện tại: ${data.so_vat})`);
        }
      } catch (netErr) {
        log("ERR", `Lỗi kết nối Backend: ${netErr.message}`);
        setState("ERROR", "err");
        return;
      }

      // 4. Cập nhật kết quả AI lên HUD
      $("rStatus").textContent = data.status;
      $("rLabel").textContent = data.label;
      $("rRoute").textContent = data.route;
      $("rConf").textContent = data.confidence;
      const confPct = Math.round((Number(data.confidence) || 0) * 100);
      $("confbarFill").style.width = confPct + "%";

      // 5. Xử lý Phân loại hoặc Từ chối (Safety Rule)
      const isHazard = data.status === "hazard" || data.status === "refused" || selectedKey === "battery";

      if(isHazard){
        setState("HAZARD_ALERT", "err");
        log("HAZARD", `🚨 PHÁT HIỆN RÁC NGUY HẠI / TỪ CHỐI (${data.label}). Cửa van giữ đóng an toàn! Rác KHÔNG rơi vào ngăn.`);
        if(window.Scene3D){
          window.Scene3D.setLedRing(0xef4444, 2.0);
          window.Scene3D.updateKioskScreen({ state: "RESULT", status: "hazard", label: data.label });
          window.Scene3D.updateQrScreenState("HAZARD", "Từ chối phân loại");
        }
        clearDucts();
        await sleep(2500);
      } else {
        setState("SORTING", "active");
        if(window.Scene3D){
          window.Scene3D.setLedRing(0x00e676, 1.5);
          window.Scene3D.updateKioskScreen({
            state: "RESULT",
            status: "ok",
            label: data.label,
            confidence: data.confidence,
            route: data.route
          });
          window.Scene3D.updateQrScreenState("SCANNED", "+10 Điểm Xanh");
        }

        const route = ["plastic","metal","paper","other"].includes(data.route) ? data.route : "other";
        const leftGroup = (route === "plastic" || route === "metal");

        // 6. Điều khiển cơ khí Servo trên sơ đồ cắt lát SVG
        log("SERVO", `Servo 1 nghiêng ${leftGroup ? "TRÁI (Plastic/Aluminum)" : "PHẢI (Paper/Other)"}`);
        setServo($("flap1"), leftGroup ? "left" : "right");
        setDuct(leftGroup ? "duct-1L" : "duct-1R", true);
        await sleep(400);

        if(leftGroup){
          const p3 = $("pivot3"); if(p3) p3.classList.add("dim");
          setServo($("flap2"), route === "plastic" ? "left" : "right");
          setDuct(route === "plastic" ? "duct-2plastic" : "duct-2metal", true);
          log("SERVO", `Servo 2 chọn nhánh ngăn: ${route === "plastic" ? "PLASTIC" : "ALUMINUM"}`);
        } else {
          const p2 = $("pivot2"); if(p2) p2.classList.add("dim");
          setServo($("flap3"), route === "paper" ? "left" : "right");
          setDuct(route === "paper" ? "duct-3paper" : "duct-3other", true);
          log("SERVO", `Servo 3 chọn nhánh ngăn: ${route === "paper" ? "PAPER" : "OTHER"}`);
        }

        // 7. Hoạt ảnh rác rơi trên cả Sơ đồ cắt lát SVG và Cảnh 3D
        setState("DROPPING", "active");
        depositedCounts[route]++;

        if(window.Scene3D){
          window.Scene3D.spawnItemInTransparentBin(route, selectedKey);
        }

        await animateMechanicalDrop(route, item.emoji);

        // 8. Tăng mức đầy ngăn tương ứng và đồng bộ realtime lên Backend ngay
        binState[route].fill = Math.min(100, binState[route].fill + 10);
        paintBin(route);
        reportOneBin(route);
        log("BIN", `📦 Ngăn kính ${route.toUpperCase()} đã nhận thêm 1 ${item.title} (Hiện có: ${depositedCounts[route]} vật phẩm, Mức đầy: ${binState[route].fill.toFixed(0)}%)`);
        
        await sleep(800);
        clearDucts();
      }
    } finally {
      isBusy = false;
      $("startBtn").disabled = false;
      $("walkBtn").disabled = false;
      if($("scanQrBtn")) $("scanQrBtn").disabled = false;
      finishCycle(true);
    }
  }

  function finishCycle(checkNear = true){
    const playerNear = checkNear && window.Scene3D && window.Scene3D.isPlayerNear && window.Scene3D.isPlayerNear();

    if(playerNear){
      setState("PRESENCE", "active");
      $("depositBtn").disabled = false;
      log("STATE", "MUN™ sẵn sàng cho món rác tiếp theo (Gia hạn 30s).");
      startSessionTimer();
      startBackendSessionPolling();
      if(window.Scene3D){
        window.Scene3D.setWasteItem(selectedKey);
        window.Scene3D.setLedRing(0x00e676, 1.0);
        window.Scene3D.updateKioskScreen({ state: "PRESENCE" });
        window.Scene3D.updateQrScreenState(isQrScanned ? "SCANNED" : "PRESENCE", "⏱️ Hết hạn sau: 30s");
      }
    } else {
      stopSessionTimer();
      stopBackendSessionPolling();
      setState("IDLE", "idle");
      $("depositBtn").disabled = true;
      log("STATE", "MUN™ Recycler trở về trạng thái IDLE — sẵn sàng đón người dùng tiếp theo.");
      if(window.Scene3D){
        window.Scene3D.setWasteItem(selectedKey);
        window.Scene3D.setLedRing(0x00e676, 1.0);
        window.Scene3D.updateKioskScreen({ state: "IDLE" });
        window.Scene3D.updateQrScreenState("IDLE", "Tích lũy +10 Điểm Xanh");
      }
    }
  }

  // ---------- Sự kiện TIẾP CẬN VÀ RỜI ĐI PIR ----------
  function onPlayerApproached(){
    $("pirLed").classList.add("on");
    $("pirStatus").textContent = "ĐÃ PHÁT HIỆN NGƯỜI DÙNG!";
    $("depositBtn").disabled = false;

    setState("PRESENCE", "active");
    log("PIR", "Cảm biến PIR (HC-SR501) tự động kích hoạt khi người dùng vào vùng ~2m!");
    log("STATE", "⏱️ Bắt đầu phiên làm việc: Có 30 giây để thực hiện bỏ rác hoặc quét QR.");

    startSessionTimer();
    startBackendSessionPolling();

    if(window.Scene3D){
      window.Scene3D.setPirLed(true);
      window.Scene3D.updateKioskScreen({ state: "PRESENCE" });
      window.Scene3D.updateQrScreenState("PRESENCE", `⏱️ Hết hạn sau: 30s`);
    }
  }

  function onPlayerLeft(){
    log("PIR", "🚶 Người dùng đã rời khỏi vùng cảm biến (>2.4m) → Tự động ngắt phiên làm việc và trở về trạng thái IDLE.");
    $("pirLed").classList.remove("on");
    $("pirStatus").textContent = "Đang quét vùng (~2m)...";
    $("depositBtn").disabled = true;
    isQrScanned = false;
    activeSessionId = null;
    stopSessionTimer();
    stopBackendSessionPolling();
    clearDucts();
    finishCycle(false);
  }

  // ---------- Các nút điều khiển trên Header & Dock ----------
  $("walkBtn").addEventListener("click", async () => {
    if(isBusy) return;
    log("STATE", "Nhân vật tự động tiến lại gần máy MUN™...");
    if(window.Scene3D){
      await window.Scene3D.autoWalkToBin();
      onPlayerApproached();
    }
  });

  if($("scanQrBtn")){
    $("scanQrBtn").addEventListener("click", async () => {
      if(isBusy) return;
      log("QR", "📱 Người dùng mở ứng dụng MUN trên điện thoại và quét màn hình nhỏ QR trên thùng rác!");
      if(window.Scene3D){
        window.Scene3D.setCameraPreset("qr");
        window.Scene3D.updateQrScreenState("SCANNED", "Đã xác thực tài khoản");
      }
      isQrScanned = true;
      log("QR", "✅ Xác thực thành công tài khoản: MUN_USER_VIP (ID: #VN-8829). Tích lũy +10 điểm sẵn sàng!");
      startSessionTimer();
      await sleep(1200);
    });
  }

  $("depositBtn").addEventListener("click", () => {
    executeWasteDeposit();
  });

  // Chạy toàn bộ chu trình tự động A-Z
  $("startBtn").addEventListener("click", async () => {
    if(isBusy) return;
    log("STATE", "=== BẮT ĐẦU CHẠY TOÀN BỘ QUY TRÌNH TỰ ĐỘNG TỪ A-Z ===");
    
    // 1. Tiến lại gần máy
    if(window.Scene3D){
      await window.Scene3D.autoWalkToBin();
      onPlayerApproached();
      await sleep(500);
    }

    // 2. Quét QR trên màn hình nhỏ
    log("QR", "📱 Tự động quét mã QR trên màn hình nhỏ...");
    if(window.Scene3D){
      window.Scene3D.updateQrScreenState("SCANNED", "Đã xác thực tài khoản");
    }
    await sleep(400);
    
    // 3. Thực hiện bỏ rác
    await executeWasteDeposit();
  });

  $("resetAllBtn").addEventListener("click", () => {
    Object.keys(binState).forEach(k => {
      binState[k].fill = 0;
      binState[k].lastStatus = "binh_thuong";
      depositedCounts[k] = 0;
      paintBin(k);
    });
    stopSessionTimer();
    stopBackendSessionPolling();
    clearDucts();

    const previewImg = $("previewImg");
    const previewPlaceholder = $("previewPlaceholder");
    const camBadge = $("camBadge");
    if(previewImg){
      previewImg.style.display = "none";
      if(previewPlaceholder) previewPlaceholder.style.display = "block";
      if(camBadge) camBadge.textContent = "chưa có ảnh";
    }

    if(window.Scene3D){
      window.Scene3D.resetPlayer();
      window.Scene3D.clearAllBins();
      window.Scene3D.updateKioskScreen({ state: "IDLE" });
      window.Scene3D.updateQrScreenState("IDLE", "Tích lũy +10 Điểm Xanh");
    }
    $("pirLed").classList.remove("on");
    $("pirStatus").textContent = "Đang quét vùng (~2m)...";
    $("depositBtn").disabled = true;
    isQrScanned = false;
    activeSessionId = null;
    logBox.innerHTML = "";
    finishCycle(false);
    log("STATE", "Đã Reset toàn bộ mô phỏng: 4 ngăn kính và sơ đồ cơ khí đã được dọn sạch hoàn toàn (0%).");
  });

  // Gắn sự kiện nút reset từng ngăn "🚚 đã gom" trên SVG
  document.querySelectorAll(".resetbtn").forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const binKey = btn.dataset.bin;
      if(binState[binKey]){
        binState[binKey].fill = 0;
        binState[binKey].lastStatus = "binh_thuong";
        depositedCounts[binKey] = 0;
        paintBin(binKey);
        reportOneBin(binKey);
        log("BIN", `🚚 Xe thu gom đã làm rỗng ngăn ${binKey.toUpperCase()} (Mức đầy: 0%).`);
      }
    });
  });

  // Khởi tạo Three.js
  window.addEventListener("DOMContentLoaded", () => {
    if(window.Scene3D){
      window.Scene3D.init("threeCanvasHost");
      window.Scene3D.armApproach(onPlayerApproached, onPlayerLeft);
    }
    Object.keys(binState).forEach(paintBin);
    selectWasteItem("plastic");
    log("STATE", "Hệ thống MUN™ AI Recycler 3D (Đồng bộ Realtime Backend & App Cư Dân) đã sẵn sàng.");
    log("NET", "Backend API: http://localhost:8000/api/v1/iot/captures (X-Device-Key: sim-test-key)");
  });
})();
