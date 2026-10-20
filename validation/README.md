# MASS-GT / NetSy comparison audit

NetSy means **Network Emissions Synthesizer**. This audit distinguishes a port,
generalization, bug fix, execution improvement, and modelling contribution.
Agreement with the source model is a software/model-transfer check, not empirical
validation of a new study area or fleet.

## Reference and artifacts

- NetSy starting point: `56f04fdef6082f5aac7dcbfb15fe4f82ff877aa2`, branch `v0.4`.
- MASS-GT reference: **`4f727c3633bf5edabc1b0d0fa081a9e232bf169a`**. This is the
  local `sweden-run` reference, already including firm-seed, NumPy scalar,
  int32-predecessor and configurable output-city fixes. Do not attribute those
  pre-existing reference fixes to this continuation.
- Original Dutch evidence: `/workdir/sweden/mass-gt/data/NL_main/`;
  reference outputs: `runs/NL_REF/`; UCC: `runs/NL_UCC/`.
- Built NetSy baseline: `/workdir/netherlands/`; independent upstream-stage runs:
  `/workdir/netsy-validation/seed-{1,2,3}/`.
- NetSy scenarios: `/workdir/netherlands-ucc/`, `/workdir/netherlands-microhub/`.
- Controlled assignment: `/workdir/netsy-validation/reference-trips/`.
- Contributions: `/workdir/netsy-validation/savings/` and `copert/`.
- `results/*.json` contains computed comparisons. `results/metrics.json` covers
  the pipeline; the presentation is generated from these files. Large case data
  are not committed. `results/manifest.json` identifies available files/revisions.

The reference data represent the Dutch study area and its external gateways;
“Netherlands” here does not mean an observed, exhaustive national freight model.

## Comparison design

1. Use the source's own evidence and coefficients. Keep all Dutch classification,
   coefficient mapping and compatibility decisions in case adapters.
2. Check deterministic stages directly: SIF by resource/OD cell; parcel demand
   by operator/zone; van matrices by OD cell.
3. Run NetSy seeds **1, 2, 3** through agents, shipments, tours, parcels and service
   matrices. Run the complete assignment/emissions chain for seed 1. Compare
   counts, retained size, tonnes, vehicle shares, tours, VKT, empty VKT and
   quantity-distance against one fixed MASS-GT reference.
4. Feed **MASS-GT's original tours, parcel schedule and original van matrices**
   into NetSy assignment and factors. This isolates downstream agreement from
   upstream stochastic differences. Report per-link errors, not only totals.
5. Compare raw/minimally repaired scenario results with NetSy, and correct the
   reference selection logic separately where necessary. Preserve original files
   and distinguish a corrected reference from an unmodified source result.
6. Compare contributions against the corrected port on the same evidence. Never
   count the parcel stop-index repair as a savings-algorithm gain.

Three NetSy seeds give sensitivity ranges, **not** confidence intervals or a
formal stochastic equivalence test. They do not estimate MASS-GT's own seed
variance. No calibration was performed to force these runs to match the reference.

## Stage inventory

| Source stage | NetSy counterpart | Port / generalization | Fix / execution change / contribution |
|---|---|---|---|
| FS | `agents` | Arbitrary size totals and class distributions by strata | Seeded NumPy generator; shared zone sampling. Source reference already fixes firm-size seeding. |
| SIF | `od-marginals`, `od-flows` | Attributes, coefficients, resources, locations and priors supplied as tables | Shared FRATAR core. Rounded Dutch matrix agrees; unsupported marginals warn. |
| SHIP | `shipments`, `facility-routing` | Typed agent/facility/zone ends, generic strata, choice terms and policy-area mappings | Deduplicate UCC vehicle shares over fuel rows. Stable parent/leg identity; fractional quantities. |
| TOUR | `tours` | Generic carrier/facility types, windows and end-tour terms | Explicit carriers and observed powertrains; scenario fuel choices with explicit fallback; compiled improvement/cached proximity. |
| PARCEL_DMND | `parcel-demand`, `parcel-routing` | Population strata, operator shares, arbitrary facility types and eligibility | Correct hub identifiers, zone indexing and per-operator selection; preserve final demand separately from transfers. |
| PARCEL_SCHD | `deliveries` | Per-vehicle capacity, drop time, relative speed, facility/operator grouping | Correct stop indices; add hub-aware downstream operations; optional Clarke–Wright savings. |
| SERVICE | `trip-matrices` | Generic attributes, segments, regressions and gravity costs | UCC powertrain classification uses endpoint flags, not loop positions. Small numerical OD residuals remain. |
| TRAF | `network-loads` | Arbitrary directed networks, speed classes, intervals, cost rules and trip sources | Sparse origin-wise paths; bounded workers; powertrain-aware routing; optional perturbed-cost averaging; no eight-neighbour arc cap; Parquet. |
| Emissions in TRAF | `network-emissions` | Source factors or declared COPERT types/coefficients | Accumulate urban parcel factors; keep combustion; optional payload-bin strata, explicit exhaust/non-exhaust multipliers; missing COPERT coverage fails. |
| OUTP | `indicators`, comparison scripts, visualizer | Tidy totals and arbitrary attribute groups rather than Dutch labels | General reporting boundary; does not reproduce every source-specific indicator layout. |

### Reference repairs and execution

The first UCC failure was an actual midnight inconsistency: the tour matrices
used `>24`, assignment used `>=24`. The single failing trip is **5419 → 152,
segment 2, departure 24.0 h** (internal indices 4708 → 151). The 24 matrices
contained 219,215 trips versus 219,216 tours. `repair_reference_midnight.py`
rebuilds them with modulo 24 and retains originals as `.txt.original`.

A second execution fault was the `nCPU > 1` guard around the entire hybrid-van
search, despite an inner single-worker branch. `reference_assignment.patch`
repairs that dispatch; it does not change cost functions or powertrain behaviour.

A subsequent run was genuinely killed under memory pressure. `run_reference.py`
backs large zero arrays by disk, converts the same LIL graph to CSR once, and
caches the reference predecessor arrays by graph/indices content hash. Dtypes,
zero initialization, route search and calculation order are retained. This is an
execution change, not a calibration or replacement assignment. The complete
UCC TRAF and OUTP run is logged in `NL_UCC_traf_complete.log`.

The collaborative microhub scenario initially failed because `.at` received a
boolean mask. `reference_microhub.patch` repairs this compatibility issue (and
the malformed per-courier DataFrame expression). A separate corrected-selection
run also fixes the selected-hub list mapping, one-based zone lookup and hub
coordinate lookup; see `reference_microhub_corrected.patch`. Both results are
retained under `runs/NL_MIC_collab_EB/` and `runs/NL_MIC_collab_EB_corrected/`.
NetSy's corrected hub-to-recipient quantities match the latter exactly.

### Differences to preserve in interpretation

- A source UCC vehicle share is repeated for each combustion row. NetSy counts a
  vehicle share once, then chooses combustion separately. A missing fuel
  distribution uses the explicit scenario fallback, not a uniform random fuel.
- Source freight hybrid volumes and emissions can use different route sets.
  NetSy uses the same physical route for loads and its emissions.
- Source service-van UCC checks use destination-list position. NetSy uses actual
  endpoint flags. Connector/cost policy handling is explicit case data.
- The source's eight-neighbour link lookup can omit a traversed arc. NetSy has
  no such cap. Residual connector differences also include shortest-path tie
  choices; the audit reports their magnitude instead of claiming exact loads.
- Source urban parcel factors overwrite earlier emissions on a link/hour.
  The fixed-input control predicts the correction analytically and reports the
  residual. Float32 output introduces tiny rounding differences.
- The existing Dutch adapter deliberately retains the reversed import/export
  reading and external-zone service mapping for reference compatibility.
  These quirks are **not** in the general core and are not presented as fixes.
- The demonstrated NetSy UCC case explicitly pools outbound parcels at the serving hub (`pool_operators=1`), whereas the source initially clusters by the original depot. This is an operational extension, not a pure-port equivalence claim. With pooling disabled, `delivery_group` retains original-depot separation.
- Microhub demand/rerouting belongs to MASS-GT. NetSy's contribution is completing
  hub-aware downstream operations; the source scheduler discards the mode/hub
  distinctions. It is not an independent source-validated microhub tour model.

## Contributions

**Savings:** compare MASS-GT's raw parcel VKT, the corrected stop-order port, and
Clarke–Wright savings, at the same 228,707 customer parcels and capacity. Report
both VKT and tour counts.

**COPERT:** the Dutch example reports CO, NOx, exhaust PM and derived CO2 on the
same seed-1 trips. `network-loads --payload-strata` keeps the published payload
bins separate before nonlinear factors are evaluated. Coefficients come from
the supplied July 2026 EMEP/EEA Appendix 4 workbook. The declared scenario fleet
is Euro VI D/E diesel trucks and Euro 6 d/e vans, **not** an observed Dutch fleet.
The network run assumes flat grades; the curve plot explicitly varies grade.
This is a model/fleet sensitivity, not evidence of better empirical predictions.

Energy consumption is used only to derive CO2 at 74.1 g/MJ, never reported as grams
of a pollutant called EC. N2O/NH3 lacked full vehicle coverage and are not reported.
Microhub operation assumptions: the supplied collaborative EB hub set is used; bicycle capacity is 13 parcels and speed 17.5 km/h. Bicycles are excluded from motorway/autoweg links and have a separate speed class. The feeder capacity is 1,800 parcels; bulk hub transfer time is assumed zero, customer drop time retains the source setting. These operating assumptions are not calibrated observations.

The example non-exhaust input is empty. The core supports independently supplied
non-exhaust factors and powertrain/weight scenario multipliers, but no Dutch
non-exhaust estimate or automatic battery-weight relationship is claimed.
The advisor paper informs the speed/grade/payload, hub and fleet extension:
Dias & Jenelius (2026), https://doi.org/10.1016/j.ubtr.2026.100031.

## Reproduction

Use Python 3.11–3.14 with NetSy's project dependencies. Plots additionally use
matplotlib; the presentation uses TeX Live, Beamer and `catppuccinpalette`.
The model and reference environments remain separate (reference: Python 3.10,
pandas 1.5, numba 0.56).

```sh
# Built case, then isolated seed sensitivity runs.
PYTHONPATH=src .venv/bin/python validation/seed_runs.py
# Source trips isolate assignment and factors.
PYTHONPATH=src .venv/bin/python validation/prepare_case.py /workdir/netsy-validation/reference-trips
PYTHONPATH=src .venv/bin/python validation/import_reference.py REF /workdir/netsy-validation/reference-trips
# import_reference.py also imports the original van matrices.
PYTHONPATH=src .venv/bin/python validation/run_case.py /workdir/netsy-validation/reference-trips --only network-loads network-emissions
# Facility scenarios.
PYTHONPATH=src .venv/bin/python validation/build_scenario.py ucc /workdir/netherlands-ucc
PYTHONPATH=src .venv/bin/python validation/run_case.py /workdir/netherlands-ucc --scenario ucc --assignment
PYTHONPATH=src .venv/bin/python validation/build_scenario.py microhub /workdir/netherlands-microhub
PYTHONPATH=src .venv/bin/python validation/run_case.py /workdir/netherlands-microhub --scenario microhub --assignment
# COPERT on the same saved trips, in an isolated directory.
PYTHONPATH=src .venv/bin/python validation/run_case.py /workdir/netsy-validation/copert --only network-loads network-emissions --payload-strata --method copert
# Measurements, then the slides.
PYTHONPATH=src .venv/bin/python validation/metrics.py
PYTHONPATH=src .venv/bin/python validation/compare_assignment.py
PYTHONPATH=src .venv/bin/python presentation/build.py
cd presentation && pdflatex -interaction=nonstopmode -halt-on-error main.tex
```

Case adapters and run scripts overwrite **their named outputs only**. Isolation
helpers never link an output that a seed run will regenerate. Validation
assignments serialize through a file lock to limit memory pressure. Stage logs
retain failures/retries. Wall times from concurrent or paused jobs are not used
as controlled performance comparisons.

## Validation boundary

This is the standard Dutch freight/parcel/service pipeline plus UCC and the
collaborative electric-bicycle microhub configuration. Optional crowdshipping,
selected-link analysis and every historical release/policy branch are **not**
benchmarked. Reporting is generalized, not every bespoke OUTP table reimplemented.
No claim is made that every MASS-GT option or every possible general stratum
configuration has been validated. Stockholm preparation remains the next study
case, outside this Dutch comparison.
