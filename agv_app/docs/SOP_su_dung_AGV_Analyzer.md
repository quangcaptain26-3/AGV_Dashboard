# SOP — Phân tích chất lượng hoạt động AGV (AGV Analyzer)

| Mục | Nội dung |
|-----|----------|
| **Mã tài liệu** | SOP-AGV-ANALYZER-01 |
| **Tên tài liệu** | Quy trình chuẩn sử dụng ứng dụng Phân tích chất lượng AGV |
| **Phiên bản** | 2.0 |
| **Ngày hiệu lực** | 2026-07-26 |
| **Đối tượng** | QA · IT / kỹ thuật AGV · Giám sát vận hành · Quản lý |
| **Phạm vi** | Ứng dụng desktop `AGV_Analyzer` (Windows) — 3 nguồn: Log AGV + Tasks CSV + API logs |
| **Tài liệu liên quan** | `agv_app/BUILD.md`, `agv_app/point_settings.json` |

---

## 0. Mục đích & nguyên tắc

### 0.1. Mục đích

Chuẩn hóa cách **chuẩn bị dữ liệu → cấu hình → phân tích → đọc kết quả → xuất báo cáo → xử lý sự cố** để mọi người dùng cùng một quy trình, cùng cách hiểu chỉ số.

### 0.2. Kết quả mong đợi sau mỗi lần chạy

| Nguồn | Chỉ số chính |
|-------|--------------|
| Log AGV (`LogYYYYMMDD` / `Log*.txt`) | Dừng bất thường tại điểm, tỷ lệ bất thường theo ca/ngày/tuần/tháng |
| Tasks CSV (`YYYYMMDD.csv`) | 稼動率, số nhiệm vụ, timeout, chu kỳ, model P1/P2/P3 |
| Tasks API logs (`YYYYMMDD.log`, `debug_*.log`) | Lệnh `taskCreate`, poll, lỗi API, điểm hot, đối chiếu CSV↔API |

### 0.3. Nguyên tắc bắt buộc

1. **Chỉ đọc** — app không sửa, không xóa log gốc; không upload SFIS/MES.
2. **Ngày suy từ tên file/folder** — không dùng ngày máy tính.
3. **Ngày thiếu không ước lượng** — báo cáo chỉ phản ánh ngày đã nạp.
4. **Đổi cấu hình → phải PHÂN TÍCH lại** mới đổi số liệu.
5. Báo cáo partial (sau Hủy) phải ghi chú rõ trên file gửi đi.

---

## 1. Phạm vi hệ thống

### 1.1. Là gì / không phải gì

| Là | Không phải |
|----|------------|
| App desktop Windows, chạy cục bộ | Web / server / database |
| Phân tích log đã có sẵn | Gọi API MES realtime |
| Dashboard + Excel cho họp / lưu trữ | Hệ thống phân quyền đăng nhập |

### 1.2. Cách mở app

1. Copy/giải nén nguyên thư mục `AGV_Analyzer` (dạng **onedir**).
2. Chạy `AGV_Analyzer.exe`.
3. Không tách riêng `.exe` khỏi các DLL cùng folder.

> Windows 10/11 64-bit. Đường dẫn có dấu tiếng Việt **chạy được**. Máy end-user **không cần** cài Python.

### 1.3. Vai trò sử dụng (nghiệp vụ)

| Vai trò | Việc chính trong app |
|---------|----------------------|
| **QA** | Phân tích ngày/tuần/tháng, xuất Excel, theo dõi tỷ lệ bất thường & 稼動 |
| **IT / kỹ thuật AGV** | Tab Theo điểm / Theo xe / Theo model / Điều phối API — truy vết gốc |
| **Giám sát vận hành** | Checklist hàng ngày, banner thiếu nguồn, so sánh ca ngày–đêm |
| **Quản lý** | Tab **Tổng quan** + sheet Excel **Cho sếp xem** |

---

## 2. Chuẩn bị dữ liệu đầu vào

### 2.1. Nguồn A — Log AGV (bắt buộc nếu cần tỷ lệ bất thường)

```
D:\AGV_Logs\
  Log20260701\
    Log2026070100.txt
    Log2026070101.txt
    ...
  Log20260702\
    ...
```

| Loại | Quy ước | Ví dụ |
|------|---------|--------|
| Thư mục ngày | Chứa `YYYYMMDD` | `Log20260715`, `20260715` |
| File log | `Log` + ngày + 2 số giờ | `Log2026071508.txt` |
| Encoding | **UTF-8** | — |

App nhận diện sự kiện: đến điểm (`目标点`), gán/kết thúc task, bắt đầu/kết thúc sạc.

### 2.2. Nguồn B — Tasks CSV (khuyến nghị — để có 稼動)

| Mục | Quy định |
|-----|----------|
| Tên file | `YYYYMMDD.csv` (vd `20260715.csv`) |
| Vị trí | Thư mục `Tasks Log 任务` hoặc bất kỳ; app quét đệ quy |
| Encoding | Tự thử: utf-8-sig → utf-8 → gbk → cp1252 |
| Cột chính | taskId, carId, send_time, complete_time, duration, final_state, model |

Nếu **không** nạp CSV: vẫn phân tích được bất thường; KPI 稼動 / model / Kẹt/100 task sẽ trống hoặc 0.

### 2.3. Nguồn C — Tasks API logs (khuyến nghị — điều phối MES)

| Mục | Quy định |
|-----|----------|
| Tên file | `YYYYMMDD.log` hoặc `debug_YYYYMMDD.log` |
| Nội dung | Có `taskCreate`, `[poll …]`, hoặc `/agvapi/` |
| Encoding | UTF-8 |

### 2.4. Checklist chuẩn bị trước khi phân tích

- [ ] Đủ folder `LogYYYYMMDD` theo ngày cần báo cáo
- [ ] File `YYYYMMDD.csv` đúng tên, đúng thư mục Tasks Log
- [ ] (Nếu cần) API logs cùng ngày đã copy
- [ ] Quyền đọc thư mục; không mở Excel đích đang ghi đè

---

## 3. Tổng quan giao diện

```
┌─────────────────────┬──────────────────────────────────────────┐
│ Tab Dữ liệu         │  Kết quả: Tổng quan / Ngày / Điểm /     │
│ Tab Cài đặt         │  Xe / Model / Tuần / Tháng / API         │
│                     │                                          │
│ [PHÂN TÍCH] [Hủy]   │                                          │
│ [Xuất Excel][CSV]   │                                          │
├─────────────────────┴──────────────────────────────────────────┤
│ Thanh tiến độ + trạng thái job                                 │
│ Nhật ký hoạt động                                              │
└────────────────────────────────────────────────────────────────┘
```

- **Trái — Dữ liệu:** danh sách nguồn đã nhận (Log AGV / CSV / API).
- **Trái — Cài đặt:** ngưỡng, ca, điểm loại trừ, đường dẫn.
- **Phải:** tab kết quả (lazy-load — chỉ nạp khi mở).
- **Banner vàng:** cảnh báo (hủy partial, thiếu nguồn, lỗi đọc).

Badge dữ liệu: `Đã nhận X CSV / Y API log / Z ngày AGV`.

---

## 4. SOP thiết lập lần đầu

> Làm **1 lần** / khi đổi dây chuyền hoặc đổi ca.

### Bước 4.1 — Mở tab **Cài đặt**, kiểm tra

| Mục | Ý nghĩa | Mặc định |
|-----|---------|----------|
| Ngưỡng bất thường | Dừng tại điểm (có task, không sạc) quá X phút → bất thường | **12 phút** |
| Áp dụng ngưỡng thang máy | Bật thì dùng ngưỡng riêng | Bật nếu có điểm |
| Ngưỡng thang máy | Điểm thang máy | **3 phút** |
| Điểm thang máy | Danh sách điểm | 221, 1294, 223, 1767 |
| Điểm loại trừ | Không tính BT dù dừng bao lâu | Home: 232, 1025, 259 · Charging: 239 |
| Ca ngày / ca đêm | Phân ca thống kê | 08:00–19:59 / 20:00–07:59 (+1 ngày) |
| Số giờ mẫu số | Mẫu số tỷ lệ bất thường | **24 giờ** |
| Ngưỡng màu Tốt / Cảnh báo | Tô màu bảng & biểu đồ | &lt;5% xanh; 5–&lt;10% vàng; ≥10% đỏ |
| Thư mục Tasks Log | Root chứa `YYYYMMDD.csv` (+ logs API nếu có) | **bắt buộc nếu cần 稼動** |
| Thư mục log / xuất mặc định | Gợi ý dialog | tùy máy |

### Bước 4.2 — Lưu

Bấm **Lưu cài đặt vào point_settings.json**. File xuất hiện cạnh `AGV_Analyzer.exe`.

### Bước 4.3 — Kiểm tra giữ cấu hình

Đổi thử một ngưỡng → Lưu → tắt app → mở lại → xác nhận giá trị còn giữ.

---

## 5. SOP nạp dữ liệu & chạy phân tích

### 5.1. Nạp dữ liệu (chọn một hoặc kết hợp)

| Cách | Thao tác | Khi nào dùng |
|------|----------|--------------|
| **A. Thêm…** | Tab Dữ liệu → **Thêm…** → chọn folder/file | Ít ngày, kiểm soát từng mục |
| **B. Thêm thư mục cha** | Quét đệ quy Log + CSV + API | Cây thư mục đã gom sẵn |
| **C. Theo khoảng ngày** | Chọn thư mục gốc → Từ/Đến → **Quét & thêm theo khoảng** | Báo cáo tuần/tháng (khuyên dùng) |
| **D. Kéo-thả** | Kéo folder/file vào cửa sổ app | Nhanh nhất: kéo cả `Tasks Log 任务` |
| **E. Cài đặt Tasks Log** | Tab Cài đặt → Chọn thư mục Tasks Log | Gắn cố định CSV/API |

**Quản lý danh sách**

| Nút | Công dụng |
|-----|-----------|
| Xóa mục chọn | Bỏ 1–vài ngày khỏi lần chạy |
| Xóa tất cả | Reset trước khi nạp khoảng mới |
| Quét lại | Làm mới bảng từ inventory |

### 5.2. Ngày thiếu trong khoảng

App có thể hỏi **Bổ sung ngày thiếu?**

- Tìm được folder trên đĩa → chọn **Yes** để bổ sung.
- Không tìm thấy → ghi nhật ký; **không chặn** phân tích.

> Báo cáo tháng chỉ phản ánh ngày **đã có trong danh sách**.

### 5.3. Chạy phân tích

1. (Khuyến nghị) Tab **Cài đặt** → xác nhận Tasks Log + ngưỡng.
2. Tab **Dữ liệu** → kiểm tra badge / số dòng ≈ số ngày cần.
3. Bấm **PHÂN TÍCH**.
4. Nếu chỉ có CSV/API (không Log AGV): xác nhận *«Vẫn phân tích KPI nhiệm vụ / điều phối?»*.
5. Theo dõi thanh tiến độ, dòng job `i/N`, nhật ký.

**Hành vi kỹ thuật**

- Song song tối đa **4 worker**.
- Tasks CSV / API được **index một lần** rồi tái dùng.
- UI không treo trong lúc chạy.

### 5.4. Hủy giữa chừng

1. Bấm **Hủy**.
2. App dừng ngày chưa xong; **giữ kết quả ngày đã xong**.
3. Banner vàng báo **partial**.
4. Vẫn xem tab kết quả và **Xuất Excel/CSV** phần đã có.

Dùng khi: chọn nhầm khoảng, cần tắt máy gấp, hoặc test nhanh.

### 5.5. Đọc banner sau khi chạy

| Banner | Việc cần làm |
|--------|--------------|
| Không banner | Bình thường → xem **Tổng quan** |
| Hủy — partial | Báo cáo chưa đủ ngày; chạy lại nếu cần full |
| Thiếu Tasks CSV / API / AGV | Bổ sung nguồn hoặc chấp nhận KPI trống |
| Có lỗi đọc | Xem nhật ký; bỏ folder hỏng / sửa quyền |

---

## 6. SOP đọc kết quả (theo tab & vai trò)

### 6.1. Tab Tổng quan — họp nhanh / sếp

1. **KPI bất thường:** số ngày, số xe, tổng lượt, tổng giờ, **tỷ lệ bất thường chung**.
2. **KPI 稼動:** tỷ lệ hoạt động, số task, timeout, TB chu kỳ.
3. **KPI API:** taskCreate, poll/task unique, lỗi API, điểm hot.
4. **Điểm nhấn:** ngày tệ/tốt nhất, xe cần chú ý, điểm hay kẹt.
5. Biểu đồ xu hướng; top điểm/xe; so sánh ca; mẫu theo thứ; phân nhóm mức độ nặng.

**Cách đọc màu tỷ lệ bất thường**

| Màu | Ý nghĩa (mặc định) |
|-----|-------------------|
| Xanh | &lt; 5% — tốt / **ỔN** |
| Vàng | 5% – &lt;10% — **CẦN CHÚ Ý** |
| Đỏ | ≥ 10% — **CẦN XỬ LÝ** |

### 6.2. Tab Theo ngày

- **Trên:** bảng so sánh các ngày + chart 10 ngày tỷ lệ cao nhất.
- **Dưới:** báo cáo 1 ngày (verdict ỔN / CẦN CHÚ Ý / CẦN XỬ LÝ), 8 thẻ KPI, biểu đồ, 3 sub-tab chi tiết (bất thường / Tasks / API).
- Mặc định mở **ngày mới nhất có Log AGV**.
- Ngày chưa có Log AGV hiện `-` (nền vàng) — **không đọc nhầm là 0 lỗi**.
- UI tối đa **500 dòng** chi tiết; nhiều hơn → xem Excel.

### 6.3. Tab Theo điểm — chỗ nào hay tắc?

- **P1 — xử lý ngay:** còn xảy ra trong 7 ngày gần nhất **và** (lượt/ngày ≥ 1 **hoặc** TB dừng ≥ 2× ngưỡng).
- **P2 — theo dõi:** còn gần đây **hoặc** lượt/ngày ≥ 0,5.
- **P3 — đã lắng:** còn lại.
- Điểm thang máy đánh dấu riêng (ngưỡng 3 phút).
- Chọn 1 điểm → chẩn đoán: ≥ 60% lượt dồn 1 xe → nghiêng **lỗi xe**; rải nhiều xe → nghiêng **lỗi điểm**.

### 6.4. Tab Theo xe — xe nào thật sự có vấn đề?

- **Kẹt/100 task** = (lượt kẹt ÷ task completed) × 100 — cần Tasks CSV.
- Xe đáng lo nhất = Kẹt/100 task cao nhất trong xe có **≥ 20 task**.
- Có CSV: P1 nếu còn gần đây **và** (Kẹt/100 ≥ 2× TB đội **hoặc** TB dừng ≥ 2× ngưỡng).
- Không CSV: fallback theo lượt/ngày + TB phút.
- Chọn 1 xe → ≥ 60% lượt dồn 1 điểm → nghiêng **lỗi điểm**; rải nhiều điểm → nghiêng **lỗi xe**.

### 6.5. Tab Theo model — model timeout / chu kỳ lệch

- Chỉ có ý nghĩa khi đã nạp Tasks CSV.
- Mẫu tin cậy khi model ≥ **20 task**.
- **P1:** đủ mẫu + còn gần đây + (`%timeout ≥ max(5, 2×TB đội)` **hoặc** chu kỳ ≥ 2× TB đội).
- **P2:** còn gần đây / timeout ≥ max(1, TB đội) / chu kỳ ≥ 1,5× TB.
- Chọn 1 model → timeout dồn 1 xe ≥ 60% → nghiêng lỗi xe.

### 6.6. Tab Theo tuần / Theo tháng

- Tuần = ISO (Thứ Hai–Chủ Nhật); Tháng = dương lịch.
- Phần trên: so sánh các kỳ + chart.
- Phần dưới: click 1 kỳ → verdict + KPI + xu hướng ngày + bảng ngày trong kỳ.
- Mặc định mở kỳ **mới nhất**.
- Ngày chỉ có API (không Log/CSV) xem ở tab **Điều phối (API)**.

### 6.7. Tab Điều phối (API)

| Khối | Nội dung |
|------|----------|
| Theo ngày | taskCreate · Poll · Task unique · Gán xe · Lỗi API · Điểm hot |
| Top điểm payload | Điểm xuất hiện nhiều trong route create/poll |
| Đối chiếu CSV↔API | CSV task − API create; \|chênh\| > 5 tô vàng |

> CSV task count **không bắt buộc bằng** API create (khác cửa sổ thời gian / semantics). Dùng để phát hiện lệch bất thường, không force bằng số.

---

## 7. Định nghĩa chỉ số (chuẩn kỹ thuật)

| Chỉ số | Định nghĩa |
|--------|------------|
| **Bất thường (kẹt)** | Xe **có task**, **không sạc**, dừng tại điểm (không thuộc loại trừ) **quá ngưỡng** (12′ thường / 3′ thang máy) |
| **Tỷ lệ bất thường** | `(tổng giờ dừng BT) / (denom_hours × số xe) × 100%` — mặc định denom = 24 |
| **稼動率** | `(tổng duration_sec của task completed) / (thời gian ca × số xe có task) × 100%` |
| **Timeout** | `final_state = timeout` trong CSV |
| **Ca đêm** | Từ `night_start` đến `night_end` **sang sáng hôm sau**; CSV load cả ngày kế để bắt spill |
| **Mức độ nặng** | Ngắn &lt;20′ · Vừa 20–40′ · Dài 40–60′ · Rất dài &gt;60′ |

---

## 8. SOP xuất báo cáo

### 8.1. Xuất Excel (khuyến nghị họp / lưu trữ)

1. Phân tích xong (hoặc partial chấp nhận được).
2. **Xuất Excel** → chọn nơi lưu (mặc định `BaoCao_AGV.xlsx`).
3. Mở bằng Microsoft Excel / tương thích.

**Các sheet chính**

| Sheet | Dành cho |
|-------|----------|
| **Cho sếp xem** | Kết luận ỔN / CẦN CHÚ Ý / CẦN XỬ LÝ · KPI lớn · top điểm/xe · ngày tệ |
| Theo ngày / tuần / tháng | So sánh kỳ + công thức sống |
| Tỷ lệ hoạt động · Theo model · 稼動 theo xe | KPI Tasks |
| Chi tiết Tasks Log | Từng nhiệm vụ |
| Điều phối API · Chi tiết API taskCreate · Đối chiếu CSV↔API | MES / điều phối |
| Theo điểm · Theo xe · Chi tiết bất thường | Truy vết kỹ thuật |

### 8.2. Xuất CSV

Dùng khi cần pivot / tool khác. Có cột đầu vào + chú thích công thức.

### 8.3. Quy ước đặt tên lưu trữ

```
AGV_Report_YYYYMM_DDMMYYYY.xlsx
```

Ví dụ: `AGV_Report_202607_26072026.xlsx` — báo cáo tháng 7, xuất ngày 26/07/2026.

Không ghi đè bản đã gửi sếp; lưu thư mục chung team.

---

## 9. Quy trình theo chu kỳ

### 9.1. Hàng ngày (5–10 phút) — Giám sát / QA

1. Copy folder `LogYYYYMMDD` + `YYYYMMDD.csv` (+ API log nếu có).
2. Mở app → kéo-thả hoặc thêm folder ngày → **PHÂN TÍCH**.
3. Xem **Tổng quan** + ngày tệ / điểm–xe nổi bật.
4. Tỷ lệ đỏ hoặc P1 mới → ghi ticket / báo kỹ thuật.
5. (Tuỳ chọn) Xuất Excel lưu nhật ký ngày.

### 9.2. Hàng tuần — QA / Giám sát

1. Khoảng Thứ Hai → Chủ Nhật.
2. **Quét & thêm theo khoảng** → **PHÂN TÍCH**.
3. Tab **Theo tuần** + **Tổng quan** + P1 điểm/xe.
4. Xuất Excel gửi họp tuần.

### 9.3. Hàng tháng — QA (mục tiêu chính)

1. Chuẩn bị đủ folder log + CSV (+ API) cả tháng.
2. Cài đặt → Tasks Log → **Lưu**.
3. Tab Dữ liệu → khoảng ngày cả tháng → **Quét & thêm theo khoảng**.
4. Xử lý hộp thoại ngày thiếu nếu cần.
5. **PHÂN TÍCH** đến xong (không Hủy trừ khi cố ý).
6. Kiểm tra banner sạch.
7. Tab **Theo tháng** + **Tổng quan** → **Xuất Excel**.

**Checklist tháng**

- [ ] Đủ folder log theo ngày làm việc
- [ ] Tasks Log đúng path, CSV đúng tên `YYYYMMDD.csv`
- [ ] (Nếu dùng) API logs đủ ngày
- [ ] Cài đặt ngưỡng/ca đã lưu
- [ ] Phân tích hoàn tất (không partial trừ khi cố ý)
- [ ] Banner không báo thiếu CSV/API hàng loạt
- [ ] Đã xuất Excel đúng quy ước tên
- [ ] Đã xem ngày tệ nhất / điểm–xe–model P1

---

## 10. Ma trận xử lý sau phân tích

| Tình huống | Hành động |
|------------|-----------|
| Tỷ lệ BT đỏ (≥10%) | Mở Theo ngày → ngày tệ nhất → Theo điểm/xe P1 → ticket |
| Điểm P1 | Kiểm tra hiện trường điểm; nếu 1 xe ≥60% lượt → kiểm tra xe trước |
| Xe P1 (Kẹt/100 cao) | Nếu dồn 1 điểm → sửa điểm; nếu rải nhiều điểm → bảo dưỡng xe |
| Model P1 | So %timeout & chu kỳ vs TB đội; drill-down xe gây timeout |
| \|CSV − API create\| lớn | Kiểm tra thiếu file / lệch ngày / log debug vs log chính |
| Ngày có `-` bất thường | Thiếu Log AGV — bổ sung log, không kết luận “0 kẹt” |

---

## 11. Xử lý sự cố thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|------------|-------------|------------|
| Không thêm được folder | Không có `Log*.txt` / tên không chứa ngày | Đúng cấu trúc mục 2.1 |
| «Chưa có dữ liệu» khi PHÂN TÍCH | Inventory trống | Thêm nguồn trước |
| 稼動 = 0 / trống | Chưa set Tasks Log hoặc thiếu CSV | Cài đặt → chọn thư mục; kiểm tra tên file |
| Banner thiếu CSV/API | Thiếu file ngày đó | Bổ sung hoặc chấp nhận KPI trống |
| Phân tích lâu | Tháng nhiều file | Bình thường (≤4 worker); có thể Hủy xem partial |
| App không mở | Thiếu DLL onedir / antivirus | Chạy từ full folder; whitelist |
| Xuất Excel lỗi | File đang mở / không quyền ghi | Đóng Excel; chọn thư mục có quyền |
| Kết quả “lạ” sau đổi ngưỡng | Đổi Cài đặt chưa chạy lại | **PHÂN TÍCH** lại |
| Log AGV đọc lỗi / số liệu lệch | File không UTF-8 | Chuyển encoding UTF-8 |
| Drop «Không nhận diện được» | Sai loại file | Dùng LogYYYYMMDD / Tasks Log / `YYYYMMDD.csv` / `.log` |

---

## 12. An toàn dữ liệu & trách nhiệm

1. **Không** sửa nội dung log gốc trên máy sản xuất từ app.
2. Sao lưu log + CSV trước khi dọn dung lượng ổ đĩa.
3. Excel là **snapshot** theo cấu hình lúc chạy — ghi rõ ngưỡng/ca nếu gửi ngoài team.
4. Báo cáo partial: ghi chú *«phân tích chưa đủ ngày»*.
5. Sheet **Cho sếp xem** nêu ngưỡng chung `threshold_min`; điểm thang máy thực tế dùng 3 phút — kỹ thuật giải thích với hiện trường khi cần.

---

## 13. Tài liệu kèm & liên hệ kỹ thuật

| Tài liệu | Vị trí |
|----------|--------|
| Hướng dẫn build `.exe` | `agv_app/BUILD.md` |
| Cấu hình mặc định | `agv_app/point_settings.json` (và bản cạnh `.exe`) |
| App chạy | `dist/AGV_Analyzer/AGV_Analyzer.exe` |
| Source logic | `agv_app/core/`, `agv_app/gui/` |

---

## Phụ lục A — Quy trình 1 trang (in treo bàn)

1. Mở `AGV_Analyzer.exe`  
2. **Cài đặt** → Tasks Log (+ ngưỡng nếu cần) → **Lưu**  
3. **Dữ liệu** → Quét khoảng ngày / Thêm thư mục cha / kéo-thả  
4. **PHÂN TÍCH** → chờ xong (hoặc **Hủy** nếu chỉ cần partial)  
5. Đọc **banner** → **Tổng quan** → P1 điểm/xe/model  
6. **Xuất Excel** → đặt tên `AGV_Report_YYYYMM_DDMMYYYY.xlsx`  
7. Gửi họp / lưu trữ / mở ticket nếu đỏ hoặc P1  

---

## Phụ lục B — Phân tích 1 tháng (từng click)

1. Chuẩn bị ổ chứa `Log2026MMDD` đủ tháng.  
2. Chuẩn bị thư mục Tasks Log có `2026MMDD.csv` (+ API logs nếu có).  
3. Mở app → tab **Cài đặt** → **Thư mục Tasks Log** → Chọn → **Lưu cài đặt**.  
4. Tab **Dữ liệu** → Thêm theo khoảng → chọn thư mục gốc log.  
5. Từ = ngày 1 tháng; Đến = ngày cuối tháng → **Quét & thêm theo khoảng**.  
6. Hộp thoại ngày thiếu → Yes nếu muốn bổ sung folder tìm được.  
7. Kiểm tra badge / số dòng ≈ số ngày có log.  
8. **PHÂN TÍCH**.  
9. Theo dõi `i/N` và worker; không tắt máy nếu cần full.  
10. Banner sạch → tab **Theo tháng** + **Tổng quan** + P1.  
11. **Xuất Excel** → `AGV_Report_YYYYMM_....xlsx`.  
12. (Tuỳ chọn) Xuất CSV backup.  

---

## Phụ lục C — Lịch sử sửa đổi

| Phiên bản | Ngày | Nội dung |
|-----------|------|----------|
| 1.0 | — | SOP sử dụng ban đầu (3 nguồn, GUI, chu kỳ) |
| 2.0 | 2026-07-26 | Chuẩn hóa mã SOP; bổ sung định nghĩa chỉ số, tab API, ma trận xử lý, checklist & hạn chế vận hành theo logic core hiện tại |

---

**Kết thúc SOP.**
