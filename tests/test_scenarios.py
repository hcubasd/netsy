"""Cross-stage conservation and policy regression tests."""
import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point
from netsy.synth.facility_routing import facility_routing
from netsy.synth.parcel_routing import parcel_routing
from netsy.helpers.combustion import tour_combustion, emission_multipliers
from netsy.synth.network_emissions import emissions_by_factors
from tests.test_tours import _zones, _shipments, _settings, _end, _facilities, ZONES, STEPS, DAY, GO_ON
from netsy.synth.tours import tours
from tests.test_network import _loads, _trips, _csv, _network, _load_rows


def frame(rows, columns): return pd.DataFrame(rows,columns=columns)


def freight(origin=2,destination=3,flags=(0,1,1,0),areas=('a','a','b','b')):
    zones=_zones();zones['flag']=flags;zones['hub']=['h1']*2+['h2']*2;zones['area']=areas
    facilities=gpd.GeoDataFrame({'facility_id':['h1','h2'],'facility_type':['ucc']*2,'zone_id':[1,4]},geometry=[Point(0,0),Point(3,0)],crs=zones.crs)
    s=_shipments([(origin,destination,2.5,'van','food',*DAY,None)])
    settings=frame([('zone_column','flag'),('facility_column','hub'),('area_column','area')],['setting','value'])
    probabilities=frame([('food',1)],['segment','probability'])
    vehicles=frame([('food','van',1)],['segment','vehicle','share'])
    return s,zones,facilities,settings,probabilities,vehicles


@pytest.mark.parametrize('origin,destination,legs',[(1,4,1),(1,3,2),(2,4,2),(2,3,3),(2,2,1)])
def test_facility_routing_preserves_each_consignment_on_connected_legs(origin,destination,legs):
    result=facility_routing(*freight(origin,destination),np.random.default_rng(0))
    assert len(result)==legs
    assert result.transaction_id.is_unique and result.parent_transaction_id.nunique()==1
    assert result.quantity.tolist()==[2.5]*legs
    assert result.origin_zone_id.iloc[0]==origin and result.destination_zone_id.iloc[-1]==destination
    assert result.destination_zone_id.iloc[:-1].tolist()==result.origin_zone_id.iloc[1:].tolist()
    assert result.leg.tolist()==list(range(1,legs+1))


def test_tours_honor_explicit_carriers_and_parent_quantity():
    s=_shipments([(1,2,1,'van','food',*DAY,None),(1,3,1,'van','food',*DAY,None)])
    s['carrier']=['named_a','named_b'];s['parent_transaction_id']=[7,7]
    trips,parts=tours(_zones(),None,(ZONES,STEPS,STEPS*10),s,frame([('van',4)],['vehicle','capacity']),_settings(),_end(GO_ON),_end(GO_ON),np.random.default_rng(0))
    assert set(trips.carrier)=={'named_a','named_b'} and trips.tour_id.nunique()==2
    assert parts.groupby('parent_transaction_id').quantity.sum().to_dict()=={7:2}


def test_combustion_rules_choose_by_actual_zone_flags():
    trips=frame([(1,'dc','van',1,2),(1,'dc','van',2,1),(2,'independent_1','van',2,3)],['tour_id','carrier','vehicle','origin_zone_id','destination_zone_id'])
    rules=frame([('distribution_centre',None,'electric',1),('independent','none','fuel',1),('independent','some','hybrid',1)],['carrier_type','zone_relation','combustion','share'])
    result=tour_combustion(trips,_zones(),_facilities(),rules,'urban',np.random.default_rng(0))
    assert result.combustion.tolist()==['electric','electric','fuel']


def test_hybrid_routing_uses_a_different_cost_and_preserves_powertrain_counts():
    trips=_trips([(7,'lorry',.5,1,3,'food'),(7,'lorry',.5,1,3,'food')]);trips['combustion']=['fuel','hybrid']
    costs=frame([('motorway','truck',1000,'fuel')],['road_type','speed_class','cost','combustion'])
    loads=_loads(trips,road_costs=costs)
    assert set(loads[loads.combustion=='fuel'].link_id)=={'ab','bc'}
    assert set(loads[loads.combustion=='hybrid'].link_id)=={'ad','dc'}


def test_electric_exhaust_zero_does_not_imply_zero_non_exhaust():
    loads=_load_rows();loads['combustion']='electric'
    rules=frame([('electric','exhaust',0)],['combustion','source','multiplier'])
    factors=_csv([('lorry','street','co2',100,300)],['vehicle','road_type','pollutant','empty','full'])
    assert emissions_by_factors(loads,_network(),factors,rules).co2.sum()==0
    assert (emission_multipliers(loads,_network(),rules,'pm','non_exhaust')==1).all()


def test_parcel_hubs_preserve_customer_demand_and_select_nearest_eligible_operator_hub():
    zones=_zones();zones['flag']=2
    hubs=gpd.GeoDataFrame({'facility_id':['h1','h2','other'],'facility_type':['hub']*3,'zone_id':[2,3,4],'operator':['a','a','b']},geometry=[Point(1,0),Point(2,0),Point(3,0)],crs=zones.crs)
    demand=frame([(4,'a','depot',1,31)],['destination_zone_id','operator','facility_id','origin_zone_id','parcels'])
    settings=frame([('flag_column','flag'),('facility_type','hub'),('selection','nearest'),('probability',1),('operator_column','operator')],['setting','value'])
    shares=frame([('robot',1,.5,'bike')],['vehicle','share','maximum_distance','fallback_vehicle'])
    routed=parcel_routing(demand,zones,hubs,(ZONES,STEPS,STEPS),settings,shares,np.random.default_rng(0))
    assert routed[routed.final_delivery].parcels.sum()==31
    assert routed.parcels.sum()==62
    final=routed[routed.leg=='outbound'].iloc[0]
    assert final.facility_id=='h2' and final.vehicle=='bike' and final.origin_zone_id==3


def test_invalid_routing_probability_fails():
    args=list(freight());args[4]['probability']=1.2
    with pytest.raises(ValueError,match='invalid probabilities'): facility_routing(*args,np.random.default_rng(0))


def test_payload_strata_do_not_average_away_nonlinear_emission_inputs():
    from tests.test_network import _zones as zones, _speeds
    from netsy.synth.network_loads import network_loads
    trips=_trips([(7,'lorry',0,1,3,'food'),(7,'lorry',1,1,3,'food')])
    args=(_network(),zones(),_csv([('lorry','truck',10,1)],['vehicle','speed_class','cost_per_hour','cost_per_km']),_speeds(),
          _csv([],['road_type','speed_class','cost']),_csv([('day',0,24)],['time_interval','start','end']),{'tours':trips},None,None)
    mixed=network_loads(*args)
    stratified=network_loads(*args,payload_strata=True)
    assert mixed.utilization.unique().tolist()==[.5]
    assert set(stratified.utilization)=={0,1}
    assert stratified.trips.sum()==mixed.trips.sum()


def test_hybrid_multiplier_matches_numeric_network_attributes_read_from_csv():
    loads=_load_rows();loads['combustion']='hybrid'
    network=_network();network['restricted']=[1,0,0,0,0,0,0,0]
    rules=frame([('hybrid','exhaust','1.0',0)],['combustion','source','restricted','multiplier'])
    assert emission_multipliers(loads,network,rules,'nox','exhaust').tolist()==[0,1]


def test_multiple_route_samples_preserve_counts_and_repeat_with_seed():
    from tests.test_network import _zones as zones, _speeds
    from netsy.synth.network_loads import network_loads
    args=(_network(),zones(),_csv([('lorry','truck',10,1)],['vehicle','speed_class','cost_per_hour','cost_per_km']),_speeds(),
          _csv([],['road_type','speed_class','cost']),_csv([('day',0,24)],['time_interval','start','end']),
          {'trips':_trips([(7,'lorry',.5,1,3,'food')])},None,None)
    first=network_loads(*args,route_samples=3,seed=42)
    second=network_loads(*args,route_samples=3,seed=42)
    pd.testing.assert_frame_equal(first,second)
    assert first.trips.sum()==pytest.approx(2)


def test_observed_powertrains_are_preserved_and_never_mixed_in_one_tour():
    s=_shipments([(1,2,1,'van','food',*DAY,None),(1,3,1,'van','food',*DAY,None)])
    s['combustion']=['fuel','electric']
    trips,parts=tours(_zones(),None,(ZONES,STEPS,STEPS*10),s,frame([('van',4)],['vehicle','capacity']),_settings(),_end(GO_ON),_end(GO_ON),np.random.default_rng(0))
    assert set(trips.combustion)=={'fuel','electric'}
    assert trips.tour_id.nunique()==2
    assert all(group.combustion.nunique()==1 for _,group in trips.groupby('tour_id'))


def test_general_output_indicators_preserve_units_and_grouping():
    from netsy.synth.indicators import indicators
    loads=pd.DataFrame({'link_id':['a','b'],'vehicle':['truck','van'],'trips':[2.,3.],'utilization':[.5,.5]})
    report=indicators('loads',loads,['','vehicle'],{'a':1,'b':2})
    total=report[(report.group=='all')&(report.indicator=='vehicle_km')].iloc[0]
    assert total.value==8 and total.unit=='vehicle_km'
    assert report[(report.group=='vehicle')&(report.group_value=='van')&(report.indicator=='vehicle_km')].value.iloc[0]==6


def test_excluded_road_types_are_not_used_by_the_mode():
    trips=_trips([(7,'lorry',.5,1,3,'food')])
    costs=frame([('motorway','truck',0,'exclude')],['road_type','speed_class','cost','operation'])
    assert set(_loads(trips,road_costs=costs).link_id)=={'ab','bc'}


def test_facility_routing_preserves_text_zone_ids_and_actor_ids():
    args=list(freight(2,3));labels={i:f'{i:03d}' for i in range(1,5)}
    for column in ['origin_zone_id','destination_zone_id']:args[0][column]=args[0][column].map(labels)
    args[0]['origin_agent_id']=['producer'];args[0]['destination_agent_id']=['consumer']
    args[1]['zone_id']=args[1].zone_id.map(labels);args[2]['zone_id']=args[2].zone_id.map(labels)
    routed=facility_routing(*args,np.random.default_rng(0))
    assert routed.origin_zone_id.tolist()==['002','001','004']
    assert routed.destination_zone_id.tolist()==['001','004','003']
    assert routed.origin_agent_id.iloc[0]=='producer' and routed.destination_agent_id.iloc[-1]=='consumer'
