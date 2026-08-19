/**
 * BQL Smart Trash Bin System - Leaflet Map Integration (Senior Architecture)
 * Handles:
 * - Tile Layer initialization (CartoDB Voyager Light Tiles for clean Enterprise UI)
 * - Markers rendering using custom SVG Marker Factory
 * - Interactive Popup rendering with real-time specs
 * - Fit Bounds to enclose all active managed trash bins
 * - Map controls (Zoom, Pan, Reset bounds)
 */

class BQLTrashMap {
  constructor(mapContainerId, options = {}) {
    this.containerId = mapContainerId;
    this.options = options;
    this.map = null;
    this.markersMap = new Map(); // binId -> L.Marker
    this.tileLayer = null;
    this.routePolyline = null;
    this.routeDecorators = [];
  }

  init(binsData) {
    if (!document.getElementById(this.containerId)) {
      console.error(`Map container #${this.containerId} not found.`);
      return;
    }

    // Initialize Leaflet Map centered on Ho Chi Minh City
    this.map = L.map(this.containerId, {
      center: [10.7765, 106.7010],
      zoom: 15,
      zoomControl: false,
      attributionControl: false
    });

    // Custom Zoom control position (top right)
    L.control.zoom({ position: 'topright' }).addTo(this.map);

    // Google Maps Tile Layer
    this.tileLayer = L.tileLayer(
      'https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}&hl=vi&gl=VN',
      {
        maxZoom: 19,
        attribution: '&copy; Google Maps'
      }
    ).addTo(this.map);

    // Render Markers
    if (binsData && binsData.length > 0) {
      this.renderBins(binsData);
      this.fitAllBounds(binsData);
    }
  }

  renderBins(binsData) {
    // Clear existing markers if any
    this.clearMarkers();

    binsData.forEach(bin => {
      const icon = createTrashBinMarkerIcon(bin);
      const marker = L.marker([bin.lat, bin.lng], { icon: icon });

      // Create rich popup content according to spec
      const popupContent = this.buildPopupHtml(bin);
      marker.bindPopup(popupContent, {
        maxWidth: 290,
        className: 'bql-leaflet-custom-popup'
      });

      // Hover animation / interaction
      marker.on('click', () => {
        if (typeof this.options.onBinSelect === 'function') {
          this.options.onBinSelect(bin);
        }
      });

      marker.addTo(this.map);
      this.markersMap.set(bin.id, marker);
    });
  }

  buildPopupHtml(bin) {
    const status = getBinStatus(bin);
    const isOffline = bin.batteryLevel <= 0;

    return `
      <div class="bql-popup-card">
        <div class="bql-popup-header">
          <h4 class="bql-popup-title">${bin.name}</h4>
          <span class="bql-popup-id">${bin.id}</span>
        </div>

        <div class="bql-popup-location">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>
            <circle cx="12" cy="10" r="3"/>
          </svg>
          ${bin.building} • ${bin.locationDesc}
        </div>

        <div class="bql-popup-metrics">
          <div class="bql-popup-metric-box">
            <div class="bql-popup-metric-label">Lượng rác</div>
            <div class="bql-popup-metric-value" style="color: ${status.color}">
              ${bin.fillLevel}%
            </div>
            <div class="popup-progress-track">
              <div class="popup-progress-fill" style="width: ${bin.fillLevel}%; background-color: ${status.color}"></div>
            </div>
          </div>

          <div class="bql-popup-metric-box">
            <div class="bql-popup-metric-label">Pin Cảm Biến</div>
            <div class="bql-popup-metric-value" style="color: ${isOffline ? 'var(--status-offline)' : 'var(--primary-green)'}">
              ${isOffline ? '0%' : `${bin.batteryLevel}%`}
            </div>
            <div class="popup-progress-track">
              <div class="popup-progress-fill" style="width: ${bin.batteryLevel}%; background-color: ${isOffline ? 'var(--status-offline)' : 'var(--primary-green)'}"></div>
            </div>
          </div>
        </div>

        <div style="margin-bottom: 8px; font-size: 12px; display: flex; justify-content: space-between;">
          <span style="color: var(--text-muted)">Trạng thái:</span>
          <span style="font-weight: 800; color: ${status.color}">${status.badgeText}</span>
        </div>

        <div style="font-size: 12px; display: flex; justify-content: space-between; margin-bottom: 12px;">
          <span style="color: var(--text-muted)">Loại dung tích:</span>
          <span style="color: var(--text-secondary); font-weight: 600;">${bin.type} (${bin.capacityLiters}L)</span>
        </div>

        <div class="bql-popup-footer">
          <span>Cập nhật: ${bin.lastUpdated}</span>
        </div>

        <button class="bql-popup-action-btn" onclick="window.dispatchCollectionRequest('${bin.id}')">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
            <polyline points="22 4 12 14.01 9 11.01"/>
          </svg>
          Yêu cầu thu gom ngay
        </button>
      </div>
    `;
  }

  fitAllBounds(binsData) {
    if (!binsData || binsData.length === 0) return;
    const bounds = L.latLngBounds(binsData.map(b => [b.lat, b.lng]));
    this.map.fitBounds(bounds, { padding: [50, 50], maxZoom: 16 });
  }

  focusBin(binId) {
    const marker = this.markersMap.get(binId);
    if (marker) {
      const latLng = marker.getLatLng();
      this.map.flyTo(latLng, 17, { duration: 1.2 });
      setTimeout(() => {
        marker.openPopup();
      }, 600);
    }
  }

  clearMarkers() {
    this.markersMap.forEach(marker => this.map.removeLayer(marker));
    this.markersMap.clear();
  }

  drawRoute(routeResult) {
    this.clearRoute();

    if (!routeResult || !routeResult.route || routeResult.route.length === 0) return;

    const route = routeResult.route;
    const latLngs = route.map(item => [item.lat, item.lng]);

    // Outer Glow Polyline (Emerald Green)
    const glowLine = L.polyline(latLngs, {
      color: '#059669',
      weight: 8,
      opacity: 0.35,
      lineCap: 'round',
      lineJoin: 'round'
    }).addTo(this.map);

    // Core Animated Polyline (Bright Mint)
    this.routePolyline = L.polyline(latLngs, {
      color: '#10B981',
      weight: 4,
      opacity: 0.95,
      dashArray: '10, 10',
      className: 'animated-route-line',
      lineCap: 'round',
      lineJoin: 'round'
    }).addTo(this.map);

    this.routeDecorators.push(glowLine, this.routePolyline);

    // Numbered step badges on route markers
    route.forEach((item, index) => {
      let isDepot = item.isDepot;
      let badgeColor = isDepot ? '#0284C7' : '#059669';
      let badgeLabel = isDepot ? (index === 0 ? 'XUẤT PHÁT' : 'ĐÍCH') : `BƯỚC ${index}`;

      const stepBadgeIcon = L.divIcon({
        html: `<div class="route-step-badge" style="background:${badgeColor}; border: 2px solid #FFFFFF;">${badgeLabel}</div>`,
        className: 'route-badge-container',
        iconSize: [64, 22],
        iconAnchor: [32, 70]
      });

      const badgeMarker = L.marker([item.lat, item.lng], { icon: stepBadgeIcon }).addTo(this.map);
      this.routeDecorators.push(badgeMarker);
    });

    // Zoom to fit entire route
    const bounds = L.latLngBounds(latLngs);
    this.map.fitBounds(bounds, { padding: [60, 60], maxZoom: 16 });
  }

  clearRoute() {
    if (this.routeDecorators && this.routeDecorators.length > 0) {
      this.routeDecorators.forEach(layer => this.map.removeLayer(layer));
      this.routeDecorators = [];
    }
    this.routePolyline = null;
  }
}

window.BQLTrashMap = BQLTrashMap;
