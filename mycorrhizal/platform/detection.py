"""
Platform Detection and Resource Profiling

Detects the runtime environment (MicroPython vs CPython) and measures
available resources to determine node capabilities.

Node Tiers:
- MCU: ESP32, Nordic chips (50-200 routing entries, minimal features)
- Edge: Raspberry Pi (1,000-10,000 entries, moderate features)
- Gateway: Servers (100,000+ entries, persistent storage, full features)
"""

import sys
import gc

# Platform detection
IS_MICROPYTHON = sys.implementation.name == 'micropython'
IS_CPYTHON = sys.implementation.name == 'cpython'

class NodeCapability:
    """Node capability tiers based on available resources"""
    MCU = 'mcu'           # <1MB RAM, minimal features
    EDGE = 'edge'         # 1MB-500MB RAM, moderate features
    GATEWAY = 'gateway'   # >500MB RAM, full features

class ResourceProfile:
    """
    Measures and profiles system resources to determine node capabilities.
    """

    def __init__(self):
        self.platform = 'micropython' if IS_MICROPYTHON else 'cpython'
        self.total_ram = self._measure_ram()
        self.available_ram = self._measure_available_ram()
        self.has_filesystem = self._check_filesystem()
        self.capability = self._determine_capability()

        # Capability-based limits
        self._set_limits()

    def _measure_ram(self):
        """Measure total RAM in bytes"""
        if IS_MICROPYTHON:
            try:
                # ESP32 MicroPython doesn't expose total RAM directly
                # Use a reasonable estimate based on platform
                return 520 * 1024  # ESP32 typical: 520KB
            except:
                return 256 * 1024  # Conservative default
        else:
            # CPython - try to get system RAM
            try:
                import psutil
                return psutil.virtual_memory().total
            except ImportError:
                # Fallback: assume it's a decent machine
                return 4 * 1024 * 1024 * 1024  # 4GB default

    def _measure_available_ram(self):
        """Measure currently available RAM"""
        if IS_MICROPYTHON:
            gc.collect()
            return gc.mem_free()
        else:
            try:
                import psutil
                return psutil.virtual_memory().available
            except ImportError:
                # Can't measure, assume 50% available
                return self.total_ram // 2

    def _check_filesystem(self):
        """Check if persistent filesystem is available"""
        try:
            import os
            # Try to check if we can write
            return hasattr(os, 'listdir')
        except:
            return False

    def _determine_capability(self):
        """Determine node capability tier based on resources"""
        total_mb = self.total_ram / (1024 * 1024)

        if total_mb < 1:
            return NodeCapability.MCU
        elif total_mb < 500:
            return NodeCapability.EDGE
        else:
            return NodeCapability.GATEWAY

    def _set_limits(self):
        """Set resource limits based on capability tier"""
        if self.capability == NodeCapability.MCU:
            self.max_routing_entries = 100
            self.max_cache_entries = 50
            self.max_message_queue = 10
            self.enable_persistence = False
            self.enable_statistics = False
        elif self.capability == NodeCapability.EDGE:
            self.max_routing_entries = 5000
            self.max_cache_entries = 1000
            self.max_message_queue = 100
            self.enable_persistence = True
            self.enable_statistics = True
        else:  # GATEWAY
            self.max_routing_entries = 100000
            self.max_cache_entries = 50000
            self.max_message_queue = 1000
            self.enable_persistence = True
            self.enable_statistics = True

    def __repr__(self):
        return (f"ResourceProfile(platform={self.platform}, "
                f"capability={self.capability}, "
                f"total_ram={self.total_ram//1024}KB, "
                f"available_ram={self.available_ram//1024}KB, "
                f"max_routes={self.max_routing_entries})")


# Global resource profile - initialized once
_profile = None

def get_profile():
    """Get the global resource profile (singleton)"""
    global _profile
    if _profile is None:
        _profile = ResourceProfile()
    return _profile

def is_micropython():
    """Check if running on MicroPython"""
    return IS_MICROPYTHON

def is_cpython():
    """Check if running on CPython"""
    return IS_CPYTHON
