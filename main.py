import sys
import csv
import serial.tools.list_ports
from PyQt6.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout, QTableWidget, QLabel,
    QLineEdit, QPushButton, QTableWidgetItem, QMessageBox, QHeaderView,
    QInputDialog, QTextEdit, QDialog
)
from PyQt6.QtCore import Qt, QTimer
from datetime import datetime, timedelta
from timer_manager import TimerManager
from esp32_manager import ESP32Manager, TestESP32Manager





class MyApp(QWidget):
    def __init__(self):
        super().__init__()
        self.data_file = 'data_file.csv'
        self.datas_file = 'datas.csv'
        
        # Таймеры
        self.data_collection_timer = None  # Для постоянного опроса ESP32 (каждую секунду)
        self.table_update_timer = None     # Для обновления таблицы (с заданным интервалом)
        self.reconnect_timer = None        # Для переподключения при разрыве
        
        # Параметры
        self.interval_seconds = 0          # Интервал обновления таблицы
        self.gpio_columns = set()          # Динамические GPIO-столбцы
        self.latest_data = {}              # Буфер для хранения ПОСЛЕДНИХ значений
        self.was_collecting = False        # Флаг: работала ли программа до разрыва
        self.com_monitor_window = None     # Окно монитора порта

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
            return TestESP32Manager(baud_rate=9600)

        port, ok = QInputDialog.getItem(
            self,
            "Select COM Port",
            "Choose the COM port for ESP32 (or TEST): ",
            items,
            0,
            False
        )

        if not ok:
            QMessageBox.information(self, "Info", "Application will exit")
            sys.exit(0)

        if port == "TEST (no device)":
            return TestESP32Manager(baud_rate=9600)

        return ESP32Manager(port=port, baud_rate=9600)

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
        self.monitor_btn = QPushButton("COM Monitor")  # НОВАЯ КНОПКА

        self.apply_btn.setStyleSheet(button_style)
        self.start_btn.setStyleSheet(button_style)
        self.stop_btn.setStyleSheet(button_style)
        self.save_btn.setStyleSheet(button_style)
        self.clear_btn.setStyleSheet(button_style)
        self.monitor_btn.setStyleSheet(button_style + "background-color: #2196F3; color: white;")  # Синий цвет

        right_layout.addLayout(step_group)
        right_layout.addWidget(self.apply_btn)
        right_layout.addWidget(self.start_btn)
        right_layout.addSpacing(20)
        right_layout.addWidget(self.stop_btn)
        right_layout.addWidget(self.save_btn)
        right_layout.addWidget(self.clear_btn)
        right_layout.addSpacing(20)
        

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
            self.time_edit.setStyleSheet(self.time_edit.styleSheet().replace("border: 2px solid red; ", ""))

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
            self.time_edit.setStyleSheet(self.time_edit.styleSheet() + "border: 2px solid red; ")

    def start_clicked(self):
        if self.interval_seconds <= 0:
            QMessageBox.warning(self, "Error", "First set interval using 'Apply' button")
            return

        if not self.esp32.is_connected():
            if not self.esp32.connect():
                QMessageBox.warning(self, "Error", "Failed to connect to ESP32/Test")
                self.refresh_connection_ui()
                return

        # Останавливаем все существующие таймеры
        self.stop_clicked()
        
        # Инициализируем буфер для хранения ПОСЛЕДНИХ значений
        self.latest_data = {}
        
        # Таймер для постоянного опроса ESP32 (каждую секунду)
        self.data_collection_timer = QTimer()
        self.data_collection_timer.timeout.connect(self.collect_latest_data_from_esp32)
        self.data_collection_timer.start(1000)  # Каждую секунду
        
        # Таймер для обновления таблицы (с заданным интервалом)
        self.table_update_timer = QTimer()
        self.table_update_timer.timeout.connect(self.update_table_with_latest_data)
        self.table_update_timer.start(int(self.interval_seconds * 1000))

        self.refresh_connection_ui()
        QMessageBox.information(self, "Start", f"Data collection started. Table update interval: {self.interval_seconds} seconds")

    def collect_latest_data_from_esp32(self):
        """Постоянный опрос ESP32 каждую секунду для сбора ПОСЛЕДНИХ данных"""
        try:
            # ИСПОЛЬЗУЕМ ВАЛИДАЦИЮ
            sensor_data = self.esp32.read_and_validate_sensor_data()
            
            if sensor_data is not None:
                # Проверяем, есть ли ошибки валидации
                if "errors" in sensor_data:
                    errors = sensor_data["errors"]
                    print(f"⚠️ Validation errors ({len(errors)}):")
                    for error in errors:
                        print(f"  - {error}")
                    return  # Пропускаем некорректные данные
                
                # Обновляем список GPIO-столбцов при обнаружении новых
                new_columns = False
                for gpio in sensor_data.keys():
                    if gpio not in self.gpio_columns:
                        self.gpio_columns.add(gpio)
                        new_columns = True
                
                # Если появились новые столбцы, обновляем заголовки
                if new_columns:
                    self.update_table_headers()
                
                # Сохраняем ПОСЛЕДНИЕ значения
                for gpio, value in sensor_data.items():
                    self.latest_data[gpio] = value
                
                # Обновляем индикацию подключения
                if not self.esp32.is_connected():
                    self.refresh_connection_ui()
            else:
                # Данные не получены - проверяем соединение
                if not self.esp32.is_connected():
                    self.handle_connection_lost()
        
        except Exception as e:
            print(f"❌ Error in collect_latest_data_from_esp32: {e}")
            self.handle_connection_lost()

    def handle_connection_lost(self):
        """Обработка разрыва соединения"""
        print("⚠️ Connection lost! Stopping data collection...")
        
        # Сохраняем состояние: работала ли программа
        was_active = self.table_update_timer is not None and self.table_update_timer.isActive()
        if was_active:
            self.was_collecting = True
        
        # Останавливаем все таймеры сбора данных
        self.stop_data_collection()
        
        # Обновляем интерфейс
        self.refresh_connection_ui()
        
        # Запускаем таймер переподключения (каждые 5 секунд)
        if self.reconnect_timer is None:
            self.reconnect_timer = QTimer()
            self.reconnect_timer.timeout.connect(self.attempt_reconnect)
            self.reconnect_timer.start(5000)  # 5 секунд
            print("🔄 Reconnection attempts started (every 5 seconds)...")

    def attempt_reconnect(self):
        """Попытка переподключения к ESP32"""
        print("🔄 Attempting to reconnect to ESP32...")
        
        if self.esp32.connect():
            print("✅ Reconnection successful!")
            
            # Останавливаем таймер переподключения
            if self.reconnect_timer:
                self.reconnect_timer.stop()
                self.reconnect_timer = None
            
            # Обновляем интерфейс
            self.refresh_connection_ui()
            
            # Если программа работала до разрыва - возобновляем работу
            if self.was_collecting:
                self.resume_data_collection()
                self.was_collecting = False
                QMessageBox.information(self, "Connection restored", "Connection to ESP32 restored. Data collection resumed.")
        else:
            print("❌ Reconnection failed. Will try again in 5 seconds...")

    def stop_data_collection(self):
        """Остановка таймеров сбора данных (без сброса буфера)"""
        if self.data_collection_timer:
            self.data_collection_timer.stop()
            self.data_collection_timer = None
        
        if self.table_update_timer:
            self.table_update_timer.stop()
            self.table_update_timer = None
        
        print("⏹️ Data collection stopped")

    def resume_data_collection(self):
        """Возобновление сбора данных после переподключения"""
        if self.interval_seconds <= 0:
            print("⚠️ Cannot resume: interval not set")
            return
        
        # Инициализируем буфер для хранения ПОСЛЕДНИХ значений
        self.latest_data = {}
        
        # Таймер для постоянного опроса ESP32 (каждую секунду)
        self.data_collection_timer = QTimer()
        self.data_collection_timer.timeout.connect(self.collect_latest_data_from_esp32)
        self.data_collection_timer.start(1000)
        
        # Таймер для обновления таблицы (с заданным интервалом)
        self.table_update_timer = QTimer()
        self.table_update_timer.timeout.connect(self.update_table_with_latest_data)
        self.table_update_timer.start(int(self.interval_seconds * 1000))
        
        print(f"▶️ Data collection resumed. Interval: {self.interval_seconds} seconds")
        self.refresh_connection_ui()

    def update_table_headers(self):
        headers = ["Date", "Time"] + sorted(list(self.gpio_columns))
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

    def update_table_with_latest_data(self):
        """Обновление таблицы с ПОСЛЕДНИМИ полученными данными за интервал"""
        # Проверяем, есть ли данные для отображения
        if self.latest_data:
            now = datetime.now()
            date_str = now.strftime("%d.%m.%Y")
            time_str = now.strftime("%H:%M:%S")
            
            # Формируем строку данных
            data_row = [date_str, time_str]
            for gpio in sorted(self.gpio_columns):
                data_row.append(self.latest_data.get(gpio, ""))
            
            # Добавляем данные в таблицу
            row_position = self.table.rowCount()
            self.table.insertRow(row_position)
            
            for col, item in enumerate(data_row):
                self.table.setItem(row_position, col, QTableWidgetItem(str(item)))
            
            self.table.resizeColumnsToContents()
            print(f"✅ Data added to table: {data_row}")

    def stop_clicked(self):
        """Остановка всех процессов сбора данных"""
        # Останавливаем таймеры сбора данных
        self.stop_data_collection()
        
        # Останавливаем таймер переподключения
        if self.reconnect_timer:
            self.reconnect_timer.stop()
            self.reconnect_timer = None
        
        # Сбрасываем флаг
        self.was_collecting = False
        
        # Сбрасываем буфер
        self.latest_data = {}
        
        QMessageBox.information(self, "Completion", "Data collection stopped")

    def save_clicked(self):
        self.save_data_to_file()
        QMessageBox.information(self, "Save", "Data successfully saved")

    def clear_clicked(self):
        self.stop_clicked()
        self.table.setRowCount(0)
        self.gpio_columns = set()
        self.update_table_headers()
        self.time_edit.setStyleSheet(self.time_edit.styleSheet().replace("border: 2px solid red; ", ""))


if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = MyApp()
    sys.exit(app.exec())