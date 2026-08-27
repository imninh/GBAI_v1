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

  // ---------- Cấu hình Backend & Tự động kết nối ----------
  function initBackendConfig(){
    const isLocal = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
    const defaultBase = isLocal
      ? "http://localhost:8000/api/v1"
      : "https://greenbin-api-production-d08d.up.railway.app/api/v1";

    const params = new URLSearchParams(window.location.search);
    const queryApi = params.get("api_url") || params.get("api");
    const savedApi = localStorage.getItem("greenbin_backend_api");
    const cfgBaseEl = $("cfgBase");

    if (cfgBaseEl) {
      if (queryApi) {
        cfgBaseEl.value = queryApi.endsWith("/api/v1") ? queryApi : (queryApi.replace(/\/+$/, "") + "/api/v1");
      } else if (savedApi) {
        cfgBaseEl.value = savedApi;
      } else {
        cfgBaseEl.value = defaultBase;
      }
      cfgBaseEl.addEventListener("change", (e) => {
        localStorage.setItem("greenbin_backend_api", e.target.value.trim());
      });
    }
  }

  function cfg(){
    const isLocal = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
    const defaultBase = isLocal
      ? "http://localhost:8000/api/v1"
      : "https://greenbin-api-production-d08d.up.railway.app/api/v1";
    const baseVal = ($("cfgBase") && $("cfgBase").value.trim()) ? $("cfgBase").value.trim() : defaultBase;
    const commonBinCode = ($("cfgBinCode") && $("cfgBinCode").value.trim()) || "BIN-01";

    return {
      base: baseVal.replace(/\/$/,""),
      device: ($("cfgDevice") && $("cfgDevice").value.trim()) || "GBIN-001",
      key: ($("cfgKey") && $("cfgKey").value.trim()) || "sim-test-key",
      binKey: ($("cfgBinKey") && $("cfgBinKey").value.trim()) || "M4c7_1EJaTo2vUgKkS4zXmKghjCmPlh5LQ3Vg7hTs3o",
      binCode: commonBinCode,
      bins: {
        plastic: commonBinCode,
        metal: commonBinCode,
        paper: commonBinCode,
        other: commonBinCode
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

  // Tính toán mức đầy lớn nhất trong 4 ngăn của trạm
  function getMaxFillInfo(){
    let maxFill = 0;
    let bottleneckKey = "plastic";
    for(const k of ["plastic", "metal", "paper", "other"]){
      const val = binState[k] ? (binState[k].fill || 0) : 0;
      if(val >= maxFill){
        maxFill = val;
        bottleneckKey = k;
      }
    }
    const nameMap = { plastic: "NHỰA", metal: "KIM LOẠI", paper: "GIẤY/BÌA", other: "RÁC KHÁC" };
    return {
      maxFill: Math.min(100, maxFill),
      bottleneckKey,
      bottleneckName: nameMap[bottleneckKey] || bottleneckKey.toUpperCase()
    };
  }

  // Vòng lặp báo mức đầy thùng (Lấy max 4 ngăn) lên Backend Realtime
  let fillLoopTimer = null;
  let lastReportedStatus = "binh_thuong";

  async function reportStationMaxFill(){
    const c = cfg();
    const binCode = c.binCode || "BIN-01";
    const info = getMaxFillInfo();
    const url = `${c.base}/bins/${encodeURIComponent(binCode)}/readings`;
    try{
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Device-Key": c.binKey },
        body: JSON.stringify({
          fill_percent: Math.round(info.maxFill),
          battery_percent: 100,
          source: "simulator",
          device_id: c.device,
          uptime_s: Math.floor(performance.now() / 1000),
        }),
      });
      if(!res.ok) return;
      const data = await res.json();
      const newStatus = data.status;
      if((newStatus === "can_gom" || info.maxFill >= 80) && lastReportedStatus !== "can_gom"){
        log("BIN", `⚠️ Thùng ${binCode} đạt ${info.maxFill.toFixed(0)}% (Ngăn đầy nhất: ${info.bottleneckName}) → Kích hoạt trạng thái CẦN THU GOM (can_gom)!`);
      }
      lastReportedStatus = newStatus;
    }catch(err){
      // Chạy nền im lặng
    }
  }

  function startFillLoop(){
    if(fillLoopTimer) return;
    fillLoopTimer = setInterval(() => {
      reportStationMaxFill();
    }, 4000);
    reportStationMaxFill();
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

  // ---------- Quản lý Nguồn Ảnh Camera (Webcam / Upload / Sample) ----------
  let cameraSourceMode = "webcam"; // "webcam" | "upload" | "sample"
  let webcamStream = null;
  let isWebcamLive = false;
  let customUploadedBlob = null;
  let customUploadedFileName = "uploaded_item.jpg";

  // Khởi động luồng Webcam thật từ trình duyệt
  async function startWebcam(){
    if(isWebcamLive && webcamStream) return true;
    try {
      log("CAM", "📷 Đang yêu cầu quyền truy cập Camera / Webcam thiết bị...");
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 1280, min: 640 },
          height: { ideal: 720, min: 480 },
          facingMode: "environment"
        },
        audio: false
      });
      webcamStream = stream;
      isWebcamLive = true;

      const dockVideo = $("dockWebcamVideo");
      const mechVideo = $("mechCamVideo");
      const offPlaceholder = $("webcamOffPlaceholder");
      const liveBadge = $("webcamLiveBadge");
      const toggleBtn = $("toggleWebcamBtn");
      const snapBtn = $("snapAndDepositBtn");
      const previewPlaceholder = $("previewPlaceholder");
      const previewImg = $("previewImg");

      if(dockVideo){
        dockVideo.srcObject = stream;
        dockVideo.style.display = "block";
      }
      if(mechVideo){
        mechVideo.srcObject = stream;
        mechVideo.style.display = "block";
      }
      if(offPlaceholder) offPlaceholder.style.display = "none";
      if(liveBadge) liveBadge.style.display = "block";
      if(toggleBtn) {
        toggleBtn.textContent = "🛑 Tắt Webcam";
        toggleBtn.style.background = "#450a0a";
        toggleBtn.style.borderColor = "#991b1b";
      }
      if(snapBtn) snapBtn.disabled = isBusy;
      if(previewPlaceholder) previewPlaceholder.style.display = "none";
      if(previewImg) previewImg.style.display = "none";

      const camBadge = $("camBadge");
      if(camBadge) camBadge.textContent = "webcam live";

      log("CAM", "✅ ĐÃ KẾT NỐI WEBCAM THÀNH CÔNG! Đang truyền luồng video trực tiếp tới ESP32-CAM.");
      return true;
    } catch (err) {
      log("ERR", `⚠️ Không thể mở Webcam: ${err.name} - ${err.message}. (Bạn có thể chuyển sang tab 'Tải Ảnh Lên' hoặc '5 Mẫu Rác')`);
      stopWebcam();
      return false;
    }
  }

  function stopWebcam(){
    if(webcamStream){
      webcamStream.getTracks().forEach(track => track.stop());
      webcamStream = null;
    }
    isWebcamLive = false;

    const dockVideo = $("dockWebcamVideo");
    const mechVideo = $("mechCamVideo");
    const offPlaceholder = $("webcamOffPlaceholder");
    const liveBadge = $("webcamLiveBadge");
    const toggleBtn = $("toggleWebcamBtn");
    const snapBtn = $("snapAndDepositBtn");

    if(dockVideo){ dockVideo.style.display = "none"; dockVideo.srcObject = null; }
    if(mechVideo){ mechVideo.style.display = "none"; mechVideo.srcObject = null; }
    if(offPlaceholder) offPlaceholder.style.display = "block";
    if(liveBadge) liveBadge.style.display = "none";
    if(toggleBtn){
      toggleBtn.textContent = "📷 Bật Webcam Thật";
      toggleBtn.style.background = "#1e293b";
      toggleBtn.style.borderColor = "#334155";
    }
    if(snapBtn) snapBtn.disabled = true;

    const camBadge = $("camBadge");
    if(camBadge) camBadge.textContent = "chưa có ảnh";
    log("CAM", "Đã tắt Webcam.");
  }

  // Chụp 1 khung hình JPEG từ luồng video Webcam thật
  async function captureWebcamJpegBlob(){
    const dockVideo = $("dockWebcamVideo");
    if(!dockVideo || !isWebcamLive){
      throw new Error("Webcam chưa được kích hoạt!");
    }

    const vw = dockVideo.videoWidth || 1280;
    const vh = dockVideo.videoHeight || 720;
    const canvas = $("webcamCaptureCanvas") || document.createElement("canvas");
    canvas.width = vw;
    canvas.height = vh;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(dockVideo, 0, 0, vw, vh);

    return new Promise((resolve, reject) => {
      canvas.toBlob((blob) => {
        if(blob){
          // Cập nhật ảnh chụp lên khung preview sơ đồ cơ khí
          const previewImg = $("previewImg");
          const mechVideo = $("mechCamVideo");
          if(previewImg){
            previewImg.src = URL.createObjectURL(blob);
            previewImg.style.display = "block";
          }
          if(mechVideo) mechVideo.style.display = "none";
          resolve(blob);
        } else {
          reject(new Error("Lỗi khi xuất ảnh từ canvas"));
        }
      }, "image/jpeg", 0.92);
    });
  }

  // Khởi tạo các Tab chọn nguồn ảnh (Webcam / Upload / Mẫu)
  function initCameraSourceTabs(){
    const tabWebcam = $("tabWebcam");
    const tabUpload = $("tabUpload");
    const tabSample = $("tabSample");
    const panelWebcam = $("panelWebcam");
    const panelUpload = $("panelUpload");
    const panelSample = $("panelSample");
    const sourceStatusBadge = $("sourceStatusBadge");

    function setSource(mode){
      cameraSourceMode = mode;
      [tabWebcam, tabUpload, tabSample].forEach(t => {
        if(t) t.classList.toggle("active", t.dataset.source === mode);
      });
      if(panelWebcam) panelWebcam.style.display = (mode === "webcam") ? "flex" : "none";
      if(panelUpload) panelUpload.style.display = (mode === "upload") ? "flex" : "none";
      if(panelSample) panelSample.style.display = (mode === "sample") ? "flex" : "none";

      if(sourceStatusBadge){
        if(mode === "webcam"){
          sourceStatusBadge.textContent = "● WEBCAM TRỰC TIẾP";
          sourceStatusBadge.style.color = "#10b981";
        } else if(mode === "upload"){
          sourceStatusBadge.textContent = "● TẢI ẢNH LÊN";
          sourceStatusBadge.style.color = "#38bdf8";
        } else {
          sourceStatusBadge.textContent = "● 5 MẪU SẴN CÓ";
          sourceStatusBadge.style.color = "#fbbf24";
        }
      }

      if(mode === "webcam"){
        startWebcam();
      } else {
        const previewImg = $("previewImg");
        const mechVideo = $("mechCamVideo");
        if(mechVideo) mechVideo.style.display = "none";
        if(mode === "sample"){
          selectWasteItem(selectedKey);
        } else if(mode === "upload" && customUploadedBlob){
          if(previewImg){
            previewImg.src = URL.createObjectURL(customUploadedBlob);
            previewImg.style.display = "block";
          }
        }
      }
    }

    if(tabWebcam) tabWebcam.addEventListener("click", () => setSource("webcam"));
    if(tabUpload) tabUpload.addEventListener("click", () => setSource("upload"));
    if(tabSample) tabSample.addEventListener("click", () => setSource("sample"));

    const toggleBtn = $("toggleWebcamBtn");
    if(toggleBtn){
      toggleBtn.addEventListener("click", () => {
        if(isWebcamLive) stopWebcam();
        else startWebcam();
      });
    }

    const snapBtn = $("snapAndDepositBtn");
    if(snapBtn){
      snapBtn.addEventListener("click", () => {
        executeWasteDeposit();
      });
    }

    // Xử lý Upload file ảnh từ máy
    const chooseFileBtn = $("chooseFileBtn");
    const wasteFileInput = $("wasteFileInput");
    const uploadAndDepositBtn = $("uploadAndDepositBtn");
    const uploadPreviewImg = $("uploadPreviewImg");
    const uploadOffPlaceholder = $("uploadOffPlaceholder");

    if(chooseFileBtn && wasteFileInput){
      chooseFileBtn.addEventListener("click", () => wasteFileInput.click());
      wasteFileInput.addEventListener("change", (e) => {
        const file = e.target.files && e.target.files[0];
        if(file){
          customUploadedBlob = file;
          customUploadedFileName = file.name;
          const url = URL.createObjectURL(file);
          if(uploadPreviewImg){
            uploadPreviewImg.src = url;
            uploadPreviewImg.style.display = "block";
          }
          if(uploadOffPlaceholder) uploadOffPlaceholder.style.display = "none";
          if(uploadAndDepositBtn) uploadAndDepositBtn.disabled = false;

          const previewImg = $("previewImg");
          const previewPlaceholder = $("previewPlaceholder");
          const camBadge = $("camBadge");
          if(previewImg){
            previewImg.src = url;
            previewImg.style.display = "block";
          }
          if(previewPlaceholder) previewPlaceholder.style.display = "none";
          if(camBadge) camBadge.textContent = "ảnh tải lên";

          log("CAM", `📁 Đã chọn file ảnh: ${file.name} (${Math.round(file.size / 1024)} KB)`);
        }
      });
    }

    if(uploadAndDepositBtn){
      uploadAndDepositBtn.addEventListener("click", () => {
        executeWasteDeposit();
      });
    }
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
    if(cameraSourceMode === "sample"){
      const previewImg = $("previewImg");
      const previewPlaceholder = $("previewPlaceholder");
      const camBadge = $("camBadge");
      if(previewImg){
        previewImg.src = item.fixture;
        previewImg.style.display = "block";
        if(previewPlaceholder) previewPlaceholder.style.display = "none";
        if(camBadge) camBadge.textContent = "ảnh mẫu";
      }
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
    if($("snapAndDepositBtn")) $("snapAndDepositBtn").disabled = true;
    if($("uploadAndDepositBtn")) $("uploadAndDepositBtn").disabled = true;

    startFillLoop();

    const c = cfg();
    const item = WASTE_ITEMS[selectedKey] || WASTE_ITEMS.plastic;

    try {
      // 1. Hoạt ảnh 5 pha trên Three.js
      setState("DEPOSITING", "active");
      const displayTitle = (cameraSourceMode === "webcam")
        ? "Vật thể thật trước Webcam"
        : (cameraSourceMode === "upload" ? customUploadedFileName : item.title);

      log("STATE", `Người dùng đưa ${displayTitle} vào lỗ nhận rác của MUN™...`);
      
      if(window.Scene3D){
        window.Scene3D.updateKioskScreen({ state: "COUNTDOWN", sec: 3 });
        await window.Scene3D.playInsertAnimation();
      }

      // 2. HC-SR04 xác nhận vật thể rơi vào & Flash ESP32-CAM
      log("HC-SR04", "Cảm biến siêu âm xác nhận vật thể: before=50.0cm after=24.5cm delta=25.5cm -> waste_confirmed ✅");
      
      // Chớp đèn flash toàn màn hình
      if(typeof window.appFlashTrigger === "function"){
        window.appFlashTrigger();
      }

      let imgBlob;
      let uploadFileName = "waste_capture.jpg";

      if(cameraSourceMode === "webcam"){
        if(!isWebcamLive){
          log("CAM", "📷 Tự động bật Webcam để chụp ảnh...");
          await startWebcam();
          await sleep(600);
        }
        try {
          imgBlob = await captureWebcamJpegBlob();
          uploadFileName = `webcam_${Date.now()}.jpg`;
          log("CAM", `📸 ESP32-CAM đã chụp 1 ảnh thật từ WEBCAM (${Math.round(imgBlob.size / 1024)} KB)`);
        } catch(snapErr){
          log("WARN", `Không chụp được từ webcam: ${snapErr.message} → Dùng ảnh mẫu thay thế.`);
          imgBlob = await loadFixtureBlob(item.fixture);
          uploadFileName = item.fixture.split("/").pop();
        }
      } else if(cameraSourceMode === "upload" && customUploadedBlob){
        imgBlob = customUploadedBlob;
        uploadFileName = customUploadedFileName;
        log("CAM", `📁 Sử dụng ảnh tải lên từ máy: ${uploadFileName}`);
      } else {
        imgBlob = await loadFixtureBlob(item.fixture);
        uploadFileName = item.fixture.split("/").pop();
        log("CAM", `ESP32-CAM chớp đèn flash 📸 — Đã nạp ảnh mẫu: ${item.title}.`);
      }

      const camBadge = $("camBadge");
      if(camBadge) camBadge.textContent = "đã chụp";

      if(window.Scene3D){
        window.Scene3D.setLedRing(0x38bdf8, 1.5);
        window.Scene3D.updateKioskScreen({ state: "ANALYZING", itemTitle: displayTitle });
      }

      // 3. Gửi ảnh thật lên Backend AI (/api/v1/iot/captures)
      setState("AI_ANALYZING", "wait");
      log("NET", `POST ${c.base}/iot/captures (multipart image: ${uploadFileName}, X-Device-Key=${c.key})`);

      const form = new FormData();
      form.append("image", imgBlob, uploadFileName);
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
        log("AI", `Backend Vision AI phản hồi sau ${elapsed}ms: status=${data.status} label=${data.label} route=${data.route} confidence=${data.confidence}`);
        if(data.ma_phien){
          log("QR", `🎯 Backend đã tự động gắn kết quả vào phiên ${data.ma_phien.slice(0,8)}... (Tổng số vật hiện tại: ${data.so_vat})`);
        }
      } catch (netErr) {
        log("WARN", `⚠️ Không thể kết nối Backend (${c.base}): ${netErr.message} → Tự động chạy mô phỏng AI offline.`);
        data = {
          status: item.key === "battery" ? "hazard" : "ok",
          label: item.expectedLabel,
          route: item.route,
          confidence: "0.96",
          ma_phien: activeSessionId || null
        };
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

        // 8. Tăng mức đầy ngăn tương ứng và đồng bộ mức đầy lớn nhất (max của 4 ngăn) lên Backend
        binState[route].fill = Math.min(100, binState[route].fill + 10);
        paintBin(route);
        reportStationMaxFill();
        const info = getMaxFillInfo();
        log("BIN", `📦 Ngăn kính ${route.toUpperCase()} nhận thêm 1 ${item.title} (Ngăn này: ${binState[route].fill.toFixed(0)}% | Độ đầy toàn thùng ${c.binCode}: ${info.maxFill.toFixed(0)}% - Ngăn ${info.bottleneckName} đầy nhất)`);
        
        await sleep(800);
        clearDucts();
      }
    } finally {
      isBusy = false;
      $("startBtn").disabled = false;
      $("walkBtn").disabled = false;
      if($("scanQrBtn")) $("scanQrBtn").disabled = false;
      if($("snapAndDepositBtn")) $("snapAndDepositBtn").disabled = !isWebcamLive;
      if($("uploadAndDepositBtn")) $("uploadAndDepositBtn").disabled = !customUploadedBlob;
      finishCycle(true);
    }
  }

  function finishCycle(checkNear = true){
    const playerNear = checkNear && window.Scene3D && window.Scene3D.isPlayerNear && window.Scene3D.isPlayerNear();

    if(playerNear){
      setState("PRESENCE", "active");
      $("depositBtn").disabled = false;
      if($("snapAndDepositBtn")) $("snapAndDepositBtn").disabled = !isWebcamLive;
      if($("uploadAndDepositBtn")) $("uploadAndDepositBtn").disabled = !customUploadedBlob;
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
      if($("snapAndDepositBtn")) $("snapAndDepositBtn").disabled = true;
      if($("uploadAndDepositBtn")) $("uploadAndDepositBtn").disabled = true;
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
    if($("snapAndDepositBtn")) $("snapAndDepositBtn").disabled = !isWebcamLive;
    if($("uploadAndDepositBtn")) $("uploadAndDepositBtn").disabled = !customUploadedBlob;

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

  let isQrZoomedActive = false;

  if($("scanQrBtn")){
    $("scanQrBtn").addEventListener("click", async () => {
      if(isBusy) return;

      // Nếu đang phóng to QR -> Bấm một lần nữa để hoàn tác về toàn cảnh
      if(isQrZoomedActive){
        isQrZoomedActive = false;
        log("QR", "↩️ Hoàn tác: Thu nhỏ góc nhìn về toàn cảnh trạm MUN™.");
        if(window.Scene3D){
          window.Scene3D.setCameraPreset("overview");
        }
        return;
      }

      // Lần bấm đầu tiên -> Phóng to vào QR để người dùng dùng điện thoại quét thật
      isQrZoomedActive = true;
      log("QR", "📱 Đang phóng to mã QR. Hãy dùng App Cư Dân quét mã QR trên màn hình! (Bấm lại nút này để thu nhỏ).");
      
      // Kích hoạt cảm biến và màn hình QR nếu đang ở trạng thái IDLE
      if(!isQrScanned && statePill.textContent === "IDLE"){
        onPlayerApproached();
      }

      if(window.Scene3D){
        window.Scene3D.setCameraPreset("qr");
        window.Scene3D.updateQrScreenState(isQrScanned ? "SCANNED" : "PRESENCE", isQrScanned ? "Đã xác thực tài khoản" : "Đưa điện thoại quét");
      }

      startSessionTimer();
      startBackendSessionPolling();
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

    // 2. Phóng to màn hình QR
    log("QR", "📱 Hiển thị mã QR phiên làm việc trên trạm...");
    if(window.Scene3D){
      window.Scene3D.setCameraPreset("qr");
      window.Scene3D.updateQrScreenState(isQrScanned ? "SCANNED" : "PRESENCE", isQrScanned ? "Đã xác thực" : "Đưa điện thoại quét");
    }
    await sleep(800);
    
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
    isQrZoomedActive = false;
    stopSessionTimer();
    stopBackendSessionPolling();
    reportStationMaxFill();
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

  // Khởi tạo Three.js & Camera Tabs
  window.addEventListener("DOMContentLoaded", () => {
    initBackendConfig();
    initCameraSourceTabs();
    if(window.Scene3D){
      window.Scene3D.init("threeCanvasHost");
      window.Scene3D.armApproach(onPlayerApproached, onPlayerLeft);
    }
    Object.keys(binState).forEach(paintBin);
    selectWasteItem("plastic");
    const c = cfg();
    log("STATE", "Hệ thống MUN™ AI Recycler 3D (Webcam Live AI & Đồng bộ Realtime) đã sẵn sàng.");
    log("NET", `Backend API: ${c.base}/iot/captures (X-Device-Key: ${c.key})`);
  });
})();
