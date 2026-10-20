"""Zone-to-zone skims in OMX, the open matrix format of transport models:
an HDF5 file with `time` (hours) and `distance` (kilometres) matrices and a
`zone_id` lookup naming each row and column.
"""

import os

import h5py
import numpy as np

MATRICES = ("time", "distance")


def _zone_ids(values):
    return [value.decode() if isinstance(value, bytes) else str(value) for value in values.tolist()]


def read_skims(path):
    """The zone ids (as text) and the `time` and `distance` matrices of the
    OMX file at `path`. Raises ValueError, prefixed with the path, if the
    file is missing or malformed.
    """
    if not os.path.exists(path):
        raise ValueError(f"{path}: not found")
    try:
        with h5py.File(path, "r") as file:
            if "lookup" not in file or "zone_id" not in file["lookup"]:
                raise ValueError("missing lookup 'zone_id'")
            missing = [name for name in MATRICES if name not in file.get("matrices", {})]
            if missing:
                raise ValueError(f"missing matrices {missing}")
            zone_ids = _zone_ids(file["lookup"]["zone_id"][()])
            time, distance = (np.asarray(file["matrices"][name][()], dtype=np.float32) for name in MATRICES)
    except OSError as error:
        raise ValueError(f"{path}: {error}") from None
    except ValueError as error:
        raise ValueError(f"{path}: {error}") from None
    count = len(zone_ids)
    if len(set(zone_ids)) != count:
        raise ValueError(f"{path}: 'zone_id' values must be unique")
    for name, matrix in zip(MATRICES, (time, distance)):
        if matrix.shape != (count, count):
            raise ValueError(f"{path}: '{name}' must be a {count} x {count} matrix, one row and column per zone")
        if not np.isfinite(matrix).all():
            raise ValueError(f"{path}: '{name}' must hold numbers in every cell")
    return zone_ids, time, distance


def write_skims(path, zone_ids, time, distance):
    """Write `time` and `distance` matrices with their `zone_ids` to `path`
    as OMX.
    """
    write_matrices(path, zone_ids, dict(zip(MATRICES, (time, distance))))


def write_matrices(path, zone_ids, matrices):
    """Write named zone-by-zone `matrices` with their `zone_ids` to `path`
    as OMX.
    """
    zone_ids = np.asarray(zone_ids)
    if zone_ids.dtype.kind in "OU":
        zone_ids = zone_ids.astype("S")
    with h5py.File(path, "w") as file:
        file.attrs["OMX_VERSION"] = np.bytes_("0.2")
        file.attrs["SHAPE"] = np.array([len(zone_ids)] * 2, dtype=np.int32)
        for name, matrix in matrices.items():
            file.create_dataset(f"matrices/{name}", data=np.asarray(matrix, dtype=np.float32), compression="gzip")
        file.create_dataset("lookup/zone_id", data=zone_ids)


def read_matrices(path):
    """The zone ids (as text) and every matrix of the OMX file at `path`, by
    name.
    """
    if not os.path.exists(path):
        raise ValueError(f"{path}: not found")
    try:
        with h5py.File(path, "r") as file:
            zone_ids = _zone_ids(file["lookup"]["zone_id"][()])
            matrices = {name: np.asarray(file["matrices"][name][()], dtype=np.float32) for name in file.get("matrices", {})}
    except (OSError, KeyError) as error:
        raise ValueError(f"{path}: {error}") from None
    for name, matrix in matrices.items():
        if matrix.shape != (len(zone_ids), len(zone_ids)):
            raise ValueError(f"{path}: '{name}' must be a square matrix, one row and column per zone")
    return zone_ids, matrices
