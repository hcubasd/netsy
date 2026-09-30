import pyproj


_KILOMETER_CRS = pyproj.CRS.from_user_input(
    "+proj=etmerc +lat_0=0 +lon_0=0 +k=1 +x_0=0 +y_0=0 +ellps=WGS84 +units=km +no_defs"
)


def kilometers(table, path, projected_crs=None):
    """Return a transient geometry table whose coordinate values are
    kilometres. Geographic input is projected first; other projected units
    are scaled through the CRS's declared conversion to metres.
    """
    if table.crs is None:
        raise ValueError(f"{path}: missing CRS")
    if projected_crs is not None:
        metric = table.to_crs(projected_crs)
    elif table.crs.is_geographic:
        metric = table.to_crs(table.estimate_utm_crs())
    else:
        metric = table
    factor = metric.crs.axis_info[0].unit_conversion_factor / 1000
    result = metric.copy()
    result["geometry"] = metric.geometry.affine_transform([factor, 0, 0, factor, 0, 0])
    return result.set_crs(_KILOMETER_CRS, allow_override=True)
