import asyncio, json, logging, re, time
from typing import Any
try:
 from openai import AsyncOpenAI
except ImportError:  # Allows deterministic parser-only use without installing the LLM client.
 AsyncOpenAI=None
from .config import settings
log=logging.getLogger(__name__)
_ALLOWED={'google/gemini-3.8-flash','google/gemini-3.1-pro-preview','anthropic/claude-haiku-5.5','anthropic/claude-sonnet-5.5','openai/gpt-6-luna','openai/gpt-6.1-sol','z-ai/glm-5.3-flash','qwen/qwen3-vl-235b-a22b-instruct','deepseek/deepseek-v3.2'}
_sem=asyncio.Semaphore(max(1,settings.max_llm_concurrency))
class LLM:
 def __init__(self):
  self.client=AsyncOpenAI(base_url=settings.llm_base_url,api_key=settings.llm_api_key,timeout=150,max_retries=0) if settings.llm_api_key and AsyncOpenAI else None
  self.calls=0; self.failed_calls=0; self.tokens_in=0; self.tokens_out=0; self.cost_usd=0.0; self.by_model={}
 async def complete(self, messages, model=None, temperature=0, max_tokens=7000, retries=3):
  if not self.client: raise RuntimeError('LLM_API_KEY is not configured')
  model=model or settings.fast_model
  if model not in _ALLOWED: raise ValueError(f'Model not allowed by assignment: {model}')
  async with _sem:
   for attempt in range(retries+1):
    try:
     m=self.by_model.setdefault(model,{'calls':0,'tokens_in':0,'tokens_out':0,'cost_usd':0.0})
     self.calls+=1; m['calls']+=1
     r=await self.client.chat.completions.create(model=model,messages=messages,temperature=temperature,max_tokens=max_tokens,extra_body={'usage':{'include':True}})
     usage=r.usage
     ti=getattr(usage,'prompt_tokens',0) or 0; to=getattr(usage,'completion_tokens',0) or 0
     self.tokens_in+=ti; self.tokens_out+=to
     cost=float(getattr(usage,'cost',0) or 0); self.cost_usd+=cost
     m['tokens_in']+=ti; m['tokens_out']+=to; m['cost_usd']+=cost
     return r.choices[0].message.content or ''
    except Exception as e:
     status=getattr(e,'status_code',None)
     if attempt>=retries or (status not in (429,500,502,503,504) and status is not None):
      self.failed_calls+=1
      raise
     await asyncio.sleep(min(12,0.8*(2**attempt))*(0.8+0.4*((time.time()%1))))
   raise RuntimeError('LLM retries exhausted')

def parse_json(text:str):
 s=text.strip()
 s=re.sub(r'^```(?:json)?\s*','',s,flags=re.I); s=re.sub(r'\s*```$','',s)
 try:return json.loads(s)
 except Exception:
  m=re.search(r'\{.*\}',s,re.S)
  if m:return json.loads(m.group(0))
  raise
