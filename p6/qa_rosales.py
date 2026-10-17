"""Independent read-only HTML + HTTP Chromium gate for model-origin Rosales Café.
A source file alone can NEVER count as DONE. No fabrication, remote assets or repairs.
"""
import argparse
from bs4 import BeautifulSoup
import hashlib, json, re, os, http.server, threading
from pathlib import Path
from urllib.parse import urlparse,unquote
BRAND='Rosales Café, o melhor café brasileiro ao estilo Colombiano.'
BANNED=['O Melhor Café da América do Sul','Encontre-nos em qualquer lugar do Brasil',
 'Cartão de Crédito','Transferência bancária','Tarjeta de Débito',
 'Nossa equipe de profissionais qualificados','Faça seu Prato',
 'entrega grátis','100% orgânico','certificado','preço']
def verify(filename:Path, *, browser:bool=False, out:Path|None=None):
 filename=filename.resolve(strict=True);root=filename.parent
 data=filename.read_bytes();html=data.decode('utf-8');soup=BeautifulSoup(html,'html.parser')
 problems=[];screens={}
 def fail(code,detail=''):problems.append({'code':code,'detail':str(detail)[:220]})
 text=re.sub(r'\s+',' ',soup.get_text(' ',strip=True))
 if BRAND.casefold() not in text.casefold():fail('BRAND_POSITIONING_MISSING')
 if not soup.html or soup.html.get('lang','').lower()!='pt-br':fail('LANG_NOT_PT_BR')
 if not soup.title or 'rosales café' not in soup.title.get_text().lower():fail('TITLE_MISSING')
 if not soup.find('meta',attrs={'name':'viewport'}):fail('VIEWPORT_MISSING')
 for tag in ['header','nav','main','footer','h1']:
  if not soup.find(tag):fail('SEMANTIC_'+tag.upper())
 if len(soup.find_all('section'))<2:fail('TOO_FEW_SECTIONS')
 for claim in BANNED:
  if claim.casefold() in html.casefold():fail('UNVERIFIED_CLAIM',claim)
 if soup.find('form'):fail('UNVERIFIED_FORM')
 if soup.find(['script','iframe','object']):fail('EXECUTABLE_CONTENT')
 css='\n'.join(tag.get_text() for tag in soup.find_all('style'))
 if len(css)<350:fail('INLINE_CSS_MISSING')
 if '@media' not in css:fail('RESPONSIVE_CSS_MISSING')
 if not re.search(r'background(?:-color)?\s*:|linear-gradient\(',css,re.I):fail('VISUAL_STYLING_MISSING')
 ids={tag.get('id') for tag in soup.find_all(id=True)}
 for link in soup.find_all('a'):
  href=link.get('href','')
  if not href or href.startswith(('javascript:','data:')):fail('INVALID_LINK',href)
  elif href.startswith('#') and href[1:] not in ids:fail('BROKEN_ANCHOR',href)
 for tag,attr in [('link','href'),('script','src'),('img','src'),('source','src')]:
  for obj in soup.find_all(tag):
   ref=obj.get(attr,'')
   if not ref or ref.startswith(('data:','#')):continue
   u=urlparse(ref)
   if u.scheme or u.netloc or ref.startswith('//'):
    fail('EXTERNAL_DEPENDENCY',ref);continue
   target=(root/unquote(u.path)).resolve()
   if not target.is_relative_to(root) or not target.is_file():fail('MISSING_LOCAL_ASSET',ref)
 if browser:
  from playwright.sync_api import sync_playwright
  class Quiet(http.server.SimpleHTTPRequestHandler):
   def __init__(self,*a,**kw):super().__init__(*a,directory=str(root),**kw)
   def log_message(self,*a):pass
  server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Quiet)
  threading.Thread(target=server.serve_forever,daemon=True).start()
  try:
   with sync_playwright() as p:
    kw={'headless':True,'args':['--no-sandbox','--disable-dev-shm-usage']}
    binary=os.environ.get('CHROMIUM_BIN','')
    if binary and Path(binary).is_file():kw['executable_path']=binary
    engine=p.chromium.launch(**kw)
    for name,width,height in [('desktop',1440,900),('mobile',390,844)]:
     ctx=engine.new_context(viewport={'width':width,'height':height},service_workers='block')
     ctx.route('**/*',lambda route:route.continue_() if route.request.url.startswith('http://127.0.0.1:') else route.abort())
     page=ctx.new_page();errors=[];failed=[]
     page.on('pageerror',lambda err:errors.append(str(err)))
     page.on('requestfailed',lambda req:failed.append(req.url))
     response=page.goto('http://127.0.0.1:'+str(server.server_address[1])+'/'+filename.name,
                        wait_until='load',timeout=30000)
     result=page.evaluate("""() => ({overflow:document.documentElement.scrollWidth>innerWidth,
             headerHeight:document.querySelector('header')?.getBoundingClientRect().height||0,
             headings:document.querySelectorAll('h1').length})""")
     screens[name]={'http':response.status if response else None,**result,
                    'page_errors':errors[:5],'failed_requests':failed[:5]}
     if out:
      out.mkdir(parents=True,exist_ok=True)
      page.screenshot(path=str(out/('rosales-'+name+'.png')),full_page=True)
     if screens[name]['http']!=200:fail('BROWSER_HTTP_FAILURE',name)
     if result['overflow']:fail('BROWSER_OVERFLOW',name)
     if result['headerHeight']<35:fail('BROWSER_LAYOUT_FAILURE',name)
     if failed:fail('BROWSER_ASSET_FAILURE',name)
     if errors:fail('BROWSER_JS_ERROR',name)
     ctx.close()
    engine.close()
  except Exception as err:fail('BROWSER_QA_UNAVAILABLE',str(err))
  finally:server.shutdown();server.server_close()
 report={'schema':'olympus.p6.qa.v1',
         'status':'DONE' if browser and not problems else 'BLOCKED',
         'source_sha256':hashlib.sha256(data).hexdigest(),'html_bytes':len(data),
         'blocking_count':len(problems),'issues':problems,'browser':screens,
         'methodology':'No generated source was edited by this validator; real local HTTP/browser required.'}
 if out:
  out.mkdir(parents=True,exist_ok=True)
  (out/'qa-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
 return report
if __name__=='__main__':
 arg=argparse.ArgumentParser();arg.add_argument('html');arg.add_argument('--browser',action='store_true');arg.add_argument('--out')
 args=arg.parse_args();report=verify(Path(args.html),browser=args.browser,out=Path(args.out) if args.out else None)
 print(json.dumps(report,ensure_ascii=False,indent=2));raise SystemExit(0 if report['status']=='DONE' else 2)