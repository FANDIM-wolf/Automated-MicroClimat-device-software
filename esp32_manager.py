import time
import re
from typing import Optional, Dict

try:
    import serial
except Exception:
    serial = None

class ESP32Manager:
    def __init__(self, port: str, baud_rate: int = 9600, timeout: float = 2.0):
        self.port = port
        self.baud_rate = baud_rate
        # Таймаут 2.0 сек, потому что датчики DS18B20 измеряют температуру до 0.75 сек каждый
        self.timeout = timeout
        self.ser = None
        self.connected = False
        self.known_gpios = set()
        self.connect()

    def connect(self) -> bool:
        if serial is None:
            self.connected = False
            return False

        try:
            if self.ser and self.ser.is_open:
                self.ser.close()

            self.ser = serial.Serial(self.port, self.baud_rate, timeout=self.timeout)
            time.sleep(2)  # Пауза на перезагрузку ESP при подключении
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()

            self.connected = True
            print(f"✅ Connected to ESP32 on {self.port}")
            return True
        except Exception as e:
            print(f"❌ Connection error: {e}")
            self.connected = False
            return False

    def disconnect(self):
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
        finally:
            self.connected = False
            print("🔌 ESP32 disconnected")

    def is_connected(self) -> bool:
        return self.connected and self.ser is not None and self.ser.is_open

    def send_command(self, cmd: str) -> bool:
        if not self.is_connected():
            return False
        try:
            # Очищаем буфер от старых данных перед запросом новых
            self.ser.reset_input_buffer()
            self.ser.write((cmd + '\n').encode('utf-8'))
            self.ser.flush()
            return True
        except Exception as e:
            print(f"❌ Send command failed: {e}")
            self.connected = False
            return False

    def read_and_validate_sensor_data(self) -> Optional[Dict[str, str]]:
        """
        Прямое чтение без буферизации.
        Шлет GET -> ждет пакет -> парсит -> отдает.
        """
        if not self.is_connected():
            return None

        # 1. Отправляем запрос
        if not self.send_command("GET"):
            return None

        # 2. Ждем стартовый маркер ':'
        start_time = time.time()
        while time.time() - start_time < self.timeout:
            if self.ser.in_waiting:
                line = self.ser.readline().decode('utf-8', errors='replace').strip()
                if line == ':':
                    break
            time.sleep(0.01)
        else:
            print("⚠️ Timeout waiting for ':'")
            return None

        # 3. Собираем данные до конечного маркера ';'
        data_lines = []
        start_time = time.time()
        while time.time() - start_time < self.timeout:
            if self.ser.in_waiting:
                line = self.ser.readline().decode('utf-8', errors='replace').strip()
                if line == ';':
                    break
                if line and line != ',':
                    data_lines.append(line)
            time.sleep(0.01)
        else:
            print("⚠️ Timeout waiting for ';'")
            return None

        # 4. Парсинг и валидация
        validated_data = {}
        parsed_gpios = set()
        
        for line in data_lines:
            match = re.match(r'gpio\s+(\d+)\s+([\d.,-]+)', line)
            if match:
                gpio_num = match.group(1)
                value_str = match.group(2)
                gpio_name = f"GPIO{gpio_num}"
                parsed_gpios.add(gpio_name)
                self.known_gpios.add(gpio_name)
                
                try:
                    val_float = float(value_str.replace(',', '.'))
                    
                    # Фильтруем физические ошибки датчика DS18B20
                    if val_float == 85.0 or val_float <= -100.0:
                        print(f"❌ {gpio_name}: Аппаратная ошибка датчика ({val_float})")
                        validated_data[gpio_name] = "ERR"
                    else:
                        rounded = round(val_float, 3)
                        validated_data[gpio_name] = f"{rounded:.3f}".replace('.', ',')
                except ValueError:
                    print(f"❌ {gpio_name}: Ошибка парсинга ({value_str})")
                    validated_data[gpio_name] = "ERR"

        # 5. Если какой-то датчик пропал, ставим NaN
        for gpio in self.known_gpios:
            if gpio not in parsed_gpios:
                validated_data[gpio] = "NaN"

        return validated_data if validated_data else None


class TestESP32Manager:
    """Тестовая заглушка для запуска без платы"""
    def __init__(self, baud_rate: int = 9600):
        self.connected = True
        self.known_gpios = set(["GPIO14", "GPIO15"])
        self.val14 = 25.0
        self.val15 = 25.0

    def connect(self): return True
    def disconnect(self): self.connected = False
    def is_connected(self): return self.connected
    
    def read_and_validate_sensor_data(self) -> Optional[Dict[str, str]]:
        if not self.connected: return None
        
        # Имитируем падение температуры
        self.val14 -= 0.3
        self.val15 -= 0.5
        
        return {
            "GPIO14": f"{self.val14:.3f}".replace('.', ','),
            "GPIO15": f"{self.val15:.3f}".replace('.', ',')
        }

