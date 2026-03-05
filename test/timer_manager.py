from PyQt6.QtCore import QTimer

class TimerManager:
    def __init__(self, interval_ms, callback):
        """
        param interval_ms: Интервал таймера в миллисекундах
        """
        self.timer = QTimer()
        self.timer.timeout.connect(callback)
        self.interval_ms = interval_ms

    def start(self):
        """Запуск таймера"""
        self.timer.start(self.interval_ms)

    def stop(self):
        """Остановка таймера"""
        self.timer.stop()

    def is_active(self):
        """Проверка активности таймера"""
        return self.timer.isActive()