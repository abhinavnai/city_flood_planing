# Flood Help Agent - Prototype

A LangGraph-based AI agent for flood disaster management in Jodhpur, Rajasthan. This prototype demonstrates how AI can help answer critical questions about flood impacts on infrastructure, accessibility, and emergency services.

## 🎯 Purpose

This agent assists in flood disaster management by:
- Finding hospitals, schools, and emergency services in flood-affected areas
- Checking which facilities are accessible or cut off due to flooding
- Analyzing route safety through flooded regions
- Determining vehicle passability in flood conditions
- Providing real-time flood depth information

## 🏗️ Architecture

The system uses **LangGraph** to orchestrate multiple tools with **Google Gemini** LLM:

```
User Query → Gemini LLM → Tool Selection → Tool Execution → Synthesized Response
                ↑                                   ↓
                └──────── Feedback Loop ────────────┘
```

**Key Components:**
1. **LangGraph**: Orchestrates the agent workflow
2. **Gemini AI**: Understands queries and decides which tools to use
3. **Tools**: Execute specific tasks (search, check floods, analyze routes)
4. **Flood Simulator**: Generates realistic test data for prototype

## 📦 Installation

### 1. Activate Virtual Environment

```bash
cd /Users/mayankbansal/Desktop/btp
source btp/bin/activate
```

### 2. Install Dependencies

```bash
pip install langgraph langchain langchain-google-genai langchain-core requests pillow
```

### 3. Set Google API Key

Get your API key from [Google AI Studio](https://makersuite.google.com/app/apikey)

```bash
# For current session
export GOOGLE_API_KEY='your-gemini-api-key-here'

# Or add to ~/.zshrc for permanent use
echo 'export GOOGLE_API_KEY="your-key-here"' >> ~/.zshrc
source ~/.zshrc
```

## 🚀 Quick Start

### Run the Agent

```bash
python flood_agent.py
```

### Test the Flood Simulator

```bash
python flood_data_simulator.py
```

### Test Geocoding Feature (NEW!)

```bash
python test_geocoding.py
python demo_geocoding_comparison.py
```

## 🆕 NEW FEATURE: Natural Language Location Support!

**You no longer need coordinates!** The agent now understands location names.

### Before:
```
"Is the location at 26.2414, 73.0039 flooded?"
```

### After (NEW):
```
"Is AIIMS Jodhpur flooded?"
"Can ambulance reach Railway Station?"
"Route safety from Clock Tower to Mehrangarh Fort?"
```

**Supported locations:** Hospitals, railway stations, airports, landmarks, schools, and any named place in Jodhpur!

📖 **Full documentation:** See [GEOCODING_FEATURE.md](GEOCODING_FEATURE.md)

## 💬 Example Queries

### 1. Finding Facilities
```
"Find hospitals in Jodhpur"
"Show me all pharmacies in Jodhpur"
"List schools in Jodhpur"
```

### 2. Flood Impact Analysis (with location names! ⭐ NEW)
```
"Which hospitals in Jodhpur are affected by current flooding?"
"Is AIIMS Jodhpur flooded?"  ⭐ NEW
"Are there any flooded areas in Jodhpur right now?"
"Show me schools that are inaccessible due to flooding"
"Check flood status at Railway Station"  ⭐ NEW
"Which pharmacies can I access during this flood?"
```

### 3. Route Safety (now with place names! ⭐ NEW)
```
"Is the route from 26.2389, 73.0243 to 26.2971, 73.0489 safe?"
"Check if the path between these coordinates passes through floods"
"Is it safe to go from Railway Station to Clock Tower?"  ⭐ NEW
"Route safety from AIIMS to Umaid Bhawan Palace?"  ⭐ NEW
```

### 4. Vehicle Assessment (location names supported! ⭐ NEW)
```
"Can an ambulance pass through coordinates 26.2389, 73.0243?"
"Is this location safe for a car at 26.2650, 73.0300?"
"Can a truck navigate through 26.2389, 73.0243?"
"Can ambulance reach AIIMS Hospital?"  ⭐ NEW
"Is MDM Hospital accessible by car?"  ⭐ NEW
```

### 5. Specific Location Data (coordinates OR names! ⭐ NEW)
```
"What is the flood depth at 26.2650, 73.0300?"
"Check flood status at coordinates 26.2389, 73.0243"
"Find coordinates of Clock Tower Jodhpur"  ⭐ NEW
"Where is Mehrangarh Fort located?"  ⭐ NEW
"Show me all currently flooded areas"
```

## 🛠️ Available Tools

### 1. **search_amenity**
Search for facilities using OpenStreetMap
- **Use**: "Find hospitals in Jodhpur"
- **Returns**: List with names, coordinates, addresses

### 2. **check_flood_depth**
Get flood depth at specific coordinates
- **Use**: "What's the flood depth at 26.2389, 73.0243?"
- **Returns**: Depth in meters, safety status, severity

### 3. **get_flooded_areas**
List all currently flooded zones
- **Use**: "Show me all flooded areas"
- **Returns**: Locations, depth, severity, affected radius

### 4. **check_amenity_flood_status**
Analyze which facilities are flooded vs. accessible
- **Use**: "Which hospitals are flooded?"
- **Returns**: Affected vs. safe facilities with locations

### 5. **check_route_flood_safety**
Verify if a route passes through floods
- **Use**: "Is this route safe from flooding?"
- **Returns**: Safety status, flooded checkpoints, recommendations

### 6. **check_vehicle_passability**
Check if vehicles can pass through locations
- **Use**: "Can an ambulance pass through here?"
- **Returns**: Passability for car/ambulance/truck/boat

### 7. **get_city_bbox**
Get bounding box for mapping
- **Use**: "Get Jodhpur city boundaries"
- **Returns**: Min/max latitude and longitude

### 8. **calculate_route**
Calculate shortest path (Bhuvan API)
- **Use**: "Find route from A to B"
- **Returns**: Route information

## 📁 File Structure

```
btp/
├── flood_agent.py              # Main LangGraph agent with tools
├── flood_data_simulator.py     # Simulates flood data for testing
├── aminity.py                  # OpenStreetMap amenity search
├── shortest_path.py            # Bhuvan routing integration
├── flood.py                    # Flood WMS data fetching
├── README.md                   # This file
└── btp/                        # Virtual environment
    ├── bin/
    ├── lib/
    └── ...
```

## 🧪 Flood Data Simulation

Since real-time flood APIs require active flood events and authentication, we created a **realistic simulator** for prototype testing.

### Simulated Features:
- **5 flood zones** around Jodhpur (near Luni River)
- **Depth range**: 0 to 2.5 meters
- **Severity levels**: 
  - High: > 2.0m (evacuation recommended)
  - Medium: > 1.0m (avoid if possible)
  - Low: > 0.3m (proceed with caution)
- **Vehicle limits**:
  - Car: 0.3m max depth
  - Ambulance: 0.5m max depth
  - Truck: 0.7m max depth
  - Boat: No limit

### Why Simulated Data?

✅ Works anytime for demos  
✅ Predictable and reproducible  
✅ Demonstrates all capabilities  
✅ Can be replaced with real API when available  
✅ No dependency on active disasters  

### Replacing with Real Data

When real Bhuvan flood API is accessible, update `flood_data_simulator.py`:

```python
def get_flood_depth(lat, lon):
    # Replace with actual Bhuvan WMS API call
    response = requests.get(BHUVAN_WMS_URL, params={...})
    # Parse raster data at coordinates
    return actual_flood_depth
```

## 📊 Example Output

```
============================================================
Query: Which hospitals in Jodhpur are affected by flooding?
============================================================

[Agent uses tools: search_amenity → check_amenity_flood_status]

============================================================
Agent Response:
============================================================
Flood Impact Analysis for Hospitals in Jodhpur:

Total hospitals analyzed: 12
✓ Safe/Accessible: 8
✗ Affected/Flooded: 4

AFFECTED HOSPITALS (unreachable/flooded):
  ✗ Government Hospital, Jodhpur
    Flood depth: 1.8m at (26.2389, 73.0243)
  ✗ City Medical Center
    Flood depth: 2.1m at (26.2650, 73.0300)
  
SAFE/ACCESSIBLE HOSPITALS:
  ✓ AIIMS Jodhpur
    Location: (26.4650, 73.1040)
  ✓ MG Hospital
    Location: (26.2800, 73.0650)
  ... and 6 more
============================================================
```

## 🎓 For Your Presentation

### Key Points to Highlight:

1. **Intelligent Tool Selection**
   - Agent automatically decides which tools to use
   - Can chain multiple tools for complex queries
   - No manual programming for each query type

2. **Natural Language Interface**
   - Professors can ask questions naturally
   - No need to know API parameters
   - Context-aware responses

3. **Practical Applications**
   - Emergency response coordination
   - Evacuation planning
   - Resource allocation
   - Public communication

4. **Extensibility**
   - Easy to add new tools (evacuation centers, shelter capacity)
   - Can integrate real APIs when available
   - RAG for historical analysis (future)

### Demo Flow:

1. **Start Simple**: "Find hospitals in Jodhpur"
2. **Add Complexity**: "Which hospitals are flooded?"
3. **Route Analysis**: "Is this route safe?"
4. **Vehicle Check**: "Can ambulances reach there?"
5. **Show Architecture**: Explain LangGraph workflow

## ⚙️ Configuration

You can modify these in the code:

### flood_agent.py
```python
# Line 157: Change Gemini model
model = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash-exp",  # or gemini-pro
    temperature=0
)

# Line 284: Change example queries
queries = [
    "Your custom query here",
    # ...
]
```

### flood_data_simulator.py
```python
# Line 17: Adjust flood zones
FLOOD_ZONES = [
    {"center": (lat, lon), "radius": 0.02, "base_depth": 2.5},
    # Add more zones
]

# Line 70: Change severity thresholds
threshold = 0.5  # meters
```

## ⚠️ Known Limitations

1. **Simulated Data**: Flood data is simulated (intentional for prototype)
2. **OSM Coverage**: Some facilities may not be in OpenStreetMap
3. **API Rate Limits**: Nominatim has request limits
4. **Network Required**: All APIs need internet connection
5. **Gemini Quota**: API calls consume your quota

## 🔮 Future Enhancements

### Short-term:
- [ ] Add more amenity types (evacuation centers, relief camps)
- [ ] Implement shelter capacity tracking
- [ ] Add population density overlays
- [ ] Generate evacuation priority lists

### Long-term:
- [ ] Integrate real Bhuvan flood raster API
- [ ] Add RAG with Pinecone for historical data
- [ ] Implement automated alert generation
- [ ] Create web interface for officials
- [ ] Add predictive flood modeling

## 🐛 Troubleshooting

### Issue: "GOOGLE_API_KEY not set"
```bash
export GOOGLE_API_KEY='your-actual-key'
python flood_agent.py
```

### Issue: "No results found" for amenities
- OpenStreetMap may not have that amenity type in that city
- Try variations: "hospital" vs "clinic"
- Check if city name is spelled correctly

### Issue: "Module not found"
```bash
source btp/bin/activate
pip install langgraph langchain langchain-google-genai
```

### Issue: Rate limiting errors
- Wait 1-2 seconds between requests
- Reduce `limit` parameter in search_amenity

### Issue: "Connection timeout"
- Check internet connection
- Some APIs may be temporarily down
- Try again after a few seconds

## 📚 Resources

- **LangGraph**: https://python.langchain.com/docs/langgraph
- **Gemini API**: https://ai.google.dev/docs
- **OpenStreetMap**: https://nominatim.org/release-docs/develop/api/Overview/
- **Bhuvan Portal**: https://bhuvan.nrsc.gov.in/
- **LangChain**: https://python.langchain.com/docs/get_started/introduction

## 👥 Team

**Project**: B.Tech Flood Disaster Management Agent  
**Institution**: [Your University]  
**Year**: 2025

## 📄 License

Educational/Research Project

---

**Built with:** LangGraph • Google Gemini • OpenStreetMap • Python  
**Purpose:** Flood Disaster Management Prototype Demonstration

**Status:** ✅ Ready for Prototype Demo
