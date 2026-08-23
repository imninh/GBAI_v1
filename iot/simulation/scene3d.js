// scene3d.js — Three.js scene: nhân vật 3D di chuyển bằng WASD lại gần thùng rác.
// Không phụ thuộc vào phần logic demo (app.js) — chỉ expose window.Scene3D:
//   Scene3D.init(hostElementId)
//   Scene3D.armApproach(onTriggered)   // gọi onTriggered() đúng 1 lần khi nhân vật vào phạm vi gần thùng
//   Scene3D.disarmApproach()
//   Scene3D.setPirLed(on)              // đổi màu đèn cảm biến trên mô hình thùng 3D
//   Scene3D.resetPlayer()              // đưa nhân vật về vị trí xuất phát
(function(window){
  "use strict";

  const FLOOR_HALF = 7;
  const TRIGGER_DIST = 1.7;
  const PLAYER_SPEED = 4.2;

  const keys = {};
  let scene, camera, renderer, clock, playerGroup, binGroup, sensorMesh, hostEl;
  let approachArmed = false;
  let wasNear = false;
  let onApproachCb = null;

  // Thùng rác 4 tầng (từ trên xuống):
  //   Tầng 1: cảm biến hồng ngoại PIR (HC-SR501) + ESP32-CAM (phát hiện người + chụp ảnh rác)
  //   Tầng 2: servo 1 (van chính, hướng rác trái/phải)
  //   Tầng 3: 2 servo lắp song song (chọn đúng 1 trong 2 ngăn của mỗi nhánh)
  //   Tầng 4: 4 ngăn phân loại, mỗi ngăn có cảm biến siêu âm HC-SR04 báo đầy
  const BIN_W = 1.3, BIN_D = 1.1, BIN_H = 3.0;
  const TIER_H = BIN_H / 4;

  function makeStdMat(color, opts){
    return new THREE.MeshStandardMaterial(Object.assign({ color, roughness: 0.85, metalness: 0.05 }, opts || {}));
  }

  // Vỏ ngoài để hở mặt trước (hướng về phía người chơi) để nhìn thấy cấu trúc bên trong
  function buildOpenFrontHousing(w, h, d, color){
    const g = new THREE.Group();
    const mat = makeStdMat(color, { side: THREE.DoubleSide });

    const back = new THREE.Mesh(new THREE.PlaneGeometry(w, h), mat);
    back.position.set(0, h/2, -d/2);
    g.add(back);

    const left = new THREE.Mesh(new THREE.PlaneGeometry(d, h), mat);
    left.position.set(-w/2, h/2, 0); left.rotation.y = Math.PI/2;
    g.add(left);

    const right = new THREE.Mesh(new THREE.PlaneGeometry(d, h), mat);
    right.position.set(w/2, h/2, 0); right.rotation.y = -Math.PI/2;
    g.add(right);

    const top = new THREE.Mesh(new THREE.PlaneGeometry(w, d), mat);
    top.position.set(0, h, 0); top.rotation.x = Math.PI/2;
    g.add(top);

    const bottom = new THREE.Mesh(new THREE.PlaneGeometry(w, d), mat);
    bottom.position.set(0, 0, 0); bottom.rotation.x = -Math.PI/2;
    g.add(bottom);

    g.children.forEach(m=>{ m.castShadow = true; m.receiveShadow = true; });
    return g;
  }

  function buildCompartmentsTier(){
    const g = new THREE.Group();
    const colors = [0x3aa0ff, 0x8a93a8, 0xd69a3f, 0x7a7f92]; // plastic, metal, paper, other
    const n = 4;
    const gap = 0.025;
    const cw = (BIN_W - gap*(n+1)) / n;
    const cd = BIN_D * 0.8;
    const ch = TIER_H * 0.82;
    const eyeMat = makeStdMat(0x1c2438);
    for(let i=0;i<n;i++){
      const cx = -BIN_W/2 + gap + cw/2 + i*(cw+gap);
      const box = new THREE.Mesh(new THREE.BoxGeometry(cw, ch, cd), makeStdMat(colors[i]));
      box.position.set(cx, ch/2 + 0.03, 0);
      box.castShadow = true; box.receiveShadow = true;
      g.add(box);

      // HC-SR04 — cặp mắt cảm biến gắn trên nóc mỗi ngăn, hướng xuống để đo mức đầy
      [-0.05, 0.05].forEach(dx=>{
        const eye = new THREE.Mesh(new THREE.CylinderGeometry(0.032, 0.032, 0.025, 12), eyeMat);
        eye.rotation.x = Math.PI/2;
        eye.position.set(cx+dx, TIER_H - 0.03, cd*0.28);
        g.add(eye);
      });
    }
    return g;
  }

  function buildServoUnit(width){
    const g = new THREE.Group();
    const body = new THREE.Mesh(new THREE.BoxGeometry(width, 0.22, 0.28), makeStdMat(0x33405e));
    body.position.y = 0.11; body.castShadow = true;
    g.add(body);
    const arm = new THREE.Mesh(new THREE.BoxGeometry(width*1.5, 0.035, 0.06), makeStdMat(0x8994ab));
    arm.position.set(0, 0.24, 0.08); arm.castShadow = true;
    g.add(arm);
    return g;
  }

  function buildDualServoTier(){
    const g = new THREE.Group();
    const sL = buildServoUnit(0.34); sL.position.set(-0.3, TIER_H*0.28, 0); g.add(sL);
    const sR = buildServoUnit(0.34); sR.position.set(0.3, TIER_H*0.28, 0); g.add(sR);
    return g;
  }

  function buildServo1Tier(){
    const g = new THREE.Group();
    const s = buildServoUnit(0.55);
    s.position.set(0, TIER_H*0.28, 0);
    g.add(s);
    return g;
  }

  function buildSensorCamTier(){
    const g = new THREE.Group();

    const camBody = new THREE.Mesh(new THREE.BoxGeometry(0.32, 0.22, 0.2), makeStdMat(0x141a26));
    camBody.position.set(-0.22, TIER_H*0.42, BIN_D*0.32);
    camBody.castShadow = true;
    g.add(camBody);
    const lens = new THREE.Mesh(new THREE.CylinderGeometry(0.055, 0.055, 0.06, 16), makeStdMat(0x0a0e18));
    lens.rotation.x = Math.PI/2;
    lens.position.set(-0.22, TIER_H*0.42, BIN_D*0.32 + 0.13);
    g.add(lens);

    // cảm biến hồng ngoại PIR (HC-SR501)
    const pirBase = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.09, 0.03, 16), makeStdMat(0x2a3145));
    pirBase.position.set(0.22, TIER_H*0.4, BIN_D*0.32);
    g.add(pirBase);
    const pirDome = new THREE.Mesh(
      new THREE.SphereGeometry(0.09, 16, 12),
      makeStdMat(0xf2f4f8, { transparent: true, opacity: 0.85 })
    );
    pirDome.position.set(0.22, TIER_H*0.42 + 0.03, BIN_D*0.32);
    g.add(pirDome);

    // đèn báo trạng thái PIR — đổi màu khi kích hoạt (điều khiển bởi updatePirLedMesh)
    sensorMesh = new THREE.Mesh(
      new THREE.SphereGeometry(0.045, 12, 12),
      makeStdMat(0x2a3145, { emissive: 0x000000 })
    );
    sensorMesh.position.set(0.22, TIER_H*0.75, BIN_D*0.32);
    g.add(sensorMesh);

    return g;
  }

  function makeLabelSprite(text){
    const canvas = document.createElement("canvas");
    canvas.width = 300; canvas.height = 72;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "rgba(18,26,43,.88)";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = "#3aa0ff";
    ctx.lineWidth = 3;
    ctx.strokeRect(1.5, 1.5, canvas.width-3, canvas.height-3);
    ctx.fillStyle = "#e7edf7";
    ctx.font = "bold 24px sans-serif";
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.fillText(text, 14, canvas.height/2);
    const tex = new THREE.CanvasTexture(canvas);
    const mat = new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false });
    const sprite = new THREE.Sprite(mat);
    sprite.scale.set(1.1, 0.26, 1);
    return sprite;
  }

  function buildBin(){
    const g = new THREE.Group();

    const housing = buildOpenFrontHousing(BIN_W, BIN_H, BIN_D, 0xe4e9f2);
    g.add(housing);

    const edges = new THREE.LineSegments(
      new THREE.EdgesGeometry(new THREE.BoxGeometry(BIN_W, BIN_H, BIN_D)),
      new THREE.LineBasicMaterial({ color: 0x38455e })
    );
    edges.position.y = BIN_H/2;
    g.add(edges);

    const tier4 = buildCompartmentsTier(); tier4.position.y = 0; g.add(tier4);
    const tier3 = buildDualServoTier(); tier3.position.y = TIER_H*1; g.add(tier3);
    const tier2 = buildServo1Tier(); tier2.position.y = TIER_H*2; g.add(tier2);
    const tier1 = buildSensorCamTier(); tier1.position.y = TIER_H*3; g.add(tier1);

    // phễu hứng rác trên nóc thùng
    const funnel = new THREE.Mesh(
      new THREE.CylinderGeometry(0.06, 0.24, 0.22, 14, 1, true),
      makeStdMat(0x475269, { side: THREE.DoubleSide })
    );
    funnel.position.y = BIN_H + 0.05;
    g.add(funnel);

    // nhãn từng tầng để dễ nhận diện cấu trúc thật
    const labelX = -BIN_W/2 - 0.75;
    const labels = [
      { y: TIER_H*3.45, text: "Tầng 1 · PIR + ESP32-CAM" },
      { y: TIER_H*2.35, text: "Tầng 2 · Servo 1" },
      { y: TIER_H*1.35, text: "Tầng 3 · 2 Servo song song" },
      { y: TIER_H*0.35, text: "Tầng 4 · 4 ngăn phân loại" },
    ];
    labels.forEach(l=>{
      const sprite = makeLabelSprite(l.text);
      sprite.position.set(labelX, l.y, BIN_D*0.2);
      g.add(sprite);
    });

    return g;
  }

  function buildPlayer(){
    const g = new THREE.Group();
    const body = new THREE.Mesh(
      new THREE.CapsuleGeometry(0.32, 0.55, 4, 10),
      new THREE.MeshStandardMaterial({ color: 0x3aa0ff })
    );
    body.position.y = 0.62; body.castShadow = true;
    g.add(body);
    const head = new THREE.Mesh(
      new THREE.SphereGeometry(0.26, 16, 16),
      new THREE.MeshStandardMaterial({ color: 0xffd9b3 })
    );
    head.position.y = 1.15; head.castShadow = true;
    g.add(head);
    return g;
  }

  function updatePirLedMesh(on){
    if(!sensorMesh) return;
    sensorMesh.material.color.set(on ? 0xffb020 : 0x2a3145);
    sensorMesh.material.emissive.set(on ? 0xffb020 : 0x000000);
    sensorMesh.material.emissiveIntensity = on ? 1.2 : 0;
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
  function updatePlayer(dt){
    let dx = 0, dz = 0;
    if(keys["w"] || keys["arrowup"]) dz -= 1;
    if(keys["s"] || keys["arrowdown"]) dz += 1;
    if(keys["a"] || keys["arrowleft"]) dx -= 1;
    if(keys["d"] || keys["arrowright"]) dx += 1;
    if(dx || dz){
      const len = Math.hypot(dx, dz);
      dx /= len; dz /= len;
      playerGroup.position.x = clamp(playerGroup.position.x + dx*PLAYER_SPEED*dt, -FLOOR_HALF+0.5, FLOOR_HALF-0.5);
      playerGroup.position.z = clamp(playerGroup.position.z + dz*PLAYER_SPEED*dt, -FLOOR_HALF+0.5, FLOOR_HALF-0.5);
      const targetAngle = Math.atan2(dx, dz);
      playerGroup.rotation.y += angleDiff(playerGroup.rotation.y, targetAngle) * Math.min(1, dt*10);
    }
  }
  function distanceToBin(){
    return Math.hypot(playerGroup.position.x - binGroup.position.x, playerGroup.position.z - binGroup.position.z);
  }

  function animate(){
    requestAnimationFrame(animate);
    const dt = Math.min(clock.getDelta(), 0.05);
    updatePlayer(dt);
    if(approachArmed){
      const near = distanceToBin() < TRIGGER_DIST;
      if(near && !wasNear){
        approachArmed = false;
        updatePirLedMesh(true);
        const cb = onApproachCb; onApproachCb = null;
        if(cb) cb();
      }
      wasNear = near;
    }
    renderer.render(scene, camera);
  }

  function init(hostId){
    hostEl = document.getElementById(hostId);

    scene = new THREE.Scene();
    scene.background = new THREE.Color(0xeef2f8);

    camera = new THREE.PerspectiveCamera(42, hostEl.clientWidth / Math.max(1, hostEl.clientHeight), 0.1, 100);
    camera.position.set(0, 6.2, 9.5);
    camera.lookAt(0, 1.5, -3.5);

    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.shadowMap.enabled = true;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    hostEl.appendChild(renderer.domElement);

    scene.add(new THREE.HemisphereLight(0xffffff, 0xc9d2e0, 0.95));
    const dir = new THREE.DirectionalLight(0xffffff, 0.85);
    dir.position.set(5, 10, 6);
    dir.castShadow = true;
    dir.shadow.mapSize.set(1024, 1024);
    scene.add(dir);

    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(FLOOR_HALF*2, FLOOR_HALF*2),
      new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 1 })
    );
    floor.rotation.x = -Math.PI/2;
    floor.receiveShadow = true;
    scene.add(floor);

    const grid = new THREE.GridHelper(FLOOR_HALF*2, FLOOR_HALF*2, 0xc7cfdd, 0xdfe5ee);
    grid.position.y = 0.01;
    scene.add(grid);

    binGroup = buildBin();
    binGroup.position.set(0, 0, -5);
    scene.add(binGroup);

    playerGroup = buildPlayer();
    playerGroup.position.set(0, 0, 4);
    scene.add(playerGroup);

    clock = new THREE.Clock();
    window.addEventListener("resize", onResize);
    onResize();
    requestAnimationFrame(animate);
  }

  window.addEventListener("keydown", e=>{ keys[e.key.toLowerCase()] = true; });
  window.addEventListener("keyup", e=>{ keys[e.key.toLowerCase()] = false; });

  function armApproach(onTriggered){
    approachArmed = true;
    onApproachCb = onTriggered;
    wasNear = distanceToBin() < TRIGGER_DIST; // đứng sẵn trong phạm vi thì chưa kích hoạt ngay, phải ra rồi vào lại
  }
  function disarmApproach(){
    approachArmed = false;
    onApproachCb = null;
  }
  function setPirLed(on){
    updatePirLedMesh(on);
  }
  function resetPlayer(){
    if(playerGroup) playerGroup.position.set(0, 0, 4);
  }

  window.Scene3D = { init, armApproach, disarmApproach, setPirLed, resetPlayer };
})(window);
