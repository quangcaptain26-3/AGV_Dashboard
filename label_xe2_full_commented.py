# ================================================================
# FILE TỔNG HỢP: LOGIC KIỂM TRA NHÃN SẢN PHẨM (LABEL CHECK) - MODEL XE2
# Sắp xếp theo đúng THỨ TỰ ĐƯỢC GỌI khi chạy thực tế, không theo thứ tự
# xuất hiện trong file gốc, để dễ đọc theo luồng:
#
#   show_image_Label_check (hàm chính)
#       -> normalize_* (chuẩn hoá text OCR đọc được)
#       -> check_value (so khớp với giá trị chuẩn)
#       -> cambrian_space / cambrian_space_SN (chấm điểm YOLO, Pass/Fail cuối)
# ================================================================


# ================================================================
# NHÓM 1: CÁC HÀM "NORMALIZE" - SỬA LỖI OCR HAY GẶP
# Camera + PaddleOCR thường đọc nhầm 1 số ký tự quen thuộc:
#   O <-> 0   (chữ O và số 0)
#   l <-> I   (chữ l thường và chữ I hoa)
#   ~ bị đọc thành "-"
#   dấu "," giữa các cụm số bị đọc thành dấu "."
# Các hàm dưới đây dùng "từ điển lỗi đã biết trước" (whitelist) + regex
# để sửa lại text OCR trước khi đem so sánh với giá trị chuẩn.
# ================================================================

def normalize_switch(text):
    """Chuẩn hóa tên switch -> 'eero Switch'"""
    if not text:
        return ""
    text = text.strip()

    # Liệt kê sẵn các kiểu OCR đọc sai từng gặp trong thực tế của
    # chuỗi "eero Switch" -> map thẳng về đúng 1 chuỗi chuẩn.
    # LƯU Ý: đây là whitelist cứng - lỗi OCR nào MỚI, chưa có trong
    # danh sách này sẽ KHÔNG được sửa -> dễ dẫn tới Fail oan.
    replacements = {
        'eeroSwltch': 'eero Switch',
        'eeroSw1tch': 'eero Switch',
        'eero5witch': 'eero Switch',
        'eeroSwitch': 'eero Switch',
        'eeroswitch': 'eero Switch',
        'eer0Switch': 'eero Switch',
        'eer0 Swltch': 'eero Switch',
        'eero Swltch': 'eero Switch',
        'eero Sw1tch': 'eero Switch',
        'eero  Switch': 'eero Switch',   # 2 khoảng trắng
        'eero  Swltch': 'eero Switch',
    }
    for wrong, correct in replacements.items():
        text = text.replace(wrong, correct)

    # Cuối cùng gom mọi khoảng trắng thừa (nhiều space liên tiếp) về 1 space
    return re.sub(r'\s+', ' ', text).strip()


def normalize_model(text):
    """Chuẩn hóa model -> 'M/N: WH01'"""
    if not text:
        return ""
    text = text.strip()

    # Sửa lỗi hay gặp nhất: chữ O bị đọc lẫn vào số 0 trong mã model
    # "WHO2" (chữ O) thực chất phải là "WH02" (số 0)
    text = text.replace('WHO', 'WH0')
    text = text.replace('XEO', 'XE0')

    # Chuẩn hoá lại định dạng "M/N: " dù OCR đọc dính liền
    # ("M/N:XE02"), có nhiều khoảng trắng ("M/N :  XE02"),
    # hay thiếu dấu 2 chấm ("M/N XE02")
    text = re.sub(r'M/N\s*:\s*', 'M/N: ', text, flags=re.IGNORECASE)
    text = re.sub(r'M/N\s+', 'M/N: ', text, flags=re.IGNORECASE)

    return re.sub(r'\s+', ' ', text).strip()


def normalize_input(text):
    """Chuẩn hóa input -> 'Input: 100-240V\~, 10.55A, 50-60Hz'"""
    if not text:
        return ""
    text = text.strip()

    # Chữ "Input" bị OCR đọc sai theo nhiều kiểu -> ép về đúng 1 dạng
    text = text.replace('lnput', 'Input')   # chữ "l" nhầm chữ "I"
    text = text.replace('INPUT', 'Input')
    text = text.replace('input', 'Input')

    # Dấu "~" (approximately/AC) trên nhãn thật hay bị OCR đọc thành "-"
    text = text.replace('100-240V-', '100-240V\~')

    # Regex quan trọng: sửa trường hợp dấu PHẨY giữa các cụm số
    # (vd giữa "1.67A" và "50-60Hz") bị OCR đọc nhầm thành dấu CHẤM
    # Ví dụ: "1.67A.50-60Hz"  ->  "1.67A,50-60Hz"
    text = re.sub(r'(\d+\.?\d*A)[.,](\d)', r'\1,\2', text)

    # Chuẩn hoá lại "Input: " (khoảng trắng, dấu 2 chấm)
    text = re.sub(r'Input\s*:\s*', 'Input: ', text, flags=re.IGNORECASE)

    return re.sub(r'\s+', ' ', text).strip()


def normalize_output(text):
    """Chuẩn hóa output -> 'Output: 54.5V⎓, 1.65A, per port'
       LƯU Ý: hàm này hiện KHÔNG được gọi trong show_image_Label_check
       (phần self.output / output_ok đã bị comment hết trong code chính)
       -> có thể để dành cho model khác hoặc tính năng sẽ bật lại sau."""
    if not text:
        return ""
    text = text.strip()
    text = text.replace('0utput', 'Output')
    text = text.replace('OUTPUT', 'Output')
    text = text.replace('output', 'Output')
    text = text.replace('perp0rt', 'per port')
    text = text.replace('perport', 'per port')
    text = text.replace('per p0rt', 'per port')
    text = text.replace('V-', 'V⎓')          # ký hiệu DC bị đọc nhầm thành "-"
    text = re.sub(r'(\d+\.?\d*A)[.,](\d)', r'\1,\2', text)
    text = re.sub(r'Output\s*:\s*', 'Output: ', text, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', text).strip()


def normalize_power(text):
    """Chuẩn hóa power -> '720W'
       LƯU Ý: cũng KHÔNG được gọi trong code chính hiện tại (đã bị comment)"""
    if not text:
        return ""
    text = text.strip()
    # Ép toàn bộ chữ O/o thành số 0 (áp dụng cho MỌI ký tự trong chuỗi,
    # khác với các hàm trên chỉ thay theo từng cụm cố định)
    text = text.replace('O', '0')
    text = text.replace('o', '0')
    text = text.replace('72OW', '720W')
    text = text.replace('I72OW', '720W')
    text = text.replace('l72OW', '720W')
    text = text.replace('|72OW', '720W')
    return re.sub(r'\s+', '', text)


def normalize_sn(text):
    """Chuẩn hóa S/N đọc được từ OCR để so sánh với SN thật (self.thissn)"""
    if not text:
        return ""
    text = text.strip()

    # Bỏ tiền tố "S/N:" hoặc "S/N " ra khỏi chuỗi, chỉ giữ lại phần số serial
    text = re.sub(r'S/N\s*:\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'S/N\s+', '', text, flags=re.IGNORECASE)

    # CẨN THẬN: ép cứng toàn bộ chữ O -> số 0, chữ l -> chữ I
    # trên TOÀN BỘ chuỗi SN. Nếu SN thật của sản phẩm có chứa
    # đúng chữ O hoặc chữ l/I thì việc ép này có thể gây sai lệch
    # khi so với self.thissn (SN thật lấy từ máy scan/barcode).
    # -> Đây là điểm nên kiểm tra kỹ nếu gặp lỗi "SN mismatch" bất thường.
    text = text.replace('O', '0')
    text = text.replace('l', 'I')

    return text.strip()


# ================================================================
# NHÓM 2: HÀM SO KHỚP GIÁ TRỊ
# ================================================================

def check_value(value, expected):
    """Kiểm tra value (giá trị OCR đọc + đã normalize) có khớp với
    expected (giá trị chuẩn khai báo trong check_label_xe2/...) không.

    expected có thể là:
      - string đơn  -> so khớp tuyệt đối (==)
      - list nhiều biến thể -> chỉ cần khớp 1 trong các biến thể đó

    Đây là lý do trong check_label_xe2, "model" và "input" được khai báo
    dạng LIST (nhiều cách viết được coi là đúng do OCR hay đọc lệch),
    còn "switch" là STRING đơn (vì sau khi normalize chỉ còn đúng 1 dạng).
    """
    if expected is None or value is None:
        return False
    if isinstance(expected, list):
        return value in expected
    return value == expected


# ================================================================
# NHÓM 3: HÀM CHẤM ĐIỂM KẾT QUẢ YOLO (AOI INFERENCE)
# Cả 2 hàm dưới đây LOGIC GIỐNG HỆT NHAU, chỉ khác:
#   - cambrian_space_SN: có thêm tham số save_sn -> tên file ảnh lưu
#     kèm theo SN sản phẩm (dùng khi CÓ SFIS, cần truy vết theo SN)
#   - cambrian_space: không có SN trong tên file (dùng khi BYPASS SFIS)
# ================================================================

def cambrian_space(self, cambrian_result_list, cambrian_img, cambrian_label_list):
    """
    cambrian_result_list : kết quả YOLO dự đoán cho từng vùng ảnh đã cắt
                            (ví dụ trả về "1","2",...,"6" nếu nhận diện đúng
                            class, hoặc "NG" nếu model báo lỗi/không nhận diện được)
    cambrian_img          : ảnh gốc (grayscale) để vẽ khung kết quả lên
    cambrian_label_list   : chính là step1_check_draw từ show_image_Label_check
                            -> list các [y1, y2, x1, x2, label_so] đã cắt trước đó
    """
    try:
        AOI_inference_step = []   # danh sách True/False cho từng vùng, dùng để tổng kết Pass/Fail cuối

        # Chuyển ảnh xám về lại 3 kênh màu để có thể vẽ khung màu (đỏ/xanh) lên
        cambrian_img = cv2.cvtColor(cambrian_img, cv2.COLOR_GRAY2RGB)

        # Duyệt qua từng vùng đã cắt (ứng với từng nhãn số 1-6)
        for each_label in range(len(cambrian_label_list)):

            # ------------------------------------------------------------
            # TRƯỜNG HỢP FAIL cho vùng này:
            #   - YOLO trả về "NG" (Not Good - model tự báo lỗi), HOẶC
            #   - Kết quả YOLO trả về KHÔNG TRÙNG với nhãn số gốc đã đặt
            #     (ví dụ vùng được đặt tên là "3" nhưng YOLO lại nhận
            #     diện/phân loại ra kết quả khác "3")
            # ------------------------------------------------------------
            if cambrian_result_list[each_label] == "NG" or cambrian_result_list[each_label] != str(
                    cambrian_label_list[each_label][4]):

                # Vẽ khung ĐỎ quanh vùng lỗi
                # cambrian_label_list[each_label] = [y1, y2, x1, x2, label]
                # -> điểm góc (x1,y1) và (x2,y2)
                cv2.rectangle(cambrian_img,
                              (cambrian_label_list[each_label][2], cambrian_label_list[each_label][0]),
                              (cambrian_label_list[each_label][3], cambrian_label_list[each_label][1]),
                              (0, 0, 255), 10, 15)

                # Ghi text kết quả YOLO ngay phía trên khung (để biết model trả về gì)
                text1 = str(cambrian_result_list[each_label])
                org = (int(cambrian_label_list[each_label][2]), int(cambrian_label_list[each_label][0]) - 50)
                font = cv2.FONT_HERSHEY_SIMPLEX
                fontScale = 2
                color = (0, 0, 255)
                thickness = 6
                cv2.putText(cambrian_img, text1, org, font, fontScale, color, thickness)

                AOI_inference_step.append(False)   # đánh dấu vùng này FAIL

            # ------------------------------------------------------------
            # TRƯỜNG HỢP PASS cho vùng này:
            #   - Kết quả YOLO khác "NG" VÀ trùng đúng với nhãn số gốc
            # ------------------------------------------------------------
            elif cambrian_result_list[each_label] != "NG" and cambrian_result_list[each_label] == str(
                    cambrian_label_list[each_label][4]):

                # Vẽ khung XANH quanh vùng đạt
                cv2.rectangle(cambrian_img,
                              (cambrian_label_list[each_label][2], cambrian_label_list[each_label][0]),
                              (cambrian_label_list[each_label][3], cambrian_label_list[each_label][1]),
                              (0, 255, 0), 10, 15)

                text1 = str(cambrian_result_list[each_label])
                org = (int(cambrian_label_list[each_label][2]), int(cambrian_label_list[each_label][0]) - 50)
                font = cv2.FONT_HERSHEY_SIMPLEX
                fontScale = 2
                color = (0, 255, 0)
                thickness = 6
                cv2.putText(cambrian_img, text1, org, font, fontScale, color, thickness)

                AOI_inference_step.append(True)    # đánh dấu vùng này PASS

        # ------------------------------------------------------------
        # TỔNG KẾT: chỉ cần 1 vùng bất kỳ bị False (FAIL) thì cả sản phẩm
        # coi như FAIL. Phải TẤT CẢ các vùng đều True mới được "Pass".
        # ------------------------------------------------------------
        if False not in AOI_inference_step:
            cv2.imwrite(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_pass.jpg",
                        cambrian_img)
            return "Pass"
        elif False in AOI_inference_step:
            cv2.imwrite(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_fail.jpg",
                        cambrian_img)
            return "Fail"

    except Exception as e:
        logging.error(str(e))
        self.myuihand.textbox.emit(str(e))


def cambrian_space_SN(self, cambrian_result_list, cambrian_img, cambrian_label_list, save_sn=""):
    """
    Logic hoàn toàn giống hệt cambrian_space() ở trên.
    Khác biệt DUY NHẤT: tên file ảnh lưu ra có kèm theo save_sn (SN sản phẩm)
    thay vì chỉ có timestamp -> phục vụ truy vết theo từng SN cụ thể
    (dùng khi CÓ bật SFIS, vì lúc đó cần map ảnh kết quả với đúng SN
    đã được ghi nhận trên hệ thống MES).
    """
    try:
        AOI_inference_step = []
        cambrian_img = cv2.cvtColor(cambrian_img, cv2.COLOR_GRAY2RGB)

        for each_label in range(len(cambrian_label_list)):
            if cambrian_result_list[each_label] == "NG" or cambrian_result_list[each_label] != str(
                    cambrian_label_list[each_label][4]):

                cv2.rectangle(cambrian_img,
                              (cambrian_label_list[each_label][2], cambrian_label_list[each_label][0]),
                              (cambrian_label_list[each_label][3], cambrian_label_list[each_label][1]),
                              (0, 0, 255), 10, 15)
                text1 = str(cambrian_result_list[each_label])
                org = (int(cambrian_label_list[each_label][2]), int(cambrian_label_list[each_label][0]) - 50)
                font = cv2.FONT_HERSHEY_SIMPLEX
                fontScale = 2
                color = (0, 0, 255)
                thickness = 6
                cv2.putText(cambrian_img, text1, org, font, fontScale, color, thickness)
                AOI_inference_step.append(False)

            elif cambrian_result_list[each_label] != "NG" and cambrian_result_list[each_label] == str(
                    cambrian_label_list[each_label][4]):

                cv2.rectangle(cambrian_img,
                              (cambrian_label_list[each_label][2], cambrian_label_list[each_label][0]),
                              (cambrian_label_list[each_label][3], cambrian_label_list[each_label][1]),
                              (0, 255, 0), 10, 15)
                text1 = str(cambrian_result_list[each_label])
                org = (int(cambrian_label_list[each_label][2]), int(cambrian_label_list[each_label][0]) - 50)
                font = cv2.FONT_HERSHEY_SIMPLEX
                fontScale = 2
                color = (0, 255, 0)
                thickness = 6
                cv2.putText(cambrian_img, text1, org, font, fontScale, color, thickness)
                AOI_inference_step.append(True)

        # save_sn được chèn vào tên file (khác với cambrian_space không có)
        if False not in AOI_inference_step:
            cv2.imwrite(self.pciture_save + "//" + todaytime + "//" + save_sn + "_" + self.img_time + "_pass.jpg",
                        cambrian_img)
            return "Pass"
        elif False in AOI_inference_step:
            cv2.imwrite(self.pciture_save + "//" + todaytime + "//" + save_sn + "_" + self.img_time + "_fail.jpg",
                        cambrian_img)
            return "Fail"

    except Exception as e:
        logging.error(str(e))
        self.myuihand.textbox.emit(str(e))


# ================================================================
# NHÓM 4: BỘ GIÁ TRỊ CHUẨN DÙNG ĐỂ ĐỐI CHIẾU NHÃN SẢN PHẨM
# Mỗi model (XE2, XE4, WORMHOLE...) có 1 dict riêng như thế này
# ================================================================
check_label_xe2 = {
    "switch": "eero Switch",                                   # tên switch in trên nhãn phải khớp đúng chuỗi này
    "model": ["M/N: XE02", "M/N: XEO2"],                        # cho phép 2 biến thể (OCR hay nhầm số 0 <-> chữ O)
    "input": ["Input: 100-240V\~,1.67A,50-60Hz",                # 2 biến thể ký tự "~" bị OCR đọc lệch encoding
              "Input: 100-240V~,1.67A,50-60Hz"]
}


# ================================================================
# NHÓM 5: HÀM CHÍNH - ĐIỀU PHỐI TOÀN BỘ QUY TRÌNH KIỂM TRA NHÃN
# self          : instance của class UI/controller chính
# image_numpy   : ảnh chụp từ camera (dạng numpy array, BGR)
# stepname      : tên bước hiện tại, hàm này chỉ xử lý khi = "STEP 1"
# ================================================================
def show_image_Label_check(self, image_numpy, stepname):
    try:
        # ------------------------------------------------------
        # Lưu ảnh gốc chụp được ra ổ đĩa (để truy vết / audit sau này)
        # Tên file gồm: SN + tên bước + thời gian chụp
        # ------------------------------------------------------
        self.thissn = self.scaninfo
        cv2.imwrite(
            self.pciture_save + "/" + todaytime + "//" + self.thissn + "_" + stepname + "_" + self.img_time + ".jpg",
            image_numpy)

        # Chuyển ảnh màu -> ảnh xám để việc cắt vùng / xử lý sau đỡ nặng hơn
        image_numpy = cv2.cvtColor(image_numpy, cv2.COLOR_BGR2GRAY)

        if stepname == "STEP 1":
            if self.sfis_choose == True:
                # ========================================================
                # BƯỚC 1: TRUY VẤN HỆ THỐNG SFIS ĐỂ BIẾT SẢN PHẨM NÀY
                # THUỘC MODEL NÀO (dựa trên mã lệnh sản xuất "liaohao")
                # ========================================================
                print(self.thissn)
                liaohao = (self.mysfis.get_sfis_90(self.thissn)).split("\x7f")[3].split("/")[0]
                print(liaohao)

                # ============================================================
                # GÁN need_check DỰA TRÊN LIAOHAO
                # -> mỗi model có bộ giá trị chuẩn khác nhau để so sánh sau này
                # -> self.eero_model / eero_model1: 2 biến thể chuỗi model
                #    (phòng trường hợp OCR đọc nhầm số 0 thành chữ O)
                # ============================================================
                if ("WORMHOLE.4" in liaohao or "WORMHOLE4" in liaohao):
                    self.eero_model = "M/N: WH01"
                    self.eero_model1 = "M/N: WHO1"
                    need_check = check_label_worm4
                elif ("WORMHOLE.2" in liaohao or "WORMHOLE2" in liaohao):
                    self.eero_model = "M/N: WH02"
                    self.eero_model1 = "M/N: WHO2"
                    need_check = check_label_worm2
                elif ("XENIA.2" in liaohao or "XENIA2" in liaohao):
                    self.eero_model = "M/N: XE02"
                    self.eero_model1 = "M/N: XEO2"
                    need_check = check_label_xe2          # <-- model đang xử lý trong file này
                elif ("XENIA.4" in liaohao or "XENIA4" in liaohao):
                    self.eero_model = "M/N: XE01"
                    self.eero_model1 = "M/N: XEO1"
                    need_check = check_label_xe4
                else:
                    # Không nhận diện được model -> dừng xử lý, báo lỗi lên UI
                    logging.error(f"Unknown liaohao: {liaohao}")
                    self.myuihand.textbox.emit(f"Unknown liaohao: {liaohao}")
                    return

                print(self.eero_model, self.eero_model1)
                print(need_check)

                # ========================================================
                # BƯỚC 2: CẮT ẢNH THEO TỪNG VÙNG ĐÃ ĐÁNH DẤU SẴN
                # (self.barcode_point là file annotation kiểu labelme,
                #  đã được setup thủ công từ trước, KHÔNG tự sinh lúc chạy)
                # ========================================================
                step1_check = []        # list ảnh đã cắt (đưa vào YOLO -> cambrian_result_list)
                step1_check_draw = []   # list toạ độ + nhãn số (đưa vào cambrian_space/cambrian_space_SN)
                ok1 = self.barcode_point

                for shape in ok1["shapes"]:
                    label = shape['label']      # tên vùng: "1","2",..."6" hoặc "model"
                    points = shape["points"]    # toạ độ 2 điểm góc [[x1,y1],[x2,y2]]

                    # Nếu label là số 1-6 -> đây là các vùng chi tiết cần YOLO kiểm tra
                    # (logo, mã vạch, dòng chữ...) đã được đặt tên số thủ công lúc setup
                    if "1" in label or "2" in label or "3" in label or "4" in label or "5" in label or "6" in label:
                        valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]),
                                     label]
                        y1, y2, x1, x2, label = valuelist
                        cut_img_step1 = image_numpy[int(y1):int(y2), int(x1):int(x2)]  # cắt ảnh theo toạ độ
                        step1_check_draw.append(valuelist)   # lưu lại toạ độ để vẽ số lên ảnh sau
                        step1_check.append(cut_img_step1)    # lưu ảnh cắt để đưa vào model YOLO
                        # cv2.imwrite(... )  # (đã comment - dòng debug cũ, không dùng nữa)

                    # Nếu label = "model" -> đây là vùng chứa toàn bộ khối text nhãn
                    # (Switch / Input / S-N) để đưa qua OCR ở bước sau
                    elif label == "model":
                        valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]),
                                     label]
                        y1, y2, x1, x2, label = valuelist
                        cut_img = image_numpy[int(y1):int(y2), int(x1):int(x2)]
                        cv2.imwrite("source/model.jpg", cut_img)   # lưu ra file tạm để OCR đọc

                # Đọc lại 2 ảnh: ảnh nhãn vừa cắt, và ảnh mẫu chuẩn (dùng để hiển thị so sánh trên UI)
                need_show1 = cv2.imread("source/model.jpg")
                need_show2 = cv2.imread("source/XE02.jpg")

                if self.cambrian_is_open:
                    self.lineEdit_8.setText(self.thissn)

                    if self.sfis_choose == True:
                        # ============================================================
                        # BƯỚC 3: CHECK ROUTE TRÊN SFIS
                        # (kiểm tra xem SN này có đang đúng quy trình sản xuất không)
                        # ============================================================
                        self.sfisreturn = self.mysfis.check_route(self.thissn)
                        if self.sfisreturn[0] == "0":
                            # FAIL route -> thử auto repair (sửa lỗi tuyến tự động)
                            logging.info(f"check route FAIL")
                            self.myuihand.textbox.emit("check route FAIL")

                            # Lần fail đầu tiên (LF#:0) -> repair lần 1
                            if "[LF#:0]" in self.sfisreturn and "[REPAIR OF" in self.sfisreturn:
                                sfisrepairreturn = self.mysfis.repair_SN(self.thissn)
                                if sfisrepairreturn[0] == "1":
                                    logging.info(f"first auto repair OK")
                                    self.myuihand.textbox.emit(f"first auto repair OK")
                                    self.check_result_OK = True
                                elif sfisrepairreturn[0] == "0":
                                    logging.info(f"first auto repair NG")
                                    self.myuihand.textbox.emit(f"first auto repair NG")
                                    self.check_result_OK = False
                            # Lần fail thứ hai (LF#:1) -> repair lần 2
                            elif "[LF#:1]" in self.sfisreturn and "[REPAIR OF" in self.sfisreturn:
                                sfisrepairreturn = self.mysfis.repair_SN(self.thissn)
                                if sfisrepairreturn[0] == "1":
                                    logging.info(f"second auto repair OK")
                                    self.myuihand.textbox.emit(f"second auto repair OK")
                                    self.check_result_OK = True
                                elif sfisrepairreturn[0] == "0":
                                    logging.info(f"second auto repair NG")
                                    self.myuihand.textbox.emit(f"second auto repair NG")
                                    self.check_result_OK = False

                        elif self.sfisreturn[0] == "1":
                            # Route OK ngay từ đầu, không cần repair
                            logging.info(f"check route OK")
                            self.myuihand.textbox.emit("check route OK")
                            self.check_result_OK = True

                        # LƯU Ý: dòng này ép cứng luôn thành True, bỏ qua kết quả
                        # check_result_OK thật sự phía trên -> có thể là code debug/tạm thời
                        self.check_result_OK = True

                        if self.check_result_OK:
                            # ============================================================
                            # BƯỚC 4: OCR ĐỌC NỘI DUNG NHÃN
                            # Dùng PaddleOCR để đọc chữ trong ảnh "source/model.jpg"
                            # ============================================================
                            ocr = PaddleOCR(use_gpu=False, use_angle_cls=True, lang="ch", )
                            img_path = "source/model.jpg"
                            result = ocr.ocr(img_path, cls=True)
                            # result[0] = list các dòng text OCR tìm được, mỗi dòng gồm:
                            #   [ [4 điểm góc polygon], (text, confidence) ]
                            # Thứ tự các dòng theo đúng thứ tự OCR quét được trên ảnh (trên -> dưới)

                            # Khởi tạo giá trị mặc định trước khi parse OCR
                            self.switch = ""
                            self.model = ""
                            self.input = ""
                            self.sn_check = ""

                            # Duyệt từng dòng OCR đọc được, phân loại theo từ khoá xuất hiện trong dòng
                            for each_result in result[0]:
                                text_raw = each_result[1][0]   # nội dung text của dòng này
                                print(each_result[1][0])

                                # Dòng chứa "M/N:" -> đây là dòng ghép "Switch | M/N: model"
                                if "M/N:" in text_raw or "M/N" in text_raw:
                                    text = re.sub(r'\s+', '', text_raw)   # xoá hết khoảng trắng để dễ tách chuỗi

                                    # Lấy phần TRƯỚC "M/N" -> đó là tên switch
                                    # -> đưa qua normalize_switch() ở NHÓM 1 để sửa lỗi OCR
                                    m = re.search(r'^(.*?)M/N', text, re.I)
                                    if m:
                                        self.switch = normalize_switch(m.group(1).replace("|", "").strip())
                                    else:
                                        self.switch = ""

                                    # Lấy 9 ký tự bắt đầu từ "M/N:" -> đó là mã model (vd "M/N: XE02")
                                    # -> đưa qua normalize_model() để sửa O/0
                                    idx = text.upper().find("M/N:")
                                    if idx != -1:
                                        self.model = normalize_model(text[idx:idx + 9])
                                    else:
                                        self.model = ""

                                    print(f"Switch: '{self.switch}', Model: '{self.model}'")

                                # Dòng chứa "Input" -> lấy nguyên dòng, đưa qua normalize_input()
                                elif "Input" in text_raw:
                                    self.input = normalize_input(text_raw)
                                    print(f"Input: '{self.input}'")

                                # Dòng chứa "S/N" -> đây là serial number in trên nhãn
                                # -> đưa qua normalize_sn()
                                elif "S/N" in text_raw:
                                    self.sn_check = normalize_sn(text_raw)
                                    print(f"SN: '{self.sn_check}'")

                            # ============================================================
                            # KIỂM TRA (GỌN - DÙNG check_value ở NHÓM 2)
                            # So sánh giá trị đọc được (đã normalize) với giá trị chuẩn (need_check)
                            # ============================================================
                            model_ok = check_value(self.model, need_check.get("model"))
                            switch_ok = check_value(self.switch, need_check.get("switch"))
                            input_ok = check_value(self.input, need_check.get("input"))
                            # SN thì so trực tiếp: SN đọc từ nhãn phải khớp đúng SN đã scan (self.thissn)
                            sn_ok = (self.thissn == self.sn_check)

                            print(f"Model: {model_ok}, Switch: {switch_ok} ",
                                  f"Input: {input_ok}, SN: {sn_ok}")

                            # ============================================================
                            # XỬ LÝ PASS / FAIL (dựa trên kết quả OCR + normalize + check_value)
                            # ============================================================
                            if model_ok and switch_ok and input_ok and sn_ok:
                                # ============================================================
                                # TRƯỜNG HỢP OCR PASS - Vẽ khung XANH quanh 3 dòng text OCR
                                # đầu tiên (Switch, Input, S/N) để người vận hành nhìn trực quan
                                # result[0][i][0][0] = điểm góc trên-trái của dòng i
                                # result[0][i][0][2] = điểm góc dưới-phải của dòng i
                                # ============================================================
                                if len(result[0]) >= 3:
                                    cv2.rectangle(need_show1,
                                                  (int(result[0][0][0][0][0]), int(result[0][0][0][0][1])),
                                                  (int(result[0][0][0][2][0]), int(result[0][0][0][2][1])),
                                                  (0, 255, 0), 6, 6)   # dòng 0 (Switch/Model)
                                    cv2.rectangle(need_show1,
                                                  (int(result[0][1][0][0][0]), int(result[0][1][0][0][1])),
                                                  (int(result[0][1][0][2][0]), int(result[0][1][0][2][1])),
                                                  (0, 255, 0), 6, 6)   # dòng 1 (Input)
                                    cv2.rectangle(need_show1,
                                                  (int(result[0][2][0][0][0]), int(result[0][2][0][0][1])),
                                                  (int(result[0][2][0][2][0]), int(result[0][2][0][2][1])),
                                                  (0, 255, 0), 6, 6)   # dòng 2 (S/N)

                                # Lưu ảnh đã khoanh xanh + hiển thị lên UI (khung số 3, vị trí số 2)
                                cv2.imwrite(
                                    self.pciture_save + "//" + todaytime + "//" + self.img_time + "_label_Pass.jpg",
                                    need_show1)
                                self.UI_show(
                                    self.pciture_save + "//" + todaytime + "//" + self.img_time + "_label_Pass.jpg",
                                    3, 2)
                                # Lưu thêm ảnh mẫu chuẩn (need_show2) để hiển thị đối chiếu song song
                                cv2.imwrite(
                                    self.pciture_save + "//" + todaytime + "//" + self.img_time + "_label1_Pass.jpg",
                                    need_show2)
                                self.UI_show(
                                    self.pciture_save + "//" + todaytime + "//" + self.img_time + "_label1_Pass.jpg",
                                    3, 1)

                                logging.info("content check OK")
                                self.myuihand.textbox.emit("content check OK")

                                # ============================================================
                                # BƯỚC 5: YOLO INFERENCE
                                # Đưa các ảnh đã cắt theo số 1-6 (step1_check) vào model YOLO
                                # để kiểm tra chất lượng in ấn / vị trí (méo, mờ, lệch...)
                                # ============================================================
                                inference_result = self.get_inference_result(step1_check)
                                logging.error("inference finish")
                                self.myuihand.textbox.emit("inference finish")

                                # Gọi cambrian_space_SN (NHÓM 3) - đây mới là nơi CHẤM ĐIỂM
                                # thật sự Pass/Fail dựa trên việc so khớp kết quả YOLO với
                                # nhãn số gốc (1-6), đồng thời vẽ khung xanh/đỏ + text kết quả
                                # lên ảnh gốc (ảnh dưới-trái trong UI)
                                yolo_step1 = self.cambrian_space_SN(inference_result, image_numpy, step1_check_draw,
                                                                    self.thissn)

                                if yolo_step1 == "Pass":
                                    # Tất cả đều đạt -> hiển thị PASS, cập nhật thống kê, upload SFIS
                                    self.UI_show(
                                        self.pciture_save + "//" + todaytime + "//" + self.thissn + "_" + self.img_time + "_pass.jpg",
                                        3, 3)
                                    logging.info("step1 check ok")
                                    self.myuihand.textbox.emit("step1 check ok")
                                    my_inference_result = "pass"

                                    if my_inference_result == "pass":
                                        self.resultcolor("Pass")   # đổi màu ô kết quả trên UI thành xanh
                                        # Cập nhật số liệu: Total+1, Pass+1, Fail giữ nguyên, tính lại % Yield Rate
                                        self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                                         str(int(self.lineEdit_5.text()) + 1),
                                                         self.lineEdit_6.text(),
                                                         "%.2f%%" % ((int(self.lineEdit_5.text()) + 1) / (
                                                                 int(self.lineEdit_4.text()) + 1) * 100))

                                    if self.sfis_choose == True:
                                        # Upload kết quả kiểm tra lên hệ thống SFIS
                                        self.mysfis.data_upload(self.thissn, self.data)
                                        logging.info("sfis upload OK")
                                        self.myuihand.textbox.emit("sfis upload OK")

                                    # Lưu ảnh tổng kết "ALL PASS"
                                    cv2.imwrite(
                                        self.pciture_save + "//" + todaytime + "//" + self.thissn + " ALL PASS " + self.img_time + ".jpg",
                                        image_numpy)
                                    logging.info(self.thissn + " all test PASS")
                                    self.myuihand.textbox.emit(self.thissn + " all test PASS")

                                    self.step1 = True   # đánh dấu bước STEP 1 đã pass

                                elif yolo_step1 == "Fail":
                                    # YOLO phát hiện lỗi (dù OCR nội dung đã đúng)
                                    self.UI_show(
                                        self.pciture_save + "//" + todaytime + "//" + self.thissn + "_" + self.img_time + "_fail.jpg",
                                        3, 1)
                                    logging.info("step1 check fail")
                                    self.myuihand.textbox.emit("step1 check fail")
                                    self.step1 = False

                            else:
                                # ============================================================
                                # TRƯỜNG HỢP OCR FAIL - Vẽ khung ĐỎ quanh 3 dòng text (thay vì xanh)
                                # + lưu ảnh debug để xem lỗi ở đâu. Đến đây thì KHÔNG chạy YOLO
                                # nữa (vì nội dung nhãn đã sai ngay từ vòng OCR)
                                # ============================================================
                                if len(result[0]) >= 3:
                                    cv2.rectangle(need_show1,
                                                  (int(result[0][0][0][0][0]), int(result[0][0][0][0][1])),
                                                  (int(result[0][0][0][2][0]), int(result[0][0][0][2][1])),
                                                  (0, 0, 255), 6, 6)
                                    cv2.rectangle(need_show1,
                                                  (int(result[0][1][0][0][0]), int(result[0][1][0][0][1])),
                                                  (int(result[0][1][0][2][0]), int(result[0][1][0][2][1])),
                                                  (0, 0, 255), 6, 6)
                                    cv2.rectangle(need_show1,
                                                  (int(result[0][2][0][0][0]), int(result[0][2][0][0][1])),
                                                  (int(result[0][2][0][2][0]), int(result[0][2][0][2][1])),
                                                  (0, 0, 255), 6, 6)

                                cv2.imwrite(
                                    self.pciture_save + "//" + todaytime + "//" + self.img_time + "_label_Fail.jpg",
                                    need_show1)
                                self.UI_show(
                                    self.pciture_save + "//" + todaytime + "//" + self.img_time + "_label_Fail.jpg",
                                    3, 2)

                                # Tổng hợp thông tin lỗi cụ thể (giá trị đọc được vs giá trị mong đợi)
                                # để in ra log / UI, giúp người vận hành biết chính xác chỗ nào sai
                                error_details = []
                                if not model_ok:
                                    error_details.append(
                                        f"Model: '{self.model}' (expected: {need_check.get('model')})")
                                if not switch_ok:
                                    error_details.append(
                                        f"Switch: '{self.switch}' (expected: {need_check.get('switch')})")
                                if not input_ok:
                                    error_details.append(
                                        f"Input: '{self.input}' (expected: {need_check.get('input')})")
                                # Output/Power hiện đang bị comment (chưa dùng)
                                # if not output_ok:
                                #     error_details.append(
                                #         f"Output: '{self.output}' (expected: {need_check.get('output')})")
                                # if not power_ok:
                                #     error_details.append(
                                #         f"Power: '{self.power}' (expected: {need_check.get('power')})")
                                if not sn_ok:
                                    error_details.append(f"SN: '{self.sn_check}' (expected: '{self.thissn}')")

                                error_msg = " | ".join(error_details)
                                logging.error(f"content check FAIL: {error_msg}")
                                self.myuihand.textbox.emit(f"content check FAIL: {error_msg}")
                                self.step1 = False   # đánh dấu STEP 1 fail

                    elif self.sfis_choose == False:
                        # ============================================================
                        # NHÁNH BYPASS SFIS
                        # Không kiểm tra route / không OCR nội dung nhãn,
                        # chỉ chạy thẳng YOLO trên các vùng đã cắt (step1_check)
                        # ============================================================
                        logging.info(f"check route bypass")
                        self.myuihand.textbox.emit("check route bypass")
                        inference_result1 = self.get_inference_result(step1_check)
                        print(inference_result1)
                        logging.error("inference finish")
                        self.myuihand.textbox.emit("inference finish")

                        # Gọi cambrian_space (KHÔNG có "_SN") - logic chấm điểm giống hệt
                        # cambrian_space_SN, chỉ khác tên file lưu không gắn kèm SN
                        yolo_step1 = self.cambrian_space(inference_result1, image_numpy, step1_check_draw)

                        if yolo_step1 == "Pass":
                            self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_pass.jpg",
                                         6, 1)
                            logging.info(self.scaninfo + " all test PASS")
                            self.myuihand.textbox.emit(self.scaninfo + " all test PASS")
                            cv2.imwrite(
                                self.pciture_save + "//" + todaytime + "//" + self.scaninfo + "ALL PASS " + self.img_time + ".jpg",
                                image_numpy)
                            self.resultcolor("Pass")
                            self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                             str(int(self.lineEdit_5.text()) + 1),
                                             self.lineEdit_6.text(),
                                             "%.2f%%" % ((int(self.lineEdit_5.text()) + 1) / (
                                                     int(self.lineEdit_4.text()) + 1) * 100))
                            if self.sfis_choose == True:
                                self.mysfis.data_upload(self.scaninfo, self.data)
                                logging.info("sfis upload OK")
                                self.myuihand.textbox.emit("sfis upload OK")
                            self.step1 = True
                        elif yolo_step1 == "Fail":
                            self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_fail.jpg",
                                         1, 1)
                            self.step1 = False

                elif self.cambrian_is_open == False:
                    # Giao diện Cambrian tắt -> bỏ qua toàn bộ kiểm tra, mặc định coi như Pass
                    self.step1 = True

    except Exception as e:
        # Bắt mọi lỗi phát sinh trong quá trình xử lý (OCR lỗi, YOLO lỗi, SFIS timeout...)
        # để chương trình không bị crash, chỉ log lại và báo lên UI
        logging.error(str(e))
        self.myuihand.textbox.emit(str(e))
