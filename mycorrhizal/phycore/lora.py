"""
Generic LoRa Phycore

Abstract interface for LoRa devices. Uses a pattern where the
interface is transport-agnostic and device-specific implementations handle
the hardware details.

Device-specific drivers (SX1262, SX1276, etc.) live in mycorrhizal/devices/
"""

from .base import PhycoreBase, InterfaceMode


class LoRaPhycore(PhycoreBase):
    """
    Generic LoRa phycore interface.

    This is an abstract interface that provides a consistent API for LoRa
    communication regardless of the underlying radio hardware (SX1262, SX1276, etc.)

    Device-specific implementations should:
    1. Subclass or be wrapped by this interface
    2. Implement the device-specific radio operations
    3. Call _on_receive(data) when packets arrive

    Example:
        from mycorrhizal.phycore.lora import LoRaPhycore
        from mycorrhizal.devices.sx1262 import SX1262Radio

        # Create device-specific radio
        radio = SX1262Radio(
            frequency=915_000_000,
            spreading_factor=9,
            bandwidth=125_000
        )

        # Wrap in generic LoRa interface
        lora = LoRaPhycore(name="lora0", device=radio)
        lora.start()
    """

    def __init__(self, name="lora0", device=None, mode=InterfaceMode.FULL,
                 announce_budget_percent=1.0):
        """
        Initialize generic LoRa phycore.

        Args:
            name: Interface name
            device: Device-specific radio implementation (e.g., SX1262Radio)
            mode: InterfaceMode (FULL, GATEWAY, BOUNDARY, etc.)
            announce_budget_percent: Percentage of bandwidth for announces (default 1%)
        """
        if device is None:
            raise ValueError("LoRa phycore requires a device implementation")

        # Get bandwidth from device
        bandwidth_bps = device.get_bitrate()

        super().__init__(name, bandwidth_bps=bandwidth_bps, mode=mode,
                         announce_budget_percent=announce_budget_percent)

        self.device = device

        # Set up device callback to route received packets to phycore
        self.device.set_receive_callback(self._on_receive)

    def start(self):
        """Start LoRa device"""
        if self.online:
            return True

        success = self.device.start()
        if success:
            self.online = True
            print(f"  ✓ {self.name}: {self.device.get_config_string()}")
            print(f"    Bitrate: {self.bandwidth_bps:.0f} bps, "
                  f"Announce budget: {self.announce_budget_bps:.0f} bps")
        else:
            print(f"  ✗ {self.name}: Failed to start device")
            self.online = False

        return success

    def stop(self):
        """Stop LoRa device"""
        if not self.online:
            return

        self.device.stop()
        self.online = False

    def send(self, data):
        """
        Send data via LoRa.

        Args:
            data: bytes to transmit

        Returns:
            bool: True if sent successfully
        """
        if not self.online:
            return False

        success = self.device.send(data)

        if success:
            self.tx_count += 1
            self.tx_bytes += len(data)

        return success

    def get_config(self):
        """Get current device configuration"""
        return self.device.get_config()

    def set_config(self, **kwargs):
        """
        Update device configuration.

        Args:
            **kwargs: Device-specific configuration parameters
                     (frequency, spreading_factor, bandwidth, tx_power, etc.)

        Returns:
            bool: True if configuration updated successfully
        """
        return self.device.set_config(**kwargs)

    def get_stats(self):
        """Get interface statistics including device-specific stats"""
        stats = super().get_stats()

        # Add device-specific stats if available
        if hasattr(self.device, 'get_stats'):
            stats['device'] = self.device.get_stats()

        return stats

    def __repr__(self):
        return f"LoRaPhycore(name='{self.name}', device={self.device.__class__.__name__}, online={self.online})"


class LoRaDevice:
    """
    Abstract base class for LoRa device implementations.

    Device-specific drivers (SX1262, SX1276, RNode, etc.) should implement this interface.
    """

    def __init__(self):
        """Initialize device"""
        self.receive_callback = None

    def start(self):
        """
        Initialize and start the radio.

        Returns:
            bool: True if started successfully
        """
        raise NotImplementedError("Device must implement start()")

    def stop(self):
        """Stop the radio"""
        raise NotImplementedError("Device must implement stop()")

    def send(self, data):
        """
        Transmit data.

        Args:
            data: bytes to send

        Returns:
            bool: True if transmitted successfully
        """
        raise NotImplementedError("Device must implement send()")

    def set_receive_callback(self, callback):
        """
        Set callback for received packets.

        Args:
            callback: function(data: bytes) called when packet received
        """
        self.receive_callback = callback

    def get_bitrate(self):
        """
        Get current LoRa bitrate in bps.

        Returns:
            int: bitrate in bits per second
        """
        raise NotImplementedError("Device must implement get_bitrate()")

    def get_config(self):
        """
        Get current configuration.

        Returns:
            dict: Configuration parameters
        """
        raise NotImplementedError("Device must implement get_config()")

    def set_config(self, **kwargs):
        """
        Update configuration.

        Args:
            **kwargs: Device-specific parameters

        Returns:
            bool: True if updated successfully
        """
        raise NotImplementedError("Device must implement set_config()")

    def get_config_string(self):
        """
        Get human-readable configuration string.

        Returns:
            str: Configuration summary (e.g., "915.0 MHz, SF9, BW125")
        """
        raise NotImplementedError("Device must implement get_config_string()")
