# Hướng dẫn build & chạy - AGV Analyzer

Ứng dụng phân tích chất lượng hoạt động của AGV (tỷ lệ bất thường + tỷ lệ hoạt động
稼動率 từ Tasks Log) từ các thư mục log.
Khuyến nghị **Python 3.10** (tương thích 3.8–3.10). Không dùng pandas/numpy.

Giao diện hoàn toàn **tiếng Việt có dấu**, thiết kế theo hướng "sếp nhìn phát là hiểu".

## 1. Tính năng chính
- Thêm nhiều thư mục log cùng lúc (nút, chọn thư mục cha tự quét, **khoảng ngày**, hoặc kéo-thả).
- Gợi ý / bổ sung ngày thiếu trong khoảng đã chọn (hữu ích sau ngày nghỉ).
- **Phân tích song song** nhiều ngày (ThreadPool, tới 4 worker) + nút **Hủy** (giữ kết quả partial).
- Index Tasks Log **một lần** / phiên (không quét lại từng ngày) — phù hợp nạp cả tháng.
- Giữ nguyên logic phát hiện bất thường của bản gốc (`ptich_agv/abnormalAnalyse.py`).
- **Tasks Log CSV**: 稼動率 theo ca/ngày/tuần/tháng, model mix, chu kỳ nhiệm vụ, timeout.
- **Tab Tổng quan (dashboard)**: thẻ KPI + biểu đồ xu hướng bất thường & 稼動 + xếp hạng điểm/xe +
  so sánh ca ngày/đêm + mẫu theo thứ + phân nhóm mức độ nặng.
- Panel trái tách **Dữ liệu / Cài đặt**; tab kết quả **lazy-load** khi mở.
- Các tab chi tiết: Theo ngày / Theo điểm / Theo xe / Theo model / Theo tuần / Theo tháng / Điều phối (API).
- **Xuất Excel** nhiều sheet (gồm tỷ lệ hoạt động, Theo model), có **công thức sống** và **biểu đồ**.
- **Xuất CSV** kèm cột đầu vào, khối 稼動 theo ca và chú thích công thức.
- **Cài đặt mở rộng**: ngưỡng bất thường, thang máy, điểm loại trừ, giờ ca, số giờ mẫu số,
  ngưỡng màu, thư mục log / Tasks Log / xuất mặc định; lưu ra `point_settings.json`.

### Checklist: phân tích 1 tháng
1. Tab **Dữ liệu** → chọn thư mục cha hoặc khoảng ngày (~28–31 folder `LogYYYYMMDD`).
2. Cài đặt → chỉ đường dẫn **Tasks Log** (nếu có CSV nhiệm vụ).
3. Bấm **PHÂN TÍCH** — theo dõi thanh trạng thái (`ngày i/N · file · worker`).
4. Có thể **Hủy** giữa chừng; banner báo partial nếu dừng sớm.
5. Xem **Tổng quan** / tuần / tháng / 稼動; xuất Excel khi cần.
6. Dist onedir thường ~80MB (soft cap &lt;100MB) — không cần siết size.

## 2. Yêu cầu môi trường build
- Windows 10/11 **64-bit**.
- **Python 3.10.x (x64)** khuyến nghị (dùng để build; runtime `.exe` cần không Python).
  Python 3.8–3.9 vẫn chạy được nếu cần.

## 3. Tạo môi trường và cài thư viện (chỉ làm 1 lần)
Chạy từ **thư mục gốc dự án** (nơi chứa thư mục `agv_app`):

```powershell
py -3.10 -m venv .venv310
.\.venv310\Scripts\python.exe -m pip install --upgrade pip
.\.venv310\Scripts\python.exe -m pip install -r agv_app\requirements.txt
```

Các phiên bản PINNED:
- PyQt5 5.15.10 + PyQt5-Qt5 5.15.2 + PyQt5-sip 12.13.0
- openpyxl 3.1.2 (đủ để tạo công thức + biểu đồ trong Excel)
- pyinstaller 5.13.2

> Biểu đồ trong ứng dụng được vẽ bằng `QPainter` (tự vẽ), không cần thư viện
> biểu đồ ngoài, giữ gói nhẹ và "bật là chạy".

## 4. Chạy thử (chế độ phát triển)
```powershell
.\.venv310\Scripts\python.exe -m agv_app.main
```

## 5. Build ra file .exe (onedir - bật lên chạy ngay)

> **QUAN TRỌNG:** PyInstaller bị lỗi khi **đường dẫn dự án chứa ký tự có dấu**
> (vd `Dự án CNTT`) -> lỗi `WinError 123`. Vì vậy HÃY DÙNG SCRIPT tự động build ở
> đường dẫn ASCII bên dưới. (App sau khi build vẫn chạy tốt ở thư mục có dấu.)

### Cách 1 (khuyên dùng) - script tự động:
```powershell
powershell -ExecutionPolicy Bypass -File agv_app\build\build.ps1
```
Script sẽ: tạo thư mục build ASCII (`%USERPROFILE%\agv_build`), tạo venv 3.10, cài
thư viện, build, rồi chép kết quả về `dist\AGV_Analyzer\` của dự án.

### Cách 2 - thủ công (chỉ khi dự án nằm ở đường dẫn ASCII, không dấu):
```powershell
.\.venv310\Scripts\pyinstaller.exe agv_app\build\agv_app.spec --noconfirm
```

Kết quả:
```
dist\AGV_Analyzer\AGV_Analyzer.exe   <-- nháy đúp để chạy
```
Toàn bộ thư mục `dist\AGV_Analyzer\` là app độc lập:
- **Chép cả thư mục** sang máy khác (Windows 64-bit) là chạy được ngay, không cần cài Python.
- Dạng **onedir** nên bật lên là có ngay (không phải giải nén ra temp).
- App CHẠY được ở đường dẫn có dấu; chỉ riêng quá trình BUILD mới cần đường dẫn ASCII.

## 6. Đưa lên GitHub
- Nén `dist\AGV_Analyzer\` thành `AGV_Analyzer.zip` rồi tải lên (Release hoặc LFS).
- Người dùng tải về, giải nén, chạy `AGV_Analyzer.exe`.

## 7. Tùy chỉnh cấu hình
File `point_settings.json` (nằm trong bản đóng gói và có thể đặt cạnh .exe) chứa:
- `threshold_min`: ngưỡng dừng bất thường chung (mặc định 12 phút).
- `denom_hours`: số giờ mẫu số khi tính tỷ lệ (mặc định 24).
- `elevator`: điểm thang máy + ngưỡng riêng (mặc định 3 phút).
- `excluded_points`: điểm loại trừ theo nhóm.
- `shift`: giờ ca ngày/đêm.
- `display`: ngưỡng màu tốt/cảnh báo.
- `paths`: thư mục log / xuất / **task_log_dir** (Tasks Log CSV).

App mặc định áp dụng ngưỡng thang máy nếu danh sách điểm không rỗng.
