// The files NetSy reads and writes, and the `netsy synth` commands that turn
// some of them into others (src/netsy/cli/main.py).

export interface Command {
  name: string
  inputs: string[]
  outputs: string[]
  // Read only when asked (`--transactions`).
  optional?: string[]
}

export const commands: Command[] = [
  {
    name: 'agents',
    inputs: ['zones.gpkg', 'size_totals.csv', 'size_classes.csv'],
    outputs: ['agents.gpkg'],
  },
  { name: 'desire-lines', inputs: ['agents.gpkg'], outputs: ['desire_lines.gpkg'] },
  { name: 'od-flows', inputs: ['productions.csv', 'attractions.csv', 'od_prior.csv'], outputs: ['od_flows.csv'] },
  { name: 'facility-chains', inputs: ['desire_lines.gpkg', 'facilities.gpkg', 'facility_chain_steps.csv'], outputs: ['transaction_legs.gpkg'] },
  {
    name: 'network-loads',
    inputs: [
      'network.gpkg', 'desire_lines.gpkg', 'departures.csv', 'time_intervals.csv', 'dwell_times.csv', 'vehicles.csv',
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

const acronyms: Record<string, string> = { od: 'OD', copert: 'COPERT', v: 'V' }

// "od_prior.csv" → "OD Prior".
export const titleCase = (filename: string) =>
  filename.replace(/\.[^.]+$/, '').split('_').map((word) => acronyms[word] ?? word[0].toUpperCase() + word.slice(1)).join(' ')
