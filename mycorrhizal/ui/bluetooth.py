"""
Bluetooth LE GATT Service for Mycorrhizal

Provides BLE GATT service similar to Meshtastic/RNode:
- Auto-discovery (appears in BLE scan)
- Pairing with PIN display on device
- Serial-like communication over BLE
- Configuration interface

BLE GATT Service Structure:
- Service UUID: 6E400001-B5A3-F393-E0A9-E50E24DCCA9E (Nordic UART Service)
  - TX Characteristic: 6E400002-B5A3-F393-E0A9-E50E24DCCA9E (write)
  - RX Characteristic: 6E400003-B5A3-F393-E0A9-E50E24DCCA9E (notify)

This is the same UUID as used by Adafruit/Nordic/Meshtastic for broad compatibility.
"""

try:
    import ubluetooth
    from micropython import const
    import struct
    import time
    MICROPYTHON = True
except ImportError:
    MICROPYTHON = False


if MICROPYTHON:
    # BLE Constants
    _IRQ_CENTRAL_CONNECT = const(1)
    _IRQ_CENTRAL_DISCONNECT = const(2)
    _IRQ_GATTS_WRITE = const(3)
    _IRQ_GATTS_READ_REQUEST = const(4)
    _IRQ_MTU_EXCHANGED = const(21)

    # Nordic UART Service (compatible with nRF Connect, Adafruit Bluefruit, etc.)
    _UART_UUID = ubluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
    _UART_TX = ubluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E")  # Client writes here
    _UART_RX = ubluetooth.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E")  # Client reads here

    _UART_SERVICE = (
        _UART_UUID,
        (
            (_UART_TX, ubluetooth.FLAG_WRITE),
            (_UART_RX, ubluetooth.FLAG_READ | ubluetooth.FLAG_NOTIFY),
        ),
    )

    class BLEService:
        """
        BLE GATT Service for Mycorrhizal.

        Provides serial-like communication over BLE for configuration
        and monitoring.
        """

        def __init__(self, name="Mycorrhizal", display_manager=None):
            """
            Initialize BLE service.

            Args:
                name: Device name (max 29 chars, will show in BLE scan)
                display_manager: Display manager for showing pairing PIN
            """
            self.name = name[:29]  # BLE name limit
            self.display = display_manager

            self._ble = ubluetooth.BLE()
            self._ble.active(True)
            self._ble.irq(self._irq_handler)

            # Register GATT service
            ((self._tx_handle, self._rx_handle),) = self._ble.gatts_register_services(
                (_UART_SERVICE,)
            )

            # State
            self._connections = set()
            self._pairing_enabled = False
            self._pairing_started = 0
            self._pairing_pin = None
            self._rx_buffer = bytearray()
            self._write_callback = None
            self._connected = False
            self._state = 'on'  # 'on', 'connected', 'off'

            # MTU
            self._mtu = 23  # Default BLE MTU, will be updated on exchange

            # Pairing timeout
            self._pairing_timeout = 35000  # 35 seconds

            # Start advertising
            self._advertise()

        def _irq_handler(self, event, data):
            """Handle BLE IRQ events"""
            if event == _IRQ_CENTRAL_CONNECT:
                conn_handle, _, _ = data
                self._connections.add(conn_handle)
                self._connected = True
                self._state = 'connected'
                print(f"BLE: Client connected (handle={conn_handle})")

                # If pairing enabled, generate PIN
                if self._pairing_enabled:
                    self._generate_pairing_pin()

            elif event == _IRQ_CENTRAL_DISCONNECT:
                conn_handle, _, _ = data
                if conn_handle in self._connections:
                    self._connections.remove(conn_handle)
                self._connected = False
                self._state = 'on' if self._ble.active() else 'off'
                print(f"BLE: Client disconnected (handle={conn_handle})")

                # Restart advertising
                self._advertise()

            elif event == _IRQ_GATTS_WRITE:
                conn_handle, attr_handle = data
                if attr_handle == self._tx_handle:
                    # Client wrote data
                    data = self._ble.gatts_read(self._tx_handle)
                    self._rx_buffer.extend(data)

                    # Call write callback if set
                    if self._write_callback:
                        self._write_callback(bytes(data))

            elif event == _IRQ_MTU_EXCHANGED:
                conn_handle, mtu = data
                self._mtu = mtu
                print(f"BLE: MTU exchanged = {mtu}")

        def _advertise(self, interval_us=100000):
            """
            Start BLE advertising.

            Args:
                interval_us: Advertising interval in microseconds (default 100ms = fast discovery)
            """
            try:
                # Make sure BLE is active
                if not self._ble.active():
                    self._ble.active(True)
                    time.sleep_ms(100)

                # Advertising data (flags + name)
                name_bytes = self.name.encode('utf-8')

                # Build advertising data with proper formatting
                adv_data = bytearray([
                    0x02, 0x01, 0x06,  # Flags: General discoverable, BR/EDR not supported
                    len(name_bytes) + 1, 0x09  # Complete local name type
                ]) + name_bytes

                # Scan response with service UUID
                # Add Nordic UART Service UUID to make it easier to find
                service_uuid = bytes.fromhex("6E400001B5A3F393E0A9E50E24DCCA9E")
                resp_data = bytearray([
                    0x11, 0x07  # 128-bit service UUID list (complete)
                ]) + service_uuid

                self._ble.gap_advertise(interval_us, adv_data=adv_data, resp_data=resp_data)
                print(f"BLE: Advertising as '{self.name}' (interval={interval_us}us)")
            except Exception as e:
                print(f"BLE: Advertising failed: {e}")

        def _generate_pairing_pin(self):
            """Generate 6-digit pairing PIN"""
            import urandom
            self._pairing_pin = urandom.randint(100000, 999999)
            self._pairing_started = time.ticks_ms()

            print(f"BLE: Pairing PIN = {self._pairing_pin}")

            # Show on display
            if self.display:
                self.display.show_pairing_pin(self._pairing_pin)

        def enable_pairing(self):
            """Enable pairing mode (show PIN on next connection)"""
            self._pairing_enabled = True
            self._pairing_started = time.ticks_ms()
            print("BLE: Pairing enabled")

            # Update display to show waiting
            if self.display:
                state = {'pairing_state': 'waiting'}
                self.display.pages[3].draw(self.display.display, state)

        def disable_pairing(self):
            """Disable pairing mode"""
            self._pairing_enabled = False
            self._pairing_pin = None
            print("BLE: Pairing disabled")

        def check_pairing_timeout(self):
            """Check if pairing has timed out"""
            if self._pairing_enabled:
                if time.ticks_diff(time.ticks_ms(), self._pairing_started) > self._pairing_timeout:
                    print("BLE: Pairing timeout")
                    self.disable_pairing()

                    if self.display:
                        state = {'pairing_state': 'inactive'}
                        self.display.pages[3].draw(self.display.display, state)

                    return True
            return False

        def write(self, data):
            """
            Send data to connected clients.

            Args:
                data: bytes to send

            Returns:
                bool: True if sent successfully
            """
            if not self._connected:
                return False

            # Chunk data into MTU-sized pieces
            max_chunk = self._mtu - 3  # BLE overhead
            offset = 0

            while offset < len(data):
                chunk = data[offset:offset + max_chunk]
                try:
                    for conn_handle in self._connections:
                        self._ble.gatts_notify(conn_handle, self._rx_handle, chunk)
                    offset += len(chunk)
                except OSError as e:
                    print(f"BLE write error: {e}")
                    return False

            return True

        def read(self, size=None):
            """
            Read received data.

            Args:
                size: Max bytes to read (default: all available)

            Returns:
                bytes: Received data
            """
            if size is None:
                data = bytes(self._rx_buffer)
                self._rx_buffer.clear()
            else:
                data = bytes(self._rx_buffer[:size])
                self._rx_buffer = self._rx_buffer[size:]

            return data

        def available(self):
            """Get number of bytes available to read"""
            return len(self._rx_buffer)

        def is_connected(self):
            """Check if client is connected"""
            return self._connected

        def get_state(self):
            """Get BLE state: 'off', 'on', or 'connected'"""
            return self._state

        def set_write_callback(self, callback):
            """
            Set callback for incoming data.

            Args:
                callback: function(data: bytes) called when data received
            """
            self._write_callback = callback

        def stop(self):
            """Stop BLE service"""
            self._ble.gap_advertise(None)  # Stop advertising
            self._ble.active(False)
            print("BLE: Service stopped")

else:
    # CPython stub
    class BLEService:
        """CPython stub for development"""

        def __init__(self, name="Mycorrhizal", display_manager=None):
            self.name = name
            self.display = display_manager
            self._connected = False
            self._pairing_enabled = False
            print(f"BLE: CPython stub (no actual BLE) - would advertise as '{name}'")

        def enable_pairing(self):
            self._pairing_enabled = True
            pin = 123456
            print(f"BLE: Pairing enabled, PIN = {pin}")
            if self.display:
                self.display.show_pairing_pin(pin)

        def disable_pairing(self):
            self._pairing_enabled = False
            print("BLE: Pairing disabled")

        def check_pairing_timeout(self):
            return False

        def write(self, data):
            print(f"BLE: Write {len(data)} bytes")
            return True

        def read(self, size=None):
            return b""

        def available(self):
            return 0

        def is_connected(self):
            return self._connected

        def set_write_callback(self, callback):
            pass

        def stop(self):
            print("BLE: Service stopped")
