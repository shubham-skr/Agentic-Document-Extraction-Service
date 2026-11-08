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


def test_confidence_string_is_coerced():
 field=make_field('Tenant Inc.','[Paragraph 1] Tenant Inc.', '0.95')
 assert field['confidence']==0.95

def test_malformed_json_bare_keys_and_trailing_comma():
 from app.llm import parse_json
 assert parse_json('{fields: {tenant: {value: "Acme",},},}') == {'fields': {'tenant': {'value': 'Acme'}}}

def test_truncated_json_preserves_completed_fields():
 from app.llm import parse_json
 result=parse_json('{"tenant":{"value":"Acme","citation":"[Paragraph 1] Acme","confidence":0.9},"landlord":{"value":"Landlord","citation":"[Paragraph')
 assert result['tenant']['value']=='Acme'

def test_citation_accepts_locator_plus_snippet():
 from app.extraction import _citation_ok
 source='[Paragraph 1] Tenant: Acme Properties LLC is the lessee under this Agreement.'
 assert _citation_ok('[Paragraph 1] Tenant: Acme Properties LLC is the lessee',source)


def test_sqlite_job_writes_are_committed(tmp_path, monkeypatch):
 import sqlite3
 from app import storage
 db=tmp_path/'jobs.sqlite3'
 monkeypatch.setattr(storage.settings, 'database_path', str(db))
 storage.init_db()
 stamp=storage.now()
 row={'job_id':'job-1','org_id':'org-1','status':'PENDING','stage':'QUEUED',
      'created_at':stamp,'updated_at':stamp,'file_path':'/tmp/f','filename':'f.csv',
      'schema_json':'{}','webhook_url':None,'request_hash':'hash-1'}
 storage.create_job(row)
 assert storage.get_job('job-1','org-1')['status']=='PENDING'
 storage.update_job('job-1',status='SUCCESS',stage='COMPLETE',result={'entries':[]})
 assert storage.get_job('job-1','org-1')['status']=='SUCCESS'


def test_docx_pipeline_uses_grouped_json_and_completes_without_network(tmp_path, monkeypatch):
    import asyncio
    import json as json_module
    from docx import Document
    from app.config import settings
    from app.graph import execute
    import app.llm as llm_module
    from app.llm import LLM

    docx_path = tmp_path / 'lease.docx'
    doc = Document()
    doc.add_paragraph('COMMERCIAL LEASE AGREEMENT')
    doc.add_paragraph('Tenant: Acme Properties LLC')
    doc.add_paragraph('Landlord: Example Holdings LLC')
    doc.save(docx_path)

    schema = {'name': 'lease_abstraction', 'fields': {
        'tenant_name': {'name': 'Tenant', 'description': 'Full legal name of tenant.'},
        'landlord_name': {'name': 'Landlord', 'description': 'Full legal name of landlord.'},
        'rent_start_date': {'name': 'Rent Start Date', 'description': 'Date base rent commences.'},
    }}

    async def fake_complete(self, messages, model=None, temperature=0, max_tokens=4000, retries=1, json_mode=True):
        request = json_module.loads(messages[-1]['content'])
        keys = list(request['fields'])
        self.calls += 1
        self.by_model.setdefault(model or settings.fast_model, {'calls': 0, 'tokens_in': 0, 'tokens_out': 0, 'cost_usd': 0.0})
        self.by_model[model or settings.fast_model]['calls'] += 1
        return json_module.dumps({key: {'value': None, 'citation': '', 'confidence': 0} for key in keys})

    monkeypatch.setattr(settings, 'llm_api_key', 'test-key-never-used-for-network')
    monkeypatch.setattr(llm_module, 'AsyncOpenAI', None)
    monkeypatch.setattr(LLM, 'complete', fake_complete)
    result = asyncio.run(execute(str(docx_path), schema))
    assert len(result['entries']) == 1
    assert set(result['entries'][0]) == set(schema['fields'])
    assert result['metadata']['model_calls'] == 1
    assert result['metadata']['parse_failures'] == 0
