import os
import json
import re
import time
import math
import heapq
import requests
import geopandas as gpd
from typing import List, Dict, Any
from typing import Any, Optional, TypedDict, Annotated
from itertools import groupby
from concurrent.futures import ThreadPoolExecutor, as_completed
from langchain_groq import ChatGroq
from shapely.geometry import Point


from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.prompts import PromptTemplate
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END, add_messages

from dotenv import load_dotenv

from shortest_path import get_shortest_path, visualize_routes, vechile_config, road_graph_cache

load_dotenv()

# ============================================================================
# SHAPEFILE CONFIG  — single source of truth for flood data
# ============================================================================

SHAPEFILE_PATH = r"E:\EMSR838_products\EMSR838_AOI01_DEL_PRODUCT_v1\EMSR838_AOI01_DEL_PRODUCT_floodDepthA_v1.shp"
OSM_PLACE      = "Gujrat, Punjab, Pakistan"

# Lazy-loaded once so we don't re-read the shapefile on every tool call
_flood_gdf: Optional[gpd.GeoDataFrame] = None

def _get_flood_gdf() -> gpd.GeoDataFrame:
    """Load and cache the flood shapefile in WGS-84 (EPSG:4326)."""
    global _flood_gdf
    if _flood_gdf is None:
        gdf = gpd.read_file(SHAPEFILE_PATH)
        if gdf.crs is None:
            gdf = gdf.set_crs("EPSG:4326")
        else:
            gdf = gdf.to_crs("EPSG:4326")
        _flood_gdf = gdf
    return _flood_gdf


def _flood_depth_at_point(lat: float, lon: float) -> float:
    """
    Return flood depth (metres) at a point from the real shapefile.
    Uses 'depth' column if present; otherwise returns 1.0 for any intersecting polygon.
    Returns 0.0 if the point is not in any flood polygon.
    """
    gdf   = _get_flood_gdf()
    point = Point(lon, lat)
    hits  = gdf[gdf.geometry.intersects(point)]

    if hits.empty:
        return 0.0

    depth_col = next(
        (c for c in hits.columns if "depth" in c.lower()),
        None
    )
    if depth_col:
        return float(hits[depth_col].max())
    return 1.0


def _route_points(lat1, lon1, lat2, lon2, steps: int = 20):
    """Return `steps` interpolated (lat, lon) pairs along a straight line."""
    lats = [lat1 + (lat2 - lat1) * i / steps for i in range(steps + 1)]
    lons = [lon1 + (lon2 - lon1) * i / steps for i in range(steps + 1)]
    return list(zip(lats, lons))


# ============================================================================
# ROUTE CACHE  — passes complex objects between calculate_route → visualize_route
# ============================================================================

_route_cache: dict = {}


# ============================================================================
# TOOLS
# ============================================================================

@tool
def get_coordinates_from_location(
    location_name: str,
    city: str    = "Gujrat",
    state: str   = "Punjab",
    country: str = "Pakistan"
) -> str:
    """
    Convert a location name (e.g. 'DHQ Hospital', 'Railway Station') to GPS coordinates.
    ALWAYS call this before any tool that needs lat/lon when the user gave a place name.

    Args:
        location_name: Name of the location
        city:    City   (default: Gujrat)
        state:   State  (default: Punjab)
        country: Country (default: Pakistan)

    Returns:
        Coordinates and address information.
    """
    url    = "https://nominatim.openstreetmap.org/search"
    query  = f"{location_name}, {city}, {state}, {country}"
    params = {"q": query, "format": "json", "addressdetails": 1, "limit": 3}
    headers = {"User-Agent": "FloodHelpAgent-Gujrat-2025/1.0"}

    try:
        time.sleep(1)
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        if resp.status_code != 200:
            return f"Error: API returned status {resp.status_code}"

        data = resp.json()
        if not data:
            return f"Location '{location_name}' not found in {city}. Try a different name or provide coordinates directly."

        lines = [f"Found {len(data)} match(es) for '{location_name}' in {city}:\n"]
        for idx, place in enumerate(data, 1):
            lat = float(place.get("lat", 0))
            lon = float(place.get("lon", 0))
            lines += [
                f"{idx}. {place.get('display_name', 'Unknown')}",
                f"   Type: {place.get('type', 'location')}",
                f"   Coordinates: Latitude {lat}, Longitude {lon}",
                f"   Use these coordinates: ({lat}, {lon})",
                "",
            ]
        lines.append("Tip: Use the coordinates above with other tools.")
        return "\n".join(lines)

    except Exception as e:
        return f"Error finding location coordinates: {e}"


@tool
def search_amenity(
    amenity: str,
    city: str    = "Gujrat",
    state: str   = "Punjab",
    country: str = "Pakistan",
    limit: int   = 10
) -> str:
    """
    Find amenities (hospitals, schools, shelters, pharmacies, etc.) in a city.

    Args:
        amenity: Type of amenity (e.g. 'hospital', 'school', 'pharmacy', 'shelter')
        city:    City   (default: Gujrat)
        state:   State  (default: Punjab)
        country: Country (default: Pakistan)
        limit:   Max results (default: 10)
    """
    url    = "https://nominatim.openstreetmap.org/search"
    params = {
        "q":             f"{amenity} in {city}, {state}, {country}",
        "format":        "json",
        "addressdetails": 1,
        "limit":         limit,
    }
    headers = {"User-Agent": "FloodHelpAgent-Gujrat-2025/1.0"}

    try:
        time.sleep(1)
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        if resp.status_code != 200:
            return f"Error: API returned status {resp.status_code}"

        data = resp.json()
        if not data:
            return f"No {amenity}s found in {city}, {state}, {country}"

        lines = [f"Found {len(data)} {amenity}(s) in {city}, {state}:\n"]
        for idx, place in enumerate(data, 1):
            lat = place.get("lat", "N/A")
            lon = place.get("lon", "N/A")
            lines += [
                f"{idx}. {place.get('display_name', 'Unknown')}",
                f"   Coordinates: Latitude {lat}, Longitude {lon}",
                "",
            ]
        return "\n".join(lines)

    except Exception as e:
        return f"Error searching amenities: {e}"


@tool
def get_city_bbox(
    city: str    = "Gujrat",
    state: str   = "Punjab",
    country: str = "Pakistan"
) -> str:
    """
    Get the bounding box coordinates for a city.

    Args:
        city:    City   (default: Gujrat)
        state:   State  (default: Punjab)
        country: Country (default: Pakistan)
    """
    url    = "https://nominatim.openstreetmap.org/search"
    params = {"format": "json", "city": city, "state": state, "country": country, "limit": 1}
    headers = {"User-Agent": "FloodHelpAgent-Gujrat-2025/1.0"}

    try:
        time.sleep(1)
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        if resp.status_code != 200:
            return f"Error: API returned status {resp.status_code}"

        data = resp.json()
        if not data:
            return f"City '{city}' not found."

        bbox = data[0].get("boundingbox")
        if bbox:
            return (
                f"Bounding box for {city}: "
                f"(min_lon: {bbox[2]}, min_lat: {bbox[0]}, "
                f"max_lon: {bbox[3]}, max_lat: {bbox[1]})"
            )
        return f"No bounding box data available for {city}."

    except Exception as e:
        return f"Error fetching city bounding box: {e}"


@tool
def check_flood_depth(lat: float, lon: float) -> str:
    """
    Check the real flood depth at a specific location using the flood shapefile.

    Args:
        lat: Latitude
        lon: Longitude
    """
    try:
        depth = _flood_depth_at_point(lat, lon)

        if depth == 0.0:
            return (
                f"Location ({lat}, {lon}):\n"
                f"- Flood Depth: 0 m\n"
                f"- Status: Safe (not in any flood zone)\n"
            )

        if depth > 2.0:
            severity = "HIGH RISK — evacuation recommended"
        elif depth > 1.0:
            severity = "MEDIUM RISK — avoid if possible"
        else:
            severity = "LOW RISK — proceed with caution"

        return (
            f"Location ({lat}, {lon}):\n"
            f"- Flood Depth : {depth:.2f} m\n"
            f"- Status      : FLOODED\n"
            f"- Severity    : {severity}\n"
        )

    except Exception as e:
        return f"Error checking flood depth: {e}"


@tool
def get_flooded_areas() -> str:
    """
    List all flood zones from the real shapefile with area, depth and centroid.
    """
    try:
        gdf = _get_flood_gdf()

        if gdf.empty:
            return "No flood zones found in the shapefile."

        depth_col = next(
            (c for c in gdf.columns if "depth" in c.lower()), None
        )

        lines = [f"Flood zones loaded from shapefile ({len(gdf)} polygon(s)):\n"]
        for i, row in gdf.iterrows():
            centroid = row.geometry.centroid
            area_km2 = row.geometry.area * (111 ** 2)

            depth_str = ""
            if depth_col and row[depth_col] is not None:
                depth_str = f"  - Max Depth  : {row[depth_col]:.2f} m\n"

            lines.append(
                f"Zone {i + 1}:\n"
                f"  - Centroid   : ({centroid.y:.5f}, {centroid.x:.5f})\n"
                f"  - Area       : ~{area_km2:.4f} km²\n"
                + depth_str
            )

        return "\n".join(lines)

    except Exception as e:
        return f"Error reading flood zones: {e}"


# ── Risk tier thresholds ──────────────────────────────────────────────────────
_RISK_TIERS = [
    (0.00, "NONE",     "No flood exposure"),
    (0.10, "LOW",      "Shallow water — passable on foot, most vehicles"),
    (0.30, "MODERATE", "Car limit reached — SUVs and trucks may pass"),
    (0.60, "HIGH",     "Impassable for most vehicles — specialist only"),
    (float("inf"), "CRITICAL", "Impassable — risk to life, do not attempt"),
]

def _depth_to_risk(depth: float) -> tuple[str, str]:
    """Return (tier_label, tier_description) for a given flood depth."""
    for threshold, label, desc in _RISK_TIERS:
        if depth <= threshold:
            return label, desc
    return "CRITICAL", "Impassable — risk to life, do not attempt"


@tool
def assess_path_flood_risk(
    start_lat: float, start_lon: float,
    end_lat:   float, end_lon:   float,
    steps:     int = 30
) -> str:
    """
    Assess the flood risk along the straight-line corridor between two points.
    Samples `steps + 1` evenly-spaced checkpoints, classifies each by flood
    depth into a risk tier, and returns an overall risk rating with a breakdown.

    Risk tiers (by max flood depth encountered):
      NONE     : 0.00 m  — no flood exposure
      LOW      : ≤ 0.10 m — passable on foot and by most vehicles
      MODERATE : ≤ 0.30 m — car flood tolerance limit
      HIGH     : ≤ 0.60 m — specialist/heavy vehicle only
      CRITICAL : > 0.60 m — impassable, risk to life

    NOTE: This scans a geometric straight line, not the actual road network.
    Use calculate_route for a flood-avoiding route on real roads.

    Args:
        start_lat / start_lon : Origin coordinates
        end_lat   / end_lon   : Destination coordinates
        steps                 : Number of intervals (default 30 → 31 checkpoints)
    """
    try:
        points = _route_points(start_lat, start_lon, end_lat, end_lon, steps=steps)
        n_checkpoints = len(points)

        # ── Sample every checkpoint ───────────────────────────────────────────
        samples = [
            (lat, lon, _flood_depth_at_point(lat, lon))
            for lat, lon in points
        ]

        flooded   = [(lat, lon, d) for lat, lon, d in samples if d > 0]
        max_depth = max((d for _, _, d in flooded), default=0.0)
        avg_depth = (sum(d for _, _, d in flooded) / len(flooded)) if flooded else 0.0

        # ── Overall risk tier ─────────────────────────────────────────────────
        overall_tier, overall_desc = _depth_to_risk(max_depth)

        # ── Per-tier breakdown ────────────────────────────────────────────────
        tier_counts: dict[str, int] = {"NONE": 0, "LOW": 0, "MODERATE": 0,
                                        "HIGH": 0, "CRITICAL": 0}
        for _, _, d in samples:
            label, _ = _depth_to_risk(d)
            tier_counts[label] += 1

        # ── Recommendation ────────────────────────────────────────────────────
        recommendations = {
            "NONE":     "Corridor appears clear. Confirm on road network with calculate_route.",
            "LOW":      "Minor flood exposure. Most vehicles can pass. Verify with calculate_route.",
            "MODERATE": "Car flood tolerance exceeded. Use ambulance/truck or calculate_route to find an alternative.",
            "HIGH":     "Specialist vehicles only. calculate_route strongly recommended for a safer road path.",
            "CRITICAL": "DO NOT ATTEMPT. Immediately use calculate_route for a flood-avoiding road route.",
        }

        # ── Format output ─────────────────────────────────────────────────────
        result = (
            f"Path Flood Risk Assessment (straight-line scan):\n"
            f"  From         : ({start_lat}, {start_lon})\n"
            f"  To           : ({end_lat}, {end_lon})\n"
            f"  Checkpoints  : {n_checkpoints}\n\n"
            f"  ┌─ OVERALL RISK : {overall_tier} ─────────────────┐\n"
            f"  │  {overall_desc:<42}│\n"
            f"  └──────────────────────────────────────────────────┘\n\n"
            f"  Max flood depth  : {max_depth:.2f} m\n"
            f"  Avg flood depth  : {avg_depth:.2f} m  (flooded checkpoints only)\n"
            f"  Flooded sections : {len(flooded)} / {n_checkpoints} checkpoints "
            f"({100 * len(flooded) / n_checkpoints:.0f}%)\n\n"
            f"  Risk tier breakdown:\n"
        )

        for tier in ["NONE", "LOW", "MODERATE", "HIGH", "CRITICAL"]:
            count = tier_counts[tier]
            bar   = "█" * count + "░" * (n_checkpoints - count)
            result += f"    {tier:<10}: {count:>3} pts  {bar[:20]}\n"

        if flooded:
            result += f"\n  Worst checkpoints (up to 3):\n"
            worst = sorted(flooded, key=lambda x: x[2], reverse=True)[:3]
            for lat, lon, depth in worst:
                tier_label, _ = _depth_to_risk(depth)
                result += f"    - ({lat:.5f}, {lon:.5f}): {depth:.2f} m  [{tier_label}]\n"

        result += f"\n  Recommendation: {recommendations[overall_tier]}\n"
        return result

    except Exception as e:
        return f"Error assessing path flood risk: {e}"


@tool
def check_amenity_flood_status(
    amenity: str,
    city: str    = "Gujrat",
    state: str   = "Punjab",
    country: str = "Pakistan"
) -> str:
    """
    Check which hospitals, schools, or other amenities are currently in flood zones
    according to the real shapefile.

    Args:
        amenity: Type of amenity (e.g. 'hospital', 'school')
        city:    City   (default: Gujrat)
        state:   State  (default: Punjab)
        country: Country (default: Pakistan)
    """
    try:
        url    = "https://nominatim.openstreetmap.org/search"
        params = {
            "q":             f"{amenity} in {city}, {state}, {country}",
            "format":        "json",
            "addressdetails": 1,
            "limit":         15,
        }
        headers = {"User-Agent": "FloodHelpAgent-Gujrat-2025/1.0"}
        time.sleep(1)
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        if resp.status_code != 200:
            return f"Error fetching amenities: status {resp.status_code}"

        data = resp.json()
        if not data:
            return f"No {amenity}s found in {city}."

        safe_list, flood_list = [], []
        for place in data:
            name  = place.get("display_name", "Unknown").split(",")[0].strip()
            lat   = float(place.get("lat", 0))
            lon   = float(place.get("lon", 0))
            depth = _flood_depth_at_point(lat, lon)

            entry = {"name": name, "lat": lat, "lon": lon, "depth": depth}
            if depth > 0:
                flood_list.append(entry)
            else:
                safe_list.append(entry)

        lines = [
            f"Flood Impact Analysis — {amenity.capitalize()}s in {city}:",
            f"  Total analysed : {len(data)}",
            f"  Safe           : {len(safe_list)}",
            f"  Flooded        : {len(flood_list)}",
            "",
        ]

        if flood_list:
            lines.append(f"FLOODED {amenity.upper()}S (avoid):")
            for p in flood_list[:5]:
                lines.append(f"  ✗ {p['name']}")
                lines.append(f"    Depth: {p['depth']:.2f} m  |  ({p['lat']}, {p['lon']})")
            if len(flood_list) > 5:
                lines.append(f"  … and {len(flood_list) - 5} more")
            lines.append("")

        if safe_list:
            lines.append(f"SAFE {amenity.upper()}S (accessible):")
            for p in safe_list[:5]:
                lines.append(f"  ✓ {p['name']}")
                lines.append(f"    Location: ({p['lat']}, {p['lon']})")
            if len(safe_list) > 5:
                lines.append(f"  … and {len(safe_list) - 5} more")

        return "\n".join(lines)

    except Exception as e:
        return f"Error analysing flood impact: {e}"


@tool
def check_vehicle_passability(
    lat: float,
    lon: float,
    vehicle_type: str = "car"
) -> str:
    """
    Check if a vehicle can pass a location given current real flood depth.

    Args:
        lat:          Latitude
        lon:          Longitude
        vehicle_type: 'car', 'ambulance', 'truck', or 'boat' (default: 'car')
    """
    limits = {"car": 0.3, "ambulance": 0.4, "truck": 0.6, "boat": 999.0}
    limit  = limits.get(vehicle_type.lower(), 0.3)

    try:
        depth    = _flood_depth_at_point(lat, lon)
        passable = depth <= limit

        rec = (
            "Location is passable."
            if passable
            else f"Do NOT attempt with a {vehicle_type}. Depth {depth:.2f} m exceeds limit {limit} m."
        )

        return (
            f"Vehicle Passability at ({lat}, {lon}):\n"
            f"  Vehicle type  : {vehicle_type.capitalize()}\n"
            f"  Flood depth   : {depth:.2f} m\n"
            f"  Vehicle limit : {limit} m\n"
            f"  Status        : {'PASSABLE' if passable else 'NOT PASSABLE'}\n"
            f"  Recommendation: {rec}\n"
        )

    except Exception as e:
        return f"Error checking vehicle passability: {e}"


@tool
def calculate_route(
    start_lat: float,
    start_lon: float,
    end_lat:   float,
    end_lon:   float,
    vehicle_type: str = "car",
    k:            int = 1
) -> str:
    """
    Compute up to K flood-aware shortest routes on the real road network using the
    flood shapefile.  Results are cached for visualize_route.

    Args:
        start_lat / start_lon: Origin coordinates
        end_lat   / end_lon  : Destination coordinates
        vehicle_type:   'car' (default)
        k:              Number of alternative routes (default: 1)
    """
    try:
        routes, G, G_simple = get_shortest_path(
            lat1=start_lat, lon1=start_lon,
            lat2=end_lat,   lon2=end_lon,
            token="",
            place=OSM_PLACE,
            file_name=SHAPEFILE_PATH,
            k=k,
            vehicle_type=vehicle_type,
            vehicle_config=vechile_config,
        )

        if not routes:
            return "No routes found between the given coordinates."

        # Cache for visualize_route — also store vehicle_type so visualize
        # can pull the correct edges_gdf from road_graph_cache directly
        _route_cache["routes"]       = routes
        _route_cache["G"]            = G
        _route_cache["G_simple"]     = G_simple
        _route_cache["vehicle_type"] = vehicle_type

        lines = [f"Found {len(routes)} route(s):\n"]
        for i, route in enumerate(routes, 1):
            length = sum(
                G_simple[u][v].get("length", 0)
                for u, v in zip(route[:-1], route[1:])
                if G_simple.has_edge(u, v)
            )
            flooded = sum(
                1 for u, v in zip(route[:-1], route[1:])
                if G_simple.has_edge(u, v)
                and G_simple[u][v].get("flood_level", 0) > 0
            )
            lines.append(
                f"  Route {i}: {length:.0f} m | {len(route)} nodes "
                f"| {flooded} flooded segment(s)"
            )

        lines.append("\nCall visualize_route to generate an interactive HTML map.")
        return "\n".join(lines)

    except Exception as e:
        return f"Error calculating route: {e}"


@tool
def visualize_route(output_file: str = "graph.html") -> str:
    """
    Save an interactive Folium map of the routes computed by calculate_route.
    Must be called AFTER calculate_route.

    Args:
        output_file: Output HTML file path (default: 'graph.html')
    """
    try:
        if not _route_cache.get("routes"):
            return "No routes cached. Please run calculate_route first."

        routes       = _route_cache["routes"]
        G            = _route_cache["G"]
        G_simple     = _route_cache["G_simple"]
        vehicle_type = _route_cache.get("vehicle_type", "car")

        # Pull edges_gdf and flood_data straight from the caches —
        # no graph rebuild, no shapefile re-read
        _, G_simple_cached, edges_gdf = road_graph_cache.get(
            OSM_PLACE, SHAPEFILE_PATH, vehicle_type, vechile_config
        )
        flood_data = _get_flood_gdf().to_crs(edges_gdf.crs)
        vehicle    = vechile_config[vehicle_type]

        visualize_routes(
            G=G,
            G_simple=G_simple,
            vehicle=vehicle,
            vehicle_config=vechile_config,
            edges_gdf=edges_gdf,
            routes=routes,
            flood_data=flood_data,
        )

        return "Map saved to graph.html. Open it in any browser to view the interactive route map."

    except Exception as e:
        return f"Error visualising route: {e}"


@tool
def optimize_flood_safe_route(
    start_lat: float,
    start_lon: float,
    locations: List[Dict[str, Any]]
) -> str:
    """
    Find the safest visiting order and flood-avoiding path across multiple locations
    using the real shapefile for flood penalties.

    Args:
        start_lat / start_lon: Starting position
        locations: List of dicts — [{"name": "...", "lat": ..., "lon": ...}]
    """
    import math

    def haversine(lat1, lon1, lat2, lon2):
        R = 6371
        return R * math.acos(
            math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
            math.cos(math.radians(lon2 - lon1)) +
            math.sin(math.radians(lat1)) * math.sin(math.radians(lat2))
        )

    def flood_penalty(lat, lon):
        depth = _flood_depth_at_point(lat, lon)
        if depth > 2:   return 1000
        if depth > 1:   return 100
        if depth > 0.3: return 10
        return 0

    try:
        current     = (start_lat, start_lon)
        route_order = []
        unvisited   = locations.copy()

        while unvisited:
            nearest = min(
                unvisited,
                key=lambda loc: haversine(current[0], current[1], loc["lat"], loc["lon"])
            )
            route_order.append(nearest)
            current = (nearest["lat"], nearest["lon"])
            unvisited.remove(nearest)

        lines = ["Flood-Safe Multi-Stop Route:\n"]
        for i, loc in enumerate(route_order, 1):
            depth = _flood_depth_at_point(loc["lat"], loc["lon"])
            flag  = " ⚠ FLOODED" if depth > 0 else " ✓ Safe"
            lines.append(f"  {i}. {loc['name']} ({loc['lat']}, {loc['lon']}){flag}")
            if depth > 0:
                lines.append(f"     Flood depth at stop: {depth:.2f} m")

        lines.append("\nRoute avoids flooded areas as much as possible.")
        lines.append("Use calculate_route for turn-by-turn road directions between stops.")
        return "\n".join(lines)

    except Exception as e:
        return f"Error optimising route: {e}"


# ============================================================================
# TOOLS MAP
# ============================================================================

TOOLS_MAP = {
    "get_coordinates_from_location": get_coordinates_from_location,
    "search_amenity":                search_amenity,
    "get_city_bbox":                 get_city_bbox,
    "check_flood_depth":             check_flood_depth,
    "get_flooded_areas":             get_flooded_areas,
    "assess_path_flood_risk":        assess_path_flood_risk,
    "check_amenity_flood_status":    check_amenity_flood_status,
    "check_vehicle_passability":     check_vehicle_passability,
    "calculate_route":               calculate_route,
    "visualize_route":               visualize_route,
    "optimize_flood_safe_route":     optimize_flood_safe_route,
}


# ============================================================================
# AGENT STATE
# ============================================================================

class AgentState(TypedDict):
    messages:            Annotated[list, add_messages]
    initial_query:       str
    plan:                list
    current_group_index: int
    current_step:        str


# ============================================================================
# PROMPTS
# ============================================================================

PLANNER_PROMPT = PromptTemplate(
    input_variables=["initial_query"],
    template="""
You are a PLANNING AGENT for a Flood Disaster Assistance System in Gujrat, Punjab, Pakistan.
Flood data comes from a real EMSR838 Copernicus shapefile.

User request: {initial_query}

Produce a COMPLETE execution plan. Group independent steps that can run simultaneously
into the same "group" number. Steps that depend on a previous step's output must have
a higher group number.

AVAILABLE TOOLS:
  1.  get_coordinates_from_location — convert a place name to lat/lon
  2.  search_amenity                — find hospitals, shelters, police stations, etc.
  3.  get_city_bbox                 — get bounding box for a city
  4.  check_flood_depth             — real flood depth at coordinates (shapefile)
  5.  get_flooded_areas             — list all flood zones from the shapefile
  6.  assess_path_flood_risk        — straight-line corridor flood risk assessment with per-tier breakdown (NONE / LOW / MODERATE / HIGH / CRITICAL). Not a road route. Use calculate_route for real road-network routing.
  7.  check_amenity_flood_status    — check which facilities are in flood zones
  8.  check_vehicle_passability     — check if a vehicle can pass given flood depth
  9.  calculate_route               — K shortest flood-aware routes on real road network
  10. visualize_route               — save interactive HTML map (must run AFTER calculate_route)
  11. optimize_flood_safe_route     — safest visiting order for multiple stops

GROUPING RULES:
- Same group number = runs in PARALLEL (no dependency on each other).
- Higher group number = runs AFTER all steps in the previous group finish.
- get_coordinates_from_location must always be group 1 if place names are present.
- Any tool that needs coordinates must be in a group AFTER the coordinates step.
- visualize_route must always be in a group AFTER calculate_route.

OUTPUT — return ONLY valid JSON, no markdown fences:
{{
  "plan": [
    {{
      "group": 1,
      "step": 1,
      "tool": "<tool_name>",
      "purpose": "<one sentence why>",
      "input_description": "<what to pass>"
    }}
  ]
}}
"""
)

EXECUTOR_PROMPT = PromptTemplate(
    input_variables=["initial_query", "tool_name", "purpose", "input_description", "previous_results"],
    template="""
You are a FLOOD DISASTER EXECUTION AGENT for Gujrat, Punjab, Pakistan.
Flood data is sourced from the real EMSR838 Copernicus shapefile.

Original user request: {initial_query}

Results from previous tool calls (already completed):
{previous_results}

YOUR CURRENT TASK:
  Tool      : {tool_name}
  Purpose   : {purpose}
  Input hint: {input_description}

Using the previous results to resolve any arguments, call EXACTLY the tool "{tool_name}".
Do NOT call any other tool. Do NOT write a final answer — only the tool call.
"""
)

RESPONDER_PROMPT = PromptTemplate(
    input_variables=["initial_query", "tool_results"],
    template="""
You are a flood disaster response assistant for Gujrat, Punjab, Pakistan.
All flood information is based on the real EMSR838 Copernicus Emergency Management shapefile.

The user asked: {initial_query}

All tool results collected:
{tool_results}

Using only the information above, write a clear, helpful, safety-focused final response.
- Highlight flooded areas and unsafe routes.
- Recommend only verified-safe facilities.
- If a road route map was generated, mention that the user can open graph.html in a browser.
"""
)


# ============================================================================
# HELPERS
# ============================================================================

def _collect_tool_results(messages: list, max_chars: int = 3000) -> str:
    """Collect tool results, truncating each to avoid context overflow."""
    parts = []
    for m in messages:
        if isinstance(m, ToolMessage):
            content = m.content
            if len(content) > max_chars:
                content = content[:max_chars] + f"\n... [truncated, {len(m.content)} chars total]"
            parts.append(f"[{m.name}]: {content}")
    return "\n".join(parts) if parts else "No results yet."


def _make_model(with_tools: bool = False):
    model = ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0,
        api_key="",
    )
    return model.bind_tools(list(TOOLS_MAP.values())) if with_tools else model


def _parse_json(text: str) -> dict:
    clean = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
    return json.loads(clean)


def _get_groups(plan: list) -> list:
    sorted_plan = sorted(plan, key=lambda s: s["group"])
    return [list(steps) for _, steps in groupby(sorted_plan, key=lambda s: s["group"])]


# ============================================================================
# NODE 1 — PLANNER
# ============================================================================

def planner_node(state: AgentState) -> AgentState:
    query    = state["initial_query"]
    chain    = PLANNER_PROMPT | _make_model()
    response = chain.invoke({"initial_query": query})

    try:
        data = _parse_json(response.content)
        plan = data.get("plan", [])
    except (json.JSONDecodeError, AttributeError):
        plan = []

    groups = _get_groups(plan)
    print(f"\n[PLANNER] {len(plan)} steps across {len(groups)} group(s):")
    for g in groups:
        names = [s["tool"] for s in g]
        label = "parallel" if len(g) > 1 else "sequential"
        print(f"  Group {g[0]['group']} ({label}): {', '.join(names)}")

    return {
        **state,
        "messages":            state["messages"] + [response],
        "plan":                plan,
        "current_group_index": 0,
        "current_step":        "planner_done",
    }


# ============================================================================
# SINGLE-TOOL EXECUTOR (runs in a thread — must be stateless)
# ============================================================================

def _execute_single_step(step: dict, initial_query: str, previous_results: str) -> list:
    if len(previous_results) > 6000:
        previous_results = "[earlier results truncated]\n" + previous_results[-6000:]

    prompt_text = EXECUTOR_PROMPT.format(
        initial_query=initial_query,
        tool_name=step["tool"],
        purpose=step["purpose"],
        input_description=step["input_description"],
        previous_results=previous_results,
    )
    model_with_tools = _make_model(with_tools=True)
    llm_response     = model_with_tools.invoke([HumanMessage(content=prompt_text)])
    new_messages     = [llm_response]

    if hasattr(llm_response, "tool_calls") and llm_response.tool_calls:
        for tc in llm_response.tool_calls:
            tool_fn = TOOLS_MAP.get(tc["name"])
            try:
                result = tool_fn.invoke(tc["args"]) if tool_fn else f"Unknown tool: {tc['name']}"
            except Exception as e:
                result = f"Error: {e}"
            new_messages.append(
                ToolMessage(content=str(result), tool_call_id=tc["id"], name=tc["name"])
            )

    return new_messages


# ============================================================================
# NODE 2 — TOOL EXECUTOR
# ============================================================================

def tool_executor_node(state: AgentState) -> AgentState:
    plan      = state["plan"]
    group_idx = state["current_group_index"]
    messages  = state["messages"]
    query     = state["initial_query"]
    groups    = _get_groups(plan)

    if group_idx >= len(groups):
        return {**state, "current_step": "plan_exhausted"}

    current_group = groups[group_idx]

    recent_messages  = messages[-20:]
    previous_results = _collect_tool_results(recent_messages, max_chars=2000)

    is_parallel = len(current_group) > 1
    if is_parallel:
        all_new_messages = []
        futures_map      = {}

        with ThreadPoolExecutor(max_workers=len(current_group)) as executor:
            for step in current_group:
                future = executor.submit(_execute_single_step, step, query, previous_results)
                futures_map[future] = step["tool"]

            for future in as_completed(futures_map):
                tool_name = futures_map[future]
                try:
                    result_msgs = future.result()
                    print(f"  [parallel] {tool_name} → done")
                except Exception as e:
                    print(f"  [parallel] {tool_name} → FAILED: {e}")
                    result_msgs = []
                all_new_messages.extend(result_msgs)
    else:
        step = current_group[0]
        print(f"  [sequential] {step['tool']}")
        all_new_messages = _execute_single_step(step, query, previous_results)

    return {
        **state,
        "messages":            messages + all_new_messages,
        "current_group_index": group_idx + 1,
        "current_step":        "group_executed",
    }


# ============================================================================
# NODE 3 — RESPONDER
# ============================================================================

def responder_node(state: AgentState) -> AgentState:
    query        = state["initial_query"]
    tool_results = _collect_tool_results(state["messages"])
    chain        = RESPONDER_PROMPT | _make_model()
    response     = chain.invoke({"initial_query": query, "tool_results": tool_results})

    print("\n[RESPONDER] Final response ready.")
    return {
        **state,
        "messages":     state["messages"] + [response],
        "current_step": "done",
    }


# ============================================================================
# CONDITIONAL EDGE
# ============================================================================

def has_more_groups(state: AgentState) -> str:
    groups = _get_groups(state["plan"])
    return "continue" if state["current_group_index"] < len(groups) else "end"


# ============================================================================
# GRAPH
# ============================================================================

def create_flood_agent():
    workflow = StateGraph(AgentState)

    workflow.add_node("planner",       planner_node)
    workflow.add_node("tool_executor", tool_executor_node)
    workflow.add_node("responder",     responder_node)

    workflow.set_entry_point("planner")
    workflow.add_edge("planner", "tool_executor")
    workflow.add_conditional_edges(
        "tool_executor",
        has_more_groups,
        {"continue": "tool_executor", "end": "responder"},
    )
    workflow.add_edge("responder", END)

    g = workflow.compile()

    png_bytes = g.get_graph().draw_mermaid_png()
    with open("graph.png", "wb") as f:
        f.write(png_bytes)

    return g


# ============================================================================
# RUNNER
# ============================================================================

def run_agent(query: str):
    agent  = create_flood_agent()
    result = agent.invoke({
        "messages":            [HumanMessage(content=query)],
        "initial_query":       query,
        "plan":                [],
        "current_group_index": 0,
        "current_step":        "start",
    })

    print("\n" + "=" * 70)
    print(result["messages"][-1].content)

    groups      = _get_groups(result["plan"])
    total_steps = len(result["plan"])
    print(
        f"\n{total_steps} steps in {len(groups)} group(s) | "
        f"parallel batches: {sum(1 for g in groups if len(g) > 1)}"
    )
    return result


# ============================================================================
# DEMO QUERIES
# ============================================================================

if __name__ == "__main__":
    demo_queries = [
        "Is DHQ Hospital Gujrat flooded?",
        "Which hospitals in Gujrat are affected by current flooding?",
        "Can an ambulance reach DHQ Hospital in Gujrat?",
        (
            "I'm at Gujrat Railway Station and need urgent medical help. "
            "Find the nearest safe hospital and check if an ambulance can reach there. "
            "Find nearest safe hospital and show me the route."
        ),
        (
            "Compare flood impact on hospitals in northern vs southern Gujrat "
            "and recommend which area has better emergency services access."
        ),
        (
            "We need to evacuate patients from a flooded hospital. "
            "Find all accessible hospitals that can receive patients "
            "and check ambulance routes to each."
        ),
        (
            "Calculate the safest driving route from (32.5695347, 71.5695347) "
            "to DHQ Hospital and show me the map."
        ),
        (
            "Emergency: Show all flooded areas, identify which hospitals need "
            "immediate evacuation, find safe hospitals for patient transfer, "
            "and verify which emergency vehicles can navigate the routes."
        ),
    ]

    selected = 7  # change index 0-7 to run a different query

    print(f"\nExecuting Query {selected + 1}:")
    print(f"'{demo_queries[selected]}'\n")
    print("=" * 80 + "\n")

    run_agent(demo_queries[selected])
