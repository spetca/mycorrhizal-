# Mycorrhizal - Complete Guide

*Forgive me Lord for I have ~~sinned~~ vibe coded v0.1 slop of a mesh communication ecosystem with chat, group chat (wip), and file transfer (wip)*

Mycorrhizal focuses on **local radio and wireless technologies** that don't require internet connectivity/backbone or centralized services for transport. It's like if meshtastic and reticulum had a baby and that baby wasn't very good at what it was suppose to do yet.

---

## Table of Contents

1. [Project Vision](#project-vision)
2. [Quick Start](#quick-start)
3. [Hardware Setup](#hardware-setup)
4. [Flashing Devices](#flashing-devices)
5. [Display Features](#display-features)
6. [Chat Interfaces](#chat-interfaces)
7. [Message Commands](#message-commands)
8. [Architecture](#architecture)
9. [Stack Components](#stack-components)
10. [Storage & Persistence](#storage--persistence)
11. [Serial Communication: Why KISS Protocol?](#serial-communication-why-kiss-protocol)
12. [Security Status](#security-status)
13. [Troubleshooting](#troubleshooting)

---

## Project Vision

### Core Mission
Build a resilient mesh communication network that:

1. Has E2EE and anonyminity 
2. can transport messages extremely long distances through hops
3. Supports messaging, group messaging, and file transfer out of the box (with limitations on payload size)
4. Supports any wireless medium - lora, Ha-Low, bluetooth, wifi, packet radio, etc

### Primary Transport Technologies (Priority Order)

#### 1. LoRa (Long Range Radio) - PRIMARY FOCUS ✅
**Status:** In active development

- Long range (2-10km urban, 15-40km rural)
- Low power consumption
- License-free ISM bands (433/868/915 MHz)
- Works without any infrastructure
- Ideal for disaster/emergency scenarios

**Current:** SX1262 driver fully implemented, TX/RX working, mesh routing operational
**Next:** Improve file transfer reliability

#### 2. Bluetooth LE - 
**Status:** not yet implemented

- Short-range local connectivity (10-100m)
- Configuration interface
- Wireless chat client connection
- Low power

#### 3. WiFi 
**Status:** not yet implemented

- ESP-NOW for mesh
- WiFi Direct peer-to-peer
- High bandwidth, short range

#### 4. Packet Radio / APRS (Ham Radio)
**Status:** Not yet implemented

- Existing ham radio infrastructure
- Long range HF propagation
- Emergency communications standard
- Requires ham radio license

#### 5. HaLow (802.11ah - Long Range WiFi)
**Status:** Not yet implemented

- Sub-1 GHz WiFi (900 MHz band)
- 1km+ range
- Standard WiFi stack compatibility

### Core Use Cases

#### 1. Messaging ✅
- Direct messaging (working)
- Group Messaging
- Store-and-forward for offline nodes (planned)
- Message encryption (not yet implemented)

#### 2. File Transfer 🔄
- File transfer over mesh (in progress)
- Supports up to 64KB files, but in practice only has demonstrated 1KB files successfully
- Automatic fragmentation

#### 3. Information Sharing - Simple Web Content (Planned)
- Serve lightweight HTML pages over mesh
- Emergency information bulletins
- Community announcements
- Resource directories
- Offline Wikipedia snapshots

---

## Quick Start

### 0. clone this repo

### 1. Flash Mycorrhizal Firmware to Heltec V3

```bash
cd utilities/
python flash_device.py --device heltec_v3 --example mycorrhizal_firmware.py
```

This flashes a single unified firmware to your device (like RNode or Meshtastic).
The firmware handles all the mesh networking - you just connect with a chat client.

### 2. Connect with a Chat Client 

**Option A: Serial (USB) - Recommended**
```bash
cd utilities/
python serial_chat.py
```

**Option B: BLE - Not yet implemented**

### 3. Send Your First Message

```
!info          # Show node info
!announce      # Discover peers
!peers         # List discovered peers
!dm <addr> <message>    # Send to specific node
!sendfile <addr> </path/to/file>
```
---


## Currently Supported Devices

- Heltec WiFi LoRa 32 V3 

---

## Flashing Devices Notes

### Using the Flash Utility

#### Full Flash (First Time / Clean Install)

```bash
cd utilities/
python flash_device.py --device heltec_v3 --example mycorrhizal_firmware.py
```

**What it does:**
1. Checks for required tools (esptool, mpremote)
2. Downloads MicroPython firmware (ESP32_GENERIC_S3-20241025-v1.24.0.bin)
3. Erases flash
4. Flashes MicroPython
5. Installs packages (ssd1306 for display)
6. Uploads Mycorrhizal library (`mycorrhizal/` folder)
7. Uploads firmware as `main.py`

**Use when:**
- First time flashing a new device
- MicroPython needs to be updated
- Device has issues and needs a clean slate
- Upgrading from old MicroPython version

#### Quick Update (Skip MicroPython Flash)

```bash
cd utilities/
python flash_device.py --device heltec_v3 --skip-firmware --example mycorrhizal_firmware.py
```

**What it does:**
1. Checks for required tools (mpremote only)
2. **Skips** erasing flash
3. **Skips** flashing MicroPython (uses existing MicroPython)
4. Uploads Mycorrhizal library (`mycorrhizal/` folder)
5. Uploads firmware as `main.py`
6. Resets device

**Use when:**
- MicroPython is already installed and working
- You're updating Mycorrhizal code only
- Testing firmware changes
- Much faster (~30 seconds vs 2+ minutes)
- **Preserves** identity.dat (your node keeps same address!)

**Warning:** Only use `--skip-firmware` if MicroPython is already working. If you've never flashed the device, or if MicroPython is corrupted, do a full flash first.


## Display Features

The Heltec V3 has a 128x64 OLED display with 5 pages you can cycle through by pressing the button.

### Page 1: Main Info (RNode-style)

```
Line 0:   Heltec_Nod             B  ■
Line 10:  9151c5bf9f4d3dbe
Line 18:  12a5c8f7d1e2a6b3
Line 28:  915.0MHz SF9
Line 48:  ┌──────────────────┐ ■T:5
Line 56:  │   waterfall      │ ■R:3
Line 64:  └──────────────────┘
```

**Actual Layout (pixel coordinates):**
- **Line 0 (y=0)**: Device name (first 10 chars), BLE status at x=110, Online status at x=120
- **Line 10 (y=10)**: First 16 chars of 32-char hex address
- **Line 18 (y=18)**: Last 16 chars of 32-char hex address
- **Line 28 (y=28)**: LoRa frequency and spreading factor
- **Lines 48-64**: Waterfall (64px wide, 16px tall) on left side
- **Line 48 (y=48)**: TX activity blip (4x4 square at x=66) + "T:" + packet count (at x=70)
- **Line 56 (y=56)**: RX activity blip (4x4 square at x=66) + "R:" + packet count (at x=70)

**Status Icons (top right):**
- **B** (at x=110) = BLE connected
- **b** (at x=110) = BLE on, not connected
- **■** (at x=120) = Node online (solid 8x8 square)
- **□** (at x=120) = Node offline (hollow 8x8 square)

**TX/RX Activity Blips:**
- Small 4x4 filled square appears at x=66 when active
- TX blip at y=48 (300ms duration)
- RX blip at y=56 (300ms duration)

**Spectrum Waterfall (64x16 pixels):**
- Positioned at x=0, y=48
- Vertical bars = RSSI signal strength (0-14 pixels tall)
- `:` dotted pattern = TX activity markers
- Scrolls left to right (newest on right)
- Updates every 1 second
- Shows up to 62 samples (64px - 2px border)

### Page 2: Network Stats

```
NETWORK STATS
Routes: 2
IDs: 3
TX: 12
RX: 8
5KB / 3KB
```

Shows:
- **Routes**: Number of known routes to other nodes
- **IDs**: Number of known peer identities
- **TX/RX**: Packet counts
- **KB**: Bytes transmitted/received

### Page 3: LoRa Config

```
LORA CONFIG
Freq: 915.0MHz
SF9 BW125k
Power: 14dBm
Rate: 537bps
RSSI: -98dBm
```

Shows current LoRa radio configuration:
- **Freq**: Operating frequency
- **SF**: Spreading factor (5-12, higher = longer range, slower)
- **BW**: Bandwidth in kHz (125/250/500)
- **Power**: TX power in dBm (2-22)
- **Rate**: Calculated bitrate in bps
- **RSSI**: Current received signal strength

### Page 4: BLE Status

Shows Bluetooth connection state:

**When inactive:**
```
BLE STATUS
BLE: Ready
Waiting for
connection...
```

**When connected:**
```
BLE STATUS
BLE: Connected
Client active
```

**When disabled:**
```
BLE STATUS
BLE: Disabled
(Not enabled
in code)
```

### Page 5: Battery

```
BATTERY
Voltage: 3.85V
Level: 75%
Status: DISCHARGING
┌──────────────────────────────┐
│████████████████████░░░░░░░░░░│ ← Battery bar
└──────────────────────────────┘
```

Shows battery status (if LiPo connected):
- Voltage reading
- Percentage estimate
- Charging state
- Visual bar graph

**Note**: Battery monitoring requires ADC calibration for accurate readings.

**Button:** Press to cycle through pages (200ms debounce).

---

## Chat Interfaces

### Option 1: Serial Chat (Recommended)

**Best for: Development, debugging, full-featured chat**

Connect to your device over USB serial for a full terminal chat experience:

```bash
cd utilities/
python serial_chat.py
```
**Commands:**
```
!info                      - Show node info
!announce                  - Discover peers
!peers                     - List known peers
!dm <address> <message>    - Send direct message
!sendfile <address> <path> - Send file (max 64KB)
!target <address>          - Set chat target
<message>                  - Send to current target
!history                   - Show message history
!help                      - Show all commands
!quit                      - Exit
```

## Architecture

### Unified Firmware Design

Mycorrhizal uses a **single firmware** that runs on the device (like RNode or Meshtastic):

```
┌─────────────────────────────────────────────────────────┐
│                  Mycorrhizal Firmware                   │
│                  (runs on Heltec V3)                    │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Node (mesh networking, routing, identity)       │   │
│  │   ├── Identity (Ed25519 signing)                │   │
│  │   ├── RouteTable (multi-hop routing)            │   │
│  │   ├── IdentityCache (known peers)               │   │
│  │   └── TransferManager (file transfers)          │   │
│  └──────────────┬──────────────────────────────────┘   │
│                 │                                       │
│  ┌──────────────▼──────────────┐                       │
│  │ LoRa Phycore (SX1262 radio) │                       │
│  │   - TX/RX packet handling   │                       │
│  │   - Bandwidth management    │                       │
│  │   - Interface modes         │                       │
│  └─────────────────────────────┘                       │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Client Interfaces (serial + BLE)                │   │
│  │   ├── Serial (USB)   → serial_chat.py           │   │
│  │   └── BLE (Nordic)   → ble_chat.py/web          │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Display (OLED) - shows mesh status              │   │
│  │   - 5 pages with network info                   │   │
│  │   - RNode-style waterfall spectrum              │   │
│  │   - TX/RX activity indicators                   │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

**Benefits:**
- One firmware, multiple client options
- Device handles all mesh complexity
- Clients just send/receive messages
- Like RNode: firmware on device, client on computer/phone

### Interface Modes

**FULL (0x01)** - Default
- Forward all announces (subject to bandwidth limits)
- Full mesh participation
- Standard for most nodes

**GATEWAY (0x02)** - Bridge between network segments
- Discovers paths across segments
- Higher announce bandwidth (5% vs 2%)
- For Raspberry Pi connecting LoRa to WiFi/Internet

**BOUNDARY (0x03)** - Connects different networks
- Filters announces (only forwards local announces with low hop count)
- Prevents flooding
- For cell gateways and region gateways

**ACCESS_POINT (0x04)** - Quiet mode
- Doesn't auto-announce
- Shorter path expiry
- For mobile devices and temporary connections

**ROAMING (0x05)** - Mobile nodes
- Fast path expiration (30s vs 30min)
- Frequent re-announces (1min vs 5min)
- For vehicles, drones, hikers

### Packet Format

**32-byte header** (no source address for privacy):
```
┌─────────────────────────────────────────────────────────────┐
│ Header (fixed 32 bytes)                                     │
├─────────────────────────────────────────────────────────────┤
│ Flags (1 byte) | TTL (1 byte) | Hop Count (1 byte)         │
│ Packet Type (1 byte)                                        │
│ Destination Address (16 bytes)                              │
│ Payload Length (2 bytes)                                    │
│ Payload Hash (8 bytes)                                      │
│ Reserved (2 bytes)                                          │
├─────────────────────────────────────────────────────────────┤
│ Payload (variable length, possibly encrypted)              │
└─────────────────────────────────────────────────────────────┘
```

**Source address is implicit:**
- Proven by encryption (only sender can encrypt to destination's key)
- Proven by signature (verifies sender's identity)
- Return path cached by routing layer
- Intermediate nodes can't see source identity

### Routing

**Simple LRU route table:**
- Each route: destination → next_hop + interface + hop_count
- Routes learned from announces
- Routes expire after 30 minutes (configurable)
- Max routes based on platform:
  - MCU nodes: 100 routes
  - Desktop nodes: 100,000+ routes

**Multi-hop routing (supports 100+ hops):**
1. Node A announces → Node B receives → adds route to A
2. Node B forwards announce → Node C receives → adds route to A (via B)
3. Node C can send to A, and Node B will forward

**Default configuration: 128 hops maximum**

**Real-world distance estimates:**

| Scenario | Per-Hop Range | 128 Hops Coverage | Notes |
|----------|--------------|-------------------|-------|
| **Urban/City** | 0.5-2 km (0.3-1.2 mi) | 64-256 km (40-160 mi) | Buildings, obstacles |
| **Suburban** | 2-5 km (1.2-3 mi) | 256-640 km (160-400 mi) | Mix of open/obstacles |
| **Rural/Open** | 5-10 km (3-6 mi) | 640-1,280 km (400-800 mi) | Fields, low obstacles |
| **Line-of-Sight (Mountain)** | 15-40 km (10-25 mi) | 1,920-5,120 km (1,200-3,200 mi) | Ideal conditions |

**Examples:**
- **City mesh**: 128 hops = ~100-200 km (60-125 miles) - covers entire metropolitan area
- **Rural network**: 128 hops = ~500-800 km (300-500 miles) - multi-county/state coverage
- **Mountain relay network**: 128 hops = ~2,000-4,000 km (1,200-2,500 miles) - transcontinental possible!


**Configuration examples:**

```python
# Mobile Node (Roaming)
node = Node(name="mobile")
node.max_hops = 32  # Limited range for mobile use
node.interface_mode = InterfaceMode.ROAMING

# Gateway Node (Bridge networks)
node = Node(name="gateway")
node.max_hops = 128  # Extended range
node.interface_mode = InterfaceMode.GATEWAY  # 5% bandwidth

# Boundary Node (Regional hub)
node = Node(name="boundary")
node.max_hops = 255  # Maximum range
node.interface_mode = InterfaceMode.BOUNDARY  # Filters distant announces
```

### Platform-Specific Code

**MicroPython:**
- Temporary crypto (urandom, SHA256 hash - NOT SECURE)
- Manual announce checking (no threading)
- Simplified HKDF
- Fixed-size buffers
- No datetime objects

**CPython:**
- Full cryptography library (proper Ed25519/X25519)
- Threading-based auto-announce
- Proper HKDF
- Dynamic allocation

**⚠️ Warning:** Current MicroPython crypto is NOT production-ready. It's a temporary workaround to get the system running.

---

## Storage & Persistence

### Identity Persistence ✅
Nodes maintain the same address across reboots by saving identity keys to persistent storage.

**Platform-Agnostic Implementation:**
- **MicroPython (Heltec):** Saves to `/identity.dat` in root filesystem
- **CPython (Mac/PC):** Saves to `~/.local/share/mycorrhizal/identity.dat`

**How It Works:**
```python
# Node automatically loads/saves identity
node = Node(name="mynode", persistent_identity=True)  # Default
```

**On First Boot:**
1. No identity file exists → Generate new keys
2. Save to storage
3. Display shows new address

**On Subsequent Boots:**
1. Load identity from storage
2. Use same keys → Same address!
3. Peers remember you

**Manual Identity Management:**
```python
from mycorrhizal.storage.identity_storage import IdentityStorage

# Check if identity exists
if IdentityStorage.exists():
    print("Identity found")

# Delete identity (reset to new on next boot)
IdentityStorage.delete()

# Disable persistence
node = Node(persistent_identity=False)  # New identity each boot
```

**Storage Locations:**
- **Heltec/ESP32:** `/identity.dat` (128 bytes)
- **Mac/Linux:** `~/.local/share/mycorrhizal/identity.dat`
- **Windows:** `%APPDATA%\mycorrhizal\identity.dat` (future)

---

## Serial Communication: Why KISS Protocol?

### The Problem with Pure Serial (Text-Based)

Early versions of Mycorrhizal used simple text commands over serial:
```
!sendfile <addr> <filename>
CHUNK0:48656c6c6f...
CHUNK1:576f726c64...
```

**Why this fails for binary data:**

1. **Line Buffering Issues**
   - Serial ports buffer until newline (`\n`)
   - Binary data might not contain newlines for thousands of bytes
   - Chunks arrive unpredictably, sometimes concatenated

2. **Special Character Conflicts**
   - Binary data contains control characters (`\n`, `\r`, `\0x03`)
   - Serial interpreters treat these as commands
   - Ctrl-C (0x03) aborts transfers
   - Newlines split data unexpectedly

3. **Hex Encoding Overhead**
   - Binary → hex doubles size (1 byte = 2 hex chars)
   - 850 bytes → 1700 chars → multiple serial packets
   - Parsing hex is slow on microcontrollers

4. **No Flow Control**
   - Desktop sends chunks faster than firmware can process
   - No acknowledgment of receipt
   - Lost chunks = corrupted files

### KISS Protocol: Reliable Binary Framing

**KISS (Keep It Simple, Stupid)** is a proven protocol from the 1980s used by:
- **RNode** (LoRa TNC devices)
- **Ham radio TNCs** (Terminal Node Controllers)
- **APRS** (Automatic Packet Reporting System)

**Frame format:**
```
[FEND] [CMD] [DATA...] [FEND]
 0xC0   0x10   payload    0xC0
```

**Key features:**

1. **Binary-Safe Framing**
   - Special byte (FEND = 0xC0) marks frame boundaries
   - Data is escaped if it contains FEND:
     - 0xC0 → 0xDB 0xDC (FESC TFEND)
     - 0xDB → 0xDB 0xDD (FESC TFESC)

2. **Reliable Delimiters**
   - Each frame is self-contained
   - No line buffering issues
   - Works with any binary data

3. **Command Byte**
   - First byte identifies message type
   - CMD_FILE_INFO, CMD_FILE_START, CMD_FILE_CHUNK, etc.
   - Easy to route different operations

4. **No Encoding Overhead**
   - Send raw bytes (only ~2% escape overhead)
   - Much faster than hex encoding
   - Less memory usage


### How KISS File Transfer Works

#### Protocol Flow with End Flags

```
Desktop → [C0][11][addr+filename+size][C0]     (FILE_START)
Firmware → [C0][14][C0]                        (FILE_READY ack)
Desktop → [C0][12][seq+data][C0]               (FILE_CHUNK)
Firmware → Sends LoRa fragments with flags=0x00
Firmware → [C0][15][seq][C0]                   (CHUNK_ACK)
...repeat for all chunks...
Desktop → [C0][13][C0]                         (FILE_END)
Firmware → Sends final LoRa fragment with flags=0x01 (FINAL)
```

**Fragment Format:**
```
LoRa Fragment: [transfer_id(16)][index(1)][flags(1)][data(up to 200)]

Flags:
  0x00 = More fragments coming
  0x01 = FINAL fragment (last one)
```

**Why end flags?**

The firmware doesn't need to predict fragment count! Instead:
- Fragments are numbered sequentially (0, 1, 2...)
- Last fragment has FINAL flag set
- Receiver knows transfer is complete when FINAL arrives
- No prediction errors, works with any chunk size

#### Command Codes

```python
CMD_FILE_INFO  = 0x10   # Query: How many fragments?
CMD_FILE_START = 0x11   # Start transfer (Phase 2)
CMD_FILE_CHUNK = 0x12   # Binary data chunk
CMD_FILE_END   = 0x13   # Transfer complete
CMD_FILE_READY = 0x14   # ACK (includes fragment count)
CMD_CHUNK_ACK  = 0x15   # Chunk received
```

#### File Receive (Desktop Client)

When a file is received over LoRa, the firmware relays it to the connected desktop client:

```
Firmware → Desktop: FILE:<sender>:<transfer_id>:<filename>:<size>
Firmware → Desktop: FILEDATA:<transfer_id>:<hex_chunk>
Firmware → Desktop: FILEDATA:<transfer_id>:<hex_chunk>
...
Firmware → Desktop: FILEEND:<transfer_id>
```

Desktop saves to `~/Downloads/mycorrhizal/`

### Technical References

---

## Security Status

### ⚠️ CRITICAL: NOT PRODUCTION READY

Mycorrhizal has **major security gaps** that must be fixed before real-world use.

### ✅ What's Implemented
- Ed25519 signing keys (keypair generation)
- X25519 encryption keys (keypair generation)
- SHA-256 hashing
- 128-bit addresses from public key hash
- Packet signature field exists
- Identity persistence

### ❌ Critical Security Gaps

#### 1. No Signature Verification 🔴 CRITICAL
**Status:** Signatures generated but NOT verified

```python
def verify_signature(self, public_key):
    print("WARNING: Signature verification skipped")
    return True  # Always returns True!
```

**Risk:** Anyone can impersonate anyone
**Fix:** Implement actual Ed25519 verification

#### 2. No Key Distribution 🔴 CRITICAL
**Status:** Nodes don't exchange/store public keys properly

**Risk:** Can't verify signatures without public keys
**Fix:** Store public keys from announce packets

#### 3. No Encryption 🔴 CRITICAL
**Status:** Messages sent in PLAINTEXT

**Risk:** All traffic is public
**Fix:** Implement X25519 key exchange + ChaCha20-Poly1305 encryption

#### 4. Weak Route Authentication 🟡 MEDIUM
**Risk:** Route poisoning attacks possible
**Fix:** Sign route announcements

#### 5. No Forward Secrecy 🟡 MEDIUM
**Risk:** Compromised keys = all past messages readable
**Fix:** Ephemeral session keys

#### 6. Identity Storage Not Encrypted 🟡 MEDIUM
**Risk:** Physical access = key theft (`/identity.dat` is plaintext)
**Fix:** Encrypt identity file with device key

#### 7. No Anti-Replay Protection 🟡 MEDIUM
**Risk:** Old packets can be replayed
**Fix:** Sequence numbers + timestamps

### Implementation Roadmap

#### Phase 1: Basic Security (v0.2) - NEXT
1. Implement signature verification
2. Store public keys from announces
3. Verify all incoming packets
4. Reject unsigned/invalid packets

#### Phase 2: Encryption (v0.3)
1. X25519 key exchange implementation
2. Message encryption (ChaCha20-Poly1305)
3. Encrypt unicast messages
4. Plaintext broadcasts for discovery

#### Phase 3: Advanced Security (v0.4)
1. Ephemeral keys (forward secrecy)
2. Anti-replay protection
3. Encrypt identity storage
4. Key revocation

### Security Warnings

**DO NOT USE IN PRODUCTION** - This software is experimental with critical security gaps.

**Assume All Traffic Is PUBLIC** - Until encryption is implemented, treat all messages as public broadcasts.

**Physical Security** - Devices store private keys in plaintext. Physical access = complete compromise.

---
