#!/usr/bin/env python3
"""
Test platform detection and resource profiling
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mycorrhizal.platform.detection import get_profile, is_micropython, is_cpython

def main():
    print("=" * 60)
    print("Mycorrhizal Platform Detection Test")
    print("=" * 60)

    print(f"\nPlatform: {'MicroPython' if is_micropython() else 'CPython'}")
    print(f"Python version: {sys.version}")

    profile = get_profile()
    print(f"\n{profile}")

    print(f"\nResource Limits:")
    print(f"  Max routing entries: {profile.max_routing_entries:,}")
    print(f"  Max cache entries: {profile.max_cache_entries:,}")
    print(f"  Max message queue: {profile.max_message_queue}")
    print(f"  Persistence enabled: {profile.enable_persistence}")
    print(f"  Statistics enabled: {profile.enable_statistics}")
    print(f"  Filesystem available: {profile.has_filesystem}")

    print(f"\nNode Capability: {profile.capability.upper()}")

    if profile.capability == 'gateway':
        print("  → Can serve as a network gateway")
        print("  → Large routing tables, persistent storage")
    elif profile.capability == 'edge':
        print("  → Edge device (e.g., Raspberry Pi)")
        print("  → Moderate routing, caching enabled")
    else:
        print("  → MCU mode (minimal resources)")
        print("  → Optimized for constrained devices")

if __name__ == "__main__":
    main()
