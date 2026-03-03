import sys
import csv
import serial.tools.list_ports

from PyQt6.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout, QTableWidget, QLabel,
    QLineEdit, QPushButton, QTableWidgetItem, QMessageBox, QHeaderView,
    QInputDialog
)
from PyQt6.QtCore import Qt
from datetime import datetime, timedelta

from timer_manager import TimerManager
from esp32_manager import ESP32Manager, TestESP32Manager


class MyApp(QWidget):
    def __init__(self):
        super().__init__()

        self.data_file = 'data_file.csv'
        self.datas_file = 'datas.csv'
        self.data_timer = None
        self.interval_seconds = 0
        self.gpio_columns = set()

        self.esp32 = self.initialize_esp32()

        self.initUI()
        self.load_csv_data(self.data_file)

    def initialize_esp32(self):
        ports = serial.tools.list_ports.comports()
        available_ports = [port.device for port in ports]

        # Всегда даём вариант TEST, чтобы можно было работать без железа
        items = ["TEST (no device)"] + available_ports

        # Если портов вообще нет — сразу TEST
        if not available_ports:
            return TestESP32Manager(baud_rate=115200)

        port, ok = QInputDialog.getItem(
            self,
            "Select COM Port",
            "Choose the COM port for ESP32 (or TEST):",
            items,
            0,
            False
        )

        if not ok:
            QMessageBox.information(self, "Info", "Application will exit")
            sys.exit(0)

        if port == "TEST (no device)":
            return TestESP32Manager(baud_rate=115200)

        return ESP32Manager(port=port, baud_rate=115200)

    def initUI(self):
        self.setStyleSheet("font-family: Arial; background-color: white;")
        main_layout = QHBoxLayout()

        # Left part - data table
        left_layout = QVBoxLayout()
        self.table = QTableWidget()
        self.setup_table()
        left_label = QLabel("Received Data")
        left_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_label.setStyleSheet("font-weight: bold; font-size: 14pt;")
        left_layout.addWidget(left_label)
        left_layout.addWidget(self.table)

        # Right part - control panel
        right_layout = QVBoxLayout()
        right_layout.setSpacing(15)

        step_group = QHBoxLayout()
        step_group.setSpacing(10)
        time_label = QLabel("Interval")
        time_label.setStyleSheet("font-size: 14pt;")
        time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.time_edit = QLineEdit()
        self.time_edit.setPlaceholderText("hh:mm:ss")
        self.time_edit.setStyleSheet("""
            border: 1px solid gray;
            padding: 5px;
            font-size: 12pt;
            min-width: 50px;
        """)

        step_group.addWidget(time_label)
        step_group.addWidget(self.time_edit)

        button_style = """
            border: 1px solid black;
            padding: 12px 18px;
            font-size: 12pt;
            min-width: 50px;
        """

        self.apply_btn = QPushButton("Apply")
        self.start_btn = QPushButton("Start")
        self.stop_btn = QPushButton("Stop")
        self.save_btn = QPushButton("Save")
        self.clear_btn = QPushButton("Clear")

        self.apply_btn.setStyleSheet(button_style)
        self.start_btn.setStyleSheet(button_style)
        self.stop_btn.setStyleSheet(button_style)
        self.save_btn.setStyleSheet(button_style)
        self.clear_btn.setStyleSheet(button_style)

        right_layout.addLayout(step_group)
        right_layout.addWidget(self.apply_btn)
        right_layout.addWidget(self.start_btn)
        right_layout.addSpacing(20)
        right_layout.addWidget(self.stop_btn)
        right_layout.addWidget(self.save_btn)
        right_layout.addWidget(self.clear_btn)

        self.apply_btn.clicked.connect(self.apply_clicked)
        self.start_btn.clicked.connect(self.start_clicked)
        self.stop_btn.clicked.connect(self.stop_clicked)
        self.save_btn.clicked.connect(self.save_clicked)
        self.clear_btn.clicked.connect(self.clear_clicked)

        main_layout.addLayout(left_layout)
        main_layout.addLayout(right_layout)
        self.setLayout(main_layout)

        self.setWindowTitle('Data Processing App')
        self.setGeometry(100, 100, 1000, 600)

        self.refresh_connection_ui()
        self.show()

    def refresh_connection_ui(self):
        connected = self.esp32.is_connected()

        self.apply_btn.setStyleSheet(f"""
            border: 1px solid black;
            padding: 12px 18px;
            font-size: 12pt;
            min-width: 50px;
            background-color: {'#4CAF50' if connected else 'red'};
            color: white;
        """)

        self.start_btn.setStyleSheet(f"""
            border: 1px solid black;
            padding: 12px 18px;
            font-size: 12pt;
            min-width: 50px;
            background-color: {'green' if connected else '#cccccc'};
            color: white;
        """)

    def setup_table(self):
        self.table.setStyleSheet("""
            QTableWidget{
                border: 2px solid black;
                gridline-color: black;
                background-color: #f5f5f5;
            }
            QTableWidget::item{
                border-bottom: 1px solid #ccc;
                border-right: 1px solid #ccc;
                padding: 5px;
            }
            QTableWidget::item:selected{
                background-color: #e0f0ff;
                color: black;
            }
            QHeaderView::section{
                background-color: #d3d3d3;
                padding: 8px;
                border: 1px solid black;
                font-weight: bold;
            }
        """)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)

        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Date", "Time"])

    def load_csv_data(self, filename='data_file.csv'):
        try:
            with open(filename, 'r', encoding='utf-8') as file:
                reader = csv.reader(file, delimiter=';')
                data = list(reader)
                if not data:
                    return

                headers = data[0]
                rows = data[1:]

                for header in headers:
                    if header.startswith("GPIO"):
                        self.gpio_columns.add(header)

                if self.gpio_columns:
                    self.update_table_headers()

                self.table.setColumnCount(len(headers))
                self.table.setHorizontalHeaderLabels(headers)
                self.table.setRowCount(len(rows))

                for i, row in enumerate(rows):
                    for j, item in enumerate(row):
                        self.table.setItem(i, j, QTableWidgetItem(item))

                self.table.resizeColumnsToContents()
                self.table.resizeRowsToContents()

        except FileNotFoundError:
            # файл может не существовать при первом запуске — это нормально
            pass
        except Exception as e:
            print(f"Error reading file: {e}")

    def save_data_to_file(self, filename=None):
        if filename is None:
            filename = self.datas_file
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file, delimiter=';')
                headers = [self.table.horizontalHeaderItem(i).text() for i in range(self.table.columnCount())]
                writer.writerow(headers)
                for i in range(self.table.rowCount()):
                    row = [
                        self.table.item(i, j).text() if self.table.item(i, j) else ''
                        for j in range(self.table.columnCount())
                    ]
                    writer.writerow(row)
        except Exception as e:
            print(f"Error saving file: {e}")

    def apply_clicked(self):
        try:
            time_str = self.time_edit.text().strip()
            if not time_str:
                raise ValueError("Time input field is empty")

            t = datetime.strptime(time_str, "%H:%M:%S")
            self.interval_seconds = timedelta(hours=t.hour, minutes=t.minute, seconds=t.second).total_seconds()

            # убрать индикацию ошибки, если была
            self.time_edit.setStyleSheet(self.time_edit.styleSheet().replace("border: 2px solid red;", ""))

            if not self.esp32.is_connected():
                QMessageBox.warning(self, "Error", "No connection to ESP32/Test. Check settings.")
                self.refresh_connection_ui()
                return

            QMessageBox.information(
                self, "Interval set",
                f"Interval {time_str} saved. Click 'Start' to begin data collection."
            )
            self.refresh_connection_ui()

        except ValueError as e:
            print(f"Time format error: {e}")
            self.time_edit.setStyleSheet(self.time_edit.styleSheet() + "border: 2px solid red;")

    def start_clicked(self):
        if self.interval_seconds <= 0:
            QMessageBox.warning(self, "Error", "First set interval using 'Apply' button")
            return

        if not self.esp32.is_connected():
            if not self.esp32.connect():
                QMessageBox.warning(self, "Error", "Failed to connect to ESP32/Test")
                self.refresh_connection_ui()
                return

        if self.data_timer:
            self.data_timer.stop()
            self.data_timer = None

        self.data_timer = TimerManager(
            interval_ms=int(self.interval_seconds * 1000),
            callback=self.request_sensor_data
        )
        self.data_timer.start()

        self.refresh_connection_ui()
        QMessageBox.information(self, "Start", f"Data collection started. Interval: {self.interval_seconds} seconds")

    def request_sensor_data(self):
        sensor_data = self.esp32.read_sensor_data()

        if sensor_data is not None:
            new_columns = False
            for gpio in sensor_data.keys():
                if gpio not in self.gpio_columns:
                    self.gpio_columns.add(gpio)
                    new_columns = True

            if new_columns:
                self.update_table_headers()

            self.add_data_to_table(sensor_data)
            print(f"✅ Data added: {sensor_data}")
        else:
            print("⚠️  No data received from ESP32/Test")

    def update_table_headers(self):
        headers = ["Date", "Time"] + sorted(list(self.gpio_columns))
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

    def add_data_to_table(self, sensor_data):
        now = datetime.now()
        date_str = now.strftime("%d.%m.%Y")
        time_str = now.strftime("%H:%M:%S")

        data_row = [date_str, time_str]
        for gpio in sorted(self.gpio_columns):
            data_row.append(sensor_data.get(gpio, ""))

        row_position = self.table.rowCount()
        self.table.insertRow(row_position)

        for col, item in enumerate(data_row):
            self.table.setItem(row_position, col, QTableWidgetItem(str(item)))

        self.table.resizeColumnsToContents()

    def stop_clicked(self):
        if self.data_timer:
            self.data_timer.stop()
            self.data_timer = None
        QMessageBox.information(self, "Completion", "Data collection stopped")

    def save_clicked(self):
        self.save_data_to_file()
        QMessageBox.information(self, "Save", "Data successfully saved")

    def clear_clicked(self):
        if self.data_timer:
            self.data_timer.stop()
            self.data_timer = None
        self.table.setRowCount(0)
        self.gpio_columns = set()
        self.update_table_headers()
        self.time_edit.setStyleSheet(self.time_edit.styleSheet().replace("border: 2px solid red;", ""))


if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = MyApp()
    sys.exit(app.exec())
