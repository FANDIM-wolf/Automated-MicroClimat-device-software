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

            self.connected = True
            return True
        except Exception as e:
            print(f"❌ ESP32 connection error: {e}")
            self.connected = False
            return False

    def disconnect(self):
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
        finally:
            self.connected = False

    def is_connected(self) -> bool:
        return self.connected

    def read_sensor_data(self) -> Optional[Dict[str, str]]:

        if not self.connected or not self.ser:
            return None

        try:
            # ждём ':'
            start_time = time.time()
            while time.time() - start_time < self.timeout:
                if self.ser.in_waiting:
                    line = self.ser.readline().decode('utf-8', errors='replace').strip()
                    if line == ':':
                        break
                time.sleep(0.01)
            else:
                return None

            # collect data until ';'
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
                return None

            sensor_data = {}
            for line in data_lines:
                match = re.match(r'gpio\s+(\d+)\s+(\d+)', line)
                if match:
                    gpio_num = match.group(1)
                    value = match.group(2)
                    sensor_data[f"GPIO{gpio_num}"] = value

            return sensor_data if sensor_data else None

        except Exception as e:
            print(f"❌ Error reading data: {e}")
            self.connected = False
            return None


class TestESP32Manager:
    """
    Test ESP32 manager for testing purposes
    """
    def __init__(self, baud_rate: int = 115200):
        self.baud_rate = baud_rate
        self.connected = True

        # Base data
        self.frame = {
            "GPIO1": 100,
            "GPIO2": 200,
            "GPIO3": 300,
            "GPIO4": 400,
            "GPIO5": 400,
            "GPIO6": 423,
            "GPIO7": 423,
        }

        # Tick counter
        self._tick = 0

    def connect(self) -> bool:
        self.connected = True
        return True

    def disconnect(self):
        self.connected = False

    def is_connected(self) -> bool:
        return self.connected

    def read_sensor_data(self) -> Optional[Dict[str, str]]:
        if not self.connected:
            return None

        # light sleep
        time.sleep(0.02)

        self._tick += 1

        # Easy data update
        data = {}
        for k, v in self.frame.items():
            data[k] = str(v + (self._tick % 5))  # 0..4

        return data
