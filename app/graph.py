"""LangGraph orchestration with a dependency-free fallback for local tests."""
from typing import TypedDict, Any
from .parsers import parse_document
from .extraction import profile_document, normalize_schema, llm_extract
from .llm import LLM
import time
class PipelineState(TypedDict, total=False):
 path:str; schema:dict; parsed:dict; profile:dict; normalized:dict; entries:list; llm:Any; started:float
async def _parse(s): s['parsed']=await parse_document(s['path']); return s
async def _profile(s): s['profile']=profile_document(s['parsed']); return s
async def _normalize(s):
 from .config import settings
 if not settings.llm_api_key and not (s['parsed']['kind'] in ('xlsx','csv') and any(v.get('primary') for v in s['schema']['fields'].values())): raise RuntimeError('LLM_API_KEY is required for semantic document extraction')
 s['normalized']=await normalize_schema(s['llm'],s['schema'],s['profile']); return s
async def _extract(s): s['entries']=await llm_extract(s['llm'],s['schema'],s['normalized'],s['parsed'],s['profile']); return s
try:
 from langgraph.graph import StateGraph, END
 g=StateGraph(PipelineState)
 g.add_node('parse',_parse); g.add_node('profile',_profile); g.add_node('normalize_schema',_normalize); g.add_node('extract',_extract)
 g.set_entry_point('parse'); g.add_edge('parse','profile'); g.add_edge('profile','normalize_schema'); g.add_edge('normalize_schema','extract'); g.add_edge('extract',END)
 PIPELINE=g.compile()
except Exception:
 PIPELINE=None
async def execute(path,schema):
 if PIPELINE is None:
  from .extraction import run_pipeline
  return await run_pipeline(path,schema)
 from .extraction import make_field,infer_type
 start=time.perf_counter(); llm=LLM()
 state=await PIPELINE.ainvoke({'path':path,'schema':schema,'llm':llm,'started':start})
 fields=schema['fields']; primary=next((k for k,v in fields.items() if v.get('primary')),None)
 entries=state.get('entries') or [{}]; fixed=[]
 for e in entries:
  fixed.append({k:make_field((e.get(k) or {}).get('value'),(e.get(k) or {}).get('citation',''),(e.get(k) or {}).get('confidence',0),(e.get(k) or {}).get('page_numbers'),(e.get(k) or {}).get('source_locations'),state['normalized'].get(k,{}).get('type') or infer_type(k,v.get('description',''))) for k,v in fields.items()})
 if primary and len(fixed)>1:fixed=[r for r in fixed if r[primary]['value'] is not None]
 return {'entries':fixed,'metadata':{'model_calls':llm.calls,'failed_calls':llm.failed_calls,'parse_failures':llm.parse_failures,'tokens_in':llm.tokens_in,'tokens_out':llm.tokens_out,'cost_usd':llm.cost_usd,'latency_ms':int((time.perf_counter()-start)*1000),'models':llm.by_model}}
