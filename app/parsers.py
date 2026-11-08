import asyncio, csv, io, re, logging
from pathlib import Path
from datetime import datetime, date
from concurrent.futures import ThreadPoolExecutor
import fitz
from docx import Document
from openpyxl import load_workbook
from .config import settings
log=logging.getLogger(__name__)
_pool=ThreadPoolExecutor(max_workers=max(2,settings.max_workers))

def fmt(v):
 if v is None:return ''
 if isinstance(v,(datetime,date)): return v.strftime('%Y-%m-%d')
 return str(v).strip()
def cell_name(r,c):
 from openpyxl.utils import get_column_letter
 return f'{get_column_letter(c)}{r}'
def parse_csv(path):
 raw=Path(path).read_text(encoding='utf-8-sig',errors='replace')
 rows=list(csv.reader(io.StringIO(raw)))
 lines=[]
 for i,row in enumerate(rows,1):
  vals=[f'{i}:{v.strip()}' for v in row if v and v.strip()]
  if vals: lines.append(f'[Row {i}] '+' | '.join(vals))
 return {'kind':'csv','text':'\n'.join(lines),'pages':[],'tables':[{'name':'CSV','rows':rows}],'profile':{'format':'csv','rows':len(rows)}}
def parse_xlsx(path):
 wb=load_workbook(path,data_only=True,read_only=True)
 blocks=[]; sheets=[]
 for ws in wb.worksheets:
  rows=[]; lines=[]
  for ri,row in enumerate(ws.iter_rows(),1):
   vals=[c.value for c in row]
   rows.append(vals)
   cells=[f'{cell_name(ri,ci)}={fmt(v)}' for ci,v in enumerate(vals,1) if fmt(v)!='']
   if cells: lines.append(f'[Sheet {ws.title} row {ri}] '+' | '.join(cells))
  sheets.append({'name':ws.title,'rows':rows,'max_row':ws.max_row,'max_column':ws.max_column})
  blocks.extend(lines)
 wb.close()
 return {'kind':'xlsx','text':'\n'.join(blocks),'pages':[],'tables':sheets,'profile':{'format':'xlsx','sheets':[{'name':s['name'],'rows':s['max_row'],'columns':s['max_column']} for s in sheets]}}
def parse_docx(path):
 d=Document(path); lines=[]
 for i,p in enumerate(d.paragraphs,1):
  t=p.text.strip()
  if t: lines.append(f'[Paragraph {i}] {t}')
 for ti,t in enumerate(d.tables,1):
  for ri,row in enumerate(t.rows,1): lines.append(f'[Table {ti} row {ri}] '+' | '.join(c.text.replace('\n',' / ').strip() for c in row.cells))
 return {'kind':'docx','text':'\n'.join(lines),'pages':[],'tables':[],'profile':{'format':'docx','paragraphs':len(d.paragraphs),'tables':len(d.tables)}}
def _render_pdf_pages(path):
 doc=fitz.open(path); results=[]
 for idx,page in enumerate(doc):
  text=page.get_text('text',sort=True).strip()
  blocks=page.get_text('blocks')
  positioned=[]
  for b in blocks:
   if len(b)>=5 and str(b[4]).strip(): positioned.append({'bbox':[round(x,1) for x in b[:4]],'text':str(b[4]).strip()})
  image_bytes=None
  if len(text)<35:
   pix=page.get_pixmap(matrix=fitz.Matrix(settings.ocr_dpi/72,settings.ocr_dpi/72),alpha=False,colorspace=fitz.csGRAY)
   image_bytes=pix.tobytes('png')
  layout_text='\n'.join(f"[x={b['bbox'][0]} y={b['bbox'][1]} w={b['bbox'][2]-b['bbox'][0]}] {b['text']}" for b in sorted(positioned,key=lambda z:(z['bbox'][1],z['bbox'][0])))
  results.append({'page':idx+1,'text':text,'layout_text':layout_text,'blocks':positioned,'ocr':image_bytes is not None,'image_bytes':image_bytes})
 doc.close(); return results

def _ocr_batch(image_bytes_list):
 import subprocess, os
 from PIL import Image
 images=[]
 for data in image_bytes_list:
  with Image.open(io.BytesIO(data)) as im: images.append(im.convert('L').copy())
 buf=io.BytesIO()
 images[0].save(buf,format='TIFF',save_all=True,append_images=images[1:],compression='tiff_deflate')
 try:
  proc=subprocess.run(['tesseract','stdin','stdout','-l',settings.ocr_lang,'--psm','11'],input=buf.getvalue(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45,check=False,env={**os.environ,'OMP_THREAD_LIMIT':'1'})
  parts=proc.stdout.decode('utf-8',errors='replace').split('\x0c')
  return [x.strip() for x in parts if x.strip()]
 except subprocess.TimeoutExpired:
  return ['']*len(image_bytes_list)
 finally:
  for im in images: im.close()
async def parse_pdf(path):
 loop=asyncio.get_running_loop()
 pages=await loop.run_in_executor(_pool,_render_pdf_pages,path)
 ocr_pages=[p for p in pages if p.get('image_bytes') is not None]
 # OCR groups are independent; a single Tesseract process handles several pages to
 # avoid per-page process overhead and native-library resource leaks.
 batches=[ocr_pages[i:i+5] for i in range(0,len(ocr_pages),5)]
 tasks=[loop.run_in_executor(_pool,_ocr_batch,[p['image_bytes'] for p in batch]) for batch in batches]
 results=await asyncio.gather(*tasks) if tasks else []
 for batch,texts in zip(batches,results):
  for p,txt in zip(batch,texts): p['text']=txt
  # If Tesseract emitted fewer pages than expected, leave the remainder empty rather than shifting citations.
  for p in batch[len(texts):]: p['text']=''
 for p in pages: p.pop('image_bytes',None)
 lines=[]
 for p in pages:
  source=p['text'] if p['ocr'] else (p.get('layout_text') or p['text'])
  if source: lines.append(f"\n===== PAGE {p['page']} {'OCR' if p['ocr'] else 'TEXT WITH COORDINATES'} =====\n{source}")
 return {'kind':'pdf','text':'\n'.join(lines),'pages':pages,'tables':[],'profile':{'format':'pdf','page_count':len(pages),'ocr_pages':[p['page'] for p in pages if p['ocr']],'text_pages':[p['page'] for p in pages if not p['ocr']]}}
async def parse_document(path):
 ext=Path(path).suffix.lower()
 if ext=='.pdf': return await parse_pdf(path)
 if ext=='.docx': return await asyncio.get_running_loop().run_in_executor(_pool,parse_docx,path)
 if ext=='.xlsx': return await asyncio.get_running_loop().run_in_executor(_pool,parse_xlsx,path)
 if ext=='.csv': return await asyncio.get_running_loop().run_in_executor(_pool,parse_csv,path)
 raise ValueError(f'Unsupported file type: {ext}')

def chunks(text, size=11500, overlap=900):
 if len(text)<=size:return [text]
 out=[]; start=0
 while start<len(text):
  end=min(len(text),start+size)
  if end<len(text):
   cut=text.rfind('\n',start+size//2,end)
   if cut>start: end=cut
  out.append(text[start:end]); start=max(start+1,end-overlap)
 return out
