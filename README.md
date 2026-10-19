# netsy

NetSy is a general spatial resource-flow synthesizer. It turns case-specific activity,
facility, vehicle, timing, network, and emissions evidence into explicit transactions,
capacity-constrained movements, directional link loads, and emissions.

The built-in ordered-logit profile synthesizes supply, demand, capacities, needs, and
agents. Its direct provider-to-consumer transactions are also a useful baseline for a
broader model: observed shipments, balanced OD flows, parcel demand, service trips, and
facility-mediated chains can use the same transaction, tour, network, and emissions core.

## Install

```
pip install netsy
```

Requires Python 3.11 or newer.

## Visualizer

`docs/` is a self-contained TypeScript visualizer for NetSy's CSV and GeoPackage files.
It runs entirely in the browser: select or drop local synthesis files to inspect the WebGL
map, animated pipeline diagram, and data tables without uploading data to a service.

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
netsy synth supply       # supply_effects.csv + supply_thresholds.csv -> supply.csv
netsy synth demand       # demand_effects.csv + demand_thresholds.csv -> demand.csv
netsy synth capacities   # capacity_effects.csv + capacity_thresholds.csv -> capacities.csv
netsy synth needs        # need_effects.csv + need_thresholds.csv -> needs.csv
netsy synth agents --seed 1       # supply/demand/capacities/needs + zones.gpkg -> agents.gpkg
netsy synth desire-lines --seed 1 # agents.gpkg -> desire_lines.gpkg
netsy synth od-flows               # production/attraction marginals + OD prior -> od_flows.csv
netsy synth facility-chains        # direct transactions + facilities -> transaction_legs.gpkg
netsy synth network-loads --seed 1 # transaction lines + network inputs -> network_loads.csv
netsy synth network-emissions      # network loads + COPERT inputs -> network_emissions.csv
```

An existing output file is only replaced with `--force`.
`agents`, `desire-lines`, and `network-loads` make random draws; pass `--seed` to reproduce them.

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
| Actors | Produce, consume, carry, or transform resources. | Establishment register, household survey, or the ordered-logit agent profile. |
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

`*_effects.csv` holds one additive effect per stratum value and resource. `zone_id` is always a stratum. An empty cell means the stratum value does not take part in that resource.

| stratum | stratum_value | resource_1 | resource_2 |
|---|---|---|---|
| zone_id | 1 | -1.347 | -0.813 |
| zone_id | 2 | 1.494 | 1.546 |
| stratum_1 | value_1 | -0.627 | 0.398 |
| stratum_1 | value_2 | -0.191 | 0.078 |
| stratum_2 | value_1 | -0.204 | -1.179 |
| stratum_2 | value_2 | -2.511 | 0.471 |

`*_thresholds.csv` holds the sorted cutpoints of each resource. The largest level has none.

| resource | resource_level | threshold |
|---|---|---|
| resource_1 | 0 | 0.432 |
| resource_1 | 2 | 1.738 |
| resource_1 | 3 | |
| resource_2 | 4 | -0.220 |
| resource_2 | 9 | |

`supply.csv` and `demand.csv` have one row per stratum combination and one column per resource.

| zone_id | stratum_1 | stratum_2 | resource_1 | resource_2 |
|---|---|---|---|---|
| 1 | value_1 | value_1 | 0 | 5 |
| 1 | value_1 | value_2 | 0 | 7 |
| 1 | value_2 | value_1 | 0 | 5 |

`capacities.csv` and `needs.csv` have one row per stratum combination, resource and level.

| zone_id | stratum_1 | stratum_2 | resource | resource_level | probability |
|---|---|---|---|---|---|
| 1 | value_1 | value_1 | resource_1 | 0 | 0.9315 |
| 1 | value_1 | value_1 | resource_1 | 2 | 0.0490 |
| 1 | value_1 | value_1 | resource_1 | 3 | 0.0195 |
| 1 | value_1 | value_1 | resource_2 | 4 | 0.7980 |
| 1 | value_1 | value_1 | resource_2 | 9 | 0.2020 |

`agents.gpkg` contains an `agent_id`, its stratum columns, `{resource}_capacity` and
`{resource}_need` columns, and point geometry. `desire_lines.gpkg` contains one direct
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

The ordered-logit profile is intentionally not the only way to create transactions. NetSy's
general core is designed to accept additional, explicitly calibrated scenario adapters:

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
stage. It is independent of the ordered-logit agent profile and writes fractional resource
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

Each resource $r$ is an ordinal outcome under a cumulative-logit model, with $\sigma(x) = 1 / (1 + e^{-x})$. A stratum $s = (v_1, \dots, v_D)$ takes one value from each of the $D$ dimensions, and its linear predictor is the sum of the effects $\gamma$ of those values:

$$\beta_{r,s} = \sum_{d=1}^{D} \gamma_{r,d,v_d}$$

If any of these effects is empty the pair $(s, r)$ is omitted, which is not the same as an effect of zero. With levels $\ell_{r,1} < \dots < \ell_{r,K_r}$ and thresholds $\mu_{r,1} \le \dots \le \mu_{r,K_r-1}$, the cumulative probability of level $k$ is

$$F_{r,s}(k) = \sigma(\mu_{r,k} - \beta_{r,s})$$

with $F_{r,s}(0) = 0$ and $F_{r,s}(K_r) = 1$, and the probability of each level is the difference

$$p_{r,s}(\ell_{r,k}) = F_{r,s}(k) - F_{r,s}(k-1)$$

Capacities and needs are these probabilities. Supply and demand are the expected level rounded to a whole unit:

$$A_{r,s} = \mathrm{round}\left( \sum_{k=1}^{K_r} \ell_{r,k} p_{r,s}(\ell_{r,k}) \right)$$

Agents are sampled independently from their stratum's capacity and need distributions while
remaining aggregate supply and demand permit. Desire lines then match each resource's
providers to consumers by remaining quantity and distance-weighted proximity.

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
link distance and vehicle count. See [`netsy-report`](https://github.com/hcubasd/netsy-report)
for the complete equations and file-shape appendix.
