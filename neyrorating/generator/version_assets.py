"""Version local UI assets so an updated page cannot reuse an older catalogue."""
from pathlib import Path
from urllib.parse import urlsplit
import hashlib,re

NAMES=('data.js','app.js','ui-v2.js','style.css','v2.css','ui.svg','category-icons.svg')
ATTRIBUTE=re.compile(r'\b(?:src|href)=(?P<quote>["\'])(?P<url>[^"\'<>]+)(?P=quote)')
LOCAL=re.compile(r'^(?:\./|\.\./)*assets/([^/?#]+)$')

def version_assets(root):
    root=Path(root)
    versions={name:hashlib.sha256((root/'assets'/name).read_bytes()).hexdigest()[:12]
              for name in NAMES if (root/'assets'/name).is_file()}
    changed=references=0
    for page in root.rglob('*.html'):
        before=page.read_text()
        def replace(match):
            nonlocal references
            value=match.group('url');parsed=urlsplit(value)
            local=LOCAL.fullmatch(parsed.path)
            if parsed.scheme or parsed.netloc or not local or local[1] not in versions:return match[0]
            updated=parsed.path+'?v='+versions[local[1]]+('#'+parsed.fragment if parsed.fragment else '')
            if updated==value:return match[0]
            references+=1
            return match[0].replace(value,updated,1)
        after=ATTRIBUTE.sub(replace,before)
        if after!=before:page.write_text(after);changed+=1
    return {'versioned_assets':len(versions),'html_files_changed':changed,'references_changed':references}

if __name__=='__main__':
    import argparse,json
    parser=argparse.ArgumentParser();parser.add_argument('site');args=parser.parse_args()
    print(json.dumps(version_assets(args.site)))
