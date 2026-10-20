#!/bin/sh
# Dutch data remain outside Git. Set PYTHON, NETSY, MASSGT_INPUT and MASSGT_DIMENSIONS as needed.
set -eu
recipe=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
case_dir=${1:-/workdir/netherlands}
PYTHON=${PYTHON:-python}
NETSY=${NETSY:-netsy}
"$PYTHON" "$recipe/build/bootstrap.py" "$case_dir"
case_dir=$(CDPATH= cd -- "$case_dir" && pwd)
"$PYTHON" "$recipe/build/build_nl_agents.py" "$case_dir"
"$PYTHON" "$recipe/build/build_nl_od.py" "$case_dir"
cd "$case_dir"
"$NETSY" synth od-marginals --force
"$NETSY" synth od-flows --force
for stage in shipments parcels vans network; do
 "$PYTHON" "$recipe/build/build_nl_$stage.py" "$case_dir"
done
"$NETSY" synth agents --seed 1 --min-size 4 --force
"$NETSY" synth shipments --seed 1 --force
"$NETSY" synth tours --seed 1 --force
"$NETSY" synth parcel-demand --force
"$NETSY" synth deliveries --seed 1 --force
"$NETSY" synth trip-matrices --force
"$NETSY" synth network-loads --force
"$NETSY" synth network-emissions --force

"$NETSY" synth indicators --force
