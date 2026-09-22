import geopandas
import pandas as pd
from shapely.geometry import box

CRS = "EPSG:28992"


def zones():
    return geopandas.GeoDataFrame({"zone_id": [1, 2]}, geometry=[box(0, 0, 1, 1), box(2, 0, 3, 1)], crs=CRS)


def aggregate(rows, columns):
    """A supply or demand table as `read_aggregate` returns it: all text."""
    return pd.DataFrame(rows, columns=columns, dtype=str)


def distribution(rows):
    """A capacities or needs table as `read_distribution` returns it."""
    return pd.DataFrame(rows, columns=["zone_id", "sector", "resource", "resource_level", "probability"]).astype(
        {"zone_id": str, "sector": str, "resource": str, "resource_level": "int64", "probability": float}
    )
