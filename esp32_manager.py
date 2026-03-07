import time
import re
from typing import Optional, Dict

try:
    import serial
except Exception:
    serial = None


class RateCalculator:
    """
    Вычислитель скорости изменения (производной) 
    методом конечных разностей (Finite Differences).
    """
    def __init__(self):
        # Храним историю последних 3 измерений: {gpio: [(timestamp, value), ...]}
        self.history = {}

    def update_and_calculate(self, gpio: str, value: float) -> str:
        """
        Добавляет новое значение и вычисляет скорость изменения (градусов в секунду).
        """
        current_time = time.time()
        
        if gpio not in self.history:
            self.history[gpio] = []
            
        self.history[gpio].append((current_time, value))
        
        # Оставляем только последние 3 точки для центральной разности
        if len(self.history[gpio]) > 3:
            self.history[gpio].pop(0)
            
        history = self.history[gpio]
        n = len(history)
        
        if n == 1:
            return "0.00" # Недостаточно данных для скорости
            
        elif n == 2:
            # Левая (Backward) разность: (T_i - T_{i-1}) / dt
            t1, v1 = history[0]
            t2, v2 = history[1]
            dt = t2 - t1
            if dt <= 0.001: dt = 0.001
            rate = (v2 - v1) / dt
            return f"{rate:+.2f}"
            
        else: # n == 3
            # Центральная (Central) разность: (T_i - T_{i-2}) / (2*dt)
            # Она точнее левой разности, так как сглаживает локальный шум
            t0, v0 = history[0]
            t2, v2 = history[2]
            
            dt_total = t2 - t0
            if dt_total <= 0.001: dt_total = 0.001
            
            rate = (v2 - v0) / dt_total
            return f"{rate:+.2f}"


class ESP32Manager:
    def __init__(self, port: str, baud_rate: int = 9600, timeout: float = 2.0):
        self.port = port
        self.baud_rate = baud_rate
        self.timeout = timeout
        self.ser = None
        self.connected = False
        self.known_gpios = set()
        self.rate_calculator = RateCalculator()  # Инициализируем вычислитель
        self.connect()

    def connect(self) -> bool:
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
            self.ser.reset_input_buffer()
            self.ser.write((cmd + '\n').encode('utf-8'))
            self.ser.flush()
            return True
        except Exception as e:
            print(f"❌ Send command failed: {e}")
            self.connected = False
            return False

    def read_and_validate_sensor_data(self) -> Optional[Dict[str, str]]:
        if not self.is_connected():
            return None

        if not self.send_command("GET"):
            return None

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
                    
                    if val_float == 85.0 or val_float <= -100.0:
                        print(f"❌ {gpio_name}: Аппаратная ошибка датчика ({val_float})")
                        validated_data[gpio_name] = "ERR"
                    else:
                        rounded = round(val_float, 3)
                        validated_data[gpio_name] = f"{rounded:.3f}".replace('.', ',')
                        
                        # ВЫЧИСЛЕНИЕ СКОРОСТИ
                        rate = self.rate_calculator.update_and_calculate(gpio_name, val_float)
                        print(f"📈 {gpio_name}: {val_float} °C (Скорость: {rate} °C/сек)")
                        
                except ValueError:
                    print(f"❌ {gpio_name}: Ошибка парсинга ({value_str})")
                    validated_data[gpio_name] = "ERR"

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
        self.rate_calculator = RateCalculator()

    def connect(self): return True
    def disconnect(self): self.connected = False
    def is_connected(self): return self.connected
    
    def read_and_validate_sensor_data(self) -> Optional[Dict[str, str]]:
        if not self.connected: return None
        
        self.val14 -= 0.3
        self.val15 += 0.5
        
        r14 = self.rate_calculator.update_and_calculate("GPIO14", self.val14)
        r15 = self.rate_calculator.update_and_calculate("GPIO15", self.val15)
        
        print(f"📈 [TEST] GPIO14: {self.val14:.3f} °C (Скорость: {r14} °C/сек)")
        print(f"📈 [TEST] GPIO15: {self.val15:.3f} °C (Скорость: {r15} °C/сек)")
        
        return {
            "GPIO14": f"{self.val14:.3f}".replace('.', ','),
            "GPIO15": f"{self.val15:.3f}".replace('.', ',')
        }
