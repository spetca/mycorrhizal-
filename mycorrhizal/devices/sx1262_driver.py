"""
SX1262 LoRa Radio Driver - Low-Level Operations

This is the low-level SPI driver for the Semtech SX1262 LoRa transceiver.
Device-specific implementations (Heltec V3, T-Beam, etc.) wrap this driver
with their specific pin configurations.

Based on RNode_Firmware_CE implementation by Mark Qvist.

Supports:
- LoRa modulation (spreading factors 5-12)
- Bandwidth 7.8 kHz - 500 kHz
- Frequency 150 MHz - 960 MHz
- Hardware TCXO support
- DIO2 as RF switch (automatic TX/RX switching)
"""

from machine import Pin, SPI
import time

# SX1262 OpCodes
OP_RF_FREQ = 0x86
OP_SLEEP = 0x84
OP_STANDBY = 0x80
OP_TX = 0x83
OP_RX = 0x82
OP_PA_CONFIG = 0x95
OP_SET_IRQ_FLAGS = 0x08
OP_CLEAR_IRQ_STATUS = 0x02
OP_GET_IRQ_STATUS = 0x12
OP_RX_BUFFER_STATUS = 0x13
OP_PACKET_STATUS = 0x14
OP_CURRENT_RSSI = 0x15
OP_MODULATION_PARAMS = 0x8B
OP_PACKET_PARAMS = 0x8C
OP_STATUS = 0xC0
OP_TX_PARAMS = 0x8E
OP_PACKET_TYPE = 0x8A
OP_BUFFER_BASE_ADDR = 0x8F
OP_READ_REGISTER = 0x1D
OP_WRITE_REGISTER = 0x0D
OP_DIO3_TCXO_CTRL = 0x97
OP_DIO2_RF_CTRL = 0x9D
OP_CALIBRATE = 0x89
OP_REGULATOR_MODE = 0x96
OP_CALIBRATE_IMAGE = 0x98
OP_FIFO_WRITE = 0x0E
OP_FIFO_READ = 0x1E

# IRQ Masks
IRQ_TX_DONE = 0x01
IRQ_RX_DONE = 0x02
IRQ_PREAMBLE_DET = 0x04
IRQ_HEADER_DET = 0x10
IRQ_CRC_ERROR = 0x40

# Registers
REG_OCP = 0x08E7
REG_LNA = 0x08AC
REG_SYNC_WORD_MSB = 0x0740
REG_SYNC_WORD_LSB = 0x0741

# Modes
MODE_LONG_RANGE = 0x01  # LoRa mode
MODE_STDBY_RC = 0x00
MODE_TCXO_3_3V = 0x07
MODE_IMPLICIT_HEADER = 0x01
MODE_EXPLICIT_HEADER = 0x00

# Sync word
SYNC_WORD = 0x1424

# Frequency calculation
XTAL_FREQ = 32000000
FREQ_STEP = XTAL_FREQ / (2**25)

# Bandwidth lookup
BW_TABLE = {
    7800: 0x00,
    10400: 0x08,
    15600: 0x01,
    20800: 0x09,
    31250: 0x02,
    41700: 0x0A,
    62500: 0x03,
    125000: 0x04,
    250000: 0x05,
    500000: 0x06
}


class SX1262:
    """Low-level SX1262 radio driver"""

    def __init__(self, pin_ss, pin_sck, pin_mosi, pin_miso, pin_rst, pin_busy, pin_dio1,
                 has_tcxo=True, dio2_as_rf_switch=True):
        """
        Initialize SX1262 driver.

        Args:
            pin_ss: SPI chip select pin number
            pin_sck: SPI clock pin number
            pin_mosi: SPI MOSI pin number
            pin_miso: SPI MISO pin number
            pin_rst: Reset pin number
            pin_busy: Busy signal pin number
            pin_dio1: Interrupt pin number
            has_tcxo: Enable TCXO (default True)
            dio2_as_rf_switch: Use DIO2 for RF switching (default True)
        """
        self.has_tcxo = has_tcxo
        self.dio2_as_rf_switch = dio2_as_rf_switch

        # GPIO pins
        self.pin_ss = Pin(pin_ss, Pin.OUT, value=1)
        self.pin_rst = Pin(pin_rst, Pin.OUT, value=1)
        self.pin_busy = Pin(pin_busy, Pin.IN)
        self.pin_dio1 = Pin(pin_dio1, Pin.IN)

        # SPI (8 MHz, MSB first, mode 0)
        self.spi = SPI(1, baudrate=8_000_000, polarity=0, phase=0,
                       sck=Pin(pin_sck), mosi=Pin(pin_mosi), miso=Pin(pin_miso))

        # Radio configuration
        self.frequency = 915_000_000
        self.bandwidth = 125_000
        self.spreading_factor = 9
        self.coding_rate = 5
        self.tx_power = 14

        # State
        self.fifo_tx_addr_ptr = 0
        self.fifo_rx_addr_ptr = 0
        self.receive_callback = None
        self.online = False

    # ===== Low-Level SPI Operations =====

    def _wait_on_busy(self, timeout_ms=100):
        """Wait for BUSY pin to go low"""
        start = time.ticks_ms()
        while self.pin_busy.value() == 1:
            if time.ticks_diff(time.ticks_ms(), start) > timeout_ms:
                break
            time.sleep_ms(1)

    def _execute_opcode(self, opcode, buffer=None):
        """Execute SX1262 opcode"""
        self._wait_on_busy()
        self.pin_ss.value(0)
        self.spi.write(bytes([opcode]))
        if buffer:
            self.spi.write(buffer)
        self.pin_ss.value(1)

    def _execute_opcode_read(self, opcode, length):
        """Execute opcode and read response"""
        self._wait_on_busy()
        self.pin_ss.value(0)
        self.spi.write(bytes([opcode, 0x00]))
        result = self.spi.read(length)
        self.pin_ss.value(1)
        return result

    def _read_register(self, address):
        """Read single register"""
        self._wait_on_busy()
        self.pin_ss.value(0)
        self.spi.write(bytes([
            OP_READ_REGISTER,
            (address >> 8) & 0xFF,
            address & 0xFF,
            0x00
        ]))
        value = self.spi.read(1)[0]
        self.pin_ss.value(1)
        return value

    def _write_register(self, address, value):
        """Write single register"""
        self._wait_on_busy()
        self.pin_ss.value(0)
        self.spi.write(bytes([
            OP_WRITE_REGISTER,
            (address >> 8) & 0xFF,
            address & 0xFF,
            value
        ]))
        self.pin_ss.value(1)

    # ===== Radio Operations =====

    def _reset(self):
        """Hardware reset"""
        self.pin_rst.value(0)
        time.sleep_ms(10)
        self.pin_rst.value(1)
        time.sleep_ms(10)

    def _calibrate(self):
        """Calibrate all blocks"""
        self._execute_opcode(OP_STANDBY, bytes([MODE_STDBY_RC]))
        self._execute_opcode(OP_CALIBRATE, bytes([0x7F]))
        time.sleep_ms(5)
        self._wait_on_busy()

    def _calibrate_image(self, frequency):
        """Calibrate image rejection"""
        freq_mhz = frequency / 1_000_000
        if 430 <= freq_mhz <= 440:
            freq_bytes = bytes([0x6B, 0x6F])
        elif 470 <= freq_mhz <= 510:
            freq_bytes = bytes([0x75, 0x81])
        elif 779 <= freq_mhz <= 787:
            freq_bytes = bytes([0xC1, 0xC5])
        elif 863 <= freq_mhz <= 870:
            freq_bytes = bytes([0xD7, 0xDB])
        elif 902 <= freq_mhz <= 928:
            freq_bytes = bytes([0xE1, 0xE9])
        else:
            freq_bytes = bytes([0x00, 0x00])
        self._execute_opcode(OP_CALIBRATE_IMAGE, freq_bytes)
        self._wait_on_busy()

    def _enable_tcxo(self):
        """Enable TCXO"""
        if self.has_tcxo:
            self._execute_opcode(OP_DIO3_TCXO_CTRL,
                               bytes([MODE_TCXO_3_3V, 0x00, 0x00, 0x64]))

    def _set_packet_type_lora(self):
        """Set packet type to LoRa"""
        self._execute_opcode(OP_PACKET_TYPE, bytes([MODE_LONG_RANGE]))

    def _standby(self):
        """Enter standby mode"""
        self._execute_opcode(OP_STANDBY, bytes([MODE_STDBY_RC]))

    def _receive(self):
        """Enter continuous RX mode"""
        self._execute_opcode(OP_RX, bytes([0xFF, 0xFF, 0xFF]))

    # ===== Public API =====

    def start(self):
        """Initialize and start radio"""
        try:
            self._reset()

            # Check SPI communication
            sync_msb = self._read_register(REG_SYNC_WORD_MSB)
            sync_lsb = self._read_register(REG_SYNC_WORD_LSB)
            sync_word = (sync_msb << 8) | sync_lsb

            if sync_word not in [0x1424, 0x4434]:
                print(f"SX1262 not responding (sync: 0x{sync_word:04X})")
                return False

            self._calibrate()
            self._calibrate_image(self.frequency)
            self._enable_tcxo()
            self._set_packet_type_lora()
            self._standby()

            # Set sync word
            self._write_register(REG_SYNC_WORD_MSB, (SYNC_WORD >> 8) & 0xFF)
            self._write_register(REG_SYNC_WORD_LSB, SYNC_WORD & 0xFF)

            # Configure DIO2 as RF switch
            if self.dio2_as_rf_switch:
                self._execute_opcode(OP_DIO2_RF_CTRL, bytes([0x01]))

            # Apply configuration
            self.set_frequency(self.frequency)
            self.set_tx_power(self.tx_power)
            self.set_spreading_factor(self.spreading_factor)
            self.set_bandwidth(self.bandwidth)
            self.set_coding_rate(self.coding_rate)

            # Set LNA boost
            self._write_register(REG_LNA, 0x96)

            # Set buffer base addresses
            self._execute_opcode(OP_BUFFER_BASE_ADDR, bytes([0x00, 0x00]))

            # Configure IRQ - route RX_DONE to DIO1 pin
            # Format: [irq_mask_msb, irq_mask_lsb, dio1_mask_msb, dio1_mask_lsb, dio2_mask, dio3_mask]
            self._execute_opcode(OP_SET_IRQ_FLAGS, bytes([
                0xFF, 0xFF,        # Enable all IRQs
                0x00, IRQ_RX_DONE, # Route RX_DONE to DIO1
                0x00, 0x00,        # DIO2 mask
                0x00, 0x00         # DIO3 mask
            ]))

            # Set up DIO1 interrupt handler
            self.pin_dio1.irq(trigger=Pin.IRQ_RISING, handler=self._on_dio1_rise)

            # Start receiving
            self._receive()

            self.online = True
            return True

        except Exception as e:
            print(f"SX1262 init error: {e}")
            import sys
            sys.print_exception(e)
            return False

    def stop(self):
        """Stop radio"""
        self._execute_opcode(OP_SLEEP, bytes([0x00]))
        self.online = False

    def send(self, data):
        """Transmit data"""
        if not self.online or len(data) > 255:
            return False

        try:
            self._standby()

            # Write to FIFO
            self.fifo_tx_addr_ptr = 0
            self._wait_on_busy()
            self.pin_ss.value(0)
            self.spi.write(bytes([OP_FIFO_WRITE, self.fifo_tx_addr_ptr]))
            self.spi.write(data)
            self.pin_ss.value(1)

            # Set packet params
            self._execute_opcode(OP_PACKET_PARAMS, bytes([
                0x00, 0x08,             # Preamble
                MODE_EXPLICIT_HEADER,
                len(data),
                0x01,                   # CRC on
                0x00, 0x00, 0x00, 0x00
            ]))

            # Transmit
            self._execute_opcode(OP_TX, bytes([0x00, 0x00, 0x00]))

            # Wait for TX done
            timeout_ms = 5000
            start = time.ticks_ms()
            while time.ticks_diff(time.ticks_ms(), start) < timeout_ms:
                irq = self._execute_opcode_read(OP_GET_IRQ_STATUS, 2)
                if irq[1] & IRQ_TX_DONE:
                    break
                time.sleep_ms(10)

            # Clear IRQ
            self._execute_opcode(OP_CLEAR_IRQ_STATUS, bytes([0x00, IRQ_TX_DONE]))

            # Resume RX
            self._receive()
            return True

        except Exception as e:
            print(f"TX error: {e}")
            return False

    def set_receive_callback(self, callback):
        """Set callback for received packets"""
        self.receive_callback = callback

    def _on_dio1_rise(self, pin):
        """
        Interrupt handler for DIO1 pin (RX_DONE).
        This is called by hardware interrupt when packet is received.
        """
        # Handle RX in the main poll_receive() method
        # We can't do SPI operations directly in the interrupt handler
        pass

    def poll_receive(self):
        """
        Poll for received packets (call regularly in main loop).

        Returns:
            bool: True if packet was received
        """
        if not self.online:
            return False

        try:
            # Check IRQ status for RX done
            irq = self._execute_opcode_read(OP_GET_IRQ_STATUS, 2)
            if not irq or len(irq) < 2:
                return False

            irq_status = (irq[0] << 8) | irq[1]

            # Check if RX done
            if irq_status & IRQ_RX_DONE:
                # Clear IRQ
                self._execute_opcode(OP_CLEAR_IRQ_STATUS, bytes([0x00, IRQ_RX_DONE]))

                # Check for CRC error
                if irq_status & IRQ_CRC_ERROR:
                    self._execute_opcode(OP_CLEAR_IRQ_STATUS, bytes([0x00, IRQ_CRC_ERROR]))
                    return False

                # Get buffer status
                buf_status = self._execute_opcode_read(OP_RX_BUFFER_STATUS, 2)
                if not buf_status or len(buf_status) < 2:
                    return False

                payload_len = buf_status[0]
                rx_start_ptr = buf_status[1]

                if payload_len == 0 or payload_len > 255:
                    return False

                # Read packet from FIFO
                self._wait_on_busy()
                self.pin_ss.value(0)
                self.spi.write(bytes([OP_FIFO_READ, rx_start_ptr, 0x00]))
                data = self.spi.read(payload_len)
                self.pin_ss.value(1)

                # Call receive callback
                if self.receive_callback and data:
                    self.receive_callback(bytes(data))

                return True

        except Exception as e:
            print(f"RX poll error: {e}")

        return False

    def set_frequency(self, frequency):
        """Set RF frequency"""
        self.frequency = frequency
        freq_raw = int(frequency / FREQ_STEP)
        self._execute_opcode(OP_RF_FREQ, bytes([
            (freq_raw >> 24) & 0xFF,
            (freq_raw >> 16) & 0xFF,
            (freq_raw >> 8) & 0xFF,
            freq_raw & 0xFF
        ]))

    def set_spreading_factor(self, sf):
        """Set spreading factor (5-12)"""
        self.spreading_factor = sf
        self._update_modulation_params()

    def set_bandwidth(self, bw):
        """Set bandwidth (Hz)"""
        self.bandwidth = bw
        self._update_modulation_params()

    def set_coding_rate(self, cr):
        """Set coding rate (5-8 = 4/5 to 4/8)"""
        self.coding_rate = cr
        self._update_modulation_params()

    def set_tx_power(self, power):
        """Set TX power (dBm)"""
        self.tx_power = power
        self._execute_opcode(OP_TX_PARAMS, bytes([power, 0x04]))

    def _update_modulation_params(self):
        """Update modulation parameters"""
        bw_reg = BW_TABLE.get(self.bandwidth, 0x04)
        symbol_time = (2 ** self.spreading_factor) / self.bandwidth
        ldro = 1 if symbol_time > 0.016 else 0

        self._execute_opcode(OP_MODULATION_PARAMS, bytes([
            self.spreading_factor,
            bw_reg,
            self.coding_rate - 4,
            ldro,
            0x00, 0x00, 0x00, 0x00
        ]))

    @staticmethod
    def calculate_bitrate(bandwidth, sf, cr):
        """Calculate LoRa bitrate"""
        symbol_rate = bandwidth / (2 ** sf)
        return int(sf * symbol_rate * (4.0 / cr))

    def get_rssi(self):
        """
        Get current RSSI (Received Signal Strength Indicator).

        Returns:
            RSSI in dBm (e.g., -135 to -60), or None if not available
        """
        try:
            result = self._execute_opcode_read(OP_CURRENT_RSSI, 1)
            if result and len(result) > 0:
                # SX1262 returns RSSI as negative offset from -157 dBm
                rssi = -result[0] // 2
                return rssi
            return None
        except:
            return None

    def get_stats(self):
        """Get radio statistics"""
        return {
            'frequency': self.frequency,
            'spreading_factor': self.spreading_factor,
            'bandwidth': self.bandwidth,
            'online': self.online
        }
