/**
 * BQL Smart Trash Bin System - Sidebar Stats & Bin List Manager
 * Renders summary metrics cards, filter tabs, search functionality,
 * and syncs interaction between sidebar list and map markers.
 */

class BQLStatsManager {
  constructor(options = {}) {
    this.options = options;
    this.allBins = [];
    this.activeFilter = "all";
    this.searchQuery = "";
  }

  init(binsData) {
    this.allBins = binsData;
    this.renderStatsCards();
    this.renderBinList();
    this.setupEventListeners();
  }

  getFilteredBins() {
    return this.allBins.filter(bin => {
      const status = getBinStatus(bin);
      
      // Filter tab check
      let matchesFilter = true;
      if (this.activeFilter === "critical") matchesFilter = status.code === "critical";
      else if (this.activeFilter === "moderate") matchesFilter = status.code === "moderate";
      else if (this.activeFilter === "normal") matchesFilter = status.code === "normal";
      else if (this.activeFilter === "offline") matchesFilter = status.code === "offline";

      // Search query check
      let matchesSearch = true;
      if (this.searchQuery.trim() !== "") {
        const query = this.searchQuery.toLowerCase();
        matchesSearch = bin.name.toLowerCase().includes(query) ||
                        bin.id.toLowerCase().includes(query) ||
                        bin.building.toLowerCase().includes(query) ||
                        bin.locationDesc.toLowerCase().includes(query);
      }

      return matchesFilter && matchesSearch;
    });
  }

  renderStatsCards() {
    const total = this.allBins.length;
    let criticalCount = 0;
    let moderateCount = 0;
    let normalCount = 0;
    let offlineCount = 0;

    this.allBins.forEach(bin => {
      const status = getBinStatus(bin);
      if (status.code === "critical") criticalCount++;
      else if (status.code === "moderate") moderateCount++;
      else if (status.code === "normal") normalCount++;
      else if (status.code === "offline") offlineCount++;
    });

    // Update DOM elements if present
    const elTotal = document.getElementById("stat-total");
    const elCritical = document.getElementById("stat-critical");
    const elModerate = document.getElementById("stat-moderate");
    const elNormal = document.getElementById("stat-normal");
    const elOffline = document.getElementById("stat-offline");

    if (elTotal) elTotal.textContent = total;
    if (elCritical) elCritical.textContent = criticalCount;
    if (elModerate) elModerate.textContent = moderateCount;
    if (elNormal) elNormal.textContent = normalCount;
    if (elOffline) elOffline.textContent = offlineCount;
  }

  renderBinList() {
    const container = document.getElementById("bin-list-container");
    if (!container) return;

    const filtered = this.getFilteredBins();
    const countBadge = document.getElementById("filtered-count");
    if (countBadge) countBadge.textContent = `${filtered.length} thùng`;

    if (filtered.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#64748B" stroke-width="1.5">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          <p>Không tìm thấy thùng rác phù hợp điều kiện lọc</p>
        </div>
      `;
      return;
    }

    container.innerHTML = filtered.map(bin => {
      const status = getBinStatus(bin);
      const isOffline = status.code === "offline";

      return `
        <div class="bin-item-card ${status.code === 'critical' ? 'bin-item-critical' : ''}" 
             data-bin-id="${bin.id}"
             onclick="window.selectBinFromList('${bin.id}')">
          <div class="bin-item-header">
            <div class="bin-item-title-group">
              <span class="bin-status-indicator" style="background-color: ${status.color}; box-shadow: 0 0 8px ${status.color}"></span>
              <h4 class="bin-item-name">${bin.name}</h4>
            </div>
            <span class="bin-id-badge">${bin.id}</span>
          </div>

          <div class="bin-item-location">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>
              <circle cx="12" cy="10" r="3"/>
            </svg>
            ${bin.building} • ${bin.locationDesc}
          </div>

          <div class="bin-item-metrics">
            <div class="bin-metric-col">
              <span class="bin-metric-label">Mức rác</span>
              <span class="bin-metric-value" style="color: ${status.color}">${bin.fillLevel}%</span>
            </div>

            <div class="bin-metric-col">
              <span class="bin-metric-label">Pin Cảm Biến</span>
              <span class="bin-metric-value" style="color: ${isOffline ? '#6B7280' : '#10B981'}">
                ${isOffline ? '0%' : `${bin.batteryLevel}%`}
              </span>
            </div>

            <div class="bin-metric-col" style="text-align: right;">
              <span class="bin-status-tag" style="background: ${status.bgColor}; color: ${status.color}; border: 1px solid ${status.borderColor}">
                ${status.badgeText}
              </span>
            </div>
          </div>

          <div class="bin-progress-bar-wrap">
            <div class="bin-progress-bar-fill" style="width: ${bin.fillLevel}%; background-color: ${status.color}"></div>
          </div>
        </div>
      `;
    }).join("");
  }

  setupEventListeners() {
    // Filter tabs
    const filterButtons = document.querySelectorAll(".filter-chip");
    filterButtons.forEach(btn => {
      btn.addEventListener("click", (e) => {
        filterButtons.forEach(b => b.classList.remove("active"));
        e.currentTarget.classList.add("active");
        this.activeFilter = e.currentTarget.getAttribute("data-filter") || "all";
        this.renderBinList();
      });
    });

    // Search input
    const searchInput = document.getElementById("search-bin-input");
    if (searchInput) {
      searchInput.addEventListener("input", (e) => {
        this.searchQuery = e.target.value;
        this.renderBinList();
      });
    }
  }

  highlightBinInList(binId) {
    const cards = document.querySelectorAll(".bin-item-card");
    cards.forEach(card => card.classList.remove("selected"));

    const targetCard = document.querySelector(`.bin-item-card[data-bin-id="${binId}"]`);
    if (targetCard) {
      targetCard.classList.add("selected");
      targetCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }
}

window.BQLStatsManager = BQLStatsManager;
