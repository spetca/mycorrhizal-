"""
UDP Phycore - UDP interface for local/network communication

Modes:
- Point-to-point: Send to specific host:port, listen on own port
- Broadcast: Send to multiple destinations (for local testing)
- Multicast: Join multicast group (for LAN mesh)
"""

import socket
import threading
from .base import PhycoreBase, InterfaceMode


class UDPPhycore(PhycoreBase):
    """
    UDP phycore - flexible UDP transport.

    Can operate in different modes:
    - Single destination: listen_port + (host, port) for point-to-point
    - Multiple destinations: listen_port + [(host1, port1), ...] for broadcast
    - Multicast: listen_port + multicast_group for LAN mesh
    """

    def __init__(self, name="udp0", listen_port=4242, destinations=None,
                 multicast_group=None, host="127.0.0.1", mode=InterfaceMode.FULL,
                 announce_budget_percent=2.0, bandwidth_bps=None):
        """
        Initialize UDP phycore.

        Args:
            name: Interface name
            listen_port: Port to listen on
            destinations: Single port, list of ports, or list of (host, port) tuples
            multicast_group: Multicast group address (if using multicast)
            host: Default host for destinations (default localhost)
            mode: InterfaceMode (FULL, GATEWAY, BOUNDARY, etc.)
            announce_budget_percent: Percentage of bandwidth for announces (default 2%)
            bandwidth_bps: Override bandwidth (default 100 Mbps for Ethernet)
        """
        # UDP is typically high bandwidth (assume 100 Mbps Ethernet unless overridden)
        if bandwidth_bps is None:
            bandwidth_bps = 100_000_000

        super().__init__(name, bandwidth_bps=bandwidth_bps, mode=mode,
                         announce_budget_percent=announce_budget_percent)

        self.listen_port = listen_port
        self.multicast_group = multicast_group
        self.host = host

        # Parse destinations into list of (host, port) tuples
        self.destinations = self._parse_destinations(destinations, host)

        self.sock = None
        self.listen_thread = None
        self.running = False

    def _parse_destinations(self, destinations, default_host):
        """Convert various destination formats to list of (host, port) tuples"""
        if destinations is None:
            return []

        if isinstance(destinations, int):
            # Single port
            return [(default_host, destinations)]

        if isinstance(destinations, list):
            result = []
            for dest in destinations:
                if isinstance(dest, int):
                    # Port number
                    result.append((default_host, dest))
                elif isinstance(dest, tuple) and len(dest) == 2:
                    # (host, port) tuple
                    result.append(dest)
            return result

        return []

    def start(self):
        """Start UDP interface"""
        if self.online:
            return True

        try:
            # Create UDP socket
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            # On Mac/BSD, need SO_REUSEPORT for multiple processes on same port
            try:
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except AttributeError:
                pass  # Not available on all platforms

            # Bind to listen port
            self.sock.bind(('', self.listen_port))

            # Join multicast group if specified
            if self.multicast_group:
                import struct
                mreq = struct.pack('4sl', socket.inet_aton(self.multicast_group), socket.INADDR_ANY)
                self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
                self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)

            # Start receive thread
            self.running = True
            self.listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
            self.listen_thread.start()

            self.online = True
            return True

        except Exception as e:
            print(f"Failed to start UDP phycore: {e}")
            self.online = False
            return False

    def stop(self):
        """Stop UDP interface"""
        if not self.online:
            return

        self.running = False

        if self.sock:
            self.sock.close()
            self.sock = None

        if self.listen_thread:
            self.listen_thread.join(timeout=1.0)
            self.listen_thread = None

        self.online = False

    def send(self, data):
        """
        Send data via UDP.

        If multicast: send to multicast group
        If destinations: send to all configured destinations
        Otherwise: no-op (receive-only mode)

        Args:
            data: bytes to send

        Returns:
            bool: True if at least one send succeeded
        """
        if not self.online or not self.sock:
            return False

        success_count = 0

        try:
            if self.multicast_group:
                # Send to multicast group
                self.sock.sendto(data, (self.multicast_group, self.listen_port))
                success_count += 1
            elif self.destinations:
                # Send to all configured destinations
                for host, port in self.destinations:
                    try:
                        self.sock.sendto(data, (host, port))
                        success_count += 1
                    except Exception as e:
                        print(f"UDP send error to {host}:{port}: {e}")

            if success_count > 0:
                self.tx_count += 1
                self.tx_bytes += len(data)
                return True

        except Exception as e:
            print(f"UDP send error: {e}")

        return False

    def _listen_loop(self):
        """Background thread that listens for incoming UDP packets"""
        while self.running:
            try:
                # Receive with timeout so we can check self.running
                self.sock.settimeout(0.5)
                data, addr = self.sock.recvfrom(65535)

                # Call the receive callback
                if data:
                    self._on_receive(data)

            except socket.timeout:
                # Normal timeout, just loop again
                continue
            except Exception as e:
                if self.running:  # Only log if we're supposed to be running
                    print(f"UDP receive error: {e}")
                break

    def __repr__(self):
        mode = "multicast" if self.multicast_group else f"broadcast({len(self.destinations)} dest)" if self.destinations else "receive-only"
        return f"UDPPhycore(name='{self.name}', listen={self.listen_port}, mode={mode}, online={self.online})"
