# Git Workflow cho Collaborators

Tài liệu này thống nhất cách làm việc với Git trong dự án. Mỗi tính năng hoặc
bản sửa lỗi phải được phát triển trên một nhánh riêng và gửi Pull Request vào
nhánh `develop`.

## Cấu trúc nhánh

- `main`: phiên bản ổn định, dùng để release hoặc deploy.
- `develop`: nhánh tích hợp các thay đổi đang phát triển.
- `feature/<ten-tinh-nang>`: phát triển tính năng mới.
- `fix/<ten-loi>`: sửa lỗi.
- `docs/<noi-dung>`: cập nhật tài liệu.
- `chore/<cong-viec>`: cấu hình, dependency hoặc công việc bảo trì.

Tên nhánh dùng chữ thường, không dấu và phân tách bằng dấu gạch ngang:

```text
feature/agent-search-tool
fix/chat-validation
docs/git-workflow
```

## 1. Chuẩn bị repository lần đầu

Clone repository và chuyển vào thư mục dự án:

```bash
git clone git@github.com:AI20K-Build-Phase-Cohort-3/P-075.git
cd P-075
```

Lấy thông tin mới nhất từ remote:

```bash
git fetch origin
```

Nếu chưa có nhánh `develop` ở máy local:

```bash
git switch --track -c develop origin/develop
```

Nếu local đã có `develop`:

```bash
git switch develop
git pull --ff-only origin develop
```

## 2. Bắt đầu một tính năng mới

Luôn tạo nhánh tính năng từ phiên bản mới nhất của `develop`:

```bash
git switch develop
git pull --ff-only origin develop
git switch -c feature/agent-search-tool
```

Kiểm tra nhánh hiện tại:

```bash
git branch --show-current
git status
```

Không phát triển trực tiếp trên `main` hoặc `develop`.

## 3. Làm việc và commit

Trong dự án này, thư mục agent là `src/agents/` (`agents` ở dạng số nhiều).
Ví dụ file của search tool:

```text
src/agents/tools/search.py
```

Sau khi viết code, kiểm tra và chạy test:

```bash
git status
.venv/bin/ruff check .
.venv/bin/pytest
```

Chỉ stage những file liên quan đến thay đổi:

```bash
git add src/agents/tools/search.py
git commit -m "feat(agent): thêm tool tìm kiếm web"
```

Không nên dùng `git add .` nếu working tree có những thay đổi không liên quan.

### Quy ước commit message

Dự án sử dụng cấu trúc:

```text
<type>(<scope>): <mô tả ngắn>
```

Các `type` thường dùng:

- `feat`: thêm tính năng.
- `fix`: sửa lỗi.
- `docs`: cập nhật tài liệu.
- `test`: thêm hoặc sửa test.
- `refactor`: tái cấu trúc nhưng không thay đổi hành vi.
- `chore`: cấu hình, dependency hoặc bảo trì.

Ví dụ:

```text
feat(agent): thêm tool tìm kiếm web
fix(api): xử lý message rỗng
docs: bổ sung hướng dẫn Git workflow
test(config): kiểm tra validation của settings
```

## 4. Push và tạo Pull Request

Lần đầu push nhánh:

```bash
git push -u origin feature/agent-search-tool
```

Những lần sau chỉ cần:

```bash
git push
```

Trên GitHub, tạo Pull Request:

```text
base:    develop
compare: feature/agent-search-tool
```

Pull Request cần có:

- Mô tả mục tiêu của thay đổi.
- Danh sách phần đã triển khai.
- Cách kiểm thử.
- Screenshot hoặc log nếu có thay đổi giao diện hay hành vi.
- Link đến issue liên quan, nếu có.

Không tự merge khi CI đang lỗi hoặc chưa hoàn tất review bắt buộc.

## 5. Cập nhật nhánh khi `develop` thay đổi

Commit hoặc stash công việc đang làm trước:

```bash
git status
git stash push -u -m "WIP agent search tool"
```

Cập nhật `develop`, sau đó merge vào nhánh tính năng:

```bash
git switch develop
git pull --ff-only origin develop
git switch feature/agent-search-tool
git merge develop
```

Khôi phục công việc đã stash, nếu có:

```bash
git stash list
git stash pop
```

Nếu xảy ra conflict:

1. Mở từng file conflict và chọn nội dung đúng.
2. Xóa các marker `<<<<<<<`, `=======`, `>>>>>>>`.
3. Chạy lại test.
4. Stage và hoàn tất merge:

```bash
git add <file-da-xu-ly>
git commit
```

## 6. Sau khi Pull Request được merge

Quay về `develop`, cập nhật code và xóa nhánh local đã hoàn thành:

```bash
git switch develop
git pull --ff-only origin develop
git branch -d feature/agent-search-tool
```

Nếu GitHub chưa tự xóa nhánh remote:

```bash
git push origin --delete feature/agent-search-tool
```

Chỉ xóa nhánh sau khi Pull Request đã được merge và code đã có trên
`develop`.

## 7. Xử lý thay đổi chưa commit

Nếu cần chuyển nhánh nhưng chưa muốn commit:

```bash
git stash push -u -m "WIP mô tả công việc"
```

Xem danh sách stash:

```bash
git stash list
```

Khôi phục stash:

```bash
git stash pop
```

Nên tạo các nhánh riêng cho những thay đổi không liên quan. Ví dụ, thay đổi
config không nên được commit chung trong nhánh `feature/agent-search-tool`.

## 8. Các lỗi thường gặp

### `pathspec 'develop' did not match`

Local chưa biết nhánh `develop`:

```bash
git fetch origin
git switch --track -c develop origin/develop
```

### `src refspec ... does not match any`

Nhánh chưa được tạo, chưa có commit, hoặc tên nhánh bị sai:

```bash
git branch --show-current
git status
git log -1 --oneline
```

Sau đó push lại:

```bash
git push -u origin <ten-nhanh>
```

### `pathspec ... did not match any files`

Kiểm tra đường dẫn và đảm bảo file đã được tạo:

```bash
git status
find src -type f
```

Đường dẫn đúng của agent tools trong dự án là:

```text
src/agents/tools/
```

### Không thể chuyển nhánh vì có thay đổi local

Commit thay đổi vào đúng nhánh hoặc tạm lưu:

```bash
git stash push -u -m "WIP"
git switch <ten-nhanh>
```

## Checklist trước khi tạo Pull Request

- [ ] Nhánh được tạo từ `develop` mới nhất.
- [ ] Chỉ chứa thay đổi liên quan đến một mục tiêu.
- [ ] Không commit `.env`, API key hoặc dữ liệu bí mật.
- [ ] Code đã được format và lint.
- [ ] Test liên quan đã chạy thành công.
- [ ] Commit message tuân theo quy ước.
- [ ] Pull Request trỏ vào `develop`.
- [ ] Nội dung Pull Request mô tả rõ cách kiểm thử.
