"""
Mycorrhizal Firmware for Heltec V3 (MicroPython)

Single unified firmware that runs on the device.
Connect via serial (USB) OR Bluetooth LE to send/receive messages.

Similar to RNode or Meshtastic - the device handles the mesh networking,
you just connect with a chat client.

Platform: Heltec WiFi LoRa 32 V3 (ESP32-S3 + SX1262)
Runtime: MicroPython

Flash this to your device:
  cd utilities/
  python flash_device.py --device heltec_v3 --example mycorrhizal_firmware.py
"""

from mycorrhizal.core.node import Node
from mycorrhizal.phycore.lora import LoRaPhycore
from mycorrhizal.devices.heltec_v3 import HeltecV3
import sys
import time
import gc
import os

# Try to import select for non-blocking serial input
try:
    import select
    HAS_SELECT = True
except ImportError:
    HAS_SELECT = False

# KISS Framing Constants (RNode-style binary protocol)
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


class KISSReader:
    """
    KISS frame reader for binary serial communication.
    Replaces text-based line reading with reliable KISS framing.
    """
    def __init__(self):
        self.buffer = bytearray()
        self.in_frame = False
        self.escape = False
        self.max_frame_size = 8192  # 8KB max frame

    def feed_byte(self, byte_val):
        """
        Feed a single byte to the reader.
        Returns complete frame bytes if frame complete, else None.
        """
        if self.escape:
            if byte_val == TFEND:
                self.buffer.append(FEND)
            elif byte_val == TFESC:
                self.buffer.append(FESC)
            self.escape = False

        elif byte_val == FESC:
            self.escape = True

        elif byte_val == FEND:
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
            # Prevent buffer overflow
            if len(self.buffer) >= self.max_frame_size:
                print(f"[KISS] Buffer overflow! Resetting frame.")
                self.buffer = bytearray()
                self.in_frame = False
                return None
            self.buffer.append(byte_val)

        return None

    def read_frame(self):
        """
        Read bytes from stdin until complete KISS frame.
        Non-blocking - returns None if no complete frame available.
        """
        if not HAS_SELECT:
            return None

        max_bytes = 2048  # Read up to 2KB per call
        bytes_read = 0

        while bytes_read < max_bytes:
            if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                data = sys.stdin.read(1)
                if not data:
                    break

                bytes_read += 1
                frame = self.feed_byte(ord(data))
                if frame:
                    return frame
            else:
                break

        return None


class UnifiedInput:
    """
    Unified input handler that routes between KISS frames and text commands.
    Prevents both readers from consuming bytes from the same stream.
    """

    def __init__(self):
        self.text_buffer = ""
        self.kiss_reader = KISSReader()
        self.paused = False  # Pause when mpremote detected

    def read(self):
        """
        Read from stdin and return either ('kiss', frame) or ('text', line) or (None, None).
        Non-blocking.
        """
        global file_transfer_state
        if not HAS_SELECT or self.paused:
            return None, None

        try:
            # Yield to other tasks
            gc.collect()
            # Check if we have a complete text line buffered
            if '\n' in self.text_buffer:
                line, self.text_buffer = self.text_buffer.split('\n', 1)
                return 'text', line.strip()

            # Read available data (SMALL batches to prevent watchdog timeout)
            max_bytes = 32  # Only 32 bytes per call - prevents blocking
            bytes_read = 0

            while bytes_read < max_bytes:
                readable = select.select([sys.stdin], [], [], 0)[0]
                if not readable:
                    break

                # Read raw bytes to avoid UnicodeError
                try:
                    data = sys.stdin.buffer.read(1) if hasattr(sys.stdin, 'buffer') else sys.stdin.read(1).encode('latin1')
                except:
                    # Fallback: skip invalid bytes
                    continue

                if not data:
                    break

                bytes_read += 1
                byte_val = data[0] if isinstance(data, bytes) else ord(data)

                # Detect mpremote Ctrl-A (0x01) only outside KISS frames and if no file transfer is active
                if byte_val == 0x01 and not self.kiss_reader.in_frame and not file_transfer_state:
                    print("\n[INFO] mpremote detected, stopping firmware...")
                    raise KeyboardInterrupt("mpremote control requested")

                # Feed byte to KISS reader (always)
                frame = self.kiss_reader.feed_byte(byte_val)
                if frame:
                    # Complete frame received!
                    self.text_buffer = ""  # Clear any partial text
                    return 'kiss', frame

                # Only process as text if NOT in a KISS frame
                if not self.kiss_reader.in_frame:
                    # Handle line endings
                    if byte_val == 10:  # \n
                        if self.text_buffer:
                            line = self.text_buffer
                            self.text_buffer = ""
                            return 'text', line.strip()
                    elif byte_val == 13:  # \r - skip
                        continue
                    # Accumulate printable ASCII as text
                    elif 32 <= byte_val < 127:
                        # Convert byte to char
                        char = chr(byte_val)
                        self.text_buffer += char
                    # else: ignore non-printable/non-ASCII

        except Exception as e:
            print(f"[ERROR] UnifiedInput.read(): {e}")
            sys.print_exception(e)

        return None, None

# Global file transfer state (for streaming mode)
file_transfer_state = None


def escape_kiss_data(data):
    """Escape FEND and FESC bytes in data"""
    result = bytearray()
    for byte in data:
        if byte == FEND:
            result.append(FESC)
            result.append(TFEND)
        elif byte == FESC:
            result.append(FESC)
            result.append(TFESC)
        else:
            result.append(byte)
    return bytes(result)


def unescape_kiss_data(data):
    """Unescape FEND and FESC bytes in data"""
    result = bytearray()
    escape = False
    for byte in data:
        if escape:
            if byte == TFEND:
                result.append(FEND)
            elif byte == TFESC:
                result.append(FESC)
            escape = False
        elif byte == FESC:
            escape = True
        else:
            result.append(byte)
    return bytes(result)


def write_kiss_frame(cmd, data=b""):
    """Write KISS frame to stdout (serial)"""
    frame = bytearray([FEND, cmd])
    frame.extend(escape_kiss_data(data))
    frame.append(FEND)

    # Write to stdout.buffer as binary to avoid mixing with text output
    # Using buffer prevents print() from corrupting binary frames
    sys.stdout.buffer.write(bytes(frame))
    # Note: No flush() needed in MicroPython (auto-flushes)


def send_to_clients(message, ble_service=None):
    """Send message to both serial and BLE clients"""
    import sys
    # Serial (always available) - write directly to avoid buffer issues
    sys.stdout.write(message + '\n')

    # BLE (if connected)
    if ble_service and ble_service.get_state() == 'connected':
        try:
            ble_service.write((message + '\n').encode('utf-8'))
        except Exception as e:
            sys.stdout.write(f"ERROR:BLE write failed: {e}\n")


def handle_kiss_frame(frame_bytes, node, lora):
    """
    Handle KISS binary frames for file transfers.
    More reliable than text commands for large data.
    """
    global file_transfer_state

    if len(frame_bytes) < 3:  # Min: [FEND][CMD][FEND]
        return

    if frame_bytes[0] != FEND or frame_bytes[-1] != FEND:
        print("[KISS] Invalid frame delimiters")
        return

    cmd = frame_bytes[1]
    data = unescape_kiss_data(frame_bytes[2:-1])

    print(f"[KISS] CMD=0x{cmd:02X}, data_len={len(data)}")

    if cmd == CMD_FILE_INFO:
        # Phase 1: Calculate fragment count
        # Parse: addr(16) + filename_len(1) + filename + size(4)
        try:
            addr = data[0:16]
            fname_len = data[16]
            filename = data[17:17+fname_len].decode('utf-8')
            size = int.from_bytes(data[17+fname_len:17+fname_len+4], 'big')

            print(f"[KISS] FILE_INFO: {filename} ({size} bytes) to {addr.hex()[:16]}")

            # Build metadata header (same as we'll do during actual transfer)
            metadata = {
                'size': str(size),
                'filename': filename
            }
            meta_str = '\n'.join([f"{k}={v}" for k, v in metadata.items()])
            meta_bytes = meta_str.encode('utf-8')
            import struct
            meta_header = struct.pack('!H', len(meta_bytes)) + meta_bytes

            # Calculate exact fragment count
            from mycorrhizal.transport.fragments import FRAGMENT_DATA_SIZE

            # Total bytes = metadata header + file data
            total_bytes = len(meta_header) + size

            # Each LoRa fragment can hold FRAGMENT_DATA_SIZE (200) bytes of payload
            # The 18-byte header is separate and not counted against this limit
            total_fragments = (total_bytes + FRAGMENT_DATA_SIZE - 1) // FRAGMENT_DATA_SIZE

            print(f"[KISS] Calculated: {total_fragments} fragments for {total_bytes} bytes")

            # Respond with FILE_READY containing fragment count
            # Format: total_fragments(2 bytes, big-endian)
            response_data = total_fragments.to_bytes(2, 'big')
            write_kiss_frame(CMD_FILE_READY, response_data)
            print(f"[KISS] Sent FILE_READY with fragment_count={total_fragments}")

        except Exception as e:
            print(f"[KISS] FILE_INFO error: {e}")
            sys.print_exception(e)

    elif cmd == CMD_FILE_START:
        # Parse: addr(16) + filename_len(1) + filename + size(4)
        try:
            addr = data[0:16]
            fname_len = data[16]
            filename = data[17:17+fname_len].decode('utf-8')
            size = int.from_bytes(data[17+fname_len:17+fname_len+4], 'big')

            print(f"[KISS] FILE_START: {filename} ({size} bytes) to {addr.hex()[:16]}")

            # Generate transfer ID (same method as Fragmenter)
            from mycorrhizal.platform.crypto_adapter import CryptoBackend
            import struct
            import os as os_module
            random_bytes = os_module.urandom(8)
            transfer_id = CryptoBackend.hash_sha256(
                filename.encode('utf-8') + struct.pack('!I', size) + addr +
                struct.pack('!Q', int(time.time() * 1000)) + random_bytes
            )[:16]

            # Build metadata header
            metadata = {
                'size': str(size),
                'filename': filename
            }
            meta_str = '\n'.join([f"{k}={v}" for k, v in metadata.items()])
            meta_bytes = meta_str.encode('utf-8')
            meta_header = struct.pack('!H', len(meta_bytes)) + meta_bytes

            # Calculate total fragments needed
            from mycorrhizal.transport.fragments import FRAGMENT_DATA_SIZE

            # Each LoRa fragment can hold FRAGMENT_DATA_SIZE (200) bytes of payload
            # Account for metadata header in first fragment
            total_file_bytes = len(meta_header) + size
            total_fragments = (total_file_bytes + FRAGMENT_DATA_SIZE - 1) // FRAGMENT_DATA_SIZE

            print(f"[KISS] Transfer ID: {transfer_id.hex()[:16]}, fragments: {total_fragments}")

            file_transfer_state = {
                'dest': addr,
                'filename': filename,
                'size': size,
                'transfer_id': transfer_id,
                'meta_header': meta_header,
                'meta_sent': False,
                'bytes_sent': 0,
                'fragment_index': 0,
                'total_bytes': total_file_bytes  # Track total for end detection
            }

            # Send ACK
            write_kiss_frame(CMD_FILE_READY)
            print("[KISS] Sent FILE_READY")

            # Force garbage collection
            gc.collect()

        except Exception as e:
            print(f"[KISS] FILE_START error: {e}")
            sys.print_exception(e)

    elif cmd == CMD_FILE_CHUNK:
        # Parse: seq(2) + binary_data
        if not file_transfer_state:
            print("[KISS] ERROR: No active file transfer")
            return

        try:
            import struct
            from mycorrhizal.transport.fragments import FRAGMENT_DATA_SIZE
            from mycorrhizal.transport.packet import Packet, PacketType, PacketFlags

            seq = int.from_bytes(data[0:2], 'big')
            chunk_data = data[2:]

            print(f"[KISS] CHUNK {seq}: {len(chunk_data)} bytes")

            transfer = file_transfer_state
            transfer_id = transfer['transfer_id']
            frag_idx = transfer['fragment_index']

            # Build LoRa fragment data stream
            fragment_payload = bytearray()

            # First fragment includes metadata header
            if not transfer['meta_sent']:
                fragment_payload.extend(transfer['meta_header'])
                transfer['meta_sent'] = True
                print(f"[KISS] Added metadata header: {len(transfer['meta_header'])} bytes")

            # Handle chunk data (split into multiple LoRa fragments)
            # Each LoRa fragment = header (18 bytes) + data (up to 200 bytes) = 218 bytes total
            # The data portion can be up to FRAGMENT_DATA_SIZE (200 bytes)

            while len(chunk_data) > 0:
                # How much space left in current fragment payload?
                space_left = FRAGMENT_DATA_SIZE - len(fragment_payload)

                # Take as much as will fit
                chunk_to_send = chunk_data[:space_left]
                chunk_data = chunk_data[space_left:]  # Remaining for next fragment

                fragment_payload.extend(chunk_to_send)
                transfer['bytes_sent'] += len(chunk_to_send)

                # If fragment is full OR no more chunk data, send it
                if len(fragment_payload) >= FRAGMENT_DATA_SIZE or len(chunk_data) == 0:
                    # Build complete LoRa fragment: header (18) + payload (up to 200)
                    # Format: transfer_id(16) + index(1) + flags(1) + data
                    # FINAL flag will be sent in FILE_END command
                    lora_fragment = struct.pack(
                        '!16sBB',
                        transfer_id,
                        frag_idx,
                        0x00  # No flags during chunks, FINAL sent in FILE_END
                    ) + bytes(fragment_payload)

                    # Send using node.send_data
                    node.send_data(
                        destination_address=transfer['dest'],
                        payload=lora_fragment,
                        sign=True,
                        flags=PacketFlags.FRAGMENTED
                    )

                    print(f"[KISS] → LoRa fragment {frag_idx} ({len(lora_fragment)} bytes)")

                    transfer['fragment_index'] += 1
                    frag_idx += 1
                    fragment_payload = bytearray()  # Reset for next fragment

            # Send ACK for the chunk
            ack_data = seq.to_bytes(2, 'big')
            write_kiss_frame(CMD_CHUNK_ACK, ack_data)

            # Free memory
            del fragment_payload
            del lora_fragment
            gc.collect()
            print(f"[KISS] RAM: {gc.mem_free()} bytes")

        except Exception as e:
            print(f"[KISS] CHUNK error: {e}")
            sys.print_exception(e)

    elif cmd == CMD_FILE_END:
        # Send final fragment with FINAL flag
        if not file_transfer_state:
            print("[KISS] ERROR: No active file transfer")
            return

        try:
            print("[KISS] FILE_END - sending final fragment marker")

            transfer = file_transfer_state
            transfer_id = transfer['transfer_id']
            transfer_id_hex = transfer_id.hex()
            frag_idx = transfer['fragment_index'] - 1  # Last fragment we sent

            # Re-send the last fragment with FINAL flag set
            # (This is a marker, not actual data - receiver will detect duplicate index)
            import struct
            from mycorrhizal.transport.fragments import FRAGMENT_FLAG_FINAL
            from mycorrhizal.transport.packet import PacketFlags

            # Build FINAL marker fragment (empty payload, just header with flag)
            lora_fragment = struct.pack(
                '!16sBB',
                transfer_id,
                frag_idx,
                FRAGMENT_FLAG_FINAL
            )

            node.send_data(
                destination_address=transfer['dest'],
                payload=lora_fragment,
                sign=True,
                flags=PacketFlags.FRAGMENTED
            )

            print(f"[KISS] → LoRa fragment {frag_idx} [FINAL MARKER] ({len(lora_fragment)} bytes)")
            print(f"[KISS] Transfer complete: {transfer['fragment_index']} fragments, {transfer['bytes_sent']} bytes")

            # Send text notification (for serial_chat compatibility)
            dest_hex = transfer['dest'].hex()
            send_to_clients(f"FILESENT:{dest_hex[:16]}:{transfer_id_hex[:8]}:{transfer['filename']}", None)

            # Clean up
            file_transfer_state = None
            gc.collect()

        except Exception as e:
            print(f"[KISS] FILE_END error: {e}")
            sys.print_exception(e)
            file_transfer_state = None


def handle_command(cmd, node, lora, ble, colony_callback=None):
    """
    Handle commands from serial OR BLE.
    Commands are the same regardless of input source.

    Args:
        cmd: Command string
        node: Node instance
        lora: LoRa phycore
        ble: BLE interface (or None for serial)
        colony_callback: Callback function for colony messages
    """
    global file_transfer_state

    cmd = cmd.strip()

    if not cmd:
        return

    # Debug: log command details
    print(f"[CMD] Received: '{cmd}' (len={len(cmd)}, bytes={cmd.encode('utf-8').hex()[:50]})")

    # INFO command - show node info
    if cmd == "!info":
        send_to_clients(f"NODE:{node.identity.address_hex()}", ble)
        send_to_clients(f"ROUTES:{node.route_table.size()}", ble)
        send_to_clients(f"PEERS:{node.identity_cache.size()}", ble)
        send_to_clients(f"TX:{lora.tx_count} RX:{lora.rx_count}", ble)
        send_to_clients(f"TX_BYTES:{lora.tx_bytes} RX_BYTES:{lora.rx_bytes}", ble)

    # ANNOUNCE command - send announce to discover peers
    elif cmd == "!announce":
        send_to_clients("INFO:Sending announce...", ble)
        node.announce(verbose=False)

    # SEND command - send message to specific address
    # Format: !send <address> <message>
    elif cmd.startswith("!send "):
        parts = cmd[6:].split(None, 1)
        if len(parts) < 2:
            send_to_clients("ERROR:Usage: !send <address> <message>", ble)
            return

        addr_hex = parts[0]
        message = parts[1]

        try:
            dest_addr = bytes.fromhex(addr_hex)
            node.send_data(dest_addr, message.encode('utf-8'))
            send_to_clients(f"SENT:{addr_hex[:16]}", ble)
        except ValueError:
            send_to_clients(f"ERROR:Invalid address: {addr_hex}", ble)
        except Exception as e:
            send_to_clients(f"ERROR:Send failed: {e}", ble)

    # BROADCAST command - send to all known peers
    # Format: !broadcast <message>
    elif cmd.startswith("!broadcast "):
        message = cmd[11:]
        peers = node.identity_cache.get_all()

        if not peers:
            send_to_clients("ERROR:No peers discovered yet", ble)
            return

        count = 0
        for addr_hex in peers:
            try:
                dest_addr = bytes.fromhex(addr_hex)
                node.send_data(dest_addr, message.encode('utf-8'))
                count += 1
            except Exception as e:
                send_to_clients(f"ERROR:Failed to send to {addr_hex[:8]}: {e}", ble)

        send_to_clients(f"BROADCAST:{count} peers", ble)

    # PEERS command - list known peers
    elif cmd == "!peers":
        peers = node.identity_cache.get_all()
        if not peers:
            send_to_clients("PEERS:0", ble)
        else:
            send_to_clients(f"PEERS:{len(peers)}", ble)
            for addr_hex in peers:
                send_to_clients(f"PEER:{addr_hex}", ble)

    # GROUP CHAT COMMANDS

    # CREATECOLONY command - create a new group chat
    # Format: !createcolony <name>
    elif cmd.startswith("!createcolony "):
        colony_name = cmd[14:].strip()
        if not colony_name:
            send_to_clients("ERROR:Usage: !createcolony <name>", ble)
            return

        try:
            colony = node.create_colony(colony_name)
            print(f"[COLONY] Created: {colony.colony_id.hex()} - {colony_name}")

            # Set up colony message callback
            if colony_callback:
                def on_msg(sender_addr, sender_name, message):
                    print(f"[COLONY] MSG callback fired: {sender_name}: {message}")
                    colony_callback(colony.colony_id.hex(), sender_addr, sender_name, message)
                colony.on_message(on_msg)
                print(f"[COLONY] Callback registered for {colony.colony_id.hex()}")
            else:
                print(f"[COLONY] WARNING: No colony_callback provided!")

            # Send colony info to client
            key_material = colony.get_key_material()
            colony_id_hex = key_material['colony_id'].hex()
            group_key_hex = key_material['group_key'].hex()
            send_to_clients(f"COLONY_CREATED:{colony_id_hex}:{colony_name}", ble)
            send_to_clients(f"COLONY_KEY:{colony_id_hex}:{group_key_hex}", ble)
            print(f"[COLONY] Sent COLONY_CREATED to client")
        except Exception as e:
            send_to_clients(f"ERROR:Failed to create colony: {e}", ble)
            sys.print_exception(e)

    # JOINCOLONY command - join an existing group chat
    # Format: !joincolony <colony_id> <group_key> <name>
    elif cmd.startswith("!joincolony "):
        parts = cmd[12:].split(None, 2)
        if len(parts) < 3:
            send_to_clients("ERROR:Usage: !joincolony <colony_id> <group_key> <name>", ble)
            return

        try:
            colony_id = bytes.fromhex(parts[0])
            group_key = bytes.fromhex(parts[1])
            colony_name = parts[2]

            key_material = {
                'colony_id': colony_id,
                'group_key': group_key,
                'name': colony_name
            }
            colony = node.join_colony(key_material)

            # Set up colony message callback
            if colony_callback:
                def on_msg(sender_addr, sender_name, message):
                    colony_callback(colony.colony_id.hex(), sender_addr, sender_name, message)
                colony.on_message(on_msg)

            send_to_clients(f"COLONY_JOINED:{colony_id.hex()}:{colony_name}", ble)
        except Exception as e:
            send_to_clients(f"ERROR:Failed to join colony: {e}", ble)
            sys.print_exception(e)

    # COLONYSEND command - send message to a colony
    # Format: !colonysend <colony_id> <message>
    elif cmd.startswith("!colonysend "):
        parts = cmd[12:].split(None, 1)
        if len(parts) < 2:
            send_to_clients("ERROR:Usage: !colonysend <colony_id> <message>", ble)
            return

        try:
            colony_id_hex = parts[0]
            message = parts[1]

            print(f"[COLONY] Sending to {colony_id_hex}: {message}")
            print(f"[COLONY] Available colonies: {list(node.colonies.keys())}")

            if colony_id_hex not in node.colonies:
                send_to_clients(f"ERROR:Colony not found: {colony_id_hex}", ble)
                print(f"[COLONY] ERROR: Colony {colony_id_hex} not in node.colonies")
                return

            colony = node.colonies[colony_id_hex]
            print(f"[COLONY] Colony has {len(colony.members)} members")
            success = colony.send(message)
            print(f"[COLONY] Send result: {success}")
            send_to_clients(f"COLONY_SENT:{colony_id_hex}:{colony.name}", ble)
        except Exception as e:
            send_to_clients(f"ERROR:Failed to send to colony: {e}", ble)
            print(f"[COLONY] Exception in colonysend:")
            sys.print_exception(e)

    # COLONYADDMEMBER command - add member to colony (requires their address)
    # Format: !colonyaddmember <colony_id> <member_address> [name]
    elif cmd.startswith("!colonyaddmember "):
        parts = cmd[17:].split(None, 2)
        if len(parts) < 2:
            send_to_clients("ERROR:Usage: !colonyaddmember <colony_id> <member_address> [name]", ble)
            return

        try:
            colony_id_hex = parts[0]
            member_addr = bytes.fromhex(parts[1])
            member_name = parts[2] if len(parts) > 2 else None

            if colony_id_hex not in node.colonies:
                send_to_clients(f"ERROR:Colony not found: {colony_id_hex}", ble)
                return

            colony = node.colonies[colony_id_hex]
            # Get member's public identity from cache if available
            member_identity = node.identity_cache.get(member_addr)
            colony.add_member(member_addr, member_identity, member_name)

            # Send invitation to the member with colony key
            # Format: COLONY_INVITE:<colony_id>:<group_key>:<colony_name>
            # Note: Member list sync will happen when they join and send their first message
            invite_msg = f"COLONY_INVITE:{colony_id_hex}:{colony.group_key.hex()}:{colony.name}"
            invite_bytes = invite_msg.encode('utf-8')

            print(f"[COLONY] Sending invite to {parts[1]}")
            print(f"[COLONY] Member addr (bytes): {member_addr.hex()}")
            print(f"[COLONY] Invite size: {len(invite_bytes)} bytes (payload only)")
            print(f"[COLONY] Total with headers+sig: ~{len(invite_bytes) + 96} bytes")

            # Send invitation
            success = node.send_data(member_addr, invite_bytes, sign=True)
            print(f"[COLONY] Invite send_data returned: {success}")

            send_to_clients(f"COLONY_MEMBER_ADDED:{colony_id_hex}:{parts[1]}", ble)
            print(f"[COLONY] Added member {parts[1]} to colony {colony_id_hex}")
        except Exception as e:
            send_to_clients(f"ERROR:Failed to add member: {e}", ble)
            sys.print_exception(e)

    # LISTCOLONIES command - list all colonies
    elif cmd == "!listcolonies":
        if not node.colonies:
            send_to_clients("COLONIES:0", ble)
        else:
            send_to_clients(f"COLONIES:{len(node.colonies)}", ble)
            for colony_id_hex, colony in node.colonies.items():
                send_to_clients(f"COLONY:{colony_id_hex}:{colony.name}:{len(colony.members)}", ble)

    # FILESTART command - start chunked file transfer with flow control
    # Format: !filestart <address> <filename> <size>
    elif cmd.startswith("!filestart "):
        parts = cmd[11:].split(None, 2)
        if len(parts) < 3:
            send_to_clients("ERROR:Usage: !filestart <address> <filename> <size>", ble)
            return

        addr_hex = parts[0]
        filename = parts[1]
        size = int(parts[2])

        try:
            global file_transfer_state
            dest_addr = bytes.fromhex(addr_hex)
            file_transfer_state = {
                'dest': dest_addr,
                'filename': filename,
                'size': size,
                'chunks': {}  # Changed to dict for sequence numbers
            }
            send_to_clients(f"INFO:Starting file transfer: {filename} ({size} bytes)", ble)
            # Send ACK to proceed
            send_to_clients("FILEREADY", ble)
        except Exception as e:
            send_to_clients(f"ERROR:File start failed: {e}", ble)

    # FILECHUNK command - receive file data chunk with sequence number
    # Format: !filechunk <seq_num> <hex_data>
    elif cmd.startswith("!filechunk "):
        print(f"[DEBUG] Processing !filechunk command")

        if not file_transfer_state:
            send_to_clients("ERROR:No active file transfer", ble)
            print(f"[DEBUG] ERROR: No file transfer state")
            return

        parts = cmd[11:].split(None, 1)
        print(f"[DEBUG] Split into {len(parts)} parts")

        if len(parts) < 2:
            send_to_clients("ERROR:Usage: !filechunk <seq_num> <hex_data>", ble)
            print(f"[DEBUG] ERROR: Not enough parts")
            return

        try:
            seq_num = int(parts[0])
            hex_chunk = parts[1].strip()

            print(f"[DEBUG] Chunk {seq_num}: {len(hex_chunk)} hex chars")

            # Store chunk by sequence number
            file_transfer_state['chunks'][seq_num] = hex_chunk
            print(f"[DEBUG] Stored chunk {seq_num}, total chunks: {len(file_transfer_state['chunks'])}")

            # Send ACK for this chunk
            send_to_clients(f"CHUNKACK:{seq_num}", ble)
            print(f"[DEBUG] Sent CHUNKACK:{seq_num}")

        except Exception as e:
            send_to_clients(f"ERROR:Chunk failed: {e}", ble)
            print(f"[DEBUG] EXCEPTION in filechunk: {e}")
            sys.print_exception(e)

    # FILEEND command - finish file transfer and send
    elif cmd == "!fileend":
        send_to_clients("INFO:Received !fileend command", ble)
        if not file_transfer_state:
            send_to_clients("ERROR:No active file transfer", ble)
            return

        try:
            global file_transfer_state
            transfer = file_transfer_state

            # Reconstruct file from hex chunks IN SEQUENCE ORDER
            chunk_dict = transfer['chunks']
            num_chunks = len(chunk_dict)

            # Sort chunks by sequence number
            sorted_seq_nums = sorted(chunk_dict.keys())

            # Check for missing chunks
            expected_chunks = list(range(sorted_seq_nums[0], sorted_seq_nums[-1] + 1))
            if sorted_seq_nums != expected_chunks:
                missing = set(expected_chunks) - set(sorted_seq_nums)
                send_to_clients(f"ERROR:Missing chunks: {missing}", ble)
                file_transfer_state = None
                return

            # Concatenate chunks in order
            hex_data = ''.join([chunk_dict[seq] for seq in sorted_seq_nums])
            send_to_clients(f"INFO:Reconstructed {num_chunks} chunks, {len(hex_data)} hex chars", ble)

            file_data = bytes.fromhex(hex_data)
            send_to_clients(f"INFO:File data: {len(file_data)} bytes", ble)

            # Verify size matches
            if len(file_data) != transfer['size']:
                send_to_clients(f"ERROR:Size mismatch! Expected {transfer['size']}, got {len(file_data)}", ble)
                file_transfer_state = None
                return

            # Determine mime type
            mime_type = None
            if '.' in transfer['filename']:
                ext = transfer['filename'].split('.')[-1].lower()
                mime_map = {
                    'txt': 'text/plain',
                    'jpg': 'image/jpeg',
                    'jpeg': 'image/jpeg',
                    'png': 'image/png',
                    'gif': 'image/gif',
                    'pdf': 'application/pdf',
                    'html': 'text/html',
                    'json': 'application/json',
                    'py': 'text/x-python',
                    'js': 'application/javascript',
                    'md': 'text/markdown'
                }
                mime_type = mime_map.get(ext)

            # Send file via LoRa
            send_to_clients(f"INFO:Sending via LoRa to {transfer['dest'].hex()[:16]}...", ble)
            transfer_id = node.send_file(
                transfer['dest'],
                file_data,
                filename=transfer['filename'],
                mime_type=mime_type
            )

            dest_hex = transfer['dest'].hex()
            send_to_clients(f"FILESENT:{dest_hex[:16]}:{transfer_id}:{transfer['filename']}", ble)

            # Clear transfer state
            file_transfer_state = None

        except Exception as e:
            send_to_clients(f"ERROR:File send failed: {e}", ble)
            sys.print_exception(e)
            file_transfer_state = None

    # TRANSFERS command - show active file transfers
    elif cmd == "!transfers":
        transfers = node.transfer_manager.get_active_transfers()
        if not transfers:
            send_to_clients("TRANSFERS:0", ble)
        else:
            send_to_clients(f"TRANSFERS:{len(transfers)}", ble)
            for tid, info in transfers.items():
                send_to_clients(f"TRANSFER:{tid}:{info['progress']:.0f}%:{info['received']}/{info['total']}", ble)

    # Unknown command
    else:
        send_to_clients(f"ERROR:Unknown command: {cmd}", ble)
        send_to_clients("ERROR:Try: !info, !announce, !send, !broadcast, !peers, !transfers", ble)


def main():
    print("=" * 60)
    print("Mycorrhizal Firmware v0.1")
    print("=" * 60)

    # Disable Ctrl-C interrupt for binary KISS protocol
    # Ctrl-A (mpremote) is still detected and will pause the firmware
    import micropython
    micropython.kbd_intr(-1)
    print("🔒 Binary mode: Ctrl-C disabled, Ctrl-A will pause")

    # Create Heltec V3 device
    device = HeltecV3(
        frequency=915_000_000,
        spreading_factor=9,
        bandwidth=125_000,
        coding_rate=5,
        tx_power=14,
        enable_display=True,
        enable_ble=True,
        device_name="Mycorrhizal"
    )

    # Fun boot animation
    if device.display:
        try:
            display = device.display.display

            # Clear and show boot screen
            display.fill(0)
            display.text("MYCORRHIZAL", 20, 10, 1)
            display.text("v0.1", 48, 25, 1)
            display.text("Booting...", 30, 45, 1)
            display.show()
            time.sleep(1)

            # Simple animation
            for i in range(3):
                display.fill_rect(30 + i*20, 45, 15, 8, 1)
                display.show()
                time.sleep(0.2)

            time.sleep(0.5)
        except Exception as e:
            print(f"Display animation error: {e}")

    # Create LoRa phycore
    lora = LoRaPhycore(name="lora0", device=device)

    # Create node with persistent identity
    print("\n" + "=" * 60)
    print("Creating node with persistent identity...")
    print("=" * 60)
    node = Node(name="Mycorrhizal", persistent_identity=True)
    node.add_phycore(lora)

    print(f"\nNode: {node.name}")
    print(f"Address: {node.identity.address_hex()}")
    print(f"Platform: {node.profile.platform}")
    print("=" * 60)

    # Message handler - forward received messages to clients
    def on_data(payload, source_address, packet):
        try:
            message = payload.decode('utf-8')
            sender_hex = source_address.hex() if source_address else "unknown"

            # Debug: log ALL incoming messages
            print(f"[RX] Payload preview: {message[:60]}...")
            print(f"[RX] From: {sender_hex[:16]}...")

            # Check if this is a colony invitation
            if message.startswith('COLONY_INVITE:'):
                print(f"[COLONY] Received invitation: {message[:80]}...")
                parts = message.split(':', 3)  # Only split into 4 parts (no member list)
                if len(parts) >= 4:
                    colony_id_hex = parts[1]
                    group_key_hex = parts[2]
                    colony_name = parts[3]

                    # Auto-join the colony
                    colony_id = bytes.fromhex(colony_id_hex)
                    group_key = bytes.fromhex(group_key_hex)

                    key_material = {
                        'colony_id': colony_id,
                        'group_key': group_key,
                        'name': colony_name
                    }
                    colony = node.join_colony(key_material)
                    print(f"[COLONY] Joined colony {colony_id_hex[:16]}... ('{colony_name}')")

                    # Add the inviter as a member
                    if source_address:
                        inviter_identity = node.identity_cache.get(source_address)
                        colony.add_member(source_address, inviter_identity, "Inviter")
                        print(f"[COLONY] Added inviter {source_address.hex()[:16]}... as member")

                    # Set up colony message callback
                    if on_colony_message:
                        def on_msg(sender_addr, sender_name, msg):
                            print(f"[COLONY] MSG callback fired: {sender_name}: {msg}")
                            on_colony_message(colony.colony_id.hex(), sender_addr, sender_name, msg)
                        colony.on_message(on_msg)
                        print(f"[COLONY] Callback registered for {colony.colony_id.hex()}")

                    # Notify client about the new colony
                    send_to_clients(f"COLONY_JOINED:{colony_id_hex}:{colony_name}", device.ble)
                    print(f"[COLONY] Auto-joined colony {colony_name} from invitation")
                    print(f"[COLONY] Colony now has {len(colony.members)} members")
                    return

            # Regular message
            send_to_clients(f"MSG:{sender_hex}:{message}", device.ble)
        except Exception as e:
            print(f"ERROR:RX handler: {e}")
            sys.print_exception(e)

    node.on_data(on_data)

    # File transfer handler - notify clients of received files
    def on_file_received(transfer_id, data, metadata, sender_address):
        try:
            filename = metadata.get('filename', 'unknown')
            print(f"📁 File received: {filename} ({len(data)} bytes)")

            # Send file to desktop using KISS binary protocol
            # Frame 1: CMD_FILE_RECEIVED with metadata
            transfer_id_bytes = bytes.fromhex(transfer_id) if isinstance(transfer_id, str) else bytes(transfer_id)
            sender_bytes = bytes(sender_address) if (sender_address and len(sender_address) >= 16) else bytes(16)
            filename_bytes = filename.encode('utf-8')

            # Payload: transfer_id(16) + sender(16) + filename_len(1) + filename + size(4)
            payload = bytearray()
            payload.extend(transfer_id_bytes[:16])  # Ensure 16 bytes
            payload.extend(sender_bytes[:16])  # Ensure 16 bytes
            payload.append(len(filename_bytes))
            payload.extend(filename_bytes)
            payload.extend(len(data).to_bytes(4, 'big'))

            # Send header frame
            print(f"[FILE_RX] Sending CMD_FILE_RECEIVED (0x16), payload={len(payload)} bytes")
            frame = bytes([FEND, CMD_FILE_RECEIVED]) + escape_kiss_data(bytes(payload)) + bytes([FEND])
            sys.stdout.buffer.write(frame)
            print(f"[FILE_RX] Sent header frame ({len(frame)} bytes)")

            # Frame 2+: CMD_FILE_DATA with chunks
            chunk_size = 250
            chunk_count = 0
            for i in range(0, len(data), chunk_size):
                chunk = data[i:i+chunk_size]
                # Payload: transfer_id(16) + chunk_data
                chunk_payload = transfer_id_bytes[:16] + bytes(chunk)
                print(f"[FILE_RX] Chunk {chunk_count}: chunk_payload type={type(chunk_payload)}, len={len(chunk_payload)}")
                frame = bytes([FEND, CMD_FILE_DATA]) + escape_kiss_data(chunk_payload) + bytes([FEND])
                sys.stdout.buffer.write(frame)
                chunk_count += 1
                time.sleep(0.01)  # Small delay between chunks

            print(f"[FILE_RX] Sent {chunk_count} data chunks")

            # Frame 3: CMD_FILE_COMPLETE
            complete_payload = transfer_id_bytes[:16]
            frame = bytes([FEND, CMD_FILE_COMPLETE]) + escape_kiss_data(complete_payload) + bytes([FEND])
            sys.stdout.buffer.write(frame)
            print(f"[FILE_RX] Sent CMD_FILE_COMPLETE")

            print(f"✓ Forwarded {filename} to desktop")
        except Exception as e:
            print(f"ERROR:File RX handler: {e}")
            sys.print_exception(e)

    node.on_file_received(on_file_received)

    # Announce handler - notify clients of new peers
    def on_announce(packet, public_identity):
        try:
            addr_hex = packet.destination.hex()
            send_to_clients(f"PEER:{addr_hex}", device.ble)
        except Exception as e:
            print(f"ERROR:Announce handler: {e}")
            # sys already imported
            sys.print_exception(e)

    node.on_announce(on_announce)

    # Colony (group chat) message handler - called when colony messages are received
    def on_colony_message(colony_id_hex, sender_address, sender_name, message):
        try:
            sender_hex = sender_address.hex() if sender_address else "unknown"
            msg_str = message if isinstance(message, str) else message.decode('utf-8', errors='replace')
            send_to_clients(f"COLONY_MSG:{colony_id_hex}:{sender_hex}:{sender_name}:{msg_str}", device.ble)
        except Exception as e:
            print(f"ERROR:Colony message handler: {e}")
            sys.print_exception(e)

    # Set up colony message callbacks
    # Note: Callbacks are set when colonies are created/joined in handle_command

    # BLE message handler - handle commands from BLE client
    def handle_ble_message(data):
        try:
            cmd = data.decode('utf-8', errors='replace').strip()
            handle_command(cmd, node, lora, device.ble, colony_callback=on_colony_message)
        except Exception as e:
            send_to_clients(f"ERROR:BLE handler: {e}", device.ble)

    # Register BLE callback
    if device.ble:
        device.ble.set_write_callback(handle_ble_message)
        print("BLE: Enabled")

    # Start node
    print("\nStarting...")
    node.start(auto_announce=True, announce_now=True)

    print("\n" + "-" * 60)
    print("Firmware running")
    print("-" * 60)

    # Send node address on boot
    send_to_clients(f"NODE:{node.identity.address_hex()}", device.ble)

    # Unified input handler (routes between KISS and text)
    unified_input = UnifiedInput() if HAS_SELECT else None

    # Main loop
    try:
        while True:
            try:
                # Update device (display, BLE, button)
                # This updates node_state and refreshes display every 1s
                device.update(node)

                # Check auto-announce
                node.check_announce()

                # Check for input (KISS frames or text commands)
                if unified_input and not unified_input.paused:
                    # Process up to 50 inputs per loop iteration (increased)
                    for _ in range(50):
                        try:
                            input_type, data = unified_input.read()
                            if input_type == 'kiss':
                                print(f"[MAIN] Got KISS frame, len={len(data) if data else 0}")
                                handle_kiss_frame(data, node, lora)
                            elif input_type == 'text':
                                print(f"[MAIN] Got text: {data[:50] if data else ''}")
                                handle_command(data, node, lora, device.ble, colony_callback=on_colony_message)
                            else:
                                break
                        except Exception as e:
                            print(f"[ERROR] Input handler crashed: {e}")
                            sys.print_exception(e)
                            # Try to recover
                            gc.collect()

                # Sleep shorter to keep serial buffer from overflowing
                time.sleep_ms(1)  # 1ms = 1000Hz loop rate

            except Exception as e:
                print(f"[FATAL] Main loop crashed: {e}")
                sys.print_exception(e)
                time.sleep_ms(100)
                gc.collect()

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        node.stop()
        print("Stopped")


if __name__ == "__main__":
    main()
