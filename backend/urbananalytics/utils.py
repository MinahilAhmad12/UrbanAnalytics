from fastkml import kml
from shapely.geometry import shape
import os

import xml.etree.ElementTree as ET
from django.contrib.gis.geos import Polygon

import xml.etree.ElementTree as ET
from django.contrib.gis.geos import Polygon

def extract_bounds_from_kml(kml_file_path):
    try:
        tree = ET.parse(kml_file_path)
        root = tree.getroot()

        ns = {"kml": "http://www.opengis.net/kml/2.2"}

        coords = []
        for coord in root.findall(".//kml:coordinates", ns):
            coord_text = coord.text.strip()
            coord_text = (
                coord_text.replace("[", "")
                          .replace("]", "")
                          .replace(",", " ")
            )
            parts = coord_text.split()
            for i in range(0, len(parts), 2):
                try:
                    lon = float(parts[i])
                    lat = float(parts[i + 1])
                    coords.append((lon, lat))
                except (ValueError, IndexError):
                    continue

        if not coords:
            return None

        lons, lats = zip(*coords)
        minx, maxx = min(lons), max(lons)
        miny, maxy = min(lats), max(lats)

        polygon = Polygon.from_bbox((minx, miny, maxx, maxy))

        # 🔑 Convert Polygon to GeoJSON dict
        return polygon.geojson  

    except Exception as e:
        print(f"Error parsing KML: {e}")
        return None
