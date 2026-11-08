import json, sqlite3, threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from .config import settings

_lock = threading.Lock()
def now(): return datetime.now(timezone.utc).isoformat()
@contextmanager
def conn():
    c=sqlite3.connect(settings.database_path, timeout=30, check_same_thread=False)
    c.row_factory=sqlite3.Row
    try:
        yield c
    finally:
        c.close()

def init_db():
    Path(settings.database_path).parent.mkdir(parents=True,exist_ok=True)
    with conn() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS jobs(job_id TEXT PRIMARY KEY, org_id TEXT NOT NULL, status TEXT NOT NULL, stage TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, file_path TEXT NOT NULL, filename TEXT NOT NULL, schema_json TEXT NOT NULL, webhook_url TEXT, result_json TEXT, error_json TEXT, request_hash TEXT)''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_jobs_org ON jobs(org_id, created_at)')
        c.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_idempotency ON jobs(org_id, request_hash) WHERE request_hash IS NOT NULL')

def create_job(row):
    with _lock, conn() as c:
        if row.get('request_hash'):
            old=c.execute('SELECT * FROM jobs WHERE request_hash=? AND org_id=?',(row['request_hash'],row['org_id'])).fetchone()
            if old: return dict(old), False
        c.execute('INSERT INTO jobs(job_id,org_id,status,stage,created_at,updated_at,file_path,filename,schema_json,webhook_url,request_hash) VALUES(?,?,?,?,?,?,?,?,?,?,?)',tuple(row[k] for k in ['job_id','org_id','status','stage','created_at','updated_at','file_path','filename','schema_json','webhook_url','request_hash']))
        return dict(c.execute('SELECT * FROM jobs WHERE job_id=?',(row['job_id'],)).fetchone()), True

def get_job(job_id, org_id):
    with conn() as c:
        r=c.execute('SELECT * FROM jobs WHERE job_id=? AND org_id=?',(job_id,org_id)).fetchone()
        return dict(r) if r else None

def update_job(job_id, status=None, stage=None, result=None, error=None):
    with _lock, conn() as c:
        r=c.execute('SELECT status FROM jobs WHERE job_id=?',(job_id,)).fetchone()
        if not r or r['status'] in ('SUCCESS','PARTIAL','FAILED'): return
        fields=['updated_at=?']; vals=[now()]
        if status is not None: fields.append('status=?'); vals.append(status)
        if stage is not None: fields.append('stage=?'); vals.append(stage)
        if result is not None: fields.append('result_json=?'); vals.append(json.dumps(result,ensure_ascii=False))
        if error is not None: fields.append('error_json=?'); vals.append(json.dumps(error))
        vals.append(job_id)
        c.execute(f"UPDATE jobs SET {','.join(fields)} WHERE job_id=?",vals)

def response(row):
    return {k:row[k] for k in ['job_id','status','created_at','updated_at','stage']} | ({'result':json.loads(row['result_json'])} if row.get('result_json') else {}) | ({'error':json.loads(row['error_json'])} if row.get('error_json') else {})


def unfinished_jobs():
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM jobs WHERE status IN ('PENDING','RUNNING')").fetchall()]
