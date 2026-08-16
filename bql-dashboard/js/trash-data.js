/**
 * BQL Smart Trash Bin System - Data Layer
 * Mock data & status evaluation logic
 */

window.TRASH_BINS_DATA = [
  {
    id: "BIN-001",
    name: "Sảnh Tòa A1 (Cổng Chính)",
    building: "Tòa A1",
    locationDesc: "Cạnh cửa xoay lối vào",
    lat: 10.776889,
    lng: 106.700806,
    fillLevel: 85,
    batteryLevel: 92,
    capacityLiters: 120,
    type: "Rác hữu cơ",
    lastUpdated: "2 phút trước"
  },
  {
    id: "BIN-002",
    name: "Tầng Trệt Tòa A2 (Thang Máy B)",
    building: "Tòa A2",
    locationDesc: "Hành lang thang máy số 3",
    lat: 10.777500,
    lng: 106.701500,
    fillLevel: 95,
    batteryLevel: 88,
    capacityLiters: 120,
    type: "Rác tái chế",
    lastUpdated: "5 phút trước"
  },
  {
    id: "BIN-003",
    name: "Công Viên Nội Khu (Khu A)",
    building: "Công Viên",
    locationDesc: "Gần sân chơi trẻ em",
    lat: 10.776100,
    lng: 106.702200,
    fillLevel: 65,
    batteryLevel: 74,
    capacityLiters: 240,
    type: "Rác thông thường",
    lastUpdated: "12 phút trước"
  },
  {
    id: "BIN-004",
    name: "Hầm B1 Tòa B1 (Khu Vực Thu Gom)",
    building: "Tòa B1",
    locationDesc: "Gần cột B1-12",
    lat: 10.775200,
    lng: 106.699800,
    fillLevel: 42,
    batteryLevel: 0, // Mất kết nối / Hết pin
    capacityLiters: 660,
    type: "Thùng rác lớn",
    lastUpdated: "4 giờ trước"
  },
  {
    id: "BIN-005",
    name: "Khu Thể Thao Ngoài Trời",
    building: "Công Viên",
    locationDesc: "Gần hồ bơi trung tâm",
    lat: 10.778100,
    lng: 106.703100,
    fillLevel: 25,
    batteryLevel: 95,
    capacityLiters: 120,
    type: "Rác tái chế",
    lastUpdated: "1 phút trước"
  },
  {
    id: "BIN-006",
    name: "Sảnh Tòa B2 (Lối Ra Bãi Xe)",
    building: "Tòa B2",
    locationDesc: "Cửa kính phía tây",
    lat: 10.774900,
    lng: 106.701200,
    fillLevel: 88,
    batteryLevel: 45,
    capacityLiters: 120,
    type: "Rác hữu cơ",
    lastUpdated: "8 phút trước"
  },
  {
    id: "BIN-007",
    name: "Khu Shophouse SH-04",
    building: "Shophouse",
    locationDesc: "Trước cửa hàng tiện lợi",
    lat: 10.778800,
    lng: 106.699500,
    fillLevel: 78,
    batteryLevel: 60,
    capacityLiters: 240,
    type: "Rác tái chế",
    lastUpdated: "15 phút trước"
  },
  {
    id: "BIN-008",
    name: "Sảnh Tòa A3 (Lễ Tân)",
    building: "Tòa A3",
    locationDesc: "Đối diện bàn lễ tân",
    lat: 10.776300,
    lng: 106.698500,
    fillLevel: 15,
    batteryLevel: 99,
    capacityLiters: 120,
    type: "Rác khô",
    lastUpdated: "3 phút trước"
  },
  {
    id: "BIN-009",
    name: "Hầm B2 Tòa A1 (Cạnh Thang Bộ)",
    building: "Tòa A1",
    locationDesc: "Hầm B2 lối thoát hiểm 2",
    lat: 10.777100,
    lng: 106.697900,
    fillLevel: 90,
    batteryLevel: 0, // Mất kết nối / Hết pin + Đầy
    capacityLiters: 240,
    type: "Rác nguy hại",
    lastUpdated: "1 ngày trước"
  },
  {
    id: "BIN-010",
    name: "Tầng 5 Tòa B1 (Khu Tiện Ích)",
    building: "Tòa B1",
    locationDesc: "Gần phòng Gym nội khu",
    lat: 10.774300,
    lng: 106.700300,
    fillLevel: 55,
    batteryLevel: 82,
    capacityLiters: 120,
    type: "Rác tái chế",
    lastUpdated: "7 phút trước"
  }
];

/**
 * Rules according to spec:
 * 1. batteryLevel === 0 => offline (Gray #6B7280, label "HẾT PIN")
 * 2. fillLevel >= 80%   => critical (Neon Red #EF4444, Pulse effect)
 * 3. fillLevel 50-79%   => moderate (Yellow #F59E0B)
 * 4. fillLevel < 50%    => normal (Green #10B981)
 */
function getBinStatus(bin) {
  if (bin.batteryLevel <= 0) {
    return {
      code: "offline",
      label: "Hết pin / Mất kết nối",
      badgeText: "HẾT PIN",
      color: "#6B7280",
      bgColor: "rgba(107, 114, 128, 0.15)",
      borderColor: "#6B7280",
      isPulsing: false
    };
  }
  if (bin.fillLevel >= 80) {
    return {
      code: "critical",
      label: "Cảnh báo đầy (Gấp)",
      badgeText: "ĐẦY CẤP BÁCH",
      color: "#EF4444",
      bgColor: "rgba(239, 68, 68, 0.15)",
      borderColor: "#EF4444",
      isPulsing: true
    };
  }
  if (bin.fillLevel >= 50) {
    return {
      code: "moderate",
      label: "Mức trung bình",
      badgeText: "CẦN THEO DÕI",
      color: "#F59E0B",
      bgColor: "rgba(245, 158, 11, 0.15)",
      borderColor: "#F59E0B",
      isPulsing: false
    };
  }
  return {
    code: "normal",
    label: "Bình thường",
    badgeText: "AN TOÀN",
    color: "#10B981",
    bgColor: "rgba(16, 185, 129, 0.15)",
    borderColor: "#10B981",
    isPulsing: false
  };
}

window.getBinStatus = getBinStatus;
