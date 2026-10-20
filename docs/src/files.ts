// The files NetSy reads and writes, and the `netsy synth` commands that turn
// some of them into others (src/netsy/cli/main.py).

export interface Command {
  name: string
  inputs: string[]
  outputs: string[]
  // Read only when present, or by an option.
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
  {
    name: 'od-marginals',
    inputs: ['location_attributes.csv', 'marginal_coefficients.csv', 'od_prior.csv'],
    outputs: ['productions.csv', 'attractions.csv'],
  },
  { name: 'od-flows', inputs: ['productions.csv', 'attractions.csv', 'od_prior.csv'], outputs: ['od_flows.csv'] },
  { name: 'facility-chains', inputs: ['shipments.gpkg', 'facilities.gpkg', 'facility_chain_steps.csv'], outputs: ['transaction_legs.gpkg'] },
  {
    name: 'parcel-demand',
    inputs: [
      'zones.gpkg', 'facilities.gpkg', 'skims.omx', 'parcel_attributes.csv', 'parcel_rates.csv', 'population.csv',
      'order_levels.csv', 'order_utility.csv', 'operator_shares.csv', 'parcel_settings.csv',
    ],
    outputs: ['parcel_demand.csv'],
  },
  {
    name: 'deliveries',
    inputs: ['parcel_demand.csv', 'zones.gpkg', 'skims.omx', 'delivery_settings.csv', 'delivery_departures.csv'],
    outputs: ['delivery_tours.gpkg'],
  },
  {
    name: 'trip-matrices',
    inputs: ['zones.gpkg', 'skims.omx', 'trip_attributes.csv', 'trip_rates.csv', 'trip_decay.csv'],
    outputs: ['trip_matrices.omx'],
  },
  {
    name: 'network-loads',
    inputs: [
      'network.gpkg', 'zones.gpkg', 'assignment_vehicles.csv', 'link_speeds.csv', 'road_costs.csv', 'time_intervals.csv',
    ],
    optional: ['tours.gpkg', 'delivery_tours.gpkg', 'trip_matrices.omx', 'matrix_assignment.csv'],
    outputs: ['network_loads.csv'],
  },
  {
    name: 'network-emissions',
    inputs: ['network_loads.csv', 'network.gpkg', 'emission_factors.csv'],
    // COPERT V (--method copert) instead of MASS-GT's factors.
    optional: ['copert_vehicles.csv', 'copert_v_coefficients.csv', 'non_exhaust_factors.csv'],
    outputs: ['network_emissions.csv'],
  },
]

// The browser reads NetSy's CSV and GeoPackage files; OMX skims are HDF5.
export const viewable = (filename: string) => /\.(csv|gpkg)$/.test(filename)

const acronyms: Record<string, string> = { od: 'OD', copert: 'COPERT', v: 'V' }

// "od_prior.csv" → "OD Prior".
export const titleCase = (filename: string) =>
  filename.replace(/\.[^.]+$/, '').split('_').map((word) => acronyms[word] ?? word[0].toUpperCase() + word.slice(1)).join(' ')
