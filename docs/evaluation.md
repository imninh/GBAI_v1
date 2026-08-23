# Bằng chứng đánh giá — GreenBin AI (VHR-17)

> **Deliverable #10.** Gom mọi con số đã đo được của hệ thống về một chỗ, kèm
> điều kiện đo và giới hạn của từng con số.
>
> **Nguyên tắc của trang này: không có con số nào được viết ra mà không nói rõ
> nó đo trên cái gì.** Một con số accuracy không kèm tên bộ dữ liệu là con số vô
> nghĩa — chính nhóm đã trả giá cho bài học đó (xem mục 5).
>
> Cập nhật 10/08/2026. File kết quả thô: [`eval/results/`](../eval/results/).

---

## 1. Chất lượng phân loại rác

Chạy bằng `python eval/run_eval.py`, đi **đúng đường sản phẩm** (cùng bộ định
tuyến bốn tầng, cùng prompt, cùng ngưỡng) chứ không gọi thẳng model — số đo ra
là số của hệ thống, không phải của riêng model.

**Lần chạy dùng được:** [`eval/results/phan_loai-20260808-062531.json`](../eval/results/phan_loai-20260808-062531.json)

| | |
|---|---|
| Bộ ảnh | **30 ảnh RealWaste** (ảnh rác thật chụp tại bãi), 6 nhóm |
| Số ảnh lỗi | **0** |
| Tỉ lệ trả lời | **100%** (0 ảnh bị từ chối) |
| **Accuracy** | **93,3%** (28/30) |
| **Macro F1** | **94,8%** |
| Độ trễ | p50 **2.627 ms** · p95 **8.113 ms** · min 2.023 ms · max 9.317 ms |
| Phân tầng thực tế | T1 `gemini-flash-lite-latest` **25 ảnh** · T2 `gemini-3.6-flash` **5 ảnh** |
| Chi phí | **"chưa có giá"** — nhà cung cấp không công bố giá theo token cho model đang chạy |

### 1.1 Theo từng nhóm rác

| Nhóm | Đúng / Tổng |
|---|---|
| `organic` | 5/5 |
| `other` | 5/5 |
| `recyclable_paper` | 5/5 |
| `recyclable_glass` | 5/5 |
| `recyclable_metal` | 4/5 |
| `recyclable_plastic` | 4/5 |

### 1.2 Hai ảnh sai — sai theo hướng nào cũng quan trọng

| Ảnh | Nhãn đúng | Model đoán | Tầng |
|---|---|---|---|
| `Metal__Metal_241.jpg` | `recyclable_metal` | `hazardous` | T2 |
| `Plastic__Plastic_182.jpg` | `recyclable_plastic` | `other` | T1 |

Ca thứ nhất là **sai về phía an toàn**: hệ thống gọi một vật kim loại là rác
nguy hại, tức là đẩy nó sang nhánh cảnh báo và chuyển người thay vì cho qua. Với
bài toán này, sai kiểu đó rẻ hơn nhiều so với sai ngược lại.

Ca thứ hai là sai về phía **mất giá trị tái chế**: nhựa bị gọi là rác khác. Không
nguy hiểm nhưng làm hụt số liệu thu hồi.

**Không có ca nào "nguy hại thành rác thường"** — chỉ số
`ty_le_nguy_hai_thanh_thuong` = **0,0%**.

### 1.3 ⚠️ `recall nguy hại = 0,0%` không phải hệ thống bỏ sót

**RealWaste không có lớp rác nguy hại nào.** Không có gì để bắt thì recall bằng 0
là hệ quả số học, không phải kết luận về năng lực. Đây là câu bắt buộc phải nói
kèm mỗi lần trích con số này.

Hệ quả thật, và là giới hạn lớn nhất của bằng chứng hiện có: **nhánh an toàn AI —
phần mạnh nhất của đồ án — chưa được đo bằng dữ liệu.** Nó mới chỉ được chốt chặn
bằng test (mục 3).

### 1.4 Lần chạy KHÔNG dùng được — vì sao vẫn giữ lại

[`phan_loai-20260808-062850.json`](../eval/results/phan_loai-20260808-062850.json)
ghi accuracy 85,7%. **Con số đó là rác, không được trích.** 16/30 ảnh lỗi
`VISION-429`: tầng T1 chết vì trần token mỗi phút, rơi xuống T2, rồi T2 cạn quota
ngày. 85,7% là điểm của một tầng dự phòng đang hấp hối, không phải điểm của cấu
hình định đo.

Giữ file lại có chủ đích: nó là bằng chứng cho việc **`run_eval.py` tự phát hiện
và tự cảnh báo** khi số đo không hợp lệ, thay vì in ra một con số đẹp.

---

## 2. Chất lượng truy hồi quy định (RAG)

Chạy bằng `python eval/run_retrieval_eval.py`. Báo cáo đầy đủ:
[`eval/results/report.md`](../eval/results/report.md).

Bộ đo: **18 câu hỏi**, mỗi câu có 1–2 đoạn quy định được tính là đúng; kho 13
đoạn, 13/13 đoạn có vector.

| Chỉ số | Thuần BM25 | **Hybrid BM25 + embedding** |
|---|---|---|
| hit@1 | 0,667 | **0,722** |
| hit@3 | 0,889 | **0,944** |
| hit@5 | 0,944 | **1,000** |
| MRR | 0,792 | **0,838** |

**Con số quan trọng nhất là hit@5 = 1,000**: node `advise` đưa 5 đoạn đầu vào
prompt, nên chỉ số này nói rằng model **luôn** nhận được đoạn quy định đúng. Phần
còn lại là việc của prompt, không còn là việc của truy hồi.

Dùng hit@k và MRR **thay cho precision@5** có lý do: mỗi câu chỉ có 1–2 đoạn
đúng, nên precision@5 trần cứng ở 0,2–0,4 — đọc lên gây hiểu nhầm là hệ thống dở.

⚠️ **Giới hạn tự nhận:** 18 câu này do chính nhóm viết, theo lối nói của cư dân,
nên **thiên vị sẵn cho embedding** và bất lợi cho BM25. Bảng dò trọng số vector
gợi ý nên tăng trọng số lên, nhưng nhóm **cố ý không đổi** — chốt theo bảng đó là
overfit vào bộ test của chính mình.

---

## 3. Bộ test tự động

```bash
python -m pytest -q
python -m ruff check src/ tests/ eval/ scripts/
```

**447 test, 0 test gọi API thật** — model được thay bằng `FakeVisionClient` ở
`tests/conftest.py` nên chi phí chạy test bằng 0 và kết quả xác định.

Test không chỉ để "có test". Những nhóm dưới đây tồn tại vì chúng **chốt chặn một
lời hứa cụ thể của sản phẩm**:

| Nhóm test | Chốt chặn điều gì |
|---|---|
| `test_image.py` | Ảnh sau tiền xử lý **không còn EXIF** (gồm toạ độ GPS), có làm mờ khuôn mặt, có hạn lưu trữ |
| `test_di_tru_trang_thai.py` | Quét `src/` + `scripts/` chặn việc gán lại từ vựng trạng thái cũ cho `PickupRequest` |
| `test_pickup_lifecycle.py` | Không có đường đi tắt tới `hoan_tat` bỏ qua bước người xác nhận khối lượng thật |
| `test_toi_uu_tuyen.py` | Thuật toán xếp tuyến không làm **mất điểm dừng**, không dài hơn thứ tự đầu vào, và cho **kết quả xác định** |
| `test_loc_thung_theo_nhan_vien.py` | Nhân viên không đọc được thùng của người khác; câu lỗi **không phân biệt được** với thùng không tồn tại |
| `test_gan_thung.py` | Chỉ ban quản lý giao được thùng; mỗi lần giao đều ghi `AuditLog` |
| `test_dang_ky.py` | Client **không tự quyết được** `role` và `green_points` khi đăng ký |
| `test_lich_su.py` | Lịch sử chỉ đếm dữ liệu **của chính người đang đăng nhập** |

`ruff` sạch trên `src/ tests/ eval/ scripts/`, trừ **2 lỗi N806 nợ sẵn** ở
`scripts/log_hook.py` — đã ghi trong mục nợ kỹ thuật của
[`ARCHITECTURE.md`](../ARCHITECTURE.md) mục 21.

---

## 4. Số đo hạ tầng — tầng T0.5 chạy tại chỗ

Đo khi nén CLIP về ONNX int8 để vừa máy chủ 512 MB (chi tiết:
[ADR-0007](decisions/0007-tang-t05-chay-onnx-int8.md)).

| | Bản `torch` đầy đủ | **Bản `onnx` int8** |
|---|---|---|
| Trọng số | ~605 MB | **88,7 MB** |
| RAM tiến trình | không lọt máy chủ 512 MB | **185 MB** |
| Độ trễ mỗi ảnh | 458 ms | **56 ms** (114 ms tính cả giải mã ảnh) |

⚠️ Bản nén **đổi thang điểm**: cosine giữa hai bản lệch 0,970–0,980, nên ngưỡng
`CLIP_ACCEPT_CONFIDENCE` **chưa được chuẩn lại** cho bản nén. Tầng T0.5 vì thế
đang tắt trên bản deploy.

---

## 5. Giới hạn của toàn bộ bằng chứng trên

Mục này quan trọng ngang phần số liệu.

**1. Chưa có bộ ảnh tự chụp tại Việt Nam.** Đây là món nợ lớn nhất, treo từ
03/08. Lý do nó quan trọng chính là một phát hiện của nhóm:

> Một model đạt **94,18% trên TrashNet** chỉ còn **41,04% trên RealWaste**
> (ảnh rác thật tại bãi) — xem
> [khảo sát SOTA](research/sota-model-nhe-phan-loai-rac.md).

Nghĩa là **con số 93,3% ở mục 1 không phải năng lực sản phẩm trên rác Việt Nam**.
Nó là năng lực trên 30 ảnh RealWaste. Bộ ảnh tự chụp không phải bộ bổ sung — nó
là bộ quan trọng nhất, và chưa có.

**2. Bộ đo phân loại mới có 30 ảnh.** Đủ để nói "hệ thống chạy được đầu-cuối và
không lỗi", chưa đủ để nói một con số accuracy có khoảng tin cậy hẹp. Bộ ảnh đã
dựng sẵn 180 ảnh (`data/eval/cong_khai/`), chưa chạy hết vì quota model miễn phí.

**3. Nhánh an toàn AI chưa có dữ liệu để đo** — xem mục 1.3.

**4. Chưa đo với người dùng thật.** Chưa phỏng vấn được lao công và người ban
quản lý, là chỗ yếu nhất của giả định sản phẩm.

**5. Chi phí mỗi request chưa đo được** vì nhà cung cấp không công bố giá token
cho model đang dùng. Hệ thống hiển thị thẳng **"chưa có giá"** thay vì in $0 —
"chưa biết giá" không phải là "miễn phí".

---

## 6. Cách chạy lại toàn bộ

```bash
python eval/chuan_bi_realwaste.py --so-anh 20 --xoa-truoc   # dựng bộ ảnh từ RealWaste
python eval/run_eval.py --limit 30 --dong-y                 # chạy đánh giá phân loại
python eval/run_retrieval_eval.py                           # chạy đánh giá truy hồi
python eval/so_sanh_lan_chay.py <file_cu> <file_moi>         # so hai lần chạy
python -m pytest -q                                         # 447 test
```

`run_eval.py` **bắt buộc phải có cờ `--dong-y`** mới gọi model thật, và in dự
toán chi phí trước khi chạy — để không ai vô tình đốt hết quota của cả nhóm.
`so_sanh_lan_chay.py` in ra danh sách **những ảnh đổi kết quả** giữa hai lần
chạy, không chỉ so hai con số tổng.
