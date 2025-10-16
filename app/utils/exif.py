from PIL import Image, ExifTags
from typing import Optional, Tuple
def _to_deg(value):
    d = float(value[0][0]) / float(value[0][1])
    m = float(value[1][0]) / float(value[1][1])
    s = float(value[2][0]) / float(value[2][1])
    return d + (m/60.0) + (s/3600.0)
def read_gps_latlon(image_path:str) -> Optional[Tuple[float,float]]:
    try:
        img = Image.open(image_path)
        exif = img._getexif()
        if not exif: return None
        label_map = {ExifTags.TAGS.get(k,k): v for k,v in exif.items()}
        gps = label_map.get("GPSInfo")
        if not gps: return None
        gps_map = {ExifTags.GPSTAGS.get(k,k): v for k,v in gps.items()}
        lat = _to_deg(gps_map["GPSLatitude"])
        if gps_map.get("GPSLatitudeRef") in ["S","s"]: lat = -lat
        lon = _to_deg(gps_map["GPSLongitude"])
        if gps_map.get("GPSLongitudeRef") in ["W","w"]: lon = -lon
        return (lat, lon)
    except Exception:
        return None
