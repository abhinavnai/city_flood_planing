import os
from typing import Optional, TypedDict, Annotated, Sequence
import operator
from langchain_core import messages
from langgraph.graph import StateGraph, END, add_messages
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.tools import tool
import requests
import time
from flood_data_simulator import flood_simulator
from dotenv import load_dotenv
import json
import re
import ssl
import certifi
from shortest_path import get_shortest_path, visualize_routes

load_dotenv()

# ============================================================================
# TOOLS DEFINITION
# ============================================================================

@tool
def search_amenity(amenity: str, city: str, state: str = "Rajasthan", country: str = "India", limit: int = 10) -> str:
    """
     # Select query to run (change index: 0-6 for queries 1-7)
    selected_query_index = 0  # Default: Query 1 (simple - uses fewer API calls)
    
    print(f"\nExecuting Query {selected_query_index + 1}:")
    print(f"'{btp_demo_queries[selected_query_index]}'\n")
    print("="*80 + "\n")es (like hospitals, schools, shelters, pharmacies) in a specific city.
    
    Args:
        amenity: Type of amenity to search (e.g., 'hospital', 'school', 'pharmacy', 'shelter', 'fire_station')
        city: Name of the city (e.g., 'Jodhpur')
        state: State name (default: 'Rajasthan')
        country: Country name (default: 'India')
        limit: Maximum number of results (default: 10)
    
    Returns:
        Formatted string with amenity locations, names, and coordinates
    """
    url = "https://nominatim.openstreetmap.org/search"
    
    # Use free-form query format for better results
    query = f"{amenity} in {city}, {state}, {country}"
    
    params = {
        "q": query,
        "format": "json",
        "addressdetails": 1,
        "limit": limit
    }

    headers = {
        "User-Agent": "FloodHelpAgent-BTP-2025/1.0"
    }

    try:
        # Add small delay to respect rate limits
        time.sleep(1)
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        if response.status_code != 200:
            return f"Error: API returned status code {response.status_code}"

        data = response.json()
        if not data:
            return f"No {amenity}s found in {city}, {state}, {country}"

        # Format results
        results = []
        results.append(f"Found {len(data)} {amenity}(s) in {city}, {state}:\n")
        
        for idx, place in enumerate(data, 1):
            name = place.get("display_name", "Unknown")
            lat = place.get("lat", "N/A")
            lon = place.get("lon", "N/A")
            results.append(f"{idx}. {name}")
            results.append(f"   Coordinates: Latitude {lat}, Longitude {lon}")
            results.append("")
        
        return "\n".join(results)
    
    except Exception as e:
        return f"Error searching for amenities: {str(e)}"


@tool
def get_city_bbox(city: str="Gujrat", state: str = "Punjab", country: str = "pakistan") -> str:
    """
    Get the bounding box coordinates for a city. Useful for flood mapping and area analysis.
    
    Args:
        city: Name of the city (e.g., 'Jodhpur')
        state: State name (default: 'Rajasthan')
        country: Country name (default: 'India')
    
    Returns:
        Bounding box coordinates as string (min_lon, min_lat, max_lon, max_lat)
    """
    url = "https://nominatim.openstreetmap.org/search"
    
    params = {
        "format": "json",
        "city": city,
        "state": state,
        "country": country,
        "limit": 1
    }
    
    headers = {
        "User-Agent": "FloodHelpAgent-BTP-2025/1.0"
    }
    
    try:
        time.sleep(1)  # Rate limiting
        response = requests.get(url, params=params, headers=headers, timeout=10)
        if response.status_code != 200:
            return f"Error: API returned status code {response.status_code}"
        
        data = response.json()
        if not data:
            return f"City {city} not found"
        
        bbox = data[0].get("boundingbox")
        if bbox:
            # bbox format: [min_lat, max_lat, min_lon, max_lon]
            return f"Bounding box for {city}: (min_lon: {bbox[2]}, min_lat: {bbox[0]}, max_lon: {bbox[3]}, max_lat: {bbox[1]})"
        else:
            return f"No bounding box data available for {city}"
    
    except Exception as e:
        return f"Error fetching city bounding box: {str(e)}"


@tool
def get_coordinates_from_location(location_name: str, city: str="Gujrat", state: str = "Punjab", country: str = "India") -> str:
    """
    Convert a location name (like "AIIMS", "Railway Station", "City Hospital") to GPS coordinates.
    ALWAYS use this tool when user provides a place name instead of coordinates.
    This tool must be called BEFORE using tools that require lat/lon parameters.
    
    Args:
        location_name: Name of the location (e.g., "AIIMS Jodhpur", "Railway Station", "Umaid Bhawan Palace")
        city: City name (default: 'Jodhpur')
        state: State name (default: 'Rajasthan')
        country: Country name (default: 'India')
    
    Returns:
        Coordinates and address information. Extract the lat/lon from the response to use with other tools.
    """
    url = "https://nominatim.openstreetmap.org/search"
    
    # Build query with location context
    query = f"{location_name}, {city}, {state}, {country}"
    
    params = {
        "q": query,
        "format": "json",
        "addressdetails": 1,
        "limit": 3  # Get top 3 matches
    }
    
    headers = {
        "User-Agent": "FloodHelpAgent-BTP-2025/1.0"
    }
    
    try:
        time.sleep(1)  # Rate limiting
        response = requests.get(url, params=params, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return f"Error: API returned status code {response.status_code}"
        
        data = response.json()
        if not data:
            return f"Location '{location_name}' not found in {city}. Please try a different name or provide coordinates."
        
        # Format results
        results = []
        results.append(f"Found {len(data)} match(es) for '{location_name}' in {city}:\n")
        
        for idx, place in enumerate(data, 1):
            name = place.get("display_name", "Unknown")
            lat = float(place.get("lat", 0))
            lon = float(place.get("lon", 0))
            place_type = place.get("type", "location")
            
            results.append(f"{idx}. {name}")
            results.append(f"   Type: {place_type}")
            results.append(f"   Coordinates: Latitude {lat}, Longitude {lon}")
            results.append(f"   📍 Use these coordinates: ({lat}, {lon})")
            results.append("")
        
        results.append("💡 Tip: Use the coordinates above with other tools like check_flood_depth or check_route_flood_safety")
        
        return "\n".join(results)
    
    except Exception as e:
        return f"Error finding location coordinates: {str(e)}"


@tool
def calculate_route(start_lat: float, start_lon: float, end_lat: float, end_lon: float) -> str:
    """
    Calculate the shortest route between two points.
    
    Args:
        start_lat: Starting point latitude
        start_lon: Starting point longitude
        end_lat: Destination point latitude
        end_lon: Destination point longitude
    
    Returns:
        Route information as a list
    """
    
    try:
        routes,G,G_simple=get_shortest_path(start_lat,start_lon,end_lat,end_lon)
        return routes,G,G_simple
    
    except Exception as e:
        return f"Error calculating route: {str(e)}"

@tool 
def visulize_route(route: list) -> str:
    """
    Visualize the calculated route on a map.
    
    Args:
        route: List of coordinates representing the route
    
    Returns:
        A URL or file path to the visualized route map
    """
    try:
        return visualize_routes(route)
    
    except Exception as e:
        return f"Error visualizing route: {str(e)}"
@tool
def check_flood_depth(lat: float, lon: float) -> str:
    """
    Check the flood depth at a specific location in Jodhpur.
    
    Args:
        lat: Latitude of the location
        lon: Longitude of the location
    
    Returns:
        Flood depth information and safety status
    """
    try:
        depth = flood_simulator.get_flood_depth(lat, lon)
        is_flooded = flood_simulator.is_location_flooded(lat, lon)
        
        status = "FLOODED" if is_flooded else "Safe"
        
        result = f"Location ({lat}, {lon}):\n"
        result += f"- Flood Depth: {depth} meters\n"
        result += f"- Status: {status}\n"
        
        if depth > 0:
            if depth > 2.0:
                result += "- Severity: HIGH RISK - Evacuation recommended\n"
            elif depth > 1.0:
                result += "- Severity: MEDIUM RISK - Avoid if possible\n"
            elif depth > 0.3:
                result += "- Severity: LOW RISK - Proceed with caution\n"
        
        return result
    
    except Exception as e:
        return f"Error checking flood depth: {str(e)}"


@tool
def get_flooded_areas() -> str:
    """
    Get a list of all currently flooded areas in Jodhpur.
    
    Returns:
        Formatted list of flooded zones with severity and depth information
    """
    try:
        areas = flood_simulator.get_flooded_areas()
        
        if not areas:
            return "No significant flooding detected in Jodhpur at this time."
        
        result = f"Currently {len(areas)} flooded areas detected in Jodhpur:\n\n"
        
        for area in areas:
            result += f"Area {area['area_id']}:\n"
            result += f"  - Location: ({area['center_lat']}, {area['center_lon']})\n"
            result += f"  - Affected Radius: {area['radius_km']:.2f} km\n"
            result += f"  - Max Depth: {area['max_depth_meters']} meters\n"
            result += f"  - Severity: {area['severity']}\n\n"
        
        return result
    
    except Exception as e:
        return f"Error fetching flooded areas: {str(e)}"


@tool
def check_amenity_flood_status(amenity: str, city: str = "Jodhpur", state: str = "Rajasthan", country: str = "India") -> str:
    """
    Check which hospitals, schools, or other amenities are affected by current flooding.
    
    Args:
        amenity: Type of amenity (e.g., 'hospital', 'school', 'pharmacy')
        city: City name (default: 'Jodhpur')
        state: State name (default: 'Rajasthan')
        country: Country name (default: 'India')
    
    Returns:
        Analysis of which amenities are flooded and which are safe
    """
    try:
        # First, get the amenities using free-form query
        url = "https://nominatim.openstreetmap.org/search"
        query = f"{amenity} in {city}, {state}, {country}"
        params = {
            "q": query,
            "format": "json",
            "addressdetails": 1,
            "limit": 15
        }
        headers = {"User-Agent": "FloodHelpAgent-BTP-2025/1.0"}
        
        time.sleep(1)  # Rate limiting
        response = requests.get(url, params=params, headers=headers, timeout=10)
        if response.status_code != 200:
            return f"Error fetching amenities: Status {response.status_code}"
        
        data = response.json()
        if not data:
            return f"No {amenity}s found in {city}"
        
        # Format POIs for flood check
        pois = []
        for place in data:
            pois.append({
                'name': place.get('display_name', 'Unknown').split(',')[0],
                'lat': place.get('lat'),
                'lon': place.get('lon')
            })
        
        # Check flood status
        analysis = flood_simulator.get_affected_pois(pois, threshold=0.5)
        
        result = f"Flood Impact Analysis for {amenity.capitalize()}s in {city}:\n\n"
        result += f"Total {amenity}s analyzed: {analysis['total_pois']}\n"
        result += f"✓ Safe/Accessible: {analysis['safe_count']}\n"
        result += f"✗ Affected/Flooded: {analysis['affected_count']}\n\n"
        
        if analysis['affected_count'] > 0:
            result += f"AFFECTED {amenity.upper()}S (unreachable/flooded):\n"
            for poi in analysis['affected_pois'][:5]:  # Show first 5
                result += f"  ✗ {poi['name']}\n"
                result += f"    Flood depth: {poi['flood_depth']}m at ({poi['lat']}, {poi['lon']})\n"
            
            if len(analysis['affected_pois']) > 5:
                result += f"  ... and {len(analysis['affected_pois']) - 5} more\n"
        
        if analysis['safe_count'] > 0:
            result += f"\nSAFE/ACCESSIBLE {amenity.upper()}S:\n"
            for poi in analysis['safe_pois'][:5]:  # Show first 5
                result += f"  ✓ {poi['name']}\n"
                result += f"    Location: ({poi['lat']}, {poi['lon']})\n"
            
            if len(analysis['safe_pois']) > 5:
                result += f"  ... and {len(analysis['safe_pois']) - 5} more\n"
        
        return result
    
    except Exception as e:
        return f"Error analyzing flood impact: {str(e)}"


@tool
def check_route_flood_safety(start_lat: float, start_lon: float, end_lat: float, end_lon: float) -> str:
    """
    Check if a route passes through flooded areas and is safe for travel.
    If user provides location NAMES instead of coordinates, first call get_coordinates_from_location 
    for BOTH the start and end locations to get their lat/lon values.
    
    Args:
        start_lat: Starting point latitude (get from get_coordinates_from_location if name provided)
        start_lon: Starting point longitude (get from get_coordinates_from_location if name provided)
        end_lat: Destination latitude (get from get_coordinates_from_location if name provided)
        end_lon: Destination longitude (get from get_coordinates_from_location if name provided)
    
    Returns:
        Route safety analysis with flood information
    """
    try:
        analysis = flood_simulator.check_route_flooding(start_lat, start_lon, end_lat, end_lon)
        
        result = f"Route Safety Analysis:\n"
        result += f"From: ({start_lat}, {start_lon})\n"
        result += f"To: ({end_lat}, {end_lon})\n\n"
        result += f"Status: {'✓ SAFE' if analysis['route_safe'] else '✗ UNSAFE - FLOODED'}\n"
        result += f"Flooded sections: {analysis['flooded_sections']}\n"
        result += f"Maximum flood depth on route: {analysis['max_depth_on_route']} meters\n"
        result += f"Recommendation: {analysis['recommendation']}\n"
        
        if analysis['flooded_points']:
            result += f"\nFlooded checkpoints:\n"
            for point in analysis['flooded_points']:
                result += f"  - ({point['lat']}, {point['lon']}): {point['depth']}m deep\n"
        
        return result
    
    except Exception as e:
        return f"Error checking route safety: {str(e)}"


@tool
def check_vehicle_passability(lat: float, lon: float, vehicle_type: str = "car") -> str:
    """
    Check if a location is passable for a specific vehicle type given current flood conditions.
    
    Args:
        lat: Latitude of the location
        lon: Longitude of the location
        vehicle_type: Type of vehicle - 'car', 'ambulance', 'truck', or 'boat' (default: 'car')
    
    Returns:
        Vehicle passability information
    """
    try:
        result_data = flood_simulator.is_road_passable(lat, lon, vehicle_type)
        
        result = f"Vehicle Passability at ({lat}, {lon}):\n"
        result += f"Vehicle Type: {vehicle_type.capitalize()}\n"
        result += f"Flood Depth: {result_data['flood_depth']} meters\n"
        result += f"Vehicle Limit: {result_data['vehicle_limit']} meters\n"
        result += f"Status: {'✓ PASSABLE' if result_data['passable'] else '✗ NOT PASSABLE'}\n"
        result += f"Recommendation: {result_data['recommendation']}\n"
        
        return result
    
    except Exception as e:
        return f"Error checking vehicle passability: {str(e)}"
class AgentState(TypedDict):
    messages:       Annotated[list, add_messages]
    initial_query:  str
    plan:           list        # full ordered list of steps — written once by planner
    current_step_index: int     # which step the executor is currently on
    current_step:   str

# ============================================================================
# UPDATED PLANNER PROMPT — marks parallel groups
# ============================================================================

PLANNER_PROMPT = PromptTemplate(
    input_variables=["initial_query"],
    template="""
You are a PLANNING AGENT for a Flood Disaster Assistance System (Jodhpur, Rajasthan).

User request: {initial_query}

Produce a COMPLETE execution plan. Group independent steps that can run simultaneously
into the same "group" number. Steps that depend on a previous step's output must have
a higher group number.

AVAILABLE TOOLS:
  1. get_coordinates_from_location  — convert a place name to lat/lon
  2. search_amenity                 — find hospitals, shelters, police stations, etc.
  3. check_amenity_flood_status     — check if a specific facility is flooded
  4. check_route_flood_safety       — check if a route between two points is safe
  5. check_vehicle_passability      — check if a vehicle type can pass flood water
  6. check_flood_depth              — get flood depth at coordinates
  7. get_flooded_areas              — list all currently flooded zones

GROUPING RULES:
- Same group number = runs in PARALLEL (no dependency on each other).
- Higher group number = runs AFTER all steps in the previous group finish.
- get_coordinates_from_location must always be group 1 if place names are present.
- Any tool that needs coordinates must be in a group AFTER the coordinates step.
- Tools that are fully independent of each other (e.g. get_flooded_areas and
  get_coordinates_from_location) can share the same group.

EXAMPLE for "find safe hospital near Sardarpura and check if ambulance can pass":
  group 1 (parallel): get_coordinates_from_location(Sardarpura), get_flooded_areas
  group 2 (parallel): search_amenity(hospitals), check_flood_depth(coords)
  group 3 (parallel): check_amenity_flood_status(hospital_1), check_amenity_flood_status(hospital_2)
  group 4 (sequential): check_route_flood_safety(safe hospital)
  group 5 (sequential): check_vehicle_passability(ambulance, route)

OUTPUT — return ONLY valid JSON, no markdown fences:
{{
  "plan": [
    {{
      "group": 1,
      "step": 1,
      "tool": "<tool_name>",
      "purpose": "<one sentence why>",
      "input_description": "<what to pass>"
    }},
    {{
      "group": 1,
      "step": 2,
      "tool": "<tool_name>",
      "purpose": "<one sentence why>",
      "input_description": "<what to pass>"
    }},
    {{
      "group": 2,
      "step": 3,
      "tool": "<tool_name>",
      "purpose": "<one sentence why>",
      "input_description": "<what to pass>"
    }}
  ]
}}
"""
)


# ============================================================================
# UPDATED EXECUTOR PROMPT — for a single tool call within a parallel batch
# ============================================================================

EXECUTOR_PROMPT = PromptTemplate(
    input_variables=["initial_query", "tool_name", "purpose", "input_description", "previous_results"],
    template="""
You are a FLOOD DISASTER EXECUTION AGENT for Jodhpur, Rajasthan.

Original user request: {initial_query}

Results from previous tool calls (already completed):
{previous_results}

YOUR CURRENT TASK:
  Tool     : {tool_name}
  Purpose  : {purpose}
  Input hint: {input_description}

Using the previous results to resolve any arguments, call EXACTLY the tool "{tool_name}".
Do NOT call any other tool. Do NOT write a final answer — only the tool call.
"""
)

RESPONDER_PROMPT = PromptTemplate(
    input_variables=["initial_query", "tool_results"],
    template="""
You are a flood disaster response assistant for Jodhpur, Rajasthan.

The user asked: {initial_query}

All tool results collected:
{tool_results}

Using only the information above, write a clear, helpful, safety-focused final response to the user.
Highlight any flooded areas or unsafe routes. Recommend only verified-safe facilities.
"""
)
# ============================================================================
# HELPERS
# ============================================================================
TOOLS_MAP = {
    "search_amenity": search_amenity,
    "get_city_bbox": get_city_bbox,
    "get_coordinates_from_location": get_coordinates_from_location,
    "calculate_route": calculate_route,
    "check_flood_depth": check_flood_depth,
    "get_flooded_areas": get_flooded_areas,
    "check_amenity_flood_status": check_amenity_flood_status,
    "check_route_flood_safety": check_route_flood_safety,
    "check_vehicle_passability": check_vehicle_passability,
}

def _collect_tool_results(messages: list) -> str:
    parts = []
    for m in messages:
        if isinstance(m, ToolMessage):
            parts.append(f"[{m.name}]: {m.content}")
    return "\n".join(parts) if parts else "No results yet."

def _make_model(with_tools: bool = False):
    model = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=0,
        google_api_key=os.getenv("GOOGLE_API_KEY"),
    )
    return model.bind_tools(list(TOOLS_MAP.values())) if with_tools else model

def _parse_json(text: str) -> dict:
    clean = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
    return json.loads(clean)

def _get_groups(plan: list) -> list[list]:
    """
    Returns plan steps grouped by their 'group' number, ordered ascending.
    Each inner list is one batch of steps that can run in parallel.
    """
    from itertools import groupby
    sorted_plan = sorted(plan, key=lambda s: s["group"])
    return [list(steps) for _, steps in groupby(sorted_plan, key=lambda s: s["group"])]


# ============================================================================
# NODE 1 — PLANNER  (runs exactly once)
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
# SINGLE-TOOL EXECUTOR  (used inside the parallel worker)
# ============================================================================

def _execute_single_step(step: dict, initial_query: str, previous_results: str) -> list:
    """
    Asks the LLM to make exactly one tool call, runs it, and returns
    the resulting messages [AIMessage, ToolMessage].
    Runs in a thread — must be stateless.
    """
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
# NODE 2 — TOOL EXECUTOR  (runs one group per call; parallel within the group)
# ============================================================================

def tool_executor_node(state: AgentState) -> AgentState:
    plan        = state["plan"]
    group_idx   = state["current_group_index"]
    messages    = state["messages"]
    query       = state["initial_query"]

    groups = _get_groups(plan)

    if group_idx >= len(groups):
        return {**state, "current_step": "plan_exhausted"}

    current_group    = groups[group_idx]
    previous_results = _collect_tool_results(messages)
    is_parallel      = len(current_group) > 1

    print(f"\n[EXECUTOR] Group {group_idx + 1}/{len(groups)} "
          f"— {len(current_group)} tool(s) "
          f"({'parallel' if is_parallel else 'sequential'})")

    if is_parallel:
        # ── Run all steps in this group concurrently ──────────────────────
        from concurrent.futures import ThreadPoolExecutor, as_completed

        all_new_messages = []
        futures_map      = {}

        with ThreadPoolExecutor(max_workers=len(current_group)) as executor:
            for step in current_group:
                future = executor.submit(
                    _execute_single_step, step, query, previous_results
                )
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
        # ── Single step — no threading overhead ───────────────────────────
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

    chain    = RESPONDER_PROMPT | _make_model()
    response = chain.invoke({"initial_query": query, "tool_results": tool_results})

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
    if state["current_group_index"] < len(groups):
        return "continue"
    return "end"


# ============================================================================
# STATE  (updated — step_index → group_index)
# ============================================================================

class AgentState(TypedDict):
    messages:             Annotated[list, add_messages]
    initial_query:        str
    plan:                 list
    current_group_index:  int    # which GROUP the executor is on (not step)
    current_step:         str


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
        {
            "continue": "tool_executor",
            "end":      "responder",
        }
    )

    workflow.add_edge("responder", END)
    g=workflow.compile()
    png_bytes = g.draw_mermaid_png()
    with open("workflow.png", "wb") as f:
        f.write(png_bytes)
    return g


# ============================================================================
# RUNNER
# ============================================================================

def run_agent(query: str):
    agent = create_flood_agent()

    result = agent.invoke({
        "messages":            [HumanMessage(content=query)],
        "initial_query":       query,
        "plan":                [],
        "current_group_index": 0,
        "current_step":        "start",
    })

    print("\n" + "=" * 70)
    print(result["messages"][-1].content)
    groups     = _get_groups(result["plan"])
    total_steps = len(result["plan"])
    print(f"\n{total_steps} steps in {len(groups)} group(s) | "
          f"parallel batches: {sum(1 for g in groups if len(g) > 1)}")
    return result



if __name__ == "__main__":

    
    
    btp_demo_queries = [
        # Query 1: Basic but Essential - Show natural language location support
        "Is AIIMS Jodhpur flooded?",
        
        # Query 2: Core Feature - Hospital flood analysis with automatic coordinate lookup
        "Which hospitals in Jodhpur are affected by current flooding?",
        
        # Query 3: Emergency Vehicle Intelligence - Vehicle-specific passability
        "Can an ambulance reach MDM Hospital in Jodhpur?",
        
        # Query 4: Multi-Step Emergency Scenario - Complex reasoning
        "I'm at Railway Station Jodhpur and need urgent medical help. Find the nearest safe hospital and check if an ambulance can reach there.",
        
        # Query 5: Comparative Decision Support - Intelligent recommendations
        "Compare flood impact on hospitals in northern vs southern Jodhpur and recommend which area has better emergency services access.",
        
        # Query 6: Evacuation Planning - Multi-facility analysis
        "We need to evacuate patients from a flooded hospital. Find all accessible hospitals that can receive patients and check ambulance routes to each.",
        
        # Query 7: Complete Emergency Coordination - Maximum complexity
        "Emergency situation: Show all flooded areas, identify which hospitals need immediate evacuation, find safe hospitals for patient transfer, and verify which emergency vehicles can navigate the routes."
    ]
    
    
    
    
    # Select query to run (change index: 0-7)
    selected_query_index = 4 # Default: Query 1 

    print(f"\nExecuting Query {selected_query_index + 1}:")
    print(f"'{btp_demo_queries[selected_query_index]}'\n")
    print("="*80 + "\n")
    
    run_agent(btp_demo_queries[selected_query_index])
