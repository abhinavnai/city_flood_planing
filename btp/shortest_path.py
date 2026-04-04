from numpy import place
import requests
import osmnx as ox
import networkx as nx
import geopandas as gpd
from shapely.geometry import LineString
import folium
import sklearn
vechile_config = {
    "car": {
        "speed": 15,          # km/h
        "flood_tolerance": 0.3,
        "flood_penalty_factor": 20
    }
}


def yen_k_shortest(G, G_simple, vehicle, vehicle_config, source, target, k, weight="weight"):
    """Yen's K-shortest simple paths — only computes what you need."""
    import heapq
    from itertools import count

    try:
        first = nx.dijkstra_path(G, source, target, weight=weight)
    except nx.NetworkXNoPath:
        return []

    A = [first]
    B = []
    counter = count()

    for _ in range(1, k):
        prev = A[-1]
        for i in range(len(prev) - 1):
            spur_node = prev[i]
            root_path = prev[:i + 1]
            removed_edges = []

            # Remove edges used by existing k-shortest paths with same root
            for path in A:
                if path[:i + 1] == root_path and i + 1 < len(path):
                    u, v = path[i], path[i + 1]
                    if G.has_edge(u, v):
                        data = G[u][v]
                        G.remove_edge(u, v)
                        removed_edges.append((u, v, data))

            # Remove root nodes except spur node
            removed_nodes = {}
            for node in root_path[:-1]:
                removed_nodes[node] = dict(G[node])
                for v in list(G.successors(node)):
                    edge_data = G[node][v]
                    removed_edges.append((node, v, edge_data))
                    G.remove_edge(node, v)

            try:
                spur_path = nx.dijkstra_path(G, spur_node, target, weight=weight)
                total_path = root_path[:-1] + spur_path
                cost = sum(
                    G_simple[u][v].get(weight, 1)
                    for u, v in zip(total_path[:-1], total_path[1:])
                    if G_simple.has_edge(u, v)
                )
                heapq.heappush(B, (cost, next(counter), total_path))
            except nx.NetworkXNoPath:
                pass

            # Restore edges and nodes
            for u, v, data in removed_edges:
                G.add_edge(u, v, **data)

        if not B:
            break
        _, _, next_path = heapq.heappop(B)
        # Deduplicate
        while B and next_path in A:
            _, _, next_path = heapq.heappop(B)
        A.append(next_path)

    return A


def compute_edge_weight(edge, vehicle):
    distance = edge.get("length", 1)
    speed = vehicle["speed"]
    time_cost = distance / speed
    flood_level = edge.get("flood_level", 0)

    if flood_level > vehicle["flood_tolerance"]:
        return 1e9  # avoid completely

    flood_penalty = flood_level * vehicle["flood_penalty_factor"]

    road_type = edge.get("highway", "residential")
    if isinstance(road_type, list):
        road_type = road_type[0]

    road_factor_map = {
        "motorway": 0.8,
        "primary": 1.0,
        "secondary": 1.2,
        "tertiary": 1.3,
        "residential": 1.5,
        "service": 1.8
    }
    road_factor = road_factor_map.get(road_type, 1.5)

    return (time_cost * road_factor) + flood_penalty


def get_shortest_path(
    lat1, lon1, lat2, lon2,
    token,
    place="Gujrat,Pakistan",
    file_name=r"E:\EMSR838_products\EMSR838_AOI01_DEL_PRODUCT_v1\EMSR838_AOI01_DEL_PRODUCT_floodDepthA_v1.shp",
    k=3,
    vehicle_type="car",
    vehicle_config=vechile_config
):
    G = ox.graph_from_place(place, network_type="drive")
    flood_data = gpd.read_file(file_name)
    nodes_gdf, edges_gdf = ox.graph_to_gdfs(G, nodes=True, edges=True)
    flood_data = flood_data.to_crs(edges_gdf.crs)

    
    edges_gdf = gpd.sjoin(
        edges_gdf,
        flood_data[["geometry"]],
        how="left",
        predicate="intersects"
    )

    # Derive flood_level: use existing column or binary presence flag
    if "flood_level" in edges_gdf.columns:
        edges_gdf["flood_level"] = edges_gdf["flood_level"].fillna(0)
    else:
        edges_gdf["flood_level"] = edges_gdf["index_right"].notnull().astype(float)

    # Collapse duplicate rows from the spatial join; keep max flood per edge
    agg_dict = {col: "first" for col in edges_gdf.columns if col != "flood_level"}
    agg_dict["flood_level"] = "max"
    edges_gdf = edges_gdf.groupby(level=[0, 1, 2]).agg(agg_dict)

    # ── 4. Write flood_level back into the graph ──────────────────────────────
    for (u, v, key), row in edges_gdf.iterrows():
        if key in G[u][v]:
            G[u][v][key]["flood_level"] = row["flood_level"]

    # ── 5. Compute edge weights ───────────────────────────────────────────────
    vehicle = vehicle_config[vehicle_type]

    for u, v, key, data in G.edges(keys=True, data=True):
        data["weight"] = compute_edge_weight(data, vehicle)

    edges_gdf["weight"] = edges_gdf.apply(
        lambda row: compute_edge_weight(row, vehicle), axis=1
    )

    # ── 6. Snap start / end coordinates to nearest graph nodes ───────────────
    orig = ox.distance.nearest_nodes(G, lon1, lat1)   # note: osmnx expects (lon, lat)
    dest = ox.distance.nearest_nodes(G, lon2, lat2)

    # ── 7. Build a simple DiGraph (keep best edge between each node pair) ─────
    G_simple = nx.DiGraph()
    for u, v, data in G.edges(data=True):
        weight = data.get("weight", 1)
        if G_simple.has_edge(u, v):
            if weight < G_simple[u][v]["weight"]:
                G_simple[u][v].update(data)
        else:
            G_simple.add_edge(u, v, **data)

    # Copy node positions so visualise_routes can use G.nodes[n]["x"/"y"]
    for node, attrs in G.nodes(data=True):
        if node in G_simple.nodes:
            G_simple.nodes[node].update(attrs)

    # ── 8. Find K shortest paths ──────────────────────────────────────────────
    routes = yen_k_shortest(
        G_simple, G_simple,          # pass G_simple for both working copy & reference
        vehicle, vehicle_config,
        orig, dest,
        k=k,
        weight="weight"
    )

    if not routes:
        print("No routes found between the given coordinates.")
        return None, None, None

    # ── 9. Print route summaries ──────────────────────────────────────────────
    for i, route in enumerate(routes):
        length = sum(
            G_simple[u][v].get("length", 0)
            for u, v in zip(route[:-1], route[1:])
            if G_simple.has_edge(u, v)
        )
        flooded = sum(
            1 for u, v in zip(route[:-1], route[1:])
            if G_simple.has_edge(u, v) and G_simple[u][v].get("flood_level", 0) > 0
        )
        print(f"Route {i + 1}: {length:.0f} m, {len(route)} nodes, {flooded} flooded segments")

    return routes, G, G_simple


def visualize_routes(G, G_simple, vehicle, vehicle_config, edges_gdf, routes, flood_data):
    centroid = flood_data.geometry.unary_union.centroid
    m = folium.Map(location=[centroid.y, centroid.x], zoom_start=14)

    # ── Road edges layer ──────────────────────────────────────────────────────
    road_layer = folium.FeatureGroup(name="Road network", show=True)
    for (u, v, k_idx), row in edges_gdf.iterrows():
        geom = row.geometry
        if geom is None:
            continue
        lines = geom.geoms if geom.geom_type == "MultiLineString" else [geom]
        for line in lines:
            coords = [(lat, lon) for lon, lat in line.coords]
            flood = row.get("flood_level", 0)
            if flood > vehicle["flood_tolerance"]:
                color, w, op = "red", 4, 0.9
            elif flood > 0:
                color, w, op = "orange", 3, 0.8
            else:
                color, w, op = "green", 1, 0.5
            folium.PolyLine(
                coords, color=color, weight=w, opacity=op,
                tooltip=f"Flood: {flood:.2f} | Road: {row.get('highway', 'N/A')}"
            ).add_to(road_layer)
    road_layer.add_to(m)

    # ── Flood polygon layer ───────────────────────────────────────────────────
    flood_layer = folium.FeatureGroup(name="Flood zones", show=True)
    folium.GeoJson(
        flood_data,
        style_function=lambda x: {
            "color": "blue",
            "fillColor": "blue",
            "fillOpacity": 0.25,
            "weight": 1
        }
    ).add_to(flood_layer)
    flood_layer.add_to(m)

    # ── Route layers ──────────────────────────────────────────────────────────
    route_styles = [
        {"color": "#9B30FF", "weight": 7, "opacity": 1.0,  "dash_array": None,  "label": "Route 1 (Best)"},
        {"color": "#FF6600", "weight": 6, "opacity": 0.95, "dash_array": "10 6", "label": "Route 2 (Alt)"},
        {"color": "#000000", "weight": 5, "opacity": 0.85, "dash_array": "4 4",  "label": "Route 3 (Alt)"},
    ]

    for i, route in enumerate(routes):
        style = route_styles[i % len(route_styles)]

        route_length = sum(
            G_simple[u][v].get("length", 0)
            for u, v in zip(route[:-1], route[1:])
            if G_simple.has_edge(u, v)
        )
        flooded_edges_count = sum(
            1 for u, v in zip(route[:-1], route[1:])
            if G_simple.has_edge(u, v) and G_simple[u][v].get("flood_level", 0) > 0
        )

        route_layer = folium.FeatureGroup(
            name=f"{style['label']} — {route_length:.0f}m, {flooded_edges_count} flooded segments",
            show=True
        )

        coords = [(G.nodes[n]["y"], G.nodes[n]["x"]) for n in route]

        folium.PolyLine(
            coords,
            color=style["color"],
            weight=style["weight"],
            opacity=style["opacity"],
            dash_array=style["dash_array"],
            tooltip=f"{style['label']} | {route_length:.0f} m | {flooded_edges_count} flooded segments"
        ).add_to(route_layer)

        # Start marker (Route 1 only)
        if i == 0:
            folium.Marker(
                coords[0],
                popup=folium.Popup("<b>Start</b>", max_width=120),
                icon=folium.Icon(color="green", icon="play", prefix="fa")
            ).add_to(route_layer)

        # End marker (Route 1 only)
        if i == 0:
            folium.Marker(
                coords[-1],
                popup=folium.Popup("<b>Destination</b>", max_width=120),
                icon=folium.Icon(color="red", icon="flag", prefix="fa")
            ).add_to(route_layer)

        # Waypoint dots
        step = max(1, len(route) // 6)
        for j, node in enumerate(route[1:-1:step], 1):
            folium.CircleMarker(
                location=(G.nodes[node]["y"], G.nodes[node]["x"]),
                radius=4,
                color=style["color"],
                fill=True,
                fill_color=style["color"],
                fill_opacity=0.9,
                tooltip=f"{style['label']} — waypoint {j}"
            ).add_to(route_layer)

        route_layer.add_to(m)

    # ── Legend ────────────────────────────────────────────────────────────────
    legend_html = """
    <div style="
      position: fixed; bottom: 30px; left: 30px; z-index: 1000;
      background: white; padding: 14px 18px; border-radius: 10px;
      border: 2px solid #ccc; font-size: 13px; line-height: 1.8;
      box-shadow: 2px 2px 6px rgba(0,0,0,0.2);">
      <b style="font-size:14px">Map Legend</b><br>
      <span style="color:green;">━━</span> Safe road<br>
      <span style="color:orange;">━━</span> Partially flooded<br>
      <span style="color:red;">━━</span> Impassable (avoid)<br>
      <hr style="margin:6px 0">
      <span style="color:#9B30FF;">━━</span> Route 1 — Best path<br>
      <span style="color:#FF6600;">╌╌</span> Route 2 — Alternate<br>
      <span style="color:#000000;">┄┄</span> Route 3 — Alternate<br>
      <hr style="margin:6px 0">
      <span style="color:blue; opacity:0.6;">▓▓</span> Flood zone
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    folium.LayerControl(collapsed=False).add_to(m)
    m.save("graph.html")
    print("Map saved to graph.html")


if __name__ == "__main__":
    token = ""
    start = (32.5695347, 74.0842997)   # lat, lon  — Gujrat area
    end   = (32.597075,  74.033844)

    routes, G, G_simple = get_shortest_path(
        lat1=start[0], lon1=start[1],
        lat2=end[0],   lon2=end[1],
        token=token,
        place="Gujrat, Pakistan",
        file_name=r"E:\EMSR838_products\EMSR838_AOI01_DEL_PRODUCT_v1\EMSR838_AOI01_DEL_PRODUCT_floodDepthA_v1.shp",
        k=3,
        vehicle_type="car"
    )