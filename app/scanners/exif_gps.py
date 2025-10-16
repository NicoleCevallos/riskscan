from typing import Optional, Tuple
from ..utils.exif import read_gps_latlon
def scan_image_for_gps(image_path: str) -> Optional[Tuple[float,float]]:
    return read_gps_latlon(image_path)
