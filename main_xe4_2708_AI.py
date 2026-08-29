# config：iplas+sfis設定
# 選擇機種model文件，相機+點位+推論+纍計測試信息

##20250213 8P還差推論和SFIS部分，Button_check也一樣，目前僅供驗證


# from yolov5.classify import  predict_change
import sys
import typing
from UI import Ui_MainWindow
import sfisapi
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtWidgets import *
from PyQt5.QtCore import QObject, Qt, QTranslator, QEvent, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QPixmap, QStandardItemModel, QImage
import json
import os
import time
from datetime import datetime, timedelta
import logging
import ctypes
from suds.client import Client
from pega_inference.v2.sample_client import SampleClient as SampleClientV2
import re
import cv2
import threading
from pypylon import pylon
from basler_my import camera
# from ioCardNew import IoCard
from pylibdmtx import pylibdmtx
import numpy as np
from PIL import ImageChops, ImageStat, Image
import pyzbar.pyzbar as pyzbar
from paddleocr import PaddleOCR
import paddle
from queue import Queue
import hashlib

# from ipex_check_yolo import camera_check_ipex2586929307542

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
basicdir = os.path.join(os.getcwd())
todaytime = datetime.now().strftime("%Y%m%d")
todaytime1 = datetime.now().strftime("%Y-%m-%d %H%M%S")
check_ocr_C1000_8P_2G_L = ['品名：以太网交换机/乙太網交换機', '型号/型號：C1000-8P-2G-L',
                           '制造商/製造商：CiscoSystems,Inc', '输人/输入：100-240V~，电流/電流：1A-0.4A.50-60Hz',
                           'MTCTE:379402216', 'R-R-TNY-C1000-8P-2G-L', 'ANATEL', 'HU101357-24008',
                           'A/SNo:+822-3429-8000', 'Rating/classe:100-240V~,1A-0.4A,50-60Hz', 'CANICES-3(A)/NMB-3(A)',
                           '仅适用于海拔2000m以下地区安全使用', 'PoEOutputInfo:Singleport-54VDC,0.55A,30WMax.',
                           'Totaloutput67w', 'ModelNo/ModeleNo:C1000-8P-2G-L', 'MfgDate（DatedeFab):']
check_ocr_C1000_8P_2G_L_part1 = 9
check_ocr_C1000_8P_2G_L_part2 = 7
check_label_C1000_8P_2G_L = ['CMM5800ARC', 'CLEI+S/N', "74-122903-03 B0", "C1000-8P-2G-L V03"]
check_ocr_C1000_8T_2G_L = ['品名：以太网交换机/乙太網交换機', '型号/型号：C1000-8T-2G-L',
                           '制造商/製造商：CiscoSystems,Inc', '输人/输入：100-240V~，电流/電流：0.4A-0.2A,50-60Hz',
                           'E317539MTCTE:379402216', 'R-R-TNY-C1000-8T-2G-L', 'ANATEL',
                           'Rating/classe:100-240V~0.4A-0.2A,50-60Hz', 'CANICES-3(A)/NMB-3(A)',
                           '仅适用于海拔2000m以下地区安全使用', 'ModelNo/ModeleNo:C1000-8T-2G-L', 'MfgDate（DatedeFab):']
check_ocr_C1000_8T_2G_L_part1 = 7
check_ocr_C1000_8T_2G_L_part2 = 5
check_label_C1000_8T_2G_L = ['CMM5700ARD', 'CLEI+S/N', "74-122902-04 B0", "C1000-8T-2G-L V04"]
check_ocr_C1200_8FP_2G = ['MfgDate(DatedeFab):']
check_label_C1200_8FP_2G = ["74-131959-03 A0", "C1200-8FP-2G V03"]
check_ocr_C1200_8P_E_2G = ['MfgDate(DatedeFab):']
check_label_C1200_8P_E_2G = ["74-131958-03 A0", "C1200-8P-E-2G V03"]
check_ocr_C1200_8T_E_2G = ['MfgDate(DatedeFab):']
check_label_C1200_8T_E_2G = ["74-131957-03 A0", "C1200-8T-E-2G V03"]
check_ocr_C1300_8P_E_2G = ['MfgDate(DatedeFab):']
check_label_C1300_8P_E_2G = ["479627", "74-131829-02 A0", "C1300-8P-E-2G V02"]
check_ocr_C1300_8T_E_2G = ['MfgDate(DatedeFab):']
check_label_C1300_8T_E_2G = ["479622", "74-131828-02 A0", "C1300-8T-E-2G V02"]
model_and_90 = {"90BBA61002G0": "C1000_8P_2G_L", "90BBA61002H0": "C1000_8T_2G_L", "90BBAV1000Q0": "C1200_8FP_2G",
                "90BBAV1000P0": "C1200_8P_E_2G", "90BBAV1000T0": "C1200_8T_E_2G", "90BBAV1000R0": "C1300_8P_E_2G",
                "90BBAV1000V0": "C1300_8T_E_2G"}

check_label_worm2 = []
check_label_xe2 = []
check_label_worm4 = []

check_label_xe4 = {
    "switch": "eero Switch",
    "model": ["M/N:XE01", "M/N:XEO1"],
    "input": ["Input: 100-240V\~,6.11A,50-60Hz", "Input: 100-240V~,6.11A,50-60Hz"],
    "output": "Output: 54.5V⎓,1.65A,per port",
    "power": "360WPoE",
}


def normalize_switch(text):
    """Chuẩn hóa tên switch -> 'eero Switch'"""
    if not text:
        return ""
    text = text.strip()
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
        'eero  Switch': 'eero Switch',
        'eero  Swltch': 'eero Switch',
    }
    for wrong, correct in replacements.items():
        text = text.replace(wrong, correct)
    return re.sub(r'\s+', ' ', text).strip()


def normalize_model(text):
    """Chuẩn hóa model -> 'M/N: WH01'"""
    if not text:
        return ""
    text = text.strip()
    text = text.replace('WHO', 'WH0')
    text = text.replace('XEO', 'XE0')
    text = re.sub(r'M/N\s*:\s*', 'M/N: ', text, flags=re.IGNORECASE)
    text = re.sub(r'M/N\s+', 'M/N: ', text, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', text).strip()


def normalize_input(text):
    """Chuẩn hóa input -> 'Input: 100-240V\~, 10.55A, 50-60Hz'"""
    if not text:
        return ""
    text = text.strip()
    text = text.replace('lnput', 'Input')
    text = text.replace('INPUT', 'Input')
    text = text.replace('input', 'Input')
    text = text.replace('100-240V-', '100-240V\~')
    text = re.sub(r'(\d+\.?\d*A)[.,](\d)', r'\1,\2', text)
    text = re.sub(r'Input\s*:\s*', 'Input: ', text, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', text).strip()


def normalize_output(text):
    """Chuẩn hóa output -> 'Output: 54.5V⎓, 1.65A, per port'"""
    if not text:
        return ""
    text = text.strip()
    text = text.replace('0utput', 'Output')
    text = text.replace('OUTPUT', 'Output')
    text = text.replace('output', 'Output')
    text = text.replace('perp0rt', 'per port')
    text = text.replace('perport', 'per port')
    text = text.replace('per p0rt', 'per port')
    text = text.replace('V-', 'V⎓')
    text = re.sub(r'(\d+\.?\d*A)[.,](\d)', r'\1,\2', text)
    text = re.sub(r'Output\s*:\s*', 'Output: ', text, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', text).strip()


def normalize_power(text):
    """Chuẩn hóa power -> '720W'"""
    if not text:
        return ""
    text = text.strip()
    text = text.replace('O', '0')
    text = text.replace('o', '0')
    text = text.replace('36OW', '360W')
    text = text.replace('I36OW', '360W')
    text = text.replace('l36OW', '360W')
    text = text.replace('|36OW', '360W')
    text = text.replace('360WP0E', '360WPoE')
    text = text.replace('360WPOE', '360WPoE')
    text = text.replace('360Wp0E', '360WPoE')
    return re.sub(r'\s+', '', text)


def normalize_sn(text):
    """Chuẩn hóa S/N"""
    if not text:
        return ""
    text = text.strip()
    text = re.sub(r'S/N\s*:\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'S/N\s+', '', text, flags=re.IGNORECASE)
    text = text.replace('O', '0')
    text = text.replace('l', 'I')
    return text.strip()


def check_value(value, expected):
    """Kiểm tra value có khớp expected không (expected có thể là str hoặc list)"""
    if expected is None or value is None:
        return False
    if isinstance(expected, list):
        return value in expected
    return value == expected


# DEFAULT_BARCODE_WIDTH = 3840
# DEFAULT_BARCODE_HEIGHT = 2748
#
# DEFAULT_RESOLUTION_WIDTH = 3840
# DEFAULT_RESOLUTION_HEIGHT = 2748
# print(ctypes.windll.user32.MessageBoxW(0,'python！','111',1))

class Uihand(QtCore.QObject):
    textbox = QtCore.pyqtSignal(str)
    test1 = QtCore.pyqtSignal()
    test2 = QtCore.pyqtSignal()
    test3 = QtCore.pyqtSignal()
    clear_show = QtCore.pyqtSignal()


class Mytest(QThread):
    timeout = pyqtSignal()

    def __init__(self):
        super(Mytest, self).__init__()

    def run(self):
        self.timeout.emit()


class Demo(QMainWindow, Ui_MainWindow):
    is_saved = True
    is_saved_first = True
    _startThread = pyqtSignal()
    _startThread1 = pyqtSignal()

    def __init__(self):
        super(Demo, self).__init__()
        self.setupUi(self)
        self.setWindowFlags(Qt.WindowStaysOnTopHint)

        self.mysignal = QtCore.pyqtSignal(str)
        self.text_browser = QTextBrowser(self)
        self.scrollArea.setWidget(self.text_browser)
        self.data = r'"TEST","STATUS","VALUE"' + '\r\n'

        self.create_log()
        python_obj = json.load(open('config.json', 'r'))

        self.deviceshow = python_obj["sfisinfo"]["device"]
        self.sfis_choose = python_obj["sfisinfo"]["is_open"]

        ##check sfis
        if python_obj["sfisinfo"]["is_open"] == True:
            try:
                self.mysfis = sfisapi.do_sfis(python_obj["sfisinfo"]["service_web_url"], self.deviceshow,
                                              python_obj["sfisinfo"]["opid"])
                if self.mysfis.sfis:
                    # self.sfis = Client(python_obj["sfisinfo"]["service_web_url"])
                    logging.info(f"SFIS Connect OK")
                    self.get_rightnow("SFIS Connect OK")
            except:
                logging.error(f"Please check SFIS Eth")
                ctypes.windll.user32.MessageBoxW(0, 'Please check SFIS Eth！', 'Error Message', 0)
                sys.exit()

            loginstring = self.mysfis.loginout("5")
            if loginstring[0] == "0":
                self.mysfis.loginout("2")
                loginstring1 = self.mysfis.loginout("1")
                if loginstring1[0] == "1":
                    logging.info(f"SFIS Login ok")
                    self.get_rightnow("SFIS Login ok")
                elif loginstring1[0] == "0":
                    logging.error(f"Login failed, Please check the SFIS network or Device")
                    self.get_rightnow("Login failed, Please check the SFIS network or Device")
            elif loginstring[0] == "1":
                self.mysfis.loginout("1")
                logging.info(f"SFIS Login ok")
                self.get_rightnow("SFIS Login ok")
        elif python_obj["sfisinfo"]["is_open"] != True:
            if python_obj["sfisinfo"]["is_open"] == False:
                logging.info(f"SFIS Disable,go on")
                self.get_rightnow("SFIS Disable,go on")
            elif python_obj["sfisinfo"]["is_open"] != False:
                logging.error(f"SFIS Input error,please check")
                ctypes.windll.user32.MessageBoxW(0, 'SFIS Input error,please check！', 'Error Message', 0)
                sys.exit()

        ##check iplas
        # if python_obj["iplasinfo"]["is_open"] == True:

        # check camera
        self.comboBox_2.addItem("from model")
        self.comboBox_2.setCurrentIndex(0)
        self.mycamera = camera()
        self.allcameras, self.cameras_dev = self.mycamera.search_get_device()
        if self.allcameras == []:
            logging.error(f"cameras get failed")
            ctypes.windll.user32.MessageBoxW(0, 'cameras get failed！', 'Error Message', 0)
            sys.exit()
        elif self.allcameras != []:
            logging.info(f"cameras get OK")
            self.get_rightnow("cameras get OK")
            for cameraconfig in self.allcameras:
                self.comboBox_2.addItem(str(cameraconfig))

        if python_obj["choose_model"] != "":
            try:

                selected_file = python_obj["choose_model"]

                modelinfo = json.load(open(selected_file, 'r', encoding="utf8"))
                logging.info(f"model read OK")
                self.get_rightnow("model read OK")
                self.select_model = modelinfo["model"]
                cambrian = modelinfo.get("cambrian", False)
                # self.get_rightnow(json.dumps(cambrian))

                logging.info(json.dumps(cambrian))
                models_point_path = modelinfo.get("path_json", False)
                self.count_path = modelinfo.get("count_json", False)
                self.sensor_no = modelinfo.get("sensor_no", False)
                self.sensor_start = modelinfo.get("sensor_start", False)
                self.is_sensor = modelinfo.get("is_sensor", True)
                self.HH4K = modelinfo

                if cambrian["is_cambrian"] == True:
                    self.cambrian_is_open = True
                    self.cambrian_inference_server_url = cambrian.get("inference_server_url")
                    self.cambrian_inference_server_port = cambrian.get("inference_server_port")
                    self.cambrian_model_name = cambrian["model_name"]
                    self.cambrian_model_token = cambrian["model_token"]
                    self.cambrian_product_name = cambrian["product_name"]
                    self.cambrian_model_weight = cambrian["model_weight"]
                    self.cambrian_model_version = cambrian["model_version"]
                    self.cambrian_caller_id = cambrian.get("caller_id", "S15052752")

                    if (self.cambrian_model_weight is None) or (self.cambrian_model_version is None):

                        self.client = SampleClientV2(
                            url=self.cambrian_inference_server_url,
                            port=self.cambrian_inference_server_port,
                            model_name=self.cambrian_model_name,
                            model_token=self.cambrian_model_token
                            # product_name=self.product_name,
                            # product_sku=self.product_sku,
                            # caller_id=self.caller_id,

                        )
                    else:
                        self.client = SampleClientV2(
                            url=self.cambrian_inference_server_url,
                            port=self.cambrian_inference_server_port,
                            model_name=self.cambrian_model_name,
                            model_token=self.cambrian_model_token,
                            # product_name=self.product_name,
                            # product_sku=self.product_sku,
                            # caller_id=self.caller_id,
                            model_weight=self.cambrian_model_weight,
                            model_version=self.cambrian_model_version
                        )

                    try:
                        self.window_name = self.get_version()
                        logging.info(f"Canbrian initialization succeeded {self.window_name}")  # Canbrian初始化成功
                        self.get_rightnow("Canbrian initialization succeeded")
                    except:
                        logging.error(f"Canbrian initialization failed")  # Canbrian初始化失败
                        ctypes.windll.user32.MessageBoxW(0, "Canbrian initialization failed, Please check",
                                                         "Cambrian API FAIL !!!", 1)
                        sys.exit()

                    if cambrian["is_cambrian"] == False:
                        logging.info(f"Canbrian disable")  # Canbrian初始化成功
                        self.get_rightnow("Canbrian disable")

                # check camera
                if modelinfo["camera_id"] not in self.allcameras:
                    ctypes.windll.user32.MessageBoxW(0, 'check cameras config failed！', 'Error Message', 0)
                    logging.error(f"check cameras config failed")
                    sys.exit()
                elif modelinfo["camera_id"] in self.allcameras:

                    logging.info(f"check cameras config OK")
                    self.get_rightnow("check cameras config OK")

                # 獲取點位信息
                self.barcode_point = json.load(open(models_point_path.get("barcode_path_json"), 'r'))
                if "step" not in (models_point_path.get("model_path_json")):
                    self.model_point = json.load(open(models_point_path.get("model_path_json"), 'r'))
                elif "step" in (models_point_path.get("model_path_json")):
                    self.model_point = models_point_path.get("model_path_json")

                # 獲取纍計測試信息,相機信息
                self.count_object = json.load(open(self.count_path, 'r'))
                self.camera_id_info = modelinfo["camera_id"]
                self.camera_barcode_info = modelinfo["camera_barcode"]
                # if self.camera_id_info not in self.allcameras or self.camera_barcode_info not in self.allcameras:
                #     logging.error(f"model camera set error")
                #     ctypes.windll.user32.MessageBoxW(0, "model camera set error",
                #                                      "Cambrian API FAIL !!!", 1)
                #     sys.exit()
                # elif self.camera_id_info in self.allcameras and self.camera_barcode_info in self.allcameras:
                #     logging.info(f"model camera get ok")
                #     self.get_rightnow(f"model camera get ok")

                # 更新頁面count信息
                self.lineEdit_2.setText(self.select_model)
                self.lineEdit_3.setText(str(self.deviceshow))
                self.lineEdit_4.setText(self.count_object["Total"])
                self.lineEdit_5.setText(self.count_object["Pass"])
                self.lineEdit_6.setText(self.count_object["fail"])
                self.lineEdit_7.setText(self.count_object["Yield rate"])
                logging.info(f"count info get ok")  #
                self.get_rightnow("count info get ok")
            except Exception as e:
                print(str(e))

        if python_obj["choose_route"] != "":

            self.pciture_save = python_obj["choose_route"]
            self.lineEdit_1.setText(self.pciture_save)
            logging.info(f"route choose ok")  #
            self.get_rightnow("route choose ok")
            try:
                os.makedirs(self.pciture_save + '\\' + todaytime)
            except FileExistsError:
                pass

        # self.imagesource_barcode = ImageSourceAgent(image_source="internet_basler", camera_id=0,
        #                                            basler_camera_id=python_obj["camera_id"])
        # self.imagesource_barcode.get_source(DEFAULT_RESOLUTION_WIDTH, DEFAULT_RESOLUTION_HEIGHT)
        # self.imagesource_barcode.set_resolution(DEFAULT_RESOLUTION_WIDTH, DEFAULT_RESOLUTION_HEIGHT)

        # 頁面語言轉換
        self.trans = QTranslator(self)  # 1
        self.comboBox_1.currentTextChanged.connect(self.change_language)
        self.comboBox_2.currentTextChanged.connect(self.change_camera)
        self.actionchoose.triggered.connect(self.choose_model)
        self.pushButton_4.clicked.connect(self.choose_route)
        self.pushButton_5.clicked.connect(self.clearcount)
        self.pushButton_1.clicked.connect(self.trainstart)
        self.pushButton_2.clicked.connect(self.startprogram)
        self.pushButton_3.clicked.connect(self.stopprogram)
        self.myuihand = Uihand()
        self.myuihand.textbox.connect(self.get_rightnow)
        self.myuihand.test1.connect(self.go_run1)
        self.myuihand.test2.connect(self.go_run2)
        self.myuihand.test3.connect(self.go_run3)
        self.myuihand.clear_show.connect(self.clear_showing)

    def get_rightnow(self, showinfo):
        rightnow = (datetime.now().strftime("%Y-%m-%d %H:%M:%S")) + "---" + showinfo
        self.text_browser.append(rightnow)
        self.update()

    def choose_route(self):
        self.file_dialog = QFileDialog.getExistingDirectory(self, "Select Folder")
        if self.file_dialog:
            self.pciture_save = "\\".join(self.file_dialog.split("/"))
            self.lineEdit_1.setText(self.pciture_save)
            logging.info(f"route choose ok")  #
            self.get_rightnow("route choose ok")
            try:
                os.makedirs(self.pciture_save + '\\' + todaytime)
            except FileExistsError:
                pass
        python_obj2 = json.load(open('config.json', 'r'))
        python_obj2["choose_route"] = self.pciture_save
        with open('config.json', "w", encoding="utf-8") as json_file:
            json.dump(python_obj2, json_file, indent=4, separators=(',', ":"))
        return self.pciture_save

    def clearcount(self):
        self.lineEdit_4.setText("0")
        self.lineEdit_5.setText("0")
        self.lineEdit_6.setText("0")
        self.lineEdit_7.setText("0%")
        self.count_object["Total"] = "0"
        self.count_object["Pass"] = "0"
        self.count_object["fail"] = "0"
        self.count_object["Yield rate"] = "0%"
        with open(self.count_path, "w", encoding="utf-8") as json_file:
            json.dump(self.count_object, json_file, indent=4, separators=(',', ":"))
        logging.info(f"count info clear ok")  #
        self.get_rightnow("count info clear ok")

    def updatecount(self, a1, a2, a3, a4):
        self.lineEdit_4.setText(a1)
        self.lineEdit_5.setText(a2)
        self.lineEdit_6.setText(a3)
        self.lineEdit_7.setText(a4)
        self.count_object["Total"] = a1
        self.count_object["Pass"] = a2
        self.count_object["fail"] = a3
        self.count_object["Yield rate"] = a4
        with open(self.count_path, "w", encoding="utf-8") as json_file:
            json.dump(self.count_object, json_file, indent=4, separators=(',', ":"))
        logging.info(f"count info update ok")  #
        self.get_rightnow("count info update ok")

    def get_version(self):
        model_version_json = self.client.get_version_json()
        # print(self.client.get_version())
        # print(model_version_json)
        model_version_json = json.loads(model_version_json)
        return (
                "name: "
                + model_version_json["models"][0]["name"]
                + ", version: "
                + model_version_json["models"][0]["version"]
        )

    def choose_model(self):
        try:
            self.file_dialog = QFileDialog()
            self.file_dialog.setFileMode(QFileDialog.AnyFile)
            if self.file_dialog.exec_():
                selected_file = "\\".join(((self.file_dialog.selectedFiles())[0]).split("/"))

                modelinfo = json.load(open(selected_file, 'r', encoding="utf8"))

                logging.info(f"model read OK")
                self.get_rightnow("model read OK")
                self.select_model = modelinfo["model"]
                cambrian = modelinfo.get("cambrian", False)
                # self.get_rightnow(json.dumps(cambrian))

                logging.info(json.dumps(cambrian))
                models_point_path = modelinfo.get("path_json", False)
                self.count_path = modelinfo.get("count_json", False)
                self.sensor_no = modelinfo.get("sensor_no", False)
                self.sensor_start = modelinfo.get("sensor_start", False)
                self.is_sensor = modelinfo.get("is_sensor", True)
                self.HH4K = modelinfo

                if cambrian["is_cambrian"] == True:
                    self.cambrian_inference_server_url = cambrian.get("inference_server_url")
                    self.cambrian_inference_server_port = cambrian.get("inference_server_port")
                    self.cambrian_model_name = cambrian["model_name"]
                    self.cambrian_model_token = cambrian["model_token"]
                    self.cambrian_product_name = cambrian["product_name"]
                    self.cambrian_model_weight = cambrian["model_weight"]
                    self.cambrian_model_version = cambrian["model_version"]
                    self.cambrian_caller_id = cambrian.get("caller_id", "S15052752")

                    if (self.cambrian_model_weight is None) or (self.cambrian_model_version is None):

                        self.client = SampleClientV2(
                            url=self.cambrian_inference_server_url,
                            port=self.cambrian_inference_server_port,
                            model_name=self.cambrian_model_name,
                            model_token=self.cambrian_model_token
                            # product_name=self.product_name,
                            # product_sku=self.product_sku,
                            # caller_id=self.caller_id,

                        )
                    else:
                        self.client = SampleClientV2(
                            url=self.cambrian_inference_server_url,
                            port=self.cambrian_inference_server_port,
                            model_name=self.cambrian_model_name,
                            model_token=self.cambrian_model_token,
                            # product_name=self.product_name,
                            # product_sku=self.product_sku,
                            # caller_id=self.caller_id,
                            model_weight=self.cambrian_model_weight,
                            model_version=self.cambrian_model_version
                        )

                    try:
                        self.window_name = self.get_version()
                        logging.info(f"Canbrian initialization succeeded {self.window_name}")  # Canbrian初始化成功
                        self.get_rightnow("Canbrian initialization succeeded")
                    except:
                        logging.error(f"Canbrian initialization failed")  # Canbrian初始化失败
                        ctypes.windll.user32.MessageBoxW(0, "Canbrian initialization failed, Please check",
                                                         "Cambrian API FAIL !!!", 1)
                        sys.exit()

                    if cambrian["is_cambrian"] == False:
                        logging.info(f"Canbrian disable")  # Canbrian初始化成功
                        self.get_rightnow("Canbrian disable")

                # check camera
                if modelinfo["camera_id"] not in self.allcameras:
                    ctypes.windll.user32.MessageBoxW(0, 'check cameras config failed！', 'Error Message', 0)
                    logging.error(f"check cameras config failed")
                    sys.exit()
                elif modelinfo["camera_id"] in self.allcameras:

                    logging.info(f"check cameras config OK")
                    self.get_rightnow("check cameras config OK")

                # 獲取點位信息
                self.barcode_point = json.load(open(models_point_path.get("barcode_path_json"), 'r'))
                if "step" not in (models_point_path.get("model_path_json")):
                    self.model_point = json.load(open(models_point_path.get("model_path_json"), 'r'))
                elif "step" in (models_point_path.get("model_path_json")):
                    self.model_point = models_point_path.get("model_path_json")
                # 獲取纍計測試信息,相機信息
                self.count_object = json.load(open(self.count_path, 'r'))
                self.camera_id_info = modelinfo["camera_id"]
                self.camera_barcode_info = modelinfo["camera_barcode"]
                # if self.camera_id_info not in self.allcameras or self.camera_barcode_info not in self.allcameras:
                #     logging.error(f"model camera set error")
                #     ctypes.windll.user32.MessageBoxW(0, "model camera set error",
                #                                      "Cambrian API FAIL !!!", 1)
                #     sys.exit()
                # elif self.camera_id_info in self.allcameras and self.camera_barcode_info in self.allcameras:
                #     logging.info(f"model camera get ok")
                #     self.get_rightnow(f"model camera get ok")

                # 更新頁面count信息
                self.lineEdit_2.setText(self.select_model)
                self.lineEdit_3.setText(str(self.deviceshow))
                self.lineEdit_4.setText(self.count_object["Total"])
                self.lineEdit_5.setText(self.count_object["Pass"])
                self.lineEdit_6.setText(self.count_object["fail"])
                self.lineEdit_7.setText(self.count_object["Yield rate"])
                logging.info(f"count info get ok")  #
                self.get_rightnow("count info get ok")
            python_obj1 = json.load(open('config.json', 'r'))
            python_obj1["choose_model"] = selected_file
            with open('config.json', "w", encoding="utf-8") as json_file:
                json.dump(python_obj1, json_file, indent=4, separators=(',', ":"))


        except Exception as e:
            print(str(e))

        # barcode
        # self.all_barcode_info = None
        #
        # # 條碼點位
        # barcode_path_json = config.get("path_json").get("barcode_path_json", "barcode/barcode.json")
        # self.barcode = get_points.Points(barcode_path_json)
        # self.barcodepoints = self.barcode.get_points()
        # print(self.barcodepoints)
        #
        # # 機種點位
        # models_path_json = config.get("path_json").get("models_path_json", "models/models.json")
        # self.model = get_points.Points(models_path_json)
        # self.modelpoints = self.model.get_points()

    def resultcolor(self, myresult):
        self.label_6.setText(myresult)
        # Result區域添加規則
        if self.label_6.text() == "Waiting":
            self.label_6.setStyleSheet("font: 16pt \"Arial\";color: black;background-color: yellow")
        elif self.label_6.text() == "Pass":
            self.label_6.setStyleSheet("font: 16pt \"Arial\";color: black;background-color: green")
        elif self.label_6.text() == "Fail":
            self.label_6.setStyleSheet("font: 16pt \"Arial\";color: black;background-color: red")

    def change_language(self):
        if self.comboBox_1.currentText() == '中文':
            self.trans.load('eng-chs')
            _app = QApplication.instance()
            _app.installTranslator(self.trans)
            self.retranslateUi(self)

        else:
            _app = QApplication.instance()
            _app.removeTranslator(self.trans)
            self.retranslateUi(self)

    def change_camera(self):
        1

    def create_log(self):
        try:
            os.makedirs(basicdir + '\\' + "log" + '\\' + todaytime)
        except FileExistsError:
            pass

        # try:
        #     os.makedirs(basicdir+ '\\' + "result"+ '\\' + todaytime)
        # except FileExistsError:
        #     pass

        logging.basicConfig(format='%(asctime)s -%(levelname)s: %(message)s',
                            level=logging.INFO,
                            filename=rf'.\log\{todaytime}\{todaytime1}.log',
                            filemode='a+')
        logging.info(f"Create logging route ok!!!")

    def savelog(self, neirong):
        1

    def get_inference_result(self, img_list):
        image_result_list = []
        # print(img_list)
        response_predict = self.client.predict_images(img_list)
        response_outputs = response_predict.outputs
        # print("==========Classification Results:==========")
        # print("category_name\tcategory_id\tmax_prop")
        for index, output in enumerate(response_outputs):
            for index1, result in enumerate(output.results):
                # category_id = int(result.category_id)
                category_name = str(result.category_name)
                # max_prop = max(result.category_probs)
                # print(category_name,"\t",category_id,"\t",max_prop)
                # print("{:<13}\t{:<11}\t{:<8}".format(category_name,category_id,max_prop))

                image_result_list.append(category_name)

        return image_result_list

    def trainstart(self):
        print(self.barcode_point, self.model_point, self.count_object, self.pciture_save, self.camera_id_info,
              self.camera_barcode_info)
        # if self.camera_id_info==self.camera_barcode_info:
        #     self.imagesource_barcode = ImageSourceAgent(image_source="internet_basler", camera_id=0,
        #                                                basler_camera_id=self.camera_id_info)
        #     self.imagesource_barcode.get_source(DEFAULT_RESOLUTION_WIDTH, DEFAULT_RESOLUTION_HEIGHT)
        #     self.imagesource_barcode.set_resolution(DEFAULT_RESOLUTION_WIDTH, DEFAULT_RESOLUTION_HEIGHT)
        #     is_ok, img, _, _ = self.imagesource_barcode.read()
        #     if is_ok == 0:
        #         self.preview_image = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    def startprogram(self):
        try:
            self.ekkoshan = camera()
            logging.info("camera open,wait grap")
            self.myuihand.textbox.emit("camera open,wait grap")
            self.wait_test = True
            self.scan_sta = False
            self.stop_program = False
            self.pushButton_2.setEnabled(False)

            if self.is_sensor:

                self.iocard = IoCard(deviceDescription="PCI-1756,BID#0", profilePath=u"profile\\pci1756.xml")
                logging.info("IO CARD init ok")
                self.myuihand.textbox.emit("IO CARD init ok")

                # self.mytest=Mytest()2643692801227

                # self.mytest.timeout.connect(self.go_run)
                # self.mytest.start()

                # main_thread=threading.Thread(target=self.go_run,name="main_proc")
                # main_thread.start()
                # main_thread.join()

                while True:
                    if self.wait_test and self.stop_program == False:
                        self.resultcolor("Waiting")
                        self.wait_test = False
                        self.tableWidget.clear()
                        self.myuihand.test1.emit()
                        if self.scan_sta and self.stop_program == False:
                            logging.info("NO DUT FOUND,WAIT")
                            self.myuihand.textbox.emit("NO DUT FOUND,WAIT")
                            self.scan_sta = False
                            self.myuihand.test2.emit()
                    if self.stop_program:
                        self.pushButton_2.setEnabled(True)
                        break

            elif self.is_sensor == False:
                while True:
                    if self.wait_test and self.stop_program == False:
                        relay = QMessageBox.question(self, "Start Test", "Please enter for test")
                        # print(relay)
                        if relay == 16384:
                            # ctypes.windll.user32.MessageBoxW(0, "Canbrian initialization failed, Please check",
                            #                                  "Cambrian API FAIL !!!", 1)

                            self.myuihand.clear_show.emit()

                            self.wait_test = False
                            self.tableWidget.clear()
                            self.myuihand.test1.emit()
                            if self.scan_sta and self.stop_program == False:
                                logging.info("NO DUT FOUND,WAIT")
                                self.myuihand.textbox.emit("NO DUT FOUND,WAIT")
                                self.scan_sta = False
                                self.myuihand.test3.emit()
                        if relay == 65536:
                            self.pushButton_2.setEnabled(True)
                            break
                    if self.stop_program:
                        self.pushButton_2.setEnabled(True)
                        break
        except Exception as e:
            logging.info(str(e))
            self.myuihand.textbox.emit(str(e))

    def clear_showing(self):
        self.resultcolor("Waiting")
        self.lineEdit_8.setText("")
        self.lineEdit_9.setText("")

    def go_run1(self):
        if self.select_model == "Button_check" or self.select_model == "Label_check":
            while True:

                input_dialog = QInputDialog(self)
                input_dialog.setInputMode(QInputDialog.TextInput)
                input_dialog.setWindowTitle('Label Input')
                input_dialog.setLabelText('please scan label:')

                input_dialog.setStyleSheet("""
                                QLabel{
                                font-size:20px;
                                font-weight:bold;
                                font-family:Arial;
                                }
                                QLineEdit{
                                font-size:20px;
                                font-weight:bold;
                                font-family:Arial;
                                }
                                QPushButton{
                                font-size:20px;
                                font-weight:bold;
                                font-family:Arial;
                                }
                                """)  # # border-style:solid;
                # border-color:black;
                # border-width:2px;

                a = ''
                input_dialog.setTextValue(a)
                # input_dialog.textValueChanged.connect('输入框 发生变化时 响应')
                input_dialog.setFixedSize(400, 400)  # 设置 输入对话框大小
                input_dialog.show()
                if input_dialog.exec_() == input_dialog.Accepted:
                    self.scaninfo = input_dialog.textValue()  # 点击ok 后 获取输入对话框内容
                    logging.info("Scan Label: " + self.scaninfo)  #
                    self.get_rightnow("Scan Label: " + self.scaninfo)
                    self.lineEdit_8.setText(self.scaninfo)
                    self.scan_sta = True
                    break
                else:
                    logging.error(f"Scan Label cancel")  # Scan失败
                    ctypes.windll.user32.MessageBoxW(0, "Scan Label cancel", 1)
                    self.wait_test = True
                    self.stop_program = True
                    break

                    # main_thread.join()

                    # self.pushButton_2.setEnabled(True)


        else:
            logging.info("Bypass Scan")
            self.myuihand.textbox.emit("Bypass Scan")
            self.scan_sta = True

    def go_run2(self):
        while self.stop_program == False:
            mysta = self.iocard.get_io_signal()
            QApplication.processEvents()

            if mysta[0] == int(self.sensor_no) and self.wait_test == False:
                continue

                # logging.info("NO DUT FOUND,WAIT 1S")
                # self.myuihand.textbox.emit("NO DUT FOUND,WAIT 1S")

                # time.sleep(1)
            elif mysta[0] == int(self.sensor_start) and self.wait_test == False:
                logging.info("DUT FOUND,start camera")
                self.myuihand.textbox.emit("DUT FOUND,start camera")

                time.sleep(5)

                # print(ekkoshan.is_open)
                ekko, shan = self.ekkoshan.get_image()
                # ekko1,shan1=ekkoshan.get_image()

                # self.shan=cv2.rotate(shan,cv2.ROTATE_180)
                self.shan = shan
                self.img_time = datetime.now().strftime("%Y%m%d%H%M")
                # cv2.imwrite(self.pciture_save+"//"+todaytime+"//"+self.scaninfo+"_"+self.img_time+".jpg",shan)

                # cv2.imwrite(self.pciture_save+"//"+todaytime+"//pic2.jpg",shan1)

                self.show_image_MR6500(self.shan)
                self.wait_test = True
            elif mysta[0] == int(self.sensor_no) and self.wait_test:
                break

    def go_run3(self):
        QApplication.processEvents()  # 必须加，不然页面不刷新

        # relay=QMessageBox.about(self,"Start Test","please enter for test")
        # if relay==None:
        if self.select_model == "MR6500":
            logging.info("DUT FOUND,start camera")
            self.myuihand.textbox.emit("DUT FOUND,start camera")

            # print(ekkoshan.is_open)
            ekko, shan = self.ekkoshan.get_image()
            # ekko1,shan1=ekkoshan.get_image()

            # self.shan=cv2.rotate(shan,cv2.ROTATE_180)
            self.shan = shan
            self.img_time = datetime.now().strftime("%Y%m%d%H%M")
            # cv2.imwrite(self.pciture_save+"//"+todaytime+"//"+self.scaninfo+"_"+self.img_time+".jpg",shan)

            # cv2.imwrite(self.pciture_save+"//"+todaytime+"//pic2.jpg",shan1)

            self.show_image_MR6500(self.shan)
            self.wait_test = True
        elif self.select_model == "ipex_check":

            logging.info("DUT FOUND,start camera")
            self.myuihand.textbox.emit("DUT FOUND,start camera")
            QApplication.processEvents()
            ekko, shan = self.ekkoshan.get_image()
            self.shan = shan
            # self.shan=cv2.imread("sample/capture_2024-12-07 113828.jpg")
            self.img_time = datetime.now().strftime("%Y%m%d%H%M")
            cv2.imwrite(self.pciture_save + "//" + todaytime + "//" + self.img_time + ".jpg", self.shan)
            try:
                mycheck_ipex = camera_check_ipex(self.shan, self.model_point)
                realisn = mycheck_ipex.decode_bar()
                if realisn != "barcode decode fail":
                    logging.error(f"Get isn ok " + realisn)
                    self.myuihand.textbox.emit(f"Get isn ok " + realisn)
                    QApplication.processEvents()
                elif realisn == "barcode decode fail":
                    logging.error(f"Get isn fail")
                    self.myuihand.textbox.emit("Get isn fail")
                    QApplication.processEvents()

                    input_dialog = QInputDialog(self)
                    input_dialog.setInputMode(QInputDialog.TextInput)
                    input_dialog.setWindowTitle('Label Input')
                    input_dialog.setLabelText('please scan label:')

                    input_dialog.setStyleSheet("""
                                        QLabel{
                                        font-size:20px;
                                        font-weight:bold;
                                        font-family:Arial;
                                        }
                                        QLineEdit{
                                        font-size:20px;
                                        font-weight:bold;
                                        font-family:Arial;
                                        }
                                        QPushButton{
                                        font-size:20px;
                                        font-weight:bold;
                                        font-family:Arial;
                                        }
                                        """)  # # border-style:solid;
                    # border-color:black;
                    # border-width:2px;

                    a = ''
                    input_dialog.setTextValue(a)
                    # input_dialog.textValueChanged.connect('输入框 发生变化时 响应')
                    input_dialog.setFixedSize(400, 400)  # 设置 输入对话框大小
                    input_dialog.show()
                    if input_dialog.exec_() == input_dialog.Accepted:
                        self.scaninfo = input_dialog.textValue()  # 点击ok 后 获取输入对话框内容
                        logging.info("Scan Label: " + self.scaninfo)  #
                        self.get_rightnow("Scan Label: " + self.scaninfo)
                        realisn = self.scaninfo

                    else:
                        logging.error(f"Scan Label cancel")  # Scan失败
                        realisn = "EMPTY"

                self.lineEdit_8.setText(realisn)
                # classpath=self.pciture_save + "//" + todaytime + "//" + realisn
                analyse_result, final_img = mycheck_ipex.analyse_image()
                if False not in analyse_result:
                    cv2.imwrite(
                        self.pciture_save + "//" + todaytime + "//" + realisn + "_" + self.img_time + "_pass.jpg",
                        final_img)
                    self.lineEdit_9.setText("Pass")
                    self.UI_show(
                        self.pciture_save + "//" + todaytime + "//" + realisn + "_" + self.img_time + "_pass.jpg",
                        1, 1)
                    self.resultcolor("Pass")
                    self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                     str(int(self.lineEdit_5.text()) + 1),
                                     self.lineEdit_6.text(),

                                     "%.2f%%" % ((int(self.lineEdit_5.text()) + 1) / (
                                             int(self.lineEdit_4.text()) + 1) * 100))
                elif False in analyse_result:
                    cv2.imwrite(
                        self.pciture_save + "//" + todaytime + "//" + realisn + "_" + self.img_time + "_fail.jpg",
                        final_img)
                    self.lineEdit_9.setText("Fail")
                    self.UI_show(
                        self.pciture_save + "//" + todaytime + "//" + realisn + "_" + self.img_time + "_fail.jpg",
                        1, 1)
                    self.resultcolor("Fail")
                    self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                     self.lineEdit_5.text(),
                                     str(int(self.lineEdit_6.text()) + 1),

                                     "%.2f%%" % ((int(self.lineEdit_5.text())) / (
                                             int(self.lineEdit_4.text()) + 1) * 100))

                QApplication.processEvents()

                logging.info(f"check ipex finish")
                self.myuihand.textbox.emit("check ipex finish")

                logging.info(f"check finish {analyse_result}")
                # self.myuihand.textbox.emit("Save OK")


            except Exception as e:
                logging.error(str(e))
                self.myuihand.textbox.emit(str(e))
            self.wait_test = True

        elif self.select_model == "HH4K":
            self.step1 = False
            self.step2 = False
            self.step3 = False
            self.step4 = False
            mychoose = QMessageBox.question(self, "STEP 1", "Please enter for test SETP 1")
            if mychoose == 16384:
                # logging.info("DUT FOUND,start camera")
                # self.myuihand.textbox.emit("DUT FOUND,start camera")
                ekko1, shan1 = self.ekkoshan.get_image()
                # ekko1,shan1=ekkoshan.get_image()

                # self.shan=cv2.rotate(shan,cv2.ROTATE_180)
                self.shan1 = shan1
                self.img_time = datetime.now().strftime("%Y%m%d%H%M%S")
                # cv2.imwrite(self.pciture_save+"//"+todaytime+"//"+self.scaninfo+"_"+self.img_time+".jpg",shan)

                # cv2.imwrite(self.pciture_save+"//"+todaytime+"//pic2.jpg",shan1)

                self.show_image_HH4K(self.shan1)
                if self.step1 == True:
                    mychoose = QMessageBox.question(self, "STEP 2", "Please enter for test SETP 2")
                    if mychoose == 16384:
                        ekko2, shan2 = self.ekkoshan.get_image()
                        self.shan2 = shan2
                        self.img_time = datetime.now().strftime("%Y%m%d%H%M%S")
                        self.show_image_HH4K(self.shan2)
                        if self.step2 == True:
                            mychoose = QMessageBox.question(self, "STEP 3", "Please enter for test SETP 3")
                            if mychoose == 16384:
                                ekko3, shan3 = self.ekkoshan.get_image()
                                self.shan3 = shan3
                                self.img_time = datetime.now().strftime("%Y%m%d%H%M%S")
                                self.show_image_HH4K(self.shan3)
                                if self.step3 == True:
                                    mychoose = QMessageBox.question(self, "STEP 4", "Please enter for test SETP 4")
                                    if mychoose == 16384:
                                        ekko4, shan4 = self.ekkoshan.get_image()
                                        self.shan4 = shan4
                                        self.img_time = datetime.now().strftime("%Y%m%d%H%M%S")
                                        self.show_image_HH4K(self.shan4)
                                        if self.step4 == True:
                                            self.wait_test = True
                                    elif mychoose == 65536:
                                        mychoose = QMessageBox.question(self, "Warning", "Yes for exit")
                                        if mychoose == 16384:
                                            self.wait_test = True
                            elif mychoose == 65536:
                                mychoose = QMessageBox.question(self, "Warning", "Yes for exit")
                                if mychoose == 16384:
                                    self.wait_test = True
                    elif mychoose == 65536:
                        mychoose = QMessageBox.question(self, "Warning", "Yes for exit")
                        if mychoose == 16384:
                            self.wait_test = True
            elif mychoose == 65536:
                mychoose = QMessageBox.question(self, "Warning", "Yes for exit")
                if mychoose == 16384:
                    self.wait_test = True
        elif self.select_model == "SKY" or self.select_model == "SKY_4G":
            self.step1 = False
            self.step2 = False
            self.step3 = False
            self.step4 = False
            self.step5 = False
            self.step6 = False
            shanshan1 = cv2.imread("source/1.jpg")
            shanshan2 = cv2.imread("source/2.jpg")
            shanshan3 = cv2.imread("source/3.jpg")
            shanshan4 = cv2.imread("source/4.jpg")
            shanshan5 = cv2.imread("source/5.jpg")
            shanshan6 = cv2.imread("source/6.jpg")

            mychoose = QMessageBox.question(self, "STEP 1", "Please enter for test SETP 1")
            if mychoose == 16384:
                # logging.info("DUT FOUND,start camera")
                # self.myuihand.textbox.emit("DUT FOUND,start camera")
                ekko1, shan1 = self.ekkoshan.get_image()
                # ekko1,shan1=ekkoshan.get_image()

                # self.shan=cv2.rotate(shan,cv2.ROTATE_180)
                self.shan1 = shan1  ####verify#######
                # self.shan1 = shanshan1  ####verify#######
                self.img_time = datetime.now().strftime("%Y%m%d%H%M%S")
                # cv2.imwrite(self.pciture_save+"//"+todaytime+"//"+self.scaninfo+"_"+self.img_time+".jpg",shan)

                # cv2.imwrite(self.pciture_save+"//"+todaytime+"//pic2.jpg",shan1)

                self.show_image_SKY(self.shan1, "STEP 1")
                if self.step1 == True:
                    mychoose = QMessageBox.question(self, "STEP 2", "Please enter for test SETP 2")
                    if mychoose == 16384:
                        ekko2, shan2 = self.ekkoshan.get_image()
                        self.shan2 = shan2  ####verify#######
                        # self.shan2 = shanshan2
                        self.img_time = datetime.now().strftime("%Y%m%d%H%M%S")
                        self.show_image_SKY(self.shan2, "STEP 2")
                        if self.step2 == True:
                            mychoose = QMessageBox.question(self, "STEP 3", "Please enter for test SETP 3")
                            if mychoose == 16384:
                                ekko3, shan3 = self.ekkoshan.get_image()
                                self.shan3 = shan3  ####verify#######
                                # self.shan3 = shanshan3
                                self.img_time = datetime.now().strftime("%Y%m%d%H%M%S")
                                self.show_image_SKY(self.shan3, "STEP 3")
                                if self.step3 == True:
                                    mychoose = QMessageBox.question(self, "STEP 4", "Please enter for test SETP 4")
                                    if mychoose == 16384:
                                        ekko4, shan4 = self.ekkoshan.get_image()
                                        self.shan4 = shan4  ####verify#######
                                        # self.shan4 = shanshan4
                                        self.img_time = datetime.now().strftime("%Y%m%d%H%M%S")
                                        self.show_image_SKY(self.shan4, "STEP 4")
                                        if self.step4 == True:
                                            mychoose = QMessageBox.question(self, "STEP 5",
                                                                            "Please enter for test SETP 5")
                                            if mychoose == 16384:
                                                ekko5, shan5 = self.ekkoshan.get_image()
                                                self.shan5 = shan5  ####verify#######
                                                # self.shan5 = shanshan5
                                                self.img_time = datetime.now().strftime("%Y%m%d%H%M%S")
                                                self.show_image_SKY(self.shan5, "STEP 5")
                                                if self.step5 == True:
                                                    mychoose = QMessageBox.question(self, "STEP 6",
                                                                                    "Please enter for test SETP 6")
                                                    if mychoose == 16384:
                                                        ekko6, shan6 = self.ekkoshan.get_image()
                                                        self.shan6 = shan6  ####verify#######
                                                        # self.shan6 = shanshan6
                                                        self.img_time = datetime.now().strftime("%Y%m%d%H%M%S")
                                                        self.show_image_SKY(self.shan6, "STEP 6")
                                                        if self.step6 == True:
                                                            self.wait_test = True
                                                        elif self.step6 == False:
                                                            logging.error(f"save fail")
                                                            self.myuihand.textbox.emit("save fail")

                                                            self.lineEdit_9.setText("Fail")

                                                            self.resultcolor("Fail")
                                                            self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                                                             self.lineEdit_5.text(),
                                                                             str(int(self.lineEdit_6.text()) + 1),

                                                                             "%.2f%%" % ((
                                                                                             int(self.lineEdit_5.text())) / (
                                                                                                 int(self.lineEdit_4.text()) + 1) * 100))
                                                            if self.sfis_choose == True:
                                                                self.mysfis.data_upload(self.thissn, self.data,
                                                                                        error="BDFA01")
                                                            logging.error("fail upload OK")
                                                            self.myuihand.textbox.emit("fail upload OK")
                                                            self.wait_test = True
                                                    elif mychoose == 65536:
                                                        mychoose = QMessageBox.question(self, "Warning", "Yes for exit")
                                                        if mychoose == 16384:
                                                            self.wait_test = True
                                                            self.stop_program = True
                                                elif self.step5 == False:
                                                    logging.error(f"save fail")
                                                    self.myuihand.textbox.emit("save fail")

                                                    self.lineEdit_9.setText("Fail")

                                                    self.resultcolor("Fail")
                                                    self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                                                     self.lineEdit_5.text(),
                                                                     str(int(self.lineEdit_6.text()) + 1),

                                                                     "%.2f%%" % ((int(self.lineEdit_5.text())) / (
                                                                             int(self.lineEdit_4.text()) + 1) * 100))
                                                    if self.sfis_choose == True:
                                                        self.mysfis.data_upload(self.thissn, self.data,
                                                                                error="BDFA01")
                                                    logging.error("fail upload OK")
                                                    self.myuihand.textbox.emit("fail upload OK")
                                                    self.wait_test = True
                                            elif mychoose == 65536:
                                                mychoose = QMessageBox.question(self, "Warning", "Yes for exit")
                                                if mychoose == 16384:
                                                    self.wait_test = True
                                                    self.stop_program = True
                                        elif self.step4 == False:
                                            logging.error(f"save fail")
                                            self.myuihand.textbox.emit("save fail")

                                            self.lineEdit_9.setText("Fail")

                                            self.resultcolor("Fail")
                                            self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                                             self.lineEdit_5.text(),
                                                             str(int(self.lineEdit_6.text()) + 1),

                                                             "%.2f%%" % ((int(self.lineEdit_5.text())) / (
                                                                     int(self.lineEdit_4.text()) + 1) * 100))
                                            if self.sfis_choose == True:
                                                self.mysfis.data_upload(self.thissn, self.data,
                                                                        error="BDFA01")
                                            logging.error("fail upload OK")
                                            self.myuihand.textbox.emit("fail upload OK")
                                            self.wait_test = True
                                    elif mychoose == 65536:
                                        mychoose = QMessageBox.question(self, "Warning", "Yes for exit")
                                        if mychoose == 16384:
                                            self.wait_test = True
                                            self.stop_program = True
                                elif self.step3 == False:
                                    logging.error(f"model or sn check fail")
                                    self.myuihand.textbox.emit("model or sn check fail")

                                    self.lineEdit_9.setText("Fail")

                                    self.resultcolor("Fail")
                                    self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                                     self.lineEdit_5.text(),
                                                     str(int(self.lineEdit_6.text()) + 1),

                                                     "%.2f%%" % ((int(self.lineEdit_5.text())) / (
                                                             int(self.lineEdit_4.text()) + 1) * 100))
                                    if self.sfis_choose == True:
                                        self.mysfis.data_upload(self.thissn, self.data,
                                                                error="BDFA01")
                                    logging.error("fail upload OK")
                                    self.myuihand.textbox.emit("fail upload OK")
                                    self.wait_test = True
                            elif mychoose == 65536:
                                mychoose = QMessageBox.question(self, "Warning", "Yes for exit")
                                if mychoose == 16384:
                                    self.wait_test = True
                                    self.stop_program = True
                        elif self.step2 == False:
                            logging.error(f"save fail")
                            self.myuihand.textbox.emit("save fail")

                            self.lineEdit_9.setText("Fail")

                            self.resultcolor("Fail")
                            self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                             self.lineEdit_5.text(),
                                             str(int(self.lineEdit_6.text()) + 1),

                                             "%.2f%%" % ((int(self.lineEdit_5.text())) / (
                                                     int(self.lineEdit_4.text()) + 1) * 100))
                            if self.sfis_choose == True:
                                self.mysfis.data_upload(self.thissn, self.data,
                                                        error="BDFA01")
                            logging.error("fail upload OK")
                            self.myuihand.textbox.emit("fail upload OK")
                            self.wait_test = True
                    elif mychoose == 65536:
                        mychoose = QMessageBox.question(self, "Warning", "Yes for exit")
                        if mychoose == 16384:
                            self.wait_test = True
                            self.stop_program = True
                elif self.step1 == False:
                    logging.error(f"step1 test fail")
                    self.myuihand.textbox.emit("step1 test fail")

                    self.lineEdit_9.setText("Fail")

                    self.resultcolor("Fail")
                    self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                     self.lineEdit_5.text(),
                                     str(int(self.lineEdit_6.text()) + 1),

                                     "%.2f%%" % ((int(self.lineEdit_5.text())) / (
                                             int(self.lineEdit_4.text()) + 1) * 100))
                    try:

                        if self.sfis_choose == True:
                            self.mysfis.data_upload(self.thissn, self.data,
                                                    error="BDFA01")
                            logging.error("fail upload OK")
                            self.myuihand.textbox.emit("fail upload OK")
                    except Exception as e:
                        logging.error("step1 test fail,sfis upload fail")
                        self.myuihand.textbox.emit("step1 test fail,sfis upload fail")
                    self.wait_test = True

            elif mychoose == 65536:
                mychoose = QMessageBox.question(self, "Warning", "Yes for exit")
                if mychoose == 16384:
                    self.wait_test = True
                    self.stop_program = True
        elif self.select_model == "C1000-8FP-E-2G-L" or self.select_model == "C1000-8P-2G-L" or self.select_model == "C1000-8T-2G-L" or self.select_model == "C1200-8FP-2G" or self.select_model == "C1200-8P-E-2G" or self.select_model == "C1200-8T-E-2G" or self.select_model == "C1300-8P-E-2G" or self.select_model == "C1300-8T-E-2G":
            self.step1 = False
            self.step2 = False
            # if self.select_model=="C1000-8P-2G-L":
            #     shanshan1=cv2.imread("sample/C1000-8P-2G-L/button.jpg")
            #     shanshan2 = cv2.imread("sample/C1000-8P-2G-L/top.jpg")
            # elif self.select_model=="C1000-8T-2G-L":
            #     shanshan1=cv2.imread("sample/C1000-8T-2G-L/button.jpg")
            #     shanshan2 = cv2.imread("sample/C1000-8T-2G-L/top.jpg")
            # elif self.select_model=="C1200-8FP-2G":
            #     shanshan1=cv2.imread("sample/C1200-8FP-2G/button.jpg")
            #     shanshan2 = cv2.imread("sample/C1200-8FP-2G/top.jpg")
            # elif self.select_model=="C1200-8P-E-2G":
            #     shanshan1=cv2.imread("sample/C1200-8P-E-2G/button.jpg")
            #     shanshan2 = cv2.imread("sample/C1200-8P-E-2G/top.jpg")
            # elif self.select_model=="C1200-8T-E-2G":
            #     shanshan1=cv2.imread("sample/C1200-8T-E-2G/button.jpg")
            #     shanshan2 = cv2.imread("sample/C1200-8T-E-2G/top.jpg")
            # elif self.select_model=="C1300-8P-E-2G":
            #     shanshan1=cv2.imread("sample/C1300-8P-E-2G/button.jpg")
            #     shanshan2 = cv2.imread("sample/C1300-8P-E-2G/top.jpg")
            # elif self.select_model=="C1300-8T-E-2G":
            #     shanshan1=cv2.imread("sample/C1300-8T-E-2G/button.jpg")
            #     shanshan2 = cv2.imread("sample/C1300-8T-E-2G/top.jpg")

            mychoose = QMessageBox.question(self, "STEP 1", "Please enter for test SETP 1")
            if mychoose == 16384:
                # logging.info("DUT FOUND,start camera")
                # self.myuihand.textbox.emit("DUT FOUND,start camera")
                ekko1, shan1 = self.ekkoshan.get_image()
                # ekko1,shan1=ekkoshan.get_image()

                # self.shan=cv2.rotate(shan,cv2.ROTATE_180)
                self.shan1 = shan1  ####verify#######
                # self.shan1 = shanshan1  ####verify#######
                self.img_time = datetime.now().strftime("%Y%m%d%H%M%S")
                # cv2.imwrite(self.pciture_save+"//"+todaytime+"//"+self.scaninfo+"_"+self.img_time+".jpg",shan)

                # cv2.imwrite(self.pciture_save+"//"+todaytime+"//pic2.jpg",shan1)

                self.show_image_C1000_8FP_E_2G_L(self.shan1, "STEP 1")
                if self.step1 == True:
                    mychoose = QMessageBox.question(self, "STEP 2", "Please enter for test SETP 2")
                    if mychoose == 16384:
                        ekko2, shan2 = self.ekkoshan.get_image()
                        self.shan2 = shan2  ####verify#######
                        # self.shan2 = shanshan2
                        self.img_time = datetime.now().strftime("%Y%m%d%H%M%S")
                        self.show_image_C1000_8FP_E_2G_L(self.shan2, "STEP 2")
                        if self.step2 == True:
                            self.wait_test = True
                        elif self.step2 == False:
                            logging.error(f"save fail")
                            self.myuihand.textbox.emit("save fail")

                            self.lineEdit_9.setText("Fail")

                            self.resultcolor("Fail")
                            self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                             self.lineEdit_5.text(),
                                             str(int(self.lineEdit_6.text()) + 1),

                                             "%.2f%%" % ((
                                                             int(self.lineEdit_5.text())) / (
                                                                 int(self.lineEdit_4.text()) + 1) * 100))
                            if self.sfis_choose == True:
                                self.mysfis.data_upload(self.thissn, self.data,
                                                        error="BDFA01")
                            logging.error("fail upload OK")
                            self.myuihand.textbox.emit("fail upload OK")
                            self.wait_test = True
                    elif mychoose == 65536:
                        mychoose = QMessageBox.question(self, "Warning", "Yes for exit")
                        if mychoose == 16384:
                            self.wait_test = True
                            self.stop_program = True

                elif self.step1 == False:
                    logging.error(f"step1 test fail")
                    self.myuihand.textbox.emit("step1 test fail")

                    self.lineEdit_9.setText("Fail")

                    self.resultcolor("Fail")
                    self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                     self.lineEdit_5.text(),
                                     str(int(self.lineEdit_6.text()) + 1),

                                     "%.2f%%" % ((int(self.lineEdit_5.text())) / (
                                             int(self.lineEdit_4.text()) + 1) * 100))
                    try:

                        if self.sfis_choose == True:
                            self.mysfis.data_upload(self.thissn, self.data,
                                                    error="BDFA01")
                            logging.error("fail upload OK")
                            self.myuihand.textbox.emit("fail upload OK")
                    except Exception as e:
                        logging.error("step1 test fail,sfis upload fail")
                        self.myuihand.textbox.emit("step1 test fail,sfis upload fail")
                    self.wait_test = True

            elif mychoose == 65536:
                mychoose = QMessageBox.question(self, "Warning", "Yes for exit")
                if mychoose == 16384:
                    self.wait_test = True
                    self.stop_program = True

        elif self.select_model == "Button_check":
            self.step1 = False

            shanshan1 = cv2.imread("sample/button_check.jpg")

            mychoose = QMessageBox.question(self, "warning", "Please Flip the model")
            if mychoose == 16384:

                # logging.info("DUT FOUND,start camera")
                # self.myuihand.textbox.emit("DUT FOUND,start camera")
                ekko1, shan1 = self.ekkoshan.get_image()
                # ekko1,shan1=ekkoshan.get_image()

                # self.shan=cv2.rotate(shan,cv2.ROTATE_180)
                self.shan1 = shan1  ####verify#######
                # self.shan1 = shanshan1  ####verify#######
                self.img_time = datetime.now().strftime("%Y%m%d%H%M%S")
                # cv2.imwrite(self.pciture_save+"//"+todaytime+"//"+self.scaninfo+"_"+self.img_time+".jpg",shan)

                # cv2.imwrite(self.pciture_save+"//"+todaytime+"//pic2.jpg",shan1)

                self.show_image_Button_check(self.shan1, "STEP 1")
                if self.step1 == True:
                    self.wait_test = True

                elif self.step1 == False:
                    logging.error(f"step1 test fail")
                    self.myuihand.textbox.emit("step1 test fail")

                    self.lineEdit_9.setText("Fail")

                    self.resultcolor("Fail")
                    self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                     self.lineEdit_5.text(),
                                     str(int(self.lineEdit_6.text()) + 1),

                                     "%.2f%%" % ((int(self.lineEdit_5.text())) / (
                                             int(self.lineEdit_4.text()) + 1) * 100))
                    try:

                        if self.sfis_choose == True:
                            self.mysfis.data_upload(self.thissn, self.data,
                                                    error="BDFA01")
                            logging.error("fail upload OK")
                            self.myuihand.textbox.emit("fail upload OK")
                    except Exception as e:
                        logging.error("step1 test fail,sfis upload fail")
                        self.myuihand.textbox.emit("step1 test fail,sfis upload fail")
                    self.wait_test = True

            elif mychoose == 65536:
                mychoose = QMessageBox.question(self, "Warning", "Yes for exit")
                if mychoose == 16384:
                    self.wait_test = True
                    self.stop_program = True
        elif self.select_model == "Label_check":
            self.step1 = False

            shanshan1 = cv2.imread("point/5555.jpg")

            mychoose = QMessageBox.question(self, "warning", "Please Flip the model")
            if mychoose == 16384:

                # logging.info("DUT FOUND,start camera")
                # self.myuihand.textbox.emit("DUT FOUND,start camera")
                ekko1, shan1 = self.ekkoshan.get_image()
                # ekko1,shan1=ekkoshan.get_image()

                # self.shan=cv2.rotate(shan,cv2.ROTATE_180)
                # self.shan1 = shan1                                               ####verify#######
                self.shan1 = shanshan1  ####verify#######
                self.img_time = datetime.now().strftime("%Y%m%d%H%M%S")
                # cv2.imwrite(self.pciture_save+"//"+todaytime+"//"+self.scaninfo+"_"+self.img_time+".jpg",shan)

                # cv2.imwrite(self.pciture_save+"//"+todaytime+"//pic2.jpg",shan1)

                self.show_image_Label_check(self.shan1, "STEP 1")
                if self.step1 == True:
                    self.wait_test = True

                elif self.step1 == False:
                    logging.error(f"step1 test fail")
                    self.myuihand.textbox.emit("step1 test fail")

                    self.lineEdit_9.setText("Fail")

                    self.resultcolor("Fail")
                    self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                     self.lineEdit_5.text(),
                                     str(int(self.lineEdit_6.text()) + 1),

                                     "%.2f%%" % ((int(self.lineEdit_5.text())) / (
                                             int(self.lineEdit_4.text()) + 1) * 100))
                    try:

                        if self.sfis_choose == True:
                            self.mysfis.data_upload(self.thissn, self.data,
                                                    error="BDFA0")
                            logging.error("fail upload OK")
                            self.myuihand.textbox.emit("fail upload OK")
                    except Exception as e:
                        logging.error("step1 test fail,sfis upload fail")
                        self.myuihand.textbox.emit("step1 test fail,sfis upload fail")
                    self.wait_test = True

            elif mychoose == 65536:
                mychoose = QMessageBox.question(self, "Warning", "Yes for exit")
                if mychoose == 16384:
                    self.wait_test = True
                    self.stop_program = True

        elif self.select_model == "WP_check" or self.select_model == "C9105AXW_E":
            self.step1 = False
            self.step2 = False
            self.step3 = False
            self.step4 = False
            self.step5 = False
            self.step6 = False
            shanshan1 = cv2.imread("sample/C9105AXW_E/1.jpg")
            shanshan2 = cv2.imread("sample/C9105AXW_E/2.jpg")
            shanshan3 = cv2.imread("sample/C9105AXW_E/3.jpg")
            shanshan4 = cv2.imread("sample/C9105AXW_E/4.jpg")
            shanshan5 = cv2.imread("sample/C9105AXW_E/5.jpg")
            shanshan6 = cv2.imread("sample/C9105AXW_E/6.jpg")

            mychoose = QMessageBox.question(self, "STEP 1", "Please enter for test SETP 1")
            if mychoose == 16384:
                # logging.info("DUT FOUND,start camera")
                # self.myuihand.textbox.emit("DUT FOUND,start camera")
                ekko1, shan1 = self.ekkoshan.get_image()
                # ekko1,shan1=ekkoshan.get_image()

                # self.shan=cv2.rotate(shan,cv2.ROTATE_180)
                self.shan1 = shan1  ####verify#######
                self.shan1 = shanshan1  ####verify#######
                self.img_time = datetime.now().strftime("%Y%m%d%H%M%S")
                # cv2.imwrite(self.pciture_save+"//"+todaytime+"//"+self.scaninfo+"_"+self.img_time+".jpg",shan)

                # cv2.imwrite(self.pciture_save+"//"+todaytime+"//pic2.jpg",shan1)

                self.show_image_WP(self.shan1, "STEP 1")
                if self.step1 == True:
                    mychoose = QMessageBox.question(self, "STEP 2", "Please enter for test SETP 2")
                    if mychoose == 16384:
                        ekko2, shan2 = self.ekkoshan.get_image()
                        self.shan2 = shan2  ####verify#######
                        self.shan2 = shanshan2
                        self.img_time = datetime.now().strftime("%Y%m%d%H%M%S")
                        self.show_image_WP(self.shan2, "STEP 2")
                        if self.step2 == True:
                            mychoose = QMessageBox.question(self, "STEP 3", "Please enter for test SETP 3")
                            if mychoose == 16384:
                                ekko3, shan3 = self.ekkoshan.get_image()
                                self.shan3 = shan3  ####verify#######
                                self.shan3 = shanshan3
                                self.img_time = datetime.now().strftime("%Y%m%d%H%M%S")
                                self.show_image_WP(self.shan3, "STEP 3")
                                if self.step3 == True:
                                    mychoose = QMessageBox.question(self, "STEP 4", "Please enter for test SETP 4")
                                    if mychoose == 16384:
                                        ekko4, shan4 = self.ekkoshan.get_image()
                                        self.shan4 = shan4  ####verify#######
                                        self.shan4 = shanshan4
                                        self.img_time = datetime.now().strftime("%Y%m%d%H%M%S")
                                        self.show_image_WP(self.shan4, "STEP 4")
                                        if self.step4 == True:
                                            mychoose = QMessageBox.question(self, "STEP 5",
                                                                            "Please enter for test SETP 5")
                                            if mychoose == 16384:
                                                ekko5, shan5 = self.ekkoshan.get_image()
                                                self.shan5 = shan5  ####verify#######
                                                self.shan5 = shanshan5
                                                self.img_time = datetime.now().strftime("%Y%m%d%H%M%S")
                                                self.show_image_WP(self.shan5, "STEP 5")
                                                if self.step5 == True:
                                                    mychoose = QMessageBox.question(self, "STEP 6",
                                                                                    "Please enter for test SETP 6")
                                                    if mychoose == 16384:
                                                        ekko6, shan6 = self.ekkoshan.get_image()
                                                        self.shan6 = shan6  ####verify#######
                                                        self.shan6 = shanshan6
                                                        self.img_time = datetime.now().strftime("%Y%m%d%H%M%S")
                                                        self.show_image_WP(self.shan6, "STEP 6")
                                                        if self.step6 == True:
                                                            self.wait_test = True
                                                        elif self.step6 == False:
                                                            logging.error(f"save fail")
                                                            self.myuihand.textbox.emit("save fail")

                                                            self.lineEdit_9.setText("Fail")

                                                            self.resultcolor("Fail")
                                                            self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                                                             self.lineEdit_5.text(),
                                                                             str(int(self.lineEdit_6.text()) + 1),

                                                                             "%.2f%%" % ((
                                                                                             int(self.lineEdit_5.text())) / (
                                                                                                 int(self.lineEdit_4.text()) + 1) * 100))
                                                            if self.sfis_choose == True:
                                                                self.mysfis.data_upload(self.thissn, self.data,
                                                                                        error="BDFA01")
                                                            logging.error("fail upload OK")
                                                            self.myuihand.textbox.emit("fail upload OK")
                                                            self.wait_test = True
                                                    elif mychoose == 65536:
                                                        mychoose = QMessageBox.question(self, "Warning", "Yes for exit")
                                                        if mychoose == 16384:
                                                            self.wait_test = True
                                                            self.stop_program = True
                                                elif self.step5 == False:
                                                    logging.error(f"save fail")
                                                    self.myuihand.textbox.emit("save fail")

                                                    self.lineEdit_9.setText("Fail")

                                                    self.resultcolor("Fail")
                                                    self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                                                     self.lineEdit_5.text(),
                                                                     str(int(self.lineEdit_6.text()) + 1),

                                                                     "%.2f%%" % ((int(self.lineEdit_5.text())) / (
                                                                             int(self.lineEdit_4.text()) + 1) * 100))
                                                    if self.sfis_choose == True:
                                                        self.mysfis.data_upload(self.thissn, self.data,
                                                                                error="BDFA01")
                                                    logging.error("fail upload OK")
                                                    self.myuihand.textbox.emit("fail upload OK")
                                                    self.wait_test = True
                                            elif mychoose == 65536:
                                                mychoose = QMessageBox.question(self, "Warning", "Yes for exit")
                                                if mychoose == 16384:
                                                    self.wait_test = True
                                                    self.stop_program = True
                                        elif self.step4 == False:
                                            logging.error(f"save fail")
                                            self.myuihand.textbox.emit("save fail")

                                            self.lineEdit_9.setText("Fail")

                                            self.resultcolor("Fail")
                                            self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                                             self.lineEdit_5.text(),
                                                             str(int(self.lineEdit_6.text()) + 1),

                                                             "%.2f%%" % ((int(self.lineEdit_5.text())) / (
                                                                     int(self.lineEdit_4.text()) + 1) * 100))
                                            if self.sfis_choose == True:
                                                self.mysfis.data_upload(self.thissn, self.data,
                                                                        error="BDFA01")
                                            logging.error("fail upload OK")
                                            self.myuihand.textbox.emit("fail upload OK")
                                            self.wait_test = True
                                    elif mychoose == 65536:
                                        mychoose = QMessageBox.question(self, "Warning", "Yes for exit")
                                        if mychoose == 16384:
                                            self.wait_test = True
                                            self.stop_program = True
                                elif self.step3 == False:
                                    logging.error(f"model or sn check fail")
                                    self.myuihand.textbox.emit("model or sn check fail")

                                    self.lineEdit_9.setText("Fail")

                                    self.resultcolor("Fail")
                                    self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                                     self.lineEdit_5.text(),
                                                     str(int(self.lineEdit_6.text()) + 1),

                                                     "%.2f%%" % ((int(self.lineEdit_5.text())) / (
                                                             int(self.lineEdit_4.text()) + 1) * 100))
                                    if self.sfis_choose == True:
                                        self.mysfis.data_upload(self.thissn, self.data,
                                                                error="BDFA01")
                                    logging.error("fail upload OK")
                                    self.myuihand.textbox.emit("fail upload OK")
                                    self.wait_test = True
                            elif mychoose == 65536:
                                mychoose = QMessageBox.question(self, "Warning", "Yes for exit")
                                if mychoose == 16384:
                                    self.wait_test = True
                                    self.stop_program = True
                        elif self.step2 == False:
                            logging.error(f"save fail")
                            self.myuihand.textbox.emit("save fail")

                            self.lineEdit_9.setText("Fail")

                            self.resultcolor("Fail")
                            self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                             self.lineEdit_5.text(),
                                             str(int(self.lineEdit_6.text()) + 1),

                                             "%.2f%%" % ((int(self.lineEdit_5.text())) / (
                                                     int(self.lineEdit_4.text()) + 1) * 100))
                            if self.sfis_choose == True:
                                self.mysfis.data_upload(self.thissn, self.data,
                                                        error="BDFA01")
                            logging.error("fail upload OK")
                            self.myuihand.textbox.emit("fail upload OK")
                            self.wait_test = True
                    elif mychoose == 65536:
                        mychoose = QMessageBox.question(self, "Warning", "Yes for exit")
                        if mychoose == 16384:
                            self.wait_test = True
                            self.stop_program = True
                elif self.step1 == False:
                    logging.error(f"step1 test fail")
                    self.myuihand.textbox.emit("step1 test fail")

                    self.lineEdit_9.setText("Fail")

                    self.resultcolor("Fail")
                    self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                     self.lineEdit_5.text(),
                                     str(int(self.lineEdit_6.text()) + 1),

                                     "%.2f%%" % ((int(self.lineEdit_5.text())) / (
                                             int(self.lineEdit_4.text()) + 1) * 100))
                    try:

                        if self.sfis_choose == True:
                            self.mysfis.data_upload(self.thissn, self.data,
                                                    error="BDFA01")
                            logging.error("fail upload OK")
                            self.myuihand.textbox.emit("fail upload OK")
                    except Exception as e:
                        logging.error("step1 test fail,sfis upload fail")
                        self.myuihand.textbox.emit("step1 test fail,sfis upload fail")
                    self.wait_test = True

            elif mychoose == 65536:
                mychoose = QMessageBox.question(self, "Warning", "Yes for exit")
                if mychoose == 16384:
                    self.wait_test = True
                    self.stop_program = True

    def show_image(self, image_path):
        inference_img = []
        inference_label = []
        try:
            image_old = cv2.imread(image_path)

            for shape in self.model_point["shapes"]:
                label = shape['label']
                points = shape["points"]

                valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]

                y1, y2, x1, x2, label = valuelist
                cut_img = image_old[int(y1):int(y2), int(x1):int(x2)]
                # cv2.imwrite(label+".jpg",cut_img)
                inference_img.append(cut_img)
                inference_label.append(valuelist)

            inference_result = self.get_inference_result(inference_img)
            # print(inference_label)
            # print(inference_result)
            logging.error("inference finish")
            self.myuihand.textbox.emit("inference finish")
            for each_label in range(len(inference_label)):
                if inference_result[each_label] == "fail":
                    cv2.rectangle(image_old, (inference_label[each_label][2], inference_label[each_label][0]),
                                  (inference_label[each_label][3], inference_label[each_label][1]), (0, 0, 255), 10, 15)
                elif inference_result[each_label] != "fail":
                    if inference_result[each_label] in inference_label[each_label][4]:
                        cv2.rectangle(image_old, (inference_label[each_label][2], inference_label[each_label][0]),
                                      (inference_label[each_label][3], inference_label[each_label][1]), (0, 255, 0), 10,
                                      15)

            # cv2.rectangle(image_old, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 10, 15)
            if "fail" in inference_result:
                my_inference_result = "fail"
            elif "fail" not in inference_result:
                my_inference_result = "pass"
            cv2.imwrite("sample/Alula_H4.jpg", image_old)
            cv2.imwrite(
                self.pciture_save + "//" + todaytime + "//" + self.scaninfo + "_" + self.img_time + "_" + my_inference_result + ".jpg",
                image_old)
            check_result = True

            if check_result:
                self.tableWidget.horizontalHeader().setVisible(False)
                self.tableWidget.verticalHeader().setVisible(False)
                self.tableWidget.setRowCount(1)
                self.tableWidget.setColumnCount(1)

                self.tableWidget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
                self.tableWidget.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)

                image_1 = QPixmap("sample/Alula_H4.jpg")
                label = QLabel()
                image_1 = image_1.scaled(self.tableWidget.columnWidth(0), self.tableWidget.rowHeight(0),
                                         Qt.AspectRatioMode.IgnoreAspectRatio)
                label.setPixmap(image_1)
                self.tableWidget.setCellWidget(0, 0, label)
                # image_2 = QPixmap(self.pciture_save+"//MR65002.jpg")
                # label2 = QLabel()
                # image_2 = image_2.scaled(self.tableWidget.columnWidth(0), self.tableWidget.rowHeight(0),
                #                       Qt.AspectRatioMode.IgnoreAspectRatio)
                # label2.setPixmap(image_2)
                # self.tableWidget.setCellWidget(0, 1, label2)

                # self.lineEdit_9.setText(str(max_val))
                # if max_val < 0.92:
                if "fail" in inference_result:
                    self.resultcolor("Fail")
                    self.lineEdit_9.setText("Fail")
                    self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                     self.lineEdit_5.text(),
                                     str(int(self.lineEdit_6.text()) + 1),

                                     "%.2f%%" % ((int(self.lineEdit_5.text())) / (
                                                 int(self.lineEdit_4.text()) + 1) * 100))
                elif "fail" not in inference_result:
                    self.resultcolor("Pass")
                    self.lineEdit_9.setText("Pass")
                    self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                     str(int(self.lineEdit_5.text()) + 1),
                                     self.lineEdit_6.text(),

                                     "%.2f%%" % ((int(self.lineEdit_5.text()) + 1) / (
                                                 int(self.lineEdit_4.text()) + 1) * 100))
                logging.info(f"Save OK")
                self.myuihand.textbox.emit("Save OK")
                # 更新頁面count信息


        except Exception as e:
            logging.error(str(e))
            self.myuihand.textbox.emit(str(e))

    def show_image_MR6500(self, image_numpy):
        try:
            image_old = image_numpy

            for shape in self.barcode_point["shapes"]:
                label = shape['label']
                points = shape["points"]
                if label == "ISN":
                    valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]

                    y1, y2, x1, x2, label = valuelist
                    isn_img = image_old[int(y1):int(y2), int(x1):int(x2)]
                    break

            for shape in self.model_point["shapes"]:
                label = shape['label']
                points = shape["points"]
                if label == "CHECK":
                    valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]

                    y1, y2, x1, x2, label = valuelist
                    cut_img = image_old[int(y1):int(y2), int(x1):int(x2)]
                    break

            reader = ReadDataMatrixCode()
            reader.decode(isn_img)
            if reader.getISN()[0] == True:
                logging.info(f"Get isn OK")
                self.myuihand.textbox.emit("Get isn OK")
                mbsn = ((self.mysfis.get_sfis_SN(reader.getISN()[1])).split("\x7f")[2]).split(":")[1]
                self.mbsn = str(mbsn)
                self.lineEdit_8.setText(str(mbsn))
                liaohao = (self.mysfis.get_sfis_90(mbsn)).split("\x7f")[2]
                logging.info(f"Get 90 OK")
                self.myuihand.textbox.emit("Get 90 OK")
                sample_image = (cv2.imread("sample/" + liaohao + ".jpg"))[int(y1):int(y2), int(x1):int(x2)]
                sample_gray = cv2.cvtColor(sample_image, cv2.COLOR_BGR2GRAY)
                cut_gray = cv2.cvtColor(cut_img, cv2.COLOR_BGR2GRAY)

                hash_sample = self.pHash(sample_gray)
                hash_cut = self.pHash(cut_gray)
                max_val = self.cmHash(hash_sample, hash_cut)
                self.max_val = str(max_val)
                # print(n)

                sample_image_pil = Image.fromarray(cv2.cvtColor(sample_image, cv2.COLOR_BGR2RGB))
                cut_img_pil = Image.fromarray(cv2.cvtColor(cut_img, cv2.COLOR_BGR2RGB))
                sample_image_pil_gray = sample_image_pil.convert('L')
                cut_img_pil_gray = cut_img_pil.convert('L')
                diff = ImageChops.difference(sample_image_pil_gray, cut_img_pil_gray)
                # 统计差异的统计信息，计算整个图像或图像的部分区域的统计数据
                stat = ImageStat.Stat(diff)
                # 输出差异的平均值，值越大差异越大
                # print(stat.mean[0])#<br><br>输出：<br>39.72462890625

                # cv2.imwrite("source/MR6500_1.jpg", dst1)
                # cv2.imwrite("source/MR6500_2.jpg", dst2)

                # check_result = cv2.matchTemplate(cut_gray, sample_gray, cv2.TM_CCORR_NORMED)
                # # threshold = 0.9
                # # loc=np.where( result >=threshold)
                # min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(check_result)
                if max_val >= 0.85 and stat.mean[0] <= 30:
                    cv2.rectangle(image_old, (valuelist[2], valuelist[0]), (valuelist[3], valuelist[1]), (0, 255, 0),
                                  10, 15)
                    my_inference_result = "pass"
                elif max_val < 0.85 or stat.mean[0] > 30:
                    cv2.rectangle(image_old, (valuelist[2], valuelist[0]), (valuelist[3], valuelist[1]), (0, 0, 255),
                                  10, 15)
                    my_inference_result = "fail"
                cv2.imwrite("source/MR6500.jpg", image_old)
                cv2.imwrite(
                    self.pciture_save + "//" + todaytime + "//" + mbsn + "_" + self.img_time + "_" + my_inference_result + ".jpg",
                    image_old)
                check_result = True
                logging.info(f"check label OK")
                self.myuihand.textbox.emit("check label OK")

                if check_result:
                    self.tableWidget.horizontalHeader().setVisible(False)
                    self.tableWidget.verticalHeader().setVisible(False)
                    self.tableWidget.setRowCount(1)
                    self.tableWidget.setColumnCount(2)

                    self.tableWidget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
                    self.tableWidget.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)
                    image_1 = QPixmap("sample/" + liaohao + ".jpg")
                    label = QLabel()
                    image_1 = image_1.scaled(self.tableWidget.columnWidth(0), self.tableWidget.rowHeight(0),
                                             Qt.AspectRatioMode.IgnoreAspectRatio)
                    label.setPixmap(image_1)
                    self.tableWidget.setCellWidget(0, 0, label)
                    image_2 = QPixmap("source/MR6500.jpg")
                    label2 = QLabel()
                    image_2 = image_2.scaled(self.tableWidget.columnWidth(0), self.tableWidget.rowHeight(0),
                                             Qt.AspectRatioMode.IgnoreAspectRatio)
                    label2.setPixmap(image_2)
                    self.tableWidget.setCellWidget(0, 1, label2)

                    self.lineEdit_9.setText(str(max_val) + ";" + str(stat.mean[0]))

                    if my_inference_result == "fail":
                        self.resultcolor("Fail")
                        self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                         self.lineEdit_5.text(),
                                         str(int(self.lineEdit_6.text()) + 1),

                                         "%.2f%%" % ((int(self.lineEdit_5.text())) / (
                                                     int(self.lineEdit_4.text()) + 1) * 100))
                    elif my_inference_result == "pass":
                        self.resultcolor("Pass")
                        self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                         str(int(self.lineEdit_5.text()) + 1),
                                         self.lineEdit_6.text(),

                                         "%.2f%%" % ((int(self.lineEdit_5.text()) + 1) / (
                                                     int(self.lineEdit_4.text()) + 1) * 100))
                    logging.info(f"Save OK {self.mbsn}")
                    logging.info(f"check finish {self.max_val}")
                    logging.info(f"check finish {stat.mean[0]}")
                    self.myuihand.textbox.emit("Save OK")
                    # 更新頁面count信息
            elif reader.getISN()[0] == False:
                logging.error(f"Get isn fail")
                self.myuihand.textbox.emit("Get isn fail")

                self.lineEdit_9.setText("Fail")

                self.resultcolor("Fail")
                self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                 self.lineEdit_5.text(),
                                 str(int(self.lineEdit_6.text()) + 1),

                                 "%.2f%%" % ((int(self.lineEdit_5.text())) / (int(self.lineEdit_4.text()) + 1) * 100))

                # logging.info(f"Save OK {self.mbsn}")
                # logging.info(f"check finish {self.max_val}")
                # self.get_rightnow("Save OK")


        except Exception as e:
            logging.error(str(e))
            self.myuihand.textbox.emit(str(e))

    def show_image_HH4K(self, image_numpy):
        try:

            cv2.imwrite(self.pciture_save + "//" + todaytime + "//" + self.img_time + ".jpg", image_numpy)
            ok1 = json.load(open("point/step1.json", 'r', encoding="utf8"))
            ok2 = json.load(open("point/step2.json", 'r', encoding="utf8"))
            ok3 = json.load(open("point/step3.json", 'r', encoding="utf8"))
            ok4 = json.load(open("point/step4.json", 'r', encoding="utf8"))
            step1_result = []

            if self.step1 == False:
                sample_image = (cv2.imread("sample/step1.jpg"))

                for shape in ok1["shapes"]:

                    label = shape['label']

                    points = shape["points"]

                    valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]

                    y1, y2, x1, x2, label = valuelist
                    step1_hash, step1_pil, step1_color = self.HH4K_compare(sample_image, image_numpy, valuelist)
                    step1_color_sample = step1_color[0][0]
                    step1_color_cam = step1_color[1][0]

                    # print(int(self.HH4K.get("color_spec",False)),int(self.HH4K.get("pil_spec",False)))

                    if step1_pil <= int(self.HH4K.get("pil_spec", False)) and (
                            int(step1_color_sample) - int(self.HH4K.get("color_spec", False))) <= int(
                            step1_color_cam) <= (int(step1_color_sample) + int(self.HH4K.get("color_spec", False))):
                        # pass
                        step1_result.append("pass")
                        cv2.rectangle(image_numpy, (valuelist[2], valuelist[0]), (valuelist[3], valuelist[1]),
                                      (0, 255, 0), 10, 15)
                    elif step1_pil > int(self.HH4K.get("pil_spec", False)) or (
                            int(step1_color_sample) - int(self.HH4K.get("color_spec", False))) > int(
                            step1_color_cam) or int(step1_color_cam) > (
                            int(step1_color_sample) + int(self.HH4K.get("color_spec", False))):
                        step1_result.append("fail")
                        cv2.rectangle(image_numpy, (valuelist[2], valuelist[0]), (valuelist[3], valuelist[1]),
                                      (0, 0, 255), 10, 15)

                    step1_pil = str("{:.3f}".format(step1_pil))
                    logging.info(label + ";" + step1_pil + ";" + str(step1_color_sample) + ";" + str(step1_color_cam))

                cv2.imwrite("source/HH4K.jpg", image_numpy)
                # cv2.imwrite(self.pciture_save+"//"+todaytime+"//"+self.img_time+"_"+my_inference_result+".jpg",image_numpy)
                check_result = True
                logging.info(f"check PIC finish")
                self.myuihand.textbox.emit("check PIC finish")

                if "fail" not in step1_result:
                    my_inference_result = "pass"
                    cv2.imwrite(
                        self.pciture_save + "//" + todaytime + "//" + self.img_time + "_" + my_inference_result + ".jpg",
                        image_numpy)
                elif "fail" in step1_result:
                    my_inference_result = "fail"
                    cv2.imwrite(
                        self.pciture_save + "//" + todaytime + "//" + self.img_time + "_" + my_inference_result + ".jpg",
                        image_numpy)
                if check_result:
                    self.tableWidget.horizontalHeader().setVisible(False)
                    self.tableWidget.verticalHeader().setVisible(False)
                    self.tableWidget.setRowCount(1)
                    self.tableWidget.setColumnCount(2)

                    self.tableWidget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
                    self.tableWidget.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)
                    image_1 = QPixmap("sample/step1.jpg")
                    label = QLabel()
                    image_1 = image_1.scaled(self.tableWidget.columnWidth(0), self.tableWidget.rowHeight(0),
                                             Qt.AspectRatioMode.IgnoreAspectRatio)
                    label.setPixmap(image_1)
                    self.tableWidget.setCellWidget(0, 0, label)
                    image_2 = QPixmap("source/HH4K.jpg")
                    label2 = QLabel()
                    image_2 = image_2.scaled(self.tableWidget.columnWidth(0), self.tableWidget.rowHeight(0),
                                             Qt.AspectRatioMode.IgnoreAspectRatio)
                    label2.setPixmap(image_2)
                    self.tableWidget.setCellWidget(0, 1, label2)

                    self.lineEdit_9.setText(str(step1_color_sample) + ";" + str(step1_color_cam) + ";" + str(step1_pil))
                    # logging.info(str(step1_color_sample)+";"+str(step1_color_cam)+";"+str(step1_pil))

                    if my_inference_result == "fail":
                        self.resultcolor("Fail")
                        self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                         self.lineEdit_5.text(),
                                         str(int(self.lineEdit_6.text()) + 1),

                                         "%.2f%%" % ((int(self.lineEdit_5.text())) / (
                                                     int(self.lineEdit_4.text()) + 1) * 100))
                    elif my_inference_result == "pass":
                        self.resultcolor("Pass")
                        self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                         str(int(self.lineEdit_5.text()) + 1),
                                         self.lineEdit_6.text(),

                                         "%.2f%%" % ((int(self.lineEdit_5.text()) + 1) / (
                                                     int(self.lineEdit_4.text()) + 1) * 100))
                    # logging.info(f"Save OK {self.mbsn}")
                    # logging.info(f"check finish {self.max_val}")
                    # logging.info(f"check finish {stat.mean[0]}")
                    self.myuihand.textbox.emit("Save OK")

                self.step1 = True
            elif self.step1 != False and self.step2 == False:
                sample_image = (cv2.imread("sample/step2.jpg"))
                for shape in ok2["shapes"]:
                    label = shape['label']
                    points = shape["points"]

                    valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]

                    y1, y2, x1, x2, label = valuelist
                    step1_hash, step1_pil, step1_color = self.HH4K_compare(sample_image, image_numpy, valuelist)
                    step1_color_sample = step1_color[0][0]
                    step1_color_cam = step1_color[1][0]

                    if step1_pil <= int(self.HH4K.get("pil_spec", False)) and (
                            int(step1_color_sample) - int(self.HH4K.get("color_spec", False))) <= int(
                            step1_color_cam) <= (int(step1_color_sample) + int(self.HH4K.get("color_spec", False))):
                        # pass
                        step1_result.append("pass")
                        cv2.rectangle(image_numpy, (valuelist[2], valuelist[0]), (valuelist[3], valuelist[1]),
                                      (0, 255, 0), 10, 15)
                    else:
                        step1_result.append("fail")
                        cv2.rectangle(image_numpy, (valuelist[2], valuelist[0]), (valuelist[3], valuelist[1]),
                                      (0, 0, 255), 10, 15)

                    step1_pil = str("{:.3f}".format(step1_pil))
                    logging.info(label + ";" + step1_pil + ";" + str(step1_color_sample) + ";" + str(step1_color_cam))
                cv2.imwrite("source/HH4K.jpg", image_numpy)
                # cv2.imwrite(self.pciture_save+"//"+todaytime+"//"+self.img_time+"_"+my_inference_result+".jpg",image_numpy)
                check_result = True
                logging.info(f"check PIC finish")
                self.myuihand.textbox.emit("check PIC finish")

                if "fail" not in step1_result:
                    my_inference_result = "pass"
                    cv2.imwrite(
                        self.pciture_save + "//" + todaytime + "//" + self.img_time + "_" + my_inference_result + ".jpg",
                        image_numpy)
                elif "fail" in step1_result:
                    my_inference_result = "fail"
                    cv2.imwrite(
                        self.pciture_save + "//" + todaytime + "//" + self.img_time + "_" + my_inference_result + ".jpg",
                        image_numpy)
                if check_result:
                    self.tableWidget.horizontalHeader().setVisible(False)
                    self.tableWidget.verticalHeader().setVisible(False)
                    self.tableWidget.setRowCount(1)
                    self.tableWidget.setColumnCount(2)

                    self.tableWidget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
                    self.tableWidget.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)
                    image_1 = QPixmap("sample/step2.jpg")
                    label = QLabel()
                    image_1 = image_1.scaled(self.tableWidget.columnWidth(0), self.tableWidget.rowHeight(0),
                                             Qt.AspectRatioMode.IgnoreAspectRatio)
                    label.setPixmap(image_1)
                    self.tableWidget.setCellWidget(0, 0, label)
                    image_2 = QPixmap("source/HH4K.jpg")
                    label2 = QLabel()
                    image_2 = image_2.scaled(self.tableWidget.columnWidth(0), self.tableWidget.rowHeight(0),
                                             Qt.AspectRatioMode.IgnoreAspectRatio)
                    label2.setPixmap(image_2)
                    self.tableWidget.setCellWidget(0, 1, label2)

                    self.lineEdit_9.setText(str(step1_color_sample) + ";" + str(step1_color_cam) + ";" + str(step1_pil))
                    # logging.info(str(step1_color_sample)+";"+str(step1_color_cam)+";"+str(step1_pil))

                    if my_inference_result == "fail":
                        self.resultcolor("Fail")
                        self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                         self.lineEdit_5.text(),
                                         str(int(self.lineEdit_6.text()) + 1),

                                         "%.2f%%" % ((int(self.lineEdit_5.text())) / (
                                                     int(self.lineEdit_4.text()) + 1) * 100))
                    elif my_inference_result == "pass":
                        self.resultcolor("Pass")
                        self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                         str(int(self.lineEdit_5.text()) + 1),
                                         self.lineEdit_6.text(),

                                         "%.2f%%" % ((int(self.lineEdit_5.text()) + 1) / (
                                                     int(self.lineEdit_4.text()) + 1) * 100))
                    # logging.info(f"Save OK {self.mbsn}")
                    # logging.info(f"check finish {self.max_val}")
                    # logging.info(f"check finish {stat.mean[0]}")
                    self.myuihand.textbox.emit("Save OK")

                self.step2 = True
            elif self.step1 != False and self.step2 != False and self.step3 == False:
                sample_image = (cv2.imread("sample/step3.jpg"))
                for shape in ok3["shapes"]:
                    label = shape['label']
                    points = shape["points"]

                    valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]

                    y1, y2, x1, x2, label = valuelist
                    step1_hash, step1_pil, step1_color = self.HH4K_compare(sample_image, image_numpy, valuelist)
                    step1_color_sample = step1_color[0][0]
                    step1_color_cam = step1_color[1][0]

                    if step1_pil <= int(self.HH4K.get("pil_spec", False)) and (
                            int(step1_color_sample) - int(self.HH4K.get("color_spec", False))) <= int(
                            step1_color_cam) <= (int(step1_color_sample) + int(self.HH4K.get("color_spec", False))):
                        # pass
                        step1_result.append("pass")
                        cv2.rectangle(image_numpy, (valuelist[2], valuelist[0]), (valuelist[3], valuelist[1]),
                                      (0, 255, 0), 10, 15)
                    else:
                        step1_result.append("fail")
                        cv2.rectangle(image_numpy, (valuelist[2], valuelist[0]), (valuelist[3], valuelist[1]),
                                      (0, 0, 255), 10, 15)
                    step1_pil = str("{:.3f}".format(step1_pil))
                    logging.info(label + ";" + step1_pil + ";" + str(step1_color_sample) + ";" + str(step1_color_cam))
                cv2.imwrite("source/HH4K.jpg", image_numpy)
                # cv2.imwrite(self.pciture_save+"//"+todaytime+"//"+self.img_time+"_"+my_inference_result+".jpg",image_numpy)
                check_result = True
                logging.info(f"check PIC finish")
                self.myuihand.textbox.emit("check PIC finish")

                if "fail" not in step1_result:
                    my_inference_result = "pass"
                    cv2.imwrite(
                        self.pciture_save + "//" + todaytime + "//" + self.img_time + "_" + my_inference_result + ".jpg",
                        image_numpy)
                elif "fail" in step1_result:
                    my_inference_result = "fail"
                    cv2.imwrite(
                        self.pciture_save + "//" + todaytime + "//" + self.img_time + "_" + my_inference_result + ".jpg",
                        image_numpy)
                if check_result:
                    self.tableWidget.horizontalHeader().setVisible(False)
                    self.tableWidget.verticalHeader().setVisible(False)
                    self.tableWidget.setRowCount(1)
                    self.tableWidget.setColumnCount(2)

                    self.tableWidget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
                    self.tableWidget.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)
                    image_1 = QPixmap("sample/step3.jpg")
                    label = QLabel()
                    image_1 = image_1.scaled(self.tableWidget.columnWidth(0), self.tableWidget.rowHeight(0),
                                             Qt.AspectRatioMode.IgnoreAspectRatio)
                    label.setPixmap(image_1)
                    self.tableWidget.setCellWidget(0, 0, label)
                    image_2 = QPixmap("source/HH4K.jpg")
                    label2 = QLabel()
                    image_2 = image_2.scaled(self.tableWidget.columnWidth(0), self.tableWidget.rowHeight(0),
                                             Qt.AspectRatioMode.IgnoreAspectRatio)
                    label2.setPixmap(image_2)
                    self.tableWidget.setCellWidget(0, 1, label2)

                    self.lineEdit_9.setText(str(step1_color_sample) + ";" + str(step1_color_cam) + ";" + str(step1_pil))
                    # logging.info(str(step1_color_sample)+";"+str(step1_color_cam)+";"+str(step1_pil))

                    if my_inference_result == "fail":
                        self.resultcolor("Fail")
                        self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                         self.lineEdit_5.text(),
                                         str(int(self.lineEdit_6.text()) + 1),

                                         "%.2f%%" % ((int(self.lineEdit_5.text())) / (
                                                     int(self.lineEdit_4.text()) + 1) * 100))
                    elif my_inference_result == "pass":
                        self.resultcolor("Pass")
                        self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                         str(int(self.lineEdit_5.text()) + 1),
                                         self.lineEdit_6.text(),

                                         "%.2f%%" % ((int(self.lineEdit_5.text()) + 1) / (
                                                     int(self.lineEdit_4.text()) + 1) * 100))
                    # logging.info(f"Save OK {self.mbsn}")
                    # logging.info(f"check finish {self.max_val}")
                    # logging.info(f"check finish {stat.mean[0]}")
                    self.myuihand.textbox.emit("Save OK")
                self.step3 = True
            elif self.step1 != False and self.step2 != False and self.step3 != False and self.step4 == False:
                sample_image = (cv2.imread("sample/step4.jpg"))
                for shape in ok4["shapes"]:
                    label = shape['label']
                    points = shape["points"]

                    valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]

                    y1, y2, x1, x2, label = valuelist
                    step1_hash, step1_pil, step1_color = self.HH4K_compare(sample_image, image_numpy, valuelist)
                    step1_color_sample = step1_color[0][0]
                    step1_color_cam = step1_color[1][0]

                    if step1_pil <= int(self.HH4K.get("pil_spec", False)) and (
                            int(step1_color_sample) - int(self.HH4K.get("color_spec", False))) <= int(
                            step1_color_cam) <= (int(step1_color_sample) + int(self.HH4K.get("color_spec", False))):
                        # pass
                        step1_result.append("pass")
                        cv2.rectangle(image_numpy, (valuelist[2], valuelist[0]), (valuelist[3], valuelist[1]),
                                      (0, 255, 0), 10, 15)
                    else:
                        step1_result.append("fail")
                        cv2.rectangle(image_numpy, (valuelist[2], valuelist[0]), (valuelist[3], valuelist[1]),
                                      (0, 0, 255), 10, 15)
                    step1_pil = str("{:.3f}".format(step1_pil))
                    logging.info(label + ";" + step1_pil + ";" + str(step1_color_sample) + ";" + str(step1_color_cam))

                cv2.imwrite("source/HH4K.jpg", image_numpy)
                # cv2.imwrite(self.pciture_save+"//"+todaytime+"//"+self.img_time+"_"+my_inference_result+".jpg",image_numpy)
                check_result = True
                logging.info(f"check PIC finish")
                self.myuihand.textbox.emit("check PIC finish")

                if "fail" not in step1_result:
                    my_inference_result = "pass"
                    # cv2.imwrite(self.pciture_save+"//"+todaytime+"//"+self.img_time+"_"+my_inference_result+".jpg",image_numpy)
                elif "fail" in step1_result:
                    my_inference_result = "fail"
                    # cv2.imwrite(self.pciture_save+"//"+todaytime+"//"+self.img_time+"_"+my_inference_result+".jpg",image_numpy)
                if check_result:
                    self.tableWidget.horizontalHeader().setVisible(False)
                    self.tableWidget.verticalHeader().setVisible(False)
                    self.tableWidget.setRowCount(1)
                    self.tableWidget.setColumnCount(2)

                    self.tableWidget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
                    self.tableWidget.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)
                    image_1 = QPixmap("sample/step4.jpg")
                    label = QLabel()
                    image_1 = image_1.scaled(self.tableWidget.columnWidth(0), self.tableWidget.rowHeight(0),
                                             Qt.AspectRatioMode.IgnoreAspectRatio)
                    label.setPixmap(image_1)
                    self.tableWidget.setCellWidget(0, 0, label)
                    image_2 = QPixmap("source/HH4K.jpg")
                    label2 = QLabel()
                    image_2 = image_2.scaled(self.tableWidget.columnWidth(0), self.tableWidget.rowHeight(0),
                                             Qt.AspectRatioMode.IgnoreAspectRatio)
                    label2.setPixmap(image_2)
                    self.tableWidget.setCellWidget(0, 1, label2)

                    self.lineEdit_9.setText(str(step1_color_sample) + ";" + str(step1_color_cam) + ";" + str(step1_pil))
                    # logging.info(str(step1_color_sample)+";"+str(step1_color_cam)+";"+str(step1_pil))

                    if my_inference_result == "fail":
                        self.resultcolor("Fail")
                        self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                         self.lineEdit_5.text(),
                                         str(int(self.lineEdit_6.text()) + 1),

                                         "%.2f%%" % ((int(self.lineEdit_5.text())) / (
                                                     int(self.lineEdit_4.text()) + 1) * 100))
                    elif my_inference_result == "pass":
                        self.resultcolor("Pass")
                        self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                         str(int(self.lineEdit_5.text()) + 1),
                                         self.lineEdit_6.text(),

                                         "%.2f%%" % ((int(self.lineEdit_5.text()) + 1) / (
                                                     int(self.lineEdit_4.text()) + 1) * 100))
                    # logging.info(f"Save OK {self.mbsn}")
                    # logging.info(f"check finish {self.max_val}")
                    # logging.info(f"check finish {stat.mean[0]}")
                    self.myuihand.textbox.emit("Save OK")
                self.step4 = True

                input_dialog = QInputDialog(self)
                input_dialog.setInputMode(QInputDialog.TextInput)
                input_dialog.setWindowTitle('Label Input')
                input_dialog.setLabelText('please scan label:')

                input_dialog.setStyleSheet("""
                QLabel{
                font-size:20px;
                font-weight:bold;
                font-family:Arial;
                }
                QLineEdit{
                font-size:20px;
                font-weight:bold;
                font-family:Arial;
                }
                QPushButton{
                font-size:20px;
                font-weight:bold;
                font-family:Arial;
                }
                """)  # # border-style:solid;
                # border-color:black;
                # border-width:2px;

                a = ''
                input_dialog.setTextValue(a)
                # input_dialog.textValueChanged.connect('输入框 发生变化时 响应')
                input_dialog.setFixedSize(400, 400)  # 设置 输入对话框大小
                input_dialog.show()
                if input_dialog.exec_() == input_dialog.Accepted:
                    self.scaninfo = input_dialog.textValue()  # 点击ok 后 获取输入对话框内容
                    logging.info("Scan Label: " + self.scaninfo)  #
                    self.get_rightnow("Scan Label: " + self.scaninfo)
                    self.lineEdit_8.setText(self.scaninfo)
                    self.scan_sta = True
                    cv2.imwrite(
                        self.pciture_save + "//" + todaytime + "//" + self.scaninfo + "_" + self.img_time + "_" + my_inference_result + ".jpg",
                        image_numpy)
                else:
                    logging.error(f"Scan Label cancel")  # Scan失败
                    ctypes.windll.user32.MessageBoxW(0, "Scan Label cancel", 1)
                    self.wait_test = True
                    self.stop_program = True
        except Exception as e:
            logging.error(str(e))
            self.myuihand.textbox.emit(str(e))

    def yolov5_inference(self, yolo_name, yolo_list, yolo_img):
        try:
            if self.select_model == "SKY":
                myweights = "best.pt"
            elif self.select_model == "SKY_4G":
                myweights = "best_4G.pt"

            inference_step = []
            yolo_img = cv2.cvtColor(yolo_img, cv2.COLOR_GRAY2RGB)
            os.chdir(basicdir + '\\' + "yolov5" + '\\' + "classify")
            inference_result1 = predict_change.run(weights=myweights,
                                                   source=yolo_name,
                                                   imgsz=224)

            os.chdir(basicdir)
            logging.error("step inference finish")
            self.myuihand.textbox.emit("step inference finish")
            QApplication.processEvents()

            for each_label in range(len(yolo_list)):
                self.myuihand.textbox.emit(inference_result1[each_label])

                ii = inference_result1[each_label].split(",")
                iii = ii[0].split(" ")
                # if float(iii[1])>= 0.85:
                #     print(float(iii[1]),11)
                # finalresult.append(iii[0])

                if "NG" not in iii[0] and float(iii[1]) >= 0.85 and iii[0] in yolo_name[each_label]:
                    cv2.rectangle(yolo_img, (yolo_list[each_label][2], yolo_list[each_label][0]),
                                  (yolo_list[each_label][3], yolo_list[each_label][1]), (0, 255, 0), 10,
                                  15)
                    text1 = str(iii)
                    org = (int(yolo_list[each_label][2]), int(yolo_list[each_label][0]) - 50)
                    font = cv2.FONT_HERSHEY_SIMPLEX
                    fontScale = 2
                    color = (0, 255, 0)
                    thickness = 6
                    cv2.putText(yolo_img, text1, org, font, fontScale, color, thickness)

                    inference_step.append(True)
                else:  # iii[0]=="ng":
                    # if inference_result[each_label] in inference_label[each_label][4]:
                    cv2.rectangle(yolo_img, (yolo_list[each_label][2], yolo_list[each_label][0]),
                                  (yolo_list[each_label][3], yolo_list[each_label][1]), (0, 0, 255), 10,
                                  15)
                    text1 = str(iii)
                    org = (int(yolo_list[each_label][2]), int(yolo_list[each_label][0]) - 50)
                    font = cv2.FONT_HERSHEY_SIMPLEX
                    fontScale = 2
                    color = (0, 0, 255)
                    thickness = 6
                    cv2.putText(yolo_img, text1, org, font, fontScale, color, thickness)

                    inference_step.append(False)
            if False not in inference_step:
                cv2.imwrite(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_pass.jpg", yolo_img)
                return "Pass"
            elif False in inference_step:
                cv2.imwrite(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_fail.jpg", yolo_img)
                return "Fail"
        except Exception as e:
            logging.error(str(e))
            self.myuihand.textbox.emit(str(e))

    def cambrian_space(self, cambrian_result_list, cambrian_img, cambrian_label_list):
        try:
            AOI_inference_step = []
            cambrian_img = cv2.cvtColor(cambrian_img, cv2.COLOR_GRAY2RGB)

            for each_label in range(len(cambrian_label_list)):
                if cambrian_result_list[each_label] == "NG" or cambrian_result_list[each_label] != str(
                        cambrian_label_list[each_label][4]):

                    cv2.rectangle(cambrian_img,
                                  (cambrian_label_list[each_label][2], cambrian_label_list[each_label][0]),
                                  (cambrian_label_list[each_label][3], cambrian_label_list[each_label][1]), (0, 0, 255),
                                  10,
                                  15)
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
                                  (0, 255, 0), 10,
                                  15)
                    text1 = str(cambrian_result_list[each_label])
                    org = (
                        int(cambrian_label_list[each_label][2]), int(cambrian_label_list[each_label][0]) - 50)
                    font = cv2.FONT_HERSHEY_SIMPLEX
                    fontScale = 2
                    color = (0, 255, 0)
                    thickness = 6
                    cv2.putText(cambrian_img, text1, org, font, fontScale, color, thickness)
                    AOI_inference_step.append(True)

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
        try:
            AOI_inference_step = []
            cambrian_img = cv2.cvtColor(cambrian_img, cv2.COLOR_GRAY2RGB)

            for each_label in range(len(cambrian_label_list)):
                if cambrian_result_list[each_label] == "NG" or cambrian_result_list[each_label] != str(
                        cambrian_label_list[each_label][4]):

                    cv2.rectangle(cambrian_img,
                                  (cambrian_label_list[each_label][2], cambrian_label_list[each_label][0]),
                                  (cambrian_label_list[each_label][3], cambrian_label_list[each_label][1]), (0, 0, 255),
                                  10,
                                  15)
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
                                  (0, 255, 0), 10,
                                  15)
                    text1 = str(cambrian_result_list[each_label])
                    org = (
                        int(cambrian_label_list[each_label][2]), int(cambrian_label_list[each_label][0]) - 50)
                    font = cv2.FONT_HERSHEY_SIMPLEX
                    fontScale = 2
                    color = (0, 255, 0)
                    thickness = 6
                    cv2.putText(cambrian_img, text1, org, font, fontScale, color, thickness)
                    AOI_inference_step.append(True)

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

    def show_image_SKY(self, image_numpy, stepname):
        try:

            cv2.imwrite(self.pciture_save + "//" + todaytime + "//" + self.img_time + ".jpg", image_numpy)
            image_numpy = cv2.cvtColor(image_numpy, cv2.COLOR_BGR2GRAY)
            if stepname == "STEP 1":
                step1_check = []
                step1_check_draw = []

                if self.select_model == "SKY":
                    ok1 = json.load(open("point/SKY_barcode.json", 'r', encoding="utf8"))
                elif self.select_model == "SKY_4G":
                    ok1 = json.load(open("point/SKY_4G_barcode.json", 'r', encoding="utf8"))
                for shape in ok1["shapes"]:
                    label = shape['label']
                    points = shape["points"]
                    if label == "SN":
                        valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]
                        y1, y2, x1, x2, label = valuelist
                        cut_img = image_numpy[int(y1):int(y2), int(x1):int(x2)]
                    elif "mylar" in label or "rubber" in label:
                        valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]
                        y1, y2, x1, x2, label = valuelist
                        cut_img_step1 = image_numpy[int(y1):int(y2), int(x1):int(x2)]
                        step1_check_draw.append(valuelist)
                        step1_check.append(cut_img_step1)

                barcodes = pyzbar.decode(cut_img)
                barcode_list = []
                for barcode in barcodes:
                    # print(barcode)
                    barcode_data = barcode.data.decode("utf-8")
                    # print(barcode_data)
                    # if "PSZ" in barcode:
                    if barcode.type != "QRCODE":
                        barcode_list.append(barcode_data)
                    # if "74-" in barcode:
                    #     barcode_74.append(barcode_data)
                    # if "088972" in barcode:
                    #     barcode_upc.append(barcode_data)
                if len(barcode_list) != 4:
                    logging.error("barcode decode fail")
                    self.myuihand.textbox.emit("barcode decode fail")
                elif len(barcode_list) == 4:
                    self.checksn = True
                    self.thismodel = barcode_list[3]
                    self.thissn = barcode_list[1]
                    logging.info(f"barcode decode OK")
                    self.myuihand.textbox.emit("barcode decode OK")
                    print(self.thismodel, self.thissn)

                    self.lineEdit_8.setText(self.thissn)
                    # self.step1 = True
                    if self.sfis_choose == True:
                        ###修改复测次数
                        sfisreturn = self.mysfis.check_route(self.thissn)
                        if sfisreturn[0] == "0":
                            logging.info(f"check route FAIL")
                            self.myuihand.textbox.emit("check route FAIL")

                            print(sfisreturn)

                            if "[LF#:0]" in sfisreturn and "[REPAIR OF AOI take picture]" in sfisreturn:
                                sfisrepairreturn = self.mysfis.repair_SN(self.thissn)
                                if sfisrepairreturn[0] == "1":
                                    logging.info(f"first auto repair OK")
                                    self.myuihand.textbox.emit(f"first auto repair OK")
                                    self.check_result_OK = True
                                elif sfisrepairreturn[0] == "0":
                                    logging.info(f"first auto repair NG")
                                    self.myuihand.textbox.emit(f"first auto repair NG")
                                    self.check_result_OK = False
                            elif "[LF#:1]" in sfisreturn and "[REPAIR OF AOI take picture]" in sfisreturn:
                                sfisrepairreturn = self.mysfis.repair_SN(self.thissn)
                                if sfisrepairreturn[0] == "1":
                                    logging.info(f"second auto repair OK")
                                    self.myuihand.textbox.emit(f"second auto repair OK")
                                    self.check_result_OK = True
                                elif sfisrepairreturn[0] == "0":
                                    logging.info(f"second auto repair NG")
                                    self.myuihand.textbox.emit(f"second auto repair NG")
                                    self.check_result_OK = False


                        elif sfisreturn[0] == "1":
                            logging.info(f"check route OK")
                            self.myuihand.textbox.emit("check route OK")
                            self.check_result_OK = True

                        # if (self.mysfis.check_route(self.thissn))[0]=="0":
                        #     logging.info(f"check route FAIL")
                        #     self.myuihand.textbox.emit("check route FAIL")
                        # elif (self.mysfis.check_route(self.thissn))[0]=="1":
                        #     logging.info(f"check route OK")
                        #     self.myuihand.textbox.emit("check route OK")
                        if self.check_result_OK:
                            logging.info("label model get:" + self.thismodel)
                            self.myuihand.textbox.emit("label model get:" + self.thismodel)
                            logging.info("label sn get:" + self.thissn)
                            self.myuihand.textbox.emit("label sn get:" + self.thissn)

                            # self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + ".jpg",6,1)
                            # self.lineEdit_8.setText(self.thissn)
                            inference_result = self.get_inference_result(step1_check)
                            logging.error("inference finish")
                            self.myuihand.textbox.emit("inference finish")
                            yolo_step1 = self.cambrian_space(inference_result, image_numpy, step1_check_draw)
                            if yolo_step1 == "Pass":
                                self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_pass.jpg",
                                             6, 1)
                                self.step1 = True
                            elif yolo_step1 == "Fail":
                                self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_fail.jpg",
                                             6, 1)
                                self.step1 = False  ##!!!!!!!!!改回

                    elif self.sfis_choose == False:
                        logging.info(f"check route bypass")
                        self.myuihand.textbox.emit("check route bypass")
                        logging.info("label model get:" + self.thismodel)
                        self.myuihand.textbox.emit("label model get:" + self.thismodel)
                        logging.info("label sn get:" + self.thissn)
                        self.myuihand.textbox.emit("label sn get:" + self.thissn)

                        # self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + ".jpg",6,1)
                        # self.lineEdit_8.setText(self.thissn)
                        inference_result1 = self.get_inference_result(step1_check)
                        logging.error("inference finish")
                        self.myuihand.textbox.emit("inference finish")
                        yolo_step1 = self.cambrian_space(inference_result1, image_numpy, step1_check_draw)
                        if yolo_step1 == "Pass":
                            self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_pass.jpg",
                                         6, 1)
                            self.step1 = True
                        elif yolo_step1 == "Fail":
                            self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_fail.jpg",
                                         6, 1)
                            self.step1 = False  ##!!!!!!!!!改回


            elif self.step2 == True and stepname == "STEP 3":
                step3_check = []
                step3_check_draw = []
                if self.select_model == "SKY":
                    ok3 = json.load(open("point/SKY_model2.json", 'r', encoding="utf8"))
                elif self.select_model == "SKY_4G":
                    ok3 = json.load(open("point/SKY_4G_model2.json", 'r', encoding="utf8"))

                for shape in ok3["shapes"]:
                    label = shape['label']
                    points = shape["points"]
                    if label == "model":
                        valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]
                        y1, y2, x1, x2, label = valuelist
                        cut_img = image_numpy[int(y1):int(y2), int(x1):int(x2)]
                        cv2.imwrite("source/model.jpg", cut_img)
                    elif label == "topsn":
                        valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]
                        y1, y2, x1, x2, label = valuelist
                        cut_img1 = image_numpy[int(y1):int(y2), int(x1):int(x2)]
                        cv2.imwrite("source/topsn.jpg", cut_img1)
                    elif "screw_big" in label:
                        valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]
                        y1, y2, x1, x2, label = valuelist
                        cut_img_step3 = image_numpy[int(y1):int(y2), int(x1):int(x2)]
                        cv2.imwrite("yolov5/classify/" + label + ".jpg", cut_img_step3)
                        step3_check_draw.append(valuelist)
                        step3_check.append(cut_img_step3)
                    elif "screw_yellow" in label:
                        valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]
                        y1, y2, x1, x2, label = valuelist
                        cut_img_step3 = image_numpy[int(y1):int(y2), int(x1):int(x2)]
                        cv2.imwrite("yolov5/classify/" + label + ".jpg", cut_img_step3)
                        step3_check_draw.append(valuelist)
                        step3_check.append(cut_img_step3)
                    elif "sim" in label:
                        valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]
                        y1, y2, x1, x2, label = valuelist
                        cut_img_step3 = image_numpy[int(y1):int(y2), int(x1):int(x2)]
                        cv2.imwrite("yolov5/classify/" + label + ".jpg", cut_img_step3)
                        step3_check_draw.append(valuelist)
                        step3_check.append(cut_img_step3)

                ocr = PaddleOCR(use_gpu=False, use_angle_cls=True,
                                lang="ch", )  # need to run only once to download and load model into memory

                img_path = "source/model.jpg"
                img_path1 = "source/topsn.jpg"
                # img_path="2.jpg"
                result = ocr.ocr(img_path, cls=True)

                if result != [[]]:
                    # result1 = ocr1.ocr(img_path, cls=True)
                    # img=cv2.imread("model.jpg")
                    # time.sleep(3)
                    for line in result[0]:
                        self.getmodel = str(line[1][0])
                        logging.info("model get:" + self.getmodel)
                        self.myuihand.textbox.emit("model get:" + self.getmodel)
                        if self.getmodel in self.thismodel:
                            self.modelcheck = True
                            logging.info("model check ok")
                            self.myuihand.textbox.emit("model check ok")
                            # self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + ".jpg", 6, 3)
                            # self.step3 = True

                            result1 = ocr.ocr(img_path1, cls=True)
                            if result1 != [[]]:
                                for line in result1[0]:
                                    try:
                                        self.topsn = (str(line[1][0]).split(":"))[1]
                                    except Exception as e:
                                        self.topsn = (str(line[1][0]).split(":"))[0]
                                    logging.info("topsn get:" + self.topsn)
                                    self.myuihand.textbox.emit("topsn get:" + self.topsn)
                                    if self.thissn in self.topsn and self.modelcheck:
                                        self.sncheck = True
                                        logging.info("sn check ok")
                                        self.myuihand.textbox.emit("sn check ok")

                                        inference_result3 = self.get_inference_result(step3_check)
                                        logging.error("inference finish")
                                        self.myuihand.textbox.emit("inference finish")
                                        yolo_step3 = self.cambrian_space(inference_result3, image_numpy,
                                                                         step3_check_draw)
                                        if yolo_step3 == "Pass":
                                            self.UI_show(
                                                self.pciture_save + "//" + todaytime + "//" + self.img_time + "_pass.jpg",
                                                6, 3)
                                            self.step3 = True
                                        elif yolo_step3 == "Fail":
                                            self.UI_show(
                                                self.pciture_save + "//" + todaytime + "//" + self.img_time + "_fail.jpg",
                                                6, 3)
                                            self.step3 = False  ##!!!!!!!!!改回

                                    elif self.thissn != self.topsn or self.modelcheck:

                                        self.sncheck = False
                                        logging.info("sn check fail")
                                        self.myuihand.textbox.emit("sn check fail")
                        elif self.getmodel not in self.thismodel:

                            self.modelcheck = False
                            logging.info("model check fail")
                            self.myuihand.textbox.emit("model check fail")
            elif self.step1 == True and stepname == "STEP 2":
                step2_check = []
                step2_check_draw = []
                if self.select_model == "SKY":
                    ok2 = json.load(open("point/SKY_model1.json", 'r', encoding="utf8"))
                elif self.select_model == "SKY_4G":
                    ok2 = json.load(open("point/SKY_4G_model1.json", 'r', encoding="utf8"))

                for shape in ok2["shapes"]:
                    label = shape['label']
                    points = shape["points"]
                    if "screw" in label:
                        valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]
                        y1, y2, x1, x2, label = valuelist
                        cut_img_step2 = image_numpy[int(y1):int(y2), int(x1):int(x2)]
                        cv2.imwrite("yolov5/classify/" + label + ".jpg", cut_img_step2)
                        step2_check_draw.append(valuelist)
                        step2_check.append(cut_img_step2)
                inference_result2 = self.get_inference_result(step2_check)
                logging.error("inference finish")
                self.myuihand.textbox.emit("inference finish")
                yolo_step2 = self.cambrian_space(inference_result2, image_numpy,
                                                 step2_check_draw)

                if yolo_step2 == "Pass":
                    self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_pass.jpg", 6, 2)
                    logging.info("step2 check ok")
                    self.myuihand.textbox.emit("step2 check ok")
                    self.step2 = True
                elif yolo_step2 == "Fail":
                    self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_fail.jpg", 6, 2)
                    logging.info("step2 check fail")
                    self.myuihand.textbox.emit("step2 check fail")
                    self.step2 = False

            elif self.step3 == True and stepname == "STEP 4":
                step4_check = []
                step4_check_draw = []
                if self.select_model == "SKY":
                    ok4 = json.load(open("point/SKY_model3.json", 'r', encoding="utf8"))
                elif self.select_model == "SKY_4G":
                    ok4 = json.load(open("point/SKY_4G_model3.json", 'r', encoding="utf8"))

                for shape in ok4["shapes"]:
                    label = shape['label']
                    points = shape["points"]
                    if "screw" in label:
                        valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]
                        y1, y2, x1, x2, label = valuelist
                        cut_img_step4 = image_numpy[int(y1):int(y2), int(x1):int(x2)]
                        cv2.imwrite("yolov5/classify/" + label + ".jpg", cut_img_step4)
                        step4_check_draw.append(valuelist)
                        step4_check.append(cut_img_step4)
                inference_result4 = self.get_inference_result(step4_check)
                logging.error("inference finish")
                self.myuihand.textbox.emit("inference finish")
                yolo_step4 = self.cambrian_space(inference_result4, image_numpy,
                                                 step4_check_draw)
                if yolo_step4 == "Pass":
                    self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_pass.jpg", 6, 4)
                    logging.info("step4 check ok")
                    self.myuihand.textbox.emit("step4 check ok")
                    self.step4 = True
                elif yolo_step4 == "Fail":
                    self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_fail.jpg", 6, 4)
                    logging.info("step4 check fail")
                    self.myuihand.textbox.emit("step4 check fail")
                    self.step4 = False

            elif self.step4 == True and stepname == "STEP 5":
                self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + ".jpg", 6, 5)
                logging.info("picture save ok")
                self.myuihand.textbox.emit("picture save ok")
                self.step5 = True
            elif self.step5 == True and stepname == "STEP 6":
                step6_check = []
                step6_check_draw = []
                if self.select_model == "SKY":
                    ok6 = json.load(open("point/SKY_model5.json", 'r', encoding="utf8"))
                elif self.select_model == "SKY_4G":
                    ok6 = json.load(open("point/SKY_4G_model5.json", 'r', encoding="utf8"))

                for shape in ok6["shapes"]:
                    label = shape['label']
                    points = shape["points"]
                    if "screw" in label:
                        valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]
                        y1, y2, x1, x2, label = valuelist
                        cut_img_step6 = image_numpy[int(y1):int(y2), int(x1):int(x2)]
                        cv2.imwrite("yolov5/classify/" + label + ".jpg", cut_img_step6)
                        step6_check_draw.append(valuelist)
                        step6_check.append(cut_img_step6)
                inference_result6 = self.get_inference_result(step6_check)
                logging.error("inference finish")
                self.myuihand.textbox.emit("inference finish")
                yolo_step6 = self.cambrian_space(inference_result6, image_numpy,
                                                 step6_check_draw)
                if yolo_step6 == "Pass":
                    self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_pass.jpg", 6, 6)
                    logging.info("step6 check ok")
                    self.myuihand.textbox.emit("step6 check ok")

                    if self.checksn and self.modelcheck and self.sncheck:
                        self.lineEdit_9.setText(str(self.thismodel) + ";" + str(self.getmodel))
                        my_inference_result = "pass"

                    elif self.checksn == False or self.modelcheck == False or self.sncheck == False:
                        my_inference_result = "fail"

                    # if my_inference_result == "fail":
                    #     self.resultcolor("Fail")
                    #     self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                    #                      self.lineEdit_5.text(),
                    #                      str(int(self.lineEdit_6.text()) + 1),
                    #
                    #                      "%.2f%%" % ((int(self.lineEdit_5.text())) / (
                    #                                  int(self.lineEdit_4.text()) + 1) * 100))
                    if my_inference_result == "pass":
                        self.resultcolor("Pass")
                        self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                         str(int(self.lineEdit_5.text()) + 1),
                                         self.lineEdit_6.text(),

                                         "%.2f%%" % ((int(self.lineEdit_5.text()) + 1) / (
                                                 int(self.lineEdit_4.text()) + 1) * 100))
                    if self.sfis_choose == True:
                        self.mysfis.data_upload(self.thissn, self.data)

                        # logging.info(f"Save OK {self.mbsn}")
                        # logging.info(f"check finish {self.max_val}")
                        logging.info("sfis upload OK")
                        self.myuihand.textbox.emit("sfis upload OK")
                    cv2.imwrite(
                        self.pciture_save + "//" + todaytime + "//" + self.thissn + " ALL PASS " + self.img_time + ".jpg",
                        image_numpy)
                    logging.info(self.thissn + " all test PASS")
                    self.myuihand.textbox.emit(self.thissn + " all test PASS")

                    self.step6 = True

                elif yolo_step6 == "Fail":
                    self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_fail.jpg", 6, 6)
                    logging.info("step6 check fail")
                    self.myuihand.textbox.emit("step6 check fail")
                    self.step6 = False

        except Exception as e:
            logging.error(str(e))
            self.myuihand.textbox.emit(str(e))

    def show_image_SKY_yolo(self, image_numpy, stepname):
        try:

            cv2.imwrite(self.pciture_save + "//" + todaytime + "//" + self.img_time + ".jpg", image_numpy)
            image_numpy = cv2.cvtColor(image_numpy, cv2.COLOR_BGR2GRAY)
            if stepname == "STEP 1":
                step1_check = []
                step1_check_draw = []
                if self.select_model == "SKY":
                    ok1 = json.load(open("point/SKY_barcode.json", 'r', encoding="utf8"))
                elif self.select_model == "SKY_4G":
                    ok1 = json.load(open("point/SKY_4G_barcode.json", 'r', encoding="utf8"))
                for shape in ok1["shapes"]:
                    label = shape['label']
                    points = shape["points"]
                    if label == "SN":
                        valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]
                        y1, y2, x1, x2, label = valuelist
                        cut_img = image_numpy[int(y1):int(y2), int(x1):int(x2)]
                    elif "mylar" in label or "rubber" in label:
                        valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]
                        y1, y2, x1, x2, label = valuelist
                        cut_img_step1 = image_numpy[int(y1):int(y2), int(x1):int(x2)]
                        cv2.imwrite("yolov5/classify/" + label + ".jpg", cut_img_step1)
                        step1_check_draw.append(valuelist)
                        step1_check.append(label + ".jpg")

                barcodes = pyzbar.decode(cut_img)
                barcode_list = []
                for barcode in barcodes:
                    # print(barcode)
                    barcode_data = barcode.data.decode("utf-8")
                    # print(barcode_data)
                    # if "PSZ" in barcode:
                    if barcode.type != "QRCODE":
                        barcode_list.append(barcode_data)
                    # if "74-" in barcode:
                    #     barcode_74.append(barcode_data)
                    # if "088972" in barcode:
                    #     barcode_upc.append(barcode_data)
                if len(barcode_list) != 4:
                    logging.error("barcode decode fail")
                    self.myuihand.textbox.emit("barcode decode fail")
                elif len(barcode_list) == 4:
                    self.checksn = True
                    self.thismodel = barcode_list[3]
                    self.thissn = barcode_list[1]
                    logging.info(f"barcode decode OK")
                    self.myuihand.textbox.emit("barcode decode OK")
                    print(self.thismodel, self.thissn)

                    self.lineEdit_8.setText(self.thissn)
                    # self.step1 = True
                    if self.sfis_choose == True:
                        if (self.mysfis.check_route(self.thissn))[0] == "0":
                            logging.info(f"check route FAIL")
                            self.myuihand.textbox.emit("check route FAIL")
                        elif (self.mysfis.check_route(self.thissn))[0] == "1":
                            logging.info(f"check route OK")
                            self.myuihand.textbox.emit("check route OK")
                            logging.info("label model get:" + self.thismodel)
                            self.myuihand.textbox.emit("label model get:" + self.thismodel)
                            logging.info("label sn get:" + self.thissn)
                            self.myuihand.textbox.emit("label sn get:" + self.thissn)

                            # self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + ".jpg",6,1)
                            # self.lineEdit_8.setText(self.thissn)
                            yolo_step1 = self.yolov5_inference(step1_check, step1_check_draw, image_numpy)
                            if yolo_step1 == "Pass":
                                self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_pass.jpg",
                                             6, 1)
                                self.step1 = True
                            elif yolo_step1 == "Fail":
                                self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_fail.jpg",
                                             6, 1)
                                self.step1 = False
                    elif self.sfis_choose == False:
                        logging.info(f"check route bypass")
                        self.myuihand.textbox.emit("check route bypass")
                        logging.info("label model get:" + self.thismodel)
                        self.myuihand.textbox.emit("label model get:" + self.thismodel)
                        logging.info("label sn get:" + self.thissn)
                        self.myuihand.textbox.emit("label sn get:" + self.thissn)

                        # self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + ".jpg",6,1)
                        # self.lineEdit_8.setText(self.thissn)
                        yolo_step1 = self.yolov5_inference(step1_check, step1_check_draw, image_numpy)
                        if yolo_step1 == "Pass":
                            self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_pass.jpg", 6,
                                         1)
                            self.step1 = True
                        elif yolo_step1 == "Fail":
                            self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_fail.jpg", 6,
                                         1)
                            self.step1 = False  ##!!!!!!!!!改回


            elif self.step2 == True and stepname == "STEP 3":
                step3_check = []
                step3_check_draw = []
                if self.select_model == "SKY":
                    ok3 = json.load(open("point/SKY_model2.json", 'r', encoding="utf8"))
                elif self.select_model == "SKY_4G":
                    ok3 = json.load(open("point/SKY_4G_model2.json", 'r', encoding="utf8"))

                for shape in ok3["shapes"]:
                    label = shape['label']
                    points = shape["points"]
                    if label == "model":
                        valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]
                        y1, y2, x1, x2, label = valuelist
                        cut_img = image_numpy[int(y1):int(y2), int(x1):int(x2)]
                        cv2.imwrite("source/model.jpg", cut_img)
                    elif label == "topsn":
                        valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]
                        y1, y2, x1, x2, label = valuelist
                        cut_img1 = image_numpy[int(y1):int(y2), int(x1):int(x2)]
                        cv2.imwrite("source/topsn.jpg", cut_img1)
                    elif "screw_big" in label:
                        valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]
                        y1, y2, x1, x2, label = valuelist
                        cut_img_step3 = image_numpy[int(y1):int(y2), int(x1):int(x2)]
                        cv2.imwrite("yolov5/classify/" + label + ".jpg", cut_img_step3)
                        step3_check_draw.append(valuelist)
                        step3_check.append(label + ".jpg")
                    elif "screw_yellow" in label:
                        valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]
                        y1, y2, x1, x2, label = valuelist
                        cut_img_step3 = image_numpy[int(y1):int(y2), int(x1):int(x2)]
                        cv2.imwrite("yolov5/classify/" + label + ".jpg", cut_img_step3)
                        step3_check_draw.append(valuelist)
                        step3_check.append(label + ".jpg")
                    elif "sim" in label:
                        valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]
                        y1, y2, x1, x2, label = valuelist
                        cut_img_step3 = image_numpy[int(y1):int(y2), int(x1):int(x2)]
                        cv2.imwrite("yolov5/classify/" + label + ".jpg", cut_img_step3)
                        step3_check_draw.append(valuelist)
                        step3_check.append(label + ".jpg")

                ocr = PaddleOCR(use_gpu=False, use_angle_cls=True,
                                lang="ch", )  # need to run only once to download and load model into memory

                img_path = "source/model.jpg"
                img_path1 = "source/topsn.jpg"
                # img_path="2.jpg"
                result = ocr.ocr(img_path, cls=True)

                if result != [[]]:
                    # result1 = ocr1.ocr(img_path, cls=True)
                    # img=cv2.imread("model.jpg")
                    # time.sleep(3)
                    for line in result[0]:
                        self.getmodel = str(line[1][0])
                        logging.info("model get:" + self.getmodel)
                        self.myuihand.textbox.emit("model get:" + self.getmodel)
                        if self.getmodel in self.thismodel:
                            self.modelcheck = True
                            logging.info("model check ok")
                            self.myuihand.textbox.emit("model check ok")
                            # self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + ".jpg", 6, 3)
                            # self.step3 = True

                            result1 = ocr.ocr(img_path1, cls=True)
                            if result1 != [[]]:
                                for line in result1[0]:
                                    try:
                                        self.topsn = (str(line[1][0]).split(":"))[1]
                                    except Exception as e:
                                        self.topsn = (str(line[1][0]).split(":"))[0]
                                    logging.info("topsn get:" + self.topsn)
                                    self.myuihand.textbox.emit("topsn get:" + self.topsn)
                                    if self.thissn in self.topsn and self.modelcheck:
                                        self.sncheck = True
                                        logging.info("sn check ok")
                                        self.myuihand.textbox.emit("sn check ok")
                                        yolo_step3 = self.yolov5_inference(step3_check, step3_check_draw, image_numpy)
                                        if yolo_step3 == "Pass":
                                            self.UI_show(
                                                self.pciture_save + "//" + todaytime + "//" + self.img_time + "_pass.jpg",
                                                6, 3)
                                            self.step3 = True
                                        elif yolo_step3 == "Fail":
                                            self.UI_show(
                                                self.pciture_save + "//" + todaytime + "//" + self.img_time + "_fail.jpg",
                                                6, 3)
                                            self.step3 = False  ##!!!!!!!!!改回

                                    elif self.thissn != self.topsn or self.modelcheck:

                                        self.sncheck = False
                                        logging.info("sn check fail")
                                        self.myuihand.textbox.emit("sn check fail")
                        elif self.getmodel not in self.thismodel:

                            self.modelcheck = False
                            logging.info("model check fail")
                            self.myuihand.textbox.emit("model check fail")
            elif self.step1 == True and stepname == "STEP 2":
                step2_check = []
                step2_check_draw = []
                if self.select_model == "SKY":
                    ok2 = json.load(open("point/SKY_model1.json", 'r', encoding="utf8"))
                elif self.select_model == "SKY_4G":
                    ok2 = json.load(open("point/SKY_4G_model1.json", 'r', encoding="utf8"))

                for shape in ok2["shapes"]:
                    label = shape['label']
                    points = shape["points"]
                    if "screw" in label:
                        valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]
                        y1, y2, x1, x2, label = valuelist
                        cut_img_step2 = image_numpy[int(y1):int(y2), int(x1):int(x2)]
                        cv2.imwrite("yolov5/classify/" + label + ".jpg", cut_img_step2)
                        step2_check_draw.append(valuelist)
                        step2_check.append(label + ".jpg")
                yolo_step2 = self.yolov5_inference(step2_check, step2_check_draw, image_numpy)
                if yolo_step2 == "Pass":
                    self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_pass.jpg", 6, 2)
                    logging.info("step2 check ok")
                    self.myuihand.textbox.emit("step2 check ok")
                    self.step2 = True
                elif yolo_step2 == "Fail":
                    self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_fail.jpg", 6, 2)
                    logging.info("step2 check fail")
                    self.myuihand.textbox.emit("step2 check fail")
                    self.step2 = False

            elif self.step3 == True and stepname == "STEP 4":
                step4_check = []
                step4_check_draw = []
                if self.select_model == "SKY":
                    ok4 = json.load(open("point/SKY_model3.json", 'r', encoding="utf8"))
                elif self.select_model == "SKY_4G":
                    ok4 = json.load(open("point/SKY_4G_model3.json", 'r', encoding="utf8"))

                for shape in ok4["shapes"]:
                    label = shape['label']
                    points = shape["points"]
                    if "screw" in label:
                        valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]
                        y1, y2, x1, x2, label = valuelist
                        cut_img_step4 = image_numpy[int(y1):int(y2), int(x1):int(x2)]
                        cv2.imwrite("yolov5/classify/" + label + ".jpg", cut_img_step4)
                        step4_check_draw.append(valuelist)
                        step4_check.append(label + ".jpg")
                yolo_step4 = self.yolov5_inference(step4_check, step4_check_draw, image_numpy)
                if yolo_step4 == "Pass":
                    self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_pass.jpg", 6, 4)
                    logging.info("step4 check ok")
                    self.myuihand.textbox.emit("step4 check ok")
                    self.step4 = True
                elif yolo_step4 == "Fail":
                    self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_fail.jpg", 6, 4)
                    logging.info("step4 check fail")
                    self.myuihand.textbox.emit("step4 check fail")
                    self.step4 = False

            elif self.step4 == True and stepname == "STEP 5":
                self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + ".jpg", 6, 5)
                logging.info("picture save ok")
                self.myuihand.textbox.emit("picture save ok")
                self.step5 = True
            elif self.step5 == True and stepname == "STEP 6":
                step6_check = []
                step6_check_draw = []
                if self.select_model == "SKY":
                    ok6 = json.load(open("point/SKY_model5.json", 'r', encoding="utf8"))
                elif self.select_model == "SKY_4G":
                    ok6 = json.load(open("point/SKY_4G_model5.json", 'r', encoding="utf8"))

                for shape in ok6["shapes"]:
                    label = shape['label']
                    points = shape["points"]
                    if "screw" in label:
                        valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]
                        y1, y2, x1, x2, label = valuelist
                        cut_img_step6 = image_numpy[int(y1):int(y2), int(x1):int(x2)]
                        cv2.imwrite("yolov5/classify/" + label + ".jpg", cut_img_step6)
                        step6_check_draw.append(valuelist)
                        step6_check.append(label + ".jpg")
                yolo_step6 = self.yolov5_inference(step6_check, step6_check_draw, image_numpy)
                if yolo_step6 == "Pass":
                    self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_pass.jpg", 6, 6)
                    logging.info("step6 check ok")
                    self.myuihand.textbox.emit("step6 check ok")

                    if self.checksn and self.modelcheck and self.sncheck:
                        self.lineEdit_9.setText(str(self.thismodel) + ";" + str(self.getmodel))
                        my_inference_result = "pass"

                    elif self.checksn == False or self.modelcheck == False or self.sncheck == False:
                        my_inference_result = "fail"

                    # if my_inference_result == "fail":
                    #     self.resultcolor("Fail")
                    #     self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                    #                      self.lineEdit_5.text(),
                    #                      str(int(self.lineEdit_6.text()) + 1),
                    #
                    #                      "%.2f%%" % ((int(self.lineEdit_5.text())) / (
                    #                                  int(self.lineEdit_4.text()) + 1) * 100))
                    if my_inference_result == "pass":
                        self.resultcolor("Pass")
                        self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                         str(int(self.lineEdit_5.text()) + 1),
                                         self.lineEdit_6.text(),

                                         "%.2f%%" % ((int(self.lineEdit_5.text()) + 1) / (
                                                 int(self.lineEdit_4.text()) + 1) * 100))
                    if self.sfis_choose == True:
                        self.mysfis.data_upload(self.thissn, self.data)

                        # logging.info(f"Save OK {self.mbsn}")
                        # logging.info(f"check finish {self.max_val}")
                        logging.info("sfis upload OK")
                        self.myuihand.textbox.emit("sfis upload OK")
                    cv2.imwrite(
                        self.pciture_save + "//" + todaytime + "//" + self.thissn + " ALL PASS " + self.img_time + ".jpg",
                        image_numpy)
                    logging.info(self.thissn + " all test PASS")
                    self.myuihand.textbox.emit(self.thissn + " all test PASS")

                    self.step6 = True

                elif yolo_step6 == "Fail":
                    self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_fail.jpg", 6, 6)
                    logging.info("step6 check fail")
                    self.myuihand.textbox.emit("step6 check fail")
                    self.step6 = False

        except Exception as e:
            logging.error(str(e))
            self.myuihand.textbox.emit(str(e))

    def call_backlog(self, msg):
        self.ocr_8P_result = msg

    def call_backlog1(self, msg1):
        self.ocr1_8P_result = msg1

    def show_image_C1000_8FP_E_2G_L(self, image_numpy, stepname):
        try:

            cv2.imwrite(self.pciture_save + "//" + todaytime + "//" + self.img_time + ".jpg", image_numpy)
            image_numpy = cv2.cvtColor(image_numpy, cv2.COLOR_BGR2GRAY)

            if stepname == "STEP 1":
                self.step1_sfis = False
                self.step1_1 = False

                step1_check_draw = []
                for shape in self.barcode_point["shapes"]:
                    label = shape['label']
                    points = shape["points"]
                    if label == "warn":
                        valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]
                        y1, y2, x1, x2, label = valuelist
                        cut_img = image_numpy[int(y1):int(y2), int(x1):int(x2)]
                        step1_check_draw.append(valuelist)
                    elif "ocr" in label:
                        valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]
                        y1, y2, x1, x2, label = valuelist
                        cut_img_step1 = image_numpy[int(y1):int(y2), int(x1):int(x2)]

                        if self.select_model == "C1000-8P-2G-L" or self.select_model == "C1000-8T-2G-L":
                            if label == "ocr1" or label == "ocr2":
                                cut_img_step1 = cv2.rotate(cut_img_step1, cv2.ROTATE_90_COUNTERCLOCKWISE)

                        cv2.imwrite("source/8P/" + label + ".jpg", cut_img_step1)

                need_show2 = cv2.imread("source/8P/ocr1.jpg")
                if self.select_model == "C1000-8P-2G-L" or self.select_model == "C1000-8T-2G-L":
                    need_show1 = cv2.imread("source/8P/ocr3.jpg")

                    need_show3 = cv2.imread("source/8P/ocr2.jpg")
                elif self.select_model != "C1000-8P-2G-L" and self.select_model != "C1000-8T-2G-L":
                    need_show1 = cv2.imread("source/8P/ocr2.jpg")

                ##新增多进程部分
                self.myT = Runthread("source/8P/ocr1.jpg")
                self.thread = QThread(self)
                self.myT.moveToThread(self.thread)
                self._startThread.connect(self.myT.run)
                self.myT.signal.connect(self.call_backlog)

                if self.thread.isRunning():
                    return

                self.thread.start()
                self._startThread.emit()

                if self.select_model == "C1000-8P-2G-L" or self.select_model == "C1000-8T-2G-L":

                    self.myT1 = Runthread("source/8P/ocr2.jpg")
                    self.thread1 = QThread(self)
                    self.myT1.moveToThread(self.thread1)
                    self._startThread1.connect(self.myT1.run)
                    self.myT1.signal.connect(self.call_backlog1)

                    if self.thread1.isRunning():
                        return

                    self.thread1.start()
                    self._startThread1.emit()

                    logging.info("barcode OCR start")
                    self.myuihand.textbox.emit("barcode OCR start")
                    QApplication.processEvents()

                    ocr1 = PaddleOCR(use_angle_cls=True,
                                     lang="ch")  # need to run only once to download and load model into memory
                    # img_path = '20240923_162516.jpg'
                    result3 = ocr1.ocr("source/8P/ocr3.jpg", cls=True)

                    logging.info("barcode ocr finish")
                    self.myuihand.textbox.emit("barcode ocr finish")

                    QApplication.processEvents()

                # 主程序开始检测条码，多进程执行OCR识别
                barcodes = pyzbar.decode(cut_img_step1)
                barcode_list = []
                for barcode in barcodes:
                    # print(barcode)
                    barcode_data = barcode.data.decode("utf-8")
                    x, y, w, h = barcode.rect

                    # print('x=', x, 'y=', y, 'w=', w, 'h=', h)

                    # print(barcode_data)
                    # if "PSZ" in barcode:
                    if barcode.type != "QRCODE":
                        barcode_list.append(barcode_data)
                        # cut_img_step1 = cv2.cvtColor(cut_img_step1, cv2.COLOR_GRAY2RGB)
                        # cv2.rectangle(cut_img_step1, (x, y), (x + w, y + h), (0, 255, 0), 10,15)

                        cv2.rectangle(need_show1, (x, y), (x + w, y + h), (0, 255, 0), 10, 15)
                        #

                logging.info("barcode pyzbar finish")
                self.myuihand.textbox.emit("barcode pyzbar finish")
                logging.info(f"barcode pyzbar total {len(barcode_list)}", )
                self.myuihand.textbox.emit(f"barcode pyzbar total {len(barcode_list)}")
                QApplication.processEvents()

                if self.select_model == "C1000-8P-2G-L":
                    if len(barcode_list) == 4:
                        if (check_label_C1000_8P_2G_L[2] == barcode_list[0] and check_label_C1000_8P_2G_L[3] ==
                                barcode_list[1]
                                and len(("").join(barcode_list[2].split(":"))) == 12 and "PVN" in barcode_list[
                                    3] and len(barcode_list[3]) == 11):
                            logging.info("barcode check OK")
                            self.myuihand.textbox.emit("barcode check OK")
                            # cv2.imwrite(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_barcode_Pass.jpg",need_show1)
                            # self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_barcode_Pass.jpg", 6, 1)
                            QApplication.processEvents()
                            self.step1_1 = True
                            if self.sfis_choose == True:
                                liaohao = (self.mysfis.get_sfis_90(barcode_list[3])).split("\x7f")[2]
                                if model_and_90[liaohao] in barcode_list[1]:
                                    logging.info("SFIS check model OK")
                                    self.myuihand.textbox.emit("SFIS check model OK")
                                    self.step1_sfis = True
                                elif model_and_90[liaohao] not in barcode_list[1]:
                                    logging.info("SFIS check model fail")
                                    self.myuihand.textbox.emit("SFIS check model fail")

                        else:
                            logging.info("barcode check fail")
                            self.myuihand.textbox.emit("barcode check fail")
                    elif len(barcode_list) != 4:
                        logging.info("barcode pyzbar not enough")
                        self.myuihand.textbox.emit("barcode pyzbar not enough")
                elif self.select_model == "C1000-8T-2G-L":
                    if len(barcode_list) == 4:

                        if (check_label_C1000_8T_2G_L[2] == barcode_list[0] and check_label_C1000_8T_2G_L[3] ==
                                barcode_list[1]
                                and len(("").join(barcode_list[2].split(":"))) == 12 and "PVN" in barcode_list[
                                    3] and len(barcode_list[3]) == 11):
                            logging.info("barcode check OK")
                            self.myuihand.textbox.emit("barcode check OK")
                            # cv2.imwrite(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_barcode_Pass.jpg",
                            #             need_show1)
                            # self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_barcode_Pass.jpg",
                            #              6, 1)
                            QApplication.processEvents()
                            self.step1_1 = True
                            if self.sfis_choose == True:
                                liaohao = (self.mysfis.get_sfis_90(barcode_list[3])).split("\x7f")[2]
                                if model_and_90[liaohao] in barcode_list[1]:
                                    logging.info("SFIS check model OK")
                                    self.myuihand.textbox.emit("SFIS check model OK")
                                    self.step1_sfis = True
                                elif model_and_90[liaohao] not in barcode_list[1]:
                                    logging.info("SFIS check model fail")
                                    self.myuihand.textbox.emit("SFIS check model fail")
                        else:
                            self.step1_1 = False
                            logging.info("barcode check fail")
                            self.myuihand.textbox.emit("barcode check fail")
                    elif len(barcode_list) != 4:
                        logging.info("barcode pyzbar not enough")
                        self.myuihand.textbox.emit("barcode pyzbar not enough")

                elif self.select_model == "C1200-8FP-2G" or self.select_model == "C1200-8P-E-2G" or self.select_model == "C1200-8T-E-2G":
                    if len(barcode_list) == 4:

                        if self.select_model == "C1200-8FP-2G":
                            need_check_list = check_label_C1200_8FP_2G
                        elif self.select_model == "C1200-8P-E-2G":
                            need_check_list = check_label_C1200_8P_E_2G
                        elif self.select_model == "C1200-8T-E-2G":
                            need_check_list = check_label_C1200_8T_E_2G

                        if (need_check_list[0] == barcode_list[0] and need_check_list[1] == barcode_list[1]
                                and len(barcode_list[2]) == 12 and "PVN" in barcode_list[3] and len(
                                    barcode_list[3]) == 11):
                            logging.info("barcode check OK")
                            self.myuihand.textbox.emit("barcode check OK")
                            # cv2.imwrite(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_barcode_Pass.jpg",
                            #             need_show1)
                            # self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_barcode_Pass.jpg",
                            #              6, 1)
                            QApplication.processEvents()
                            self.step1_1 = True
                            if self.sfis_choose == True:
                                liaohao = (self.mysfis.get_sfis_90(barcode_list[3])).split("\x7f")[2]
                                if model_and_90[liaohao] in barcode_list[1]:
                                    logging.info("SFIS check model OK")
                                    self.myuihand.textbox.emit("SFIS check model OK")
                                    self.step1_sfis = True
                                elif model_and_90[liaohao] not in barcode_list[1]:
                                    logging.info("SFIS check model fail")
                                    self.myuihand.textbox.emit("SFIS check model fail")
                        else:
                            self.step1_1 = False
                            logging.info("barcode check fail")
                            self.myuihand.textbox.emit("barcode check fail")
                    elif len(barcode_list) != 4:
                        logging.info("barcode pyzbar not enough")
                        self.myuihand.textbox.emit("barcode pyzbar not enough")
                elif self.select_model == "C1300-8P-E-2G" or self.select_model == "C1300-8T-E-2G":
                    if len(barcode_list) == 5:

                        if self.select_model == "C1300-8P-E-2G":
                            need_check_list = check_label_C1300_8P_E_2G
                        elif self.select_model == "C1300-8T-E-2G":
                            need_check_list = check_label_C1300_8T_E_2G

                        if (need_check_list[0] == barcode_list[0] and need_check_list[1] == barcode_list[1] and
                                need_check_list[2] == barcode_list[2]
                                and len(barcode_list[3]) == 12 and "PVN" in barcode_list[4] and len(
                                    barcode_list[4]) == 11):
                            logging.info("barcode check OK")
                            self.myuihand.textbox.emit("barcode check OK")
                            # cv2.imwrite(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_barcode_Pass.jpg",
                            #             need_show1)
                            # self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_barcode_Pass.jpg",
                            #              6, 1)
                            QApplication.processEvents()
                            self.step1_1 = True
                            if self.sfis_choose == True:
                                liaohao = (self.mysfis.get_sfis_90(barcode_list[4])).split("\x7f")[2]
                                if model_and_90[liaohao] in barcode_list[1]:
                                    logging.info("SFIS check model OK")
                                    self.myuihand.textbox.emit("SFIS check model OK")
                                    self.step1_sfis = True
                                elif model_and_90[liaohao] not in barcode_list[1]:
                                    logging.info("SFIS check model fail")
                                    self.myuihand.textbox.emit("SFIS check model fail")
                        else:
                            self.step1_1 = False
                            logging.info("barcode check fail")
                            self.myuihand.textbox.emit("barcode check fail")
                    elif len(barcode_list) != 5:
                        logging.info("barcode pyzbar not enough")
                        self.myuihand.textbox.emit("barcode pyzbar not enough")

                for ttime in range(60):
                    if self.ocr_8P_result == []:
                        time.sleep(0.5)
                        self.myuihand.textbox.emit("ocr running,please wait")
                        QApplication.processEvents()
                    elif self.ocr_8P_result != []:
                        self.thread.quit()
                        self.thread.wait()
                        break

                if self.select_model == "C1000-8P-2G-L" or self.select_model == "C1000-8T-2G-L":
                    for ttime in range(60):
                        if self.ocr1_8P_result == []:
                            time.sleep(0.5)
                            self.myuihand.textbox.emit("ocr running,please wait")
                            QApplication.processEvents()
                        elif self.ocr1_8P_result != []:
                            self.thread1.quit()
                            self.thread1.wait()
                            break
                logging.info("label ocr finish")
                self.myuihand.textbox.emit("label ocr finish")
                QApplication.processEvents()
                if self.step1_1:

                    if self.select_model == "C1000-8P-2G-L" or self.select_model == "C1000-8T-2G-L":
                        if self.select_model == "C1000-8P-2G-L":
                            this_way_need_label = check_label_C1000_8P_2G_L
                            this_way_need_ocr = check_ocr_C1000_8P_2G_L
                            this_way_need_ocr_part1 = check_ocr_C1000_8P_2G_L_part1
                            this_way_need_ocr_part2 = check_ocr_C1000_8P_2G_L_part2
                        elif self.select_model == "C1000-8T-2G-L":
                            this_way_need_label = check_label_C1000_8T_2G_L
                            this_way_need_ocr = check_ocr_C1000_8T_2G_L
                            this_way_need_ocr_part1 = check_ocr_C1000_8T_2G_L_part1
                            this_way_need_ocr_part2 = check_ocr_C1000_8T_2G_L_part2

                        if this_way_need_label[0] == result3[0][-1][1][0] and this_way_need_label[1] == \
                                result3[0][-2][1][0]:

                            cv2.rectangle(need_show1, (int(result3[0][-1][0][0][0]), int(result3[0][-1][0][0][1])),
                                          (int(result3[0][-1][0][2][0]), int(result3[0][-1][0][2][1])), (0, 255, 0), 6,
                                          6)
                            cv2.rectangle(need_show1, (int(result3[0][-2][0][0][0]), int(result3[0][-2][0][0][1])),
                                          (int(result3[0][-2][0][2][0]), int(result3[0][-2][0][2][1])), (0, 255, 0), 6,
                                          6)
                            logging.info("barcode ocr3 OK")
                            self.myuihand.textbox.emit("barcode ocr3 OK")

                            cv2.imwrite(
                                self.pciture_save + "//" + todaytime + "//" + self.img_time + "_barcode_ocr3_Pass.jpg",
                                need_show1)
                            self.UI_show(
                                self.pciture_save + "//" + todaytime + "//" + self.img_time + "_barcode_ocr3_Pass.jpg",
                                6, 1)
                            QApplication.processEvents()
                            # check_8P_queue = Queue()
                            # for each_queue in this_way_need_ocr:
                            #     check_8P_queue.put(each_queue)
                            eeekko = 0
                            for eekko in range(len(this_way_need_ocr)):

                                for each_ocr_check in self.ocr_8P_result[0]:

                                    if each_ocr_check[1][0] != this_way_need_ocr[eekko]:
                                        continue
                                    elif each_ocr_check[1][0] == this_way_need_ocr[eekko]:
                                        eeekko = eeekko + 1
                                        cv2.rectangle(need_show2,
                                                      (int(each_ocr_check[0][0][0]), int(each_ocr_check[0][0][1])),
                                                      (int(each_ocr_check[0][2][0]), int(each_ocr_check[0][2][1])),
                                                      (0, 255, 0), 6, 3)
                                        logging.info(f"check ok,{this_way_need_ocr[eekko]}")
                                        self.myuihand.textbox.emit(f"check ok,{this_way_need_ocr[eekko]}")
                                        break
                            if eeekko == this_way_need_ocr_part1:
                                logging.info("barcode ocr1 OK")
                                self.myuihand.textbox.emit("barcode ocr1 OK")
                                cv2.imwrite(
                                    self.pciture_save + "//" + todaytime + "//" + self.img_time + "_barcode_ocr1_Pass.jpg",
                                    need_show2)
                                self.UI_show(
                                    self.pciture_save + "//" + todaytime + "//" + self.img_time + "_barcode_ocr1_Pass.jpg",
                                    6, 2)

                                eeeekko = 0
                                for eekkoo in range(this_way_need_ocr_part1, len(this_way_need_ocr)):
                                    if eekkoo != (len(this_way_need_ocr) - 1):
                                        for each_ocr1_check in self.ocr1_8P_result[0]:

                                            if each_ocr1_check[1][0] != this_way_need_ocr[eekkoo]:
                                                continue
                                            elif each_ocr1_check[1][0] == this_way_need_ocr[eekkoo]:
                                                eeeekko = eeeekko + 1
                                                cv2.rectangle(need_show3,
                                                              (int(each_ocr1_check[0][0][0]),
                                                               int(each_ocr1_check[0][0][1])),
                                                              (int(each_ocr1_check[0][2][0]),
                                                               int(each_ocr1_check[0][2][1])),
                                                              (0, 255, 0), 6, 3)
                                                logging.info(f"check ok,{this_way_need_ocr[eekkoo]}")
                                                self.myuihand.textbox.emit(f"check ok,{this_way_need_ocr[eekkoo]}")
                                                break
                                    elif eekkoo == (len(this_way_need_ocr) - 1):
                                        need_match = re.escape(this_way_need_ocr[eekkoo]) + r'\d{8}'

                                        for each_ocr1_check in self.ocr1_8P_result[0]:

                                            # print(each_ocr1_check[1][0])
                                            # print(eeeekko)

                                            if re.search(need_match, each_ocr1_check[1][0]):
                                                eeeekko = eeeekko + 1
                                                cv2.rectangle(need_show3,
                                                              (int(each_ocr1_check[0][0][0]),
                                                               int(each_ocr1_check[0][0][1])),
                                                              (int(each_ocr1_check[0][2][0]),
                                                               int(each_ocr1_check[0][2][1])),
                                                              (0, 255, 0), 6, 3)
                                                logging.info(
                                                    f"check ok,{re.search(need_match, each_ocr1_check[1][0]).group()}")
                                                self.myuihand.textbox.emit(
                                                    f"check ok,{re.search(need_match, each_ocr1_check[1][0]).group()}")
                                                break
                                            else:
                                                continue

                                            # if each_ocr1_check[1][0] != (this_way_need_ocr[eekkoo]+todaytimetodaytime):
                                            #     continue
                                            # elif each_ocr1_check[1][0] == (this_way_need_ocr[eekkoo]+todaytimetodaytime):
                                            #     eeeekko = eeeekko + 1
                                            #     cv2.rectangle(need_show3,
                                            #                   (int(each_ocr1_check[0][0][0]),
                                            #                    int(each_ocr1_check[0][0][1])),
                                            #                   (int(each_ocr1_check[0][2][0]),
                                            #                    int(each_ocr1_check[0][2][1])),
                                            #                   (0, 255, 0), 6, 3)
                                            #     logging.info(f"check ok,{(this_way_need_ocr[eekkoo]+todaytimetodaytime)}")
                                            #     self.myuihand.textbox.emit(
                                            #         f"check ok,{(this_way_need_ocr[eekkoo]+todaytimetodaytime)}")
                                            #     break

                                if eeeekko == this_way_need_ocr_part2:
                                    logging.info("barcode ocr2 OK")
                                    self.myuihand.textbox.emit("barcode ocr2 OK")
                                    cv2.imwrite(
                                        self.pciture_save + "//" + todaytime + "//" + self.img_time + "_barcode_ocr2_Pass.jpg",
                                        need_show3)
                                    self.UI_show(
                                        self.pciture_save + "//" + todaytime + "//" + self.img_time + "_barcode_ocr2_Pass.jpg",
                                        6, 3)

                                    # 需添加推论敢问标签
                                    cv2.imwrite(
                                        self.pciture_save + "//" + todaytime + "//" + self.img_time + "_step1_warn_Pass.jpg",
                                        cut_img)
                                    self.UI_show(
                                        self.pciture_save + "//" + todaytime + "//" + self.img_time + "_step1_warn_Pass.jpg",
                                        6, 4)
                                    self.SN_8P = barcode_list[-1]
                                    self.lineEdit_8.setText(self.SN_8P)
                                    # inference_result = self.get_inference_result(cut_img)
                                    # logging.error("inference finish")
                                    # self.myuihand.textbox.emit("inference finish")
                                    # yolo_step1=self.cambrian_space(inference_result,image_numpy,step1_check_draw)
                                    # if yolo_step1 == "Pass":
                                    #     self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_pass.jpg",
                                    #                  6, 5)
                                    #     self.step1 = True
                                    # elif yolo_step1 == "Fail":
                                    #     self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_fail.jpg",
                                    #                  6, 5)
                                    #     self.step1 = False  ##!!!!!!!!!改回
                                    if self.sfis_choose:
                                        if self.step1_sfis:
                                            self.step1 = True
                                    elif self.sfis_choose == False:
                                        self.step1 = True
                                elif eeeekko != this_way_need_ocr_part2:
                                    logging.info("barcode ocr2 fail")
                                    self.myuihand.textbox.emit("barcode ocr2 fail")

                            elif eeekko != this_way_need_ocr_part1:
                                logging.info("barcode ocr1 fail")
                                self.myuihand.textbox.emit("barcode ocr1 fail")
                        elif this_way_need_label[0] != result3[0][-1][1][0] or this_way_need_label[1] != \
                                result3[0][-2][1][0]:
                            logging.info("barcode ocr3 fail")
                            self.myuihand.textbox.emit("barcode ocr3 fail")

                    if self.select_model == "C1200-8FP-2G" or self.select_model == "C1200-8P-E-2G" or self.select_model == "C1200-8T-E-2G" or self.select_model == "C1300-8P-E-2G" or self.select_model == "C1300-8T-E-2G":
                        if self.select_model == "C1200-8FP-2G":
                            this_way_need_label = check_label_C1200_8FP_2G
                            this_way_need_ocr = check_ocr_C1200_8FP_2G
                        elif self.select_model == "C1200-8P-E-2G":
                            this_way_need_label = check_label_C1200_8P_E_2G
                            this_way_need_ocr = check_ocr_C1200_8P_E_2G
                        elif self.select_model == "C1200-8T-E-2G":
                            this_way_need_label = check_label_C1200_8T_E_2G
                            this_way_need_ocr = check_ocr_C1200_8T_E_2G
                        elif self.select_model == "C1300-8P-E-2G":
                            this_way_need_label = check_label_C1300_8P_E_2G
                            this_way_need_ocr = check_ocr_C1300_8P_E_2G
                        elif self.select_model == "C1300-8T-E-2G":
                            this_way_need_label = check_label_C1200_8T_E_2G
                            this_way_need_ocr = check_ocr_C1200_8T_E_2G

                            # check_8P_queue = Queue()
                            # for each_queue in this_way_need_ocr:
                            #     check_8P_queue.put(each_queue)

                        logging.info("barcode ocr3 bypass")
                        self.myuihand.textbox.emit("barcode ocr3 bypass")

                        cv2.imwrite(
                            self.pciture_save + "//" + todaytime + "//" + self.img_time + "_barcode_ocr3_Pass.jpg",
                            need_show1)
                        self.UI_show(
                            self.pciture_save + "//" + todaytime + "//" + self.img_time + "_barcode_ocr3_Pass.jpg",
                            6, 1)
                        QApplication.processEvents()
                        eeekko = 0
                        need_match = re.escape(this_way_need_ocr[0]) + r'\d{8}'
                        print(self.ocr_8P_result)
                        for each_ocr_check in self.ocr_8P_result[0]:
                            if re.search(need_match, each_ocr_check[1][0]):
                                eeekko = eeekko + 1
                                cv2.rectangle(need_show2,
                                              (int(each_ocr_check[0][0][0]), int(each_ocr_check[0][0][1])),
                                              (int(each_ocr_check[0][2][0]), int(each_ocr_check[0][2][1])),
                                              (0, 255, 0), 6, 3)
                                logging.info(
                                    f"check ok,{re.search(need_match, each_ocr_check[1][0]).group()}")
                                self.myuihand.textbox.emit(
                                    f"check ok,{re.search(need_match, each_ocr_check[1][0]).group()}")
                                break
                            else:
                                continue
                        if eeekko == 1:
                            logging.info("barcode ocr1 OK")
                            self.myuihand.textbox.emit("barcode ocr1 OK")
                            cv2.imwrite(
                                self.pciture_save + "//" + todaytime + "//" + self.img_time + "_barcode_ocr1_Pass.jpg",
                                need_show2)
                            self.UI_show(
                                self.pciture_save + "//" + todaytime + "//" + self.img_time + "_barcode_ocr1_Pass.jpg",
                                6, 3)

                            # if each_ocr1_check[1][0] != (this_way_need_ocr[eekkoo]+todaytimetodaytime):
                            #     continue
                            # elif each_ocr1_check[1][0] == (this_way_need_ocr[eekkoo]+todaytimetodaytime):
                            #     eeeekko = eeeekko + 1
                            #     cv2.rectangle(need_show3,
                            #                   (int(each_ocr1_check[0][0][0]),
                            #                    int(each_ocr1_check[0][0][1])),
                            #                   (int(each_ocr1_check[0][2][0]),
                            #                    int(each_ocr1_check[0][2][1])),
                            #                   (0, 255, 0), 6, 3)
                            #     logging.info(f"check ok,{(this_way_need_ocr[eekkoo]+todaytimetodaytime)}")
                            #     self.myuihand.textbox.emit(
                            #         f"check ok,{(this_way_need_ocr[eekkoo]+todaytimetodaytime)}")
                            #     break

                            # 需添加推论敢问标签
                            cv2.imwrite(
                                self.pciture_save + "//" + todaytime + "//" + self.img_time + "_step1_warn_Pass.jpg",
                                cut_img)
                            self.UI_show(
                                self.pciture_save + "//" + todaytime + "//" + self.img_time + "_step1_warn_Pass.jpg",
                                6, 4)
                            self.SN_8P = barcode_list[-1]
                            self.lineEdit_8.setText(self.SN_8P)
                            # inference_result = self.get_inference_result(cut_img)
                            # logging.error("inference finish")
                            # self.myuihand.textbox.emit("inference finish")
                            # yolo_step1=self.cambrian_space(inference_result,image_numpy,step1_check_draw)
                            # if yolo_step1 == "Pass":
                            #     self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_pass.jpg",
                            #                  6, 5)
                            #     self.step1 = True
                            # elif yolo_step1 == "Fail":
                            #     self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_fail.jpg",
                            #                  6, 5)
                            #     self.step1 = False  ##!!!!!!!!!改回
                            if self.sfis_choose:
                                if self.step1_sfis:
                                    self.step1 = True
                            elif self.sfis_choose == False:
                                self.step1 = True

                        elif eeekko != 1:
                            logging.info("barcode ocr1 fail")
                            self.myuihand.textbox.emit("barcode ocr1 fail")



                elif not self.step1_1:
                    self.step1 = False

            #         if self.sfis_choose ==  True:
            #             if (self.mysfis.check_route(self.thissn))[0]=="0":
            #                 logging.info(f"check route FAIL")
            #                 self.myuihand.textbox.emit("check route FAIL")
            #             elif (self.mysfis.check_route(self.thissn))[0]=="1":
            #                 logging.info(f"check route OK")
            #                 self.myuihand.textbox.emit("check route OK")
            #
            #
            #
            #         elif self.sfis_choose == False:
            #             logging.info(f"check route bypass")
            #             self.myuihand.textbox.emit("check route bypass")
            #
            elif self.step1 == True and stepname == "STEP 2":
                step2_check = []
                step2_check_draw = []
                need_topdate = False

                for shape in self.model_point["shapes"]:
                    label = shape['label']
                    points = shape["points"]
                    if "warn" in label:
                        valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]
                        y1, y2, x1, x2, label = valuelist
                        cut_img_step2 = image_numpy[int(y1):int(y2), int(x1):int(x2)]
                        step2_check_draw.append(valuelist)
                        step2_check.append(cut_img_step2)
                    elif "topdate" in label:
                        valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]
                        y1, y2, x1, x2, label = valuelist
                        cut_img = image_numpy[int(y1):int(y2), int(x1):int(x2)]
                        cv2.imwrite("source/8P/topdate.jpg", cut_img)
                        need_topdate = True
                if step2_check != []:
                    self.step2_1 = True
                    # inference_result2 = self.get_inference_result(step2_check)
                    # logging.error("inference finish")
                    # self.myuihand.textbox.emit("inference finish")
                    # yolo_step2 = self.cambrian_space(inference_result2, image_numpy,
                    #                                  step2_check_draw)
                    #
                    # if yolo_step2 == "Pass":
                    #     self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_pass.jpg", 6, 6)
                    #     logging.info("step2 check warn ok")
                    #     self.myuihand.textbox.emit("step2 check  warn ok")
                    #     self.step2_1 = True
                    # elif yolo_step2 == "Fail":
                    #     self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_fail.jpg", 6, 6)
                    #     logging.info("step2 check warn fail")
                    #     self.myuihand.textbox.emit("step2 check warn fail")
                    #     self.step2_1 = False
                elif step2_check == []:
                    logging.error("nothing need to check")
                    self.myuihand.textbox.emit("no nothing need to check")
                    self.step2_1 = True
                if need_topdate:
                    ocr_step2 = PaddleOCR(use_angle_cls=True,
                                          lang="ch")  # need to run only once to download and load model into memory
                    # img_path = '20240923_162516.jpg'
                    result_step2 = ocr_step2.ocr("source/8P/topdate.jpg", cls=True)

                    need_show4 = cv2.imread("source/8P/topdate.jpg")
                    # print(result_step2)

                    need_match_step2 = r'^\d{8}$'

                    if re.search(need_match_step2, result_step2[0][0][1][0]) and len(result_step2[0][0][1][0]) == 8:
                        cv2.rectangle(need_show4,
                                      (int(result_step2[0][0][0][0][0]),
                                       int(result_step2[0][0][0][0][1])),
                                      (int(result_step2[0][0][0][2][0]),
                                       int(result_step2[0][0][0][2][1])),
                                      (0, 255, 0), 6, 6)
                        logging.info(f"check ok,{result_step2[0][0][1][0]}")
                        self.myuihand.textbox.emit(
                            f"check ok,{result_step2[0][0][1][0]}")
                        self.step2_2 = True
                        cv2.imwrite(
                            self.pciture_save + "//" + todaytime + "_topdate_ocr_Pass.jpg",
                            need_show4)
                        self.UI_show(
                            self.pciture_save + "//" + todaytime + "_topdate_ocr_Pass.jpg",
                            6, 5)

                    else:
                        logging.error("check fail topdate")
                        self.myuihand.textbox.emit("check fail topdate")
                        self.step2_2 = False



                elif not need_topdate:
                    logging.error("no topdate need to check")
                    self.myuihand.textbox.emit("no topdate need to check")
                    self.step2_2 = True

                if self.step2_1 and self.step2_2:
                    logging.info(self.SN_8P + " all test PASS")
                    self.myuihand.textbox.emit(self.SN_8P + " all test PASS")
                    cv2.imwrite(
                        self.pciture_save + "//" + todaytime + "//" + self.SN_8P + "ALL PASS " + self.img_time + ".jpg",
                        image_numpy)
                    self.UI_show(
                        self.pciture_save + "//" + todaytime + "//" + self.SN_8P + "ALL PASS " + self.img_time + ".jpg",
                        6, 6)
                    self.resultcolor("Pass")
                    self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                     str(int(self.lineEdit_5.text()) + 1),
                                     self.lineEdit_6.text(),

                                     "%.2f%%" % ((int(self.lineEdit_5.text()) + 1) / (
                                             int(self.lineEdit_4.text()) + 1) * 100))
                    if self.sfis_choose == True:
                        self.mysfis.data_upload(self.thissn, self.data)
                        logging.info("sfis upload OK")
                        self.myuihand.textbox.emit("sfis upload OK")
                    self.step2 = True

                elif not self.step2_1:
                    logging.error("step2 check fail")
                    self.myuihand.textbox.emit("step2 check fail")
                    self.step2 = False


        except Exception as e:
            logging.error(str(e))
            self.myuihand.textbox.emit(str(e))

    def show_image_Button_check(self, image_numpy, stepname):
        try:

            cv2.imwrite(self.pciture_save + "//" + todaytime + "//" + self.img_time + ".jpg", image_numpy)
            image_numpy = cv2.cvtColor(image_numpy, cv2.COLOR_BGR2GRAY)
            if stepname == "STEP 1":
                step1_check = []
                step1_check_draw = []

                ok1 = json.load(open("point/Button_check_model.json", 'r', encoding="utf8"))

                for shape in ok1["shapes"]:
                    label = shape['label']
                    points = shape["points"]

                    if "ximian" in label:
                        valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]
                        y1, y2, x1, x2, label = valuelist
                        cut_img_step1 = image_numpy[int(y1):int(y2), int(x1):int(x2)]
                        step1_check_draw.append(valuelist)
                        step1_check.append(cut_img_step1)
                        # hash_suffix = hashlib.md5(name_without_ext.encode()).hexdigest()[:6]
                        cv2.imwrite(
                            self.pciture_save + "//" + todaytime + "//" + self.img_time + "_" + self.scaninfo + "_button_check_gray.jpg",
                            cut_img_step1)

                self.lineEdit_8.setText(self.scaninfo)
                # self.step1 = True
                if self.sfis_choose == True:
                    ###修改复测次数
                    self.sfisreturn = self.mysfis.check_route(self.scaninfo)
                    if self.sfisreturn[0] == "0":
                        logging.info(f"check route FAIL,{self.deviceshow},{self.sfisreturn}")
                        self.myuihand.textbox.emit(f"check route FAIL,{self.deviceshow},{self.sfisreturn}")

                        print(self.sfisreturn)
                        self.check_result_OK = False
                        if "[LF#:0]" in self.sfisreturn and "[REPAIR OF AOI take picture]" in self.sfisreturn:
                            sfisrepairreturn = self.mysfis.repair_SN(self.scaninfo)
                            if sfisrepairreturn[0] == "1":
                                logging.info(f"first auto repair OK")
                                self.myuihand.textbox.emit(f"first auto repair OK")
                                self.check_result_OK = True
                            elif sfisrepairreturn[0] == "0":
                                logging.info(f"first auto repair NG")
                                self.myuihand.textbox.emit(f"first auto repair NG")
                                self.check_result_OK = False
                        elif "[LF#:1]" in self.sfisreturn and "[REPAIR OF AOI take picture]" in self.sfisreturn:
                            sfisrepairreturn = self.mysfis.repair_SN(self.scaninfo)
                            if sfisrepairreturn[0] == "1":
                                logging.info(f"second auto repair OK")
                                self.myuihand.textbox.emit(f"second auto repair OK")
                                self.check_result_OK = True
                            elif sfisrepairreturn[0] == "0":
                                logging.info(f"second auto repair NG")
                                self.myuihand.textbox.emit(f"second auto repair NG")
                                self.check_result_OK = False


                    elif self.sfisreturn[0] == "1":
                        logging.info(f"check route OK,{self.deviceshow},{self.sfisreturn}")
                        self.myuihand.textbox.emit(f"check route OK,{self.deviceshow},{self.sfisreturn}")
                        self.check_result_OK = True

                    # if (self.mysfis.check_route(self.thissn))[0]=="0":
                    #     logging.info(f"check route FAIL")
                    #     self.myuihand.textbox.emit("check route FAIL")
                    # elif (self.mysfis.check_route(self.thissn))[0]=="1":
                    #     logging.info(f"check route OK")
                    #     self.myuihand.textbox.emit("check route OK")
                    if self.check_result_OK:

                        # self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + ".jpg",6,1)
                        # self.lineEdit_8.setText(self.thissn)
                        inference_result = self.get_inference_result(step1_check)

                        print(inference_result)

                        logging.error("inference finish")
                        self.myuihand.textbox.emit("inference finish")
                        yolo_step1 = self.cambrian_space(inference_result, image_numpy, step1_check_draw)
                        if yolo_step1 == "Pass":
                            self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_pass.jpg",
                                         1, 1)
                            logging.info(self.scaninfo + " all test PASS")
                            self.myuihand.textbox.emit(self.scaninfo + " all test PASS")
                            cv2.imwrite(
                                self.pciture_save + "//" + todaytime + "//" + self.scaninfo + "ALL PASS " + self.img_time + ".jpg",
                                image_numpy)
                            # self.UI_show(
                            #     self.pciture_save + "//" + todaytime + "//" + self.scaninfo + "ALL PASS " + self.img_time + ".jpg",
                            #     1, 1)

                            if self.sfis_choose == True:
                                thisupload = self.mysfis.data_upload(self.scaninfo, self.data)
                                if thisupload[0] == "1":
                                    logging.info(f"sfis upload OK,{thisupload}")
                                    self.myuihand.textbox.emit(f"sfis upload OK,{thisupload}")
                                    self.resultcolor("Pass")
                                    self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                                     str(int(self.lineEdit_5.text()) + 1),
                                                     self.lineEdit_6.text(),

                                                     "%.2f%%" % ((int(self.lineEdit_5.text()) + 1) / (
                                                             int(self.lineEdit_4.text()) + 1) * 100))
                                    self.step1 = True
                                elif thisupload[0] == "0":
                                    logging.info(f"sfis upload NG,{thisupload}")
                                    self.myuihand.textbox.emit(f"sfis upload NG,{thisupload}")
                                    self.step1 = False


                        elif yolo_step1 == "Fail":
                            self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_fail.jpg",
                                         1, 1)
                            self.step1 = False  ##!!!!!!!!!改回

                elif self.sfis_choose == False:
                    logging.info(f"check route bypass")
                    self.myuihand.textbox.emit("check route bypass")

                    # self.step1 = True
                    # self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + ".jpg",6,1)
                    # self.lineEdit_8.setText(self.thissn)
                    inference_result1 = self.get_inference_result(step1_check)

                    print(inference_result1)

                    logging.error("inference finish")
                    self.myuihand.textbox.emit("inference finish")
                    yolo_step1 = self.cambrian_space(inference_result1, image_numpy, step1_check_draw)
                    if yolo_step1 == "Pass":
                        self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_pass.jpg",
                                     1, 1)
                        logging.info(self.scaninfo + " all test PASS")
                        self.myuihand.textbox.emit(self.scaninfo + " all test PASS")
                        cv2.imwrite(
                            self.pciture_save + "//" + todaytime + "//" + self.scaninfo + "ALL PASS " + self.img_time + ".jpg",
                            image_numpy)
                        # self.UI_show(
                        #     self.pciture_save + "//" + todaytime + "//" + self.scaninfo + "ALL PASS " + self.img_time + ".jpg",
                        #     1, 1)
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
                        self.step1 = False  ##!!!!!!!!!改回
        except Exception as e:
            logging.error(str(e))
            self.myuihand.textbox.emit(str(e))

    def show_image_Label_check(self, image_numpy, stepname):
        try:
            self.thissn = self.scaninfo
            cv2.imwrite(
                self.pciture_save + "/" + todaytime + "//" + self.thissn + "_" + stepname + "_" + self.img_time + ".jpg",
                image_numpy)
            image_numpy = cv2.cvtColor(image_numpy, cv2.COLOR_BGR2GRAY)

            if stepname == "STEP 1":
                if self.sfis_choose == True:
                    print(self.thissn)
                    liaohao = (self.mysfis.get_sfis_90(self.thissn)).split("\x7f")[3].split("/")[0]
                    print(liaohao)

                    # ============================================================
                    # GÁN need_check DỰA TRÊN LIAOHAO
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
                        need_check = check_label_xe2
                    elif ("XENIA.4" in liaohao or "XENIA4" in liaohao):
                        self.eero_model = "M/N: XE01"
                        self.eero_model1 = "M/N: XEO1"
                        need_check = check_label_xe4
                    else:
                        logging.error(f"Unknown liaohao: {liaohao}")
                        self.myuihand.textbox.emit(f"Unknown liaohao: {liaohao}")
                        return

                    print(self.eero_model, self.eero_model1)
                    print(need_check)

                    step1_check = []
                    step1_check_draw = []
                    ok1 = self.barcode_point

                    for shape in ok1["shapes"]:
                        label = shape['label']
                        points = shape["points"]

                        if "1" in label or "2" in label or "3" in label or "4" in label or "5" in label or "6" in label:
                            valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]),
                                         label]
                            y1, y2, x1, x2, label = valuelist
                            cut_img_step1 = image_numpy[int(y1):int(y2), int(x1):int(x2)]
                            step1_check_draw.append(valuelist)
                            step1_check.append(cut_img_step1)
                            # cv2.imwrite(
                            #     self.pciture_save + "//" + todaytime + "//" + self.img_time + "_" + self.scaninfo + "_Dimension_check_gray.jpg",
                            #     cut_img_step1)

                        elif label == "model":
                            valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]),
                                         label]
                            y1, y2, x1, x2, label = valuelist
                            cut_img = image_numpy[int(y1):int(y2), int(x1):int(x2)]
                            cv2.imwrite("source/model.jpg", cut_img)

                    need_show1 = cv2.imread("source/model.jpg")
                    need_show2 = cv2.imread("source/XE04.jpg")

                    if self.cambrian_is_open:
                        self.lineEdit_8.setText(self.thissn)

                        if self.sfis_choose == True:
                            # ============================================================
                            # CHECK ROUTE
                            # ============================================================
                            self.sfisreturn = self.mysfis.check_route(self.thissn)
                            if self.sfisreturn[0] == "0":
                                logging.info(f"check route FAIL")
                                self.myuihand.textbox.emit("check route FAIL")

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
                                logging.info(f"check route OK")
                                self.myuihand.textbox.emit("check route OK")
                                self.check_result_OK = True

                            self.check_result_OK = True

                            if self.check_result_OK:
                                # ============================================================
                                # OCR
                                # ============================================================
                                ocr = PaddleOCR(use_gpu=False, use_angle_cls=True, lang="ch", )
                                img_path = "source/model.jpg"
                                result = ocr.ocr(img_path, cls=True)

                                # Khởi tạo giá trị mặc định
                                self.switch = ""
                                self.model = ""
                                self.power = ""
                                self.input = ""
                                self.output = ""
                                self.sn_check = ""

                                for each_result in result[0]:
                                    text_raw = each_result[1][0]
                                    print(text_raw)

                                    if "M/N:" in text_raw or "M/N" in text_raw:
                                        text = re.sub(r'\s+', '', text_raw)

                                        m = re.search(r'^(.*?)M/N', text, re.I)
                                        if m:
                                            self.switch = normalize_switch(m.group(1).replace("|", "").strip())
                                        else:
                                            self.switch = ""

                                        # idx = text.upper().find("M/N:")
                                        # if idx != -1:
                                        #     m_model = re.search(r'M/N\s*:\s*([A-Z0-9]+)', text, re.I)
                                        #     if m_model:
                                        #         self.model = normalize_model("M/N: " + m_model.group(1))
                                        # else:
                                        #     self.model = ""

                                        idx = text.upper().find("M/N:")

                                        if idx != -1:
                                            self.model = text[idx:idx + 8].upper()
                                        else:
                                            self.model = ""

                                        # power_text = text[idx + 9:] if idx != -1 else text
                                        # self.power = normalize_power(power_text.replace("|", "").strip())

                                        power_text = text[idx + 8:]

                                        self.power = normalize_power(power_text.replace("|", "").strip())

                                        print(f"Switch: '{self.switch}', Model: '{self.model}', Power: '{self.power}'")

                                    elif "Output" in text_raw or "0utput" in text_raw:
                                        # parts = text_raw.split("|")
                                        # if len(parts) >= 2:
                                        #     self.input = normalize_input(parts[0].strip())
                                        #     self.output = normalize_output(parts[1].strip())
                                        # else:
                                        #     self.output = normalize_output(text_raw.strip())
                                        # print(f"Input: '{self.input}', Output: '{self.output}'")
                                        output_match = re.search(r'[O0]utput', text_raw, re.I)
                                        if output_match:
                                            output_start = output_match.start()

                                            input_part = text_raw[:output_start].strip()

                                            if input_part:
                                                self.input = normalize_input(input_part)
                                            else:
                                                self.input = ""

                                            output_part = text_raw[output_start:].strip()
                                            self.output = normalize_output(output_part)

                                        else:
                                            self.input = ""
                                            self.output = normalize_output(text_raw.strip())

                                        print(f"Input: '{self.input}', Output: '{self.output}'")

                                    elif "S/N" in text_raw:
                                        self.sn_check = normalize_sn(text_raw)
                                        print(f"SN: '{self.sn_check}'")

                                # ============================================================
                                # KIỂM TRA (GỌN - DÙNG check_value)
                                # ============================================================
                                model_ok = check_value(self.model, need_check.get("model"))
                                switch_ok = check_value(self.switch, need_check.get("switch"))
                                input_ok = check_value(self.input, need_check.get("input"))
                                output_ok = check_value(self.output, need_check.get("output"))
                                power_ok = check_value(self.power, need_check.get("power"))
                                sn_ok = (self.thissn == self.sn_check)

                                print(f"Model: {model_ok}, Switch: {switch_ok}, "
                                      f"Input: {input_ok}, Output: {output_ok}, "
                                      f"Power: {power_ok}, SN: {sn_ok}")

                                # ============================================================
                                # XỬ LÝ PASS / FAIL
                                # ============================================================
                                if model_ok and switch_ok and input_ok and output_ok and power_ok and sn_ok:
                                    # ============================================================
                                    # PASS - Vẽ khung xanh
                                    # ============================================================
                                    if len(result[0]) >= 3:
                                        cv2.rectangle(need_show1,
                                                      (int(result[0][0][0][0][0]), int(result[0][0][0][0][1])),
                                                      (int(result[0][0][0][2][0]), int(result[0][0][0][2][1])),
                                                      (0, 255, 0), 6, 6)
                                        cv2.rectangle(need_show1,
                                                      (int(result[0][1][0][0][0]), int(result[0][1][0][0][1])),
                                                      (int(result[0][1][0][2][0]), int(result[0][1][0][2][1])),
                                                      (0, 255, 0), 6, 6)
                                        cv2.rectangle(need_show1,
                                                      (int(result[0][2][0][0][0]), int(result[0][2][0][0][1])),
                                                      (int(result[0][2][0][2][0]), int(result[0][2][0][2][1])),
                                                      (0, 255, 0), 6, 6)

                                    cv2.imwrite(
                                        self.pciture_save + "//" + todaytime + "//" + self.img_time + "_label_Pass.jpg",
                                        need_show1)
                                    self.UI_show(
                                        self.pciture_save + "//" + todaytime + "//" + self.img_time + "_label_Pass.jpg",
                                        3, 2)
                                    cv2.imwrite(
                                        self.pciture_save + "//" + todaytime + "//" + self.img_time + "_label1_Pass.jpg",
                                        need_show2)
                                    self.UI_show(
                                        self.pciture_save + "//" + todaytime + "//" + self.img_time + "_label1_Pass.jpg",
                                        3, 1)

                                    logging.info("content check OK")
                                    self.myuihand.textbox.emit("content check OK")

                                    # ============================================================
                                    # YOLO INFERENCE
                                    # ============================================================
                                    inference_result = self.get_inference_result(step1_check)
                                    logging.error("inference finish")
                                    self.myuihand.textbox.emit("inference finish")
                                    yolo_step1 = self.cambrian_space_SN(inference_result, image_numpy, step1_check_draw,
                                                                        self.thissn)

                                    if yolo_step1 == "Pass":
                                        self.UI_show(
                                            self.pciture_save + "//" + todaytime + "//" + self.thissn + "_" + self.img_time + "_pass.jpg",
                                            3, 3)
                                        logging.info("step1 check ok")
                                        self.myuihand.textbox.emit("step1 check ok")
                                        my_inference_result = "pass"

                                        if my_inference_result == "pass":
                                            self.resultcolor("Pass")
                                            self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                                             str(int(self.lineEdit_5.text()) + 1),
                                                             self.lineEdit_6.text(),
                                                             "%.2f%%" % ((int(self.lineEdit_5.text()) + 1) / (
                                                                     int(self.lineEdit_4.text()) + 1) * 100))

                                        if self.sfis_choose == True:
                                            self.mysfis.data_upload(self.thissn, self.data)
                                            logging.info("sfis upload OK")
                                            self.myuihand.textbox.emit("sfis upload OK")

                                        cv2.imwrite(
                                            self.pciture_save + "//" + todaytime + "//" + self.thissn + " ALL PASS " + self.img_time + ".jpg",
                                            image_numpy)
                                        logging.info(self.thissn + " all test PASS")
                                        self.myuihand.textbox.emit(self.thissn + " all test PASS")

                                        self.step1 = True

                                    elif yolo_step1 == "Fail":
                                        self.UI_show(
                                            self.pciture_save + "//" + todaytime + "//" + self.thissn + "_" + self.img_time + "_fail.jpg",
                                            3, 1)
                                        logging.info("step1 check fail")
                                        self.myuihand.textbox.emit("step1 check fail")
                                        self.step1 = False

                                else:
                                    # ============================================================
                                    # FAIL - Vẽ khung đỏ + lưu ảnh debug
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

                                    # Log chi tiết lỗi
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
                                    if not output_ok:
                                        error_details.append(
                                            f"Output: '{self.output}' (expected: {need_check.get('output')})")
                                    if not power_ok:
                                        error_details.append(
                                            f"Power: '{self.power}' (expected: {need_check.get('power')})")
                                    if not sn_ok:
                                        error_details.append(f"SN: '{self.sn_check}' (expected: '{self.thissn}')")

                                    error_msg = " | ".join(error_details)
                                    logging.error(f"content check FAIL: {error_msg}")
                                    self.myuihand.textbox.emit(f"content check FAIL: {error_msg}")
                                    self.step1 = False

                        elif self.sfis_choose == False:
                            # ============================================================
                            # BYPASS SFIS
                            # ============================================================
                            logging.info(f"check route bypass")
                            self.myuihand.textbox.emit("check route bypass")
                            inference_result1 = self.get_inference_result(step1_check)
                            print(inference_result1)
                            logging.error("inference finish")
                            self.myuihand.textbox.emit("inference finish")
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
                        self.step1 = True

        except Exception as e:
            logging.error(str(e))
            self.myuihand.textbox.emit(str(e))

    def show_image_WP(self, image_numpy, stepname):
        try:

            cv2.imwrite(self.pciture_save + "//" + todaytime + "//" + self.img_time + ".jpg", image_numpy)
            image_numpy = cv2.cvtColor(image_numpy, cv2.COLOR_BGR2GRAY)
            if stepname == "STEP 1":
                step1_check = []
                step1_check_draw = []
                ok1 = self.barcode_point
                # if self.select_model == "SKY" :
                #     ok1 = json.load(open("point/SKY_barcode.json", 'r', encoding="utf8"))
                # elif self.select_model == "SKY_4G":
                #     ok1 = json.load(open("point/SKY_4G_barcode.json", 'r', encoding="utf8"))
                for shape in ok1["shapes"]:
                    label = shape['label']
                    points = shape["points"]
                    if label == "WP_QR":
                        valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]
                        y1, y2, x1, x2, label = valuelist
                        cut_img = image_numpy[int(y1):int(y2), int(x1):int(x2)]

                    elif "WP_Label" in label or "WP_Screw" in label or "WP_Net" in label or "WP_PASS" in label or "Label" in label or "tem" in label:
                        valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]
                        y1, y2, x1, x2, label = valuelist
                        cut_img_step1 = image_numpy[int(y1):int(y2), int(x1):int(x2)]
                        step1_check_draw.append(valuelist)
                        step1_check.append(cut_img_step1)
                if self.select_model == "WP_check":
                    reader = ReadDataMatrixCode()
                    reader.decode(cut_img)
                    if reader.getISN()[0] == False:
                        logging.info(f"Get isn FAIL")
                        self.myuihand.textbox.emit("Get isn FAIL")
                        self.checksn = False
                    elif reader.getISN()[0] == True:
                        logging.info(f"Get isn OK")
                        self.myuihand.textbox.emit("Get isn OK")

                        self.checksn = True
                        self.thissn = ((reader.getISN())[1].split(";"))[0]
                elif self.select_model == "C9105AXW_E":
                    barcodes = pyzbar.decode(cut_img)
                    wp_barcode = barcodes[0].data.decode("utf-8")
                    pattern = re.escape("$SN:") + r'[0-9a-zA-Z]{11}'
                    if re.search(pattern, wp_barcode):
                        logging.info(f"Get isn OK")
                        self.myuihand.textbox.emit("Get isn OK")

                        self.checksn = True
                        self.thissn = ((re.search(pattern, wp_barcode).group()).split(":"))[1]
                    else:
                        logging.info(f"Get isn FAIL")
                        self.myuihand.textbox.emit("Get isn FAIL")
                        self.checksn = False
                # barcode_list = []
                # for barcode in barcodes:
                #     # print(barcode)
                #     barcode_data = barcode.data.decode("utf-8")
                #     # print(barcode_data)
                #     # if "PSZ" in barcode:
                #     # if barcode.type != "QRCODE":
                #     barcode_list.append(barcode_data)
                #     # if "74-" in barcode:
                #     #     barcode_74.append(barcode_data)
                #     # if "088972" in barcode:
                #     #     barcode_upc.append(barcode_data)
                # if len(barcode_list) !=1:
                #     logging.error("barcode decode fail")
                #     self.myuihand.textbox.emit("barcode decode fail")
                # elif len(barcode_list) ==1:
                #     self.checksn = True
                #     self.thissn=(barcode_list[0].split(";"))[0]

                if self.checksn:
                    # logging.info(f"barcode decode OK")
                    # self.myuihand.textbox.emit("barcode decode OK")
                    # print(self.thissn)

                    self.lineEdit_8.setText(self.thissn)
                    # self.step1 = True
                    if self.sfis_choose == True:
                        ###修改复测次数
                        sfisreturn = self.mysfis.check_route(self.thissn)
                        if sfisreturn[0] == "0":
                            logging.info(f"check route FAIL")
                            self.myuihand.textbox.emit("check route FAIL")

                            print(sfisreturn)

                            if "[LF#:0]" in sfisreturn and "[REPAIR OF AOI take picture]" in sfisreturn:
                                sfisrepairreturn = self.mysfis.repair_SN(self.thissn)
                                if sfisrepairreturn[0] == "1":
                                    logging.info(f"first auto repair OK")
                                    self.myuihand.textbox.emit(f"first auto repair OK")
                                    self.check_result_OK = True
                                elif sfisrepairreturn[0] == "0":
                                    logging.info(f"first auto repair NG")
                                    self.myuihand.textbox.emit(f"first auto repair NG")
                                    self.check_result_OK = False
                            elif "[LF#:1]" in sfisreturn and "[REPAIR OF AOI take picture]" in sfisreturn:
                                sfisrepairreturn = self.mysfis.repair_SN(self.thissn)
                                if sfisrepairreturn[0] == "1":
                                    logging.info(f"second auto repair OK")
                                    self.myuihand.textbox.emit(f"second auto repair OK")
                                    self.check_result_OK = True
                                elif sfisrepairreturn[0] == "0":
                                    logging.info(f"second auto repair NG")
                                    self.myuihand.textbox.emit(f"second auto repair NG")
                                    self.check_result_OK = False


                        elif sfisreturn[0] == "1":
                            logging.info(f"check route OK")
                            self.myuihand.textbox.emit("check route OK")
                            self.check_result_OK = True

                        # if (self.mysfis.check_route(self.thissn))[0]=="0":
                        #     logging.info(f"check route FAIL")
                        #     self.myuihand.textbox.emit("check route FAIL")
                        # elif (self.mysfis.check_route(self.thissn))[0]=="1":
                        #     logging.info(f"check route OK")
                        #     self.myuihand.textbox.emit("check route OK")
                        if self.check_result_OK:
                            logging.info("label sn get:" + self.thissn)
                            self.myuihand.textbox.emit("label sn get:" + self.thissn)

                            # self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + ".jpg",6,1)
                            # self.lineEdit_8.setText(self.thissn)
                            inference_result = self.get_inference_result(step1_check)
                            logging.error("inference finish")
                            self.myuihand.textbox.emit("inference finish")
                            yolo_step1 = self.cambrian_space(inference_result, image_numpy, step1_check_draw)
                            if yolo_step1 == "Pass":
                                self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_pass.jpg",
                                             6, 1)
                                self.step1 = True
                            elif yolo_step1 == "Fail":
                                self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_fail.jpg",
                                             6, 1)
                                self.step1 = False  ##!!!!!!!!!改回

                    elif self.sfis_choose == False:
                        logging.info(f"check route bypass")
                        self.myuihand.textbox.emit("check route bypass")
                        logging.info("label sn get:" + self.thissn)
                        self.myuihand.textbox.emit("label sn get:" + self.thissn)

                        # self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + ".jpg",6,1)
                        # self.lineEdit_8.setText(self.thissn)
                        inference_result1 = self.get_inference_result(step1_check)
                        logging.error("inference finish")
                        self.myuihand.textbox.emit("inference finish")
                        yolo_step1 = self.cambrian_space(inference_result1, image_numpy, step1_check_draw)
                        if yolo_step1 == "Pass":
                            self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_pass.jpg",
                                         6, 1)
                            self.step1 = True
                        elif yolo_step1 == "Fail":
                            self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_fail.jpg",
                                         6, 1)
                            self.step1 = False  ##!!!!!!!!!改回


            elif self.step2 == True and stepname == "STEP 3":
                step3_check = []
                step3_check_draw = []

                ok3 = json.load(open("point/WP_check_step3.json", 'r', encoding="utf8"))

                for shape in ok3["shapes"]:
                    label = shape['label']
                    points = shape["points"]

                    if "WP_Net" in label or "WP_PASS" in label:
                        valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]
                        y1, y2, x1, x2, label = valuelist
                        cut_img_step3 = image_numpy[int(y1):int(y2), int(x1):int(x2)]

                        step3_check_draw.append(valuelist)
                        step3_check.append(cut_img_step3)

                inference_result3 = self.get_inference_result(step3_check)
                logging.error("inference finish")
                self.myuihand.textbox.emit("inference finish")
                yolo_step3 = self.cambrian_space(inference_result3, image_numpy,
                                                 step3_check_draw)
                if yolo_step3 == "Pass":
                    self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_pass.jpg",
                                 6, 3)
                    self.step3 = True
                elif yolo_step3 == "Fail":
                    self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_fail.jpg",
                                 6, 3)
                    self.step3 = False  ##!!!!!!!!!改回



            elif self.step1 == True and stepname == "STEP 2":
                step2_check = []
                step2_check_draw = []
                ok2 = self.model_point

                for shape in ok2["shapes"]:
                    label = shape['label']
                    points = shape["points"]
                    if "WP_Logo" in label or "WP_PASS" in label:
                        valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]
                        y1, y2, x1, x2, label = valuelist
                        cut_img_step2 = image_numpy[int(y1):int(y2), int(x1):int(x2)]
                        step2_check_draw.append(valuelist)
                        step2_check.append(cut_img_step2)
                inference_result2 = self.get_inference_result(step2_check)
                logging.error("inference finish")
                self.myuihand.textbox.emit("inference finish")
                yolo_step2 = self.cambrian_space(inference_result2, image_numpy,
                                                 step2_check_draw)

                if yolo_step2 == "Pass":
                    self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_pass.jpg", 6, 2)
                    logging.info("step2 check ok")
                    self.myuihand.textbox.emit("step2 check ok")
                    self.step2 = True
                elif yolo_step2 == "Fail":
                    self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_fail.jpg", 6, 2)
                    logging.info("step2 check fail")
                    self.myuihand.textbox.emit("step2 check fail")
                    self.step2 = False

            elif self.step3 == True and stepname == "STEP 4":
                step4_check = []
                step4_check_draw = []

                ok4 = json.load(open("point/WP_check_step4.json", 'r', encoding="utf8"))

                for shape in ok4["shapes"]:
                    label = shape['label']
                    points = shape["points"]
                    if "WP_PASS" in label:
                        valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]
                        y1, y2, x1, x2, label = valuelist
                        cut_img_step4 = image_numpy[int(y1):int(y2), int(x1):int(x2)]
                        step4_check_draw.append(valuelist)
                        step4_check.append(cut_img_step4)
                inference_result4 = self.get_inference_result(step4_check)
                logging.error("inference finish")
                self.myuihand.textbox.emit("inference finish")
                yolo_step4 = self.cambrian_space(inference_result4, image_numpy,
                                                 step4_check_draw)
                if yolo_step4 == "Pass":
                    self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_pass.jpg", 6, 4)
                    logging.info("step4 check ok")
                    self.myuihand.textbox.emit("step4 check ok")
                    self.step4 = True
                elif yolo_step4 == "Fail":
                    self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_fail.jpg", 6, 4)
                    logging.info("step4 check fail")
                    self.myuihand.textbox.emit("step4 check fail")
                    self.step4 = False

            elif self.step4 == True and stepname == "STEP 5":
                step5_check = []
                step5_check_draw = []

                ok5 = json.load(open("point/WP_check_step5.json", 'r', encoding="utf8"))

                for shape in ok5["shapes"]:
                    label = shape['label']
                    points = shape["points"]
                    if "WP_PASS" in label:
                        valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]
                        y1, y2, x1, x2, label = valuelist
                        cut_img_step5 = image_numpy[int(y1):int(y2), int(x1):int(x2)]
                        step5_check_draw.append(valuelist)
                        step5_check.append(cut_img_step5)
                inference_result5 = self.get_inference_result(step5_check)
                logging.error("inference finish")
                self.myuihand.textbox.emit("inference finish")
                yolo_step5 = self.cambrian_space(inference_result5, image_numpy,
                                                 step5_check_draw)
                if yolo_step5 == "Pass":
                    self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_pass.jpg", 6, 5)
                    logging.info("step5 check ok")
                    self.myuihand.textbox.emit("step5 check ok")
                    self.step5 = True
                elif yolo_step5 == "Fail":
                    self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_fail.jpg", 6, 5)
                    logging.info("step5 check fail")
                    self.myuihand.textbox.emit("step5 check fail")
                    self.step5 = False

            elif self.step5 == True and stepname == "STEP 6":
                step6_check = []
                step6_check_draw = []

                ok6 = json.load(open("point/WP_check_step6.json", 'r', encoding="utf8"))

                for shape in ok6["shapes"]:
                    label = shape['label']
                    points = shape["points"]
                    if "WP_PASS" in label or "WP_USB" in label:
                        valuelist = [int(points[0][1]), int(points[1][1]), int(points[0][0]), int(points[1][0]), label]
                        y1, y2, x1, x2, label = valuelist
                        cut_img_step6 = image_numpy[int(y1):int(y2), int(x1):int(x2)]
                        step6_check_draw.append(valuelist)
                        step6_check.append(cut_img_step6)
                inference_result6 = self.get_inference_result(step6_check)
                logging.error("inference finish")
                self.myuihand.textbox.emit("inference finish")
                yolo_step6 = self.cambrian_space(inference_result6, image_numpy,
                                                 step6_check_draw)
                if yolo_step6 == "Pass":
                    self.UI_show(self.pciture_save + "//" + todaytime + "//" + self.img_time + "_pass.jpg", 6, 6)
                    logging.info("step6 check ok")
                    self.myuihand.textbox.emit("step6 check ok")
                    my_inference_result = "pass"

                    # if my_inference_result == "fail":
                    #     self.resultcolor("Fail")
                    #     self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                    #                      self.lineEdit_5.text(),
                    #                      str(int(self.lineEdit_6.text()) + 1),
                    #
                    #                      "%.2f%%" % ((int(self.lineEdit_5.text())) / (
                    #                                  int(self.lineEdit_4.text()) + 1) * 100))
                    if my_inference_result == "pass":
                        self.resultcolor("Pass")
                        self.updatecount(str(int(self.lineEdit_4.text()) + 1),
                                         str(int(self.lineEdit_5.text()) + 1),
                                         self.lineEdit_6.text(),

                                         "%.2f%%" % ((int(self.lineEdit_5.text()) + 1) / (
                                                 int(self.lineEdit_4.text()) + 1) * 100))
                    if self.sfis_choose == True:
                        self.mysfis.data_upload(self.thissn, self.data)

                        # logging.info(f"Save OK {self.mbsn}")
                        # logging.info(f"check finish {self.max_val}")
                        logging.info("sfis upload OK")
                        self.myuihand.textbox.emit("sfis upload OK")
                    cv2.imwrite(
                        self.pciture_save + "//" + todaytime + "//" + self.thissn + " ALL PASS " + self.img_time + ".jpg",
                        image_numpy)
                    logging.info(self.thissn + " all test PASS")
                    self.myuihand.textbox.emit(self.thissn + " all test PASS")

                    self.step6 = True

                elif yolo_step6 == "Fail":
                    self.UI_show(
                        self.pciture_save + "//" + todaytime + "//" + self.thissn + "_" + self.img_time + "_fail.jpg",
                        6, 6)
                    logging.info("step6 check fail")
                    self.myuihand.textbox.emit("step6 check fail")
                    self.step6 = False

        except Exception as e:
            logging.error(str(e))
            self.myuihand.textbox.emit(str(e))

    def ocr_finction_8P(self, choose1, choose2, choose3=0):
        start_time = time.perf_counter()
        # Paddleocr目前支持中英文、英文、法语、德语、韩语、日语，可以通过修改lang参数进行切换
        # 参数依次为`ch`, `en`, `french`, `german`, `korean`, `japan`。
        ocr = PaddleOCR(use_angle_cls=True, lang="ch")  # need to run only once to download and load model into memory
        # img_path = '20240923_162516.jpg'
        img_path = choose1
        result = ocr.ocr(img_path, cls=True)
        boxes = []
        txts = []
        scores = []
        check_res = []
        pass_result = []
        for idx in range(len(result)):
            res = result[idx]
            for line in res:
                print(line)
                # if line[1][1] > 0.8:  # and len(line[1][0]) > 5
                for i in choose2:
                    if i in line[1][0]:
                        check_res.append((i, "pass"))
                        pass_result.append(i)
                        boxes.append(line[0])
                        txts.append(line[1][0])
                        scores.append(line[1][1])
                    # else:
                    #     check_res.append((i, "fail"))

        # 显示结果
        # from PIL import Image

        result = result[0]
        # image = Image.open(img_path)#.convert('RGB')
        # # boxes = [line[0] for line in result]
        # # txts = [line[1][0] for line in result]
        # # scores = [line[1][1] for line in result]
        # print(boxes[0])
        # colors = [0, 255, 0]  #: 文本框蓝色，文本绿色
        # # ([0, 255, 0], [0, 0, 255]): 文本绿色，文本蓝色
        #
        #
        # im_show = draw_ocr(image, boxes, txts, scores)
        # im_show = Image.fromarray(im_show)
        # im_show.save('result14.jpg')
        image = cv2.imread(img_path)
        for box in boxes:
            x1 = int(min(box[0][0], box[3][0]))
            y1 = int(min(box[0][1], box[1][1]))
            x2 = int(max(box[1][0], box[2][0]))
            y2 = int(max(box[3][1], box[2][1]))
            # print(type(box[0][1]))
            cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 2)
        if choose3 == 0:
            cv2.imwrite("source/C1000-8FP-E-2G-L_mark1_draw.jpg", image)
        elif choose3 == 1:
            cv2.imwrite("source/C1000-8FP-E-2G-L_mark2_draw.jpg", image)
        elif choose3 == 2:
            cv2.imwrite("source/C1000-8FP-E-2G-L_mark3_draw.jpg", image)
        elif choose3 == 3:
            cv2.imwrite("source/C1000-8FP-E-2G-L_mark4_draw.jpg", image)
        end_time = time.perf_counter()
        for i in check_res:
            print(i)
            # check_res.remove(i)
        # diff = [i for i in check_list for j in range(len(check_res)) if i not in check_res[j][0]]
        diff = [i for i in choose2 if i not in pass_result]

        print("diff", diff)

        print(end_time)
        print("%.2f" % (end_time - start_time))
        return check_res

    def UI_show(self, imgpath, totalpic, thispic):
        if int(totalpic) == 1 or int(totalpic) == 2:
            thisrow = 1
            thiscol = totalpic
        elif int(totalpic) == 3 or int(totalpic) == 4:
            thisrow = 2
            thiscol = 2
        elif int(totalpic) == 5 or int(totalpic) == 6:
            thisrow = 2
            thiscol = 3
        elif int(totalpic) == 7 or int(totalpic) == 8 or int(totalpic) == 9:
            thisrow = 3
            thiscol = 3
        self.tableWidget.horizontalHeader().setVisible(False)
        self.tableWidget.verticalHeader().setVisible(False)
        self.tableWidget.setRowCount(thisrow)
        self.tableWidget.setColumnCount(thiscol)

        self.tableWidget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tableWidget.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)

        if int(totalpic) <= 2:
            image_1 = QPixmap(imgpath)
            label = QLabel()
            image_1 = image_1.scaled(self.tableWidget.columnWidth(0), self.tableWidget.rowHeight(0),
                                     Qt.AspectRatioMode.IgnoreAspectRatio)
            label.setPixmap(image_1)
            self.tableWidget.setCellWidget(0, int(thispic) - 1, label)
        elif 2 < int(totalpic) <= 4:
            if int(thispic) < 3:
                image_2 = QPixmap(imgpath)
                label2 = QLabel()
                image_2 = image_2.scaled(self.tableWidget.columnWidth(0), self.tableWidget.rowHeight(0),
                                         Qt.AspectRatioMode.IgnoreAspectRatio)
                label2.setPixmap(image_2)
                self.tableWidget.setCellWidget(0, int(thispic) - 1, label2)
            elif 3 <= int(thispic) <= 4:
                image_2 = QPixmap(imgpath)
                label2 = QLabel()
                image_2 = image_2.scaled(self.tableWidget.columnWidth(0), self.tableWidget.rowHeight(0),
                                         Qt.AspectRatioMode.IgnoreAspectRatio)
                label2.setPixmap(image_2)
                self.tableWidget.setCellWidget(1, int(thispic) - 3, label2)

        elif 4 < int(totalpic) <= 6:
            if int(thispic) <= 3:
                image_2 = QPixmap(imgpath)
                label2 = QLabel()
                image_2 = image_2.scaled(self.tableWidget.columnWidth(0), self.tableWidget.rowHeight(0),
                                         Qt.AspectRatioMode.IgnoreAspectRatio)
                label2.setPixmap(image_2)
                self.tableWidget.setCellWidget(0, int(thispic) - 1, label2)
            elif 3 < int(thispic) <= 6:
                image_2 = QPixmap(imgpath)
                label2 = QLabel()
                image_2 = image_2.scaled(self.tableWidget.columnWidth(0), self.tableWidget.rowHeight(0),
                                         Qt.AspectRatioMode.IgnoreAspectRatio)
                label2.setPixmap(image_2)
                self.tableWidget.setCellWidget(1, int(thispic) - 4, label2)
        elif 6 < int(totalpic) <= 9:
            if int(thispic) <= 3:
                image_2 = QPixmap(imgpath)
                label2 = QLabel()
                image_2 = image_2.scaled(self.tableWidget.columnWidth(0), self.tableWidget.rowHeight(0),
                                         Qt.AspectRatioMode.IgnoreAspectRatio)
                label2.setPixmap(image_2)
                self.tableWidget.setCellWidget(0, int(thispic) - 1, label2)
            elif 3 < int(thispic) <= 6:
                image_2 = QPixmap(imgpath)
                label2 = QLabel()
                image_2 = image_2.scaled(self.tableWidget.columnWidth(0), self.tableWidget.rowHeight(0),
                                         Qt.AspectRatioMode.IgnoreAspectRatio)
                label2.setPixmap(image_2)
                self.tableWidget.setCellWidget(1, int(thispic) - 4, label2)
            elif 6 < int(thispic) <= 9:
                image_2 = QPixmap(imgpath)
                label2 = QLabel()
                image_2 = image_2.scaled(self.tableWidget.columnWidth(0), self.tableWidget.rowHeight(0),
                                         Qt.AspectRatioMode.IgnoreAspectRatio)
                label2.setPixmap(image_2)
                self.tableWidget.setCellWidget(2, int(thispic) - 7, label2)

    def HH4K_compare(self, step_img, cam_img, center_id):
        ##choose 1##
        center_id_x = center_id[2] + ((center_id[3] - center_id[2]) // 2)
        center_id_y = center_id[0] + ((center_id[1] - center_id[0]) // 2)
        my_step_img = step_img[center_id[0]:center_id[1], center_id[2]:center_id[3]]
        my_cam_img = cam_img[center_id[0]:center_id[1], center_id[2]:center_id[3]]
        step_gray = cv2.cvtColor(my_step_img, cv2.COLOR_BGR2GRAY)
        cam_gray = cv2.cvtColor(my_cam_img, cv2.COLOR_BGR2GRAY)
        hash_sample = self.pHash(step_gray)
        hash_cut = self.pHash(cam_gray)
        max_val = self.cmHash(hash_sample, hash_cut)
        max_val_hash = max_val
        # print(n)
        ##choose 2###
        sample_image_pil = Image.fromarray(cv2.cvtColor(my_step_img, cv2.COLOR_BGR2RGB))
        cut_img_pil = Image.fromarray(cv2.cvtColor(my_cam_img, cv2.COLOR_BGR2RGB))
        sample_image_pil_gray = sample_image_pil.convert('L')
        cut_img_pil_gray = cut_img_pil.convert('L')
        diff = ImageChops.difference(sample_image_pil_gray, cut_img_pil_gray)
        # 统计差异的统计信息，计算整个图像或图像的部分区域的统计数据
        stat = ImageStat.Stat(diff)
        # 输出差异的平均值，值越大差异越大
        # print(stat.mean[0])#<br><br>输出：<br>39.72462890625
        max_val_pil = stat.mean[0]
        # max_val_pil=str("{:.3f}".format(max_val_pil))

        ##choose 3##
        sample_gray1 = cv2.cvtColor(step_img, cv2.COLOR_BGR2HSV)
        cut_gray1 = cv2.cvtColor(cam_img, cv2.COLOR_BGR2HSV)
        sample_color = sample_gray1[center_id_y, center_id_x]
        cut_color = cut_gray1[center_id_y, center_id_x]
        color_val = []
        color_val.append(sample_color)
        color_val.append(cut_color)

        return max_val_hash, max_val_pil, color_val

        # check_result = cv2.matchTemplate(cut_gray, sample_gray, cv2.TM_CCORR_NORMED)
        # # threshold = 0.9
        # # loc=np.where( result >=threshold)
        # min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(check_result)
        # if max_val>=0.85 and stat.mean[0]<=30:
        #     cv2.rectangle(image_old, (valuelist[2],valuelist[0]),(valuelist[3],valuelist[1]), (0, 255, 0), 10, 15)
        #     my_inference_result="pass"
        # elif max_val<0.85 or stat.mean[0]>30:
        #     cv2.rectangle(image_old, (valuelist[2],valuelist[0]),(valuelist[3],valuelist[1]), (0, 0, 255), 10, 15)
        #     my_inference_result="fail"
        # cv2.imwrite("source/MR6500.jpg", image_old)
        # cv2.imwrite(self.pciture_save+"//"+todaytime+"//"+mbsn+"_"+self.img_time+"_"+my_inference_result+".jpg",image_old)
        # check_result=True
        # logging.info(f"check label OK")
        # self.myuihand.textbox.emit("check label OK")

    def cmHash(self, hash1, hash2, shape=(10, 10)):
        n = 0
        if len(hash1) != len(hash2):
            return -1
        for i in range(len(hash1)):
            if hash1[i] == hash2[i]:
                n = n + 1
        return n / (shape[0] * shape[1])

    def pHash(self, img, shape=(10, 10)):
        img = cv2.resize(img, (32, 32))
        # gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
        dct = cv2.dct(np.float32(img))
        dct_roi = dct[0:10, 0:10]
        hash = []
        average = np.mean(dct_roi)
        for i in range(dct_roi.shape[0]):
            for j in range(dct_roi.shape[1]):
                if dct_roi[i, j] > average:
                    hash.append(1)
                else:
                    hash.append(0)
        return hash

    def stopprogram(self):
        self.stop_program = True
        try:
            self.iocard.instantDioCtrlDispose()
            self.ekkoshan.close_camera()
        except Exception as e:
            pass

    def closeEvent(self, event):
        self.stop_program = True
        try:
            self.iocard.instantDioCtrlDispose()
            self.ekkoshan.close_camera()
        except Exception as e:
            pass

        print(123)


# # class MainWindow(QMainWindow):
# #     def __init__(self):
# #         super().__init__()
# #
# #         # 创建ui.py中的主窗口对象
# #         self.ui = AOI.Ui_MainWindow()
# #         self.ui.setupUi(self)


# #
# #         # 创建布局管理器
# #         layout = QVBoxLayout()
# #
# #         # 设置主窗口的布局管理器
# #         self.ui.centralwidget.setLayout(layout)
# #
# #         # 添加ui.py中的部件到布局管理器中
# #         layout.addWidget(self.ui.widget1)
# #         layout.addWidget(self.ui.widget2)
# #
# #         # 设置部件的拉伸因子
# #         layout.setStretchFactor(self.ui.widget1, 1)
# #         layout.setStretchFactor(self.ui.widget2, 2)
#
#
#
# def startrunning():
#
#     image = cv2.imread(r"C:\Users\Lenovo\PycharmProjects\yolov5-master1\data\images\1.jpg")  # 读取图像地址
#     rows, columns, channels = image.shape  # 获取图像的行像素、列像素和通道数
#     cv2.imshow("1", image)  # 创建一个名称为ice的窗口显示读取到的图像
#     image_name = 1  # 使用数字命名将要被保存的图像
#     # 图像要被均分成2行2列的4幅图像
#     for i in range(2):  # 表示“行”
#         for j in range(2):  # 表示“列”
#             # 使用“切片”，分别得到4幅图像中的每一幅图像
#             img_roi = image[(i * int(rows / 2)):((i + 1) * int(rows / 2) - 1),
#                       (j * int(columns / 2)):((j + 1) * int(columns / 2) - 1)]
#             cv2.imshow(str(i) + "-" + str(j), img_roi)  # 窗口显示4幅图像中的每一幅图像
#             cv2.imwrite("images/" + str(image_name) + ".jpg", img_roi)  # 保存4幅图像中的每一幅图像
#             image_name = image_name + 1  # 用于命名将要被保存的图像的数字执行自加操作
#     cv2.waitKey()  # 按下键盘上的任意按键后
#     cv2.destroyAllWindows()  # 销毁显示图像的所有窗口
#
#     # mytableWidget.setRowCount(4)
#     # mytableWidget.setColumnCount(4)
#     #
#     # mytableWidget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
#     # mytableWidget.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)
#     #
#     # for row in range(4):
#     #     for col in range(4):
#     #         # Load the image using QPixmap
#     #         image = QPixmap("output_image.jpg")
#     #         # image = image.scaled(100, 100)
#     #         image = image.scaled(mytableWidget.columnWidth(col), mytableWidget.rowHeight(row),
#     #                                Qt.AspectRatioMode.IgnoreAspectRatio)
#     #         # Create a QLabel widget and set the image as its pixmap
#     #         label = QLabel()
#     #         label.setPixmap(image)
#     #
#     #         # Set the QLabel widget as the cell widget
#     #         mytableWidget.setCellWidget(row, col, label)

class Scan(QDialog):
    def __init__(self):
        super(Scan, self).__init__()
        self.scan_user_label = QLabel('please scan Label:', self)
        self.scan_user_line = QLineEdit(self)
        self.user_h_layout = QHBoxLayout()

        self.layout_init()

    def layout_init(self):
        self.user_h_layout.addWidget(self.signin_user_label)
        self.user_h_layout.addWidget(self.signin_user_line)

        self.setLayout(self.user_h_layout)


class ReadDataMatrixCode():
    def __init__(self) -> None:
        self.all_barcode_info = None

    # img -> np.arr
    def decode(self, img):
        # 解析二维码
        self.all_barcode_info = pylibdmtx.decode(img, timeout=500, max_count=1)
        return self.all_barcode_info

    def getISN(self):
        if self.all_barcode_info:
            return True, self.all_barcode_info[0].data.decode("utf-8")
        else:
            return False, None


class Runthread(QtCore.QObject):
    signal = pyqtSignal(list)

    def __init__(self, ocr_img):
        super(Runthread, self).__init__()

        self.ocr_img = ocr_img

    def __del__(self):
        print(">>>  __del__")

    def run(self):
        result = []
        while result == []:
            self.signal.emit(result)
            # start_time = time.perf_counter()
            # Paddleocr目前支持中英文、英文、法语、德语、韩语、日语，可以通过修改lang参数进行切换
            # 参数依次为`ch`, `en`, `french`, `german`, `korean`, `japan`。
            ocr = PaddleOCR(use_angle_cls=True,
                            lang="ch")  # need to run only once to download and load model into memory
            # img_path = '20240923_162516.jpg'
            img_path = self.ocr_img
            result = ocr.ocr(img_path, cls=True)
            self.signal.emit(result)

        # print(end_time)
        # print("%.2f" % (end_time - start_time))


if __name__ == "__main__":
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    app = QApplication(sys.argv)
    # window = MainWindow()
    # # 设置主窗口的大小
    # MainWindow.resize(800, 600)
    demo = Demo()
    demo.show()
    sys.exit(app.exec_())

    # # MainWindow.resize(800, 600)
    # # MainWindow.setStyleSheet("background-color: lightblue;")


