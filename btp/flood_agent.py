import os
from typing import TypedDict, Annotated, Sequence
import operator
from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.tools import tool
import requests
import time
from flood_data_simulator import flood_simulator
from dotenv import load_dotenv

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
# STATE DEFINITION
# ============================================================================

class AgentState(TypedDict):
    """State of the agent."""
    messages: Annotated[Sequence[BaseMessage], operator.add]
    current_step: str


# ============================================================================
# AGENT NODES
# ============================================================================

def call_model(state: AgentState):
    """Node that calls the LLM with available tools."""
    messages = state["messages"]
    
    # Add system instruction to guide the model
    system_message = HumanMessage(content="""You are a flood disaster management assistant for Jodhpur, Rajasthan.

 CRITICAL MULTI-STEP WORKFLOW RULES - YOU MUST FOLLOW THESE:

1. NEVER provide a final answer after calling just ONE tool!
2. For emergency/medical queries, you MUST call AT LEAST 3-4 tools before answering

MANDATORY WORKFLOW FOR "need medical help" OR "find nearest hospital" queries:
   Step 1: Call get_coordinates_from_location (user's location)
   Step 2: Call search_amenity (find hospitals)  
   Step 3: Call check_amenity_flood_status (check which are safe)
   Step 4: Call check_route_flood_safety (verify routes to safe ones)
   Step 5: ONLY THEN provide final answer

RULES:
- When users mention location names, ALWAYS use get_coordinates_from_location FIRST
- After getting coordinates, IMMEDIATELY call the next tool - DO NOT STOP
- Complete ALL necessary steps (typically 3-5 tools) before final response
- Never ask users for coordinates - look them up automatically

Available tools:
- get_coordinates_from_location: Convert place names to coordinates
- search_amenity: Find facilities (hospitals, police, etc.)
- check_amenity_flood_status: Check flood safety of facilities
- check_route_flood_safety: Verify route safety between locations
- check_vehicle_passability: Check if specific vehicles can pass
- check_flood_depth: Get flood depth at coordinates
- get_flooded_areas: List all flooded zones

Remember: Getting coordinates is just step 1. You must continue with more tools!""")
    
    # Prepend system message if not already present
    if not messages or messages[0].content != system_message.content:
        messages = [system_message] + list(messages)
    
        # Initialize Gemini model with tools
    model = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",  # Latest experimental model with better reasoning
        temperature=0,
        google_api_key=''
    )
    
    # Bind tools to model
    tools = [
        search_amenity, 
        get_city_bbox,
        get_coordinates_from_location,  # NEW: Convert place names to coordinates
        calculate_route,
        check_flood_depth,
        get_flooded_areas,
        check_amenity_flood_status,
        check_route_flood_safety,
        check_vehicle_passability
    ]
    model_with_tools = model.bind_tools(tools)
    
    # Call model
    print("\n[AGENT] Analyzing query and selecting appropriate tools...")
    response = model_with_tools.invoke(messages)
    
    # Show which tools were selected
    if hasattr(response, "tool_calls") and response.tool_calls:
        print(f"[AGENT] Selected {len(response.tool_calls)} tool(s) for execution:")
        for idx, tool_call in enumerate(response.tool_calls, 1):
            tool_name = tool_call["name"]
            tool_args = tool_call.get("args", {})
            print(f"        {idx}. {tool_name}({', '.join(f'{k}={v}' for k, v in list(tool_args.items())[:2])}...)")
    
    return {"messages": [response], "current_step": "model_called"}


def execute_tools(state: AgentState):
    """Node that executes tool calls from the model."""
    messages = state["messages"]
    last_message = messages[-1]
    
    # Check if there are tool calls
    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        return {"messages": [], "current_step": "no_tools"}
    
    print("\n[TOOLS] Executing selected tools...")
    
    # Map tool names to actual functions
    tools_map = {
        "search_amenity": search_amenity,
        "get_city_bbox": get_city_bbox,
        "get_coordinates_from_location": get_coordinates_from_location,  # NEW
        "calculate_route": calculate_route,
        "check_flood_depth": check_flood_depth,
        "get_flooded_areas": get_flooded_areas,
        "check_amenity_flood_status": check_amenity_flood_status,
        "check_route_flood_safety": check_route_flood_safety,
        "check_vehicle_passability": check_vehicle_passability
    }
    
    # Execute each tool call
    tool_messages = []
    for idx, tool_call in enumerate(last_message.tool_calls, 1):
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        tool_id = tool_call["id"]
        
        # Print tool execution
        print(f"\n        [{idx}] Executing: {tool_name}")
        if tool_args:
            for key, value in tool_args.items():
                # Truncate long values for readability
                display_value = str(value)[:50] + "..." if len(str(value)) > 50 else value
                print(f"            - {key}: {display_value}")
        
        if tool_name in tools_map:
            tool_func = tools_map[tool_name]
            try:
                print(f"            Status: Processing...")
                result = tool_func.invoke(tool_args)
                print(f"            Status: SUCCESS")
                tool_messages.append(
                    ToolMessage(
                        content=str(result),
                        tool_call_id=tool_id,
                        name=tool_name
                    )
                )
            except Exception as e:
                print(f"            Status: FAILED - {str(e)[:100]}")
                tool_messages.append(
                    ToolMessage(
                        content=f"Error executing {tool_name}: {str(e)}",
                        tool_call_id=tool_id,
                        name=tool_name
                    )
                )
    
    print(f"\n[TOOLS] Completed execution of {len(tool_messages)} tool(s)")
    
    return {"messages": tool_messages, "current_step": "tools_executed"}


def should_continue(state: AgentState):
    """Determine if we should continue to tools or end."""
    messages = state["messages"]
    last_message = messages[-1]
    
    # If there are tool calls, continue to tools
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        print("\n[AGENT] Additional information required, continuing iteration...")
        return "continue"
    
    # Otherwise, end
    print("\n[AGENT] Sufficient information gathered, generating final response...")
    return "end"


# 
# GRAPH CONSTRUCTION
# 

def create_flood_agent():
    """Create and compile the flood help agent graph."""
    
    # Create the graph
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", execute_tools)
    
    # Set entry point
    workflow.set_entry_point("agent")
    
    # Add conditional edges
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "continue": "tools",
            "end": END
        }
    )
    
    # Add edge from tools back to agent
    workflow.add_edge("tools", "agent")
    
    # Compile the graph
    app = workflow.compile()
    
    return app


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def run_agent(query: str):
    """Run the flood agent with a user query."""
    
    # Check for API key
    if not os.getenv("GOOGLE_API_KEY"):
        print("Error: GOOGLE_API_KEY environment variable not set!")
        print("Please set it using: export GOOGLE_API_KEY='your-api-key'")
        return
    

    agent = create_flood_agent()
    
    # Initialize state
    initial_state = {
        "messages": [HumanMessage(content=query)],
        "current_step": "start"
    }
    
    print("="*70)
    print("USER QUERY:")
    print("="*70)
    print(f"{query}\n")
    
    print("="*70)
    print("AGENT EXECUTION TRACE:")
    print("="*70)
    
    # Run agent
    result = agent.invoke(initial_state)
    
    # Print final response
    final_message = result["messages"][-1]
    print("\n" + "="*70)
    print("FINAL RESPONSE:")
    print("="*70)
    print(final_message.content)
    print("="*70 + "\n")
    
    # Show execution summary
    tool_calls_count = sum(1 for msg in result["messages"] if hasattr(msg, "tool_calls") and msg.tool_calls)
    print("EXECUTION SUMMARY:")
    print(f"  - Agent Iterations: {tool_calls_count}")
    print(f"  - Total Messages Exchanged: {len(result['messages'])}")
    print(f"  - Execution Status: COMPLETED")
    print("="*70 + "\n")
    
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
    selected_query_index = 1  # Default: Query 1 

    print(f"\nExecuting Query {selected_query_index + 1}:")
    print(f"'{btp_demo_queries[selected_query_index]}'\n")
    print("="*80 + "\n")
    
    run_agent(btp_demo_queries[selected_query_index])
