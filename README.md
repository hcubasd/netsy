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
```

An existing output file is only replaced with `--force`. The output is a deterministic function of its two inputs.

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

## Model

Each resource $r$ is an ordinal outcome under a cumulative-logit model, with $\sigma(x) = 1 / (1 + e^{-x})$. A stratum $s = (v_1, \dots, v_D)$ takes one value from each of the $D$ dimensions, and its linear predictor is the sum of the effects $\gamma$ of those values:

$$\beta_{r,s} = \sum_{d=1}^{D} \gamma_{r,d,v_d}$$

If any of these effects is empty the pair $(s, r)$ is omitted, which is not the same as an effect of zero. With levels $\ell_{r,1} < \dots < \ell_{r,K_r}$ and thresholds $\mu_{r,1} \le \dots \le \mu_{r,K_r-1}$, the cumulative probability of level $k$ is

$$F_{r,s}(k) = \sigma(\mu_{r,k} - \beta_{r,s})$$

with $F_{r,s}(0) = 0$ and $F_{r,s}(K_r) = 1$, and the probability of each level is the difference

$$p_{r,s}(\ell_{r,k}) = F_{r,s}(k) - F_{r,s}(k-1)$$

Capacities and needs are these probabilities. Supply and demand are the expected level rounded to a whole unit:

$$A_{r,s} = \operatorname{round}\left( \sum_{k=1}^{K_r} \ell_{r,k} p_{r,s}(\ell_{r,k}) \right)$$
