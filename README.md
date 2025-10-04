# Mycorrhizal

> A privacy-focused, decentralized mesh networking stack for secure, low-bandwidth communication over LoRa and other physical layers.

*Forgive me Lord for I have ~~sinned~~ vibe coded v0.1 slop of a mesh communication ecosystem with chat, group chat, and file transfer*

Like if Meshtastic and Reticulum had a baby that wasn't very good at what it was supposed to do yet.

---

## Demo Videos

### Direct Messaging
https://github.com/user-attachments/assets/6535c8fb-1978-4d01-91ae-b25f78b6e2d7

### File Transfer
https://github.com/user-attachments/assets/fccf7da6-b3dc-4d9d-b948-00ce303d5d27

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Core Features](#core-features)
3. [How It Works](#how-it-works)
   - [Direct Messages](#direct-messages-dms)
   - [Group Chat (Colony)](#group-chat-colony)
   - [File Transfer](#file-transfer)
4. [Hardware Setup](#hardware-setup)
5. [Chat Interfaces](#chat-interfaces)
6. [Architecture](#architecture)
7. [Packet Format](#packet-format)
8. [Routing & Multi-Hop](#routing--multi-hop)
9. [Display Features](#display-features)
10. [Security Status](#security-status)
11. [Development](#development)

---

## Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/spetca/mycorrhizal.git
cd mycorrhizal
```

### 2. Flash Firmware to Heltec V3

```bash
cd utilities/
python flash_device.py --device heltec_v3 --example mycorrhizal_firmware.py
```

This flashes unified firmware to your device (like RNode or Meshtastic). The firmware handles all mesh networking - you just connect with a chat client.

### 3. Connect with Chat Client

**Web Interface (Recommended)**
```bash
cd apps/
open web_chat.html in your browser
```

Click "Connect Serial" and select your device. Start chatting!

---

## Core Features

### ✅ What Works Now

- **Direct messaging** - Send encrypted DMs to peers
- **Group chat (Colony)** - Multi-party chat with shared keys
- **File transfer** - Send files up to 64KB (tested reliably with 1KB files)
- **Multi-hop routing** - Messages relay through intermediate nodes (up to 128 hops)
- **Source anonymity** - No source address in packets for privacy
- **Identity persistence** - Nodes keep the same address across reboots
- **Web UI** - Modern chat interface with WebSerial support
- **LoRa support** - Heltec V3 (ESP32-S3 + SX1262)

### 🚧 In Progress

- **Signature verification** - Currently signs but doesn't verify
- **E2E encryption** - Keys exist but not yet used
- **Multi-device group chat** - Works with 2 nodes, testing with more
- **Bluetooth LE interface** - Nordic UART service

### 📋 Planned

- **WiFi mesh** - 802.11s or custom protocol
- **Bluetooth mesh** - BLE flooding mesh
- **Store-and-forward** - Offline message delivery
- **Forward secrecy** - Ephemeral session keys

---

## How It Works

### Direct Messages (DMs)

DMs are simple unicast DATA packets sent between two nodes.

**Packet Flow:**
```
Alice                    Router                   Bob
  |                         |                       |
  | 1. Create DATA packet   |                       |
  |    - Type: DATA (0x01)  |                       |
  |    - Dest: Bob's addr   |                       |
  |    - Payload: "Hello"   |                       |
  |    - Sign with Alice's  |                       |
  |      private key        |                       |
  |                         |                       |
  | 2. Send via LoRa -----> |                       |
  |                         |                       |
  |                         | 3. Check destination  |
  |                         |    Not for me?        |
  |                         |    Forward to Bob --> |
  |                         |                       |
  |                         |                   4. Receive
  |                         |                      Verify sig
  |                         |                      Decrypt
  |                         |                      Display
```

**Wire Format:**
```
[32-byte header][N-byte payload]["Hello"][64-byte signature]
```

**Header Breakdown (32 bytes):**
- Flags: `0x40` (SIGNED)
- TTL: `32` (hops remaining)
- Hop count: `0`
- Type: `0x01` (DATA)
- Destination: Bob's 16-byte address
- Payload length: `5` (2 bytes, big-endian)
- Payload hash: First 8 bytes of SHA256("Hello")
- Reserved: 2 bytes (zeros)

**Total Size:** 32 + 5 + 64 = **101 bytes** (well under LoRa's 255-byte limit)

---

### Group Chat (Colony)

Colonies use **shared symmetric keys** for group encryption. All members have the same group key and can decrypt each other's messages.

**Colony Setup:**
```
Alice (creator)          Bob (invitee)
  |                         |
  | 1. Create colony        |
  |    - Generate group key |
  |    - Colony ID = hash   |
  |      of group key       |
  |                         |
  | 2. Add Bob as member    |
  |                         |
  | 3. Send invitation ---> |
  |    Format:              |
  |    COLONY_INVITE:       |
  |      <colony_id>:       |
  |      <group_key>:       |
  |      <name>             |
  |                         |
  |                     4. Receive invite
  |                        Join colony
  |                        Save group key
  |                        Add Alice as member
```

**Sending Colony Messages:**
```
Alice                                    Bob
  |                                       |
  | 1. Encrypt with group key             |
  |    Plaintext: "Hello group"           |
  |    Encrypted: ChaCha20-Poly1305       |
  |                                       |
  | 2. Build payload:                     |
  |    [colony_id (16)][encrypted data]   |
  |                                       |
  | 3. Send as DATA packet --------------> |
  |    Destination: Bob's address         |
  |                                       |
  |                                   4. Receive
  |                                      Check colony_id
  |                                      Decrypt with group key
  |                                      Auto-add Alice if new
  |                                      Display message
```

**Why colony_id first?**
- Router can quickly check if it's a colony message (first 16 bytes)
- If colony_id matches a known colony, route to that colony handler
- Efficient filtering without decryption

**Member Discovery:**
- Members auto-added when they send their first message
- No need to pre-sync member lists
- Invitation only contains colony_id + group_key + name (~126 bytes payload)
- Total invitation size: 32 + 126 + 64 = **222 bytes** (under 255 limit)

---

### File Transfer

Files are sent using **fragmented DATA packets** with KISS framing for reliability.

**Fragment Format:**
```
[transfer_id (16)][index (1)][flags (1)][data (up to 200)]
```

**Flags:**
- `0x00` - More fragments coming
- `0x01` - FINAL fragment (last one)

**Complete Flow:**

```
Desktop Client           Firmware (Alice)          Firmware (Bob)        Bob's Client
     |                         |                         |                      |
     | 1. FILE_START           |                         |                      |
     |    [KISS frame]         |                         |                      |
     |    addr + filename      |                         |                      |
     |    + size               |                         |                      |
     | ----------------------> |                         |                      |
     |                         |                         |                      |
     |                     2. Calculate fragments        |                      |
     |                        Create transfer_id         |                      |
     |                         |                         |                      |
     |                     3. FILE_READY (ACK)           |                      |
     | <---------------------- |                         |                      |
     |                         |                         |                      |
     | 4. FILE_CHUNK 0         |                         |                      |
     |    [KISS frame]         |                         |                      |
     |    seq + data           |                         |                      |
     | ----------------------> |                         |                      |
     |                         |                         |                      |
     |                     5. Send fragment 0 over LoRa  |                      |
     |                        [transfer_id][0][0x00][data]                      |
     |                        ------------------->        |                      |
     |                         |                         |                      |
     |                         |                     6. Receive frag 0          |
     |                         |                        Store in buffer         |
     |                         |                         |                      |
     |                     7. CHUNK_ACK                  |                      |
     | <---------------------- |                         |                      |
     |                         |                         |                      |
     | 8. FILE_CHUNK 1         |                         |                      |
     | ----------------------> |                         |                      |
     |                         |                         |                      |
     |                     9. Send fragment 1 over LoRa  |                      |
     |                        ------------------->        |                      |
     |                         |                         |                      |
     ... (repeat for all chunks) ...                     |                      |
     |                         |                         |                      |
     | N. FILE_END             |                         |                      |
     | ----------------------> |                         |                      |
     |                         |                         |                      |
     |                     N+1. Send FINAL fragment      |                      |
     |                         [transfer_id][N][0x01][data]                     |
     |                         ------------------->       |                      |
     |                         |                         |                      |
     |                         |                     N+2. Receive FINAL         |
     |                         |                          Reassemble file       |
     |                         |                          Verify integrity      |
     |                         |                         |                      |
     |                         |                     N+3. Send to client        |
     |                         |                          FILE:<metadata>       |
     |                         |                          FILEDATA:<chunks>     |
     |                         |                          FILEEND               |
     |                         |                         | -------------------> |
     |                         |                         |                      |
     |                         |                         |                  N+4. Save file
```

**KISS Protocol:**
- Binary-safe framing with escape sequences
- `[FEND (0xC0)][CMD][DATA][FEND (0xC0)]`
- Escaping: `0xC0 → 0xDB 0xDC`, `0xDB → 0xDB 0xDD`
- Commands: FILE_START (0x11), FILE_CHUNK (0x12), FILE_END (0x13), etc.

**Why KISS?**
1. **Binary-safe** - No issues with control characters in file data
2. **Reliable framing** - Each frame is self-contained
3. **No encoding overhead** - Send raw bytes (~2% escape overhead vs 100% for hex)
4. **Flow control** - ACKs prevent buffer overflow
5. **Proven protocol** - Used by RNode, ham radio TNCs, APRS

**File Size Limits:**
- **Theoretical max:** 64KB (limited by fragment reassembly buffer)
- **Tested reliably:** 1KB files
- **LoRa constraints:** ~200 bytes per fragment, 255 bytes total packet size

---

## Hardware Setup

### Supported Devices

- **Heltec WiFi LoRa 32 V3** (ESP32-S3 + SX1262 LoRa radio)

### Wiring

Heltec V3 has integrated LoRa radio - no wiring needed!

**Built-in components:**
- ESP32-S3 (dual-core, 240MHz)
- SX1262 LoRa transceiver
- 128x64 OLED display
- USB-C (programming + serial)
- Li-Po battery connector

---

## Chat Interfaces

### Web UI (apps/web_chat.html)

Modern browser-based interface using WebSerial API.

**Features:**
- Direct messages
- Group chat with multi-select
- File transfer (drag & drop)
- Brutalist black/white styling
- Message timestamps
- Unread indicators
- Auto-discovery of peers

**Requirements:**
- Chrome/Edge (WebSerial support)
- USB connection to device

**Usage:**
1. Open `apps/web_chat.html` in browser
2. Click "Connect Serial"
3. Select your device port
4. Start chatting!

### Serial CLI (apps/serial_chat.py)

Terminal-based interface for debugging.

```bash
cd apps/
python serial_chat.py
```

**Commands:**
- `!announce` - Broadcast presence
- `!peers` - List discovered peers
- `!send <addr> <msg>` - Send DM
- `!info` - Show node stats
- `!transfers` - List active file transfers

---

## Architecture

### Unified Firmware Design

Mycorrhizal uses **single firmware** that runs on the device (like RNode or Meshtastic):

```
┌─────────────────────────────────────────────────────────┐
│                  Mycorrhizal Firmware                   │
│                  (runs on Heltec V3)                    │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Node (mesh networking, routing, identity)       │   │
│  │   ├── Identity (Ed25519 signing, X25519 encrypt)│   │
│  │   ├── RouteTable (multi-hop routing)            │   │
│  │   ├── IdentityCache (known peers)               │   │
│  │   ├── Colony (group chat management)            │   │
│  │   └── TransferManager (file fragmentation)      │   │
│  └──────────────┬──────────────────────────────────┘   │
│                 │                                       │
│  ┌──────────────▼──────────────┐                       │
│  │ LoRa Phycore (SX1262 radio) │                       │
│  │   - TX/RX packet handling   │                       │
│  │   - Bandwidth management    │                       │
│  │   - 915MHz, SF9, BW125kHz   │                       │
│  └─────────────────────────────┘                       │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Client Interfaces (serial + BLE)                │   │
│  │   ├── Serial (USB)   → web_chat.html           │   │
│  │   └── BLE (Nordic)   → mobile apps (future)     │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Display (OLED) - mesh status                    │   │
│  │   - 5 pages with network info                   │   │
│  │   - Spectrum waterfall                          │   │
│  │   - TX/RX activity indicators                   │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

**Benefits:**
- One firmware, multiple client options
- Device handles all mesh complexity
- Clients just send/receive messages
- Like RNode: firmware on device, client on computer/phone

---

## Packet Format

### Header Structure (32 bytes)

```
┌─────────────────────────────────────────────────────────────┐
│ Header (fixed 32 bytes)                                     │
├─────────────────────────────────────────────────────────────┤
│ Flags (1) | TTL (1) | Hop Count (1) | Type (1)             │
│ Destination Address (16 bytes)                              │
│ Payload Length (2 bytes, big-endian)                        │
│ Payload Hash (8 bytes, SHA256 truncated)                    │
│ Reserved (2 bytes)                                          │
├─────────────────────────────────────────────────────────────┤
│ Payload (variable length, 0-65535 bytes)                   │
├─────────────────────────────────────────────────────────────┤
│ Signature (64 bytes, Ed25519, if SIGNED flag set)          │
└─────────────────────────────────────────────────────────────┘
```

### Packet Types

| Type | Value | Purpose |
|------|-------|---------|
| DATA | 0x01 | Regular messages, files, colony messages |
| ANNOUNCE | 0x02 | Node presence broadcast (includes public key) |
| PATH_REQUEST | 0x03 | Request route to destination |
| PATH_RESPONSE | 0x04 | Reply with path information |
| ACK | 0x05 | Acknowledgment |
| KEEPALIVE | 0x06 | Keep connection alive |

### Packet Flags (Bit Flags)

| Bit | Flag | Description |
|-----|------|-------------|
| 7 | ENCRYPTED | Payload encrypted with X25519 + ChaCha20-Poly1305 |
| 6 | SIGNED | Packet includes 64-byte Ed25519 signature |
| 5 | PRIORITY | High priority (routing preference) |
| 4 | FRAGMENTED | Part of fragmented file transfer |
| 3-0 | Reserved | Future use |

### Privacy Design

**No source address in header!**

Source identity is proven through:
- **Encryption** - Only sender can encrypt to destination's public key
- **Signature** - Verifies sender's identity (64-byte Ed25519)
- **Return path** - Cached by routing layer from announces

**Benefits:**
- Intermediate routers can't see source
- Only destination knows who sent the message
- Reduces header overhead (16 bytes saved)

---

## Routing & Multi-Hop

### Route Discovery

Routes are learned from ANNOUNCE packets:

```
Node A                  Node B                  Node C
  |                       |                       |
  | 1. ANNOUNCE           |                       |
  |    (broadcast)        |                       |
  | --------------------> |                       |
  |                       |                       |
  |                   2. Add route: A via direct  |
  |                      Increment hop count      |
  |                      Forward ANNOUNCE ------> |
  |                       |                       |
  |                       |                   3. Add route:
  |                       |                      A via B
  |                       |                      (2 hops)
```

### Route Table

Simple LRU cache:
- **Entry:** `destination → (next_hop, interface, hop_count, timestamp)`
- **Expiry:** 30 minutes (configurable)
- **Capacity:** 100 routes (MCU), 100,000+ (desktop)

### Multi-Hop Example

**Network topology:**
```
Alice ←→ Router1 ←→ Router2 ←→ Bob
```

**Message flow (Alice → Bob):**
```
1. Alice creates packet:
   - Destination: Bob's address
   - TTL: 32
   - Hop count: 0

2. Alice sends to Router1:
   - Router1 receives
   - Checks destination ≠ Router1's address
   - Looks up Bob in route table → next_hop = Router2
   - Increments hop count to 1
   - Decrements TTL to 31
   - Forwards to Router2

3. Router2 receives:
   - Checks destination ≠ Router2's address
   - Looks up Bob in route table → next_hop = Bob (direct)
   - Increments hop count to 2
   - Decrements TTL to 30
   - Forwards to Bob

4. Bob receives:
   - Destination matches Bob's address
   - Delivers to application layer
   - Verifies signature (learns source = Alice)
   - Decrypts payload
```

### Distance Coverage

| Scenario | Per-Hop Range | 128 Hops Coverage |
|----------|--------------|-------------------|
| **Urban** | 0.5-2 km | 64-256 km (40-160 mi) |
| **Suburban** | 2-5 km | 256-640 km (160-400 mi) |
| **Rural** | 5-10 km | 640-1,280 km (400-800 mi) |
| **Line-of-Sight** | 15-40 km | 1,920-5,120 km (1,200-3,200 mi) |

**Example:** A city mesh with 128 hops can cover an entire metropolitan area (100-200 km radius).

---

## Display Features

The Heltec V3 has a 128x64 OLED with 5 pages (cycle with button):

### Page 1: Main Info (RNode-style)
```
Heltec_Nod             B  ■
9151c5bf9f4d3dbe
12a5c8f7d1e2a6b3
915.0MHz SF9
┌──────────────────┐ ■T:5
│   waterfall      │ ■R:3
└──────────────────┘
```

- **Top right:** BLE status (B/b), online indicator (■/□)
- **Address:** Your node's 32-char hex address (16 chars per line)
- **LoRa config:** Frequency and spreading factor
- **Waterfall:** RSSI spectrum (scrolling, 64x16 pixels)
- **TX/RX blips:** Activity indicators with packet counts

### Page 2: Network Stats
```
NETWORK STATS
Routes: 2
IDs: 3
TX: 12  RX: 8
5KB / 3KB
```

### Page 3: LoRa Config
```
LORA CONFIG
Freq: 915.0MHz
SF9 BW125kHz
Power: 14dBm
Rate: 537bps
RSSI: -98dBm
```

### Page 4: BLE Status
```
BLE STATUS
BLE: Connected
Client active
```

### Page 5: File Transfers
```
TRANSFERS
Active: 2
█████░░░░░ 50%
File: photo.jpg
```

---

## Security Status

### ⚠️ CRITICAL: NOT PRODUCTION READY

Mycorrhizal has **major security gaps** that must be fixed before real-world use.

### ✅ Implemented
- Ed25519 signing keys (generation)
- X25519 encryption keys (generation)
- SHA-256 hashing
- 128-bit addresses from public key hash
- Packet signature field
- Identity persistence

### ❌ Critical Gaps

#### 1. No Signature Verification 🔴
**Status:** Signatures generated but NOT verified

```python
def verify_signature(self, public_key):
    print("WARNING: Signature verification skipped")
    return True  # Always returns True!
```

**Risk:** Anyone can impersonate anyone
**Fix:** Implement Ed25519 verification

#### 2. No Key Distribution 🔴
**Status:** Nodes don't exchange/store public keys properly

**Risk:** Can't verify signatures without public keys
**Fix:** Store public keys from announce packets

#### 3. No Encryption 🔴
**Status:** Messages sent in PLAINTEXT

**Risk:** All traffic is public
**Fix:** Implement X25519 ECDH + ChaCha20-Poly1305

#### 4. Weak Route Authentication 🟡
**Risk:** Route poisoning attacks possible
**Fix:** Sign route announcements

#### 5. No Forward Secrecy 🟡
**Risk:** Compromised keys = all past messages readable
**Fix:** Ephemeral session keys (Double Ratchet)

#### 6. Identity Storage Not Encrypted 🟡
**Risk:** Physical access = key theft (`/identity.dat` is plaintext)
**Fix:** Encrypt identity file with device key

#### 7. No Anti-Replay Protection 🟡
**Risk:** Old packets can be replayed
**Fix:** Sequence numbers + timestamps

### Implementation Roadmap

**Phase 1: Basic Security (v0.2) - NEXT**
1. Implement signature verification
2. Store public keys from announces
3. Verify all incoming packets
4. Reject unsigned/invalid packets

**Phase 2: Encryption (v0.3)**
1. X25519 key exchange
2. Message encryption (ChaCha20-Poly1305)
3. Encrypt unicast messages
4. Plaintext broadcasts for discovery

**Phase 3: Advanced Security (v0.4)**
1. Ephemeral keys (forward secrecy)
2. Anti-replay protection
3. Encrypt identity storage
4. Key revocation

### Current Security Warnings

⚠️ **DO NOT USE IN PRODUCTION** - Experimental software with critical security gaps

⚠️ **Assume All Traffic Is PUBLIC** - Until encryption is implemented

⚠️ **Physical Security** - Devices store private keys in plaintext

---

## Development

### Flashing Firmware

**Full flash (first time):**
```bash
cd utilities/
python flash_device.py --device heltec_v3 --example mycorrhizal_firmware.py
```

**Quick update (skip MicroPython flash):**
```bash
python flash_device.py --device heltec_v3 --skip-firmware --example mycorrhizal_firmware.py
```

### Project Structure

```
mycorrhizal/
├── mycorrhizal/          # Core library
│   ├── core/             # Node, routing, identity cache
│   ├── crypto/           # Ed25519, X25519, encryption
│   ├── transport/        # Packets, fragmentation
│   ├── phycore/          # Physical layer (LoRa, UDP)
│   ├── devices/          # Hardware drivers (SX1262, Heltec)
│   ├── messaging/        # Colony (group chat)
│   ├── routing/          # Route table
│   ├── storage/          # Identity persistence
│   └── ui/               # Display, BLE
├── firmware/             # Device firmware
│   └── mycorrhizal_firmware.py
├── apps/                 # Client applications
│   ├── web_chat.html     # Web UI
│   └── serial_chat.py    # CLI client
├── utilities/            # Tools
│   ├── flash_device.py   # Firmware flasher
│   └── mycctl.py         # CLI control utility
├── examples/             # Example scripts
└── tests/                # Unit tests
```

### Requirements

**Desktop (for clients):**
- Python 3.8+
- pyserial (for serial communication)

**Device (Heltec V3):**
- MicroPython 1.24.0+
- ssd1306 (OLED driver, auto-installed)

### Contributing

This is experimental software. Contributions welcome!

**Priority areas:**
1. Signature verification implementation
2. E2E encryption (X25519 + ChaCha20)
3. Multi-device group chat testing
4. File transfer reliability improvements
5. Documentation

### License

See LICENSE file for details.

---

## Troubleshooting

### Device won't flash
- Try erasing flash first: `esptool.py --port /dev/ttyUSB0 erase_flash`
- Check USB cable (needs data lines, not just power)
- Press BOOT button during flash if needed

### No peers discovered
- Both devices need to announce: `!announce`
- Check LoRa frequency matches (915MHz US, 868MHz EU, 433MHz Asia)
- Ensure devices are within range (~1-5km urban, ~5-15km rural)

### Messages not sending
- Check route exists: `!peers` should show destination
- Verify LoRa radio is online (■ icon on display)
- Check TX counter incrementing (display page 1)

### File transfer fails
- Keep files under 1KB for reliable transfer
- Ensure stable connection (no movement during transfer)
- Check free memory: `!info` → watch for memory errors
- Try smaller chunk size in transfer settings

### Display issues
- Blank screen: Check I2C connection (address 0x3C)
- Frozen display: Reset device (RST button)
- Waterfall not updating: Normal if no RF activity

---

**Built with curiosity, vibes, and questionable architecture decisions** 🍄✨
