#!/usr/bin/env python3
"""
Mycorrhizal Device Flasher

One-stop tool for flashing MicroPython and Mycorrhizal code to devices.

Supports:
- Heltec WiFi LoRa 32 V3 (ESP32-S3)
- Generic ESP32-S3 + SX1262
- More devices coming soon

Usage:
    python flash_device.py --device heltec_v3
    python flash_device.py --device heltec_v3 --port /dev/ttyUSB0
    python flash_device.py --device heltec_v3 --skip-firmware
"""

import argparse
import sys
import os
import time
import subprocess
import tempfile
from pathlib import Path

try:
    import serial.tools.list_ports
except ImportError:
    print("Error: pyserial not installed")
    print("Install with: pip install pyserial")
    sys.exit(1)


# Device configurations
DEVICES = {
    'heltec_v3': {
        'name': 'Heltec WiFi LoRa 32 V3',
        'chip': 'esp32s3',
        'flash_size': '8MB',
        'firmware_url': 'https://micropython.org/resources/firmware/ESP32_GENERIC_S3-20241025-v1.24.0.bin',
        'firmware_file': 'ESP32_GENERIC_S3-20241025-v1.24.0.bin',
        'baud_rate': 460800,
        'reset_required': True,
        'required_packages': ['ssd1306'],  # MicroPython packages
    },
    'esp32s3_sx1262': {
        'name': 'Generic ESP32-S3 + SX1262',
        'chip': 'esp32s3',
        'flash_size': '8MB',
        'firmware_url': 'https://micropython.org/resources/firmware/ESP32_GENERIC_S3-20241025-v1.24.0.bin',
        'firmware_file': 'ESP32_GENERIC_S3-20241025-v1.24.0.bin',
        'baud_rate': 460800,
        'reset_required': True,
        'required_packages': [],
    },
}


def print_header(text):
    """Print formatted header"""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)


def print_step(number, text):
    """Print formatted step"""
    print(f"\n[{number}] {text}")
    print("-" * 70)


def list_serial_ports():
    """List available serial ports"""
    ports = serial.tools.list_ports.comports()
    if not ports:
        print("No serial ports found!")
        return None

    print("\nAvailable serial ports:")
    for i, port in enumerate(ports):
        print(f"  [{i}] {port.device}")
        print(f"      Description: {port.description}")
        print(f"      Hardware ID: {port.hwid}")

    return ports


def select_port(ports=None):
    """Interactive port selection"""
    if ports is None:
        ports = list_serial_ports()

    if not ports:
        return None

    if len(ports) == 1:
        port = ports[0].device
        print(f"\nAuto-selected only available port: {port}")
        return port

    while True:
        try:
            choice = input(f"\nSelect port [0-{len(ports)-1}] or enter path: ").strip()

            # Check if it's a number
            if choice.isdigit():
                idx = int(choice)
                if 0 <= idx < len(ports):
                    return ports[idx].device
                else:
                    print(f"Invalid choice. Please enter 0-{len(ports)-1}")
            else:
                # Assume it's a path
                if os.path.exists(choice):
                    return choice
                else:
                    print(f"Port {choice} does not exist")
        except (ValueError, KeyboardInterrupt):
            return None


def check_tool(tool_name, install_hint):
    """Check if a command-line tool is installed"""
    import sys

    # Different tools use different version commands
    version_cmds = ['--version', 'version', '-v']

    # Try direct command
    for ver_cmd in version_cmds:
        try:
            result = subprocess.run([tool_name, ver_cmd],
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE)
            if result.returncode == 0 or (result.returncode == 2 and b'esptool' in result.stderr):
                return True
        except FileNotFoundError:
            pass

    # Try with full venv path
    venv_bin = Path(sys.executable).parent / tool_name
    if venv_bin.exists():
        for ver_cmd in version_cmds:
            try:
                result = subprocess.run([str(venv_bin), ver_cmd],
                                      stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE)
                if result.returncode == 0 or (result.returncode == 2 and b'esptool' in result.stderr):
                    return True
            except FileNotFoundError:
                pass

    print(f"\nError: {tool_name} not found!")
    print(f"Install with: {install_hint}")
    return False


def get_tool_cmd(tool_name):
    """Get the correct command to run a tool"""
    # Try direct command first
    try:
        result = subprocess.run([tool_name, '--version'],
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,
                              shell=False)
        if result.returncode == 0:
            return tool_name
    except FileNotFoundError:
        pass

    # Try with full path (in case venv bin not in PATH)
    import sys
    venv_bin = Path(sys.executable).parent / tool_name
    if venv_bin.exists():
        try:
            result = subprocess.run([str(venv_bin), '--version'],
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,
                                  shell=False)
            if result.returncode == 0:
                return str(venv_bin)
        except FileNotFoundError:
            pass

    # Try python -m variant
    module_name = tool_name.replace('.py', '')
    return f"python -m {module_name}"


def download_firmware(device_config, cache_dir):
    """Download MicroPython firmware if not cached"""
    firmware_path = cache_dir / device_config['firmware_file']

    if firmware_path.exists():
        print(f"Using cached firmware: {firmware_path}")
        return firmware_path

    print(f"Downloading MicroPython firmware...")
    print(f"  URL: {device_config['firmware_url']}")

    try:
        import urllib.request
        urllib.request.urlretrieve(device_config['firmware_url'], firmware_path)
        print(f"  Downloaded to: {firmware_path}")
        return firmware_path
    except Exception as e:
        print(f"Error downloading firmware: {e}")
        return None


def flash_firmware(port, device_config, firmware_path, erase_first=True):
    """Flash MicroPython firmware to device"""
    chip = device_config['chip']
    baud = device_config['baud_rate']
    esptool = get_tool_cmd('esptool.py')

    if erase_first:
        print("\nErasing flash...")
        cmd = f"{esptool} --chip {chip} --port {port} erase_flash"
        print(f"  $ {cmd}")
        result = subprocess.run(cmd, shell=True)
        if result.returncode != 0:
            print("Error erasing flash!")
            return False

        print("\nWaiting for device to reset...")
        time.sleep(2)

    print("\nFlashing MicroPython firmware...")
    cmd = f"{esptool} --chip {chip} --port {port} --baud {baud} write_flash -z 0x0 {firmware_path}"
    print(f"  $ {cmd}")
    result = subprocess.run(cmd, shell=True)

    if result.returncode != 0:
        print("Error flashing firmware!")
        return False

    print("\nFirmware flashed successfully!")
    print("Waiting for device to boot...")
    time.sleep(3)

    return True


def upload_mycorrhizal(port):
    """Upload Mycorrhizal package to device"""
    # Get mycorrhizal package path
    script_dir = Path(__file__).parent.parent
    mycorrhizal_dir = script_dir / "mycorrhizal"

    if not mycorrhizal_dir.exists():
        print(f"Error: Mycorrhizal package not found at {mycorrhizal_dir}")
        return False

    print("\nUploading Mycorrhizal package...")
    cmd = f"mpremote connect {port} cp -r {mycorrhizal_dir} :"
    print(f"  $ {cmd}")
    result = subprocess.run(cmd, shell=True)

    if result.returncode != 0:
        print("Error uploading Mycorrhizal package!")
        return False

    print("Mycorrhizal package uploaded successfully!")
    return True


def install_packages(port, packages):
    """Install required MicroPython packages"""
    if not packages:
        return True

    print("\nInstalling required MicroPython packages...")
    for package in packages:
        print(f"  Installing {package}...")
        cmd = f"mpremote connect {port} mip install {package}"
        result = subprocess.run(cmd, shell=True)
        if result.returncode != 0:
            print(f"Warning: Failed to install {package}")
            # Continue anyway - some packages might not be critical

    return True


def upload_example(port, example_name):
    """Upload firmware file as main.py"""
    script_dir = Path(__file__).parent.parent

    # Try firmware folder first, then examples folder for backward compatibility
    firmware_path = script_dir / "firmware" / example_name
    if not firmware_path.exists():
        firmware_path = script_dir / "examples" / example_name

    if not firmware_path.exists():
        print(f"Error: Firmware {example_name} not found at {firmware_path}")
        return False

    print(f"\nUploading {example_name} as main.py...")
    cmd = f"mpremote connect {port} cp {firmware_path} :main.py"
    print(f"  $ {cmd}")
    result = subprocess.run(cmd, shell=True)

    if result.returncode != 0:
        print("Error uploading firmware!")
        return False

    print(f"Firmware uploaded successfully!")
    print("Device will run this on boot.")
    return True


def verify_device(port):
    """Verify MicroPython is running"""
    print("\nVerifying MicroPython installation...")

    # Try to get device info
    cmd = f"mpremote connect {port} eval 'import sys; print(sys.implementation)'"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    if result.returncode != 0:
        print("Warning: Could not verify MicroPython installation")
        return False

    print("MicroPython is running!")
    print(f"  {result.stdout.strip()}")
    return True


def main():
    print_header("Mycorrhizal Device Flasher")

    # Parse arguments
    parser = argparse.ArgumentParser(
        description="Flash MicroPython and Mycorrhizal to devices",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --device heltec_v3
  %(prog)s --device heltec_v3 --port /dev/ttyUSB0 --skip-firmware
  %(prog)s --device heltec_v3 --example mycorrhizal_firmware.py
        """
    )

    parser.add_argument('--device', choices=DEVICES.keys(), required=True,
                       help='Device type to flash')
    parser.add_argument('--port', help='Serial port (auto-detect if not specified)')
    parser.add_argument('--skip-firmware', action='store_true',
                       help='Skip firmware flashing (only upload code)')
    parser.add_argument('--skip-erase', action='store_true',
                       help='Skip erasing flash before firmware flash')
    parser.add_argument('--example', default='mycorrhizal_firmware.py',
                       help='Firmware file to upload as main.py (default: mycorrhizal_firmware.py)')
    parser.add_argument('--no-example', action='store_true',
                       help='Do not upload example file')

    args = parser.parse_args()

    device_config = DEVICES[args.device]

    print(f"\nDevice: {device_config['name']}")
    print(f"Chip: {device_config['chip']}")
    print(f"Flash size: {device_config['flash_size']}")

    # Check required tools
    print_step(1, "Checking required tools")

    if not args.skip_firmware:
        if not check_tool('esptool.py', 'pip install esptool'):
            return 1

    if not check_tool('mpremote', 'pip install mpremote'):
        return 1

    print("All required tools are installed!")

    # Select port
    print_step(2, "Selecting serial port")

    if args.port:
        port = args.port
        print(f"Using specified port: {port}")
    else:
        port = select_port()

    if not port:
        print("No port selected. Exiting.")
        return 1

    # Flash firmware (if not skipped)
    if not args.skip_firmware:
        print_step(3, "Downloading and flashing MicroPython firmware")

        # Create cache directory
        cache_dir = Path.home() / '.mycorrhizal' / 'firmware'
        cache_dir.mkdir(parents=True, exist_ok=True)

        firmware_path = download_firmware(device_config, cache_dir)
        if not firmware_path:
            return 1

        if not flash_firmware(port, device_config, firmware_path,
                            erase_first=not args.skip_erase):
            return 1

        # Verify installation
        if not verify_device(port):
            print("Warning: Could not verify installation, but continuing...")
    else:
        print_step(3, "Skipping firmware flash")

    # Install packages
    print_step(4, "Installing required packages")
    install_packages(port, device_config['required_packages'])

    # Upload Mycorrhizal
    print_step(5, "Uploading Mycorrhizal package")
    if not upload_mycorrhizal(port):
        return 1

    # Upload example
    if not args.no_example:
        print_step(6, "Uploading example")
        if not upload_example(port, args.example):
            print("Warning: Failed to upload example, but continuing...")
    else:
        print_step(6, "Skipping example upload")

    # Reset device
    print_step(7, "Resetting device")
    print("Sending reset command...")
    cmd = f"mpremote connect {port} reset"
    result = subprocess.run(cmd, shell=True)
    if result.returncode == 0:
        print("✓ Device reset successfully!")
    else:
        print("⚠ Reset command failed (device may need manual reset)")

    # Done!
    print_header("Flashing Complete!")
    print(f"""
Device is ready to use!

To monitor device:
  mpremote connect {port}

To run REPL:
  mpremote connect {port} repl

To reset device:
  mpremote connect {port} reset

The device will auto-run main.py on boot.
""")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Exiting.")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
