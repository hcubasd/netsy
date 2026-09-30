# netsy

Synthesizes aggregate supply and demand, and the capacity and need distributions of individual agents, from effects and thresholds files.

## Install

```
pip install netsy
```

Requires Python 3.11 or newer.

## Usage

Run each command in the directory holding its input files.

```
netsy synth supply       # supply_effects.csv + supply_thresholds.csv -> supply.csv
netsy synth demand       # demand_effects.csv + demand_thresholds.csv -> demand.csv
netsy synth capacities   # capacity_effects.csv + capacity_thresholds.csv -> capacities.csv
netsy synth needs        # need_effects.csv + need_thresholds.csv -> needs.csv
netsy synth agents       # supply/demand/capacities/needs + zones.gpkg -> agents.gpkg
netsy synth desire-lines # agents.gpkg -> desire_lines.gpkg
netsy synth network-loads --seed 1
netsy synth network-emissions
```

An existing output file is only replaced with `--force`.
`agents`, `desire-lines`, and `network-loads` make random draws; pass `--seed` to reproduce them.

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
`{resource}_need` columns, and point geometry. `desire_lines.gpkg` contains one
provider-to-consumer transaction per row:

| resource | quantity | origin_agent_id | geometry |
|---|---|---|---|
| resource_1 | 2 | 1 | LINESTRING (0.42 0.71, 0.38 0.65) |

For each resource, a provider is selected by remaining capacity and matched with
consumers until the provider is depleted. Consumers are selected by their remaining need
and distance-weighted proximity. A desire line starts at its provider and ends at its
consumer.

`network-loads` combines ten supplied files. It does not synthesize their contents:

| file | purpose |
|---|---|
| `network.gpkg` | Directed road links: `link_id`, `grade`, `road_type`, `oneway`, and line geometry. |
| `desire_lines.gpkg` | Provider-to-consumer resource transactions. |
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

`network_loads.csv` is the only output. It has a row per directional link, interval,
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

## Model

Each resource $r$ is an ordinal outcome under a cumulative-logit model, with $\sigma(x) = 1 / (1 + e^{-x})$. A stratum $s = (v_1, \dots, v_D)$ takes one value from each of the $D$ dimensions, and its linear predictor is the sum of the effects $\gamma$ of those values:

$$\beta_{r,s} = \sum_{d=1}^{D} \gamma_{r,d,v_d}$$

If any of these effects is empty the pair $(s, r)$ is omitted, which is not the same as an effect of zero. With levels $\ell_{r,1} < \dots < \ell_{r,K_r}$ and thresholds $\mu_{r,1} \le \dots \le \mu_{r,K_r-1}$, the cumulative probability of level $k$ is

$$F_{r,s}(k) = \sigma(\mu_{r,k} - \beta_{r,s})$$

with $F_{r,s}(0) = 0$ and $F_{r,s}(K_r) = 1$, and the probability of each level is the difference

$$p_{r,s}(\ell_{r,k}) = F_{r,s}(k) - F_{r,s}(k-1)$$

Capacities and needs are these probabilities. Supply and demand are the expected level rounded to a whole unit:

$$A_{r,s} = \mathrm{round}\left( \sum_{k=1}^{K_r} \ell_{r,k} p_{r,s}(\ell_{r,k}) \right)$$
