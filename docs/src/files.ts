// The files NetSy reads and writes, and the `netsy synth` commands that turn
// some of them into others (src/netsy/cli/main.py).

export interface Command {
  name: string
  inputs: string[]
  outputs: string[]
  // Read only when present, or when asked (`--transactions`).
  optional?: string[]
}

export const commands: Command[] = [
  {
    name: 'agents',
    inputs: ['zones.gpkg', 'size_totals.csv', 'size_classes.csv'],
    outputs: ['agents.gpkg'],
  },
  {
    name: 'shipments',
    inputs: [
      'zones.gpkg', 'agents.gpkg', 'skims.omx', 'production_rates.csv', 'consumption_rates.csv', 'shipment_totals.csv',
      'flow_types.csv', 'distance_decay.csv', 'shipment_sizes.csv', 'shipment_vehicles.csv', 'vehicle_choice.csv',
    ],
    optional: ['facilities.gpkg', 'delivery_windows.csv', 'delivery_choice.csv'],
    outputs: ['shipments.gpkg'],
  },
  {
    name: 'tours',
    inputs: [
      'shipments.gpkg', 'zones.gpkg', 'skims.omx', 'shipment_vehicles.csv', 'tour_settings.csv',
      'end_tour_first.csv', 'end_tour_later.csv',
    ],
    optional: ['facilities.gpkg'],
    outputs: ['tours.gpkg', 'tour_shipments.csv'],
  },
  { name: 'od-flows', inputs: ['productions.csv', 'attractions.csv', 'od_prior.csv'], outputs: ['od_flows.csv'] },
  { name: 'facility-chains', inputs: ['shipments.gpkg', 'facilities.gpkg', 'facility_chain_steps.csv'], outputs: ['transaction_legs.gpkg'] },
  {
    name: 'network-loads',
    inputs: [
      'network.gpkg', 'shipments.gpkg', 'departures.csv', 'time_intervals.csv', 'dwell_times.csv', 'vehicles.csv',
      'vehicle_velocities.csv', 'vehicle_capacities.csv', 'road_capacities.csv', 'alternative_specific_constants.csv',
    ],
    optional: ['transaction_legs.gpkg'],
    outputs: ['network_loads.csv'],
  },
  {
    name: 'network-emissions',
    inputs: ['network_loads.csv', 'network.gpkg', 'vehicles.csv', 'copert_v_coefficients.csv', 'emission_factors.csv'],
    outputs: ['network_emissions.csv'],
  },
]

// The browser reads NetSy's CSV and GeoPackage files; OMX skims are HDF5.
export const viewable = (filename: string) => /\.(csv|gpkg)$/.test(filename)

const acronyms: Record<string, string> = { od: 'OD', copert: 'COPERT', v: 'V' }

// "od_prior.csv" → "OD Prior".
export const titleCase = (filename: string) =>
  filename.replace(/\.[^.]+$/, '').split('_').map((word) => acronyms[word] ?? word[0].toUpperCase() + word.slice(1)).join(' ')
