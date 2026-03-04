import time
import re
from datetime import datetime
from typing import Optional, Dict

try:
    import serial
except Exception:
    serial = None


class ESP32Manager:
    def __init__(self, port: str, baud_rate: int = 9600, timeout: float = 1.0):
        self.port = port
        self.baud_rate = baud_rate
        self.timeout = timeout
        self.ser = None
        self.connected = False
        self.last_connect_attempt = 0.0
        self.reconnect_delay = 2.0  # секунды между попытками
        self.max_reconnect_attempts = 5
        self.attempt_count = 0
        self.connect()

    def connect(self) -> bool:
        """Подключение к порту"""
        if serial is None:
            self.connected = False
            return False

        try:
            if self.ser and self.ser.is_open:
                self.ser.close()

            self.ser = serial.Serial(self.port, self.baud_rate, timeout=self.timeout)
            time.sleep(2)
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()

            self.connected = True
            self.last_connect_attempt = time.time()
            self.attempt_count = 0
            print(f"✅ Connected to ESP32 on {self.port}")
            return True
        except Exception as e:
            print(f"❌ Connection error: {e}")
            self.connected = False
            self.last_connect_attempt = time.time()
            return False

    def disconnect(self):
        """Отключение от порта"""
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
        finally:
            self.connected = False
            print("🔌 ESP32 disconnected")

    def is_connected(self) -> bool:
        """Проверка активности соединения"""
        return self.connected and self.ser is not None and self.ser.is_open

    def ensure_connection(self) -> bool:
        """
        Автоматическое восстановление соединения при разрыве.
        Проверяет соединение и при необходимости пытается переподключиться.
        """
        # Если соединение активно — возвращаем сразу
        if self.is_connected():
            return True

        current_time = time.time()
        
        # Проверяем, не слишком ли рано пытаться переподключиться
        if current_time - self.last_connect_attempt < self.reconnect_delay:
            return False

        # Увеличиваем счётчик попыток
        self.attempt_count += 1
        
        # Если превышено максимальное количество попыток — сдаёмся
        if self.attempt_count > self.max_reconnect_attempts:
            print("⚠️ Max reconnect attempts reached. Waiting longer...")
            self.reconnect_delay = 30.0  # увеличиваем задержку до 30 секунд
            self.last_connect_attempt = current_time
            return False

        print(f"🔄 Attempting reconnect #{self.attempt_count} to {self.port}...")
        
        success = self.connect()
        
        if success:
            print("✅ Reconnected successfully")
            self.reconnect_delay = 2.0  # сбрасываем задержку
        else:
            # Экспоненциальная задержка между попытками (максимум 30 секунд)
            self.reconnect_delay = min(self.reconnect_delay * 1.5, 30.0)
            self.last_connect_attempt = current_time
        
        return success

    def send_command(self, cmd: str) -> bool:
        """
        Отправка команды на ESP32 (например, "GET")
        Автоматически проверяет и восстанавливает соединение
        """
        if not self.ensure_connection():
            print(f"❌ Cannot send command '{cmd}': no connection")
            return False

        try:
            cmd_bytes = (cmd + '\n').encode('utf-8')
            self.ser.write(cmd_bytes)
            self.ser.flush()
            print(f"📤 Sent command: {cmd}")
            return True
        except Exception as e:
            print(f"❌ Send command failed: {e}")
            self.connected = False
            return False

    def read_sensor_data(self) -> Optional[Dict[str, str]]:
        """
        Чтение данных с датчиков после отправки команды GET.
        Формат данных от ESP32:
          :
          gpio 1 123
          gpio 2 456
          ;
        """
        if not self.ensure_connection():
            print("❌ Cannot read data: no connection")
            return None

        # Ждём начало данных ':'
        start_time = time.time()
        while time.time() - start_time < self.timeout:
            if self.ser.in_waiting:
                line = self.ser.readline().decode('utf-8', errors='replace').strip()
                if line == ':':
                    break
            time.sleep(0.01)
        else:
            print("⚠️ Timeout waiting for start marker ':'")
            return None

        # Собираем данные до ';'
        data_lines = []
        start_time = time.time()
        while time.time() - start_time < self.timeout:
            if self.ser.in_waiting:
                line = self.ser.readline().decode('utf-8', errors='replace').strip()
                if line == ';':
                    break
                if not line or line == ',':
                    continue
                data_lines.append(line)
            time.sleep(0.01)
        else:
            print("⚠️ Timeout waiting for end marker ';'")
            return None

        # Парсим данные
        sensor_data = {}
        for line in data_lines:
            match = re.match(r'gpio\s+(\d+)\s+(\d+)', line)
            if match:
                gpio_num = match.group(1)
                value = match.group(2)
                sensor_data[f"GPIO{gpio_num}"] = value

        if sensor_data:
            print(f"📡 Received {len(sensor_data)} sensor values: {sensor_data}")
        else:
            print("⚠️ No sensor data parsed")

        return sensor_data if sensor_data else None


class TestESP32Manager:
    """
    Тестовый менеджер для работы без реального устройства
    """
    def __init__(self, baud_rate: int = 9600):
        self.baud_rate = baud_rate
        self.connected = True
        self._tick = 0
        # Базовые значения
        self.frame = {
            "GPIO1": 100,
            "GPIO2": 200,
            "GPIO3": 300,
            "GPIO4": 400,
            "GPIO5": 400,
            "GPIO6": 423,
            "GPIO7": 423,
        }
        self.simulate_disconnection = False  # для тестирования восстановления

    def connect(self) -> bool:
        """Подключение (всегда успешно)"""
        self.connected = not self.simulate_disconnection
        if self.connected:
            print("✅ Test mode: connected")
        return self.connected

    def disconnect(self):
        """Отключение"""
        self.connected = False
        print("🔌 Test mode: disconnected")

    def is_connected(self) -> bool:
        """Проверка соединения"""
        return self.connected

    def ensure_connection(self) -> bool:
        """
        Восстановление соединения в тестовом режиме
        """
        if not self.connected:
            print("🔄 Test mode: simulating reconnect...")
            self.connected = True
            print("✅ Test mode: reconnected")
        return self.connected

    def send_command(self, cmd: str) -> bool:
        """
        Отправка команды в тестовом режиме
        """
        if not self.is_connected():
            print("⚠️ Test: not connected — command ignored")
            return False
        
        print(f"[TEST] Received command: '{cmd}'")
        return True

    def read_sensor_data(self) -> Optional[Dict[str, str]]:
        """
        Генерация тестовых данных
        """
        if not self.is_connected():
            print("⚠️ Test: no connection — returning None")
            return None

        self._tick += 1
        
        # Генерируем вариативные данные
        test_data = {}
        for gpio, base_value in self.frame.items():
            variation = (self._tick % 5) - 2  # вариация от -2 до +2
            test_data[gpio] = str(base_value + variation)
        
        print(f"[TEST] Generated data: {test_data}")
        return test_data