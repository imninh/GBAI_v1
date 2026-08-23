// app.js — luồng demo GreenBin AI: state machine, gọi backend thật, hoạt hình cơ khí,
// và chụp ảnh rác qua webcam hoặc tải ảnh lên. Phần chuyển động nhân vật 3D nằm ở scene3d.js
// và được điều khiển qua window.Scene3D.
(function(){
  "use strict";

  const $ = (id) => document.getElementById(id);
  const logBox = $("log");
  const statePill = $("statePill");

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
    statePill.className = "pill " + (kind || "idle");
  }
  setInterval(()=>{ $("clock").textContent = new Date().toLocaleTimeString(); }, 1000);

  // ---------- config ----------
  function cfg(){
    return {
      base: $("cfgBase").value.replace(/\/$/,""),
      device: $("cfgDevice").value.trim(),
      key: $("cfgKey").value.trim(),
      binKey: $("cfgBinKey").value.trim(),
      bins: {
        plastic: $("cfgBinPlastic").value.trim(),
        metal: $("cfgBinMetal").value.trim(),
        paper: $("cfgBinPaper").value.trim(),
        other: $("cfgBinOther").value.trim(),
      },
    };
  }

  const sleep = (ms) => new Promise(r => setTimeout(r, ms));

  // ---------- bin fill state (shared between classify-drop and background sonar loop) ----------
  const binState = {
    plastic: { fill: 0, lastStatus: "binh_thuong" },
    metal:   { fill: 0, lastStatus: "binh_thuong" },
    paper:   { fill: 0, lastStatus: "binh_thuong" },
    other:   { fill: 0, lastStatus: "binh_thuong" },
  };

  const FILL_BOTTOM_Y = 368;
  const FILL_MAX_H = 128;
  function paintBin(key){
    const s = binState[key];
    const h = (s.fill / 100) * FILL_MAX_H;
    const y = FILL_BOTTOM_Y - h;
    $("fill-" + key).setAttribute("height", h.toFixed(1));
    $("fill-" + key).setAttribute("y", y.toFixed(1));
    $("beam-" + key).setAttribute("y2", y.toFixed(1));
    $("pct-" + key).textContent = s.fill.toFixed(0) + "%";
    $("badge-" + key).classList.toggle("show", s.lastStatus === "can_gom");
  }
  Object.keys(binState).forEach(paintBin);

  document.querySelectorAll(".resetbtn").forEach(btn=>{
    btn.addEventListener("click", ()=>{
      const key = btn.dataset.bin;
      binState[key].fill = 0;
      binState[key].lastStatus = "binh_thuong";
      paintBin(key);
      log("BIN", `${key} đã được xe thu gom rỗng lại — reset fill=0% (demo cục bộ, không gọi backend).`);
    });
  });

  // ---------- background HC-SR04 fill reporting loop (independent of PIR/capture flow) ----------
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
          uptime_s: Math.floor(performance.now()/1000),
        }),
      });
      if(!res.ok){
        const t = await res.text();
        log("ERR", `${key} readings HTTP ${res.status}: ${t.slice(0,160)}`);
        return;
      }
      const data = await res.json();
      const newStatus = data.status;
      log("BIN", `${key} fill=${s.fill.toFixed(0)}% battery=100% -> status=${newStatus}`);
      if(newStatus === "can_gom" && s.lastStatus !== "can_gom"){
        log("BIN", `${key} fill=${s.fill.toFixed(0)}% -> pickup request sent (chuyển trạng thái -> can_gom, mã thùng ${code})`);
      }
      s.lastStatus = newStatus;
      paintBin(key);
    }catch(err){
      log("ERR", `Không gọi được /bins/${code}/readings — ${err.message}. Kiểm tra backend đang chạy và CORS_ORIGINS.`);
    }
  }
  function startFillLoop(){
    if(fillLoopTimer) return;
    log("STATE", "Bắt đầu vòng lặp nền: 4x HC-SR04 báo mức đầy độc lập (song song với luồng PIR/chụp ảnh).");
    fillLoopTimer = setInterval(()=>{
      Object.keys(binState).forEach(reportOneBin);
    }, 6000);
    Object.keys(binState).forEach(reportOneBin);
  }

  // ---------- capture ảnh rác thật: webcam hoặc tải ảnh lên máy ----------
  let captureResolve = null;
  let webcamStream = null;

  function showCaptureChoice(){ $("captureBtnRow").style.display = "flex"; }
  function hideCaptureChoice(){ $("captureBtnRow").style.display = "none"; }
  function showSnapRow(){ $("snapBtnRow").style.display = "flex"; }
  function hideSnapRow(){ $("snapBtnRow").style.display = "none"; }

  function stopWebcam(){
    if(webcamStream){ webcamStream.getTracks().forEach(t=>t.stop()); webcamStream = null; }
    $("webcamVideo").style.display = "none";
    $("webcamVideo").srcObject = null;
    hideSnapRow();
  }

  async function startWebcam(){
    hideCaptureChoice();
    try{
      webcamStream = await navigator.mediaDevices.getUserMedia({ video: true });
      const video = $("webcamVideo");
      video.srcObject = webcamStream;
      video.style.display = "block";
      showSnapRow();
      log("CAM", "Đã mở webcam — bấm 'Chụp ảnh' khi sẵn sàng.");
    }catch(err){
      log("ERR", `Không mở được webcam: ${err.message}. Hãy dùng 'Tải ảnh lên' thay thế.`);
      showCaptureChoice();
    }
  }

  function snapWebcamPhoto(){
    const video = $("webcamVideo");
    if(!video.videoWidth){ log("ERR", "Webcam chưa sẵn sàng khung hình, thử lại sau."); return; }
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(blob=>{
      stopWebcam();
      const file = new File([blob], "webcam_capture.png", { type: "image/png" });
      if(captureResolve){ const r = captureResolve; captureResolve = null; r(file); }
    }, "image/png");
  }

  function retakePhoto(){
    stopWebcam();
    showCaptureChoice();
  }

  function openFilePicker(){
    hideCaptureChoice();
    $("fileInput").value = "";
    $("fileInput").click();
  }

  function waitForCaptureSource(){
    return new Promise(resolve=>{
      captureResolve = resolve;
      showCaptureChoice();
    });
  }

  $("btnUseWebcam").addEventListener("click", startWebcam);
  $("btnUseUpload").addEventListener("click", openFilePicker);
  $("btnSnap").addEventListener("click", snapWebcamPhoto);
  $("btnRetake").addEventListener("click", retakePhoto);
  $("fileInput").addEventListener("change", ()=>{
    const f = $("fileInput").files[0];
    if(!f) return;
    hideCaptureChoice();
    if(captureResolve){ const r = captureResolve; captureResolve = null; r(f); }
  });

  // ---------- servo helpers ----------
  function setServo(el, dir){ // dir: 'left' | 'right' | 'center'
    el.classList.remove("left","right");
    if(dir === "left") el.classList.add("left");
    if(dir === "right") el.classList.add("right");
  }
  function setDuct(id, active){
    $(id).classList.toggle("active", active);
  }
  function clearDucts(){
    ["duct-1L","duct-1R","duct-2plastic","duct-2metal","duct-3paper","duct-3other"].forEach(id=>setDuct(id,false));
  }

  // ---------- falling item animation — fixed SVG waypoints, no DOM measuring needed ----------
  const WAY = {
    start:   { x: 166, y: 40  },
    servo1:  { x: 166, y: 106 },
    servo2:  { x: 86,  y: 170 },
    servo3:  { x: 246, y: 170 },
    plastic: { x: 46,  y: 224 },
    metal:   { x: 126, y: 224 },
    paper:   { x: 206, y: 224 },
    other:   { x: 286, y: 224 },
  };
  function moveFallItem(pt){
    $("fallItem").style.transform = `translate(${pt.x}px,${pt.y}px)`;
  }
  async function animateDrop(routeKey){
    const item = $("fallItem");
    const leftGroup = (routeKey === "plastic" || routeKey === "metal");

    item.style.transition = "none";
    moveFallItem(WAY.start);
    item.style.opacity = "1";
    void item.getBoundingClientRect();
    item.style.transition = "";

    await sleep(50);
    moveFallItem(WAY.servo1);          // fall down the hopper/chute to servo1
    await sleep(550);

    moveFallItem(leftGroup ? WAY.servo2 : WAY.servo3);   // routed to the correct branch
    await sleep(550);

    const compTop = WAY[routeKey];
    moveFallItem(compTop);             // enters the chosen compartment
    await sleep(400);
    moveFallItem({ x: compTop.x, y: compTop.y + 40 }); // settles into the pile
    await sleep(300);
    item.style.opacity = "0";

    const box = $("compBox-" + routeKey);
    box.classList.remove("flashGo"); void box.getBoundingClientRect(); box.classList.add("flashGo");
  }

  // ---------- PIR approach: uỷ quyền cho scene3d.js (WASD, va chạm gần thùng) ----------
  function waitForApproach(){
    return new Promise(resolve=>{
      window.Scene3D.armApproach(()=>{
        $("pirLed").classList.add("on");
        log("PIR", "HC-SR501 phát hiện chuyển động (nhân vật vừa tới gần thùng) -> đèn báo sáng.");
        resolve();
      });
    });
  }
  function disarmApproach(){
    window.Scene3D.disarmApproach();
  }

  // ---------- main cycle ----------
  let running = false;

  function resetCaptureView(){
    $("previewImg").style.display = "none";
    $("previewImg").src = "";
    $("previewPlaceholder").style.display = "block";
    $("camBadge").textContent = "chưa có ảnh";
    stopWebcam();
    hideCaptureChoice();
  }

  async function runOnce(){
    const c = cfg();

    // 1) PIR detects presence — tự kích hoạt khi nhân vật 3D (WASD) đi vào gần thùng
    setState("IDLE", "idle");
    $("oled").textContent = "Đang chờ người dùng...\n(đi tới gần bằng WASD)";
    log("STATE", "IDLE -> chờ bạn điều khiển nhân vật (WASD) lại gần cảm biến PIR...");
    await waitForApproach();

    setState("PIR_DETECT", "wait");
    log("STATE", "IDLE -> PIR_DETECT");
    await sleep(300);

    // 2) OLED choice screen
    setState("AWAIT_CHOICE", "wait");
    log("STATE", "PIR_DETECT -> AWAIT_CHOICE");
    $("oled").textContent = "Xin chào!\nNhấn SKIP để ẩn danh\nhoặc QR để xác thực";
    $("btnSkip").disabled = false;
    $("btnQr").disabled = false;
    log("STATE", "Chờ bạn bấm SKIP hoặc QR (không tự động, không giới hạn thời gian)...");

    let userChoice = await waitForChoice();
    $("btnSkip").disabled = true;
    $("btnQr").disabled = true;

    let userId = null;
    if(userChoice === "qr"){
      setState("QR_SCAN", "wait");
      log("STATE", "AWAIT_CHOICE -> QR_SCAN");
      $("oled").innerHTML = 'Quét mã QR để\nxác thực...\n<div class="qr"></div>';
      log("QR", "Hiện mã QR mô phỏng trên OLED — chờ quét...");
      await sleep(1600);
      userId = "user_demo_" + Math.floor(Math.random()*9000+1000);
      $("oled").textContent = "Đã xác thực!\n" + userId;
      log("QR", `Quét thành công (mô phỏng) -> gắn user_id=${userId}`);
      await sleep(700);
    } else {
      log("STATE", "Người dùng bấm SKIP -> tiếp tục ẩn danh.");
      $("oled").textContent = "Tiếp tục ẩn danh...";
    }
    await sleep(500);

    // 3) fixed timer before capture
    setState("TIMER", "wait");
    log("STATE", "-> TIMER (đếm ngược trước khi chụp)");
    $("oled").textContent = "Chuẩn bị chụp ảnh...";
    for(let s = 3; s >= 1; s--){
      log("TIMER", `capture in ${s}s...`);
      await sleep(700);
    }

    // 4) capture — chụp ảnh rác thật qua webcam hoặc tải ảnh từ máy
    setState("CAPTURE", "wait");
    log("STATE", "TIMER -> CAPTURE (chọn nguồn ảnh: webcam hoặc tải ảnh lên)");
    $("oled").textContent = "Chọn ảnh rác\nđể chụp...";
    log("CAM", "Đến lúc chụp — hãy dùng webcam hoặc tải ảnh rác lên.");
    const blob = await waitForCaptureSource();
    $("previewImg").src = URL.createObjectURL(blob);
    $("previewImg").style.display = "block";
    $("previewPlaceholder").style.display = "none";
    $("camBadge").textContent = blob.name.length > 14 ? blob.name.slice(0,12) + "…" : blob.name;

    setState("CAPTURE", "active");
    log("STATE", "CAPTURE -> đã có ảnh, chớp đèn flash");
    const flashEl = $("flashRect");
    flashEl.classList.remove("go"); void flashEl.getBoundingClientRect(); flashEl.classList.add("go");
    log("CAM", "ESP32-CAM chụp ảnh (flash) — đang chuẩn bị dữ liệu gửi lên backend...");
    await sleep(400);

    // 5) real fetch — no fake delay, elapsed time is the real network time
    setState("UPLOADING", "wait");
    log("STATE", "CAPTURE -> UPLOADING");
    const form = new FormData();
    form.append("image", blob, blob.name);
    form.append("device_id", c.device);
    form.append("bin_code", c.bins.other);
    form.append("event_type", "waste_detected");
    form.append("uptime_s", String(Math.floor(performance.now()/1000)));
    if(userId) form.append("item_id", userId + "_" + Date.now());

    const url = `${c.base}/iot/captures`;
    log("NET", `POST ${url} (multipart, X-Device-Key=${"*".repeat(Math.max(c.key.length-2,0))}${c.key.slice(-2)})`);
    const t0 = performance.now();
    let resp, data;
    try{
      resp = await fetch(url, {
        method: "POST",
        headers: { "X-Device-Key": c.key },
        body: form,
      });
      const elapsed = Math.round(performance.now() - t0);
      if(!resp.ok){
        const errText = await resp.text();
        log("ERR", `HTTP ${resp.status} sau ${elapsed}ms: ${errText.slice(0,300)}`);
        setState("ERROR", "err");
        await sleep(1800);
        finishIdle();
        return;
      }
      data = await resp.json();
      log("NET", `Phản hồi thật sau ${elapsed}ms.`);
    }catch(err){
      log("ERR", `Gọi backend thất bại: ${err.message}. Kiểm tra backend đang chạy ở ${c.base} và CORS_ORIGINS cho phép origin này.`);
      setState("ERROR", "err");
      await sleep(2000);
      finishIdle();
      return;
    }

    // 6) show real result
    setState("RESULT", "active");
    log("AI", `status=${data.status} label=${data.label} confidence=${data.confidence} route=${data.route} review_required=${data.review_required}`);
    $("rStatus").textContent = data.status;
    $("rLabel").textContent = data.label;
    $("rRoute").textContent = data.route;
    $("rConf").textContent = data.confidence;
    const pct = Math.round((Number(data.confidence)||0) * 100);
    $("confbarFill").style.width = Math.min(100, Math.max(0,pct)) + "%";
    $("oled").textContent = `Kết quả: ${data.label}\nĐộ tin cậy: ${pct}%`;

    const route = ["plastic","metal","paper","other"].includes(data.route) ? data.route : "other";

    // 7) servo1 tilt
    setState("SORTING", "active");
    const leftGroup = (route === "plastic" || route === "metal");
    log("SERVO", `Servo1 nghiêng ${leftGroup ? "TRÁI (Plastic/Aluminum)" : "PHẢI (Paper/Other)"}`);
    setServo($("flap1"), leftGroup ? "left" : "right");
    setDuct(leftGroup ? "duct-1L" : "duct-1R", true);
    await sleep(650);

    // 8) servo2/servo3 select exact bin
    if(leftGroup){
      $("pivot3").classList.add("dim");
      setServo($("flap2"), route === "plastic" ? "left" : "right");
      setDuct(route === "plastic" ? "duct-2plastic" : "duct-2metal", true);
      log("SERVO", `Servo2 chọn ngăn: ${route === "plastic" ? "Plastic" : "Aluminum"}`);
    } else {
      $("pivot2").classList.add("dim");
      setServo($("flap3"), route === "paper" ? "left" : "right");
      setDuct(route === "paper" ? "duct-3paper" : "duct-3other", true);
      log("SERVO", `Servo3 chọn ngăn: ${route === "paper" ? "Paper" : "Other"}`);
    }
    await sleep(650);

    // 9) item falls into the chosen bin
    setState("DROPPING", "active");
    await animateDrop(route);
    binState[route].fill = Math.min(100, binState[route].fill + (10 + Math.random()*14));
    paintBin(route);
    log("BIN", `${route} nhận thêm 1 vật -> fill hiện tại=${binState[route].fill.toFixed(0)}% (đo tại chỗ, chưa gửi — vòng HC-SR04 nền sẽ báo ở chu kỳ kế tiếp).`);

    // reset servo visuals
    setServo($("flap1"), "center");
    setServo($("flap2"), "center");
    setServo($("flap3"), "center");
    clearDucts();
    $("pivot2").classList.remove("dim");
    $("pivot3").classList.remove("dim");

    await sleep(400);
    finishIdle();
  }

  function finishIdle(){
    setState("IDLE", "idle");
    log("STATE", "-> IDLE (sẵn sàng cho lượt tiếp theo)");
    $("pirLed").classList.remove("on");
    window.Scene3D.setPirLed(false);
    disarmApproach();
    resetCaptureView();
    $("oled").textContent = "Đang chờ người dùng...\n(bấm 'Bắt đầu mô phỏng' cho lượt kế tiếp)";
  }

  function waitForChoice(){
    return new Promise(resolve=>{
      let done = false;
      function onSkip(){ if(!done){ done=true; cleanup(); resolve("skip"); } }
      function onQr(){ if(!done){ done=true; cleanup(); resolve("qr"); } }
      function cleanup(){ $("btnSkip").removeEventListener("click", onSkip); $("btnQr").removeEventListener("click", onQr); }
      $("btnSkip").addEventListener("click", onSkip);
      $("btnQr").addEventListener("click", onQr);
    });
  }

  $("startBtn").addEventListener("click", async ()=>{
    if(running) return;
    running = true;
    $("startBtn").disabled = true;
    startFillLoop();
    try{
      await runOnce();
    } finally {
      running = false;
      $("startBtn").disabled = false;
    }
  });

  $("resetAllBtn").addEventListener("click", ()=>{
    Object.keys(binState).forEach(k=>{ binState[k].fill = 0; binState[k].lastStatus = "binh_thuong"; paintBin(k); });
    window.Scene3D.resetPlayer();
    logBox.innerHTML = "";
    finishIdle();
    log("STATE", "Đã reset toàn bộ mô phỏng (không gọi backend).");
  });

  window.Scene3D.init("threeCanvasHost");
  log("STATE", "Sẵn sàng. Nhấn 'Bắt đầu mô phỏng', sau đó dùng WASD điều khiển nhân vật lại gần thùng rác để kích hoạt PIR.");
  log("NET", "Lưu ý: /iot/captures và /bins/{code}/readings là các cuộc gọi mạng THẬT tới backend đang cấu hình ở góc phải trên.");
})();
