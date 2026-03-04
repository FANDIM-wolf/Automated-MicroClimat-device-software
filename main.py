import sys
import csv
import serial.tools.list_ports
from PyQt6.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout, QTableWidget, QLabel,
    QLineEdit, QPushButton, QTableWidgetItem, QMessageBox, QHeaderView,
    QInputDialog, QTextEdit, QTabWidget
)
from PyQt6.QtCore import Qt, QTimer
from datetime import datetime, timedelta
from esp32_manager import ESP32Manager, TestESP32Manager


class MonitorTab(QWidget):
    """Вкладка мониторинга COM-порта"""
    def __init__(self, esp32_manager):
        super().__init__()
        self.esp32 = esp32_manager
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()

        # Заголовок
        title = QLabel("COM Port Monitor")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-weight: bold; font-size: 14pt;")
        layout.addWidget(title)

        # QTextEdit для вывода данных
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("""
            QTextEdit {
                border: 1px solid #aaa;
                padding: 5px;
                font-family: 'Courier New', monospace;
                background-color: #f8f8f8;
            }
        """)
        layout.addWidget(self.log_view)

        # Панель отправки
        send_layout = QHBoxLayout()
        self.send_edit = QLineEdit()
        self.send_edit.setPlaceholderText("Enter command (e.g. GET, SET GPIO1 1)")
        self.send_edit.setStyleSheet("padding: 5px; font-size: 12pt;")
        self.send_btn = QPushButton("Send")
        self.send_btn.setStyleSheet("""
            padding: 6px 12px;
            font-size: 12pt;
            background-color: #2196F3;
            color: white;
            border: none;
        """)
        send_layout.addWidget(self.send_edit)
        send_layout.addWidget(self.send_btn)

        layout.addLayout(send_layout)

        self.setLayout(layout)

        # Связь кнопки
        self.send_btn.clicked.connect(self.send_command)

        # Таймер для чтения сырых данных
        self.read_timer = QTimer()
        self.read_timer.timeout.connect(self.read_raw_data)
        self.read_timer.start(100)  # каждые 100 мс

    def read_raw_data(self):
        """Чтение сырых данных из порта"""
        if not self.esp32.is_connected():
            return

        try:
            if hasattr(self.esp32, 'ser') and self.esp32.ser and self.esp32.ser.in_waiting:
                raw = self.esp32.ser.readline()
                try:
                    text = raw.decode('utf-8', errors='replace').rstrip('\r\n')
                    if text:
                        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                        self.log_view.append(f"[{timestamp}] ← {text}")
                        self.log_view.verticalScrollBar().setValue(
                            self.log_view.verticalScrollBar().maximum()
                        )
                except Exception as e:
                    self.log_view.append(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Decode error: {e}")
        except Exception as e:
            self.log_view.append(f"[{datetime.now().strftime('%H:%M:%S')}] 🔌 Read error: {e}")
            self.esp32.connected = False

    def send_command(self):
        """Отправка команды в порт"""
        cmd = self.send_edit.text().strip()
        if not cmd:
            return

        if not self.esp32.is_connected():
            QMessageBox.warning(self, "Error", "Not connected to ESP32")
            return

        try:
            # Отправляем с \n
            if hasattr(self.esp32, 'ser') and self.esp32.ser:
                self.esp32.ser.write((cmd + '\n').encode('utf-8'))
                self.esp32.ser.flush()
                timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                self.log_view.append(f"[{timestamp}] → {cmd}")
                self.log_view.verticalScrollBar().setValue(
                    self.log_view.verticalScrollBar().maximum()
                )

                # Очищаем поле
                self.send_edit.clear()
        except Exception as e:
            self.log_view.append(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Send error: {e}")
            self.esp32.connected = False


class MyApp(QWidget):
    def __init__(self):
        super().__init__()
        self.data_file = 'data_file.csv'
        self.datas_file = 'datas.csv'
        
        # Единственный таймер для отправки команды по интервалу
        self.main_timer = None
        
        # Параметры
        self.interval_seconds = 0          # Интервал отправки команды GET
        self.gpio_columns = set()           # Динамические столбцы с датчиками
        self.latest_data = {}               # Последние полученные данные

        self.esp32 = self.initialize_esp32()

        self.initUI()
        self.load_csv_data(self.data_file)

    def initialize_esp32(self):
        """Инициализация соединения с портом"""
        ports = serial.tools.list_ports.comports()
        available_ports = [port.device for port in ports]

        # Всегда даём вариант TEST
        items = ["TEST (no device)"] + available_ports

        if not available_ports:
            return TestESP32Manager(baud_rate=9600)

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
            return TestESP32Manager(baud_rate=9600)

        return ESP32Manager(port=port, baud_rate=9600)

    def initUI(self):
        """Инициализация интерфейса"""
        self.setStyleSheet("font-family: Arial; background-color: white;")
        
        # Создаём QTabWidget
        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self.create_data_tab(), "Data Collection")
        self.monitor_tab = MonitorTab(self.esp32)
        self.tab_widget.addTab(self.monitor_tab, "COM Monitor")

        main_layout = QVBoxLayout()
        main_layout.addWidget(self.tab_widget)
        self.setLayout(main_layout)

        self.setWindowTitle('Data Processing App')
        self.setGeometry(100, 100, 1000, 600)

        self.refresh_connection_ui()
        self.show()

    def create_data_tab(self):
        """Создание вкладки сбора данных"""
        widget = QWidget()
        layout = QHBoxLayout()

        # Левая часть — таблица данных
        left_layout = QVBoxLayout()
        self.table = QTableWidget()
        self.setup_table()
        left_label = QLabel("Received Data")
        left_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_label.setStyleSheet("font-weight: bold; font-size: 14pt;")
        left_layout.addWidget(left_label)
        left_layout.addWidget(self.table)

        # Правая часть — панель управления
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

        layout.addLayout(left_layout)
        layout.addLayout(right_layout)
        widget.setLayout(layout)
        return widget

    def refresh_connection_ui(self):
        """Обновление индикации соединения на кнопках"""
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
        """Настройка таблицы"""
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
        """Загрузка данных из CSV файла"""
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
        """Сохранение данных в файл"""
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
        """Применение интервала"""
        try:
            time_str = self.time_edit.text().strip()
            if not time_str:
                raise ValueError("Time input field is empty")

            t = datetime.strptime(time_str, "%H:%M:%S")
            self.interval_seconds = timedelta(hours=t.hour, minutes=t.minute, seconds=t.second).total_seconds()

            # убрать индикацию ошибки
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
        """Запуск сбора данных"""
        if self.interval_seconds <= 0:
            QMessageBox.warning(self, "Error", "First set interval using 'Apply' button")
            return

        if not self.esp32.is_connected():
            if not self.esp32.connect():
                QMessageBox.warning(self, "Error", "Failed to connect to ESP32/Test")
                self.refresh_connection_ui()
                return

        # Останавливаем предыдущий таймер
        self.stop_clicked()

        # Запускаем ЕДИНСТВЕННЫЙ таймер с интервалом
        self.main_timer = QTimer()
        self.main_timer.timeout.connect(self.fetch_and_update_data)
        self.main_timer.start(int(self.interval_seconds * 1000))

        self.refresh_connection_ui()
        QMessageBox.information(self, "Start",
            f"Data collection started. Interval: {self.interval_seconds:.0f} seconds")

    def fetch_and_update_data(self):
        """
        Вызывается раз в интервал:
        1. Отправляем команду GET
        2. Читаем данные
        3. Добавляем строку в таблицу
        """
        # Автоматически проверяет и восстанавливает соединение
        if not self.esp32.is_connected():
            print("⚠️ Not connected — skipping fetch")
            return

        # Отправляем команду GET
        if not self.esp32.send_command("GET"):
            print("❌ Failed to send GET command")
            return

        # Читаем данные
        sensor_data = self.esp32.read_sensor_data()

        if sensor_data is None:
            print("⚠️ No data received from ESP32 after GET")
            return

        # Обновляем столбцы при необходимости
        new_columns = False
        for gpio in sensor_data.keys():
            if gpio not in self.gpio_columns:
                self.gpio_columns.add(gpio)
                new_columns = True
        if new_columns:
            self.update_table_headers()

        # Формируем строку для таблицы
        now = datetime.now()
        date_str = now.strftime("%d.%m.%Y")
        time_str = now.strftime("%H:%M:%S")

        data_row = [date_str, time_str]
        for gpio in sorted(self.gpio_columns):
            data_row.append(sensor_data.get(gpio, ""))

        # Добавляем в таблицу
        row_position = self.table.rowCount()
        self.table.insertRow(row_position)
        for col, item in enumerate(data_row):
            self.table.setItem(row_position, col, QTableWidgetItem(str(item)))

        self.table.resizeColumnsToContents()
        print(f"✅ Added row: {data_row}")

    def update_table_headers(self):
        """Обновление заголовков таблицы"""
        headers = ["Date", "Time"] + sorted(list(self.gpio_columns))
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

    def stop_clicked(self):
        """Остановка сбора данных"""
        if self.main_timer:
            self.main_timer.stop()
            self.main_timer = None
        self.latest_data = {}
        QMessageBox.information(self, "Completion", "Data collection stopped")

    def save_clicked(self):
        """Сохранение данных"""
        self.save_data_to_file()
        QMessageBox.information(self, "Save", "Data successfully saved")

    def clear_clicked(self):
        """Очистка таблицы"""
        self.stop_clicked()
        self.table.setRowCount(0)
        self.gpio_columns = set()
        self.update_table_headers()
        self.time_edit.setStyleSheet(self.time_edit.styleSheet().replace("border: 2px solid red;", ""))


if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = MyApp()
    sys.exit(app.exec())