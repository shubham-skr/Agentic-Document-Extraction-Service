import json
from app.extraction import infer_type, make_field, parse_rentroll, parse_t12

def test_make_field_numeric_and_null():
 assert make_field('$1,234.50','[Page 1] $1,234.50',.9,typ='number')['value']==1234.5
 assert make_field(None,'bad',.9)['citation']==''

def test_infer_array():
 assert infer_type('broker_names','List of brokers')=='array'

def test_t12_rows():
 rows=[['']*18 for _ in range(9)]
 rows[7]=['510-000','RENTAL Income']+[None]*16
 rows[8]=['510-500','Gross Potential Rent']+[1]*12+[12,13,14,15]
 fields={'gl_code':{'primary':True,'description':'GL code'},'line_item':{'description':'name'},'amount_total':{'description':'total as number'},'amount_first_month':{'description':'first month number'},'amount_last_month':{'description':'last month number'},'months_with_activity':{'description':'count number'},'section':{'description':'section'},'property_name':{'description':'property'},'period_start':{'description':'date'},'period_end':{'description':'date'}}
 out=parse_t12(rows,'Report1',fields,'gl_code')
 assert len(out)==1 and out[0]['gl_code']['value']=='510-500'
