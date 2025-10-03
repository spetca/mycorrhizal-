#!/usr/bin/env python3
"""
Serial Chat Terminal - Connect to Mycorrhizal device over USB serial

Features:
- Direct messaging to node addresses
- Group chat (colonies)
- Message history
- Node discovery
- Full terminal UI
- KISS binary file transfers (RNode-style)

Usage:
    python serial_chat.py [--port /dev/ttyUSB0]
"""

import sys
import os
import argparse
import time
import threading
from datetime import datetime

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("Error: pyserial not installed")
    print("Install with: pip install pyserial")
    sys.exit(1)

# Import KISS framing library
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
sys.path.insert(0, parent_dir)

from mycorrhizal.util.kiss_framing import (
    KISSFramer, KISSReader,
    CMD_FILE_INFO, CMD_FILE_START, CMD_FILE_CHUNK, CMD_FILE_END,
    CMD_FILE_READY, CMD_CHUNK_ACK,
    CMD_FILE_RECEIVED, CMD_FILE_DATA, CMD_FILE_COMPLETE,
    FEND
)


class SerialChat:
    """Serial chat terminal for Mycorrhizal devices"""

    def __init__(self, port, baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.running = False
        self.rx_thread = None

        # Chat state
        self.node_address = None
        self.known_nodes = {}  # address_hex -> name
        self.groups = {}  # group_id -> {name, members}
        self.current_target = None  # Current chat target (address or group_id)
        self.message_history = []  # [(timestamp, sender, message)]

        # Flow control for file transfers
        self.pending_ack = None  # What ACK we're waiting for
        self.ack_received = False
        self.ack_data = None  # Data returned with ACK (e.g., fragment count)
        self.ack_timeout = 3.0  # seconds

        # KISS frame reader for binary responses
        self.kiss_reader = KISSReader()

        # File receive state
        self.receiving_files = {}  # transfer_id -> {filename, size, chunks}

    def connect(self):
        """Connect to serial port"""
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=0.1,
                write_timeout=1.0,
                # CRITICAL: Disable software flow control to allow 0x03 bytes
                xonxoff=False,
                rtscts=False,
                dsrdtr=False
            )
            time.sleep(2)  # Wait for device reset

            # Flush any boot messages
            self.ser.reset_input_buffer()

            print(f"✓ Connected to {self.port}")
            return True
        except serial.SerialException as e:
            print(f"✗ Failed to connect: {e}")
            return False

    def disconnect(self):
        """Disconnect from serial port"""
        self.running = False
        if self.rx_thread:
            self.rx_thread.join(timeout=1.0)
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("\n✓ Disconnected")

    def send_command(self, cmd):
        """Send command to device"""
        if not self.ser or not self.ser.is_open:
            return False
        try:
            self.ser.write((cmd + '\n').encode('utf-8'))
            self.ser.flush()
            return True
        except Exception as e:
            print(f"\n✗ Send error: {e}")
            return False

    def wait_for_ack(self, ack_type, timeout=None):
        """
        Wait for specific acknowledgment from firmware.

        Args:
            ack_type: String to wait for (e.g., "FILEREADY", "CHUNKACK:5")
            timeout: Timeout in seconds (default: self.ack_timeout)

        Returns:
            bool: True if ACK received, False if timeout
        """
        if timeout is None:
            timeout = self.ack_timeout

        self.pending_ack = ack_type
        self.ack_received = False

        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.ack_received:
                self.pending_ack = None
                return True
            time.sleep(0.01)  # Check every 10ms

        # Timeout
        self.pending_ack = None
        return False

    def read_line(self):
        """Read line from serial (non-blocking)"""
        if not self.ser or not self.ser.is_open:
            return None
        try:
            if self.ser.in_waiting:
                line = self.ser.readline().decode('utf-8', errors='replace').strip()
                return line
        except Exception as e:
            print(f"\n✗ Read error: {e}")
        return None

    def rx_worker(self):
        """Background thread to read serial data (text lines and KISS ACKs)"""
        while self.running:
            # Read available bytes and feed to both parsers
            if self.ser and self.ser.in_waiting:
                # Read byte by byte to handle both KISS and text
                byte_data = self.ser.read(1)
                if byte_data:
                    byte_val = byte_data[0]

                    # Check if it's a KISS frame (starts with FEND)
                    if byte_val == 0xC0:
                        # Read complete KISS frame
                        frame = self.kiss_reader.feed_byte(byte_val)
                        while not frame and self.running:
                            if self.ser.in_waiting:
                                b = self.ser.read(1)
                                if b:
                                    frame = self.kiss_reader.feed_byte(b[0])
                                else:
                                    break
                            else:
                                time.sleep(0.001)
                        if frame:
                            self.handle_kiss_frame(frame)
                    else:
                        # Text data - put back and read line
                        # Since we already consumed the byte, we need to buffer it
                        # This is tricky - let's just read the rest of the line
                        line_bytes = bytearray([byte_val])
                        while True:
                            if self.ser.in_waiting:
                                b = self.ser.read(1)
                                if b:
                                    line_bytes.extend(b)
                                    if b[0] == ord('\n'):
                                        break
                            else:
                                break

                        line = line_bytes.decode('utf-8', errors='replace').strip()
                        if line:
                            self.handle_message(line)
            else:
                time.sleep(0.01)

    def handle_kiss_frame(self, frame_bytes):
        """Handle incoming KISS binary frame"""
        if len(frame_bytes) < 3:
            return

        cmd = frame_bytes[1]
        data_bytes = frame_bytes[2:-1]  # Remove FEND delimiters

        # Unescape data
        data = KISSFramer.unescape_data(data_bytes)

        if cmd == CMD_FILE_READY:
            # File transfer ready (may include fragment count)
            if self.pending_ack == "FILEREADY":
                self.ack_received = True
                # Extract fragment count if present (2 bytes)
                if len(data) >= 2:
                    self.ack_data = int.from_bytes(data[0:2], 'big')

        elif cmd == CMD_CHUNK_ACK:
            # Chunk acknowledgment: seq(2 bytes)
            if len(data) >= 2:
                seq = int.from_bytes(data[0:2], 'big')
                if self.pending_ack == f"CHUNKACK:{seq}":
                    self.ack_received = True

        elif cmd == CMD_FILE_RECEIVED:
            # File received notification from device
            # Payload: transfer_id(16) + sender(16) + filename_len(1) + filename + size(4)
            print(f"[KISS] Got CMD_FILE_RECEIVED, data_len={len(data)}")
            if len(data) < 37:  # Minimum: 16+16+1+0+4
                print(f"✗ Invalid FILE_RECEIVED frame (too small)")
                return

            transfer_id = data[0:16].hex()
            sender_addr = data[16:32].hex()
            filename_len = data[32]
            filename = data[33:33+filename_len].decode('utf-8', errors='replace')
            size = int.from_bytes(data[33+filename_len:37+filename_len], 'big')

            sender_name = self.known_nodes.get(sender_addr, sender_addr[:8])
            print(f"\n📥 Receiving {filename} ({size} bytes) from {sender_name}...")
            print(f"[KISS] transfer_id={transfer_id[:8]}...")

            # Initialize receive state
            self.receiving_files[transfer_id] = {
                'sender': sender_addr,
                'filename': filename,
                'size': size,
                'chunks': []
            }

        elif cmd == CMD_FILE_DATA:
            # File data chunk
            # Payload: transfer_id(16) + chunk_data
            if len(data) < 16:
                return

            transfer_id = data[0:16].hex()
            chunk_data = data[16:]

            if transfer_id in self.receiving_files:
                self.receiving_files[transfer_id]['chunks'].append(chunk_data)
                print(f"[KISS] Got data chunk for {transfer_id[:8]}... ({len(chunk_data)} bytes, total {len(self.receiving_files[transfer_id]['chunks'])} chunks)")

        elif cmd == CMD_FILE_COMPLETE:
            # File transfer complete
            # Payload: transfer_id(16)
            print(f"[KISS] Got CMD_FILE_COMPLETE, data_len={len(data)}")
            if len(data) < 16:
                return

            transfer_id = data[0:16].hex()
            print(f"[KISS] Completing transfer {transfer_id[:8]}...")

            if transfer_id in self.receiving_files:
                file_info = self.receiving_files[transfer_id]
                filename = file_info['filename']
                sender_addr = file_info['sender']
                sender_name = self.known_nodes.get(sender_addr, sender_addr[:8])

                # Reassemble file from chunks
                file_data = b''.join(file_info['chunks'])

                # Save to downloads directory
                downloads_dir = os.path.join(os.path.expanduser('~'), 'Downloads', 'mycorrhizal')
                os.makedirs(downloads_dir, exist_ok=True)

                filepath = os.path.join(downloads_dir, filename)
                with open(filepath, 'wb') as f:
                    f.write(file_data)

                print(f"✓ Saved {filename} from {sender_name}")
                print(f"   📁 {filepath} ({len(file_data)} bytes)")

                # Clean up
                del self.receiving_files[transfer_id]

    def handle_message(self, line):
        """Handle incoming message from device"""
        # Parse different message types
        if line.startswith("NODE:"):
            # Node info: NODE:address
            parts = line.split(":", 1)
            if len(parts) == 2:
                self.node_address = parts[1].strip()
                print(f"\n📍 Your node: {self.node_address}")

        elif line.startswith("PEER:"):
            # New peer discovered: PEER:address
            parts = line.split(":", 1)
            if len(parts) == 2:
                addr = parts[1].strip()
                if addr not in self.known_nodes:
                    name = addr[:8]
                    self.known_nodes[addr] = name
                    print(f"\n👤 Found peer: {name} ({addr})")
                    self.print_prompt()

        elif line.startswith("PEERS:"):
            # Peer count: PEERS:count
            parts = line.split(":", 1)
            if len(parts) == 2:
                count = parts[1].strip()
                print(f"\n👤 Known peers: {count}")
                self.print_prompt()

        elif line.startswith("ROUTES:"):
            # Route count
            parts = line.split(":", 1)
            if len(parts) == 2:
                print(f"🗺️  Routes: {parts[1].strip()}")

        elif line.startswith("TX:") or line.startswith("RX:"):
            # Stats
            print(f"📊 {line}")

        elif line.startswith("SENT:"):
            # Message sent confirmation
            parts = line.split(":", 1)
            if len(parts) == 2:
                print(f"\n✓ Sent to {parts[1].strip()}")
                self.print_prompt()

        elif line.startswith("BROADCAST:"):
            # Broadcast confirmation
            parts = line.split(":", 1)
            if len(parts) == 2:
                print(f"\n✓ Broadcast to {parts[1].strip()}")
                self.print_prompt()

        elif line.startswith("MSG:"):
            # Received message: MSG:sender_addr:message
            parts = line.split(":", 2)
            if len(parts) == 3:
                sender_addr = parts[1].strip()
                message = parts[2].strip()
                sender_name = self.known_nodes.get(sender_addr, sender_addr[:8])

                timestamp = datetime.now().strftime("%H:%M:%S")
                self.message_history.append((timestamp, sender_name, message))

                print(f"\n💬 [{timestamp}] {sender_name}: {message}")
                self.print_prompt()

        elif line.startswith("GROUP:"):
            # Group message: GROUP:group_id:sender_addr:message
            parts = line.split(":", 3)
            if len(parts) == 4:
                group_id = parts[1].strip()
                sender_addr = parts[2].strip()
                message = parts[3].strip()

                group_name = self.groups.get(group_id, {}).get('name', group_id[:8])
                sender_name = self.known_nodes.get(sender_addr, sender_addr[:8])

                timestamp = datetime.now().strftime("%H:%M:%S")
                self.message_history.append((timestamp, f"{group_name}/{sender_name}", message))

                print(f"\n💬 [{timestamp}] [{group_name}] {sender_name}: {message}")
                self.print_prompt()

        elif line.startswith("FILEREADY"):
            # File transfer ready acknowledgment
            if self.pending_ack == "FILEREADY":
                self.ack_received = True

        elif line.startswith("CHUNKACK:"):
            # Chunk acknowledgment: CHUNKACK:123
            parts = line.split(":", 1)
            if len(parts) == 2:
                chunk_num = parts[1].strip()
                if self.pending_ack == f"CHUNKACK:{chunk_num}":
                    self.ack_received = True

        elif line.startswith("INFO:") or line.startswith("ERROR:"):
            # System message
            print(f"\n{line}")

        else:
            # Unknown/debug output
            if line and not line.startswith(">>>"):  # Ignore REPL prompts
                print(f"\n[DEBUG] {line}")

    def print_prompt(self):
        """Print input prompt"""
        target = "..."
        if self.current_target:
            if self.current_target in self.groups:
                target = self.groups[self.current_target]['name']
            elif self.current_target in self.known_nodes:
                target = self.known_nodes[self.current_target]
            else:
                target = self.current_target[:8]

        print(f"\n[{target}] > ", end='', flush=True)

    def cmd_help(self):
        """Show help"""
        print("\n" + "=" * 60)
        print("Mycorrhizal Serial Chat Commands")
        print("=" * 60)
        print("\nDirect Messages:")
        print("  !dm <address> <message>    - Send direct message")
        print("  !sendfile <address> <path> - Send file (max 64KB)")
        print("  !target <address>          - Set current chat target")
        print("  <message>                  - Send to current target")
        print("\nGroup Chat:")
        print("  !group create <name>       - Create new group")
        print("  !group join <group_id>     - Join existing group")
        print("  !group invite <address>    - Invite node to current group")
        print("  !group list                - List known groups")
        print("  !group target <group_id>   - Set group as current target")
        print("\nDiscovery:")
        print("  !announce                  - Send announce to discover peers")
        print("  !peers                     - List known peers")
        print("  !info                      - Show node info")
        print("\nOther:")
        print("  !history                   - Show message history")
        print("  !clear                     - Clear screen")
        print("  !help                      - Show this help")
        print("  !quit                      - Exit chat")
        print("=" * 60)

    def cmd_info(self):
        """Request node info"""
        self.send_command("!info")

    def cmd_announce(self):
        """Send announce"""
        print("\n📣 Sending announce...")
        self.send_command("!announce")

    def cmd_peers(self):
        """List known peers"""
        if not self.known_nodes:
            print("\n👤 No peers discovered yet. Try: !announce")
        else:
            print(f"\n👤 Known peers ({len(self.known_nodes)}):")
            for addr, name in self.known_nodes.items():
                print(f"   {name:10s} {addr}")

    def cmd_dm(self, args):
        """Send direct message"""
        parts = args.split(None, 1)
        if len(parts) < 2:
            print("\n✗ Usage: !dm <address> <message>")
            return

        addr = parts[0]
        message = parts[1]

        # Send to device
        self.send_command(f"!send {addr} {message}")

        # Add to history
        timestamp = datetime.now().strftime("%H:%M:%S")
        target_name = self.known_nodes.get(addr, addr[:8])
        self.message_history.append((timestamp, "You", f"→ {target_name}: {message}"))
        print(f"\n✓ Sent to {target_name}")

    def cmd_sendfile(self, args):
        """Send file to peer"""
        parts = args.split(None, 1)
        if len(parts) < 2:
            print("\n✗ Usage: !sendfile <address> <filepath>")
            return

        addr = parts[0]
        filepath = parts[1].strip()

        # Check if file exists
        if not os.path.exists(filepath):
            print(f"\n✗ File not found: {filepath}")
            return

        # Check file size (64KB limit)
        file_size = os.path.getsize(filepath)
        if file_size > 65536:
            print(f"\n✗ File too large: {file_size} bytes (max 64KB)")
            return

        filename = os.path.basename(filepath)
        target_name = self.known_nodes.get(addr, addr[:8])

        print(f"\n📤 Sending {filename} ({file_size} bytes) to {target_name}...")

        try:
            # Read file (BINARY!)
            with open(filepath, 'rb') as f:
                file_data = f.read()

            # Parse destination address
            try:
                dest_addr = bytes.fromhex(addr)
                if len(dest_addr) != 16:
                    print(f"\n✗ Error: Address must be 32 hex chars (16 bytes)")
                    return
            except ValueError:
                print(f"\n✗ Error: Invalid hex address")
                return

            print(f"   🔵 Using KISS binary protocol (two-phase transfer)")

            # PHASE 1: Query fragment count
            print(f"   📤 Phase 1: Querying fragment count...")
            info_data = bytearray()
            info_data.extend(dest_addr)  # 16 bytes
            info_data.append(len(filename))  # 1 byte
            info_data.extend(filename.encode('utf-8'))  # Variable
            info_data.extend(file_size.to_bytes(4, 'big'))  # 4 bytes

            frame = KISSFramer.encode_frame(CMD_FILE_INFO, bytes(info_data))
            self.ser.write(frame)
            self.ser.flush()

            # Wait for FILEREADY with fragment count
            self.ack_data = None
            if not self.wait_for_ack("FILEREADY", timeout=5.0):
                print(f"\n✗ Error: Firmware not ready (timeout)")
                return

            total_fragments = self.ack_data
            if total_fragments is None:
                print(f"\n✗ Error: No fragment count received")
                return

            print(f"   ✓ Firmware ready: {total_fragments} fragments expected")

            # PHASE 2: Send file data
            print(f"   📤 Phase 2: Sending file...")
            start_data = bytearray()
            start_data.extend(dest_addr)  # 16 bytes
            start_data.append(len(filename))  # 1 byte
            start_data.extend(filename.encode('utf-8'))  # Variable
            start_data.extend(file_size.to_bytes(4, 'big'))  # 4 bytes

            frame = KISSFramer.encode_frame(CMD_FILE_START, bytes(start_data))
            self.ser.write(frame)
            self.ser.flush()

            # Wait for acknowledgment
            if not self.wait_for_ack("FILEREADY", timeout=5.0):
                print(f"\n✗ Error: Transfer start failed (timeout)")
                return

            print(f"   ✓ Transfer started")

            # Send chunks (BINARY, not hex!)
            # Chunk size must account for KISS framing overhead:
            # - Max KISS frame buffer in firmware: 255 bytes
            # - KISS frame: FEND(1) + CMD(1) + escaped_data + FEND(1) = 3 bytes
            # - Chunk payload: seq(2) + data
            # - Worst case escaping: every byte could be escaped (2x size)
            # - Math: (2 + chunk_size) * 2 + 3 <= 255
            # - Solving: chunk_size <= (255 - 3)/2 - 2 = 124 bytes (worst case)
            # - Conservative: 200 bytes allows for typical escaping patterns
            chunk_size = 200  # bytes (safe for KISS 255-byte buffer)
            total_chunks = (len(file_data) + chunk_size - 1) // chunk_size
            print(f"   📦 Sending {total_chunks} chunks ({chunk_size} bytes each, binary)...")

            for i in range(0, len(file_data), chunk_size):
                chunk = file_data[i:i+chunk_size]
                seq = i // chunk_size

                # Encode: seq(2 bytes) + binary data
                chunk_data = seq.to_bytes(2, 'big') + chunk
                frame = KISSFramer.encode_frame(CMD_FILE_CHUNK, chunk_data)

                self.ser.write(frame)
                self.ser.flush()

                # Wait for ACK (longer timeout for LoRa transmission)
                if not self.wait_for_ack(f"CHUNKACK:{seq}", timeout=10.0):
                    print(f"\n✗ Error: Chunk {seq} not acknowledged (timeout)")
                    return

                # Progress indicator
                progress = int(((seq + 1) / total_chunks) * 100)
                if progress % 10 == 0 or seq == total_chunks - 1:
                    print(f"   Progress: {progress}% ({seq + 1}/{total_chunks} chunks)")

            # Send FILE_END
            print(f"   📨 Finalizing transfer...")
            frame = KISSFramer.encode_frame(CMD_FILE_END)
            self.ser.write(frame)
            self.ser.flush()

            time.sleep(0.5)
            print(f"✓ File sent successfully via KISS! ({total_chunks} chunks, {len(file_data)} bytes)")

        except Exception as e:
            print(f"\n✗ Error sending file: {e}")

    def cmd_target(self, target):
        """Set current chat target"""
        if not target:
            self.current_target = None
            print("\n✓ Target cleared")
        else:
            self.current_target = target
            target_name = self.known_nodes.get(target, target[:8])
            print(f"\n✓ Target set to: {target_name}")

    def cmd_history(self):
        """Show message history"""
        if not self.message_history:
            print("\n📜 No messages yet")
        else:
            print(f"\n📜 Message History ({len(self.message_history)} messages):")
            print("-" * 60)
            for timestamp, sender, message in self.message_history[-20:]:  # Last 20
                print(f"[{timestamp}] {sender:15s} {message}")

    def cmd_clear(self):
        """Clear screen"""
        os.system('clear' if os.name == 'posix' else 'cls')
        self.show_header()

    def show_header(self):
        """Show chat header"""
        print("=" * 80)
        print("Mycorrhizal Serial Chat")
        print("=" * 80)
        if self.node_address:
            print(f"📍 Your node: {self.node_address}")
        print(f"📡 Connected: {self.port}")
        print("\nType !help for commands, !quit to exit")
        print("-" * 80)

    def run(self):
        """Run interactive chat"""
        if not self.connect():
            return

        # Start RX thread
        self.running = True
        self.rx_thread = threading.Thread(target=self.rx_worker, daemon=True)
        self.rx_thread.start()

        # Show header
        self.show_header()

        # Request node info
        time.sleep(1)
        self.cmd_info()
        time.sleep(0.5)
        self.cmd_announce()

        # Main input loop
        try:
            while self.running:
                self.print_prompt()
                try:
                    line = input().strip()
                except EOFError:
                    break

                if not line:
                    continue

                # Handle commands
                if line.startswith("!"):
                    cmd_parts = line[1:].split(None, 1)
                    cmd = cmd_parts[0].lower()
                    args = cmd_parts[1] if len(cmd_parts) > 1 else ""

                    if cmd == "quit" or cmd == "exit":
                        break
                    elif cmd == "help":
                        self.cmd_help()
                    elif cmd == "info":
                        self.cmd_info()
                    elif cmd == "announce":
                        self.cmd_announce()
                    elif cmd == "peers":
                        self.cmd_peers()
                    elif cmd == "dm":
                        self.cmd_dm(args)
                    elif cmd == "target":
                        self.cmd_target(args)
                    elif cmd == "history":
                        self.cmd_history()
                    elif cmd == "sendfile":
                        self.cmd_sendfile(args)
                    elif cmd == "clear":
                        self.cmd_clear()
                    else:
                        print(f"\n✗ Unknown command: {cmd}")
                        print("   Type !help for available commands")

                else:
                    # Send to current target
                    if not self.current_target:
                        print("\n✗ No target set. Use !target <address> or !dm <address> <message>")
                    else:
                        self.send_command(f"!send {self.current_target} {line}")

                        # Add to history
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        target_name = self.known_nodes.get(self.current_target, self.current_target[:8])
                        self.message_history.append((timestamp, "You", f"→ {target_name}: {line}"))

        except KeyboardInterrupt:
            print("\n\nInterrupted by user")
        finally:
            self.disconnect()


def scan_ports():
    """Scan for available serial ports"""
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        return None

    print("\n" + "=" * 60)
    print("Available Serial Ports")
    print("=" * 60)

    for i, port in enumerate(ports):
        print(f"  [{i}] {port.device}")
        if port.description:
            print(f"      {port.description}")
        if port.manufacturer:
            print(f"      Manufacturer: {port.manufacturer}")

    print("=" * 60)

    # Auto-select if only one
    if len(ports) == 1:
        print(f"\nAuto-selecting: {ports[0].device}")
        return ports[0].device

    # Prompt user
    while True:
        try:
            choice = input(f"\nSelect port (0-{len(ports)-1}) or Enter to cancel: ").strip()
            if not choice:
                return None
            idx = int(choice)
            if 0 <= idx < len(ports):
                return ports[idx].device
            print(f"Invalid choice. Please select 0-{len(ports)-1}")
        except ValueError:
            print("Invalid input. Please enter a number.")
        except KeyboardInterrupt:
            return None


def main():
    parser = argparse.ArgumentParser(
        description="Mycorrhizal Serial Chat Terminal"
    )
    parser.add_argument(
        '--port', '-p',
        help="Serial port (e.g., /dev/ttyUSB0, COM3)"
    )
    parser.add_argument(
        '--baudrate', '-b',
        type=int,
        default=115200,
        help="Baudrate (default: 115200)"
    )

    args = parser.parse_args()

    # Determine port
    port = args.port
    if not port:
        port = scan_ports()
        if not port:
            print("\n✗ No port selected")
            return 1

    # Create and run chat
    chat = SerialChat(port, args.baudrate)
    chat.run()

    return 0


if __name__ == "__main__":
    sys.exit(main())
