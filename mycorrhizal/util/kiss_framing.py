"""
KISS-style framing for reliable serial communication.

Inspired by RNode's KISS implementation and the KISS TNC protocol.
Used for file transfers and other binary data over serial.
"""

# KISS special characters
FEND = 0xC0  # Frame delimiter
FESC = 0xDB  # Escape character
TFEND = 0xDC  # Transposed frame end
TFESC = 0xDD  # Transposed escape

# Command bytes for file transfer (desktop → device)
CMD_FILE_INFO = 0x10   # Query file transfer info (Phase 1)
CMD_FILE_START = 0x11  # Start file transfer (Phase 2)
CMD_FILE_CHUNK = 0x12  # File data chunk
CMD_FILE_END = 0x13    # End file transfer
CMD_FILE_READY = 0x14  # Device ready for transfer (returns fragment count)
CMD_CHUNK_ACK = 0x15   # Chunk acknowledged

# Command bytes for file receive (device → desktop)
CMD_FILE_RECEIVED = 0x16  # File received notification (transfer_id, sender, filename, size)
CMD_FILE_DATA = 0x17      # Received file data chunk
CMD_FILE_COMPLETE = 0x18  # File transfer complete


class KISSFramer:
    """
    KISS protocol framer for binary serial communication.

    Frame format: [FEND][CMD][DATA...][FEND]

    Special bytes in DATA are escaped:
    - 0xC0 (FEND) → 0xDB 0xDC (FESC TFEND)
    - 0xDB (FESC) → 0xDB 0xDD (FESC TFESC)
    """

    @staticmethod
    def escape_data(data):
        """
        Escape FEND and FESC bytes in data.

        Args:
            data: bytes to escape

        Returns:
            bytes with special characters escaped
        """
        result = bytearray()
        for byte in data:
            if byte == FEND:
                result.extend([FESC, TFEND])
            elif byte == FESC:
                result.extend([FESC, TFESC])
            else:
                result.append(byte)
        return bytes(result)

    @staticmethod
    def unescape_data(data):
        """
        Unescape FEND and FESC bytes in data.

        Args:
            data: bytes with escaped characters

        Returns:
            bytes with special characters unescaped
        """
        result = bytearray()
        escape = False

        for byte in data:
            if escape:
                if byte == TFEND:
                    result.append(FEND)
                elif byte == TFESC:
                    result.append(FESC)
                else:
                    # Invalid escape sequence - skip
                    pass
                escape = False
            elif byte == FESC:
                escape = True
            else:
                result.append(byte)

        return bytes(result)

    @staticmethod
    def encode_frame(cmd, data=b""):
        """
        Encode a KISS frame.

        Args:
            cmd: Command byte
            data: Binary payload (will be escaped)

        Returns:
            Complete KISS frame as bytes
        """
        frame = bytearray([FEND, cmd])
        frame.extend(KISSFramer.escape_data(data))
        frame.append(FEND)
        return bytes(frame)

    @staticmethod
    def decode_frame(raw_data):
        """
        Decode a KISS frame.

        Args:
            raw_data: Raw bytes including FEND markers

        Returns:
            tuple: (cmd, data) or (None, None) if invalid
        """
        if len(raw_data) < 3:  # Minimum: [FEND][CMD][FEND]
            return None, None

        if raw_data[0] != FEND or raw_data[-1] != FEND:
            return None, None

        cmd = raw_data[1]
        data = KISSFramer.unescape_data(raw_data[2:-1])

        return cmd, data


class KISSReader:
    """
    Stateful KISS frame reader for serial streams.

    Accumulates bytes until a complete frame is received.
    """

    def __init__(self):
        self.buffer = bytearray()
        self.in_frame = False
        self.escape = False

    def reset(self):
        """Reset reader state"""
        self.buffer = bytearray()
        self.in_frame = False
        self.escape = False

    def feed_byte(self, byte):
        """
        Feed a single byte to the reader.

        Args:
            byte: Single byte (int 0-255)

        Returns:
            Complete frame bytes if frame complete, else None
        """
        if self.escape:
            if byte == TFEND:
                self.buffer.append(FEND)
            elif byte == TFESC:
                self.buffer.append(FESC)
            self.escape = False

        elif byte == FESC:
            self.escape = True

        elif byte == FEND:
            if self.in_frame and len(self.buffer) > 0:
                # Frame complete!
                frame = bytes([FEND]) + bytes(self.buffer) + bytes([FEND])
                self.buffer = bytearray()
                self.in_frame = False
                return frame
            else:
                # Frame start
                self.in_frame = True
                self.buffer = bytearray()

        elif self.in_frame:
            self.buffer.append(byte)

        return None
