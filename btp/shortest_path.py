import requests

def get_shortest_path_bhuvan(lat1, lon1, lat2, lon2, token):
    """
    Calls Bhuvan's Shortest Path API to get the shortest route between two points.
    
    Args:
        lat1 (float): Latitude of start point
        lon1 (float): Longitude of start point
        lat2 (float): Latitude of end point
        lon2 (float): Longitude of end point
        token (str): Your Bhuvan API token (for selected theme)
    
    Returns:
        dict: GeoJSON response containing the route
    """
    
    url = (
        "https://bhuvan-app1.nrsc.gov.in/api/routing/curl_routing_state.php"
        f"?lat1={lat1}&lon1={lon1}&lat2={lat2}&lon2={lon2}&token={token}"
    )
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    response = requests.get(url, headers=headers)
    
    # Raise an error if the API call failed
    response.raise_for_status()
    
    # The API returns GeoJSON data
    return response.json()

if __name__ == "__main__":
    # Example usage (dummy values)
    token = ""
    start = (12.9715987, 77.594566)  # e.g. Bangalore
    end = (13.035542, 77.597100)     # some other point in Bangalore region
    route = get_shortest_path_bhuvan(start[0], start[1], end[0], end[1], token)
    print(route)
