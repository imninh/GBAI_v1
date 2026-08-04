/**
 * BQL Smart Trash Bin System - Markdown Editor Engine
 * Handles real-time markdown parsing with Marked.js, toolbar helpers,
 * template loading, and downloading markdown documents.
 */

const DEFAULT_BQL_MARKDOWN = `# 📋 QUY TRÌNH & NHẬT KÝ THU GOM RÁC BQL GREENBIN

---

### 📌 1. Trạng Thái Hoạt Động Thùng Rác Thông Minh (Hôm nay)
* **Tổng số điểm giám sát**: 10 điểm cảm biến IoT
* **Điểm cần thu gom gấp (🔴 ≥ 80%)**: Sảnh Tòa A1, Tầng Trệt A2, Sảnh Tòa B2, Hầm B2 A1
* **Điểm cảnh báo pin yếu (⚪ 0%)**: Hầm B1 Tòa B1, Hầm B2 Tòa A1

---

### 🎨 Quy Định Màu Sắc & Hiệu Ứng Cảnh Báo
| Trạng thái | Điều kiện cảm biến | Màu sắc | Hiệu ứng |
| :--- | :--- | :--- | :--- |
| **🟢 Bình thường** | Mức rác \`< 50%\` | Green (\`#10B981\`) | An toàn |
| **🟡 Mức Trung Bình** | Mức rác \`50% - 79%\` | Yellow (\`#F59E0B\`) | Cần theo dõi |
| **🔴 Cảnh báo Đầy** | Mức rác \`≥ 80%\` | Red (\`#EF4444\`) | **Nhấp nháy Pulse** |
| **⚪ Mất Kết Nối** | Pin cảm biến \`0%\` | Gray (\`#6B7280\`) | Gắn nhãn HẾT PIN |

---

### 📝 Ghi Chú Vận Hành & Sự Cố
\`\`\`text
[14:30] Đội Vệ Sinh đã xử lý xong thùng BIN-001 (Sảnh A1).
[15:15] Yêu cầu Kỹ thuật thay pin cảm biến IoT tại BIN-004 (Hầm B1).
[16:00] Báo cáo hoàn tất thu gom rác hữu cơ toàn khu vực.
\`\`\`

> **Lưu ý BQL**: Tất cả quy trình thu gom rác cồng kềnh phải được xác nhận qua ứng dụng BQLOps trước khi điều xe vận chuyển!
`;

document.addEventListener("DOMContentLoaded", () => {
  const textarea = document.getElementById("markdown-input");
  const preview = document.getElementById("markdown-preview-output");

  if (!textarea || !preview) return;

  // Set default initial value
  textarea.value = DEFAULT_BQL_MARKDOWN;

  // Initialize marked options if marked is loaded
  if (window.marked) {
    marked.setOptions({
      gfm: true,
      breaks: true,
      highlight: function (code, lang) {
        if (window.hljs) {
          const language = hljs.getLanguage(lang) ? lang : 'plaintext';
          return hljs.highlight(code, { language }).value;
        }
        return code;
      }
    });
  }

  function renderMarkdown() {
    const rawText = textarea.value;
    if (window.marked) {
      preview.innerHTML = marked.parse(rawText);
    } else {
      preview.textContent = rawText;
    }
  }

  textarea.addEventListener("input", renderMarkdown);
  renderMarkdown(); // Initial render

  // Toolbar action helpers
  window.insertFormatting = function(prefix, suffix = "") {
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const selectedText = textarea.value.substring(start, end);

    const replacement = `${prefix}${selectedText || "văn_bản"}${suffix}`;
    textarea.value = textarea.value.substring(0, start) + replacement + textarea.value.substring(end);
    textarea.focus();
    textarea.setSelectionRange(start + prefix.length, start + prefix.length + (selectedText.length || 7));

    renderMarkdown();
  };

  // Download markdown file helper
  window.downloadMarkdownFile = function() {
    const text = textarea.value;
    const blob = new Blob([text], { type: "text/markdown;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `BQL_BaoCao_ThungRac_${new Date().toISOString().slice(0,10)}.md`;
    link.click();
    URL.revokeObjectURL(url);
    if (window.showToast) {
      showToast("Đã tải xuống file Markdown thành công!");
    }
  };

  // Copy HTML helper
  window.copyRenderedHtml = function() {
    navigator.clipboard.writeText(preview.innerHTML);
    if (window.showToast) {
      showToast("Đã sao chép nội dung HTML rendered vào Clipboard!");
    }
  };
});
