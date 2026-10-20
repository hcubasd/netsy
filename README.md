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
netsy synth agents --seed 1       # zones + size totals + size classes -> agents.gpkg
netsy synth shipments --seed 1    # agents + zones + skims + shipment tables -> shipments.gpkg
netsy synth tours --seed 1        # shipments + zones + skims + tour tables -> tours.gpkg, tour_shipments.csv
netsy synth od-flows               # production/attraction marginals + OD prior -> od_flows.csv
netsy synth facility-chains        # direct transactions + facilities -> transaction_legs.gpkg
netsy synth network-loads --seed 1 # transaction lines + network inputs -> network_loads.csv
netsy synth network-emissions      # network loads + COPERT inputs -> network_emissions.csv
```

An existing output file is only replaced with `--force`.
`agents`, `shipments`, `tours`, and `network-loads` make random draws; pass `--seed` to reproduce them.

`network-loads` reads `shipments.gpkg` by default. Pass
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
| Transactions | Quantified origin-to-destination commitments with stable endpoint identities. | Observed shipment, balanced OD flow, parcel order, or production/consumption match. |
| Transaction legs | A direct transaction or ordered legs through facilities. | Supplier → UCC → customer; depot → microhub → low-emission-zone recipient. |
| Tours and movements | Vehicle operations that serve transaction legs on the road network. | Freight delivery, parcel route, service visit, or another capacity-constrained movement. |
| Scenario data | Choice coefficients, policy restrictions, network/fleet assumptions, and factor models. | A local calibration, an observed policy rule, COPERT V coefficients. |

This prevents a facility such as a UCC or microhub from becoming a special model branch.
It is an ordinary facility in an explicit transaction chain. Whether a case selects that
facility, and the parameters or rules used to do so, belong to scenario data rather than
to the general core.

## Data files

### Agents

`agents` synthesizes the actors the way freight models such as MASS-GT synthesize firms:
from each stratum's total size and a size distribution per agent class. A stratum is a zone
and any other dimensions, such as an employment sector; it is also the agent class.
`size_classes.csv` may be keyed by any subset of the stratum columns, so a size
distribution can be national, per sector, per zone, or anything between. What an agent
produces and consumes follows from its size and class later, when shipments are drawn.

| file | fields | purpose |
|---|---|---|
| `zones.gpkg` | `zone_id`, polygon geometry | Where agents are placed. |
| `size_totals.csv` | stratum columns (`zone_id` among them), `size` | The total size of each stratum, such as its jobs. |
| `size_classes.csv` | key columns, `size_min`, `size_max`, `probability`, and `size_median` for open classes | Each agent class's size distribution, in whole-number size classes; an empty `size_max` makes a class open. |

For example, firms drawn from jobs per zone and sector with a national size distribution per
sector:

| zone_id | sector | size |
|---|---|---:|
| 1 | government | 38 |
| 1 | services | 13 |

| sector | size_min | size_max | size_median | probability |
|---|---:|---:|---:|---:|
| retail | 0 | 4 | | 0.850 |
| retail | 5 | 9 | | 0.083 |
| retail | 100 | | 150 | 0.004 |

`--min-size` drops agents smaller than a size once they are drawn, as MASS-GT drops firms of
three employees or fewer; their size is not given to others.

`agents.gpkg` holds the actors: an `agent_id`, the stratum columns, `size`, and point
geometry.

### Shipments

`shipments` draws the shipments between agents, facilities and zones the way MASS-GT's shipment
synthesis does, generalized to any resources, regions, flow types and facility types. Every row
of `shipment_totals.csv` is a quantity of one shipment stratum to move from one region to another
by one flow type. A shipment stratum is `resource` and any other columns, such as a logistic
segment; a region is a group of zones, such as a study area or an external zone. A flow type
names what each end is: an `agent`, a facility type, or a `zone` itself.

| file | fields | purpose |
|---|---|---|
| `zones.gpkg` | `zone_id`, `region`, polygon geometry, and any numeric zone columns the delivery choice uses | Where shipments start and end. |
| `agents.gpkg` | the output of `agents` | Who sends and receives. |
| `facilities.gpkg` (optional) | `facility_id`, `facility_type`, `zone_id`, `size`, point geometry, and any weight or grouping columns | Distribution centres, terminals, depots: ends of flow types that name their type. |
| `skims.omx` | OMX matrices `time` (hours) and `distance` (km), lookup `zone_id` | Zone-to-zone travel time and distance. |
| `production_rates.csv`, `consumption_rates.csv` | key columns (agent or shipment strata), `rate` | What an agent of each class makes and uses per unit of size, such as make/use shares per sector and commodity. |
| `shipment_totals.csv` | `origin_region`, `destination_region`, optional `origin_zone_id`/`destination_zone_id`, `flow_type`, `resource` and other strata, `quantity` | The quantity to ship; a zone id pins that end to the zone. |
| `flow_types.csv` | `flow_type`, `origin`, `destination`, optional `decay`, `origin_weight`, `destination_weight`, `same`, `distinct` | What each end is, which end is drawn with distance decay, and how facility ends are weighted and paired. |
| `distance_decay.csv` | key columns, `alpha`, `beta`, `cost_per_hour`, `cost_per_km` | The decay of the sourcing cost. |
| `shipment_sizes.csv` | `size_class`, `quantity` | The quantity a shipment of each class carries. |
| `shipment_vehicles.csv` | `vehicle`, `capacity`, `cost_per_hour`, `cost_per_km` | The vehicles a shipment may take. |
| `vehicle_choice.csv` | key columns, `vehicle` (empty for every vehicle), `term`, `value` | The size class and vehicle logit. |
| `delivery_windows.csv`, `delivery_choice.csv` (optional, both or neither) | key columns, `window`, `start`, `end`; key columns, `window` (empty for every window), `term`, `value` | Delivery windows and their logit. |

Key columns are any subset of the shipment strata (or, for rates, of the agent strata too), so a
parameter can be global, per resource, per segment, or anything between.

For example, flow types of a freight model with distribution centres, external zones and parcel
depots shared by operators:

| flow_type | origin | destination | decay | origin_weight | destination_weight | same | distinct |
|---|---|---|---|---|---|---|---|
| direct | agent | agent | origin | | | | |
| to_distribution_centre | agent | distribution_centre | origin | | | | |
| import_direct | zone | agent | destination | | | | |
| parcel_between_depots | parcel_depot | parcel_depot | | size | internal_share | operator | true |

Vehicle-choice terms are `constant`, `transport_cost` (the cost of the vehicles a shipment needs),
`size` (its class quantity), `size_class:<class>`, `origin:<kind>` and `destination:<kind>`
(the kind of an end), and `distance_above:<km>`. Delivery-choice terms are `constant`,
`log_duration`, `origin:<zone column>` and `destination:<zone column>` (a numeric zone value at
an end), and `vehicle:<vehicle>`.

`shipments.gpkg` has one shipment per row: `transaction_id`, the shipment strata, `quantity`,
`origin_agent_id` and `destination_agent_id` (empty for an end that is not an agent),
`flow_type`, the facility and zone of each end, `size_class`, `vehicle`, `window`,
`window_start` and `window_end`, and a line from its origin to its destination.

`facility-chains` and `network-loads` still count quantities in whole units, so shipments of
fractional quantities, such as tonnes, do not pass them yet.

### Tours

`tours` forms vehicle tours from the shipments the way MASS-GT's tour formation does. Shipments
are carried by carriers: a carrier based at each facility of the carrier types, and a number of
independent carriers. Each carrier chains its shipments into tours with two end-tour logits.

| file | fields | purpose |
|---|---|---|
| `shipments.gpkg` | the output of `shipments` | What to carry. |
| `zones.gpkg`, `skims.omx`, `facilities.gpkg` (optional) | as for `shipments` | Where stops are, how far apart, and where carriers are based. |
| `shipment_vehicles.csv` | `vehicle`, `capacity`, ... | Each vehicle's capacity. |
| `tour_settings.csv` | `setting`, `value` | `independent_carriers`, `max_shipments`, `max_duration` (h), `max_proximity` (km), `capacity_slack`, `mean_dwell_time` (h), and any number of `carrier_facility_type` and `same_stratum` rows. |
| `end_tour_first.csv`, `end_tour_later.csv` | key columns, `term`, `value` | The logits of ending a tour after its first shipment and after each later one. |

End-tour terms are `constant`, `duration` and `sqrt_duration` (the tour's hours so far),
`utilization` and `squared_utilization` (the share of its vehicle's capacity used), `proximity`
(km to the nearest shipment left), `log_stops`, `origin:<kind>` and `destination:<kind>`,
`zone:<zone column>` (the larger value at the two zones), `vehicle:<vehicle>` and
`resource:<resource>` (the resource carried most). As in MASS-GT, the kinds, zones and vehicle are
those of the tour's first shipment.

`tours.gpkg` has one trip per row: `tour_id`, `trip` (from 1), `carrier`, `vehicle`, `resource`
(empty on the empty return), the other strata of the tour's first shipment, `shipments`,
`tour_quantity`, `quantity` (on board), `tour_departure`, `departure` and `arrival` (hours),
the trip's zones, and a line between them. `tour_shipments.csv` names the tour that carries each
part of each shipment: `transaction_id`, `tour_id`, `quantity`.

### Facility-mediated transactions

`facility-chains` is an optional general transshipment stage. It reads:

| file | required fields | purpose |
|---|---|---|
| `shipments.gpkg` | `transaction_id`, `resource`, `quantity`, `origin_agent_id`, `destination_agent_id` | Direct transactions to expand. |
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
| transaction-line GeoPackage | Direct transactions (`shipments.gpkg`) or explicit facility legs (`--transactions transaction_legs.gpkg`). |
| `departures.csv` | `resource`, `time_interval`, and departure probability. |
| `time_intervals.csv` | Ordered `time_interval` values and their `duration`. |
| `dwell_times.csv` | Per-resource `dwell_time` at every customer stop. |
| `vehicles.csv` | Vehicle behaviour: BPR parameters, time/distance coefficients, and PCU. |
| `vehicle_velocities.csv` | Vehicle speed and road accessibility by road type. |
| `vehicle_capacities.csv` | Capacity of each vehicle for each resource. |
| `road_capacities.csv` | Road capacity by road type. |
| `alternative_specific_constants.csv` | Vehicle/resource alternative-specific constants. |

`network.gpkg` and the transactions must share a CRS. NetSy transiently normalizes
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

Agents are drawn stratum by stratum, as MASS-GT draws firms. While a stratum $s$ has size
$S_s$ left, an agent's size class $c$ is drawn with probability $p_{k(s),c}$ for its agent
class $k(s)$. A closed class draws the size $e$ uniformly among the whole numbers from
$\mathrm{min}_c$ to $\mathrm{max}_c$; an open class draws it, rounded, from a triangular
distribution from $\mathrm{min}_c$ through a mode of $\max(\mathrm{min}_c, S_s/2)$ to
$\max(\mathrm{median}_c, 1.5\,S_s)$. A size above $1.3\,S_s$ becomes $S_s$. $S_s$ falls by
$e$, and the number of agents is where $S_s$ runs out. Agents of size zero, or below
`--min-size`, are dropped, and each remaining agent is placed uniformly in its zone.

Shipments are drawn total by total, as MASS-GT draws them. While a total of stratum $s$ by flow
type $f$ has quantity $Q$ left, one end is drawn by weight alone and the other by weight times
distance decay: the destination first and the origin second, unless $f$ decays the destination.
An agent's weight is its size times its rate for $s$, a facility's is its weight column, a zone's
is one, and only candidates in the end's region (or pinned zone) count. The decay between origin
zone $i$ and destination zone $j$ is $1 / (1 + e^{\alpha + \beta \ln c_{ij}})$, with
$c_{ij} = \mathrm{cost/h} \cdot t_{ij} + \mathrm{cost/km} \cdot d_{ij}$; a zero skim cell, such
as an intrazonal one, takes half the smallest positive value of its row. Ends that must share a
facility column or differ are drawn among those that do. The size class $k$ and vehicle $v$ are
then chosen together by multinomial logit, with $\mathrm{transport\_cost} = (\mathrm{cost/h}_v
\cdot t + \mathrm{cost/km}_v \cdot d) \lceil q_k / \mathrm{capacity}_v \rceil$; the shipment
carries $\min(q_k, Q)$, and $Q$ falls by it. Last, each shipment's delivery window is chosen by
multinomial logit over its stratum's windows.

With MASS-GT's Dutch inputs, regions are its superzones, flow types its twelve (external ones
split by direction), and the shipment strata its NSTR commodity, logistic segment and flow-type
id. Its exports read the commodity matrix's external-to-internal cells and its imports the
reverse, a bug that the totals reproduce, as the reference run does. Two of its quirks are not reproduced: a parcel origin depot
that equals the destination depot moves to its neighbour in MASS-GT's depot list, where NetSy
draws among the operator's other depots, and its import draws reuse one random stream for every
external zone.

Tours are formed carrier by carrier. Each shipment is split into equal parts that fit its
vehicle; a part with an end at a facility of a carrier type goes to that facility's carrier (one
of the two at random if both are), and any other to a random independent carrier. A based carrier
takes its parts shortest first, an independent one in random order. A tour starts with the first
part left. While it has fewer than `max_shipments` parts after its first, lasts less than
`max_duration`, is less than full, and has a part left within `max_proximity`, a binary logit
decides whether it ends: `end_tour_first.csv` after its first part, `end_tour_later.csv` after
each later one. If it goes on, it takes the nearest part (a part of its vehicle counts as half as
far) of the same `same_stratum` values whose weight keeps the tour under `capacity_slack` times
its capacity and whose delivery window neighbours the tour's. Its stops are ordered loading first
and then unloading, nearest first, starting from the carrier's base; single stops are then moved
where that shortens the tour without unloading before loading. A tour returns empty to its
start. With one dwell time per tour, drawn uniformly up to twice `mean_dwell_time`, its departure
time puts its trips' arrivals, on average, midway between their windows' bounds; as in MASS-GT,
the window of a stop is compared with the arrival at the stop after it.

With MASS-GT's Dutch inputs, carriers are based at distribution centres, tours keep to one
logistic segment, and the transshipment and urban indicators are zone columns. Not reproduced:
MASS-GT's transshipment indicator leaves out an end at a distribution centre in a terminal zone,
and it drops the DC-loading indicator of a shipment unloaded in a terminal zone; parcel
shipments of nominal flow types 3, 5 and 7 count as loaded at a distribution centre there.

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
