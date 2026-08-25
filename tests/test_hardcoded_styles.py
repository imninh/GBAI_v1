"""Test to scan for hardcoded styles that should use CSS tokens.

This test enforces:
1. No hardcoded hex colors (#xxxxxx) in .tsx files except allowed exceptions
   (only contexts where `var()` cannot work: PWA themeColor meta, Leaflet
   pathOptions setAttribute, SVG presentation attributes for mascot/illustration).
2. No `bg-white` utility class — replaced by `bg-surface` (token --color-surface).
3. No `var(--color-*)` reference pointing at a token that is not defined in
   `globals.css` @theme — a dead CSS variable renders fallback (black) silently.
"""

import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).parent.parent / "frontend"
FRONTEND_SRC = FRONTEND / "src"

# Hex màu còn sót lại sau đợt F2-B — MỌI GIÁ TRỊ Ở ĐÂY PHẢI KÈM LÝ DO.
# Nguyên tắc: nếu `var(--color-*)` chạy được ở ngữ cảnh đó thì KHÔNG được phép
# nằm trong danh sách này. Chỉ giữ lại ngữ cảnh var() bất lực:
#   - themeColor (PWA meta, không phải CSS)
#   - Leaflet `pathOptions` (Leaflet set `stroke` qua `setAttribute` — var() không nở)
#   - SVG presentation attribute `fill`/`stroke` của hình vẽ (mascot, minh hoạ cây)
ALLOWED_HEX_COLORS: dict[str, str] = {
    # layout.tsx themeColor — trình duyệt đọc thẳng giá trị hex, không qua CSS
    "#2fae66": "PWA themeColor meta (layout.tsx)",
    # Leaflet pathOptions — var() không hoạt động qua setAttribute
    "#1f6feb": "bin-map.tsx polyline (Leaflet pathOptions)",
    "#1a73e8": "navigation-mode.tsx polyline nền (Leaflet pathOptions)",
    "#4285f4": "navigation-mode.tsx polyline chính (Leaflet pathOptions)",
    "#1f8a4f": "route-map-base.tsx polyline (Leaflet pathOptions)",
    # SVG presentation attributes — fill/stroke qua thuộc tính SVG, var() không nở
    "#8a9a92": "onboarding.tsx mascot SVG fill",
    "#cfdcd4": "onboarding.tsx mascot SVG fill",
    "#3a453d": "onboarding.tsx mascot SVG fill",
    "#16211a": "onboarding.tsx mascot SVG fill/stroke",
    "#2f7fe0": "ask.tsx icon SVG stroke",
    "#8a7a5a": "result.tsx icon SVG stroke",
    "#fff": "SVG stroke trắng trên nền màu (ask/onboarding/result)",
    "#c67139": "personal.tsx cây minh hoạ SVG fill",
    "#a85f30": "personal.tsx cây minh hoạ SVG fill",
    "#4a3524": "personal.tsx cây minh hoạ SVG fill",
    "#728157": "personal.tsx cây minh hoạ SVG fill",
    "#ffb88c": "personal.tsx cây minh hoạ SVG fill",
}


# Trang demo thiết bị 3D standalone (teammate) — màu khớp scene Three.js, không phải
# UI app nên nằm ngoài kỷ luật token app. Loại khỏi phạm vi quét.
EXCLUDE_DIRS = ("app/demo-thiet-bi",)


def find_tsx_files() -> list[Path]:
    out: list[Path] = []
    for f in FRONTEND_SRC.rglob("*.tsx"):
        rel = f.relative_to(FRONTEND_SRC).as_posix()
        if any(rel == d or rel.startswith(d + "/") for d in EXCLUDE_DIRS):
            continue
        out.append(f)
    return out


def _vi_pham(content: str, pattern: re.Pattern[str], path: Path) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for match in pattern.finditer(content):
        line_num = content[: match.start()].count("\n") + 1
        lines = content.split("\n")
        context = lines[line_num - 1].strip() if line_num <= len(lines) else ""
        out.append((line_num, context[:120]))
    return out


def scan_hex_colors() -> list[dict]:
    """Scan for hardcoded hex colors not in the allowed exception map."""
    violations = []
    hex_pattern = re.compile(r"#[0-9a-fA-F]{6}")
    for file_path in find_tsx_files():
        content = file_path.read_text(encoding="utf-8")
        for line_num, context in _vi_pham(content, hex_pattern, file_path):
            color = re.search(r"#[0-9a-fA-F]{6}", context).group().lower()
            if color not in ALLOWED_HEX_COLORS:
                violations.append(
                    {
                        "file": str(file_path.relative_to(FRONTEND_SRC.parent)),
                        "line": line_num,
                        "color": color,
                        "context": context,
                    }
                )
    return violations


def scan_bg_white() -> list[dict]:
    """Scan for `bg-white` utility — must be `bg-surface` (token --color-surface).

    `bg-white` trong class khác (`border-white`, `ring-white`, `divide-white`)
    là cố ý giữ để làm viền/ring tách khỏi nền, không nằm trong đợt gom này.
    """
    violations = []
    bg_white = re.compile(r"\bbg-white\b")
    for file_path in find_tsx_files():
        content = file_path.read_text(encoding="utf-8")
        for line_num, context in _vi_pham(content, bg_white, file_path):
            violations.append(
                {
                    "file": str(file_path.relative_to(FRONTEND_SRC.parent)),
                    "line": line_num,
                    "context": context,
                }
            )
    return violations


def _token_defined() -> set[str]:
    """Đọc danh sách token `--color-*` được định nghĩa trong globals.css."""
    css = (FRONTEND / "src" / "app" / "globals.css").read_text(encoding="utf-8")
    defined = set(re.findall(r"--color-([a-zA-Z0-9-]+)\s*:", css))
    return defined


def scan_dead_css_vars() -> list[dict]:
    """Scan `var(--color-*)` trong .tsx trỏ token không có trong globals.css.

    Biến chết là lỗi âm thầm: trình duyệt lấy fallback (thường là đen), giao
    diện đổi màu mà không ai báo. Phải là test chặn cứng.
    """
    violations = []
    var_ref = re.compile(r"var\(--color-([a-zA-Z0-9-]+)\)")
    defined = _token_defined()
    for file_path in find_tsx_files():
        content = file_path.read_text(encoding="utf-8")
        for match in var_ref.finditer(content):
            if match.group(1) not in defined:
                line_num = content[: match.start()].count("\n") + 1
                lines = content.split("\n")
                context = lines[line_num - 1].strip() if line_num <= len(lines) else ""
                violations.append(
                    {
                        "file": str(file_path.relative_to(FRONTEND_SRC.parent)),
                        "line": line_num,
                        "var": f"--color-{match.group(1)}",
                        "context": context[:120],
                    }
                )
    return violations


class TestHardcodedStyles:
    def test_no_hardcoded_hex_colors(self):
        """Không có hex gõ cứng ngoài exception có lý do."""
        violations = scan_hex_colors()
        if violations:
            for v in violations[:20]:
                print(f"  {v['file']}:{v['line']} - {v['color']} - {v['context']}")
            pytest.fail(
                f"Found {len(violations)} hardcoded hex colors không có trong "
                f"ALLOWED_HEX_COLORS (kèm lý do). Xem output trên."
            )

    def test_bg_white_uses_surface_token(self):
        """`bg-white` phải dùng `bg-surface` — token --color-surface."""
        violations = scan_bg_white()
        if violations:
            for v in violations[:20]:
                print(f"  {v['file']}:{v['line']} - {v['context']}")
            pytest.fail(
                f"Found {len(violations)} `bg-white` còn sót. Đổi thành `bg-surface` "
                f"(border-white/ring-white được phép giữ). Xem output trên."
            )

    def test_no_dead_css_vars(self):
        """Mọi `var(--color-*)` trong .tsx phải được định nghĩa trong @theme."""
        violations = scan_dead_css_vars()
        if violations:
            for v in violations[:20]:
                print(f"  {v['file']}:{v['line']} - {v['var']} - {v['context']}")
            pytest.fail(
                f"Found {len(violations)} `var(--color-*)` trỏ token không tồn tại "
                f"trong globals.css. Thêm token vào @theme hoặc bỏ tham chiếu."
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
