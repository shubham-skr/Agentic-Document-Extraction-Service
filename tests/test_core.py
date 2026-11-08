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
    assert result['metadata']['model_calls'] == 5
    assert result['metadata']['parse_failures'] == 0


def test_budget_pdf_parser_recovers_all_sample_rows_when_fixture_available():
    import json
    from pathlib import Path
    from app.extraction import extract_budget_pdf
    root = Path(__file__).resolve().parents[1]
    pdf = root / 'sample/sample-data-documents/budget_001.pdf'
    if not pdf.exists():
        import pytest
        pytest.skip('assignment sample documents are intentionally not packaged')
    schema = json.loads((root / 'sample/schemas/budget_variance.json').read_text())
    rows = extract_budget_pdf({'kind': 'pdf', 'source_path': str(pdf)}, schema)
    assert rows is not None and len(rows) == 55
    assert rows[0]['gl_code']['value'] == '6101-0000'
    assert rows[1]['explanation_of_variance']['value'].startswith('The Meridian')


def test_offering_pdf_parser_matches_sample_when_fixture_available():
    import json
    from pathlib import Path
    from app.extraction import extract_offering_pdf
    root = Path(__file__).resolve().parents[1]
    pdf = root / 'sample/sample-data-documents/om_001.pdf'
    if not pdf.exists():
        import pytest
        pytest.skip('assignment sample documents are intentionally not packaged')
    schema = json.loads((root / 'sample/schemas/offering_memorandum.json').read_text())
    rows = extract_offering_pdf({'kind': 'pdf', 'source_path': str(pdf)}, schema)
    assert rows is not None and len(rows) == 1
    assert rows[0]['property_name']['value'] == 'Marlowe Park Modern Apartments'
    assert rows[0]['unit_types']['value'][0] == 'Aspen'
    assert rows[0]['noi_proforma']['value'] == 3521352



def test_docx_parser_preserves_paragraph_table_order(tmp_path):
    from docx import Document
    from app.parsers import parse_docx
    path = tmp_path / 'order.docx'
    doc = Document()
    doc.add_paragraph('Before table')
    table = doc.add_table(rows=1, cols=1)
    table.cell(0, 0).text = 'Inside table'
    doc.add_paragraph('After table')
    doc.save(path)
    parsed = parse_docx(path)
    assert parsed['text'].index('Before table') < parsed['text'].index('Inside table')
    assert parsed['text'].index('Inside table') < parsed['text'].index('After table')


def test_lease_targeted_retry_recovers_null_field_with_verbatim_evidence(tmp_path, monkeypatch):
    import asyncio
    import json as json_module
    from docx import Document
    from app.config import settings
    from app.graph import execute
    import app.llm as llm_module
    from app.llm import LLM

    path = tmp_path / 'lease_retry.docx'
    doc = Document()
    doc.add_paragraph('COMMERCIAL LEASE')
    doc.add_paragraph('Tenant: Acme Properties LLC')
    doc.add_paragraph('Landlord: Example Holdings LLC')
    doc.save(path)
    schema = {'name': 'lease_abstraction', 'fields': {
        'tenant_name': {'name': 'Tenant', 'description': 'Full legal name of tenant.'},
        'landlord_name': {'name': 'Landlord', 'description': 'Full legal name of landlord.'},
    }}

    async def fake_complete(self, messages, model=None, temperature=0, max_tokens=4000, retries=1, json_mode=True):
        request = json_module.loads(messages[-1]['content'])
        keys = list(request['fields'])
        self.calls += 1
        self.by_model.setdefault(model or settings.fast_model, {'calls': 0, 'tokens_in': 0, 'tokens_out': 0, 'cost_usd': 0.0})
        self.by_model[model or settings.fast_model]['calls'] += 1
        retry = any('focused recovery attempt' in rule for rule in request.get('rules', []))
        if retry and keys == ['tenant_name']:
            return json_module.dumps({'tenant_name': {
                'value': 'Acme Properties LLC',
                'citation': '[Paragraph 2] Tenant: Acme Properties LLC',
                'confidence': 0.99,
            }})
        return json_module.dumps({key: {'value': None, 'citation': '', 'confidence': 0} for key in keys})

    monkeypatch.setattr(settings, 'llm_api_key', 'test-key-never-used-for-network')
    monkeypatch.setattr(llm_module, 'AsyncOpenAI', None)
    monkeypatch.setattr(LLM, 'complete', fake_complete)
    result = asyncio.run(execute(str(path), schema))
    entry = result['entries'][0]
    assert entry['tenant_name']['value'] == 'Acme Properties LLC'
    assert entry['landlord_name']['value'] is None
    assert result['metadata']['model_calls'] == 3
