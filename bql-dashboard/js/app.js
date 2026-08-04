/**
 * BQL Smart Trash Bin System - App Entry Point & Controller
 * Glues Map & Sidebar Stats Manager together
 */

document.addEventListener("DOMContentLoaded", () => {
  const binsData = window.TRASH_BINS_DATA || [];

  // Initialize Map
  const trashMap = new BQLTrashMap("map-container", {
    onBinSelect: (bin) => {
      if (statsManager) {
        statsManager.highlightBinInList(bin.id);
      }
    }
  });
  trashMap.init(binsData);
  window.trashMapInstance = trashMap;

  // Initialize Sidebar Stats Manager
  const statsManager = new BQLStatsManager();
  statsManager.init(binsData);
  window.statsManagerInstance = statsManager;

  // Global helper to select bin from list click
  window.selectBinFromList = function(binId) {
    statsManager.highlightBinInList(binId);
    trashMap.focusBin(binId);
  };

  // Global helper for Fit Bounds button
  window.fitAllMapBounds = function() {
    trashMap.fitAllBounds(binsData);
    showToast("Đã tự động căn chỉnh khung nhìn bản đồ (Fit Bounds)");
  };

  // Route Optimizer Initialization
  const optimizer = new BQLRouteOptimizer();
  window.optimizerInstance = optimizer;

  window.generateShortestRoute = function(onlyCritical = false) {
    let targetBins = binsData.filter(b => b.batteryLevel > 0); // Active bins
    if (onlyCritical) {
      targetBins = targetBins.filter(b => b.fillLevel >= 80);
    } else {
      // Urgent or moderate
      targetBins = targetBins.filter(b => b.fillLevel >= 50);
    }

    if (targetBins.length === 0) {
      showToast("Không có thùng rác nào cần thu gom trong điều kiện lọc hiện tại!");
      return;
    }

    const routeResult = optimizer.calculateShortestRoute(targetBins);
    trashMap.drawRoute(routeResult);
    renderRoutePanel(routeResult);
    showToast(`🗺️ Đã tính toán đường đi ngắn nhất qua ${routeResult.binCount} thùng rác (${routeResult.totalDistanceKm} km)!`);
  };

  window.clearRouteOnMap = function() {
    trashMap.clearRoute();
    const panel = document.getElementById("route-panel-modal");
    if (panel) panel.style.display = "none";
    showToast("Đã xóa tuyến đường thu gom.");
  };

  function renderRoutePanel(routeResult) {
    let panel = document.getElementById("route-panel-modal");
    if (!panel) {
      panel = document.createElement("div");
      panel.id = "route-panel-modal";
      panel.className = "route-panel-modal";
      document.querySelector(".map-view-wrapper").appendChild(panel);
    }

    panel.style.display = "flex";
    panel.innerHTML = `
      <div class="route-modal-header">
        <div class="route-modal-title">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <polyline points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polyline>
          </svg>
          Lộ Trình Thu Gom Tối Ưu
        </div>
        <button class="tb-btn" onclick="window.clearRouteOnMap()" style="color: #94A3B8;">✕</button>
      </div>

      <div class="route-stats-bar">
        <div>
          <div class="route-stat-val">${routeResult.totalDistanceKm} <span style="font-size:12px">km</span></div>
          <div class="route-stat-lbl">Quãng đường</div>
        </div>
        <div>
          <div class="route-stat-val">${routeResult.estimatedMinutes} <span style="font-size:12px">phút</span></div>
          <div class="route-stat-lbl">Thời gian ước tính</div>
        </div>
      </div>

      <div style="font-size: 11px; font-weight: 700; color: #94A3B8; text-transform: uppercase;">
        Thứ tự di chuyển (${routeResult.route.length - 1} chặng):
      </div>

      <div class="route-steps-list">
        ${routeResult.route.map((step, idx) => {
          const isDepot = step.isDepot;
          return `
            <div class="route-step-card" onclick="window.selectBinFromList('${step.id}')" style="cursor: pointer;">
              <div class="route-step-num" style="${isDepot ? 'background: #3B82F6;' : ''}">${isDepot ? (idx === 0 ? 'S' : 'E') : idx}</div>
              <div class="route-step-info">
                <div class="route-step-name">${step.name}</div>
                <div class="route-step-desc">${step.building} • ${isDepot ? 'Trạm Tập Kết' : `${step.fillLevel}% rác`}</div>
              </div>
            </div>
          `;
        }).join('')}
      </div>

      <button class="bql-popup-action-btn" onclick="window.dispatchCollectionRequest('ROUTE_BATCH')" style="margin-top: 4px;">
        🚀 Điều Xe Theo Tuyến Đường Này
      </button>
    `;
  }

  // Global helper for dispatching collection request
  window.dispatchCollectionRequest = function(binId) {
    const bin = binsData.find(b => b.id === binId);
    if (!bin) return;

    showToast(`🟢 Đã phát lệnh thu gom tới Đội Vệ Sinh cho ${bin.name} (${bin.id})!`);
  };
});

/**
 * Toast Notification Helper
 */
function showToast(message) {
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    container.className = "toast-container";
    document.body.appendChild(container);
  }

  const toast = document.createElement("div");
  toast.className = "toast";
  toast.innerHTML = `
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2">
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
      <polyline points="22 4 12 14.01 9 11.01"/>
    </svg>
    <span>${message}</span>
  `;

  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateX(100%)";
    toast.style.transition = "all 0.3s ease";
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

window.showToast = showToast;
