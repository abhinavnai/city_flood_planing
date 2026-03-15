import requests
import time

def search_location(amenity=None, city=None, county=None, state=None, country=None, limit=5):
    url = "https://nominatim.openstreetmap.org/search"
    
    # Build query string - Nominatim works better with free-form queries for amenities
    query_parts = []
    if amenity:
        query_parts.append(amenity)
    if city:
        query_parts.append(city)
    if county:
        query_parts.append(county)
    if state:
        query_parts.append(state)
    if country:
        query_parts.append(country)
    
    query_string = ", ".join(query_parts)
    
    # Build query parameters
    params = {
        "q": query_string,  # Free-form query
        "format": "json",
        "addressdetails": 1,
        "limit": limit
    }

    headers = {
         "User-Agent": "FloodHelpAgent-BTP-2025/1.0 (+https://github.com/yourrepo)"
    }

    # Add delay to respect rate limits (1 request per second)
    time.sleep(1)
    
    response = requests.get(url, params=params, headers=headers)
    print("Request URL:", response.url)  # Print URL for debugging
    if response.status_code != 200:
        print("Error:", response.status_code)
        print("Response:", response.text[:200])  # Print first 200 chars
        return None

    data = response.json()
    if not data:
        print("No results found.")
        return None

    # Print neatly
    for place in data:
        print("Name:", place.get("display_name"))
        print("Latitude:", place.get("lat"))
        print("Longitude:", place.get("lon"))
        print("-" * 60)

    return data


# Example: Search for hospitals in Jodhpur, Rajasthan, India
if __name__ == "__main__":
    search_location(
        amenity="school",  # Fixed: singular form
        city="Jodhpur",
        state="Rajasthan",
        country="India",
        limit=20
    )
