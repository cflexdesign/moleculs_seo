"""Losslessly share repeated decorative SVG shapes; preserve outer SVG attributes."""
from pathlib import Path
from hashlib import sha256
import re
SVG=re.compile(r'(<svg\b[^>]*>)(.*?)(</svg>)',re.S)
FORBIDDEN=re.compile(r'<(?:title|desc|defs|use|script|style|foreignObject|text|image|animate|set)\b|\bid\s*=|\b(?:href|xlink:href)\s*=|url\s*\(|\bon\w+\s*=|\bstyle\s*=',re.I)
LABELED=re.compile(r'\b(?:role|aria-label|aria-labelledby|aria-describedby)\s*=',re.I)
ALLOWED_TAGS={'path','circle','ellipse','rect','line','polyline','polygon','g'}
def candidate(opening,inner):
 if LABELED.search(opening) or FORBIDDEN.search(inner):return False
 tags=re.findall(r'</?([\w:.-]+)\b',inner)
 return bool(tags) and all(tag in ALLOWED_TAGS for tag in tags)

def compact_tree(root):
 root=Path(root);shapes={};files=0;replaced=0;before=0;after=0;paths=list(root.rglob('*.html'))
 spritepath=root/'assets/ui.svg';existing=spritepath.read_text() if spritepath.is_file() else '';existing_inner=re.sub(r'^<svg\b[^>]*>|</svg>\s*$','',existing)
 occupied=set(re.findall(r'\bid="([^"]+)"',existing));ids={key:id for id,key in re.findall(r'<g id="([^"]+)" data-shape="([a-f0-9]{64})"',existing)}
 for path in paths:
  for opening,inner,closing in SVG.findall(path.read_text()):
   if candidate(opening,inner):shapes[sha256(inner.encode()).hexdigest()]=inner
 index=0
 for key in sorted(shapes):
  if key in ids:continue
  while 'i'+format(index,'x') in occupied:index+=1
  ids[key]='i'+format(index,'x');occupied.add(ids[key]);index+=1
 used={}
 for path in paths:
  raw=path.read_text();prefix='../'*(len(path.relative_to(root).parts)-1) or './'
  def replace(match):
   nonlocal replaced
   opening,inner,closing=match.groups()
   if not candidate(opening,inner):return match.group(0)
   key=sha256(inner.encode()).hexdigest();id=ids[key]
   usage='<use href="'+prefix+'assets/ui.svg#'+id+'"/>'
   if len(usage.encode())>=len(inner.encode()):return match.group(0)
   if not re.search(r'\bid="'+re.escape(id)+'"',existing):used[id]=(key,inner)
   replaced+=1
   return opening+usage+closing
  result=SVG.sub(replace,raw)
  if result!=raw:
   before+=len(raw.encode());after+=len(result.encode());path.write_text(result);files+=1
 sprite='<svg xmlns="http://www.w3.org/2000/svg">'+existing_inner+'<defs>'+''.join('<g id="'+id+'" data-shape="'+key+'">'+body+'</g>' for id,(key,body) in sorted(used.items()))+'</defs></svg>'
 if used:spritepath.write_text(sprite)
 return {'files_changed':files,'svg_instances_replaced':replaced,'unique_shapes':len(occupied) if used or existing else 0,'before_html_bytes':before,'after_html_bytes':after,'sprite_bytes':len(sprite.encode()) if used else 0,'saved_bytes':before-after-(len(sprite.encode())-len(existing.encode()) if used else 0)}
