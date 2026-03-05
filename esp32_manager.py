import time
import re
from datetime import datetime
from typing import Optional, Dict, List, Tuple

try:
    import serial
except Exception:
    serial = None


class DataValidator:
    """Валидатор данных: проверка скачков"""
    
    def __init__(self, window_size: int = 5):
        self.history: Dict[str, List[Tuple[float, float]]] = {}  # {gpio: [(timestamp, value)]}
        self.window_size = window_size
        self.max_rate_change = 10.0  # макс. изменение в секунду

    def add_reading(self, gpio: str, value: float, timestamp: float = None):
        """Добавление нового показания в историю"""
        if timestamp is None:
            timestamp = time.time()
        
        if gpio not in self.history:
            self.history[gpio] = []
        
        self.history[gpio].append((timestamp, value))
        
        # Ограничиваем размер истории
        if len(self.history[gpio]) > self.window_size:
            self.history[gpio].pop(0)

    def validate(self, gpio: str, value: float) -> Tuple[bool, str]:
        """
        Валидация значения
        Возвращает: (валидно, сообщение об ошибке)
        """
        # Проверка скорости изменения (резкие скачки)
        is_valid, msg = self._check_rate_change(gpio, value)
        if not is_valid:
            return False, msg
        
        return True, "✅ Данные корректны"

    def _check_rate_change(self, gpio: str, value: float) -> Tuple[bool, str]:
        """Проверка скорости изменения (резкие скачки)"""
        if gpio not in self.history or len(self.history[gpio]) < 2:
            return True, ""  # Недостаточно данных для проверки
        
        # Берём последнее значение
        last_time, last_value = self.history[gpio][-1]
        current_time = time.time()
        
        time_diff = current_time - last_time
        if time_diff <= 0:
            time_diff = 0.1  # избегаем деления на ноль
        
        rate_change = abs(value - last_value) / time_diff
        
        if rate_change > self.max_rate_change:
            return False, f"⚠️ Резкий скачок: {rate_change:.1f} ед/сек (макс. {self.max_rate_change})"
        
        return True, ""


class ESP32Manager:
    def __init__(self, port: str, baud_rate: int = 9600, timeout: float = 1.0):
        self.port = port
        self.baud_rate = baud_rate
        self.timeout = timeout
        self.ser = None
        self.connected = False
        self.last_connect_attempt = 0.0
        self.reconnect_delay = 2.0
        self.max_reconnect_attempts = 5
        self.attempt_count = 0
        self.validator = DataValidator(window_size=5)  # Валидатор данных
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
        """Автоматическое восстановление соединения"""
        if self.is_connected():
            return True

        current_time = time.time()
        
        if current_time - self.last_connect_attempt < self.reconnect_delay:
            return False

        self.attempt_count += 1
        
        if self.attempt_count > self.max_reconnect_attempts:
            print("⚠️ Max reconnect attempts reached. Waiting longer...")
            self.reconnect_delay = 30.0
            self.last_connect_attempt = current_time
            return False

        print(f"🔄 Attempting reconnect #{self.attempt_count} to {self.port}...")
        
        success = self.connect()
        
        if success:
            print("✅ Reconnected successfully")
            self.reconnect_delay = 2.0
        else:
            self.reconnect_delay = min(self.reconnect_delay * 1.5, 30.0)
            self.last_connect_attempt = current_time
        
        return success

    def send_command(self, cmd: str) -> bool:
        """Отправка команды на ESP32"""
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
        """Чтение данных с датчиков"""
        if not self.ensure_connection():
            print("❌ Cannot read data: no connection")
            return None

        # Отправляем команду GET
        if not self.send_command("GET"):
            print("⚠️ Cannot send GET command")
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

        # Парсим данные - ПОДДЕРЖКА ЧИСЕЛ С ЗАПЯТЫМИ
        sensor_data = {}
        for line in data_lines:
            match = re.match(r'gpio\s+(\d+)\s+([\d,]+)', line)  # ИСПРАВЛЕНО: поддержка запятых
            if match:
                gpio_num = match.group(1)
                value = match.group(2)
                sensor_data[f"GPIO{gpio_num}"] = value

        if sensor_data:
            print(f"📡 Received {len(sensor_data)} sensor values: {sensor_data}")
        else:
            print("⚠️ No sensor data parsed")

        return sensor_data if sensor_data else None

    def read_and_validate_sensor_data(self) -> Optional[Dict[str, str]]:
        """
        Чтение данных с валидацией:
        - Проверка формата
        - Проверка резких скачков
        Возвращает только валидные данные или список ошибок
        """
        raw_data = self.read_sensor_data()
        
        if raw_data is None:
            return None
        
        validated_data = {}
        errors = []
        
        for gpio, value_str in raw_data.items():
            try:
                # Заменяем запятую на точку для преобразования в float
                value_normalized = value_str.replace(',', '.')
                value = float(value_normalized)
                
                # Валидация
                is_valid, message = self.validator.validate(gpio, value)
                
                if is_valid:
                    # Округляем до 3 знаков после запятой
                    rounded_value = round(value, 3)
                    # Форматируем с запятой для отображения
                    formatted_value = f"{rounded_value:.3f}".replace('.', ',')
                    validated_data[gpio] = formatted_value
                    self.validator.add_reading(gpio, value)
                    print(f"✅ {gpio}: {formatted_value} - {message}")
                else:
                    error_msg = f"{gpio}: {value_str} - {message}"
                    errors.append(error_msg)
                    print(f"❌ {error_msg}")
                    
            except ValueError:
                error_msg = f"{gpio}: Невозможно преобразовать '{value_str}' в число"
                errors.append(error_msg)
                print(f"❌ {error_msg}")
        
        # Если есть ошибки — возвращаем их
        if errors:
            return {"errors": errors}
        
        return validated_data if validated_data else None


class TestESP32Manager:
    """Тестовый менеджер"""
    def __init__(self, baud_rate: int = 9600):
        self.baud_rate = baud_rate
        self.connected = True
        self._tick = 0
        self.frame = {
            "GPIO1": 100.0,
            "GPIO2": 200.5,
            "GPIO3": 300.75,
            "GPIO4": 400.123,
            "GPIO5": 400.999,
            "GPIO6": 423.456,
            "GPIO7": 423.001,
        }
        self.simulate_disconnection = False
        self.validator = DataValidator(window_size=5)
        self.simulate_jump = False
        self.jump_count = 0

    def connect(self) -> bool:
        self.connected = not self.simulate_disconnection
        if self.connected:
            print("✅ Test mode: connected")
        return self.connected

    def disconnect(self):
        self.connected = False
        print("🔌 Test mode: disconnected")

    def is_connected(self) -> bool:
        return self.connected

    def ensure_connection(self) -> bool:
        if not self.connected:
            print("🔄 Test mode: simulating reconnect...")
            self.connected = True
            print("✅ Test mode: reconnected")
        return self.connected

    def send_command(self, cmd: str) -> bool:
        if not self.is_connected():
            print("⚠️ Test: not connected — command ignored")
            return False
        
        print(f"[TEST] Received command: '{cmd}'")
        return True

    def read_sensor_data(self) -> Optional[Dict[str, str]]:
        if not self.is_connected():
            print("⚠️ Test: no connection — returning None")
            return None

        self._tick += 1
        
        # Для тестирования резких скачков
        if self.simulate_jump and self._tick % 10 == 0:
            self.jump_count += 1
            if self.jump_count == 1:
                print("💥 Simulating sharp jump on GPIO1...")
                return {"GPIO1": "500.0", "GPIO2": "200.5"}
        
        test_data = {}
        for gpio, base_value in self.frame.items():
            variation = (self._tick % 5) - 2
            # Форматируем с запятой
            test_data[gpio] = f"{base_value + variation:.3f}".replace('.', ',')
        
        print(f"[TEST] Generated data: {test_data}")
        return test_data

    def read_and_validate_sensor_data(self) -> Optional[Dict[str, str]]:
        """Тестовая валидация данных"""
        raw_data = self.read_sensor_data()
        
        if raw_data is None:
            return None
        
        validated_data = {}
        errors = []
        
        for gpio, value_str in raw_data.items():
            try:
                # Заменяем запятую на точку для преобразования в float
                value_normalized = value_str.replace(',', '.')
                value = float(value_normalized)
                is_valid, message = self.validator.validate(gpio, value)
                
                if is_valid:
                    # Округляем до 3 знаков после запятой
                    rounded_value = round(value, 3)
                    # Форматируем с запятой для отображения
                    formatted_value = f"{rounded_value:.3f}".replace('.', ',')
                    validated_data[gpio] = formatted_value
                    self.validator.add_reading(gpio, value)
                    print(f"✅ {gpio}: {formatted_value} - {message}")
                else:
                    error_msg = f"{gpio}: {value_str} - {message}"
                    errors.append(error_msg)
                    print(f"❌ {error_msg}")
                    
            except ValueError:
                error_msg = f"{gpio}: Невозможно преобразовать '{value_str}' в число"
                errors.append(error_msg)
                print(f"❌ {error_msg}")
        
        if errors:
            return {"errors": errors}
        
        return validated_data if validated_data else None