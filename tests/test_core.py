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


def test_docx_pipeline_uses_planner_grouped_extraction_and_one_review(tmp_path, monkeypatch):
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
    calls = []

    async def fake_complete(self, messages, model=None, temperature=0, max_tokens=4000, retries=1, json_mode=True):
        request = json_module.loads(messages[-1]['content'])
        calls.append((model, request))
        self.calls += 1
        model_name = model or settings.fast_model
        stats = self.by_model.setdefault(model_name, {'calls': 0, 'tokens_in': 0, 'tokens_out': 0, 'cost_usd': 0.0})
        stats['calls'] += 1
        if 'required_json_shape' in request:  # document/schema planner
            keys = list(request['fields'])
            return json_module.dumps({
                'document_type': 'commercial lease', 'complexity': 'high',
                'field_guidance': {k: {'semantic_intent': request['fields'][k]['description'],
                                       'aliases': [], 'search_queries': [], 'section_hints': [],
                                       'strategy': 'direct'} for k in keys},
                'groups': [{'name': 'Parties and term', 'field_keys': keys,
                            'instructions': 'Extract the related contract facts.'}],
            })
        if 'output_contract' in request:  # grouped extraction
            return json_module.dumps({'fields': {
                'tenant_name': {'value': 'Acme Properties LLC',
                                'citation': '[Paragraph 2] Tenant: Acme Properties LLC', 'confidence': .99},
                'landlord_name': {'value': 'Example Holdings LLC',
                                  'citation': '[Paragraph 3] Landlord: Example Holdings LLC', 'confidence': .99},
                'rent_start_date': {'value': None, 'citation': '', 'confidence': 0},
            }})
        if 'required_shape' in request:  # one batched semantic review of populated candidates
            return json_module.dumps({'decisions': {
                'tenant_name': {'decision': 'keep', 'confidence': .99},
                'landlord_name': {'decision': 'keep', 'confidence': .99},
            }})
        if 'output' in request:  # bounded recovery for unresolved fields
            return json_module.dumps({'fields': {'rent_start_date': {'value': None, 'citation': '', 'confidence': 0}}})
        raise AssertionError('Unexpected model stage')

    monkeypatch.setattr(settings, 'llm_api_key', 'test-key-never-used-for-network')
    monkeypatch.setattr(llm_module, 'AsyncOpenAI', None)
    monkeypatch.setattr(LLM, 'complete', fake_complete)
    result = asyncio.run(execute(str(docx_path), schema))
    entry = result['entries'][0]
    assert entry['tenant_name']['value'] == 'Acme Properties LLC'
    assert entry['landlord_name']['value'] == 'Example Holdings LLC'
    assert entry['rent_start_date']['value'] is None
    assert result['metadata']['model_calls'] == 4  # planner + group + review + one batched recovery
    assert result['metadata']['planner_version'] == 'schema-aware-v1'
    assert result['metadata']['document_complexity'] == 'high'
    assert result['metadata']['extraction_groups'] == 1
    assert calls[0][0] == settings.fast_model
    assert calls[1][0] == settings.fast_model  # direct facts use Flash despite high document complexity
    assert calls[2][0] == settings.strong_model
    assert calls[3][0] == settings.strong_model  # unresolved fields are recovered in one batch


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


def test_citation_authenticity_does_not_require_schema_keyword():
    from app.extraction import _citation_ok
    source = '[Paragraph 70] HOLDING OVER. Tenant shall pay 150% of the monthly Base Rent after expiration.'
    citation = '[Paragraph 70] HOLDING OVER. Tenant shall pay 150% of the monthly Base Rent after expiration.'
    # A citation is authentic even though the schema field might be named "holdover_rent".
    assert _citation_ok(citation, source)


def test_retrieval_uses_planner_generated_semantic_aliases():
    from app.extraction import retrieve
    source = '\n'.join([
        '[Paragraph 10] SECURITY DEPOSIT. Tenant shall deposit the sum of $2,850.',
        '[Paragraph 70] HOLDING OVER. Tenant shall pay double the Base Rent after expiration.',
        '[Paragraph 71] SURRENDER. Tenant shall deliver the Premises to Landlord.',
    ])
    evidence = retrieve(source, {
        'key': 'holdover_rent', 'name': 'Holdover Rent',
        'description': 'Rent payable if the tenant remains after expiration.',
        'semantic_intent': 'Compensation for continued occupancy after lease expiry.',
        'aliases': ['holding over', 'continued occupancy after expiration'],
        'search_queries': ['holding over rent', 'post-expiration occupancy charge'],
        'section_hints': ['HOLDING OVER'],
    }, max_chars=1800, max_hits=12)
    assert 'HOLDING OVER' in evidence
    assert 'double the Base Rent' in evidence


def test_planner_plan_covers_every_schema_key_once_with_bounded_groups():
    from app.extraction import _sanitize_plan
    fields = {f'field_{i}': {'name': f'Field {i}', 'description': f'Description for field {i}'} for i in range(11)}
    schema = {'fields': fields}
    raw = {'document_type': 'commercial contract', 'complexity': 'medium',
           'field_guidance': {'field_0': {'aliases': ['equivalent wording'], 'semantic_intent': 'Meaning'}},
           'groups': [{'name': 'Group A', 'field_keys': ['field_0', 'field_1', 'field_1', 'unknown']}]}
    plan = _sanitize_plan(raw, schema, {'document_type': 'contract'}, {'text': 'x' * 50000, 'profile': {'page_count': 20}})
    groups = plan['_plan']['groups']
    flattened = [key for group in groups for key in group['field_keys']]
    assert sorted(flattened) == sorted(fields)
    assert len(flattened) == len(set(flattened))
    assert all(1 <= len(group['field_keys']) <= 8 for group in groups)
    assert plan['_plan']['complexity'] == 'high'
    assert plan['field_0']['aliases'] == ['equivalent wording']


def test_rent_schedule_is_reconstructed_and_calculated_from_document_structure():
    from app.extraction import extract_rent_schedule_fields, infer_type
    schema = {'fields': {
        'rent_period_start_dates': {'name': 'Rent Schedule Start Dates',
                                    'description': 'List of the start date of each rent period.'},
        'rent_period_end_dates': {'name': 'Rent Schedule End Dates',
                                  'description': 'List of the end date of each rent period.'},
        'monthly_base_rents': {'name': 'Monthly Rent Schedule',
                               'description': 'List of monthly base rent amounts.'},
        'annual_rent_rsf': {'name': 'Annual Rent per RSF',
                            'description': 'Annual base rent per rentable square foot aligned with the schedule.'},
        'total_base_rent': {'name': 'Total Base Rent',
                            'description': 'Sum of all base rent due over the term, as a number.'},
        'base_rent_escalation': {'name': 'Base Rent Escalation',
                                 'description': 'How base rent increases, in a short phrase.'},
    }}
    text = '''===== PAGE 4
BASE RENT SCHEDULE
Annual Base Rent Monthly Installment
May 1, 2020 through April 30, 2021 $24,000 $2,000 12
May 1, 2021 through April 30, 2022 $24,720 $2,060 12
'''
    out = extract_rent_schedule_fields({'text': text}, schema)
    assert out['rent_period_start_dates']['value'] == ['2020-05-01', '2021-05-01']
    assert out['rent_period_end_dates']['value'] == ['2021-04-30', '2022-04-30']
    assert out['monthly_base_rents']['value'] == [2000.0, 2060.0]
    assert out['total_base_rent']['value'] == 48720.0
    assert 'base_rent_escalation' not in out
    assert infer_type('base_rent_escalation', 'How base rent increases, in a short phrase.') == 'string'
    assert infer_type('holdover_rent', 'As the lease states it, e.g. 150% of rent.') == 'string'
    assert infer_type('late_fee', 'Late charge as the lease states it, in a short phrase.') == 'string'


def test_schedule_role_discovery_uses_schema_descriptions_not_fixed_sample_keys():
    from app.extraction import _schedule_field_roles
    schema = {'fields': {
        'period_begin_dates': {'name': 'Rent Schedule Begin Dates', 'description': 'List of start dates for the rent schedule.'},
        'period_finish_dates': {'name': 'Rent Schedule Finish Dates', 'description': 'List of end dates for the rent schedule.'},
        'base_rent_installments': {'name': 'Monthly Rent Installments', 'description': 'List of monthly rent for each schedule period.'},
    }}
    assert _schedule_field_roles(schema) == {
        'starts': 'period_begin_dates', 'ends': 'period_finish_dates', 'monthly': 'base_rent_installments'}


def test_group_router_uses_field_complexity_not_global_document_complexity():
    from app.extraction import _route_model
    from app.config import settings
    normalized = {'_plan': {'complexity': 'high'},
                  'tenant_name': {'strategy': 'direct', 'semantic_intent': 'legal name of tenant'},
                  'landlord_name': {'strategy': 'direct', 'semantic_intent': 'legal name of landlord'},
                  'renewal_option': {'strategy': 'boolean', 'semantic_intent': 'whether tenant holds an option to renew'},
                  'termination_terms': {'strategy': 'narrative', 'semantic_intent': 'conditions and fees for early termination'}}
    assert _route_model(normalized, {}, ['tenant_name', 'landlord_name']) == settings.fast_model
    assert _route_model(normalized, {}, ['renewal_option', 'termination_terms']) == settings.strong_model


def test_schedule_calculations_run_from_aligned_source_values_after_review():
    from app.extraction import apply_schedule_calculations, make_field
    schema = {'fields': {
        'rent_schedule_start_dates': {'name': 'Rent Schedule Start Dates', 'description': 'List of start dates.'},
        'rent_schedule_end_dates': {'name': 'Rent Schedule End Dates', 'description': 'List of end dates.'},
        'rent_schedule_monthly_rent': {'name': 'Rent Schedule Monthly Rent', 'description': 'List of monthly rent.'},
        'rent_schedule_annual_rent_per_rsf': {'name': 'Rent Schedule Annual Rent per RSF', 'description': 'Annual rent per square foot.'},
        'rentable_square_footage': {'name': 'Rentable Square Footage', 'description': 'Rentable square footage as a number.'},
        'total_base_rent': {'name': 'Total Base Rent', 'description': 'Sum of all base rent due over the term.'},
        'base_rent_escalation': {'name': 'Base Rent Escalation', 'description': 'How base rent increases.'},
    }}
    entry = {
        'rent_schedule_start_dates': make_field(['2020-01-01'], '[Page 1] 2020-01-01 through 2020-12-31 $1,000', typ='array', item_type='date'),
        'rent_schedule_end_dates': make_field(['2020-12-31'], '[Page 1] 2020-01-01 through 2020-12-31 $1,000', typ='array', item_type='date'),
        'rent_schedule_monthly_rent': make_field([1000], '[Page 1] 2020-01-01 through 2020-12-31 $1,000', typ='array', item_type='number'),
        'rentable_square_footage': make_field(1200, '[Page 1] 1,200 rentable square feet', typ='number'),
        'rent_schedule_annual_rent_per_rsf': {'value': None, 'citation': '', 'confidence': 0},
        'total_base_rent': {'value': None, 'citation': '', 'confidence': 0},
        'base_rent_escalation': {'value': None, 'citation': '', 'confidence': 0},
    }
    out = apply_schedule_calculations([entry], schema)[0]
    assert out['rent_schedule_annual_rent_per_rsf']['value'] == [10.0]
    assert out['total_base_rent']['value'] == 12000.0
    assert out['base_rent_escalation']['value'] == 'none'


def test_compact_planner_guidance_aliases_are_normalized():
    from app.extraction import _sanitize_plan
    schema = {'fields': {'post_expiry_rent': {'name': 'Holdover Rent',
              'description': 'Rent payable when tenant remains after lease expiration.'}}}
    plan = _sanitize_plan({'complexity': 'medium', 'field_guidance': {
        'post_expiry_rent': {'intent': 'compensation for occupancy after expiry',
                             'terms': ['holding over', 'continued occupancy'],
                             'queries': ['holding over rent'], 'sections': ['HOLDING OVER'],
                             'strategy': 'narrative'}}}, schema,
        {'document_type': 'contract'}, {'text': 'x', 'profile': {'page_count': 1}})
    assert plan['post_expiry_rent']['semantic_intent'].startswith('compensation')
    assert plan['post_expiry_rent']['aliases'] == ['holding over', 'continued occupancy']
    assert plan['post_expiry_rent']['search_queries'] == ['holding over rent']
    assert plan['post_expiry_rent']['section_hints'] == ['HOLDING OVER']


def test_page_number_can_be_inferred_from_authentic_citation_without_locator():
    from app.extraction import _infer_page_numbers
    source = '''===== PAGE 1 OCR =====
LEASE AGREEMENT
Tenant: Example LLC
===== PAGE 2 OCR =====
SECURITY DEPOSIT: $2406 21
===== PAGE 3 OCR =====
HOLDING OVER. Tenant shall pay 150% of rent.
'''
    assert _infer_page_numbers('SECURITY DEPOSIT: $2406 21', source) == [2]


def test_unresolved_field_recovery_is_batched_not_one_call_per_field():
    import asyncio
    import json as json_module
    from app.extraction import recover_missing_fields, empty_field

    class FakeLLM:
        def __init__(self): self.calls = 0
        async def complete(self, messages, **kwargs):
            self.calls += 1
            payload = json_module.loads(messages[-1]['content'])
            out = {}
            for key in payload['fields']:
                # The source citations are constructed below and must be authentic.
                line = next(x for x in source.splitlines() if x.lower().startswith('[paragraph') and key in x)
                out[key] = {'value': key.upper(), 'citation': line, 'confidence': .95}
            return json_module.dumps({'fields': out})

    source = '\n'.join(f'[Paragraph {i+1}] {f"field_{i}"}: source fact {i}' for i in range(11))
    schema = {'fields': {f'field_{i}': {'name': f'Field {i}', 'description': f'Value for field {i}.'} for i in range(11)}}
    normalized = {k: {'type': 'string', 'semantic_intent': f'meaning of {k}', 'aliases': [],
                      'section_hints': [], 'strategy': 'direct'} for k in schema['fields']}
    normalized['_plan'] = {'complexity': 'high'}
    entries = [{k: empty_field() for k in schema['fields']}]
    llm = FakeLLM()
    result = asyncio.run(recover_missing_fields(llm, schema, normalized,
                   {'text': source}, {'document_type': 'contract'}, entries))
    assert llm.calls == 2
    assert all(result[0][k]['value'] == k.upper() for k in schema['fields'])


def test_vision_review_can_recover_missing_high_risk_value_from_ocr_page(tmp_path):
    import asyncio
    import json as json_module
    import fitz
    from app.extraction import vision_review, empty_field

    pdf_path = tmp_path / 'scan.pdf'
    doc = fitz.open()
    doc.new_page(width=612, height=792)
    doc.new_page(width=612, height=792)
    doc.save(pdf_path)
    doc.close()

    class FakeVisionLLM:
        def __init__(self): self.called = False
        async def complete(self, messages, **kwargs):
            self.called = True
            return json_module.dumps({'fields': {
                'security_deposit_amount': {
                    'value': 2150,
                    'citation': '[Page 2] SECURITY DEPOSIT: $2,150.00',
                    'confidence': .99,
                    'page_numbers': [2]
                }
            }})

    parsed = {'kind': 'pdf', 'source_path': str(pdf_path),
              'text': '===== PAGE 1 TEXT =====\nLEASE AGREEMENT\n'
                      '===== PAGE 2 OCR =====\nSECURITY DEPOSIT: $2,150.00\n',
              'pages': [{'page': 1, 'ocr': False}, {'page': 2, 'ocr': True}]}
    schema = {'fields': {'security_deposit_amount': {
        'name': 'Security Deposit Amount',
        'description': 'Cash security deposit amount as a number. Use amended figure that governs.'}}}
    normalized = {'security_deposit_amount': {'type': 'number', 'semantic_intent': 'cash security amount',
                    'aliases': ['security deposit'], 'section_hints': ['SECURITY DEPOSIT']}}
    entries = [{'security_deposit_amount': empty_field()}]
    llm = FakeVisionLLM()
    out = asyncio.run(vision_review(llm, parsed, schema, normalized, entries))
    assert llm.called
    assert out[0]['security_deposit_amount']['value'] == 2150
    assert out[0]['security_deposit_amount']['page_numbers'] == [2]
