from geopy.geocoders import Nominatim
from fastkml import kml

def geocode_location(location_name):
    geolocator = Nominatim(user_agent="geoapi")
    location = geolocator.geocode(location_name)
    if location:
        return {
            "lat": location.latitude,
            "lng": location.longitude,
            "zoom": 10
        }
    return None



from fastkml import kml

def get_kml_center(kml_file):
    try:
        doc = kml.KML()
        doc.from_string(kml_file.read())
        features = list(doc.features())  # Top-level KML features
        if not features:
            return None

        folder = list(features[0].features)  # REMOVE the ()
        if not folder:
            return None

        placemark = folder[0]
        geom = placemark.geometry
        bounds = geom.bounds
        center = {
            "lat": (bounds[1] + bounds[3]) / 2,
            "lng": (bounds[0] + bounds[2]) / 2,
            "zoom": 10
        }
        return center
    except Exception as e:
        print("Error in get_kml_center:", str(e))
        return None
