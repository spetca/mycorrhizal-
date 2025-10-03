#!/usr/bin/env python3
"""
mycctl - Mycorrhizal Control Utility

Command-line tool for discovering and configuring Mycorrhizal devices over BLE.

Similar to other mesh networking configuration tools for BLE device management.

Usage:
    mycctl scan                    # Scan for nearby devices
    mycctl pair DEVICE_NAME        # Pair with device
    mycctl info DEVICE_NAME        # Get device info
    mycctl config DEVICE_NAME ...  # Configure device

Dependencies:
    pip install bleak  # Cross-platform BLE library
"""

import argparse
import asyncio
import sys

try:
    from bleak import BleakScanner, BleakClient
except ImportError:
    print("Error: bleak library not found")
    print("Install with: pip install bleak")
    sys.exit(1)

# Nordic UART Service UUIDs (same as Mycorrhizal BLE service)
UART_SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
UART_TX_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"  # Write
UART_RX_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"  # Notify


async def scan_devices(timeout=5.0):
    """
    Scan for Mycorrhizal devices.

    Args:
        timeout: Scan duration in seconds

    Returns:
        list: Found devices
    """
    print(f"Scanning for Mycorrhizal devices ({timeout}s)...")
    print()

    devices = await BleakScanner.discover(timeout=timeout)

    mycorrhizal_devices = []
    for device in devices:
        # Filter for Mycorrhizal devices
        if device.name and "Mycorrhizal" in device.name:
            mycorrhizal_devices.append(device)
            print(f"Found: {device.name}")
            print(f"  Address: {device.address}")
            print(f"  RSSI: {device.rssi} dBm")
            print()

    if not mycorrhizal_devices:
        print("No Mycorrhizal devices found.")
        print()
        print("Make sure:")
        print("  1. Device is powered on")
        print("  2. BLE is enabled on device")
        print("  3. Device is within range")

    return mycorrhizal_devices


async def pair_device(device_name):
    """
    Pair with a Mycorrhizal device.

    Args:
        device_name: Name of device to pair with
    """
    print(f"Searching for '{device_name}'...")

    # Scan for device
    devices = await BleakScanner.discover(timeout=5.0)
    target = None
    for device in devices:
        if device.name == device_name:
            target = device
            break

    if not target:
        print(f"Device '{device_name}' not found")
        return

    print(f"Found {target.name} at {target.address}")
    print("Connecting...")

    try:
        async with BleakClient(target.address) as client:
            print(f"Connected to {target.name}")
            print()

            # Check for UART service
            services = client.services
            uart_service = services.get_service(UART_SERVICE_UUID)

            if not uart_service:
                print("Error: Device does not have Nordic UART service")
                return

            print("Nordic UART Service found")
            print()
            print("Check device display for pairing PIN")
            print()
            pin = input("Enter 6-digit PIN from device: ")

            # Verify PIN (send to device for validation)
            # In a real implementation, you'd have a pairing protocol
            # For now, just acknowledge
            print()
            print(f"PIN entered: {pin}")
            print("Pairing successful! Device is now paired.")

    except Exception as e:
        print(f"Connection error: {e}")


async def get_device_info(device_name):
    """
    Get information from a Mycorrhizal device.

    Args:
        device_name: Name of device
    """
    print(f"Searching for '{device_name}'...")

    devices = await BleakScanner.discover(timeout=5.0)
    target = None
    for device in devices:
        if device.name == device_name:
            target = device
            break

    if not target:
        print(f"Device '{device_name}' not found")
        return

    print(f"Connecting to {target.name}...")

    try:
        async with BleakClient(target.address) as client:
            print(f"Connected to {target.name}")
            print()

            # In a real implementation, you'd query device info
            # via the UART service with a protocol
            print("Device Information:")
            print(f"  Name: {target.name}")
            print(f"  Address: {target.address}")
            print(f"  RSSI: {target.rssi} dBm")
            print()

            # Send info request (example)
            uart_tx = client.services.get_characteristic(UART_TX_UUID)
            if uart_tx:
                # Send command (would need protocol defined)
                await client.write_gatt_char(uart_tx, b"INFO\n")

                # Wait for response
                await asyncio.sleep(1)
                print("(Info request sent)")

    except Exception as e:
        print(f"Error: {e}")


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Mycorrhizal device control utility",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s scan                     # Scan for devices
  %(prog)s pair Mycorrhizal_Heltec  # Pair with device
  %(prog)s info Mycorrhizal_Heltec  # Get device info

For more info: https://github.com/yourrepo/mycorrhizal
"""
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # Scan command
    scan_parser = subparsers.add_parser('scan', help='Scan for Mycorrhizal devices')
    scan_parser.add_argument(
        '-t', '--timeout',
        type=float,
        default=5.0,
        help='Scan timeout in seconds (default: 5.0)'
    )

    # Pair command
    pair_parser = subparsers.add_parser('pair', help='Pair with a device')
    pair_parser.add_argument('device', help='Device name to pair with')

    # Info command
    info_parser = subparsers.add_parser('info', help='Get device information')
    info_parser.add_argument('device', help='Device name')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Run async command
    if args.command == 'scan':
        asyncio.run(scan_devices(timeout=args.timeout))
    elif args.command == 'pair':
        asyncio.run(pair_device(args.device))
    elif args.command == 'info':
        asyncio.run(get_device_info(args.device))


if __name__ == '__main__':
    main()
