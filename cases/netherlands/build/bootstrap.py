"""Initialize the study-zone layer from MASS-GT, with no bundled case data."""
import os,sys
from pathlib import Path
import geopandas as gpd
source=Path(os.environ.get('MASSGT_INPUT','/workdir/sweden/mass-gt/data/NL_main'))
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
if not (out/'zones.gpkg').exists():
 z=gpd.read_file(source/'data/Zones_v6.shp').set_crs(28992,allow_override=True)
 print('Source zone columns:',z.columns.tolist())
 municipality='GEMEENTEN' if 'GEMEENTEN' in z else 'Gemeentena'
 z=z.rename(columns={'AREANR':'zone_id',municipality:'municipality'})
 z['zone_name']=z.zone_id.astype(str)
 z[['zone_id','zone_name','municipality','geometry']].to_file(out/'zones.gpkg',driver='GPKG')
