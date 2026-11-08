"""Offline sample runner. Requires the same env vars as the service for LLM fields."""
import argparse, asyncio, json, logging
from pathlib import Path
from .graph import execute
from .config import settings

def main():
 p=argparse.ArgumentParser();p.add_argument('--file',required=True);p.add_argument('--schema',required=True);p.add_argument('--output',required=True);a=p.parse_args()
 schema=json.loads(Path(a.schema).read_text())
 if not Path(a.file).is_file():
  p.error(f'input file does not exist: {a.file}')
 result=asyncio.run(asyncio.wait_for(execute(a.file,schema), timeout=settings.job_timeout_seconds))
 result['schema']=schema.get('name','custom')
 Path(a.output).parent.mkdir(parents=True,exist_ok=True);Path(a.output).write_text(json.dumps(result,indent=2,ensure_ascii=False))
 print(a.output)
if __name__=='__main__':main()
