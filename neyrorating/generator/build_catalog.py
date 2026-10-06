#!/usr/bin/env python3
"""Build an expanded catalogue to an explicitly separate output directory.
Does not write to --source and does not publish. Own copy must be supplied in input.
"""
from pathlib import Path
from copy import deepcopy
from collections import defaultdict
from urllib.parse import urlparse
import argparse,json,math,re,shutil,gzip,html as stdhtml
from lxml import html,etree
from integration import enhance_tree,review_toc
from molecula_offer import public_offer,render_offer
from svg_sprite import compact_tree
from version_assets import version_assets
P=Path(__file__).parent
E=stdhtml.escape
SIZE=48

def markup(s):
    wrapper=html.Element('div')
    for part in html.fragments_fromstring(s or ''):
        if isinstance(part,str):wrapper.text=(wrapper.text or '')+part
        else:wrapper.append(part)
    return wrapper

def clean_public(node):
    for dangerous in node.xpath('.//script|.//iframe|.//object|.//embed'):
        dangerous.getparent().remove(dangerous)
    for el in node.iter():
        for key in list(el.attrib):
            if key.lower().startswith('on'):del el.attrib[key]
        if el.tag=='a':
            href=el.get('href','')
            if href.startswith(('http:','https:')) and urlparse(href).hostname not in ('moleculai.ru','www.moleculai.ru'):
                el.drop_tag()
            elif href.lower().startswith(('javascript:','data:')):el.attrib.pop('href',None)
    return node

def icon(paths):return '<svg viewBox="0 0 24 24" aria-hidden="true">'+paths+'</svg>'


def update_sidebar_counts(tree,tool_count,category_count,category_counts):
    """Apply the same live catalogue counts to generated and retained page sidebars."""
    sidebars=tree.xpath('self::*[contains(concat(" ",normalize-space(@class)," ")," sidebar ")]|.//*[contains(concat(" ",normalize-space(@class)," ")," sidebar ")]')
    for side in sidebars:
        total=side.xpath('.//*[contains(concat(" ",normalize-space(@class)," ")," side-count ")]')
        if total:total[0].text=str(tool_count)
        for anchor in side.xpath('.//a[contains(concat(" ",normalize-space(@class)," ")," all-cats ")]'):
            for part in anchor.iter():
                for field in ('text','tail'):
                    value=getattr(part,field)
                    if value and 'категор' in value:setattr(part,field,f'Все {category_count} категорий')
        for anchor in side.xpath('.//a[contains(@href,"category/")]'):
            slug=anchor.get('href','').split('category/')[-1].split('?',1)[0].split('#',1)[0].removesuffix('.html')
            if slug not in category_counts:continue
            for count in anchor.xpath('.//*[contains(concat(" ",normalize-space(@class)," ")," side-count ")]'):
                count.text=str(category_counts[slug])

def run(args):
    src=Path(args.source).resolve();out=Path(args.out).resolve();base=args.base.rstrip('/')+'/'
    if src==out or src in out.parents:raise SystemExit('Output must be separate from the source site.')
    if out.exists() and any(out.iterdir()) and not args.overwrite:raise SystemExit('Output is not empty. Use a new output folder or --overwrite.')
    input_path=Path(args.input);data=json.loads(gzip.decompress(input_path.read_bytes()).decode('utf-8') if input_path.suffix=='.gz' else input_path.read_text());excluded=set(data.get('excluded_ids',[]))|set(args.exclude_pages or []);tools=[t for t in data['tools'] if t['id'] not in excluded];cats=data['categories'];data['tools']=tools
    if any(not re.fullmatch('[a-z0-9][a-z0-9-]*',slug) for slug in excluded):raise SystemExit('Invalid excluded tool slug')
    if len({t['id'] for t in tools})!=len(tools):raise SystemExit('Duplicate tool IDs')
    if len({c['id'] for c in cats})!=len(cats):raise SystemExit('Duplicate category IDs')
    catby={c['id']:c for c in cats};toolby={t['id']:t for t in tools};mol=toolby.get('molecula')
    if mol is None:raise SystemExit('Molecula is required')
    for item in tools+cats:
        if not re.fullmatch('[a-z0-9][a-z0-9-]*',item['id']):raise SystemExit('Invalid slug: '+item['id'])
    for t in tools:
        if t.get('canonical_id') and (t['canonical_id'] not in toolby or toolby[t['canonical_id']].get('canonical_id') or t['canonical_id']==t['id']):
            raise SystemExit('Invalid canonical tool target: '+t['id'])
        missing=[k for k in ('description','content','meta_title','meta_description','score') if k not in t or t[k] in (None,'')]
        if missing:raise SystemExit(f"{t['id']}: missing own editorial fields {missing}")
        if not 0<=float(t['score'])<=5:raise SystemExit('Score out of range: '+t['id'])
        if any(c not in catby for c in t.get('categories',[])):raise SystemExit('Unknown category: '+t['id'])
        t['pinned']=t['id']=='molecula';t.setdefault('tags',[]);t.setdefault('price','Условия доступа не указаны');t.setdefault('category_scores',{})
        t['url']='https://moleculai.ru/' if t['pinned'] else ''
        t.pop('source',None)
        prose=clean_public(markup(t['content']))
        t['content']=(prose.text or '')+''.join(html.tostring(x,encoding='unicode') for x in prose)
        for asset in ('logo','cover','detail_cover'):
            value=t.get(asset,'')
            if value and (Path(value).is_absolute() or value.startswith(('http:','https:','//')) or '..' in Path(value).parts):raise SystemExit(f'{t["id"]}: asset must be a local safe path')
    others=[t for t in tools if not t['pinned'] and not t.get('canonical_id')]
    if any(float(t['score'])>float(mol['score']) for t in others):
        raise SystemExit('Molecula overall score must be at least as high as other owner-assigned scores.')
    for t in others:
        for category,value in t.get('category_scores',{}).items():
            if float(value)>float(mol.get('category_scores',{}).get(category,mol['score'])):
                raise SystemExit('Molecula category score must be at least as high: '+category)
    general_offer=public_offer(data.get('molecula_offer'))
    page_offers={path:public_offer(offer) for path,offer in data.get('pages_molecula_offers',{}).items()}
    for record in tools+cats:
        if record.get('molecula_offer'):record['molecula_offer']=public_offer(record['molecula_offer'])
    all_offers=[general_offer,*page_offers.values(),*[record.get('molecula_offer') for record in tools+cats]]
    out.mkdir(parents=True,exist_ok=True)
    shutil.copytree(src,out,dirs_exist_ok=True)
    for slug in excluded:
        (out/'tools'/f'{slug}.html').unlink(missing_ok=True)
    extra=Path(args.extra_assets).resolve() if args.extra_assets else Path(args.input).resolve().parent/'assets'
    referenced={t.get(field) for t in tools for field in ('logo','cover','detail_cover') if t.get(field)}
    referenced.update(offer[field] for offer in all_offers if offer for field in ('screenshot','screenshot_detail') if offer.get(field))
    for reference in sorted(referenced):
        target=out/reference
        if reference.startswith('assets/imported/'):
            relative=Path(reference).relative_to('assets/imported')
            origin=extra/relative
            if origin.is_file():
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(origin,target)
        if not target.is_file():
            raise SystemExit('Missing referenced local asset: '+reference)
    for name in ('v2.css','ui-v2.js','hero-art.png','category-icons.svg'):
        shutil.copy2(P/'assets'/name,out/'assets'/name)
    shutil.copy2(P/'assets/app-v2.js',out/'assets/app.js')
    template=html.parse(str(src/'index.html'));headTemplate=template.find('head');top=template.xpath('//header[contains(@class,"topbar")]')[0];sidebar=template.xpath('//aside[contains(@class,"sidebar")]')[0];footer=template.xpath('//footer[contains(@class,"footer")]')[0]
    previous_base=template.xpath('//link[@rel="canonical"]/@href')[0].removesuffix('index.html')
    idx=defaultdict(list)
    eligible=[t for t in tools if not t.get('canonical_id')]
    for t in eligible:
        for c in t.get('categories',[]):idx[c].append(t)
    def ordered(items,c=''):
        return sorted(items,key=lambda t:(not t['pinned'],-float(t.get('category_scores',{}).get(c,t['score'])),t['name'].casefold()))
    active=ordered(eligible)
    category_items={c["id"]:ordered([mol]+[t for t in idx[c["id"]] if t["id"]!="molecula"],c["id"]) for c in cats}
    category_counts={cid:len(items) for cid,items in category_items.items()}
    def local_node(node,root):
        n=deepcopy(node)
        for el in n.iter():
            for attr in ('href','src'):
                val=el.get(attr)
                if val and not val.startswith(('https:','http:','#','data:','mailto:')):el.set(attr,root+val.removeprefix('./'))
        return n
    def card(t,root,c=''):
        cover=t.get('cover','');logo=t.get('logo','');score=t.get('category_scores',{}).get(c,t['score'])
        visual=f'<img src="{root+E(cover)}" alt="" loading="lazy" width="640" height="330">' if cover else f'<div class="cover-fallback">{E(t["name"])}<small>Обложка сервиса</small></div>'
        offer=catby.get(c,{}).get('molecula_offer') or general_offer
        molcta=f'<a class="nr-card-task" href="{E(offer["url"])}">К задаче в Молекуле <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><path d="M7 17 17 7M7 7h10v10" fill="none" stroke="currentColor" stroke-width="1.6"/></svg></a>' if t['pinned'] and offer else ''
        badge='<span class="card-top-badge">Закреплено</span>' if t['pinned'] else ''
        logohtml=f'<img class="tool-logo" src="{root+E(logo)}" alt="" loading="lazy">' if logo else f'<span class="tool-logo letter-logo">{E(t["name"][:1])}</span>'
        category=catby[t['categories'][0]]['name'] if t.get('categories') else 'AI-сервис'
        return f'<article class="tool-card {"pinned" if t["pinned"] else ""}" data-tool-id="{E(t["id"])}"><a class="card-cover" href="{root}tools/{t["id"]}.html" tabindex="-1" aria-hidden="true">{visual}{badge}</a><button class="fav-btn" data-favorite="{E(t["id"])}" aria-pressed="false" aria-label="Добавить в избранное">{icon('<path d="M6 3h12v18l-6-4-6 4Z"/>')}</button><div class="card-body"><div class="card-name">{logohtml}<h3><a href="{root}tools/{t["id"]}.html">{E(t["name"])}</a><small>{E(category)}</small></h3></div><p class="card-desc">{E(t["description"])}</p><div class="card-tags">'+''.join(f'<a href="{root}catalog.html?q={__import__("urllib.parse",fromlist=["quote"]).quote(tag)}">{E(tag)}</a>' for tag in t['tags'][:2])+f'</div><div class="card-footer"><span class="price-label">{E(t["price"])}</span><span class="rating" title="Внутренний балл проекта">{float(score):.1f} {icon(category_icons["spark"])}</span></div>{molcta}</div></article>'
    def related_link(t,root):
        logo=t.get('logo','')
        visual=f'<img src="{root+E(logo)}" alt="" width="36" height="36" loading="lazy">' if logo else f'<span aria-hidden="true">{E(t['name'][:1])}</span>'
        purpose=t['description']
        if len(purpose)>105:purpose=purpose[:105].rsplit(' ',1)[0].rstrip('.,;:')+'…'
        return f'<a class="nr-related-item{ " nr-related-mol" if t["pinned"] else ""}" href="{root}tools/{E(t["id"])}.html"><span class="nr-related-icon">{visual}</span><span class="nr-related-copy"><strong>{E(t["name"])}</strong><span class="nr-related-purpose">{E(purpose)}</span><span class="nr-related-facts"><span>{E(t["price"])}</span><span class="nr-related-score" title="Внутренний балл проекта">{float(t["score"]):.1f} / 5</span></span></span></a>'
    category_icons=json.loads((P/'assets/category-icons.json').read_text())
    def category_icon(c):
        key=c.get('icon','')
        if key not in category_icons:
            name=c['name'].lower()
            groups=[('image',('изображ','фот','портрет','аватар','апскейл')),('video',('видео','анимац','мультфильм')),('music',('музык','песн','аудио')),('voice',('голос','реч','транскрип')),('code',('код','програм','sql','разработ')),('website',('сайт','браузер','no-code')),('presentation',('презентац','слайд')),('document',('pdf','документ','таблиц')),('education',('учеб','учёб','обуч','образован')),('health',('здоров','медицин','фитнес')),('research',('поиск','исследован')),('chart',('аналит','данн','финанс','трейдинг')),('design',('дизайн','логотип')),('cube',('3d','архитект')),('game',('игр',)),('mail',('email','письм','почт')),('network',('интеграц','api','агент')),('writing',('текст','копирайт','seo')),('chat',('чат','диалог','компаньон')),('briefcase',('бизнес','маркет','продаж','hr'))]
            key=next((key for key,words in groups if any(w in name for w in words)),'spark')
        return icon(category_icons[key])
    written=[]
    def shell(path,title,description,main,c='',tool='',page=1,home=False):
        root='../'*path.count('/') or './';r=html.Element('html',lang='ru');head=local_node(headTemplate,root);r.append(head)
        for old in head.xpath('.//script[@type="application/ld+json"]'):head.remove(old)
        head.find('title').text=title if 'НейроРейтинг' in title else title+' | НейроРейтинг'
        for m in head.xpath('.//meta[@name="description"]|.//meta[@property="og:description"]'):m.set('content',description)
        for m in head.xpath('.//meta[@property="og:title"]'):m.set('content',head.find('title').text)
        for m in head.xpath('.//meta[@name="robots"]'):m.set('content','index,follow')
        for link in head.xpath('.//link[@rel="canonical"]'):link.set('href',base+path)
        for m in head.xpath('.//meta[@property="og:image"]'):m.set('content',base+'assets/social-cover.png')
        for m in head.xpath('.//meta[@property="og:url"]'):m.set('content',base+path)
        if not head.xpath('.//meta[@property="og:url"]'):head.append(html.Element('meta',property='og:url',content=base+path))
        schema={'@context':'https://schema.org','@type':'WebPage','name':head.find('title').text,'description':description,'url':base+path,'publisher':{'@type':'Organization','name':'НейроРейтинг','url':base+'index.html'}}
        if tool:
            actual_categories=[catby[id] for id in toolby[tool].get('categories',[]) if id in catby and (catby[id].get('type') or catby[id].get('kind') or 'category')=='category']
            application_category=actual_categories[0]['name'] if actual_categories else 'Рабочий инструмент'
            entity_type=toolby[tool].get('schema_type','SoftwareApplication')
            if entity_type not in ('SoftwareApplication','Organization'):raise ValueError('Unsupported schema type: '+tool)
            schema['mainEntity']={'@type':entity_type,'name':toolby[tool]['name']}
            if entity_type=='SoftwareApplication':schema['mainEntity']['applicationCategory']=application_category
            else:schema['mainEntity']['description']=toolby[tool]['description']
        ld=html.Element('script',type='application/ld+json');ld.text=json.dumps(schema,ensure_ascii=False,separators=(',',':')).replace('</','<\\/');head.append(ld)
        body=html.Element('body',{'data-root':root,'data-page':'tool' if tool else 'catalog' if 'id="tools-grid"' in main else 'page','data-category':c,'data-tool':tool,'data-pagination':str(page)});r.append(body)
        theme=etree.SubElement(body,'script');theme.text="try{if(JSON.parse(localStorage.getItem('nr:theme'))==='dark')document.body.classList.add('dark')}catch(e){}"
        skip=etree.SubElement(body,'a',{'class':'skip-link','href':'#main'});skip.text='Перейти к содержимому'
        body.append(local_node(top,root));layout=etree.SubElement(body,'div',{'class':'layout'});side=local_node(sidebar,root)
        for x in side.xpath('.//*[contains(@class,"demo-notice")]'):x.getparent().remove(x)
        update_sidebar_counts(side,len(active),len(cats),category_counts)
        layout.append(side);etree.SubElement(layout,'div',{'class':'overlay','id':'menu-overlay'});m=etree.SubElement(layout,'main',{'class':'main','id':'main'});content=clean_public(markup(main));m.text=content.text
        for child in list(content):m.append(child)
        m.append(local_node(footer,root));toast=etree.SubElement(body,'div',{'class':'toast','id':'toast','role':'status','aria-live':'polite','hidden':'hidden'})
        enhance_tree(r,root,homepage=home)
        # Prefer server-rendered review anchors; UI supplies comparison and back-to-top.
        prose=m.xpath('.//article[@class="prose"]');aside=m.xpath('.//aside[@class="detail-aside"]')
        if prose and aside:
            toc=review_toc(prose[0])
            if toc is not None:aside[0].insert(0,toc)
        dest=out/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(html.tostring(r,encoding='unicode',doctype='<!doctype html>'));written.append(path)
    def bread(label,root='./'):
        return f'<nav class="breadcrumbs" aria-label="Хлебные крошки"><a href="{root}index.html">Главная</a><span>›</span><span>{E(label)}</span></nav>'
    def listing(path,title,desc,items,c='',page=1,home=False):
        root='../'*path.count('/') or './';pages=max(1,math.ceil(len(items)/SIZE));part=items[(page-1)*SIZE:page*SIZE]
        options='<option value="">Все категории</option>'+''.join(f'<option value="{E(cat["id"])}" {"selected" if c==cat["id"] else ""}>{E(cat["name"])}</option>' for cat in cats)
        def pagepath(n):
            if c:return f'{c}.html' if n==1 else f'{c}-page-{n}.html'
            return 'catalog.html' if n==1 else f'catalog-page-{n}.html'
        near=sorted(set([1,pages,*range(max(1,page-2),min(pages,page+2)+1)]));nav=''.join(f'<a href="{pagepath(n)}" {"aria-current=\"page\" class=\"current\"" if page==n else ""}>{n}</a>' for n in near)
        intro=f'<div class="intro"><div><div class="eyebrow">КАТАЛОГ AI-СЕРВИСОВ</div><h1>{E(title)}</h1><p>{E(desc)}</p></div><div class="intro-stat"><div class="stat-number">{len(active)}<small>AI-сервисов</small></div><div class="stat-divider"></div><div class="stat-number">{len(cats)}<small>категорий</small></div></div></div>'
        task_offer=(catby[c].get('molecula_offer') if c else page_offers.get(path) or general_offer)
        main=bread(title,root)+intro+(render_offer(task_offer,root,compact=True) if c else '')+f'<form class="search-box" id="search-form" role="search"><label class="sr-only" for="search">Поиск сервисов</label><input type="search" id="search" placeholder="Название сервиса или задача" autocomplete="off"><kbd>Ctrl K</kbd><button type="submit">Найти</button></form><section id="catalog-start"><div class="section-title"><h2>Инструменты<span id="result-count">{len(items)}</span></h2><div class="view-switch"><button data-view="grid" aria-label="Плитка">▦</button><button data-view="list" aria-label="Список">☷</button></div></div><div class="filterbar"><label><input type="checkbox" id="free-only">Бесплатные</label><select id="category-select" aria-label="Выбрать категорию">{options}</select><label class="sort">Сортировка <select id="sort"><option value="recommended">По баллам</option><option value="name">По названию</option><option value="latest">Недавно добавленные</option></select></label><button class="btn" data-reset>Сбросить</button></div><div class="grid" id="tools-grid">'+''.join(card(t,root,c) for t in part)+f'</div><nav class="pagination" id="pagination" aria-label="Страницы каталога">{nav}</nav><p class="page-note" id="results-note">Страница {page} из {pages}</p></section>'
        if c:
            related=sorted({other for t in items for other in t.get('categories',[]) if other!=c},key=lambda x:catby[x]['name'])[:12]
            main+='<section class="home-links"><h2>Смежные задачи</h2><div class="category-link-grid">'+''.join(f'<a href="{root}category/{other}.html">{E(catby[other]["name"])}</a>' for other in related)+'</div></section>'
            if page==1 and catby[c].get('content'):main+='<article class="prose">'+catby[c]['content']+'</article>'
        else:
            if home:
                review_ids=('molecula','chatgpt','claude-ai','google-notebooklm','qwen','kling-ai','grammarly','quillbot','wordtune','chatpdf','elicit','scite')
                featured_reviews=[toolby[id] for id in review_ids if id in toolby and not toolby[id].get('canonical_id')]
                main+='<section class="home-links nr-home-reviews"><h2>Подробные обзоры</h2><div class="nr-related-grid">'+''.join(related_link(t,root) for t in featured_reviews)+'</div></section>'
            main+='<section class="home-links"><h2>Выберите направление</h2><div class="category-link-grid">'+''.join(f'<a href="{root}category/{cat["id"]}.html">{E(cat["name"])}</a>' for cat in cats)+'</div></section>'
        if not c:main+=render_offer(task_offer,root,compact=True)
        meta=(catby[c].get('meta_title') or title) if c else title
        if page>1:
            meta+=f' — страница {page}'
            desc=f'{desc} Страница {page}: '+', '.join(t['name'] for t in part[:3])+'.'
        shell(path,meta,desc,main,c,page=page,home=home)
    listing('index.html','Нейросети для ваших задач','Находите и сравнивайте инструменты для работы с текстом, изображениями, видео и другими материалами.',active,home=True)
    for n in range(1,math.ceil(len(active)/SIZE)+1):listing('catalog.html' if n==1 else f'catalog-page-{n}.html','Каталог нейросетей и AI-сервисов',f'AI-сервисы по задачам: описания, условия доступа и категории. Страница {n}; инструменты '+', '.join(t['name'] for t in active[(n-1)*SIZE:n*SIZE][:3])+'.',active,page=n)
    for c in cats:
        items=category_items[c['id']]
        for n in range(1,math.ceil(len(items)/SIZE)+1):listing(f'category/{c["id"]}.html' if n==1 else f'category/{c["id"]}-page-{n}.html',c['name'],c.get('meta_description') or c.get('description') or f'Инструменты для направления «{c["name"]}»: описания, условия доступа и сравнение задач.',items,c['id'],n)
    categories_main=bread('Все категории')+'<div class="intro"><div><h1>Категории нейросетей</h1><p>Выберите рабочую задачу, профессию или способ обработки материала.</p></div></div><div class="search-box" role="search"><label class="sr-only" for="category-search">Поиск категории, профессии или преобразования</label><input id="category-search" type="search" placeholder="Например: видео, маркетолог или текст в речь" autocomplete="off"></div>'
    for kind,label in (('category','По задачам'),('audience','По профессиям'),('transformation','По преобразованию материала')):
        group=sorted([c for c in cats if ((c.get('type') or c.get('kind')) if (c.get('type') or c.get('kind')) in ('audience','transformation') else 'category')==kind],key=lambda c:c['name'].casefold())
        if not group:continue
        categories_main+=f'<section class="category-group"><h2 class="group-letter">{label}</h2><div class="categories-grid">'+''.join(f'<a class="category-card" href="category/{c["id"]}.html" data-name="{E(c["name"])}"><span class="category-icon">{category_icon(c)}</span><span><strong>{E(c["name"])}</strong><small>{category_counts[c["id"]]} сервисов</small></span></a>' for c in group)+'</div></section>'
    categories_main+=render_offer(page_offers.get('categories.html') or general_offer,'./',compact=True)
    categories_main+='<div class="empty" id="category-empty" role="status" hidden><h2>Такого направления пока нет</h2><p>Попробуйте другое название задачи или профессии.</p></div>'
    shell('categories.html','Категории ИИ: инструменты по задачам','Все направления каталога НейроРейтинга: перейдите к сервисам по нужной задаче.',categories_main)
    for t in eligible:
        root='../';cover=t.get('detail_cover') or t.get('cover');logo=t.get('logo');logohtml=f'<img class="tool-logo" src="{root+E(logo)}" alt="">' if logo else f'<span class="tool-logo letter-logo" aria-hidden="true">{E(t["name"][:1])}</span>'
        catslinks=''.join(f'<a href="../category/{c}.html">{E(catby[c]["name"])}</a>' for c in t['categories'])
        caption=t.get('screenshot_caption') or (('Обложка сервиса ' if t.get('screenshot_status') in ('source_logo','placeholder','unavailable') else 'Страница сервиса ')+t['name'])
        genuine_cover=bool(cover) and (bool(t.get('detail_cover')) or t.get('screenshot_status') not in ('source_logo','placeholder','unavailable'))
        screenshot=f'<figure class="detail-screenshot"><img src="{root+E(cover)}" alt="{E(caption)}" loading="lazy"><figcaption>{E(caption)}</figcaption></figure>' if genuine_cover else ''
        relatedids=[];seen={t['id']}
        for c in t['categories']:
            for x in category_items[c]:
                if x['id'] not in seen:
                    relatedids.append(x['id']);seen.add(x['id'])
                if len(relatedids)>=6:break
            if len(relatedids)>=6:break
        if t['id']!='molecula':relatedids=['molecula']+[x for x in relatedids if x!='molecula']
        reviews=f'<section class="review-box" id="reviews"><h2>Ваш опыт с {E(t["name"])}</h2><p>Отзыв сохраняется только в этом браузере.</p><div id="review-list"></div><form id="review-form"><div class="form-grid"><label class="field">Ваше имя<input name="name" required maxlength="60" autocomplete="name"></label><label class="field">Оценка<select name="rating"><option>5</option><option>4</option><option>3</option><option>2</option><option>1</option></select></label></div><label class="field">Отзыв<textarea name="text" required maxlength="5000"></textarea></label><button class="btn primary">Сохранить отзыв</button></form></section>'
        task_offer=t.get('molecula_offer') or next((catby[c].get('molecula_offer') for c in t['categories'] if catby[c].get('molecula_offer')),None) or general_offer
        main=bread(t['name'],root)+f'<section class="detail-hero">{logohtml}<div class="detail-title"><h1>{E(t["name"])}</h1><p>{E(t["description"])}</p><div class="card-tags">{catslinks}</div><button class="btn" data-favorite="{t["id"]}" aria-pressed="false">В избранное</button>'+('<a class="btn primary" href="https://moleculai.ru/">Открыть Молекулу</a>' if t['pinned'] else '')+'</div></section><div class="detail-layout"><div class="detail-main">'+screenshot+'<div class="author-credit"><span class="editorial-symbol" aria-hidden="true">N</span><div><a href="../author/editorial.html">Редакция НейроРейтинга</a><small><a href="../methodology.html">Правила рейтинга</a></small></div></div><article class="prose">'+t['content']+'</article>'+render_offer(task_offer,root)+reviews+'</div><aside class="detail-aside"><section class="info-panel"><h2>О сервисе</h2><div class="info-row"><span>Доступ</span><strong>'+E(t['price'])+'</strong></div><div class="info-row"><span>Внутренний балл</span><strong>'+f'{float(t["score"]):.1f} / 5'+'</strong></div><div class="card-tags">'+catslinks+'</div></section></aside></div><section><div class="section-title"><h2>Инструменты для сравнения</h2></div><div class="nr-related-grid">'+''.join(related_link(toolby[x],root) for x in relatedids[:6])+'</div></section>'
        shell('tools/'+t['id']+'.html',t['meta_title'],t['meta_description'],main,tool=t['id'])
    # Public index intentionally excludes full article prose and research/provenance URLs.
    oldjs=(src/'assets/data.js').read_text();client=json.loads(oldjs.removeprefix('window.NR=').rstrip(';\n'))
    allowed=('id','name','description','categories','tags','price','pricing_type','platforms','capabilities','languages','logo','cover','score','category_scores','pinned','order')
    client['tools']=[{k:t[k] for k in allowed if k in t} for t in eligible]
    client['categories']=[{**{k:c[k] for k in ('id','name','icon','kind','type') if k in c},**({'offer_url':c['molecula_offer']['url']} if c.get('molecula_offer') else {})} for c in cats];client['featured']=[t['id'] for t in active[:24]]
    if general_offer:client['molecula_url']=general_offer['url']
    (out/'assets/data.js').write_text('window.NR='+json.dumps(client,ensure_ascii=False,separators=(',',':'))+';')
    public_tools=('id','name','description','content','meta_title','meta_description','categories','tags','price','pricing_type','platforms','capabilities','languages','logo','cover','detail_cover','score','category_scores','pinned','order','url','content_date','screenshot_status','score_status','canonical_id','screenshot_caption','molecula_offer','schema_type')
    public_cats=('id','name','description','content','meta_title','meta_description','icon','kind','type','molecula_offer')
    public_data={'tools':[{k:t[k] for k in public_tools if k in t} for t in tools],'categories':[{k:c[k] for k in public_cats if k in c} for c in cats]}
    if general_offer:public_data['molecula_offer']=general_offer
    if page_offers:public_data['pages_molecula_offers']={key:value for key,value in page_offers.items() if value}
    for key in ('articles','collections'):
        if key in data:
            records=[]
            for original in data[key]:
                record=dict(original)
                if isinstance(record.get('tools'),list):record['tools']=[tool for tool in record['tools'] if (tool.get('id') if isinstance(tool,dict) else tool) not in excluded]
                if record.get('content'):
                    fragment=clean_public(markup(record['content']))
                    for anchor in fragment.xpath('.//a[@href]'):
                        href=anchor.get('href','').split('?',1)[0].split('#',1)[0]
                        if any(href.endswith('tools/'+slug+'.html') for slug in excluded):anchor.drop_tree()
                    record['content']=(fragment.text or '')+''.join(html.tostring(child,encoding='unicode') for child in fragment)
                records.append(record)
            public_data[key]=records
    public_bytes=json.dumps(public_data,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    if len(public_bytes)>8*1024*1024:
        (out/'catalog-data.json.gz').write_bytes(gzip.compress(public_bytes,compresslevel=9,mtime=0))
        (out/'catalog-data.json').unlink(missing_ok=True)
    else:
        (out/'catalog-data.json').write_bytes(public_bytes)
        (out/'catalog-data.json.gz').unlink(missing_ok=True)
    # Strip the removed notice from preserved editorial/collection/utility pages too.
    written_set=set(written)
    for path in out.rglob('*.html'):
        if path.relative_to(out).as_posix() in written_set:continue
        tree=html.parse(str(path));depth=len(path.relative_to(out).parts)-1;enhance_tree(tree,'../'*depth or './')
        update_sidebar_counts(tree,len(active),len(cats),category_counts)
        alias=toolby.get(path.stem) if path.parent==out/'tools' else None
        if alias and alias.get('canonical_id'):
            target=toolby[alias['canonical_id']];target_url=base+'tools/'+target['id']+'.html';head=tree.xpath('//head')[0]
            for node in head.xpath('./meta[@name="robots"]|./link[@rel="canonical"]|./meta[@property="og:url"]|./meta[translate(@http-equiv,"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz")="refresh"]|./script[@type="application/ld+json"]'):
                head.remove(node)
            etree.SubElement(head,'meta',name='robots',content='noindex, follow')
            etree.SubElement(head,'link',rel='canonical',href=target_url)
            etree.SubElement(head,'meta',property='og:url',content=target_url)
            etree.SubElement(head,'meta',attrib={'http-equiv':'refresh','content':'0; url='+target['id']+'.html'})
            for title in head.xpath('./title'):title.text=target['meta_title']
            for meta in head.xpath('./meta[@property="og:title"]'):meta.set('content',target['meta_title'])
            for meta in head.xpath('./meta[@name="description"]|./meta[@property="og:description"]'):meta.set('content',target['meta_description'])
            mains=tree.xpath('//main')
            if mains:
                for child in list(mains[0]):mains[0].remove(child)
                mains[0].text=None;article=etree.SubElement(mains[0],'article',attrib={'class':'prose'})
                etree.SubElement(article,'h1').text=target['name']
                paragraph=etree.SubElement(article,'p');paragraph.text='Карточка сервиса находится по постоянному адресу. '
                etree.SubElement(paragraph,'a',href=target['id']+'.html').text='Перейти к обзору '+target['name']
        for old_offer in tree.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," nr-task-offer ")]'):
            old_offer.getparent().remove(old_offer)
        offer=page_offers.get(path.relative_to(out).as_posix()) or general_offer
        is_alias=any('noindex' in node.get('content','') for node in tree.xpath('//meta[@name="robots"]'))
        rendered=render_offer(offer,'../'*depth or './',compact=True) if not is_alias else ''
        if rendered:
            mains=tree.xpath('//main')
            if mains:
                block=markup(rendered)[0];footers=mains[0].xpath('./footer')
                if footers:footers[0].addprevious(block)
                else:mains[0].append(block)
        if path.name=='about.html':
            for paragraph in tree.xpath('//article[contains(@class,"prose")]//p'):
                if paragraph.text and re.match(r'^\d+ сервисов в \d+ направлениях\.',paragraph.text):
                    paragraph.text=re.sub(r'^\d+ сервисов в \d+ направлениях\.',f'{len(active)} сервисов в {len(cats)} направлениях.',paragraph.text)
        for anchor in tree.xpath('//a[@href]'):
            href=anchor.get('href','').split('?',1)[0].split('#',1)[0]
            if any(href.endswith('tools/'+slug+'.html') for slug in excluded):
                cards=anchor.xpath('ancestor::*[contains(concat(" ",normalize-space(@class)," ")," tool-card ")]')
                if cards:
                    card=cards[-1]
                    if card.getparent() is not None:card.getparent().remove(card)
                elif anchor.getparent() is not None:anchor.drop_tree()
        canonical=tree.xpath('//link[@rel="canonical"]')
        if canonical:
            for link in canonical:
                if link.get('href','').startswith(previous_base):link.set('href',base+link.get('href')[len(previous_base):])
            for meta in tree.xpath('//meta[@property="og:url"]'):meta.set('content',canonical[0].get('href',''))
        for meta in tree.xpath('//meta[@property="og:image"]'):
            if meta.get('content','').startswith(previous_base):meta.set('content',base+meta.get('content')[len(previous_base):])
        for script in tree.xpath('//script[@type="application/ld+json"]'):
            if script.text and previous_base in script.text:script.text=script.text.replace(previous_base,base)
        path.write_text(html.tostring(tree,encoding='unicode',doctype='<!doctype html>'))
    sitemap=etree.Element('urlset',nsmap={None:'http://www.sitemaps.org/schemas/sitemap/0.9'})
    urls=set(written)
    for path in out.rglob('*.html'):
        tree=html.parse(str(path))
        if not any('noindex' in m.get('content','') for m in tree.xpath('//meta[@name="robots"]')):urls.add(path.relative_to(out).as_posix())
    for path in sorted(urls):etree.SubElement(etree.SubElement(sitemap,'url'),'loc').text=base+path
    (out/'sitemap.xml').write_bytes(etree.tostring(sitemap,encoding='UTF-8',xml_declaration=True))
    (out/'robots.txt').write_text('User-agent: *\nAllow: /\nSitemap: '+base+'sitemap.xml\n')
    cover_stats=None
    if getattr(args,'optimize_covers',False):
        from optimize_covers import optimize_covers
        cover_stats=optimize_covers(out,tools)
    svg_stats=compact_tree(out)
    version_stats=version_assets(out)
    report={'excluded_tool_ids':sorted(excluded),'referenced_assets':len(referenced),'tools':len(eligible),'alias_records':len(tools)-len(eligible),'categories':len(cats),'generated_pages':len(written),'indexable_pages':len(urls),'output':out.name,'notice_removed':True}
    report['svg_optimization']={key:svg_stats[key] for key in ('svg_instances_replaced','unique_shapes','saved_bytes')}
    report['asset_versioning']=version_stats
    if cover_stats:
        report['cover_optimization']={key:cover_stats[key] for key in ('candidate_assets','converted_assets','originals_removed','files_rewritten','saved_bytes')}
        report['cover_optimization']['error_count']=len(cover_stats['errors'])
    (out/'BUILD-REPORT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);parser.add_argument('--input',required=True);parser.add_argument('--out',required=True);parser.add_argument('--base',required=True);parser.add_argument('--overwrite',action='store_true');parser.add_argument('--optimize-covers',action='store_true',help='Compress declared genuine opaque PNG covers to WebP in output only (requires Pillow)');parser.add_argument('--exclude-pages',nargs='*',default=[],help='Tool slugs to omit and remove from copied source pages');parser.add_argument('--extra-assets',help='Private imported asset root containing thumbs/details/icons');run(parser.parse_args())
