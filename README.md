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
netsy synth od-marginals             # location attributes + coefficients + OD prior -> productions, attractions
netsy synth od-flows                 # productions + attractions + OD prior -> od_flows.csv
netsy synth agents --seed 1          # zones + size totals + size classes -> agents.gpkg
netsy synth shipments --seed 1       # agents + zones + skims + shipment tables -> shipments.gpkg
netsy synth tours --seed 1           # shipments + zones + skims + tour tables -> tours.gpkg, tour_shipments.csv
netsy synth parcel-demand            # zones + depots + skims + parcel tables -> parcel_demand.csv
netsy synth deliveries --seed 1      # parcel demand + zones + skims -> delivery_tours.gpkg
netsy synth trip-matrices            # zones + skims + trip tables -> trip_matrices.omx
netsy synth network-loads            # tours, delivery tours, trip matrices + network -> network_loads.parquet
netsy synth network-emissions        # network loads + network + emission factors -> network_emissions.parquet
netsy synth facility-chains          # shipments + facilities + chain steps -> transaction_legs.gpkg
```

An existing output file is only replaced with `--force`.
`agents`, `shipments`, `tours`, and `deliveries` make random draws; pass `--seed` to reproduce them.

Two options switch from MASS-GT's method to a contribution of NetSy's:

```sh
netsy synth deliveries --routing savings      # Clarke-Wright savings routes instead of MASS-GT's
netsy synth network-emissions --method copert # COPERT V instead of MASS-GT's emission factors
```

## Reproducing MASS-GT

With MASS-GT's Dutch inputs (the `netherlands` case, built by its `run.sh`), every stage
reproduces MASS-GT's reference run: firm synthesis and the commodity matrix (to MASS-GT's
rounding), shipments and tours (statistically, as random draws differ), parcel demand and van
trips (exactly, to MASS-GT's rounding), and the assignment and its emissions (link by link, on
MASS-GT's own trips). Where MASS-GT's code departs from its own intent, NetSy follows the
intent and says so in the stage's section; the case data reproduce two such departures, the
reversed reading of imports and exports and the scrambled external zones of van trips, because
MASS-GT's reference results depend on them.

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

`facility-chains` still counts quantities in whole units, so shipments of fractional
quantities, such as tonnes, do not pass it yet.

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

### Parcels

`parcel-demand` derives parcels per zone the way MASS-GT's parcel demand module does, and
`deliveries` forms delivery tours from depots the way its parcel scheduling does.

| file | fields | purpose |
|---|---|---|
| `parcel_attributes.csv`, `parcel_rates.csv` | `zone_id` and attributes; `attribute`, `rate` | Business parcels per zone, linear in attributes such as jobs. |
| `population.csv` | `zone_id`, any strata, `persons` | Persons per zone and cell, such as age and income group. |
| `order_levels.csv` | `level`, `quantity`, `threshold` (empty for the last) | The ordered logit's levels of parcels per period. |
| `order_utility.csv` | any population strata (empty for any), `value` | Its additive utility terms. |
| `operator_shares.csv` | `operator`, `share` | Parcel operators' market shares. |
| `parcel_settings.csv` | `setting`, `value` | `period` (days), `per_person` (a daily total to scale consumer parcels to), `depot_type`, `operator_column`. |
| `delivery_settings.csv` | `setting`, `value` | `max_load` (parcels per vehicle), `drop_time` (h per parcel), `vehicle`, `segment`, `utilization`. |
| `delivery_departures.csv` | `hour`, `cumulative_share` | When tours depart. |

`parcel_demand.csv` has a row per destination zone, operator and depot with its `parcels`;
`delivery_tours.gpkg` has a trip per row, in the shape of `tours.gpkg`, with the parcels
delivered at its destination.

A consumer cell's utility is the sum of its matching terms; the probability of ordering at
most a level is 1 / (1 + exp(utility − threshold)), and its expected parcels per period, times
its persons over the period, are scaled to `per_person` parcels a day. Each zone's parcels are
split by operator, rounded, and sent from the operator's nearest depot. With MASS-GT's routing a
depot sends full vehicles first, then clusters its other parcels around the farthest left,
orders each cluster nearest first and swaps pairs of stops. MASS-GT's code orders stops by the
distances of the next zones in its list, an indexing error that makes its tours 27% longer than
its clusters need; NetSy uses the right zones.

**Contribution:** `--routing savings` builds each depot's tours with the Clarke-Wright savings
algorithm under the same load, then moves single stops while that shortens a tour. With
MASS-GT's Dutch parcels it delivers the same 228,707 parcels with 10% fewer vehicle-kilometres
than MASS-GT's routing, using 4% more tours.

### Van trips

`trip-matrices` derives van trips between zones the way MASS-GT's service module does: per
segment, productions (and as many attractions) linear in zone attributes, a gravity prior
1 / (1 + e^alpha cost^beta) times both zones' productions, and FRATAR balancing (25 iterations,
0.005 tolerance). Trips between two zones flagged `external` in `zones.gpkg` are dropped. It
reads `trip_attributes.csv` (`zone_id` and attributes), `trip_rates.csv` (`segment`,
`attribute`, `rate`) and `trip_decay.csv` (`segment`, `alpha`, `beta`, `cost_per_hour`,
`cost_per_km`), and writes `trip_matrices.omx`, a matrix per segment.

### Network loads

`network-loads` loads trips onto the road network the way MASS-GT's traffic assignment does:
every trip takes the cheapest path between its zones' nodes, all or nothing, at the speeds it is
given. It does not change speeds: where a case has the whole traffic of its roads, a separate
step may derive speeds from it.

| file | fields | purpose |
|---|---|---|
| `network.gpkg` | `link_id`, `from_node`, `to_node`, `length` (km), `road_type`, line geometry, optional `grade` (%) | Directed links. |
| `zones.gpkg` | `node` | The node each zone loads at. |
| `assignment_vehicles.csv` | `vehicle`, `speed_class`, `cost_per_hour`, `cost_per_km` | How each vehicle chooses its path. |
| `link_speeds.csv` | `link_id`, `speed_class`, `speed` (km/h), optional `time_interval` | The given speeds. |
| `road_costs.csv` | `road_type`, `speed_class` (empty for all), `cost` | Fixed link costs, such as for connectors or links closed to trucks. |
| `time_intervals.csv` | `time_interval`, `start`, `end` (h) | The intervals of the period. |
| `tours.gpkg`, `delivery_tours.gpkg` (each optional) | `departure`, `vehicle`, `utilization`, zones, optional `segment` | Trips, in the interval of their departure. |
| `trip_matrices.omx`, `matrix_assignment.csv` (optional) | `matrix`, `vehicle`, `segment`, `utilization`, `minimum` | Matrix trips, over the whole period. |

`network_loads.parquet` has a row per link, interval, vehicle and segment: `trips`, their mean
`utilization`, and the link's `speed` for the vehicle.

### Network emissions

`network-emissions` computes grams per load row and pollutant, a column per pollutant.

- `--method factors` (MASS-GT's) reads `emission_factors.csv` (`vehicle`, `road_type`,
  `pollutant`, `empty`, `full` in g/km); a load's factor lies between empty and full by its
  utilization. MASS-GT overwrites rather than adds parcel vans' emissions on urban links, which
  undercounts them; NetSy adds them.
- `--method copert` (a contribution) reads `copert_vehicles.csv` (`vehicle`, `vehicle_type`),
  `copert_v_coefficients.csv` (`vehicle_type`, `pollutant`, `gradient_bin`, `payload_bin`,
  `alpha` to `eta`, `rf` as a fraction, optional `min_speed` and `max_speed`) and
  `non_exhaust_factors.csv` (`vehicle_type`, `pollutant`, `emission_factor` in g/km). Hot
  exhaust follows COPERT V's speed function at each load's speed, its link's grade and its
  payload, snapped to COPERT's bins; a speed outside a row's range counts as the nearest bound.
  Non-exhaust emissions are flat factors, reported as `<pollutant>_non_exhaust`.

## Canonical extension path

Actors and transactions can come from any source. NetSy's general core is designed to
accept explicitly calibrated scenario adapters:

1. actor/facility population synthesis or observed registers;
2. production/attraction regressions, gravity, and FRATAR OD balancing;
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

`od-marginals` and `od-flows` derive a commodity matrix the way MASS-GT's spatial interaction
freight module does: productions and attractions from linear regressions on location
attributes, then FRATAR balancing of a base matrix to them. Both are independent of agents and
write fractional flows that a case turns into shipment totals.

| file | fields | purpose |
|---|---|---|
| `location_attributes.csv` | `location_id`, attribute columns | The locations of the matrix and their attributes, such as jobs per sector; a location with all attributes empty keeps its prior totals. |
| `marginal_coefficients.csv` | `resource`, `attribute`, `production`, `attraction` | The regression coefficients. |
| `od_prior.csv` | `resource`, `origin_location_id`, `destination_location_id`, `weight` | The base matrix: supported OD pairs and their weights. |

`od-marginals` writes `productions.csv` and `attractions.csv` (`resource`, `location_id`,
`quantity`), which `od-flows` balances the prior to, writing `od_flows.csv`. Each FRATAR
iteration scales every destination's column to its attraction and then every origin's row to
its production, so the result matches the productions, and the attractions as closely as the
prior allows. It stops when the largest scaling factor of either pass is within 0.005 of one
(rounded to five decimals), when that measure stops changing, or after 50 iterations. Only
supported pairs between listed locations carry flow; a marginal without support stays unmet,
with a warning.

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

Network loads give every trip its cheapest path at the given speeds, all or nothing, and sum
trips and utilization per link, interval, vehicle and segment. Emissions are either MASS-GT's
factors, interpolated between empty and full by utilization, or COPERT V's speed function at
each load's speed, grade and payload, both times the link's length and trips.
