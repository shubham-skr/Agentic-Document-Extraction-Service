import asyncio, hashlib, json, logging, os, uuid, time
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
import httpx
from .config import settings
from .storage import init_db, now, create_job, get_job, update_job, response, unfinished_jobs
from .graph import execute
logging.basicConfig(level=getattr(logging,settings.log_level.upper(),logging.INFO),format='%(asctime)s %(levelname)s %(name)s %(message)s')
log=logging.getLogger('outcome')
TERMINAL={'SUCCESS','PARTIAL','FAILED'}
active=0; active_lock=asyncio.Lock(); MAX_ACTIVE=max(10,settings.max_workers*3); background_tasks=set()
@asynccontextmanager
async def lifespan(app:FastAPI):
 init_db()
 for job in unfinished_jobs():
  task=asyncio.create_task(_run(job['job_id'])); background_tasks.add(task); task.add_done_callback(background_tasks.discard)
 yield
app=FastAPI(title='Outcome Document Extraction Service',version='1.0.0',lifespan=lifespan)
@app.get('/health')
async def health(): return {'status':'ok','version':'1.0.0'}
async def _run(job_id):
 global active
 row=None
 from .storage import conn
 try:
  row=get_job(job_id,'__internal__')
  if not row:
   with conn() as c:
    r=c.execute('SELECT * FROM jobs WHERE job_id=?',(job_id,)).fetchone(); row=dict(r) if r else None
  if not row:return
  update_job(job_id,status='RUNNING',stage='PARSING')
  schema=json.loads(row['schema_json'])
  result=await execute(row['file_path'],schema)
  # Ensure output is JSON-serializable before persisting.
  json.dumps(result,allow_nan=False)
  final_status='PARTIAL' if result.get('metadata',{}).get('failed_calls',0)>0 else 'SUCCESS'
  update_job(job_id,status=final_status,stage='COMPLETE',result=result)
  if row.get('webhook_url'):
   try:
    async with httpx.AsyncClient(timeout=10) as client: await client.post(row['webhook_url'],json={'job_id':job_id,'status':final_status,'result':result})
   except Exception: log.exception('Webhook delivery failed for %s',job_id)
 except Exception as e:
  log.exception('Job %s failed',job_id)
  update_job(job_id,status='FAILED',stage='FAILED',error={'code':'EXTRACTION_FAILED','message':str(e)[:1000]})
 finally:
  async with active_lock: active=max(0,active-1)

@app.post('/jobs',status_code=202)
async def create(file:UploadFile=File(...), schema:str=Form(...), webhook_url:str|None=Form(None), x_organization_id:str|None=Header(None)):
 global active
 org=x_organization_id or 'default'
 ext=Path(file.filename or '').suffix.lower()
 if ext not in {'.pdf','.docx','.xlsx','.csv'}: raise HTTPException(400,'Unsupported file type; use PDF, DOCX, XLSX or CSV')
 try:
  sch=json.loads(schema)
  if not isinstance(sch,dict) or not isinstance(sch.get('fields'),dict) or not sch['fields']: raise ValueError('schema.fields must be a non-empty object')
  primaries=[k for k,v in sch['fields'].items() if isinstance(v,dict) and v.get('primary') is True]
  if len(primaries)>1: raise ValueError('At most one field may be primary')
  for k,v in sch['fields'].items():
   if not isinstance(v,dict): raise ValueError(f'Field {k} must be an object')
   v.setdefault('name',k); v.setdefault('description','')
 except Exception as e: raise HTTPException(400,f'Invalid schema JSON: {e}')
 content=await file.read(settings.max_upload_mb*1024*1024+1)
 if len(content)>settings.max_upload_mb*1024*1024: raise HTTPException(413,'File exceeds upload limit')
 async with active_lock:
  if active>=MAX_ACTIVE: raise HTTPException(429,'Too many active jobs',headers={'Retry-After':'5'})
  active+=1
 digest=hashlib.sha256(content+json.dumps(sch,sort_keys=True).encode()).hexdigest()
 path=Path(settings.upload_dir)/f'{uuid.uuid4().hex}{ext}'; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(content)
 job_id=str(uuid.uuid4()); stamp=now()
 row={'job_id':job_id,'org_id':org,'status':'PENDING','stage':'QUEUED','created_at':stamp,'updated_at':stamp,'file_path':str(path),'filename':Path(file.filename or 'document').name,'schema_json':json.dumps(sch),'webhook_url':webhook_url,'request_hash':digest}
 try: saved,created=create_job(row)
 except Exception:
  async with active_lock: active=max(0,active-1)
  path.unlink(missing_ok=True); raise
 if not created:
  async with active_lock: active=max(0,active-1)
  path.unlink(missing_ok=True)
  return JSONResponse(status_code=202,content=response(saved))
 task=asyncio.create_task(_run(job_id)); background_tasks.add(task); task.add_done_callback(background_tasks.discard)
 return {'job_id':job_id,'status':'PENDING','created_at':stamp,'updated_at':stamp,'stage':'QUEUED'}

@app.get('/jobs/{job_id}')
async def get(job_id:str,x_organization_id:str|None=Header(None)):
 row=get_job(job_id,x_organization_id or 'default')
 if not row: raise HTTPException(404,'Job not found')
 return response(row)
