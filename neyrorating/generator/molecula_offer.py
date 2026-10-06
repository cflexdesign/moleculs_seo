"""Render editorially supplied Molecula workflows, separate from service reviews."""
from html import escape
from pathlib import PurePosixPath
from urllib.parse import urlparse

FIELDS=('title','task','prompt','url','cta','screenshot','screenshot_detail','screenshot_caption','capability_id','mode')
def public_offer(value):
    if not isinstance(value,dict):return None
    value=dict(value)
    for old,new in [('summary','task'),('image','screenshot'),('alt','screenshot_caption'),('cta_label','cta')]:
        if not value.get(new) and value.get(old):value[new]=value[old]
    result={key:str(value[key]).strip() for key in FIELDS if value.get(key)}
    if isinstance(value.get('steps'),list):result['steps']=[str(step).strip() for step in value['steps'] if str(step).strip()][:5]
    if result.get('mode') and result['mode'] not in ('direct','preparation'):raise ValueError('Invalid Molecula offer mode')
    if not result.get('title') or not result.get('task') or not result.get('url'):return None
    parsed=urlparse(result['url'])
    if parsed.scheme!='https' or parsed.hostname not in ('moleculai.ru','www.moleculai.ru') or parsed.username or parsed.password:
        raise ValueError('Molecula offer must link to an HTTPS moleculai.ru page')
    for field in ('screenshot','screenshot_detail'):
        asset=result.get(field,'')
        if asset and (PurePosixPath(asset).is_absolute() or '..' in PurePosixPath(asset).parts or not asset.startswith('assets/') or ':' in asset):
            raise ValueError('Molecula offer screenshot must be a safe local assets path')
    return result

def render_offer(value,root='./',compact=False):
    offer=public_offer(value)
    if not offer:return ''
    E=escape
    visual=''
    if offer.get('screenshot'):
        caption=offer.get('screenshot_caption','Страница Молекулы для этой задачи')
        image=f'<img src="{E(root+offer["screenshot"])}" alt="{E(caption)}" width="480" height="270" loading="lazy">'
        if offer.get('screenshot_detail'):image=f'<a class="nr-task-enlarge" href="{E(root+offer["screenshot_detail"])}" aria-label="Открыть скриншот в большом размере">'+image+'</a>'
        visual=f'<figure class="nr-task-visual">{image}<figcaption>{E(caption)}</figcaption></figure>'
    steps='<ol class="nr-task-steps">'+''.join('<li>'+E(step)+'</li>' for step in offer.get('steps',[]))+'</ol>' if offer.get('steps') else ''
    if compact and steps:steps='<details class="nr-task-plan"><summary>Этапы выполнения</summary>'+steps+'</details>'
    arrow='<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><path d="M7 17 17 7M7 7h10v10" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    prompt=f'<div class="nr-task-prompt"><strong>Пример запроса</strong><p>{E(offer["prompt"])}</p></div>' if offer.get('prompt') else ''
    return f'<section class="nr-task-offer{ " nr-task-compact" if compact else ""}" aria-label="Сценарий работы в Молекуле"><div class="nr-task-copy"><span class="nr-task-kicker">Практика в Молекуле</span><h2>{E(offer["title"])}</h2><p>{E(offer["task"])}</p>{steps}{prompt}<a class="btn primary nr-task-cta" href="{E(offer["url"])}">{E(offer.get("cta","Попробовать этот сценарий"))}{arrow}</a></div>{visual}</section>'
