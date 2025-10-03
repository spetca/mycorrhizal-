"""
Display Manager for Mycorrhizal Devices

RNode-inspired display system showing:
- Device info (name, address, firmware version)
- Network stats (packets, routes, neighbors)
- LoRa parameters (freq, SF, BW, power)
- BLE pairing codes
- Battery status
- Uptime

Supports:
- SSD1306 OLED (128x64) - Heltec V3, most boards
- SH1106 OLED (128x64) - Some boards
- ST7789 TFT - T-Deck, T114
- E-Ink - T-Echo
"""

try:
    from machine import Pin, I2C
    import framebuf
    import time
    MICROPYTHON = True
except ImportError:
    MICROPYTHON = False
    import time


class DisplayPage:
    """Base class for display pages"""
    def __init__(self, name):
        self.name = name

    def draw(self, display, node_state):
        """
        Draw this page.

        Args:
            display: Display instance
            node_state: dict with current node state
        """
        raise NotImplementedError()


class InfoPage(DisplayPage):
    """Device information page with RNode-style spectrum and activity"""
    def __init__(self):
        super().__init__("Info")

    def draw(self, display, node_state):
        display.fill(0)

        # Header with device name
        name = node_state.get('name', 'Unknown')[:10]
        display.text(name, 0, 0, 1)

        # Status icons (top right)
        # BLE status icon
        ble_state = node_state.get('ble_state', 'off')
        if ble_state == 'connected':
            display.text("B", 110, 0, 1)  # B for Bluetooth connected
        elif ble_state == 'on':
            display.text("b", 110, 0, 1)  # lowercase b for on but not connected

        # Online status
        online = node_state.get('online', False)
        if online:
            display.fill_rect(120, 0, 8, 8, 1)  # Solid square = online
        else:
            display.rect(120, 0, 8, 8, 1)  # Hollow square = offline

        # Full address (2 lines, 16 chars each for 32 char hex)
        address = node_state.get('address_hex', 'N/A')
        if len(address) >= 32:
            display.text(address[:16], 0, 10, 1)
            display.text(address[16:32], 0, 18, 1)
        else:
            display.text(address[:16], 0, 10, 1)

        # LoRa info
        lora = node_state.get('lora', {})
        freq = lora.get('frequency', 0) / 1_000_000
        sf = lora.get('spreading_factor', 0)
        display.text(f"{freq:.1f}MHz SF{sf}", 0, 28, 1)

        # Spectrum waterfall (smaller - 16px high, 64px wide)
        waterfall = node_state.get('waterfall', [])
        if waterfall:
            _draw_waterfall(display, 0, 48, 64, 16, waterfall)

        # TX/RX stats next to waterfall
        tx_pkts = node_state.get('tx_packets', 0)
        rx_pkts = node_state.get('rx_packets', 0)

        # TX/RX activity indicators (blips)
        tx_activity = node_state.get('tx_activity', False)
        rx_activity = node_state.get('rx_activity', False)

        if tx_activity:
            display.fill_rect(66, 48, 4, 4, 1)  # TX blip
        display.text(f"T:{tx_pkts}", 70, 48, 1)

        if rx_activity:
            display.fill_rect(66, 56, 4, 4, 1)  # RX blip
        display.text(f"R:{rx_pkts}", 70, 56, 1)

        display.show()


class NetworkPage(DisplayPage):
    """Network statistics page"""
    def __init__(self):
        super().__init__("Network")

    def draw(self, display, node_state):
        display.fill(0)

        # Header
        display.text("NETWORK STATS", 0, 0, 1)

        # Routes
        routes = node_state.get('routes', 0)
        display.text(f"Routes: {routes}", 0, 12, 1)

        # Identities
        identities = node_state.get('identities', 0)
        display.text(f"IDs: {identities}", 0, 22, 1)

        # TX/RX packets
        tx_pkts = node_state.get('tx_packets', 0)
        rx_pkts = node_state.get('rx_packets', 0)
        display.text(f"TX: {tx_pkts}", 0, 32, 1)
        display.text(f"RX: {rx_pkts}", 0, 42, 1)

        # TX/RX bytes
        tx_bytes = node_state.get('tx_bytes', 0)
        rx_bytes = node_state.get('rx_bytes', 0)
        tx_kb = tx_bytes // 1024
        rx_kb = rx_bytes // 1024
        display.text(f"{tx_kb}KB / {rx_kb}KB", 0, 52, 1)

        display.show()


class LoRaPage(DisplayPage):
    """LoRa configuration page"""
    def __init__(self):
        super().__init__("LoRa")

    def draw(self, display, node_state):
        display.fill(0)

        # Header
        display.text("LORA CONFIG", 0, 0, 1)

        lora = node_state.get('lora', {})

        # Frequency
        freq = lora.get('frequency', 0) / 1_000_000
        display.text(f"Freq: {freq:.1f}MHz", 0, 12, 1)

        # SF and BW
        sf = lora.get('spreading_factor', 0)
        bw = lora.get('bandwidth', 0) / 1000
        display.text(f"SF{sf} BW{bw:.0f}k", 0, 22, 1)

        # TX Power
        tx_power = lora.get('tx_power', 0)
        display.text(f"Power: {tx_power}dBm", 0, 32, 1)

        # Bitrate
        bitrate = lora.get('bitrate', 0)
        display.text(f"Rate: {bitrate}bps", 0, 42, 1)

        # RSSI (if available)
        rssi = lora.get('rssi', None)
        if rssi:
            display.text(f"RSSI: {rssi}dBm", 0, 52, 1)

        display.show()


class PairingPage(DisplayPage):
    """Bluetooth pairing page"""
    def __init__(self):
        super().__init__("Pairing")

    def draw(self, display, node_state):
        display.fill(0)

        # Header
        display.text("BLE STATUS", 0, 0, 1)

        pairing_state = node_state.get('pairing_state', 'inactive')
        ble_state = node_state.get('ble_state', 'off')

        if pairing_state == 'waiting':
            display.text("Waiting for", 0, 16, 1)
            display.text("connection...", 0, 28, 1)

        elif pairing_state == 'pin':
            # Large PIN display
            pin = node_state.get('pairing_pin', '000000')
            display.text("Enter PIN:", 0, 16, 1)

            # Draw PIN in large font (simulate with spacing)
            display.text(pin[:3], 20, 32, 1)
            display.text(pin[3:], 20, 44, 1)

        elif pairing_state == 'success':
            display.text("PAIRED!", 28, 24, 1)
            display.text("Successfully", 12, 40, 1)

        elif pairing_state == 'failed':
            display.text("PAIRING", 24, 24, 1)
            display.text("FAILED", 28, 40, 1)

        else:  # inactive - show actual BLE state
            if ble_state == 'connected':
                display.text("BLE: Connected", 0, 16, 1)
                display.text("Client active", 0, 32, 1)
            elif ble_state == 'on':
                display.text("BLE: Ready", 0, 16, 1)
                display.text("Waiting for", 0, 28, 1)
                display.text("connection...", 0, 40, 1)
            else:
                display.text("BLE: Disabled", 0, 16, 1)
                display.text("(Not enabled", 0, 28, 1)
                display.text("in code)", 0, 40, 1)

        display.show()


class BatteryPage(DisplayPage):
    """Battery status page"""
    def __init__(self):
        super().__init__("Battery")

    def draw(self, display, node_state):
        display.fill(0)

        # Header
        display.text("BATTERY", 0, 0, 1)

        battery = node_state.get('battery', {})

        # Voltage
        voltage = battery.get('voltage', 0.0)
        display.text(f"Voltage: {voltage:.2f}V", 0, 12, 1)

        # Percentage
        percent = battery.get('percent', 0)
        display.text(f"Level: {percent}%", 0, 22, 1)

        # Charging status
        charging = battery.get('charging', False)
        status = "CHARGING" if charging else "DISCHARGING"
        display.text(f"Status: {status}", 0, 32, 1)

        # Battery bar graph
        bar_width = int(128 * percent / 100)
        display.rect(0, 48, 128, 12, 1)
        display.fill_rect(2, 50, bar_width - 4, 8, 1)

        display.show()


# Helper functions

def _draw_waterfall(display, x, y, width, height, waterfall_data):
    """
    Draw spectrum waterfall display.

    Each column represents one time sample. Bars grow from bottom up.
    Taller bars = stronger signal.

    Args:
        display: Display object
        x, y: Top-left corner
        width, height: Dimensions (typically 64x16)
        waterfall_data: List of RSSI values 0-14 (older at start, newer at end)
    """
    if not waterfall_data:
        return

    # Draw border
    display.rect(x, y, width, height, 1)

    # Each waterfall entry can be:
    # - Positive number (0-14): RSSI strength, height of bar in pixels
    # - -1: TX indicator (draw dotted pattern)
    # - 0: No signal / idle

    # Calculate how many samples fit in width
    num_samples = min(len(waterfall_data), width - 2)
    if num_samples == 0:
        return

    # Draw rightmost (newest) samples
    for i in range(num_samples):
        sample_idx = len(waterfall_data) - num_samples + i
        sample = waterfall_data[sample_idx]

        px = x + 1 + i

        if sample == -1:
            # TX indicator - draw dotted pattern (full height)
            for py in range(y + 1, y + height - 1, 2):
                display.pixel(px, py, 1)
        elif sample > 0:
            # RSSI bar - scale to available height
            bar_height = min(int(sample), height - 2)
            for py in range(height - 2 - bar_height, height - 2):
                display.pixel(px, y + 1 + py, 1)

def _format_uptime(seconds):
    """Format uptime in human-readable form"""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m"
    elif seconds < 86400:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h{minutes}m"
    else:
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        return f"{days}d{hours}h"


# Display manager

if MICROPYTHON:
    import ssd1306

    class DisplayManager:
        """
        Display manager for Mycorrhizal devices.

        Manages multiple pages and handles page switching.
        """

        def __init__(self, scl_pin, sda_pin, rst_pin=None, address=0x3C,
                     width=128, height=64):
            """
            Initialize display manager.

            Args:
                scl_pin: I2C SCL pin number
                sda_pin: I2C SDA pin number
                rst_pin: Reset pin number (optional)
                address: I2C address (default 0x3C)
                width: Display width (default 128)
                height: Display height (default 64)
            """
            self.width = width
            self.height = height

            # Reset display first if pin provided
            if rst_pin is not None:
                rst = Pin(rst_pin, Pin.OUT)
                rst.value(0)
                time.sleep_ms(50)
                rst.value(1)
                time.sleep_ms(50)

            # Initialize I2C with proper frequency
            self.i2c = I2C(0, scl=Pin(scl_pin), sda=Pin(sda_pin), freq=400000)

            # Initialize display
            self.display = ssd1306.SSD1306_I2C(width, height, self.i2c, addr=address)

            # Pages
            self.pages = [
                InfoPage(),
                NetworkPage(),
                LoRaPage(),
                PairingPage(),
                BatteryPage()
            ]
            self.current_page = 0
            self.last_update = 0
            self.update_interval = 50  # 50ms for smooth updates (20 fps)

            # Waterfall data (RNode-style spectrum display)
            self.waterfall_data = []
            self.waterfall_max_size = 62  # 64 pixels wide minus border
            self.last_rssi = -135

            # Activity tracking
            self.tx_activity = False
            self.rx_activity = False
            self.activity_timeout = 500  # ms to keep activity indicator on
            self.last_tx_time = 0
            self.last_rx_time = 0

            # Boot screen
            self.show_boot_screen()

        def show_boot_screen(self):
            """Show boot screen"""
            self.display.fill(0)
            self.display.text("MYCORRHIZAL", 16, 20, 1)
            self.display.text("Loading...", 24, 40, 1)
            self.display.show()
            time.sleep_ms(1000)

        def next_page(self):
            """Switch to next page"""
            self.current_page = (self.current_page + 1) % len(self.pages)
            self.update(force=True)

        def prev_page(self):
            """Switch to previous page"""
            self.current_page = (self.current_page - 1) % len(self.pages)
            self.update(force=True)

        def update(self, node_state=None, force=False):
            """
            Update display if enough time has passed.

            Args:
                node_state: dict with current node state
                force: Force update even if interval hasn't passed
            """
            now = time.ticks_ms()
            if force or time.ticks_diff(now, self.last_update) > self.update_interval:
                if node_state is None:
                    node_state = {}

                # Update activity indicators (fade out after timeout)
                if time.ticks_diff(now, self.last_tx_time) < self.activity_timeout:
                    self.tx_activity = True
                else:
                    self.tx_activity = False

                if time.ticks_diff(now, self.last_rx_time) < self.activity_timeout:
                    self.rx_activity = True
                else:
                    self.rx_activity = False

                # Add activity and waterfall to node_state
                node_state['tx_activity'] = self.tx_activity
                node_state['rx_activity'] = self.rx_activity
                node_state['waterfall'] = self.waterfall_data

                page = self.pages[self.current_page]
                page.draw(self.display, node_state)

                self.last_update = now

        def update_waterfall(self, rssi):
            """
            Update spectrum waterfall with new RSSI reading.

            Args:
                rssi: RSSI value in dBm (e.g., -135 to -30)
            """
            # Normalize RSSI to 0-14 scale (waterfall height is 16px, minus 2 for border)
            # -135 dBm (weak signal) -> 0-2
            # -100 dBm (medium) -> 5-7
            # -60 dBm (strong) -> 10-12
            # -30 dBm (very strong) -> 14
            rssi_min = -135
            rssi_max = -30
            waterfall_height = 14  # Available height for bars (16 - 2 border)

            # Clamp and normalize
            rssi_clamped = max(rssi_min, min(rssi_max, rssi))
            rssi_normalized = int(((rssi_clamped - rssi_min) / (rssi_max - rssi_min)) * waterfall_height)

            self.waterfall_data.append(rssi_normalized)

            # Keep waterfall size limited
            if len(self.waterfall_data) > self.waterfall_max_size:
                self.waterfall_data.pop(0)

            self.last_rssi = rssi

        def mark_tx(self):
            """Mark TX activity"""
            self.last_tx_time = time.ticks_ms()

        def mark_rx(self):
            """Mark RX activity"""
            self.last_rx_time = time.ticks_ms()

        def show_pairing_pin(self, pin):
            """Show pairing PIN (switch to pairing page)"""
            self.current_page = 3  # Pairing page
            state = {'pairing_state': 'pin', 'pairing_pin': str(pin)}
            self.pages[3].draw(self.display, state)

        def show_pairing_success(self):
            """Show pairing success"""
            state = {'pairing_state': 'success'}
            self.pages[3].draw(self.display, state)
            time.sleep_ms(2000)

        def show_pairing_failed(self):
            """Show pairing failed"""
            state = {'pairing_state': 'failed'}
            self.pages[3].draw(self.display, state)
            time.sleep_ms(2000)

        def clear(self):
            """Clear display"""
            self.display.fill(0)
            self.display.show()

        def text(self, string, x, y, color=1):
            """Draw text"""
            self.display.text(string, x, y, color)

        def show(self):
            """Update display"""
            self.display.show()

else:
    # CPython stub
    class DisplayManager:
        """CPython stub for development"""

        def __init__(self, *args, **kwargs):
            print("DisplayManager: CPython stub (no actual display)")
            self.pages = []
            self.current_page = 0

        def show_boot_screen(self):
            print("Display: Boot screen")

        def next_page(self):
            print("Display: Next page")

        def prev_page(self):
            print("Display: Previous page")

        def update(self, node_state=None, force=False):
            pass

        def show_pairing_pin(self, pin):
            print(f"Display: Pairing PIN = {pin}")

        def show_pairing_success(self):
            print("Display: Pairing success")

        def show_pairing_failed(self):
            print("Display: Pairing failed")

        def clear(self):
            pass

        def text(self, string, x, y, color=1):
            pass

        def show(self):
            pass
