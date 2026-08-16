/**
 * BQL Smart Trash Bin System - Marker Factory
 * Creates dynamic SVG Leaflet Marker Icons according to exact design spec:
 * - Constant Trash Can Icon SVG path
 * - Dynamic liquid level filling from bottom to top (0-100%)
 * - Status-based color fill & pulse animations
 * - Offline badge when battery = 0%
 */

function createTrashBinMarkerIcon(bin) {
  const status = getBinStatus(bin);
  const fillPct = Math.min(100, Math.max(0, bin.fillLevel));
  const isOffline = status.code === "offline";
  const isPulsing = status.isPulsing;

  // Liquid height calculation for SVG inside 48x54 box
  // Can body height in SVG coordinate system: y from 18 (top of can body) to 48 (bottom)
  const canBottom = 48;
  const canTop = 18;
  const maxFillHeight = canBottom - canTop; // 30 units
  const liquidY = canBottom - (maxFillHeight * (fillPct / 100));

  const pulseClass = isPulsing ? "marker-pulse-critical" : "";
  const offlineClass = isOffline ? "marker-offline" : "";

  // Dynamic SVG html
  const svgHtml = `
    <div class="trash-marker-wrapper ${pulseClass} ${offlineClass}">
      ${isPulsing ? `<div class="pulse-ring" style="background-color: ${status.color}"></div>` : ''}
      <div class="trash-marker-card" style="border-color: ${status.color}">
        <svg viewBox="0 0 48 54" width="42" height="48" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <!-- Clip path for the trash can body container so liquid stays strictly within walls -->
            <clipPath id="bin-clip-${bin.id}">
              <path d="M 12 18 L 14 46 C 14 47.5 15.5 48 17 48 L 31 48 C 32.5 48 34 47.5 34 46 L 36 18 Z" />
            </clipPath>

            <!-- Dynamic liquid gradient -->
            <linearGradient id="liquid-grad-${bin.id}" x1="0" y1="1" x2="0" y2="0">
              <stop offset="0%" stop-color="${status.color}" stop-opacity="0.9" />
              <stop offset="100%" stop-color="${status.color}" stop-opacity="0.65" />
            </linearGradient>
          </defs>

          <!-- Outer Glow Shadow -->
          <filter id="shadow-${bin.id}" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="${status.color}" flood-opacity="0.5"/>
          </filter>

          <!-- Trash Can Lid Handles & Lid -->
          <!-- Handle bar -->
          <path d="M 19 6 L 19 4 C 19 3 20 2 21 2 L 27 2 C 28 2 29 3 29 4 L 29 6" 
                fill="none" stroke="${status.color}" stroke-width="2.5" stroke-linecap="round" />
          
          <!-- Lid Top Plate -->
          <path d="M 8 10 C 8 8.5 9.5 8 11 8 L 37 8 C 38.5 8 40 8.5 40 10 L 40 13 L 8 13 Z" 
                fill="${isOffline ? '#4B5563' : '#1E293B'}" stroke="${status.color}" stroke-width="2" />

          <!-- Bin Body Outline (Background) -->
          <path d="M 12 18 L 14 46 C 14 47.5 15.5 48 17 48 L 31 48 C 32.5 48 34 47.5 34 46 L 36 18 Z" 
                fill="rgba(15, 23, 42, 0.85)" stroke="${status.color}" stroke-width="2" stroke-linejoin="round"/>

          <!-- Dynamic Liquid Level Filling -->
          <g clip-path="url(#bin-clip-${bin.id})">
            <rect x="10" y="${liquidY}" width="28" height="${canBottom - liquidY + 2}" 
                  fill="url(#liquid-grad-${bin.id})" />
            <!-- Liquid Surface Wave Accent Line -->
            ${fillPct > 0 ? `<line x1="10" y1="${liquidY}" x2="38" y2="${liquidY}" stroke="${status.color}" stroke-width="1.5" opacity="0.9" />` : ''}
          </g>

          <!-- Trash Can Vertical Rib Details (Transparent Overlay Lines) -->
          <line x1="19" y1="21" x2="20" y2="43" stroke="rgba(255,255,255,0.25)" stroke-width="1.5" stroke-linecap="round" />
          <line x1="24" y1="21" x2="24" y2="43" stroke="rgba(255,255,255,0.25)" stroke-width="1.5" stroke-linecap="round" />
          <line x1="29" y1="21" x2="28" y2="43" stroke="rgba(255,255,255,0.25)" stroke-width="1.5" stroke-linecap="round" />

          <!-- Fill Level Text Inside Marker SVG -->
          <text x="24" y="34" text-anchor="middle" font-family="Inter, sans-serif" font-weight="800" font-size="9.5" fill="#FFFFFF" style="text-shadow: 0px 1px 3px rgba(0,0,0,0.9);">
            ${isOffline ? 'OFF' : `${fillPct}%`}
          </text>
        </svg>

        ${isOffline ? `<div class="offline-badge">HẾT PIN</div>` : ''}
        ${isPulsing ? `<div class="alert-pulse-badge">95% RÁC</div>` : ''}
      </div>
      <div class="marker-pin-tail" style="border-top-color: ${status.color}"></div>
    </div>
  `;

  return L.divIcon({
    html: svgHtml,
    className: "custom-trash-leaflet-icon",
    iconSize: [52, 60],
    iconAnchor: [26, 58],
    popupAnchor: [0, -56]
  });
}

window.createTrashBinMarkerIcon = createTrashBinMarkerIcon;
