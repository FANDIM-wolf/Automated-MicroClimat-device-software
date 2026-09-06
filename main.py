import sys
import csv
import serial.tools.list_ports
from PyQt6.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout, QTableWidget, QLabel,
    QLineEdit, QPushButton, QTableWidgetItem, QMessageBox, QHeaderView,
    QInputDialog, QTabWidget, QGridLayout, QFileDialog
)
from PyQt6.QtCore import Qt, QTimer
from datetime import datetime, timedelta
import pyqtgraph as pg
import pyqtgraph.exporters  # Модуль для экспорта графиков
from esp32_manager import ESP32Manager, TestESP32Manager
import  time
class MyApp(QWidget):
    def __init__(self):
        super().__init__()
        self.data_file = 'data_file.csv'
        self.datas_file = 'datas.csv'
        
        self.table_update_timer = None     
        self.reconnect_timer = None        
        
        self.interval_seconds = 0          
        self.gpio_columns = set()          
        self.was_collecting = False        

        self.plot_lines = {}       
        self.data_history = {}     
        self.stats_labels = {}     
        self.start_time = None     

        self.esp32 = self.initialize_esp32()
        self.initUI()
        self.load_csv_data(self.data_file)

    def initialize_esp32(self):
        ports = serial.tools.list_ports.comports()
        available_ports = [port.device for port in ports]

        items = ["TEST (no device)"] + available_ports

        if not available_ports:
            return TestESP32Manager(baud_rate=9600)

        port, ok = QInputDialog.getItem(
            self, "Select COM Port", "Choose the COM port for ESP32 (or TEST): ",
            items, 0, False
        )

        if not ok:
            sys.exit(0)

        if port == "TEST (no device)":
            return TestESP32Manager(baud_rate=9600)

        return ESP32Manager(port=port, baud_rate=9600)

    def initUI(self):
        self.setStyleSheet("font-family: Arial; background-color: white;")
        main_layout = QHBoxLayout()

        self.tabs = QTabWidget()
        
        self.tab_table = QWidget()
        self.init_table_tab()
        
        self.tab_plots = QWidget()
        self.init_plots_tab()

        self.tabs.addTab(self.tab_table, "Table View")
        self.tabs.addTab(self.tab_plots, "Real-Time Plots")

        right_layout = QVBoxLayout()
        right_layout.setSpacing(15)

        step_group = QHBoxLayout()
        step_group.setSpacing(10)
        time_label = QLabel("Interval")
        time_label.setStyleSheet("font-size: 14pt;")
        time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.time_edit = QLineEdit()
        self.time_edit.setPlaceholderText("hh:mm:ss")
        self.time_edit.setStyleSheet("border: 1px solid gray; padding: 5px; font-size: 12pt; min-width: 50px;")

        step_group.addWidget(time_label)
        step_group.addWidget(self.time_edit)

        button_style = "border: 1px solid black; padding: 12px 18px; font-size: 12pt; min-width: 50px;"

        self.apply_btn = QPushButton("Apply")
        self.start_btn = QPushButton("Start")
        self.stop_btn = QPushButton("Stop")
        self.save_csv_btn = QPushButton("Save CSV")
        self.save_plot_btn = QPushButton("Save Plot") # НОВАЯ КНОПКА
        self.clear_btn = QPushButton("Clear")
        
        self.apply_btn.setStyleSheet(button_style)
        self.start_btn.setStyleSheet(button_style)
        self.stop_btn.setStyleSheet(button_style)
        self.save_csv_btn.setStyleSheet(button_style)
        self.save_plot_btn.setStyleSheet(button_style)
        self.clear_btn.setStyleSheet(button_style)

        right_layout.addLayout(step_group)
        right_layout.addWidget(self.apply_btn)
        right_layout.addWidget(self.start_btn)
        right_layout.addSpacing(20)
        right_layout.addWidget(self.stop_btn)
        right_layout.addWidget(self.save_csv_btn)
        right_layout.addWidget(self.save_plot_btn) # Добавляем кнопку экспорта графика
        right_layout.addWidget(self.clear_btn)
        right_layout.addStretch()

        self.apply_btn.clicked.connect(self.apply_clicked)
        self.start_btn.clicked.connect(self.start_clicked)
        self.stop_btn.clicked.connect(self.stop_clicked)
        self.save_csv_btn.clicked.connect(self.save_csv_clicked)
        self.save_plot_btn.clicked.connect(self.save_plot_clicked) # Подключаем сигнал
        self.clear_btn.clicked.connect(self.clear_clicked)
        
        main_layout.addWidget(self.tabs, stretch=3)
        main_layout.addLayout(right_layout, stretch=1)
        self.setLayout(main_layout)

        self.setWindowTitle('Data Processing App')
        self.setGeometry(100, 100, 1200, 700)

        self.refresh_connection_ui()
        self.show()

    def init_table_tab(self):
        layout = QVBoxLayout()
        self.table = QTableWidget()
        self.setup_table()
        label = QLabel("Received Data")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("font-weight: bold; font-size: 14pt;")
        layout.addWidget(label)
        layout.addWidget(self.table)
        self.tab_table.setLayout(layout)

    def init_plots_tab(self):
        layout = QVBoxLayout()
        
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('w')
        self.plot_widget.setTitle("Temperature Sensors", color="black", size="16pt")
        self.plot_widget.setLabel('left', 'Temperature', units='°C', color='black', size='14pt')
        self.plot_widget.setLabel('bottom', 'Time', units='s', color='black', size='14pt')
        self.plot_widget.showGrid(x=True, y=True)
        self.plot_widget.addLegend()
        self.plot_widget.setYRange(-15, 200)
        
        self.stats_panel = QWidget()
        self.stats_layout = QGridLayout()
        self.stats_panel.setLayout(self.stats_layout)
        
        layout.addWidget(self.plot_widget, stretch=3)
        layout.addWidget(self.stats_panel, stretch=1)
        self.tab_plots.setLayout(layout)

    def refresh_connection_ui(self):
        connected = self.esp32.is_connected()
        self.apply_btn.setStyleSheet(f"border: 1px solid black; padding: 12px 18px; font-size: 12pt; min-width: 50px; background-color: {'#4CAF50' if connected else 'red'}; color: white;")
        self.start_btn.setStyleSheet(f"border: 1px solid black; padding: 12px 18px; font-size: 12pt; min-width: 50px; background-color: {'green' if connected else '#cccccc'}; color: white;")

    def setup_table(self):
        self.table.setStyleSheet("""
            QTableWidget{ border: 2px solid black; gridline-color: black; background-color: #f5f5f5; }
            QTableWidget::item{ border-bottom: 1px solid #ccc; border-right: 1px solid #ccc; padding: 5px; }
            QTableWidget::item:selected{ background-color: #e0f0ff; color: black; }
            QHeaderView::section{ background-color: #d3d3d3; padding: 8px; border: 1px solid black; font-weight: bold; }
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
                if not data: return
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
            pass

    def save_csv_clicked(self):
        filename = self.datas_file
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file, delimiter=';')
                headers = [self.table.horizontalHeaderItem(i).text() for i in range(self.table.columnCount())]
                writer.writerow(headers)
                for i in range(self.table.rowCount()):
                    row = [self.table.item(i, j).text() if self.table.item(i, j) else '' for j in range(self.table.columnCount())]
                    writer.writerow(row)
            QMessageBox.information(self, "Save", "CSV data successfully saved")
        except Exception as e:
            print(f"Error saving file: {e}")

    # ===== НОВАЯ ФУНКЦИЯ ДЛЯ ЭКСПОРТА ГРАФИКА =====
    def save_plot_clicked(self):
        try:
            # Выбор пути для сохранения
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Save Plot", "plot_export.png", "Images (*.png *.jpg)"
            )
            
            if file_path:
                # Обязательно принудительно обновляем графику перед экспортом
                QApplication.processEvents()
                
                # Создаем объект ImageExporter и передаем ему сам PlotItem
                exporter = pg.exporters.ImageExporter(self.plot_widget.plotItem)
                
                # Сохраняем по выбранному пути
                exporter.export(file_path)
                QMessageBox.information(self, "Save", f"Plot successfully saved to:\n{file_path}")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save plot:\n{str(e)}")
            print(f"Error exporting plot: {e}")

    def apply_clicked(self):
        try:
            time_str = self.time_edit.text().strip()
            if not time_str: raise ValueError("Empty field")
            t = datetime.strptime(time_str, "%H:%M:%S")
            self.interval_seconds = timedelta(hours=t.hour, minutes=t.minute, seconds=t.second).total_seconds()
            self.time_edit.setStyleSheet(self.time_edit.styleSheet().replace("border: 2px solid red; ", ""))
            
            if not self.esp32.is_connected():
                QMessageBox.warning(self, "Error", "No connection to ESP32/Test.")
                self.refresh_connection_ui()
                return
            QMessageBox.information(self, "Interval set", f"Interval saved. Click 'Start'.")
            self.refresh_connection_ui()
        except ValueError:
            self.time_edit.setStyleSheet(self.time_edit.styleSheet() + "border: 2px solid red; ")

    def start_clicked(self):
        if self.interval_seconds <= 0:
            QMessageBox.warning(self, "Error", "Set interval first.")
            return

        if not self.esp32.is_connected():
            if not self.esp32.connect():
                QMessageBox.warning(self, "Error", "Failed to connect to ESP32.")
                self.refresh_connection_ui()
                return

        self.stop_data_collection()
        self.was_collecting = True
        
        if self.start_time is None:
            self.start_time = time.time()
        
        self.table_update_timer = QTimer()
        self.table_update_timer.timeout.connect(self.request_and_update_table)
        self.table_update_timer.start(int(self.interval_seconds * 1000))

        self.refresh_connection_ui()
        QMessageBox.information(self, "Start", f"Started. Interval: {self.interval_seconds}s")

    def init_plot_line(self, gpio: str):
        if gpio not in self.plot_lines:
            colors = [(255,0,0), (0,0,255), (0,255,0), (255,165,0), (128,0,128)]
            idx = len(self.plot_lines) % len(colors)
            pen = pg.mkPen(color=colors[idx], width=2)
            
            self.data_history[gpio] = {"time": [], "value": []}
            self.plot_lines[gpio] = self.plot_widget.plot(
                [], [], name=gpio, pen=pen, symbol='o', symbolSize=5, symbolBrush=colors[idx]
            )
            
            stat_label = QLabel()
            stat_label.setStyleSheet(f"border: 2px solid rgb{colors[idx]}; padding: 5px; border-radius: 5px; font-size: 11pt;")
            self.stats_labels[gpio] = stat_label
            
            row = idx // 2
            col = idx % 2
            self.stats_layout.addWidget(stat_label, row, col)

    def request_and_update_table(self):
        try:
            sensor_data = self.esp32.read_and_validate_sensor_data()
            
            if sensor_data:
                new_columns = False
                for gpio in sensor_data.keys():
                    if gpio not in self.gpio_columns:
                        self.gpio_columns.add(gpio)
                        self.init_plot_line(gpio)
                        new_columns = True
                
                if new_columns:
                    self.update_table_headers()

                now = datetime.now()
                data_row = [now.strftime("%d.%m.%Y"), now.strftime("%H:%M:%S")]
                current_t = time.time() - self.start_time
                
                for gpio in sorted(self.gpio_columns):
                    raw_val = sensor_data.get(gpio, "")
                    if raw_val and raw_val not in ("NaN", "ERR"):
                        try:
                            val_float = float(raw_val.replace(',', '.'))
                            rounded_val = round(val_float, 1)
                            data_row.append(f"{rounded_val:.1f}".replace('.', ','))
                            
                            self.data_history[gpio]["time"].append(current_t)
                            self.data_history[gpio]["value"].append(val_float)
                            
                            if len(self.data_history[gpio]["time"]) > 100:
                                self.data_history[gpio]["time"].pop(0)
                                self.data_history[gpio]["value"].pop(0)
                                
                            self.plot_lines[gpio].setData(
                                self.data_history[gpio]["time"], 
                                self.data_history[gpio]["value"]
                            )
                            
                            self.update_statistics(gpio)
                            
                        except ValueError:
                            data_row.append(raw_val)
                    else:
                        data_row.append(raw_val)

                row_position = self.table.rowCount()
                self.table.insertRow(row_position)
                for col, item in enumerate(data_row):
                    self.table.setItem(row_position, col, QTableWidgetItem(str(item)))
                
                self.table.resizeColumnsToContents()
            else:
                if not self.esp32.is_connected():
                    self.handle_connection_lost()
                    
        except Exception as e:
            print(f" Error during update: {e}")
            self.handle_connection_lost()

    def update_statistics(self, gpio):
        values = self.data_history[gpio]["value"]
        if not values:
            return
            
        min_val = min(values)
        max_val = max(values)
        avg_val = sum(values) / len(values)
        
        rate = "0.00"
        if hasattr(self.esp32, 'rate_calculator'):
            if len(values) >= 2:
                times = self.data_history[gpio]["time"]
                dt = times[-1] - times[-2]
                if dt > 0:
                    rate_val = (values[-1] - values[-2]) / dt
                    rate = f"{rate_val:+.2f}"

        stats_text = (
            f"<b>{gpio}</b><br>"
            f"Current: {values[-1]:.1f} °C<br>"
            f"Min: {min_val:.1f} °C | Max: {max_val:.1f} °C<br>"
            f"Avg: {avg_val:.1f} °C | Rate: {rate} °C/s"
        )
        self.stats_labels[gpio].setText(stats_text)

    def handle_connection_lost(self):
        print(" Connection lost! Stopping...")
        self.stop_data_collection()
        self.refresh_connection_ui()
        
        if self.reconnect_timer is None:
            self.reconnect_timer = QTimer()
            self.reconnect_timer.timeout.connect(self.attempt_reconnect)
            self.reconnect_timer.start(5000)

    def attempt_reconnect(self):
        print("🔄 Attempting to reconnect...")
        if self.esp32.connect():
            if self.reconnect_timer:
                self.reconnect_timer.stop()
                self.reconnect_timer = None
            self.refresh_connection_ui()
            if self.was_collecting:
                self.start_clicked()
        else:
            print(" Reconnection failed. Retrying...")

    def stop_data_collection(self):
        if self.table_update_timer:
            self.table_update_timer.stop()
            self.table_update_timer = None

    def stop_clicked(self):
        self.stop_data_collection()
        if self.reconnect_timer:
            self.reconnect_timer.stop()
            self.reconnect_timer = None
        self.was_collecting = False
        self.start_time = None
        QMessageBox.information(self, "Completion", "Data collection stopped")

    def update_table_headers(self):
        headers = ["Date", "Time"] + sorted(list(self.gpio_columns))
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

    def clear_clicked(self):
        self.stop_clicked()
        self.table.setRowCount(0)
        self.gpio_columns = set()
        self.update_table_headers()
        
        self.plot_widget.clear()
        self.plot_lines.clear()
        self.data_history.clear()
        for label in self.stats_labels.values():
            label.deleteLater()
        self.stats_labels.clear()
        
        self.time_edit.setStyleSheet(self.time_edit.styleSheet().replace("border: 2px solid red; ", ""))

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = MyApp()
    sys.exit(app.exec())

