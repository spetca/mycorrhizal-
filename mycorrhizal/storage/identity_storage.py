"""
Identity Storage - Persist node identity to storage

Saves identity keys to persistent storage so the node keeps the same address across reboots.
Platform-agnostic implementation works on MicroPython (flash) and CPython (filesystem).
"""

import os
import sys

# Detect platform
try:
    if sys.implementation.name == 'micropython':
        MICROPYTHON = True
        # MicroPython: store in root filesystem
        STORAGE_DIR = '/'
        print("[IdentityStorage] Platform: MicroPython")
    else:
        MICROPYTHON = False
        # CPython: use XDG_DATA_HOME or ~/.local/share
        from pathlib import Path
        STORAGE_DIR = str(Path.home() / '.local' / 'share' / 'mycorrhizal')
        os.makedirs(STORAGE_DIR, exist_ok=True)
        print(f"[IdentityStorage] Platform: CPython, storage: {STORAGE_DIR}")
except Exception as e:
    print(f"[IdentityStorage] Error detecting platform: {e}")
    MICROPYTHON = False
    STORAGE_DIR = '.'


class IdentityStorage:
    """Manage identity persistence to storage"""

    @staticmethod
    def _get_identity_path():
        """Get platform-specific identity file path"""
        if MICROPYTHON:
            return '/identity.dat'
        else:
            import os.path
            return os.path.join(STORAGE_DIR, 'identity.dat')

    @staticmethod
    def save(identity):
        """
        Save identity to persistent storage.

        Args:
            identity: Identity instance to save

        Returns:
            bool: True if saved successfully
        """
        try:
            path = IdentityStorage._get_identity_path()
            print(f"[IdentityStorage] Saving identity to: {path}")
            data = identity.to_bytes()
            print(f"[IdentityStorage] Identity data size: {len(data)} bytes")

            with open(path, 'wb') as f:
                f.write(data)

            # Verify write
            if MICROPYTHON:
                import os
                if 'identity.dat' in os.listdir('/'):
                    print(f"[IdentityStorage] ✓ Identity saved successfully to {path}")
                    return True
                else:
                    print(f"[IdentityStorage] ✗ File not found after write!")
                    return False
            else:
                import os.path
                if os.path.exists(path):
                    print(f"[IdentityStorage] ✓ Identity saved successfully to {path}")
                    return True
                else:
                    print(f"[IdentityStorage] ✗ File not found after write!")
                    return False
        except Exception as e:
            print(f"[IdentityStorage] ✗ Failed to save identity: {e}")
            import sys
            sys.print_exception(e)
            return False

    @staticmethod
    def load():
        """
        Load identity from persistent storage.

        Returns:
            Identity: Loaded identity, or None if not found
        """
        from ..crypto.identity import Identity

        try:
            path = IdentityStorage._get_identity_path()
            print(f"[IdentityStorage] Loading identity from: {path}")

            # Check if file exists
            if not IdentityStorage.exists():
                print(f"[IdentityStorage] No saved identity found")
                return None

            # Read identity data
            with open(path, 'rb') as f:
                data = f.read()

            print(f"[IdentityStorage] Read {len(data)} bytes")

            # Deserialize
            identity = Identity.from_bytes(data)
            print(f"[IdentityStorage] ✓ Identity loaded successfully")
            print(f"[IdentityStorage]   Address: {identity.address_hex()}")
            return identity

        except Exception as e:
            print(f"[IdentityStorage] ✗ Failed to load identity: {e}")
            import sys
            sys.print_exception(e)
            return None

    @staticmethod
    def exists():
        """
        Check if stored identity exists.

        Returns:
            bool: True if identity file exists
        """
        try:
            path = IdentityStorage._get_identity_path()
            if MICROPYTHON:
                # MicroPython: check if file in directory listing
                import os
                dir_path = '/' if path.startswith('/') else '.'
                filename = path.split('/')[-1]
                return filename in os.listdir(dir_path)
            else:
                # CPython: use os.path.exists
                import os.path
                return os.path.exists(path)
        except:
            return False

    @staticmethod
    def delete():
        """
        Delete stored identity (resets node to new identity on next boot).

        Returns:
            bool: True if deleted successfully
        """
        try:
            path = IdentityStorage._get_identity_path()
            if IdentityStorage.exists():
                os.remove(path)
                print(f"Identity deleted from {path}")
                return True
            return False
        except Exception as e:
            print(f"Failed to delete identity: {e}")
            return False
