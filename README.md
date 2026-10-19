# netsy

NetSy is a general spatial resource-flow synthesizer. It turns case-specific activity,
facility, vehicle, timing, network, and emissions evidence into explicit transactions,
capacity-constrained movements, directional link loads, and emissions.

NetSy starts from actors and the transactions between them, observed or synthesized:
observed shipments, provider-to-consumer matches, balanced OD flows, parcel demand,
service trips, and facility-mediated chains all use the same transaction, tour, network,
and emissions core.

## Install

```
pip install netsy
```

Requires Python 3.11 or newer.

## Visualizer

`docs/` is a self-contained TypeScript visualizer for NetSy's CSV and GeoPackage files.
It runs entirely in the browser: a map of the loaded geometries, the data-flow graph of every
file NetSy reads and writes (where files are loaded), and their tables. No data is uploaded.

```sh
cd docs
npm install
npm run dev
```

The development server binds to the host network so it can be reviewed from another device
on the local network. Its production output is static and is built with `npm run build`.

## Usage

Run each command in the directory holding its input files.

```
netsy synth desire-lines --seed 1 # agents.gpkg -> desire_lines.gpkg
netsy synth od-flows               # production/attraction marginals + OD prior -> od_flows.csv
netsy synth facility-chains        # direct transactions + facilities -> transaction_legs.gpkg
netsy synth network-loads --seed 1 # transaction lines + network inputs -> network_loads.csv
netsy synth network-emissions      # network loads + COPERT inputs -> network_emissions.csv
```

An existing output file is only replaced with `--force`.
`desire-lines` and `network-loads` make random draws; pass `--seed` to reproduce them.

`network-loads` reads `desire_lines.gpkg` by default. Pass
`--transactions transaction_legs.gpkg` to route facility-mediated transaction legs instead:

```sh
netsy synth network-loads --transactions transaction_legs.gpkg --seed 1
```

## Model boundary

NetSy deliberately separates the general model from the case-specific evidence that
configures it.

| General model object | Role | Examples of case-specific sources |
|---|---|---|
| Actors | Produce, consume, carry, or transform resources. | Establishment register, household survey, an operator's records, or firm synthesis. |
| Facilities | Locations with explicit operational roles and throughput constraints. | Depot, UCC, consolidation centre, microhub, hospital, transfer station. |
| Transactions | Quantified origin-to-destination commitments with stable endpoint identities. | Observed shipment, balanced OD flow, parcel order, or capacity/need match. |
| Transaction legs | A direct transaction or ordered legs through facilities. | Supplier → UCC → customer; depot → microhub → low-emission-zone recipient. |
| Tours and movements | Vehicle operations that serve transaction legs on the road network. | Freight delivery, parcel route, service visit, or another capacity-constrained movement. |
| Scenario data | Choice coefficients, policy restrictions, network/fleet assumptions, and factor models. | A local calibration, an observed policy rule, COPERT V coefficients. |

This prevents a facility such as a UCC or microhub from becoming a special model branch.
It is an ordinary facility in an explicit transaction chain. Whether a case selects that
facility, and the parameters or rules used to do so, belong to scenario data rather than
to the general core.

## Data files

`agents.gpkg` holds the actors: an `agent_id`, a `{resource}_capacity` and a
`{resource}_need` column for every resource (whole numbers; an empty cell means the agent
does not take part in that resource), any other attributes, and point geometry. It may come
from any source, such as a register, an operator's records, or a firm-synthesis adapter.
`desire_lines.gpkg` contains one direct
provider-to-consumer transaction per row. It preserves both endpoints as identities;
geometry is its spatial representation, not its only identity.

| transaction_id | resource | quantity | origin_agent_id | destination_agent_id | geometry |
|---|---|---:|---:|---:|---|
| 0 | resource_1 | 2 | 1 | 8 | LINESTRING (0.42 0.71, 0.38 0.65) |

For each resource, a provider is selected by remaining capacity and matched with
consumers until the provider is depleted. Consumers are selected by their remaining need
and distance-weighted proximity. A desire line starts at its provider and ends at its
consumer.

### Facility-mediated transactions

`facility-chains` is an optional general transshipment stage. It reads:

| file | required fields | purpose |
|---|---|---|
| `desire_lines.gpkg` | `transaction_id`, `resource`, `quantity`, `origin_agent_id`, `destination_agent_id` | Direct transactions to expand. |
| `facilities.gpkg` | `facility_id`, `facility_type`, `capacity`, point geometry | Explicit facility locations and total throughput constraints. |
| `facility_chain_steps.csv` | `transaction_id`, `sequence`, `facility_id` | Consecutive facility steps for a transaction. |

It writes `transaction_legs.gpkg`: one direct leg when no chain step is supplied, or an
ordered set of legs when it is. Each facility consumes transaction quantity as throughput;
an over-capacity scenario fails rather than silently routing through the facility.

For example, a package that must be consolidated at a UCC has one step:

| transaction_id | sequence | facility_id |
|---|---:|---|
| 0 | 1 | ucc_1 |

and becomes `supplier → ucc_1` followed by `ucc_1 → customer`. A microhub is represented
the same way. Multiple ordered facilities produce multiple legs. Facility-choice,
carrier-choice, parcel-scheduling, and service-demand models can create these transaction
and chain inputs without changing the core chain semantics.

`network-loads` combines ten supplied files. It does not synthesize their contents:

| file | purpose |
|---|---|
| `network.gpkg` | Directed road links: `link_id`, `grade`, `road_type`, `oneway`, and line geometry. |
| transaction-line GeoPackage | Direct transactions (`desire_lines.gpkg`) or explicit facility legs (`--transactions transaction_legs.gpkg`). |
| `departures.csv` | `resource`, `time_interval`, and departure probability. |
| `time_intervals.csv` | Ordered `time_interval` values and their `duration`. |
| `dwell_times.csv` | Per-resource `dwell_time` at every customer stop. |
| `vehicles.csv` | Vehicle behaviour: BPR parameters, time/distance coefficients, and PCU. |
| `vehicle_velocities.csv` | Vehicle speed and road accessibility by road type. |
| `vehicle_capacities.csv` | Capacity of each vehicle for each resource. |
| `road_capacities.csv` | Road capacity by road type. |
| `alternative_specific_constants.csv` | Vehicle/resource alternative-specific constants. |

`network.gpkg` and `desire_lines.gpkg` must share a CRS. NetSy transiently normalizes
their geometry to kilometres; vehicle velocities are kilometres per interval-time unit and
COPERT V requires interval durations in hours. There is no
`consolidation_radii.csv`: capacity-constrained routing replaces radius consolidation.
`dwell_times.csv` no longer has `load_pct`; vehicles return empty after their final stop.

`network_loads.csv` has a row per directional link, interval,
resource, vehicle, and payload fraction:

| link_id | time_interval | resource | vehicle | forward | vehicle_count | velocity | load_pct |
|---|---|---|---|---|---:|---:|---:|
| 17 | morning | parcels | van | true | 3 | 34.2 | 1.0 |
| 17 | morning | parcels | van | false | 3 | 29.8 | 0.0 |

For each resource, its total transaction quantity is apportioned exactly across the
defined time intervals. Within an interval, providers and seed consumers are drawn by
remaining transaction quantity. For every feasible vehicle type, NetSy builds a
capacity-constrained, provider-returning tour by cheapest insertion on the directed road
network, then chooses a vehicle-tour alternative with multinomial logit. A tour serves one
resource, may split a delivery across tours, waits at every customer, and returns empty.
Payload fractions remain separate output strata so downstream emissions retain their
per-leg payload information.

`network-emissions` combines `network_loads.csv`, `network.gpkg`, `vehicles.csv`,
`copert_v_coefficients.csv`, and `emission_factors.csv` into `network_emissions.csv`.
The coefficient file has one row per COPERT V
`vehicle_type`, `pollutant`, `gradient_bin`, and `payload_bin`, with columns `alpha`
through `eta` and reduction factor `rf`. Gradient bins are `-6, -4, -2, 0, 2, 4, 6`;
payload bins are `0, 50, 100`. The flat non-exhaust factor file has
`vehicle_type`, `pollutant`, and `emission_factor` in g/km.

| link_id | time_interval | resource | vehicle | forward | pollutant | source | grams |
|---|---|---|---|---|---|---|---:|
| 17 | morning | parcels | van | true | nox | exhaust | 12.84 |
| 17 | morning | parcels | van | true | pm10 | non-exhaust | 0.67 |

Exhaust follows the COPERT V speed function. It uses each load row's velocity, payload
fraction, and directed link grade, snapping grade and payload to the published coefficient
grid before scaling the resulting g/km factor by link distance and vehicle count.
Non-exhaust emissions remain velocity-independent g/km factors scaled by the same
distance and count; no unsupported speed relationship is invented.

## Canonical extension path

Actors and transactions can come from any source. NetSy's general core is designed to
accept explicitly calibrated scenario adapters:

1. actor/facility population synthesis or observed registers;
2. production/attraction, gravity, and IPF/Furness OD balancing;
3. shipment-size, vehicle, time, carrier, and facility-chain choices;
4. freight pickup/delivery, parcel, and service-operation tour strategies;
5. shortest-path, stochastic, and BPR assignment strategies;
6. COPERT V, legacy-factor, or other declared emissions-factor models;
7. stagewise calibration and validation against local OD, tours, counts, and emissions.

These adapters must declare their parameters, units, provenance, seed streams, and
validation targets. They may reproduce a case study closely at aggregate/distributional
levels, but NetSy does not claim row-for-row equivalence when a case uses a different
tour heuristic, assignment model, emissions factors, or stochastic stream.

### Balanced OD flows

`od-flows` provides the canonical doubly constrained IPF/Furness (also called FRATAR)
stage. It is independent of agents and writes fractional resource
flows that a case-specific shipment or transaction adapter can subsequently discretize.
It reads:

| file | required fields | purpose |
|---|---|---|
| `productions.csv` | `resource`, `location_id`, `quantity` | Origin marginal totals. |
| `attractions.csv` | `resource`, `location_id`, `quantity` | Destination marginal totals. |
| `od_prior.csv` | `resource`, `origin_location_id`, `destination_location_id`, `weight` | Non-negative supported OD pairs and their prior impedance/gravity/observed-flow weights. |

For every resource, production and attraction totals must agree. The stage preserves that
total and balances only supported positive-weight OD pairs; it fails when a positive
origin or destination has no feasible counterpart. This makes external gateways,
unserved areas, and policy-forbidden pairs explicit scenario inputs rather than hidden
residual flows.

## Model

Desire lines match each resource's providers to consumers by remaining quantity and
distance-weighted proximity.

Network loads apportion each resource's transaction total exactly across departure
intervals. Within an interval, NetSy draws a provider and seed consumer from residual
flow, builds a capacity-constrained provider-returning tour for every feasible vehicle type
by cheapest insertion, and selects a vehicle-tour alternative with multinomial logit.
Vehicle movement uses directed road links and a BPR volume-delay function; vehicles dwell at
each customer and return empty. Load rows retain payload fractions rather than averaging
away the changing payload of a multi-stop tour.

Network emissions use each load row's vehicle type, velocity, directed grade, and payload
to evaluate the corresponding COPERT V hot-exhaust factor. Non-exhaust emissions are
separate, velocity-independent g/km factors. Both sources scale their factor by directional
link distance and vehicle count.
