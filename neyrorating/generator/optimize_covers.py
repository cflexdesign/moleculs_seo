"""Optional mechanical WebP compression of declared genuine opaque PNG covers.
Writes only the selected build output; no source files or collector data are edited.
"""
from pathlib import Path
from PIL import Image
import re
TEXT_SUFFIXES={'.html','.css','.js','.json','.xml','.txt'}
def optimize_covers(root,tools,quality=80):
 root=Path(root);declared={t[field] for t in tools if t.get('screenshot_status') in ('captured','captured_partial') for field in ('cover','detail_cover') if t.get(field,'').lower().endswith('.png')};mapping={};converted=[];errors=[]
 for reference in sorted(declared):
  path=root/reference
  if any(word in path.name.lower() for word in ('hero-art','favicon','social-cover','logo','icon')):continue
  if not path.is_file():continue
  try:
   with Image.open(path) as img:
    if img.width<600 or img.height<300:continue
    if 'A' in img.getbands() and img.getchannel('A').getextrema()!=(255,255):continue
    if img.mode=='P' and 'transparency' in img.info:continue
    target=path.with_suffix('.webp')
    if target.exists():continue
    before=path.stat().st_size;tmp=target.with_suffix('.webp.tmp');img.convert('RGB').save(tmp,'WEBP',quality=quality,method=4);after=tmp.stat().st_size
    if after>=before*.8:tmp.unlink();continue
    with Image.open(tmp) as check:
     if check.size!=img.size or check.format!='WEBP':raise ValueError('Compressed image validation failed')
    tmp.replace(target);new=target.relative_to(root).as_posix();mapping[reference]=new;converted.append({'old':reference,'new':new,'before':before,'after':after,'width':img.width,'height':img.height})
  except Exception as exc:errors.append({'asset':reference,'error':str(exc)})
 files=[p for p in root.rglob('*') if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES];changed=0
 if mapping:
  pattern=re.compile(r'(?<![\w-])(?:'+'|'.join(re.escape(key) for key in sorted(mapping,key=len,reverse=True))+r')(?=[\s\"\'<>?#)\\]|$)')
  for path in files:
   old=path.read_text();new=pattern.sub(lambda match:mapping[match.group(0)],old)
   if new!=old:path.write_text(new);changed+=1
 # A reference outside the supported path spellings must retain the original.
 retained=set()
 if mapping:
  names={Path(reference).name:reference for reference in mapping};pattern=re.compile('|'.join(re.escape(name) for name in names))
  for path in files:
   for name in pattern.findall(path.read_text()):retained.add(names[name])
 removed=0;saved=0
 for row in converted:
  if row['old'] not in retained:
   (root/row['old']).unlink();removed+=1;saved+=row['before']-row['after']
  else:saved-=row['after']
 return {'quality':quality,'candidate_assets':len(declared),'converted_assets':len(converted),'originals_removed':removed,'originals_retained':sorted(retained),'files_rewritten':changed,'saved_bytes':saved,'errors':errors,'source_files_modified':False}
