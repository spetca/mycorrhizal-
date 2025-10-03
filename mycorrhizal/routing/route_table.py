"""
Route Table - Stores discovered paths to destinations

Each route entry contains:
- destination: 16-byte address
- next_hop: 16-byte address of next node (or None if direct)
- interface: PhycoreBase that received the announce
- hop_count: Number of hops to destination
- timestamp: When route was last seen
"""

import time


class RouteEntry:
    """A single route to a destination"""

    def __init__(self, destination, next_hop, interface, hop_count):
        """
        Create a route entry.

        Args:
            destination: 16-byte destination address
            next_hop: 16-byte address of next hop (None if direct)
            interface: PhycoreBase to use for forwarding
            hop_count: Number of hops to destination
        """
        self.destination = destination
        self.next_hop = next_hop
        self.interface = interface
        self.hop_count = hop_count
        self.timestamp = time.time()

    def update(self, next_hop, interface, hop_count):
        """Update route if we found a better path"""
        self.next_hop = next_hop
        self.interface = interface
        self.hop_count = hop_count
        self.timestamp = time.time()

    def refresh(self):
        """Refresh timestamp (route still alive)"""
        self.timestamp = time.time()

    def age(self):
        """Get age of route in seconds"""
        return time.time() - self.timestamp

    def __repr__(self):
        dest_hex = self.destination.hex()[:8]
        next_hex = self.next_hop.hex()[:8] if self.next_hop else "direct"
        return f"Route({dest_hex}... via {next_hex}, hops={self.hop_count}, if={self.interface.name})"


class RouteTable:
    """
    Stores routes to discovered destinations.

    Features:
    - Platform-adaptive size limits
    - LRU eviction when full
    - Route expiry based on age
    """

    def __init__(self, max_routes=1000, route_timeout=1800):
        """
        Create a route table.

        Args:
            max_routes: Maximum number of routes to store
            route_timeout: Route expiry time in seconds (default: 30 minutes)
        """
        self.max_routes = max_routes
        self.route_timeout = route_timeout

        # Map: destination_hex -> RouteEntry
        self.routes = {}

    def add_or_update(self, destination, next_hop, interface, hop_count):
        """
        Add or update a route.

        Only updates if:
        - Route doesn't exist, OR
        - New route has fewer hops

        Args:
            destination: 16-byte destination address
            next_hop: 16-byte next hop address (None if direct)
            interface: PhycoreBase to use
            hop_count: Number of hops

        Returns:
            bool: True if route was added/updated
        """
        dest_hex = destination.hex()

        # Check if route exists
        if dest_hex in self.routes:
            existing = self.routes[dest_hex]

            # Update if fewer hops or same path refreshed
            if hop_count < existing.hop_count:
                existing.update(next_hop, interface, hop_count)
                return True
            elif hop_count == existing.hop_count and next_hop == existing.next_hop:
                existing.refresh()
                return True
            else:
                return False

        # New route - check capacity
        if len(self.routes) >= self.max_routes:
            self._evict_oldest()

        # Add route
        self.routes[dest_hex] = RouteEntry(destination, next_hop, interface, hop_count)
        return True

    def get_route(self, destination):
        """
        Get route to destination.

        Args:
            destination: 16-byte address

        Returns:
            RouteEntry or None
        """
        dest_hex = destination.hex()
        route = self.routes.get(dest_hex)

        # Check if route expired
        if route and route.age() > self.route_timeout:
            del self.routes[dest_hex]
            return None

        return route

    def remove_route(self, destination):
        """Remove a route"""
        dest_hex = destination.hex()
        if dest_hex in self.routes:
            del self.routes[dest_hex]

    def cleanup_expired(self):
        """Remove all expired routes"""
        expired = []
        for dest_hex, route in self.routes.items():
            if route.age() > self.route_timeout:
                expired.append(dest_hex)

        for dest_hex in expired:
            del self.routes[dest_hex]

        return len(expired)

    def _evict_oldest(self):
        """Evict oldest route (LRU)"""
        if not self.routes:
            return

        oldest_dest = None
        oldest_time = float('inf')

        for dest_hex, route in self.routes.items():
            if route.timestamp < oldest_time:
                oldest_time = route.timestamp
                oldest_dest = dest_hex

        if oldest_dest:
            del self.routes[oldest_dest]

    def get_all_routes(self):
        """Get all routes (for debugging/stats)"""
        return list(self.routes.values())

    def size(self):
        """Get number of routes"""
        return len(self.routes)

    def __repr__(self):
        return f"RouteTable(size={self.size()}/{self.max_routes}, timeout={self.route_timeout}s)"
