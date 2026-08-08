# BQL Smart Trash Bin Management Dashboard (`GreenBin Ops`)

> **Tài liệu Hướng dẫn Vận hành & Kiến trúc Hệ thống Dashboard Giám sát Thùng rác Thông minh dành cho Ban Quản Lý (BQL)**

![GreenBin Ops Banner](https://img.shields.io/badge/BQL%20Ops-GreenBin%20v2.0-059669?style=for-the-badge&logo=leaflet)
![UI Design](https://img.shields.io/badge/Design-Emerald%20%26%20White-10B981?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)

---

## 📖 1. Giới thiệu Tổng quan

**BQL Smart Trash Bin Dashboard** là trung tâm điều hành & giám sát vận hành rác thải đô thị / chung cư dành cho Ban Quản Lý tòa nhà (**BQL GreenBin Ops**). Hệ thống giúp giải quyết các vấn đề rác thải ùn tắc, quá tải thông qua dữ liệu IoT realtime, hỗ trợ điều xe thu gom tự động và tự động tối ưu hóa tuyến đường di chuyển.

### 🌟 Các Tính Năng Cốt Lõi:
1. **Bản đồ Giám sát IoT Realtime (`index.html`):** Trực quan hóa các điểm thu gom rác trên bản đồ tương tác Leaflet.js với vector tiles chất lượng cao (`CartoDB Voyager`).
2. **Biểu tượng Thùng rác Động (Dynamic SVG Markers):** Hiển thị mức rác dâng theo thời gian thực (0-100%), cảnh báo nhấp nháy đỏ khi vượt ngưỡng 80% (quá tải) và cảnh báo điểm mất kết nối / hết pin.
3. **Bộ lọc & Thống kê KPI:** Phân loại nhanh các thùng rác theo trạng thái: *Đầy cấp bách 🔴*, *Mức trung bình 🟡*, *Bình thường 🟢*, *Hết pin/Offline ⚪*.
4. **Thuật toán Tối ưu Tuyến đường (TSP Route Optimizer):** Tự động tính toán tuyến đường ngắn nhất cho xe thu gom đi qua các thùng rác đang đầy, giúp tiết kiệm thời gian và nhiên liệu di chuyển.
5. **Chế độ Giao diện Dual Theme (Light & Dark Emerald):** Cho phép chuyển đổi linh hoạt giữa giao diện chuẩn **Sáng Emerald Green & Pearl White** và giao diện **Dark Emerald** tùy điều kiện ánh sáng.
6. **Công cụ Soạn thảo Báo cáo Markdown (`markdown.html`):** Hỗ trợ BQL soạn thảo báo cáo vận hành định kỳ với tính năng preview thời gian thực, sao chép HTML và xuất file `.md`.

---

## 🛠️ 2. Cấu trúc Thư mục

```text
bql-dashboard/
├── index.html              # Trang chính: Bản đồ giám sát IoT & Bảng điều khiển BQL
├── markdown.html           # Trang báo cáo: Trình soạn thảo & xem trước Markdown
├── README.md               # Tài liệu hướng dẫn sử dụng & vận hành hệ thống
├── css/
│   ├── dashboard.css       # Design Tokens, Layout Grid, Modern Elevation & Theme Vars
│   ├── map.css             # Leaflet custom styling, Pin markers, Popup cards, Route line animation
│   └── markdown.css        # GFM styling, Split editor/preview layout, formatting toolbar
└── js/
    ├── app.js              # Controller chính, Theme Switcher & Toast Notifications
    ├── map.js              # Khởi tạo Leaflet Map, Tile Layer CartoDB, Route Polyline
    ├── route-optimizer.js  # Thuật toán TSP (Nearest Neighbor) tối ưu lộ trình xe rác
    ├── stats.js            # Quản lý danh sách thùng rác, bộ lọc & chỉ số KPI Sidebar
    ├── trash-data.js       # Dữ liệu Mock IoT thùng rác & Hàm phân tích trạng thái
    ├── trash-marker.js     # SVG Marker Factory tạo icon thùng rác với mực rác động
    └── markdown-editor.js  # Logic trình soạn thảo Markdown, marked.js & highlight.js
```

---

## 🚀 3. Hướng dẫn Khởi chạy (How to Run)

Vì ứng dụng được xây dựng theo kiến trúc **Modern Frontend (Pure HTML5 / CSS3 / ES6 Javascript)**, bạn có thể khởi chạy ứng dụng cực kỳ đơn giản theo các cách dưới đây:

### Cách 1: Khởi chạy với Python (Khuyên dùng 💡)

Mở terminal/cmd tại thư mục `bql-dashboard` và thực thi lệnh:

```bash
# Di chuyển vào thư mục bql-dashboard
cd bql-dashboard

# Chạy HTTP Server tích hợp của Python ở cổng 8080
python -m http.server 8080
```

Truy cập trên trình duyệt web tại địa chỉ:
👉 **`http://localhost:8080`**

---

### Cách 2: Khởi chạy với Node.js / NPX (`serve` / `http-server`)

Nếu máy tính của bạn đã cài đặt Node.js:

```bash
cd bql-dashboard

# Sử dụng package 'serve'
npx serve -l 8080

# Hoặc sử dụng package 'http-server'
npx http-server -p 8080
```

Sau đó mở trình duyệt tại: **`http://localhost:8080`**

---

### Cách 3: Dùng Live Server Extension trong VS Code

1. Mở thư mục `bql-dashboard` bằng **Visual Studio Code**.
2. Cài đặt Extension **Live Server** (của Ritwick Dey).
3. Nhấp chuột phải vào file `index.html` chọn **"Open with Live Server"** (hoặc bấm phím tắt `Alt + L, Alt + O`).

---

### Cách 4: Mở Trực tiếp trong Trình duyệt (Offline Mode)

Bạn có thể double-click trực tiếp vào file `index.html` hoặc drag-and-drop file `index.html` vào trình duyệt (Chrome, Edge, Firefox, Safari).  
*(Lưu ý: Một số tính năng tile bản đồ cần có kết nối Internet để tải dữ liệu OpenStreetMap/CartoDB).*

---

## 🎯 4. Hướng dẫn Sử dụng Chi tiết (Operational Guide)

### 🗺️ 1. Giám sát Bản đồ & Tìm kiếm
- **Xem toàn bộ điểm rác:** Nhấn nút **"Fit Bounds (Toàn bộ)"** ở thanh công cụ nổi trên bản đồ để căn tự động khung nhìn vừa tất cả các vị trí thùng rác.
- **Lọc thùng rác:** Chọn các chip lọc ở thanh điều hướng bên trái (*🔴 Đầy*, *🟡 Trung bình*, *🟢 Bình thường*, *⚪ Hết pin*) hoặc nhập từ khóa tìm kiếm (tên tòa nhà, mã thùng `BIN-001`).
- **Xem chi tiết 1 thùng:** Click vào thẻ trong danh sách hoặc nhấp vào biểu tượng thùng rác trên bản đồ để xem chi tiết % rác, % pin cảm biến và thời gian cập nhật.

### 🚚 2. Điều Xe & Tối ưu Tuyến đường Thu gom
- **Tối ưu theo thuật toán TSP:** Nhấn nút **"🗺️ Tối Ưu Tuyến Đường (TSP)"** trên bản đồ. Hệ thống sẽ tự động tìm tuyến đường ngắn nhất kết nối từ **Trạm Tập Kết** qua tất cả các thùng rác có mức rác $\ge 50\%$.
- **Xem lộ trình:** Bảng điều khiển lộ trình sẽ xuất hiện hiển thị tổng quãng đường (km), thời gian ước tính (phút) và thứ tự chi tiết các chặng dừng.
- **Điều xe ngay:** Nhấn nút **"🚀 Điều Xe Theo Tuyến Đường Này"** hoặc nút **"Yêu cầu thu gom ngay"** trên popup của từng thùng để gửi lệnh đến tổ đội vệ sinh.

### 🎨 3. Chuyển đổi Giao diện (Theme Switcher)
- Nhấn vào biểu tượng **Mặt Trăng / Mặt Trời** ở góc dưới cùng thanh điều hướng thanh Nav Rail bên trái để chuyển giữa:
  - **Light Mode (Default):** Tông màu Xanh Emerald & Trắng thanh lịch, phù hợp làm việc ban ngày.
  - **Dark Mode:** Tông màu Đen Emerald sang trọng, dịu mắt làm việc ban đêm.

### 📝 4. Soạn thảo Báo cáo BQL
- Nhấp vào biểu tượng **Báo cáo Markdown** trên thanh Nav Rail để chuyển sang trang `markdown.html`.
- Nhập nội dung báo cáo bên khung trái hoặc bấm các nút công cụ định dạng nhanh (B, I, H1, H2, Danh sách, Bảng).
- Khung xem trước Preview bên phải sẽ cập nhật trực tiếp theo chuẩn GitHub Flavored Markdown (GFM).
- Nhấn **"Sao chép HTML"** hoặc **"Tải File .MD"** để lưu báo cáo.

---

## 📊 5. Quy chuẩn Trạng thái Thùng Rác

| Trạng thái | Ngưỡng chỉ số | Mã màu UI | Hiệu ứng trên bản đồ |
| :--- | :--- | :--- | :--- |
| **🔴 Đầy Cấp Bách** | Mức rác $\ge 80\%$ | `#EF4444` (Đỏ) | Icon nhấp nháy Pulse đỏ, cảnh báo "95% RÁC" |
| **🟡 Cần Theo Dõi** | Mức rác $50\% \rightarrow 79\%$ | `#F59E0B` (Vàng) | Biểu tượng viền vàng |
| **🟢 An Toàn** | Mức rác $< 50\%$ | `#059669` (Xanh Emerald) | Biểu tượng viền xanh lá |
| **⚪ Offline / Hết Pin** | Pin cảm biến $= 0\%$ | `#64748B` (Xám) | Khóa xám biểu tượng, gán nhãn "HẾT PIN" |

---

## 👨‍💻 6. Thông tin Phát triển & Bảo trì

- **Phiên bản:** v2.0 Enterprise Redesign
- **Bộ chuẩn UI:** Senior Clean Architecture, CSS Variables & Design Tokens System
- **Tác giả:** Team Phát triển GreenBin Ops / Ban Quản Lý (BQL)
