// scene3d.js — Mô phỏng 3D thiết bị thu đổi tái chế MUN™
(function(window){
  "use strict";

  const TRIGGER_DIST = 1.95;
  const LEAVE_DIST = 2.40;
  const PLAYER_SPEED = 3.8;

  const keys = {};
  let scene, camera, renderer, clock, playerGroup, kioskGroup, hostEl;
  let approachArmed = false;
  let wasNear = false;
  let onApproachCb = null;
  let onLeaveCb = null;
  let isAutoWalking = false;
  let autoWalkResolve = null;

  // Camera Orbit & Pan State
  let isOrbitDragging = false;
  let isPanDragging = false;
  let prevMouse = { x: 0, y: 0 };
  let touchStartDist = 0;

  let camSpherical = { radius: 6.8, theta: 0.15, phi: 1.25 };
  let targetSpherical = { radius: 6.8, theta: 0.15, phi: 1.25 };
  let camTarget = null;
  let targetLookAt = null;

  let cameraMode = "free";
  let autoRotateSpeed = 0.005;

  // Waste item state
  let currentHeldMesh = null;
  let currentItemKey = "plastic";

  // LEDs & Kiosk dynamic elements
  let ledRingMesh = null;
  let pirLedMesh = null;
  let holeInnerLight = null;

  // Màn hình phụ Mini Screen (Động theo từng trạng thái)
  // Quy tắc: Mã QR CHỈ HIỆN khi bắt đầu phiên (PRESENCE) và TẮT NGAY khi quét xong (SCANNED)
  let qrCanvas, qrCtx, qrTexture, qrMesh, qrScanY = 0;
  let qrState = "IDLE";
  let qrSubText = "";
  let qrExtraData = {};

  // Kiosk dimensions
  const K_W = 1.48;
  const K_H = 2.65;
  const K_D = 0.90;
  const KIOSK_GREEN = 0x22a06b;
  const KIOSK_DARK_GREEN = 0x166534;

  // 4 Ngăn rác trong suốt
  const binPiles = {
    plastic: null,
    metal: null,
    paper: null,
    other: null
  };

  const binItemCounts = {
    plastic: 0,
    metal: 0,
    paper: 0,
    other: 0
  };

  function ensureVectors(){
    if(!camTarget && typeof THREE !== "undefined"){
      camTarget = new THREE.Vector3(0, 1.25, 0);
      targetLookAt = new THREE.Vector3(0, 1.25, 0);
    }
  }

  function makeMat(color, opts){
    return new THREE.MeshStandardMaterial(Object.assign({
      color: color,
      roughness: 0.32,
      metalness: 0.10
    }, opts || {}));
  }

  function makeCapsule(radius, length, capSeg, radSeg){
    if(typeof THREE.CapsuleGeometry === "function"){
      return new THREE.CapsuleGeometry(radius, length, capSeg || 8, radSeg || 12);
    }
    return new THREE.CylinderGeometry(radius, radius, length + radius * 1.5, radSeg || 14);
  }

  let realQrContainer = null;
  let qrCodeDataText = "BIN-01";

  // ---------- 1. Canvas Texture Màn Hình Nhỏ Hiển Thị QR Code & Trạng Thái ----------
  function initQrScreenTexture(){
    qrCanvas = document.createElement("canvas");
    qrCanvas.width = 256;
    qrCanvas.height = 256;
    qrCtx = qrCanvas.getContext("2d");

    // Khởi tạo DOM container ẩn để sinh mã QR chuẩn ISO
    try {
      if(typeof QRCode !== "undefined"){
        realQrContainer = document.createElement("div");
        realQrContainer.style.display = "none";
        document.body.appendChild(realQrContainer);
        new QRCode(realQrContainer, {
          text: qrCodeDataText,
          width: 170,
          height: 170,
          colorDark: "#090d16",
          colorLight: "#ffffff",
          correctLevel: typeof QRCode.CorrectLevel !== "undefined" ? QRCode.CorrectLevel.M : 0
        });
      }
    } catch(e) {
      console.warn("QR code generator init:", e);
    }

    drawQrScreenUI();

    qrTexture = new THREE.CanvasTexture(qrCanvas);
    qrTexture.minFilter = THREE.LinearFilter;
    qrTexture.magFilter = THREE.LinearFilter;
  }

  function drawQrScreenUI(){
    if(!qrCtx) return;
    const ctx = qrCtx;
    const size = 256;

    // A. TRẠNG THÁI CHỜ IDLE: Màn hình tắt tiết kiệm điện (KHÔNG HIỆN MÃ QR)
    if(qrState === "IDLE"){
      ctx.fillStyle = "#090d16";
      ctx.fillRect(0, 0, size, size);

      ctx.strokeStyle = "#1e293b";
      ctx.lineWidth = 4;
      ctx.strokeRect(3, 3, size - 6, size - 6);

      ctx.fillStyle = "#334155";
      ctx.font = "bold 13px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("MUN™ STANDBY", size/2, 45);

      ctx.font = "46px sans-serif";
      ctx.fillText("🌱", size/2, 115);

      ctx.fillStyle = "#10b981";
      ctx.font = "bold 13px sans-serif";
      ctx.fillText("CHẠM HOẶC LẠI GẦN", size/2, 175);

      ctx.fillStyle = "#64748b";
      ctx.font = "11px sans-serif";
      ctx.fillText("ĐỂ BẮT ĐẦU PHIÊN", size/2, 205);
    }

    // B. TRẠNG THÁI BẮT ĐẦU PHIÊN: HIỂN THỊ MÃ QR THẬT SỰ + LASER QUÉT
    else if(qrState === "PRESENCE" || qrState === "AWAIT_QR"){
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, size, size);

      ctx.strokeStyle = "#0284c7";
      ctx.lineWidth = 5;
      ctx.strokeRect(4, 4, size - 8, size - 8);

      ctx.fillStyle = "#0f172a";
      ctx.font = "bold 13px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("📱 SCAN QR: " + qrCodeDataText, size/2, 24);

      const qrBoxX = 43, qrBoxY = 36, qrBoxSize = 170;

      // Vẽ Canvas QR thật được sinh bởi thư viện QRCode
      let drawnRealQr = false;
      if(realQrContainer){
        const realCanvas = realQrContainer.querySelector("canvas");
        const realImg = realQrContainer.querySelector("img");
        if(realCanvas && realCanvas.width > 0){
          ctx.drawImage(realCanvas, qrBoxX, qrBoxY, qrBoxSize, qrBoxSize);
          drawnRealQr = true;
        } else if(realImg && realImg.complete && realImg.naturalWidth > 0){
          ctx.drawImage(realImg, qrBoxX, qrBoxY, qrBoxSize, qrBoxSize);
          drawnRealQr = true;
        }
      }

      if(!drawnRealQr){
        function drawFinder(fx, fy){
          ctx.fillStyle = "#0f172a";
          ctx.fillRect(fx, fy, 38, 38);
          ctx.fillStyle = "#ffffff";
          ctx.fillRect(fx + 6, fy + 6, 26, 26);
          ctx.fillStyle = "#0284c7";
          ctx.fillRect(fx + 11, fy + 11, 16, 16);
        }
        drawFinder(qrBoxX + 6, qrBoxY + 6);
        drawFinder(qrBoxX + qrBoxSize - 44, qrBoxY + 6);
        drawFinder(qrBoxX + 6, qrBoxY + qrBoxSize - 44);

        ctx.fillStyle = "#0f172a";
        const dotGrid = 14;
        for(let r = 0; r < dotGrid; r++){
          for(let c = 0; c < dotGrid; c++){
            if((r < 5 && c < 5) || (r < 5 && c > 8) || (r > 8 && c < 5)) continue;
            if(((r * 7 + c * 13 + 3) % 5) < 3){
              ctx.fillRect(qrBoxX + 18 + c * 10, qrBoxY + 18 + r * 10, 8, 8);
            }
          }
        }
      }

      // Tia laser xanh quét
      qrScanY = (qrScanY + 2.5) % qrBoxSize;
      const curLaserY = qrBoxY + qrScanY;

      ctx.fillStyle = "rgba(2, 132, 199, 0.25)";
      ctx.fillRect(qrBoxX, curLaserY - 4, qrBoxSize, 8);

      ctx.strokeStyle = "#0284c7";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(qrBoxX, curLaserY);
      ctx.lineTo(qrBoxX + qrBoxSize, curLaserY);
      ctx.stroke();

      ctx.fillStyle = "#0284c7";
      ctx.font = "bold 12px sans-serif";
      ctx.fillText(qrSubText || "👉 ĐƯA ĐIỆN THOẠI QUÉT", size/2, 238);
    }

    // C. TRẠNG THÁI ĐÃ QUÉT XONG QR: MÃ QR TẮT ĐI, HIỂN THỊ XÁC THỰC THÀNH CÔNG
    else if(qrState === "SCANNED"){
      ctx.fillStyle = "#f0fdf4";
      ctx.fillRect(0, 0, size, size);

      ctx.strokeStyle = "#16a34a";
      ctx.lineWidth = 5;
      ctx.strokeRect(4, 4, size - 8, size - 8);

      ctx.fillStyle = "#166534";
      ctx.font = "bold 14px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("✅ ĐÃ QUÉT QR XONG", size/2, 34);

      ctx.font = "52px sans-serif";
      ctx.fillText("✨", size/2, 98);

      ctx.fillStyle = "#15803d";
      ctx.font = "bold 14px sans-serif";
      ctx.fillText("USER: #VN-8829", size/2, 142);

      ctx.fillStyle = "#166534";
      ctx.font = "bold 13px sans-serif";
      ctx.fillText("+10 ĐIỂM XANH SẴN SÀNG", size/2, 172);

      // Nút nhắc bỏ rác
      ctx.fillStyle = "#16a34a";
      ctx.beginPath();
      ctx.roundRect(24, 196, size - 48, 40, 8);
      ctx.fill();

      ctx.fillStyle = "#ffffff";
      ctx.font = "bold 13px sans-serif";
      ctx.fillText("📥 HÃY BỎ RÁC VÀO LỖ", size/2, 221);
    }

    // D. TRẠNG THÁI ĐANG PHÂN TÍCH AI (ANALYZING)
    else if(qrState === "ANALYZING"){
      ctx.fillStyle = "#f0f9ff";
      ctx.fillRect(0, 0, size, size);

      ctx.strokeStyle = "#0284c7";
      ctx.lineWidth = 5;
      ctx.strokeRect(4, 4, size - 8, size - 8);

      ctx.fillStyle = "#0369a1";
      ctx.font = "bold 14px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("🤖 AI ĐANG PHÂN TÍCH", size/2, 36);

      ctx.font = "48px sans-serif";
      ctx.fillText("📸", size/2, 105);

      ctx.fillStyle = "#0284c7";
      ctx.font = "bold 13px sans-serif";
      ctx.fillText("ESP32-CAM ĐANG QUÉT...", size/2, 160);

      ctx.fillStyle = "#64748b";
      ctx.font = "12px sans-serif";
      ctx.fillText(qrSubText || "Đang nhận diện vật thể", size/2, 205);
    }

    // E. TRẠNG THÁI KẾT QUẢ TỪ CHỐI / NGUY HẠI (HAZARD)
    else if(qrState === "HAZARD"){
      ctx.fillStyle = "#fef2f2";
      ctx.fillRect(0, 0, size, size);

      ctx.strokeStyle = "#dc2626";
      ctx.lineWidth = 5;
      ctx.strokeRect(4, 4, size - 8, size - 8);

      ctx.fillStyle = "#991b1b";
      ctx.font = "bold 14px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("🚨 TỪ CHỐI RÁC NGUY HẠI", size/2, 36);

      ctx.font = "52px sans-serif";
      ctx.fillText("⛔", size/2, 108);

      ctx.fillStyle = "#b91c1c";
      ctx.font = "bold 13px sans-serif";
      ctx.fillText(qrSubText || "KHÔNG ĐƯỢC BỎ VÀO", size/2, 162);

      ctx.fillStyle = "#7f1d1d";
      ctx.font = "12px sans-serif";
      ctx.fillText("CỬA VAN ĐÃ KHÓA AN TOÀN", size/2, 205);
    }

    // F. TRẠNG THÁI HẾT HẠN PHIÊN (TIMEOUT)
    else if(qrState === "TIMEOUT"){
      ctx.fillStyle = "#fffbeb";
      ctx.fillRect(0, 0, size, size);

      ctx.strokeStyle = "#d97706";
      ctx.lineWidth = 5;
      ctx.strokeRect(4, 4, size - 8, size - 8);

      ctx.fillStyle = "#92400e";
      ctx.font = "bold 14px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("⏱️ HẾT HẠN PHIÊN (30s)", size/2, 40);

      ctx.font = "50px sans-serif";
      ctx.fillText("⏳", size/2, 110);

      ctx.fillStyle = "#b45309";
      ctx.font = "bold 13px sans-serif";
      ctx.fillText("QUÁ THỜI GIAN THAO TÁC", size/2, 165);

      ctx.fillStyle = "#78350f";
      ctx.font = "12px sans-serif";
      ctx.fillText("Tự động trở về trạng thái chờ", size/2, 205);
    }

    if(qrTexture) qrTexture.needsUpdate = true;
  }

  function updateQrScreenState(newState, subText, extra){
    qrState = newState;
    if(subText !== undefined) qrSubText = subText;
    if(extra) qrExtraData = extra;
    drawQrScreenUI();
  }

  function updateKioskScreen(data){
    if(!data) return;
    if(data.state === "IDLE"){
      updateQrScreenState("IDLE");
    } else if(data.state === "PRESENCE"){
      updateQrScreenState("PRESENCE", "👉 ĐƯA ĐIỆN THOẠI QUÉT");
    } else if(data.state === "ANALYZING"){
      updateQrScreenState("ANALYZING", data.itemTitle || "AI đang nhận diện...");
    } else if(data.state === "RESULT"){
      if(data.status === "hazard" || data.status === "refused"){
        updateQrScreenState("HAZARD", "Từ chối phân loại");
      } else {
        updateQrScreenState("SCANNED", "+10 Điểm Xanh");
      }
    }
  }

  // ---------- 2. Xây dựng Mô hình 3D Kiosk ----------
  function buildMunKiosk(){
    const g = new THREE.Group();

    // A. Chân đế đáy
    const baseH = 0.08;
    const baseMesh = new THREE.Mesh(
      new THREE.BoxGeometry(K_W * 0.98, baseH, K_D * 0.96),
      makeMat(0x1e293b, { roughness: 0.7, metalness: 0.5 })
    );
    baseMesh.position.y = baseH / 2;
    baseMesh.castShadow = true;
    baseMesh.receiveShadow = true;
    g.add(baseMesh);

    const lowerH = 0.98;
    const upperH = K_H - baseH - lowerH;
    const upperY = baseH + lowerH + upperH / 2;

    // B. Thân trên màu xanh ngọc lục bảo
    const upperHousing = new THREE.Mesh(
      new THREE.BoxGeometry(K_W, upperH, K_D),
      makeMat(KIOSK_GREEN, { roughness: 0.30, metalness: 0.08 })
    );
    upperHousing.position.y = upperY;
    upperHousing.castShadow = true;
    upperHousing.receiveShadow = true;
    g.add(upperHousing);

    // C. Biển hiệu nổi trên nóc: "RECYCLE HERE ♻"
    const signW = 0.44, signH = 0.40, signD = 0.04;
    const signBox = new THREE.Mesh(
      new THREE.BoxGeometry(signW, signH, signD),
      makeMat(KIOSK_DARK_GREEN, { roughness: 0.3 })
    );
    signBox.position.set(0, K_H + signH/2, 0.05);
    g.add(signBox);

    const signCanvas = document.createElement("canvas");
    signCanvas.width = 400; signCanvas.height = 360;
    const sctx = signCanvas.getContext("2d");
    sctx.fillStyle = "#166534";
    sctx.fillRect(0, 0, 400, 360);
    sctx.fillStyle = "#ffffff";
    sctx.font = "bold 44px sans-serif";
    sctx.textAlign = "center";
    sctx.fillText("RECYCLE", 200, 90);
    sctx.fillText("HERE", 200, 150);
    sctx.font = "bold 110px sans-serif";
    sctx.fillText("♻", 200, 290);
    const signTex = new THREE.CanvasTexture(signCanvas);

    const signFace = new THREE.Mesh(
      new THREE.PlaneGeometry(signW * 0.95, signH * 0.95),
      new THREE.MeshBasicMaterial({ map: signTex })
    );
    signFace.position.set(0, K_H + signH/2, 0.05 + signD/2 + 0.002);
    g.add(signFace);

    // Cảm biến PIR trên nóc
    pirLedMesh = new THREE.Mesh(
      new THREE.SphereGeometry(0.04, 16, 12),
      makeMat(0xffffff, { transparent: true, opacity: 0.9, emissive: 0x00e676, emissiveIntensity: 0.4 })
    );
    pirLedMesh.position.set(-K_W * 0.35, K_H + 0.03, 0);
    g.add(pirLedMesh);

    const frontZ = K_D/2 + 0.01;

    // D. Header Logo MUN™ Căn Giữa Nổi Bật
    const brandCanvas = document.createElement("canvas");
    brandCanvas.width = 800; brandCanvas.height = 200;
    const bctx = brandCanvas.getContext("2d");
    bctx.fillStyle = "rgba(0,0,0,0)";
    bctx.fillRect(0, 0, 800, 200);
    bctx.fillStyle = "#ffffff";
    bctx.font = "900 84px sans-serif";
    bctx.textAlign = "center";
    bctx.fillText("MUN™", 400, 85);
    bctx.font = "700 40px sans-serif";
    bctx.fillText("SMART AI RECYCLER", 400, 145);
    const brandTex = new THREE.CanvasTexture(brandCanvas);

    const brandMesh = new THREE.Mesh(
      new THREE.PlaneGeometry(0.92, 0.23),
      new THREE.MeshBasicMaterial({ map: brandTex, transparent: true })
    );
    brandMesh.position.set(0, baseH + lowerH + upperH * 0.82, frontZ + 0.005);
    g.add(brandMesh);

    // E. Bố trí Buồng Nhận Rác & Màn Hình Nhỏ Độc Lập Cân Đối
    const centerHoleY = baseH + lowerH + upperH * 0.48;
    const holeR = 0.20;

    const whiteRim = new THREE.Mesh(
      new THREE.TorusGeometry(holeR, 0.038, 20, 36),
      makeMat(0xf8fafc, { roughness: 0.25 })
    );
    whiteRim.position.set(0, centerHoleY, frontZ + 0.015);
    g.add(whiteRim);

    ledRingMesh = new THREE.Mesh(
      new THREE.TorusGeometry(holeR + 0.048, 0.014, 14, 36),
      makeMat(0x00e676, { emissive: 0x00e676, emissiveIntensity: 1.2 })
    );
    ledRingMesh.position.set(0, centerHoleY, frontZ + 0.018);
    g.add(ledRingMesh);

    const chuteTunnel = new THREE.Mesh(
      new THREE.CylinderGeometry(holeR * 0.82, holeR * 0.65, 0.45, 28, 1, true),
      makeMat(0x030710, { roughness: 0.95, side: THREE.DoubleSide })
    );
    chuteTunnel.rotation.x = Math.PI / 2;
    chuteTunnel.position.set(0, centerHoleY, frontZ - 0.22);
    g.add(chuteTunnel);

    holeInnerLight = new THREE.PointLight(0xef4444, 0.4, 0.6);
    holeInnerLight.position.set(0, centerHoleY, frontZ - 0.15);
    g.add(holeInnerLight);

    // Chữ "DROP BOTTLES & CANS HERE"
    const dropTextCanvas = document.createElement("canvas");
    dropTextCanvas.width = 600; dropTextCanvas.height = 100;
    const dtctx = dropTextCanvas.getContext("2d");
    dtctx.fillStyle = "rgba(0,0,0,0)";
    dtctx.fillRect(0, 0, 600, 100);
    dtctx.fillStyle = "#ffffff";
    dtctx.font = "bold 34px sans-serif";
    dtctx.textAlign = "center";
    dtctx.fillText("DROP BOTTLES & CANS HERE", 300, 60);
    const dropTextTex = new THREE.CanvasTexture(dropTextCanvas);

    const dropTextMesh = new THREE.Mesh(
      new THREE.PlaneGeometry(0.72, 0.12),
      new THREE.MeshBasicMaterial({ map: dropTextTex, transparent: true })
    );
    dropTextMesh.position.set(0, centerHoleY - holeR - 0.08, frontZ + 0.005);
    g.add(dropTextMesh);

    // Màn hình nhỏ đặt bên phải lỗ nhận
    const qrScreenW = 0.22, qrScreenH = 0.22;
    const qrScreenX = K_W * 0.32;
    const qrScreenY = centerHoleY;

    const qrBezel = new THREE.Mesh(
      new THREE.BoxGeometry(qrScreenW + 0.025, qrScreenH + 0.025, 0.02),
      makeMat(0x0b1320, { roughness: 0.6 })
    );
    qrBezel.position.set(qrScreenX, qrScreenY, frontZ + 0.008);
    g.add(qrBezel);

    qrMesh = new THREE.Mesh(
      new THREE.PlaneGeometry(qrScreenW, qrScreenH),
      new THREE.MeshBasicMaterial({ map: qrTexture })
    );
    qrMesh.position.set(qrScreenX, qrScreenY, frontZ + 0.02);
    g.add(qrMesh);

    // Huy hiệu "RECYCLE RIGHT ♻" bên trái
    const badgeCanvas = document.createElement("canvas");
    badgeCanvas.width = 240; badgeCanvas.height = 100;
    const bgctx = badgeCanvas.getContext("2d");
    bgctx.fillStyle = "#ffffff";
    bgctx.roundRect(0, 0, 240, 100, 12);
    bgctx.fill();
    bgctx.fillStyle = "#166534";
    bgctx.font = "bold 26px sans-serif";
    bgctx.textAlign = "center";
    bgctx.fillText("RECYCLE", 120, 42);
    bgctx.fillText("RIGHT ♻", 120, 78);
    const badgeTex = new THREE.CanvasTexture(badgeCanvas);

    const badgeMesh = new THREE.Mesh(
      new THREE.PlaneGeometry(0.24, 0.10),
      new THREE.MeshBasicMaterial({ map: badgeTex })
    );
    badgeMesh.position.set(-K_W * 0.32, qrScreenY, frontZ + 0.006);
    g.add(badgeMesh);

    const dividerBar = new THREE.Mesh(
      new THREE.BoxGeometry(K_W + 0.02, 0.04, K_D + 0.02),
      makeMat(0x0f172a, { roughness: 0.6 })
    );
    dividerBar.position.set(0, baseH + lowerH, 0);
    g.add(dividerBar);

    // ---------- F. TẦNG DƯỚI: 4 BUỒNG KÍNH TRONG SUỐT TRỐNG ----------
    const lowerY = baseH + lowerH / 2;
    const numBins = 4;
    const binW = (K_W * 0.96) / numBins;
    const binD = K_D * 0.86;

    const binConfigs = [
      { key: "plastic", title: "PLASTIC\nBOTTLES", frameColor: 0x0284c7 },
      { key: "metal",   title: "METAL\nCANS",       frameColor: 0x94a3b8 },
      { key: "paper",   title: "PAPER &\nCARD",     frameColor: 0x16a34a },
      { key: "other",   title: "OTHER\nWASTE",      frameColor: 0xd97706 }
    ];

    const backWall = new THREE.Mesh(
      new THREE.BoxGeometry(K_W * 0.98, lowerH - 0.04, 0.04),
      makeMat(0x0c1524, { roughness: 0.9 })
    );
    backWall.position.set(0, lowerY, -binD/2 + 0.02);
    g.add(backWall);

    const bottomFloor = new THREE.Mesh(
      new THREE.BoxGeometry(K_W * 0.98, 0.03, binD),
      makeMat(0x0a111c, { roughness: 0.9 })
    );
    bottomFloor.position.set(0, baseH + 0.015, 0);
    g.add(bottomFloor);

    for(let s = 0; s <= numBins; s++){
      const sx = -K_W * 0.48 + s * binW;
      const separator = new THREE.Mesh(
        new THREE.BoxGeometry(0.02, lowerH - 0.02, binD),
        makeMat(0x1e293b, { metalness: 0.7, roughness: 0.3 })
      );
      separator.position.set(sx, lowerY, 0);
      g.add(separator);
    }

    for(let i = 0; i < numBins; i++){
      const cfg = binConfigs[i];
      const bx = -K_W * 0.48 + binW / 2 + i * binW;

      const lblCanvas = document.createElement("canvas");
      lblCanvas.width = 256; lblCanvas.height = 100;
      const lctx = lblCanvas.getContext("2d");
      lctx.fillStyle = "rgba(0,0,0,0)";
      lctx.fillRect(0, 0, 256, 100);
      lctx.fillStyle = "#ffffff";
      lctx.font = "900 28px sans-serif";
      lctx.textAlign = "center";
      const lines = cfg.title.split("\n");
      lctx.fillText(lines[0], 128, 38);
      if(lines[1]) lctx.fillText(lines[1], 128, 76);
      const lblTex = new THREE.CanvasTexture(lblCanvas);

      const lblMesh = new THREE.Mesh(
        new THREE.PlaneGeometry(binW * 0.88, 0.10),
        new THREE.MeshBasicMaterial({ map: lblTex, transparent: true })
      );
      lblMesh.position.set(bx, lowerY + lowerH/2 - 0.06, frontZ + 0.016);
      g.add(lblMesh);

      // KHUNG VIỀN KIM LOẠI 4 CẠNH RỖNG
      const frameThick = 0.014;
      const frameDepth = 0.02;
      const fw = binW - 0.02;
      const fh = lowerH - 0.14;
      const frameMat = makeMat(cfg.frameColor, { metalness: 0.85, roughness: 0.2 });

      const topBar = new THREE.Mesh(new THREE.BoxGeometry(fw, frameThick, frameDepth), frameMat);
      topBar.position.set(bx, lowerY - 0.05 + fh/2, frontZ + 0.01);
      g.add(topBar);

      const botBar = new THREE.Mesh(new THREE.BoxGeometry(fw, frameThick, frameDepth), frameMat);
      botBar.position.set(bx, lowerY - 0.05 - fh/2, frontZ + 0.01);
      g.add(botBar);

      const leftBar = new THREE.Mesh(new THREE.BoxGeometry(frameThick, fh, frameDepth), frameMat);
      leftBar.position.set(bx - fw/2 + frameThick/2, lowerY - 0.05, frontZ + 0.01);
      g.add(leftBar);

      const rightBar = new THREE.Mesh(new THREE.BoxGeometry(frameThick, fh, frameDepth), frameMat);
      rightBar.position.set(bx + fw/2 - frameThick/2, lowerY - 0.05, frontZ + 0.01);
      g.add(rightBar);

      // TẤM KÍNH TRONG SUỐT CRYSTAL-CLEAR
      const frontGlass = new THREE.Mesh(
        new THREE.PlaneGeometry(fw - 0.01, fh - 0.01),
        new THREE.MeshPhysicalMaterial({
          color: 0xffffff,
          transparent: true,
          opacity: 0.10,
          roughness: 0.02,
          metalness: 0.02,
          transmission: 0.98,
          ior: 1.5,
          thickness: 0.01,
          depthWrite: false
        })
      );
      frontGlass.position.set(bx, lowerY - 0.05, frontZ + 0.018);
      g.add(frontGlass);

      const internalLight = new THREE.PointLight(0xffffff, 1.2, 1.5);
      internalLight.position.set(bx, lowerY + 0.25, 0.15);
      g.add(internalLight);

      const pileGroup = new THREE.Group();
      pileGroup.name = "pile_" + cfg.key;
      pileGroup.position.set(bx, baseH + 0.06, 0.08);

      g.add(pileGroup);
      binPiles[cfg.key] = pileGroup;
      binItemCounts[cfg.key] = 0;

      [-0.035, 0.035].forEach(dx => {
        const eye = new THREE.Mesh(
          new THREE.CylinderGeometry(0.018, 0.018, 0.02, 14),
          makeMat(0x334155, { metalness: 0.85 })
        );
        eye.rotation.x = Math.PI / 2;
        eye.position.set(bx + dx, lowerY + lowerH/2 - 0.02, frontZ - 0.02);
        g.add(eye);
      });
    }

    return g;
  }

  function createRealDepositedWasteMesh(itemKey){
    const g = new THREE.Group();
    if(itemKey === "plastic"){
      const b = new THREE.Mesh(
        new THREE.CylinderGeometry(0.034, 0.034, 0.15, 14),
        new THREE.MeshPhysicalMaterial({ color: 0x38bdf8, transparent: true, opacity: 0.82, roughness: 0.15 })
      );
      g.add(b);
      const label = new THREE.Mesh(
        new THREE.CylinderGeometry(0.035, 0.035, 0.065, 14),
        makeMat(0x0284c7)
      );
      g.add(label);
      const neck = new THREE.Mesh(
        new THREE.CylinderGeometry(0.018, 0.034, 0.04, 14),
        new THREE.MeshPhysicalMaterial({ color: 0x38bdf8, transparent: true, opacity: 0.82, roughness: 0.15 })
      );
      neck.position.y = 0.095;
      g.add(neck);
      const cap = new THREE.Mesh(
        new THREE.CylinderGeometry(0.019, 0.019, 0.022, 12),
        makeMat(0x0284c7)
      );
      cap.position.y = 0.125;
      g.add(cap);
    }
    else if(itemKey === "metal"){
      const can = new THREE.Mesh(
        new THREE.CylinderGeometry(0.035, 0.035, 0.12, 16),
        makeMat(0xdc2626, { metalness: 0.88, roughness: 0.2 })
      );
      g.add(can);
      const rimTop = new THREE.Mesh(
        new THREE.CylinderGeometry(0.033, 0.035, 0.016, 16),
        makeMat(0xe2e8f0, { metalness: 0.95, roughness: 0.1 })
      );
      rimTop.position.y = 0.068;
      g.add(rimTop);
      const rimBot = new THREE.Mesh(
        new THREE.CylinderGeometry(0.033, 0.035, 0.016, 16),
        makeMat(0xe2e8f0, { metalness: 0.95, roughness: 0.1 })
      );
      rimBot.position.y = -0.068;
      g.add(rimBot);
    }
    else if(itemKey === "paper"){
      const p = new THREE.Mesh(
        new THREE.BoxGeometry(0.12, 0.08, 0.10),
        makeMat(0xd97706, { roughness: 0.9 })
      );
      g.add(p);
    }
    else {
      const p = new THREE.Mesh(
        new THREE.BoxGeometry(0.10, 0.12, 0.035),
        makeMat(0xf59e0b, { metalness: 0.4, roughness: 0.45 })
      );
      g.add(p);
    }
    return g;
  }

  // ---------- 3. Tạo Vật Rác 3D Trên Tay Nhân Vật ----------
  function createHandWasteMesh(key){
    const g = new THREE.Group();
    g.name = "held_item_" + key;

    if(key === "plastic"){
      const body = new THREE.Mesh(
        new THREE.CylinderGeometry(0.055, 0.055, 0.24, 16),
        new THREE.MeshPhysicalMaterial({ color: 0xbae6fd, transparent: true, opacity: 0.75, roughness: 0.15 })
      );
      g.add(body);
      const label = new THREE.Mesh(
        new THREE.CylinderGeometry(0.056, 0.056, 0.10, 16),
        makeMat(0x0284c7)
      );
      g.add(label);
      const neck = new THREE.Mesh(
        new THREE.CylinderGeometry(0.025, 0.055, 0.06, 16),
        new THREE.MeshPhysicalMaterial({ color: 0xbae6fd, transparent: true, opacity: 0.75, roughness: 0.15 })
      );
      neck.position.y = 0.15;
      g.add(neck);
      const cap = new THREE.Mesh(
        new THREE.CylinderGeometry(0.026, 0.026, 0.025, 14),
        makeMat(0x0284c7)
      );
      cap.position.y = 0.19;
      g.add(cap);
    }
    else if(key === "metal"){
      const can = new THREE.Mesh(
        new THREE.CylinderGeometry(0.055, 0.055, 0.19, 18),
        makeMat(0xdc2626, { metalness: 0.85, roughness: 0.25 })
      );
      g.add(can);
      const topRim = new THREE.Mesh(
        new THREE.CylinderGeometry(0.052, 0.055, 0.02, 18),
        makeMat(0xe2e8f0, { metalness: 0.9, roughness: 0.15 })
      );
      topRim.position.y = 0.10;
      g.add(topRim);
    }
    else if(key === "paper"){
      const box = new THREE.Mesh(
        new THREE.BoxGeometry(0.15, 0.13, 0.15),
        makeMat(0xd97706, { roughness: 0.9 })
      );
      g.add(box);
    }
    else if(key === "other"){
      const bag = new THREE.Mesh(
        new THREE.BoxGeometry(0.15, 0.20, 0.05),
        makeMat(0xf59e0b, { metalness: 0.35, roughness: 0.45 })
      );
      g.add(bag);
    }
    else if(key === "battery"){
      const bat = new THREE.Mesh(
        new THREE.CylinderGeometry(0.035, 0.035, 0.14, 16),
        makeMat(0x1e293b, { metalness: 0.75, roughness: 0.25 })
      );
      g.add(bat);
      const top = new THREE.Mesh(
        new THREE.CylinderGeometry(0.016, 0.016, 0.025, 12),
        makeMat(0xd97706, { metalness: 0.9, roughness: 0.1 })
      );
      top.position.y = 0.082;
      g.add(top);
    }

    g.rotation.z = Math.PI / 6;
    return g;
  }

  // ---------- 4. Nhân Vật 3D Có Khớp Vai & Chân Đi Bộ ----------
  let leftLegMesh, rightLegMesh, rightArmGroup, walkCycleTime = 0;

  function buildDetailedPlayer(){
    const g = new THREE.Group();

    const torso = new THREE.Mesh(
      makeCapsule(0.24, 0.58, 8, 12),
      makeMat(0x0284c7, { roughness: 0.6 })
    );
    torso.position.y = 0.72;
    torso.castShadow = true;
    g.add(torso);

    const collar = new THREE.Mesh(
      new THREE.CylinderGeometry(0.14, 0.15, 0.06, 16),
      makeMat(0xf8fafc)
    );
    collar.position.y = 1.05;
    g.add(collar);

    const head = new THREE.Mesh(
      new THREE.SphereGeometry(0.19, 18, 18),
      makeMat(0xffd5b8, { roughness: 0.85 })
    );
    head.position.y = 1.25;
    head.castShadow = true;
    g.add(head);

    const hair = new THREE.Mesh(
      new THREE.SphereGeometry(0.20, 18, 18, 0, Math.PI * 2, 0, Math.PI * 0.55),
      makeMat(0x1e293b, { roughness: 0.9 })
    );
    hair.position.y = 1.28;
    g.add(hair);

    rightArmGroup = new THREE.Group();
    rightArmGroup.name = "rightArmGroup";
    rightArmGroup.position.set(0.30, 0.95, 0);

    const rShoulder = new THREE.Mesh(
      new THREE.SphereGeometry(0.075, 12, 12),
      makeMat(0x0284c7)
    );
    rightArmGroup.add(rShoulder);

    const rUpperArm = new THREE.Mesh(
      makeCapsule(0.065, 0.24, 6, 8),
      makeMat(0x0284c7)
    );
    rUpperArm.position.set(0, -0.16, 0);
    rightArmGroup.add(rUpperArm);

    const rForearmNode = new THREE.Group();
    rForearmNode.name = "rForearmNode";
    rForearmNode.position.set(0, -0.28, 0);

    const rForearm = new THREE.Mesh(
      makeCapsule(0.06, 0.22, 6, 8),
      makeMat(0xffd5b8)
    );
    rForearm.position.set(0, -0.12, 0.05);
    rForearm.rotation.x = Math.PI / 6;
    rForearmNode.add(rForearm);

    const handNode = new THREE.Group();
    handNode.name = "handNode";
    handNode.position.set(0, -0.25, 0.12);
    rForearmNode.add(handNode);

    rightArmGroup.add(rForearmNode);
    g.add(rightArmGroup);

    const leftArmGroup = new THREE.Group();
    leftArmGroup.position.set(-0.30, 0.95, 0);

    const lShoulder = new THREE.Mesh(
      new THREE.SphereGeometry(0.075, 12, 12),
      makeMat(0x0284c7)
    );
    leftArmGroup.add(lShoulder);

    const lArm = new THREE.Mesh(
      makeCapsule(0.065, 0.42, 6, 8),
      makeMat(0x0284c7)
    );
    lArm.position.set(0, -0.22, 0);
    leftArmGroup.add(lArm);
    g.add(leftArmGroup);

    leftLegMesh = new THREE.Group();
    leftLegMesh.position.set(-0.12, 0.48, 0);
    const lLeg = new THREE.Mesh(
      new THREE.CylinderGeometry(0.075, 0.065, 0.52, 12),
      makeMat(0x334155)
    );
    lLeg.position.y = -0.24;
    lLeg.castShadow = true;
    leftLegMesh.add(lLeg);
    g.add(leftLegMesh);

    rightLegMesh = new THREE.Group();
    rightLegMesh.position.set(0.12, 0.48, 0);
    const rLeg = new THREE.Mesh(
      new THREE.CylinderGeometry(0.075, 0.065, 0.52, 12),
      makeMat(0x334155)
    );
    rLeg.position.y = -0.24;
    rLeg.castShadow = true;
    rightLegMesh.add(rLeg);
    g.add(rightLegMesh);

    return g;
  }

  function setWasteItem(key){
    currentItemKey = key;
    if(!playerGroup) return;
    const handNode = playerGroup.getObjectByName("handNode");
    if(!handNode) return;

    if(currentHeldMesh){
      handNode.remove(currentHeldMesh);
      currentHeldMesh = null;
    }

    currentHeldMesh = createHandWasteMesh(key);
    handNode.add(currentHeldMesh);
  }

  function setPirLed(on){
    if(pirLedMesh){
      pirLedMesh.material.emissive.set(on ? 0x00e676 : 0x222222);
      pirLedMesh.material.emissiveIntensity = on ? 1.6 : 0.2;
    }
  }

  function setLedRing(colorHex, intensity = 1.0){
    if(ledRingMesh){
      ledRingMesh.material.color.set(colorHex);
      ledRingMesh.material.emissive.set(colorHex);
      ledRingMesh.material.emissiveIntensity = intensity;
    }
    if(holeInnerLight){
      holeInnerLight.color.set(colorHex === 0xef4444 ? 0xff0000 : 0x00e676);
    }
  }

  function onResize(){
    if(!renderer || !hostEl) return;
    const w = hostEl.clientWidth, h = Math.max(1, hostEl.clientHeight);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
  }

  function clamp(v, min, max){ return Math.max(min, Math.min(max, v)); }
  function angleDiff(from, to){
    let d = (to - from) % (Math.PI*2);
    if(d > Math.PI) d -= Math.PI*2;
    if(d < -Math.PI) d += Math.PI*2;
    return d;
  }

  function updateCameraTransform(dt){
    ensureVectors();
    if(!camTarget) return;

    if(cameraMode === "autorotate"){
      targetSpherical.theta += autoRotateSpeed;
    }

    if(cameraMode === "follow" && playerGroup){
      targetLookAt.x = playerGroup.position.x;
      targetLookAt.y = 1.1;
      targetLookAt.z = playerGroup.position.z;
    }

    camSpherical.radius += (targetSpherical.radius - camSpherical.radius) * Math.min(1, dt * 8);
    camSpherical.theta  += (targetSpherical.theta  - camSpherical.theta)  * Math.min(1, dt * 8);
    camSpherical.phi    += (targetSpherical.phi    - camSpherical.phi)    * Math.min(1, dt * 8);

    camTarget.lerp(targetLookAt, Math.min(1, dt * 8));

    camera.position.x = camTarget.x + camSpherical.radius * Math.sin(camSpherical.phi) * Math.sin(camSpherical.theta);
    camera.position.y = camTarget.y + camSpherical.radius * Math.cos(camSpherical.phi);
    camera.position.z = camTarget.z + camSpherical.radius * Math.sin(camSpherical.phi) * Math.cos(camSpherical.theta);
    camera.lookAt(camTarget);
  }

  function setCameraPreset(presetName){
    ensureVectors();
    cameraMode = "free";

    if(presetName === "overview"){
      targetSpherical.radius = 6.8;
      targetSpherical.theta = 0.15;
      targetSpherical.phi = 1.25;
      if(targetLookAt) targetLookAt.set(0, 1.25, 0);
    }
    else if(presetName === "front"){
      targetSpherical.radius = 4.6;
      targetSpherical.theta = 0.0;
      targetSpherical.phi = 1.45;
      if(targetLookAt) targetLookAt.set(0, 1.35, 0);
    }
    else if(presetName === "qr" || presetName === "chute"){
      targetSpherical.radius = 1.85;
      targetSpherical.theta = 0.18;
      targetSpherical.phi = 1.42;
      if(targetLookAt) targetLookAt.set(0.1, 1.35, 0.45);
    }
    else if(presetName === "bins"){
      targetSpherical.radius = 2.4;
      targetSpherical.theta = 0.0;
      targetSpherical.phi = 1.58;
      if(targetLookAt) targetLookAt.set(0, 0.55, 0.3);
    }
    else if(presetName === "follow"){
      cameraMode = "follow";
      targetSpherical.radius = 4.2;
      targetSpherical.theta = 0.35;
      targetSpherical.phi = 1.30;
    }
    else if(presetName === "autorotate"){
      cameraMode = "autorotate";
    }
  }

  function updatePlayer(dt){
    let isMoving = false;

    if(isAutoWalking){
      const targetX = 0.0;
      const targetZ = 1.45;
      const dx = targetX - playerGroup.position.x;
      const dz = targetZ - playerGroup.position.z;
      const dist = Math.hypot(dx, dz);

      if(dist > 0.06){
        isMoving = true;
        const step = Math.min(dist, PLAYER_SPEED * dt * 0.95);
        playerGroup.position.x += (dx / dist) * step;
        playerGroup.position.z += (dz / dist) * step;
        const targetAngle = Math.atan2(dx, dz);
        playerGroup.rotation.y += angleDiff(playerGroup.rotation.y, targetAngle) * Math.min(1, dt * 12);
      } else {
        isAutoWalking = false;
        playerGroup.rotation.y = Math.PI;
        if(autoWalkResolve){
          const r = autoWalkResolve;
          autoWalkResolve = null;
          r();
        }
      }
    } else {
      let dx = 0, dz = 0;
      if(keys["w"] || keys["arrowup"]) dz -= 1;
      if(keys["s"] || keys["arrowdown"]) dz += 1;
      if(keys["a"] || keys["arrowleft"]) dx -= 1;
      if(keys["d"] || keys["arrowright"]) dx += 1;

      if(dx || dz){
        isMoving = true;
        const len = Math.hypot(dx, dz);
        dx /= len; dz /= len;
        playerGroup.position.x = clamp(playerGroup.position.x + dx * PLAYER_SPEED * dt, -6, 6);
        playerGroup.position.z = clamp(playerGroup.position.z + dz * PLAYER_SPEED * dt, -0.6, 6);
        const targetAngle = Math.atan2(dx, dz);
        playerGroup.rotation.y += angleDiff(playerGroup.rotation.y, targetAngle) * Math.min(1, dt * 10);
      }
    }

    if(isMoving){
      walkCycleTime += dt * 10;
      if(leftLegMesh) leftLegMesh.rotation.x = Math.sin(walkCycleTime) * 0.55;
      if(rightLegMesh) rightLegMesh.rotation.x = -Math.sin(walkCycleTime) * 0.55;
    } else {
      if(leftLegMesh) leftLegMesh.rotation.x = 0;
      if(rightLegMesh) rightLegMesh.rotation.x = 0;
    }
  }

  function distanceToBin(){
    if(!playerGroup || !kioskGroup) return 999;
    return Math.hypot(playerGroup.position.x - kioskGroup.position.x, playerGroup.position.z - kioskGroup.position.z);
  }

  function animate(){
    requestAnimationFrame(animate);
    const dt = Math.min(clock.getDelta(), 0.05);
    updatePlayer(dt);
    updateCameraTransform(dt);

    drawQrScreenUI();

    const curDist = distanceToBin();

    // 1. Kiểm tra TIẾP CẬN VÀO VÙNG QUÉT PIR (~2m) -> BẮT ĐẦU PHIÊN & HIỆN MÃ QR
    if(approachArmed){
      const near = curDist < TRIGGER_DIST;
      if(near && !wasNear){
        approachArmed = false;
        wasNear = true;
        setPirLed(true);
        setLedRing(0x00e676, 1.4);
        updateQrScreenState("PRESENCE", "👉 ĐƯA ĐIỆN THOẠI QUÉT");
        if(onApproachCb) onApproachCb();
      }
    }

    // 2. KIỂM TRA NGƯỜI DÙNG RỜI ĐI (> 2.4m) -> TỰ ĐỘNG NGẮT PHIÊN & TẮT MÀN HÌNH QR
    if(wasNear && curDist > LEAVE_DIST){
      wasNear = false;
      approachArmed = true;
      setPirLed(false);
      setLedRing(0x00e676, 1.0);
      updateQrScreenState("IDLE");
      if(onLeaveCb) onLeaveCb();
    }

    renderer.render(scene, camera);
  }

  // ---------- 5. Hoạt ảnh Bỏ Rác 5 Pha ----------
  function playMultiPhaseInsertAnimation(){
    return new Promise(resolve => {
      const armGroup = playerGroup.getObjectByName("rightArmGroup");
      const handNode = playerGroup.getObjectByName("handNode");
      if(!armGroup || !handNode) { resolve(); return; }

      const startPos = playerGroup.position.clone();
      let phase = 1;
      let phaseStart = performance.now();

      function stepAnimation(now){
        const elapsed = now - phaseStart;

        if(phase === 1){
          const p = Math.min(1, elapsed / 320);
          playerGroup.position.z = startPos.z + (1.25 - startPos.z) * p;
          playerGroup.rotation.x = Math.sin(p * Math.PI) * 0.08;
          if(p >= 1){
            phase = 2;
            phaseStart = now;
          }
        }
        else if(phase === 2){
          const p = Math.min(1, elapsed / 400);
          armGroup.rotation.x = -Math.PI * 0.48 * p;
          armGroup.rotation.y = -Math.PI * 0.12 * p;
          if(p >= 1){
            phase = 3;
            phaseStart = now;
          }
        }
        else if(phase === 3){
          const p = Math.min(1, elapsed / 380);
          armGroup.position.z = -0.15 * p;
          armGroup.position.y = 0.95 + 0.05 * p;

          if(currentHeldMesh){
            currentHeldMesh.scale.setScalar(Math.max(0.01, 1 - p * 0.85));
            currentHeldMesh.position.z = p * 0.25;
          }

          if(p >= 1){
            if(window.appFlashTrigger) window.appFlashTrigger();
            if(currentHeldMesh){
              handNode.remove(currentHeldMesh);
              currentHeldMesh = null;
            }
            phase = 4;
            phaseStart = now;
          }
        }
        else if(phase === 4){
          const p = Math.min(1, elapsed / 320);
          armGroup.rotation.x = -Math.PI * 0.48 * (1 - p);
          armGroup.rotation.y = -Math.PI * 0.12 * (1 - p);
          armGroup.position.z = -0.15 * (1 - p);
          armGroup.position.y = 0.95;
          if(p >= 1){
            phase = 5;
            phaseStart = now;
          }
        }
        else if(phase === 5){
          const p = Math.min(1, elapsed / 350);
          playerGroup.position.z = 1.25 + (startPos.z - 1.25) * p;
          playerGroup.rotation.x = 0;
          if(p >= 1){
            resolve();
            return;
          }
        }

        requestAnimationFrame(stepAnimation);
      }

      requestAnimationFrame(stepAnimation);
    });
  }

  function spawnItemInTransparentBin(routeKey, specificItemKey){
    const validKey = ["plastic", "metal", "paper", "other"].includes(routeKey) ? routeKey : "other";
    const pile = binPiles[validKey];
    if(!pile) return;

    const actualKey = specificItemKey || currentItemKey || validKey;
    const newItem = createRealDepositedWasteMesh(actualKey);

    const currentCount = pile.children.length;
    const targetY = currentCount * 0.062;

    newItem.position.set(
      (Math.random() - 0.5) * 0.16,
      0.75,
      (Math.random() - 0.5) * 0.28
    );
    pile.add(newItem);
    binItemCounts[validKey]++;

    let startTime = performance.now();
    const duration = 650;

    function fallStep(now){
      const p = Math.min(1, (now - startTime) / duration);
      const curY = 0.75 - (0.75 - targetY) * Math.sin(p * Math.PI * 0.5);
      newItem.position.y = curY;
      newItem.rotation.x += 0.08 * (1 - p);
      newItem.rotation.z += 0.06 * (1 - p);
      if(p < 1){
        requestAnimationFrame(fallStep);
      } else {
        newItem.position.y = targetY;
      }
    }
    requestAnimationFrame(fallStep);
  }

  function clearAllBins(){
    Object.keys(binPiles).forEach(key => {
      const pile = binPiles[key];
      if(pile){
        while(pile.children.length > 0){
          pile.remove(pile.children[0]);
        }
      }
      binItemCounts[key] = 0;
    });
  }

  // ---------- 6. Khởi Tạo Scene & Camera ----------
  function init(hostId){
    ensureVectors();
    hostEl = document.getElementById(hostId);

    scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf1f5f9);

    camera = new THREE.PerspectiveCamera(38, hostEl.clientWidth / Math.max(1, hostEl.clientHeight), 0.1, 100);
    updateCameraTransform(0.016);

    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    
    if(THREE.ACESFilmicToneMapping){
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.12;
    }
    if(THREE.SRGBColorSpace){
      renderer.outputColorSpace = THREE.SRGBColorSpace;
    }

    hostEl.appendChild(renderer.domElement);

    scene.add(new THREE.AmbientLight(0xffffff, 0.95));

    const mainSun = new THREE.DirectionalLight(0xffffff, 1.2);
    mainSun.position.set(5, 12, 7);
    mainSun.castShadow = true;
    mainSun.shadow.mapSize.set(2048, 2048);
    mainSun.shadow.camera.near = 0.5;
    mainSun.shadow.camera.far = 25;
    mainSun.shadow.camera.left = -5;
    mainSun.shadow.camera.right = 5;
    mainSun.shadow.camera.top = 5;
    mainSun.shadow.camera.bottom = -5;
    mainSun.shadow.bias = -0.0004;
    scene.add(mainSun);

    const ceilingSpot = new THREE.SpotLight(0x00b894, 1.2, 14, Math.PI / 3.5, 0.4);
    ceilingSpot.position.set(0, 6, 2.5);
    ceilingSpot.target.position.set(0, 0, 0);
    scene.add(ceilingSpot);
    scene.add(ceilingSpot.target);

    const floorCanvas = document.createElement("canvas");
    floorCanvas.width = 512; floorCanvas.height = 512;
    const fctx = floorCanvas.getContext("2d");
    fctx.fillStyle = "#ffffff";
    fctx.fillRect(0, 0, 512, 512);
    fctx.strokeStyle = "#e2e8f0";
    fctx.lineWidth = 3;
    fctx.strokeRect(0, 0, 256, 256);
    fctx.strokeRect(256, 0, 256, 256);
    fctx.strokeRect(0, 256, 256, 256);
    fctx.strokeRect(256, 256, 256, 256);

    const floorTex = new THREE.CanvasTexture(floorCanvas);
    floorTex.wrapS = THREE.RepeatWrapping;
    floorTex.wrapT = THREE.RepeatWrapping;
    floorTex.repeat.set(6, 6);

    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(16, 16),
      makeMat(0xffffff, { map: floorTex, roughness: 0.18, metalness: 0.08 })
    );
    floor.rotation.x = -Math.PI / 2;
    floor.receiveShadow = true;
    scene.add(floor);

    const glassWall = new THREE.Mesh(
      new THREE.PlaneGeometry(14, 5),
      new THREE.MeshPhysicalMaterial({
        color: 0xe0f2fe,
        transparent: true,
        opacity: 0.35,
        roughness: 0.05,
        transmission: 0.92
      })
    );
    glassWall.position.set(0, 2.4, -2.5);
    scene.add(glassWall);

    const wallFrame = new THREE.Mesh(
      new THREE.BoxGeometry(14.2, 0.1, 0.1),
      makeMat(0xcfd8dc, { roughness: 0.4 })
    );
    wallFrame.position.set(0, 4.8, -2.48);
    scene.add(wallFrame);

    [-2.4, 2.4].forEach(px => {
      const pot = new THREE.Mesh(
        new THREE.CylinderGeometry(0.24, 0.18, 0.5, 16),
        makeMat(0xffffff, { roughness: 0.4 })
      );
      pot.position.set(px, 0.25, -0.4);
      pot.castShadow = true;
      scene.add(pot);

      const plant = new THREE.Mesh(
        new THREE.DodecahedronGeometry(0.35, 1),
        makeMat(0x10b981, { roughness: 0.8 })
      );
      plant.position.set(px, 0.65, -0.4);
      plant.castShadow = true;
      scene.add(plant);
    });

    initQrScreenTexture();

    kioskGroup = buildMunKiosk();
    kioskGroup.position.set(0, 0, 0);
    scene.add(kioskGroup);

    playerGroup = buildDetailedPlayer();
    playerGroup.position.set(0.0, 0, 3.8);
    playerGroup.rotation.y = Math.PI;
    scene.add(playerGroup);

    setWasteItem("plastic");

    hostEl.addEventListener("contextmenu", e => e.preventDefault());

    hostEl.addEventListener("mousedown", e => {
      if(e.button === 0 && !e.shiftKey){
        isOrbitDragging = true;
        cameraMode = "free";
      } else if(e.button === 2 || (e.button === 0 && e.shiftKey) || e.button === 1){
        isPanDragging = true;
        cameraMode = "free";
      }
      prevMouse.x = e.clientX;
      prevMouse.y = e.clientY;
    });

    window.addEventListener("mouseup", () => {
      isOrbitDragging = false;
      isPanDragging = false;
    });

    window.addEventListener("mousemove", e => {
      if(!isOrbitDragging && !isPanDragging) return;
      const dx = e.clientX - prevMouse.x;
      const dy = e.clientY - prevMouse.y;
      prevMouse.x = e.clientX;
      prevMouse.y = e.clientY;

      if(isOrbitDragging){
        targetSpherical.theta -= dx * 0.007;
        targetSpherical.phi = clamp(targetSpherical.phi - dy * 0.007, 0.25, Math.PI / 2 - 0.04);
      } else if(isPanDragging){
        const forward = new THREE.Vector3().subVectors(camTarget, camera.position).normalize();
        const right = new THREE.Vector3().crossVectors(forward, camera.up).normalize();
        const up = new THREE.Vector3().crossVectors(right, forward).normalize();

        const panSpeed = targetSpherical.radius * 0.0018;
        targetLookAt.addScaledVector(right, -dx * panSpeed);
        targetLookAt.addScaledVector(up, dy * panSpeed);
      }
    });

    hostEl.addEventListener("wheel", e => {
      e.preventDefault();
      cameraMode = "free";
      targetSpherical.radius = clamp(targetSpherical.radius + e.deltaY * 0.004, 1.6, 12.0);
    }, { passive: false });

    hostEl.addEventListener("touchstart", e => {
      if(e.touches.length === 1){
        isOrbitDragging = true;
        prevMouse.x = e.touches[0].clientX;
        prevMouse.y = e.touches[0].clientY;
      } else if(e.touches.length === 2){
        touchStartDist = Math.hypot(
          e.touches[0].clientX - e.touches[1].clientX,
          e.touches[0].clientY - e.touches[1].clientY
        );
      }
    });

    hostEl.addEventListener("touchmove", e => {
      if(e.touches.length === 1 && isOrbitDragging){
        const dx = e.touches[0].clientX - prevMouse.x;
        const dy = e.touches[0].clientY - prevMouse.y;
        prevMouse.x = e.touches[0].clientX;
        prevMouse.y = e.touches[0].clientY;

        targetSpherical.theta -= dx * 0.008;
        targetSpherical.phi = clamp(targetSpherical.phi - dy * 0.008, 0.25, Math.PI / 2 - 0.04);
      } else if(e.touches.length === 2){
        const curDist = Math.hypot(
          e.touches[0].clientX - e.touches[1].clientX,
          e.touches[0].clientY - e.touches[1].clientY
        );
        const distDiff = curDist - touchStartDist;
        targetSpherical.radius = clamp(targetSpherical.radius - distDiff * 0.01, 1.6, 12.0);
        touchStartDist = curDist;
      }
    });

    hostEl.addEventListener("touchend", () => {
      isOrbitDragging = false;
    });

    clock = new THREE.Clock();
    window.addEventListener("resize", onResize);
    onResize();
    requestAnimationFrame(animate);
  }

  window.addEventListener("keydown", e => { keys[e.key.toLowerCase()] = true; });
  window.addEventListener("keyup", e => { keys[e.key.toLowerCase()] = false; });

  function armApproach(onTriggered, onLeft){
    approachArmed = true;
    onApproachCb = onTriggered;
    onLeaveCb = onLeft;
    wasNear = distanceToBin() < TRIGGER_DIST;
  }

  function disarmApproach(){
    approachArmed = false;
    onApproachCb = null;
    onLeaveCb = null;
  }

  function autoWalkToBin(){
    return new Promise(resolve => {
      isAutoWalking = true;
      autoWalkResolve = resolve;
    });
  }

  function resetPlayer(){
    if(playerGroup){
      playerGroup.position.set(0.0, 0, 3.8);
      playerGroup.rotation.y = Math.PI;
    }
    setWasteItem(currentItemKey);
    setPirLed(false);
    setLedRing(0x00e676, 1.0);
    updateQrScreenState("IDLE");
    clearAllBins();
    setCameraPreset("overview");
  }

  window.Scene3D = {
    init,
    setWasteItem,
    armApproach,
    disarmApproach,
    setPirLed,
    setLedRing,
    updateKioskScreen,
    updateQrScreenState,
    autoWalkToBin,
    playInsertAnimation: playMultiPhaseInsertAnimation,
    spawnItemInTransparentBin,
    clearAllBins,
    isPlayerNear: () => distanceToBin() < TRIGGER_DIST,
    setCameraPreset,
    resetPlayer
  };
})(window);
