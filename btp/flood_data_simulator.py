"""
Flood Data Simulator - Dummy data generator for prototype testing
Simulates flood depth data for Jodhpur area
"""

import random
from typing import Dict, List, Tuple
from datetime import datetime


class FloodDataSimulator:
    """Simulates flood data for testing purposes."""
    
    # Jodhpur approximate bounds
    JODHPUR_BOUNDS = {
        "min_lat": 26.23,
        "max_lat": 26.35,
        "min_lon": 73.00,
        "max_lon": 73.10
    }
    
    # Define flood zones targeting actual hospital locations in Jodhpur
    # These coordinates are chosen to affect real hospitals from OpenStreetMap
    FLOOD_ZONES = [
        # Zone 1: AIIMS Jodhpur area (26.24, 73.00) - HIGH RISK
        {"center": (26.2410, 73.0050), "radius": 0.008, "base_depth": 2.2},
        
        # Zone 2: Near Satellite Hospital area (26.265, 72.973) - MEDIUM RISK
        {"center": (26.2660, 72.9750), "radius": 0.010, "base_depth": 1.8},
        
        # Zone 3: Central Jodhpur hospitals (26.293, 73.018) - MEDIUM RISK
        {"center": (26.2930, 73.0160), "radius": 0.008, "base_depth": 1.5},
        
        # Zone 4: Near Ram Ratan Hospital (26.270, 72.980) - LOW RISK
        {"center": (26.2705, 72.9810), "radius": 0.006, "base_depth": 0.9},
        
        # Zone 5: Amar Nagar Road area - LOW RISK
        {"center": (26.2665, 72.9785), "radius": 0.005, "base_depth": 0.7},
    ]
    
    def __init__(self):
        """Initialize flood simulator with current timestamp."""
        self.last_update = datetime.now()
        # Use fixed seed for consistent demo results
        random.seed(42)
    
    def get_flood_depth(self, lat: float, lon: float) -> float:
        """
        Get flood depth at a specific location.
        
        Args:
            lat: Latitude
            lon: Longitude
            
        Returns:
            Flood depth in meters (0 if no flooding)
        """
        max_depth = 0.0
        
        for zone in self.FLOOD_ZONES:
            center_lat, center_lon = zone["center"]
            radius = zone["radius"]
            base_depth = zone["base_depth"]
            
            # Calculate distance from zone center
            dist = ((lat - center_lat)**2 + (lon - center_lon)**2)**0.5
            
            if dist < radius:
                # Depth decreases linearly with distance from center
                depth = base_depth * (1 - dist/radius)
                max_depth = max(max_depth, depth)
        
        return max(0, round(max_depth, 2))
    
    def is_location_flooded(self, lat: float, lon: float, threshold: float = 0.3) -> bool:
        """
        Check if a location is flooded above threshold.
        
        Args:
            lat: Latitude
            lon: Longitude
            threshold: Minimum depth to consider flooded (meters)
            
        Returns:
            True if flooded above threshold
        """
        depth = self.get_flood_depth(lat, lon)
        return depth >= threshold
    
    def is_road_passable(self, lat: float, lon: float, vehicle_type: str = "car") -> Dict:
        """
        Check if a road is passable for a vehicle type.
        
        Args:
            lat: Latitude
            lon: Longitude
            vehicle_type: Type of vehicle ('car', 'ambulance', 'boat', 'truck')
            
        Returns:
            Dictionary with passability info
        """
        depth = self.get_flood_depth(lat, lon)
        
        # Vehicle depth limits (in meters)
        limits = {
            "car": 0.3,
            "ambulance": 0.5,
            "truck": 0.7,
            "boat": 0.0  # Boats can go anywhere with water
        }
        
        limit = limits.get(vehicle_type.lower(), 0.3)
        passable = depth < limit
        
        return {
            "passable": passable,
            "flood_depth": depth,
            "vehicle_limit": limit,
            "recommendation": "Safe to pass" if passable else f"Water too deep for {vehicle_type}"
        }
    
    def get_flooded_areas(self) -> List[Dict]:
        """
        Get list of currently flooded areas.
        
        Returns:
            List of flooded zone descriptions
        """
        areas = []
        for idx, zone in enumerate(self.FLOOD_ZONES, 1):
            lat, lon = zone["center"]
            depth = zone["base_depth"]
            areas.append({
                "area_id": idx,
                "center_lat": lat,
                "center_lon": lon,
                "radius_km": zone["radius"] * 111,  # Convert degrees to km
                "max_depth_meters": depth,
                "severity": "High" if depth > 2.0 else "Medium" if depth > 1.0 else "Low"
            })
        return areas
    
    def check_route_flooding(self, start_lat: float, start_lon: float, 
                            end_lat: float, end_lon: float, 
                            points: int = 10) -> Dict:
        """
        Check if a route between two points passes through flooded areas.
        
        Args:
            start_lat: Starting latitude
            start_lon: Starting longitude
            end_lat: Ending latitude
            end_lon: Ending longitude
            points: Number of points to check along the route
            
        Returns:
            Route flooding analysis
        """
        flooded_points = []
        max_depth_on_route = 0.0
        
        for i in range(points + 1):
            t = i / points
            lat = start_lat + t * (end_lat - start_lat)
            lon = start_lon + t * (end_lon - start_lon)
            
            depth = self.get_flood_depth(lat, lon)
            if depth > 0.3:  # Consider flooded if > 30cm
                flooded_points.append({
                    "lat": round(lat, 4),
                    "lon": round(lon, 4),
                    "depth": depth
                })
                max_depth_on_route = max(max_depth_on_route, depth)
        
        is_safe = len(flooded_points) == 0
        
        return {
            "route_safe": is_safe,
            "flooded_sections": len(flooded_points),
            "max_depth_on_route": round(max_depth_on_route, 2),
            "flooded_points": flooded_points[:3],  # Return first 3 for brevity
            "recommendation": "Route is clear" if is_safe else "Route has flooded sections - use alternative"
        }
    
    def get_affected_pois(self, pois: List[Dict], threshold: float = 0.5) -> Dict:
        """
        Check which POIs (hospitals, schools, etc.) are affected by flooding.
        
        Args:
            pois: List of POIs with 'lat', 'lon', 'name' keys
            threshold: Depth threshold for being affected
            
        Returns:
            Analysis of affected POIs
        """
        affected = []
        safe = []
        
        for poi in pois:
            lat = float(poi.get('lat', 0))
            lon = float(poi.get('lon', 0))
            name = poi.get('name', 'Unknown')
            
            depth = self.get_flood_depth(lat, lon)
            
            poi_status = {
                "name": name,
                "lat": lat,
                "lon": lon,
                "flood_depth": depth,
                "status": "Affected" if depth >= threshold else "Safe"
            }
            
            if depth >= threshold:
                affected.append(poi_status)
            else:
                safe.append(poi_status)
        
        return {
            "total_pois": len(pois),
            "affected_count": len(affected),
            "safe_count": len(safe),
            "affected_pois": affected,
            "safe_pois": safe
        }


# Global instance for easy access
flood_simulator = FloodDataSimulator()


def get_flood_depth(lat: float, lon: float) -> float:
    """Convenience function to get flood depth."""
    return flood_simulator.get_flood_depth(lat, lon)


def is_location_flooded(lat: float, lon: float) -> bool:
    """Convenience function to check if location is flooded."""
    return flood_simulator.is_location_flooded(lat, lon)


if __name__ == "__main__":
    # Test the simulator
    print("=== Flood Data Simulator Test ===\n")
    
    # Test 1: Check specific locations (matching our flood zones)
    print("1. Checking flood depth at specific locations:")
    test_points = [
        (26.2410, 73.0050, "AIIMS Jodhpur area"),
        (26.2660, 72.9750, "Satellite Hospital area"),
        (26.2930, 73.0160, "Central Jodhpur")
    ]
    
    for lat, lon, desc in test_points:
        depth = flood_simulator.get_flood_depth(lat, lon)
        status = "FLOODED" if depth > 0.3 else "Safe"
        print(f"   {desc}: {depth}m - {status}")
    
    # Test 2: Get all flooded areas
    print("\n2. Currently flooded areas:")
    areas = flood_simulator.get_flooded_areas()
    for area in areas:
        print(f"   Area {area['area_id']}: {area['severity']} severity, {area['max_depth_meters']}m depth")
    
    # Test 3: Check route
    print("\n3. Route analysis:")
    route = flood_simulator.check_route_flooding(26.2410, 73.0050, 26.2930, 73.0160)
    print(f"   Route safe: {route['route_safe']}")
    print(f"   Max depth: {route['max_depth_on_route']}m")
    print(f"   Recommendation: {route['recommendation']}")
    
    # Test 4: Check vehicle passability at flooded location
    print("\n4. Vehicle passability at AIIMS area (flooded):")
    for vehicle in ['car', 'ambulance', 'truck']:
        result = flood_simulator.is_road_passable(26.2410, 73.0050, vehicle)
        print(f"   {vehicle.capitalize()}: {result['recommendation']}")
    
    print("\n=== Test Complete ===")
