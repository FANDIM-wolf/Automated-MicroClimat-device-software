# Automated MicroClimat Device Software

Desktop acquisition software and ESP32 firmware for an automated microclimate monitoring
device. Built for large-scale collection of experimental data when identifying and modelling
dynamic thermal systems, at a fraction of the cost of industrial data loggers.

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue)](https://www.python.org/)
[![PyQt6](https://img.shields.io/badge/GUI-PyQt6-41CD52)](https://pypi.org/project/PyQt6/)
[![IEEE Xplore](https://img.shields.io/badge/paper-IEEE%20Xplore-00629B)](https://ieeexplore.ieee.org/document/11302387)

---

## Overview

The number of measurement points in a thermal experiment drives both hardware cost and data
volume. This project provides a scalable, low-cost alternative: an ESP32-based measurement
node with DS18B20 digital temperature sensors, plus a PyQt6 desktop application that polls
the node on a fixed interval, tabulates and plots the readings in real time, and exports them
to CSV.

The host application runs with or without hardware attached: a built-in simulator lets you
exercise the whole UI, plotting and export path with no device connected.

## Features

**Acquisition**
- COM port selected at startup from a dialog listing all detected ports, plus a
  `TEST (no device)` entry that starts the simulator.
- Polling interval entered as `hh:mm:ss`; a `QTimer` issues one request per tick.
- Sensor columns are discovered dynamically — a new GPIO appearing in the data stream adds a
  table column, a plot line and a statistics panel at runtime, with no restart.
- Automatic reconnection: on a failed read the app stops collection, retries the port every
  5 seconds, and resumes acquisition automatically once the link is back.

**Validation**
- Readings are parsed with the pattern `gpio <number> <value>`; both `.` and `,` are accepted
  as the decimal separator.
- Known DS18B20 failure codes are caught: a value of exactly `85.0` (power-on reset value) or
  anything at or below `-100.0` is recorded as `ERR` instead of being treated as a measurement.
- A sensor that has been seen before but is missing from the current response is recorded as
  `NaN`, so gaps stay visible in the exported data.

**Rate estimation**
`RateCalculator` keeps the last three samples per sensor and estimates dT/dt by finite
differences — a backward difference from two samples, and a central difference once three are
available, which is more accurate and smooths local noise.

**Visualisation and export**
- *Table View* tab: date, time and one column per sensor, values to one decimal.
- *Real-Time Plots* tab: pyqtgraph line chart with a rolling window of the last 100 samples,
  plus a per-sensor panel showing current, min, max, mean and rate of change.
- `Save CSV` writes the full table to `datas.csv` (semicolon-delimited, comma decimal
  separator — opens directly in a Russian-locale Excel).
- `Save Plot` exports the chart to PNG/JPG through `pyqtgraph.exporters.ImageExporter`.
- On startup the app loads `data_file.csv` if present, so a previous session is restored.

## Project structure

| Path | Purpose |
|---|---|
| `main.py` | **Entry point.** PyQt6 application: tabbed UI, timers, table and plot management, CSV and image export |
| `esp32_manager.py` | `ESP32Manager` (pyserial transport, request/response protocol, validation), `RateCalculator` (finite-difference derivative), `TestESP32Manager` (hardware-free simulator) |
| `timer_manager.py` | Thin `QTimer` wrapper for interval-based polling |
| `ESP32/main.cpp` | Arduino firmware: two DS18B20 sensors via the GyverDS18 library, 12-bit resolution, serial output at 9600 baud |
| `Logic.xlsx` | Supporting logic/design table |
| `test/` | Test fixtures |

## Serial protocol

The host is the master; the device answers on request.

```
host  -> "GET\n"
device -> ":"                  start-of-frame marker
device -> "gpio 15 24.75"      one line per sensor
device -> "gpio 14 25.31"
device -> ";"                  end-of-frame marker
```

Three service tokens — start of frame, separator and end of frame — make the stream
unambiguous to parse regardless of how many sensors are attached or in which order they were
connected. The host waits up to 2 seconds for each marker and abandons the frame on timeout.

> **Known issue — firmware/host mismatch.** The firmware currently in `ESP32/main.cpp` does
> *not* emit the `:` and `;` markers: on any received byte it simply prints the two sensor
> lines. Against this firmware `read_and_validate_sensor_data()` will time out waiting for the
> start marker and return no data. It also replies once per byte in the input buffer, so the
> 4-byte `GET\n` command triggers four responses. Either add the markers to the firmware
> (print `:` before the readings and `;` after, and drain the input buffer with
> `while (Serial.available()) Serial.read();`) or relax the framing in the host. Until then,
> use `TEST (no device)` mode to exercise the application.

## Hardware

Base configuration:

- ESP32 development board (chosen over STM, ATmega and ATtiny families for its
  system-on-chip integration of Wi-Fi, Bluetooth and Thread, which opens the way to wireless
  nodes without extra modules)
- DS18B20 digital temperature sensors on the 1-Wire bus (GPIO14 and GPIO15 in the reference
  firmware); DHT11 and analogue thermistors are also supported by the design, the latter
  through a voltage divider and Steinhart — Hart conversion
- 1 kΩ resistor as the heating element and a 30×30 mm cooling fan as the controlled load
- Power MOSFETs driven through **HCPL-3120-000E** optical gate drivers, providing galvanic
  isolation: ESP32 logic runs at 3.3 V, which is not enough to open the gate, while the 20 V
  load rail is unacceptable for the microcontroller
- USB Power Delivery trigger and a 15 V linear regulator, so the whole rig runs from a
  standard 20 V PD supply

Schematics were drawn in EasyEDA.

Digital sensors are preferred over thermistors: they are less susceptible to interference and
can be placed much further from the controller, whereas a thermistor reading is affected by
the resistance of the connecting wires.

## Requirements

**Host application**
- Python 3.9+
- PyQt6
- pyserial
- pyqtgraph

**Firmware**
- Arduino core for ESP32 (Arduino IDE or PlatformIO)
- [GyverDS18](https://github.com/GyverLibs/GyverDS18) library

## Installation

```bash
git clone https://github.com/FANDIM-wolf/Automated-MicroClimat-device-software.git
cd Automated-MicroClimat-device-software

python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install PyQt6 pyserial pyqtgraph

python main.py
```

On Linux, serial port access usually requires group membership:

```bash
sudo usermod -a -G dialout $USER   # log out and back in
```

## Quick test

**Without hardware** — the fastest way to verify the build:

1. Run `python main.py`.
2. In the port dialog choose **TEST (no device)**.
3. Enter `00:00:01` in the *Interval* field and press **Apply**, then **Start**.
4. Expected: new rows appear once per second with `GPIO14` falling by 0.3 °C and `GPIO15`
   rising by 0.5 °C per sample. The *Real-Time Plots* tab shows two diverging lines and live
   min/max/mean/rate statistics.
5. Press **Save CSV** (writes `datas.csv`) and **Save Plot** (writes a PNG) to confirm both
   export paths.

**With hardware:**

1. Flash `ESP32/main.cpp` to the board and connect it over USB.
2. Run `python main.py` and pick the port (`COM3…` on Windows, `/dev/ttyUSB0` on Linux).
3. The **Apply** and **Start** buttons turn green once the port is open; red or grey means no
   connection.
4. Warm one sensor by hand — its plot line should rise and the *Rate* field should go
   positive.
5. Unplug and replug the cable: the app stops, retries every 5 seconds and resumes collection
   on its own.

## Publication

Results are published in IEEE Xplore: https://ieeexplore.ieee.org/document/11302387
