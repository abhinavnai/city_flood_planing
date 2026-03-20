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

load_dotenv()

# ============================================================================
# TOOLS DEFINITION
# ============================================================================

@tool
def search_amenity(amenity: str, city: str, state: str = "Rajasthan", country: str = "India", limit: int = 10) -> str:
    """
    Search for a    # Select query to run (change index: 0-6 for queries 1-7)
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
def get_city_bbox(city: str, state: str = "Rajasthan", country: str = "India") -> str:
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
def get_coordinates_from_location(location_name: str, city: str = "Jodhpur", state: str = "Rajasthan", country: str = "India") -> str:
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
    Calculate the shortest route between two points using Bhuvan Routing API.
    
    Args:
        start_lat: Starting point latitude
        start_lon: Starting point longitude
        end_lat: Destination point latitude
        end_lon: Destination point longitude
    
    Returns:
        Route information as a formatted string
    """
    token = ""  # Bhuvan API token
    
    url = (
        "https://bhuvan-app1.nrsc.gov.in/api/routing/curl_routing_state.php"
        f"?lat1={start_lat}&lon1={start_lon}&lat2={end_lat}&lon2={end_lon}&token={token}"
    )
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        route_data = response.json()
        
        # Extract relevant information
        if route_data and isinstance(route_data, dict):
            return f"Route calculated successfully from ({start_lat}, {start_lon}) to ({end_lat}, {end_lon}). Route data: {route_data}"
        else:
            return f"Route data received but in unexpected format: {route_data}"
    
    except Exception as e:
        return f"Error calculating route: {str(e)}"


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

# ============================================================================
# STATE
# ============================================================================

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    initial_query: str
    plan: Optional[list]          # structured plan from planner
    current_step: str
    is_satisfied: bool


# ============================================================================
# PROMPTS
# ============================================================================

PLANNER_PROMPT = PromptTemplate(
    input_variables=["initial_query", "messages"],
    template="""
You are a PLANNING AGENT for a Flood Disaster Assistance System.

Analyze the conversation history:
{messages}

User's original request:
{initial_query}

---
STEP 1 — Check if the request is already fully satisfied by previous tool results.

If YES, return EXACTLY:
{{
  "status": "satisfied",
  "reason": "<why the request is already answered>"
}}

If NO, create a step-by-step execution plan using ONLY these tools:
  1. get_coordinates_from_location  — convert place names to coordinates
  2. search_amenity                 — find hospitals, shelters, police stations, etc.
  3. check_amenity_flood_status     — check if a facility is flooded or safe
  4. check_route_flood_safety       — check if a route between two points is safe
  5. check_vehicle_passability      — check if a vehicle can pass through flood water
  6. check_flood_depth              — get flood depth at specific coordinates
  7. get_flooded_areas              — list all currently flooded zones

PLANNING RULES:
- Always resolve place names to coordinates before any geographic analysis.
- Always verify flood safety of facilities before recommending them.
- Always verify route safety before suggesting a route.
- Check vehicle passability if any vehicle is mentioned.
- Avoid redundant tool calls.
- Each step must logically build on the previous one.

Return EXACTLY:
{{
  "status": "planning_required",
  "plan": [
    {{
      "step": 1,
      "tool": "<tool_name>",
      "purpose": "<why>",
      "input": "<what to pass>",
      "expected_output": "<what the tool will return>"
    }}
  ]
}}
"""
)

EXECUTOR_PROMPT = PromptTemplate(
    input_variables=["initial_query", "messages", "plan"],
    template="""
You are a FLOOD DISASTER EXECUTION AGENT for Jodhpur, Rajasthan.

Original user request:
{initial_query}

Current conversation/tool results so far:
{messages}

Planner's step-by-step plan to follow:
{plan}

---
EXECUTION RULES:

1. Follow the plan in order. Execute only the NEXT uncompleted step.
2. Do NOT skip steps or jump ahead.
3. After each tool call, the results will be fed back for the next iteration.
4. Do NOT answer the user directly — only make the required tool calls.

AVAILABLE TOOLS:
- get_coordinates_from_location
- search_amenity
- check_amenity_flood_status
- check_route_flood_safety
- check_vehicle_passability
- check_flood_depth
- get_flooded_areas

Now execute the next required tool call from the plan.
"""
)


# ============================================================================
# NODES
# ============================================================================

def planner_node(state: AgentState) -> AgentState:
    """
    Checks if the user's request is satisfied.
    If not, creates a structured plan and stores it in state.
    """
    messages   = state["messages"]
    query      = state["initial_query"]

    model = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=0,
        google_api_key=os.getenv("GOOGLE_API_KEY")
    )

    chain    = PLANNER_PROMPT | model
    response = chain.invoke({"initial_query": query, "messages": messages})

    # Parse JSON from the model response
    try:
        raw  = response.content.strip()
        # strip markdown fences if present
        raw  = re.sub(r"```(?:json)?", "", raw).strip().rstrip("```").strip()
        data = json.loads(raw)
    except (json.JSONDecodeError, AttributeError):
        data = {"status": "planning_required", "plan": []}

    is_satisfied = data.get("status") == "satisfied"
    plan         = data.get("plan", [])
#helper function to print the plan in a readable format
    print(f"\n[PLANNER] Status: {'SATISFIED ✓' if is_satisfied else 'PLANNING REQUIRED'}")
    if not is_satisfied:
        for step in plan:
            print(f"  Step {step['step']}: {step['tool']} — {step['purpose']}")

    return {
        **state,
        "messages":     messages + [response],
        "plan":         plan,
        "is_satisfied": is_satisfied,
        "current_step": "planner_done",
    }


def tool_executor_node(state: AgentState) -> AgentState:
    """
    Validates the plan and invokes the LLM with tools bound,
    so the LLM can select and call the correct tool for the current step.
    """
    messages = state["messages"]
    query    = state["initial_query"]
    plan     = state.get("plan", [])

    model = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=0,
        google_api_key=os.getenv("GOOGLE_API_KEY")
    )

    tools_list = [
        search_amenity,
        get_city_bbox,
        get_coordinates_from_location,
        calculate_route,
        check_flood_depth,
        get_flooded_areas,
        check_amenity_flood_status,
        check_route_flood_safety,
        check_vehicle_passability,
    ]
    model_with_tools = model.bind_tools(tools_list)

    # Build the executor prompt
    prompt_text = EXECUTOR_PROMPT.format(
        initial_query=query,
        messages=messages,
        plan=json.dumps(plan, indent=2),
    )

    print("\n[EXECUTOR] Selecting next tool from plan...")
    response = model_with_tools.invoke([HumanMessage(content=prompt_text)])

    if hasattr(response, "tool_calls") and response.tool_calls:
        print(f"[EXECUTOR] Calling {len(response.tool_calls)} tool(s):")
        for tc in response.tool_calls:
            args_preview = ", ".join(
                f"{k}={str(v)[:40]}" for k, v in list(tc.get("args", {}).items())[:2]
            )
            print(f"  → {tc['name']}({args_preview})")
    else:
        print("[EXECUTOR] No tool calls generated.")

    return {
        **state,
        "messages":     messages + [response],
        "current_step": "executor_done",
    }


def tool_caller_node(state: AgentState) -> AgentState:
    """
    Executes every pending tool call in the last message
    and appends ToolMessage results back into state.
    """
    messages     = state["messages"]
    last_message = messages[-1]

    if not (hasattr(last_message, "tool_calls") and last_message.tool_calls):
        return {**state, "current_step": "no_tools"}

    tools_map = {
        "search_amenity":              search_amenity,
        "get_city_bbox":               get_city_bbox,
        "get_coordinates_from_location": get_coordinates_from_location,
        "calculate_route":             calculate_route,
        "check_flood_depth":           check_flood_depth,
        "get_flooded_areas":           get_flooded_areas,
        "check_amenity_flood_status":  check_amenity_flood_status,
        "check_route_flood_safety":    check_route_flood_safety,
        "check_vehicle_passability":   check_vehicle_passability,
    }

    print("\n[TOOL CALLER] Executing tools...")
    tool_messages = []

    for idx, tc in enumerate(last_message.tool_calls, 1):
        name    = tc["name"]
        args    = tc["args"]
        call_id = tc["id"]

        print(f"  [{idx}] {name}")
        if name in tools_map:
            try:
                result = tools_map[name].invoke(args)
                status = "SUCCESS ✓"
            except Exception as e:
                result = f"Error: {e}"
                status = f"FAILED ✗ — {str(e)[:80]}"
            print(f"      {status}")
            tool_messages.append(
                ToolMessage(content=str(result), tool_call_id=call_id, name=name)
            )
        else:
            print(f"      UNKNOWN TOOL")
            tool_messages.append(
                ToolMessage(
                    content=f"Unknown tool: {name}",
                    tool_call_id=call_id,
                    name=name,
                )
            )

    print(f"[TOOL CALLER] Completed {len(tool_messages)} tool(s).")

    return {
        **state,
        "messages":     messages + tool_messages,
        "current_step": "tools_called",
    }


# ============================================================================
# CONDITIONAL EDGE
# ============================================================================

def should_continue_or_end(state: AgentState) -> str:
    """
    After tools execute, route back to planner for another cycle,
    OR end if the planner already marked the request as satisfied.
    """
    if state.get("is_satisfied"):
        print("\n[ROUTER] Request satisfied → END")
        return "end"

    print("\n[ROUTER] More steps needed → back to PLANNER")
    return "re_plan"


# ============================================================================
# GRAPH
# ============================================================================

def create_flood_agent():
    workflow = StateGraph(AgentState)

    # Nodes
    workflow.add_node("planner",      planner_node)
    workflow.add_node("tool_executor", tool_executor_node)
    workflow.add_node("tool_caller",  tool_caller_node)

    # Entry point
    workflow.set_entry_point("planner")

    # Fixed edges
    workflow.add_edge("planner",       "tool_executor")   # planner → executor
    workflow.add_edge("tool_executor", "tool_caller")     # executor → caller

    # Conditional edge back to planner or END
    workflow.add_conditional_edges(
        "tool_caller",
        should_continue_or_end,
        {
            "re_plan": "planner",   # loop: tool_caller → planner
            "end":     END,
        }
    )

    return workflow.compile()


# ============================================================================
# RUNNER
# ============================================================================

def run_agent(query: str):
    if not os.getenv("GOOGLE_API_KEY"):
        print("Error: GOOGLE_API_KEY not set.")
        return

    agent = create_flood_agent()

    initial_state: AgentState = {
        "messages":     [HumanMessage(content=query)],
        "initial_query": query,
        "plan":         [],
        "current_step": "start",
        "is_satisfied": False,
    }

    print("=" * 70)
    print(f"QUERY: {query}")
    print("=" * 70)

    result = agent.invoke(initial_state)

    final = result["messages"][-1]
    print("\n" + "=" * 70)
    print("FINAL RESPONSE:")
    print("=" * 70)
    print(final.content)

    total_tool_calls = sum(
        1 for m in result["messages"]
        if hasattr(m, "tool_calls") and m.tool_calls
    )
    print(f"\nSUMMARY — Tool call rounds: {total_tool_calls} | "
          f"Total messages: {len(result['messages'])}")
    print("=" * 70)

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
