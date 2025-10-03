"""
Heltec WiFi LoRa 32 V3 Device Implementation

Hardware:
- MCU: ESP32-S3FN8 (Xtensa 32-bit LX7 dual-core, up to 240 MHz)
- LoRa: Semtech SX1262
- RAM: 512 KB SRAM
- Flash: 8 MB
- Display: 0.96" OLED (128x64)
- Battery: Built-in LiPo management

This device implementation handles the Heltec V3-specific:
- Pin configuration
- SX1262 initialization
- OLED display (optional)
- Power management
- Battery monitoring
"""

try:
    # MicroPython imports
    from machine import Pin, SPI
    import time
    MICROPYTHON = True
except ImportError:
    # CPython fallback (for development/testing)
    MICROPYTHON = False
    import time

from ..phycore.lora import LoRaDevice


# Heltec V3 Pin Definitions (from Boards.h analysis)
HELTEC_V3_PINS = {
    # SX1262 LoRa Radio
    'lora_ss': 8,       # SPI Chip Select
    'lora_sck': 9,      # SPI Clock
    'lora_mosi': 10,    # SPI MOSI
    'lora_miso': 11,    # SPI MISO
    'lora_rst': 12,     # Reset
    'lora_busy': 13,    # Busy signal
    'lora_dio1': 14,    # Interrupt (IRQ)

    # OLED Display (0.96" 128x64)
    'oled_sda': 17,     # I2C SDA
    'oled_scl': 18,     # I2C SCL
    'oled_rst': 21,     # Reset (also used as display enable pin)
    'vext': 36,         # Vext power supply for display (CRITICAL!)

    # LED
    'led': 35,          # Status LED

    # Button
    'button': 0,        # User button

    # Battery
    'vbat_adc': 1,      # Battery voltage ADC
}

# SX1262 Configuration
SX1262_CONFIG = {
    'has_tcxo': True,           # Heltec V3 has built-in TCXO
    'dio2_as_rf_switch': True,  # Use DIO2 for automatic TX/RX switching
    'tcxo_voltage': 3.3,        # TCXO voltage
}


if MICROPYTHON:
    # Import SX1262 low-level driver
    from . import sx1262_driver

    class HeltecV3(LoRaDevice):
        """
        Heltec WiFi LoRa 32 V3 device implementation for MicroPython.

        This wraps the low-level SX1262 driver with Heltec V3-specific configuration.
        """

        def __init__(self, frequency=915_000_000, bandwidth=125_000,
                     spreading_factor=9, coding_rate=5, tx_power=14,
                     enable_display=True, enable_ble=True, device_name="Mycorrhizal"):
            """
            Initialize Heltec V3 device.

            Args:
                frequency: Frequency in Hz (default 915 MHz)
                bandwidth: Bandwidth in Hz (default 125 kHz)
                spreading_factor: SF 5-12 (default 9)
                coding_rate: CR 5-8 (default 5 = 4/5)
                tx_power: TX power in dBm (default 14)
                enable_display: Initialize OLED display (default True)
                enable_ble: Enable Bluetooth LE (default True)
                device_name: Device name for BLE advertising
            """
            super().__init__()

            self.frequency = frequency
            self.bandwidth = bandwidth
            self.spreading_factor = spreading_factor
            self.coding_rate = coding_rate
            self.tx_power = tx_power
            self.device_name = device_name

            # Initialize pins
            self.pin_led = Pin(HELTEC_V3_PINS['led'], Pin.OUT, value=0)
            self.pin_button = Pin(HELTEC_V3_PINS['button'], Pin.IN, Pin.PULL_UP)

            # Button handler for page switching / pairing
            self._last_button_press = 0
            self._button_debounce = 200  # ms

            # Initialize display first (so BLE can show pairing)
            self.display = None
            if enable_display:
                self._init_display()

            # Initialize BLE service
            self.ble = None
            if enable_ble:
                self._init_ble()

            # Initialize SX1262 driver with Heltec V3 pinout
            self.radio = sx1262_driver.SX1262(
                pin_ss=HELTEC_V3_PINS['lora_ss'],
                pin_sck=HELTEC_V3_PINS['lora_sck'],
                pin_mosi=HELTEC_V3_PINS['lora_mosi'],
                pin_miso=HELTEC_V3_PINS['lora_miso'],
                pin_rst=HELTEC_V3_PINS['lora_rst'],
                pin_busy=HELTEC_V3_PINS['lora_busy'],
                pin_dio1=HELTEC_V3_PINS['lora_dio1'],
                has_tcxo=SX1262_CONFIG['has_tcxo'],
                dio2_as_rf_switch=SX1262_CONFIG['dio2_as_rf_switch']
            )

            # Set initial configuration
            self.radio.set_frequency(frequency)
            self.radio.set_spreading_factor(spreading_factor)
            self.radio.set_bandwidth(bandwidth)
            self.radio.set_coding_rate(coding_rate)
            self.radio.set_tx_power(tx_power)

            # Set up receive callback routing
            self.radio.set_receive_callback(self._on_radio_receive)

            # Node state for display
            self.node_state = {
                'name': device_name,
                'address_hex': '0' * 32,
                'online': False,
                'uptime': 0,
                'routes': 0,
                'identities': 0,
                'tx_packets': 0,
                'rx_packets': 0,
                'tx_bytes': 0,
                'rx_bytes': 0,
                'lora': {
                    'frequency': frequency,
                    'spreading_factor': spreading_factor,
                    'bandwidth': bandwidth,
                    'tx_power': tx_power,
                    'bitrate': self.radio.calculate_bitrate(bandwidth, spreading_factor, coding_rate)
                },
                'battery': {
                    'voltage': 0.0,
                    'percent': 0,
                    'charging': False
                },
                'pairing_state': 'inactive'
            }

            # Start time for uptime
            self._start_time = time.ticks_ms()

            # RSSI sampling for waterfall
            self._last_rssi_update = 0
            self._rssi_update_interval = 1000  # Sample RSSI every 1 second

        def _init_display(self):
            """Initialize OLED display with proper Heltec V3 power sequencing"""
            try:
                # CRITICAL: Enable Vext (pin 36) to power the display
                # This MUST be done before any display initialization!
                pin_vext = Pin(HELTEC_V3_PINS['vext'], Pin.OUT)
                pin_vext.value(0)  # LOW enables Vext
                time.sleep_ms(50)

                # Enable display power (pin 21 also acts as enable)
                pin_disp_en = Pin(HELTEC_V3_PINS['oled_rst'], Pin.OUT)
                pin_disp_en.value(0)
                time.sleep_ms(50)
                pin_disp_en.value(1)
                time.sleep_ms(50)

                # Now initialize the display manager
                from ..ui.display import DisplayManager

                self.display = DisplayManager(
                    scl_pin=HELTEC_V3_PINS['oled_scl'],
                    sda_pin=HELTEC_V3_PINS['oled_sda'],
                    rst_pin=HELTEC_V3_PINS['oled_rst']
                )
                print("Display: Initialized")
            except Exception as e:
                print(f"Warning: Could not initialize display: {e}")
                self.display = None

        def _init_ble(self):
            """Initialize BLE service"""
            try:
                from ..ui.bluetooth import BLEService

                self.ble = BLEService(
                    name=self.device_name,
                    display_manager=self.display
                )
                print(f"BLE: Initialized as '{self.device_name}'")
            except Exception as e:
                print(f"Warning: Could not initialize BLE: {e}")
                self.ble = None

        def check_button(self):
            """Check button press for actions"""
            if self.pin_button.value() == 0:  # Button pressed (active low)
                now = time.ticks_ms()
                if time.ticks_diff(now, self._last_button_press) > self._button_debounce:
                    self._last_button_press = now
                    self._handle_button_press()

        def _handle_button_press(self):
            """Handle button press"""
            # Short press: Next page
            # Long press (hold): Enable BLE pairing

            # For now, just cycle pages
            if self.display:
                self.display.next_page()
                print("Button: Next page")

            # TODO: Add long-press detection for pairing

        def enable_pairing(self):
            """Enable BLE pairing mode"""
            if self.ble:
                self.ble.enable_pairing()
                self.node_state['pairing_state'] = 'waiting'

        def update(self, node=None):
            """
            Update device state and display.

            Args:
                node: Node instance (optional, for stats)
            """
            now = time.ticks_ms()

            # Poll radio for received packets (call frequently)
            if self.radio.poll_receive():
                print("[Heltec] Packet received!")

            # Update uptime
            self.node_state['uptime'] = time.ticks_diff(now, self._start_time) // 1000

            # Update from node if provided
            if node:
                self.node_state['address_hex'] = node.identity.address_hex()
                self.node_state['online'] = any(p.online for p in node.phycores)
                self.node_state['routes'] = node.route_table.size()
                self.node_state['identities'] = node.identity_cache.size()

                # Get TX/RX stats from phycores (SET, don't add!)
                tx_packets = 0
                tx_bytes = 0
                rx_packets = 0
                rx_bytes = 0
                for phycore in node.phycores:
                    tx_packets += phycore.tx_count
                    tx_bytes += phycore.tx_bytes
                    rx_packets += phycore.rx_count
                    rx_bytes += phycore.rx_bytes

                self.node_state['tx_packets'] = tx_packets
                self.node_state['tx_bytes'] = tx_bytes
                self.node_state['rx_packets'] = rx_packets
                self.node_state['rx_bytes'] = rx_bytes

            # Sample RSSI every second for waterfall display
            if time.ticks_diff(now, self._last_rssi_update) >= self._rssi_update_interval:
                rssi = self.radio.get_rssi()
                if rssi is not None and self.display:
                    self.display.update_waterfall(rssi)
                self._last_rssi_update = now

            # Update BLE state for display
            if self.ble:
                self.node_state['ble_state'] = self.ble.get_state()
                self.ble.check_pairing_timeout()
            else:
                self.node_state['ble_state'] = 'off'

            # Update display
            if self.display:
                self.display.update(self.node_state)

            # Check button
            self.check_button()

        def _on_radio_receive(self, data):
            """Internal callback from radio, routes to phycore"""
            # Mark RX activity on display
            if self.display:
                self.display.mark_rx()

            if self.receive_callback:
                self.receive_callback(data)

        def start(self):
            """Start radio"""
            success = self.radio.start()
            if success:
                self.pin_led.value(1)  # LED on when online
            return success

        def stop(self):
            """Stop radio"""
            self.radio.stop()
            self.pin_led.value(0)  # LED off

        def send(self, data):
            """Transmit data"""
            # Mark TX activity on display
            if self.display:
                self.display.mark_tx()

            return self.radio.send(data)

        def get_bitrate(self):
            """Get current bitrate"""
            return self.radio.calculate_bitrate(
                self.bandwidth,
                self.spreading_factor,
                self.coding_rate
            )

        def get_config(self):
            """Get current configuration"""
            return {
                'frequency': self.frequency,
                'bandwidth': self.bandwidth,
                'spreading_factor': self.spreading_factor,
                'coding_rate': self.coding_rate,
                'tx_power': self.tx_power,
                'device': 'Heltec WiFi LoRa 32 V3',
                'mcu': 'ESP32-S3',
                'radio': 'SX1262'
            }

        def set_config(self, **kwargs):
            """Update configuration"""
            updated = False

            if 'frequency' in kwargs:
                self.frequency = kwargs['frequency']
                self.radio.set_frequency(self.frequency)
                updated = True

            if 'spreading_factor' in kwargs:
                self.spreading_factor = kwargs['spreading_factor']
                self.radio.set_spreading_factor(self.spreading_factor)
                updated = True

            if 'bandwidth' in kwargs:
                self.bandwidth = kwargs['bandwidth']
                self.radio.set_bandwidth(self.bandwidth)
                updated = True

            if 'tx_power' in kwargs:
                self.tx_power = kwargs['tx_power']
                self.radio.set_tx_power(self.tx_power)
                updated = True

            return updated

        def get_config_string(self):
            """Get human-readable configuration"""
            return (f"Heltec V3: {self.frequency / 1e6:.1f} MHz, "
                   f"SF{self.spreading_factor}, BW{self.bandwidth / 1000:.0f}kHz")

        def get_stats(self):
            """Get device statistics"""
            return {
                'device': 'Heltec V3',
                'radio': self.radio.get_stats() if hasattr(self.radio, 'get_stats') else {}
            }

else:
    # CPython stub for development/testing
    class HeltecV3(LoRaDevice):
        """CPython stub for Heltec V3 (for development without hardware)"""

        def __init__(self, **kwargs):
            super().__init__()
            self.config = kwargs
            print("Warning: Using CPython stub for Heltec V3 (no actual radio)")

        def start(self):
            print("Heltec V3 stub: start()")
            return True

        def stop(self):
            print("Heltec V3 stub: stop()")

        def send(self, data):
            print(f"Heltec V3 stub: send({len(data)} bytes)")
            return True

        def get_bitrate(self):
            return self.config.get('bandwidth', 125000) * self.config.get('spreading_factor', 9) / (2 ** 9)

        def get_config(self):
            return self.config

        def set_config(self, **kwargs):
            self.config.update(kwargs)
            return True

        def get_config_string(self):
            return "Heltec V3 (stub)"
