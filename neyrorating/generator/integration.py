"""Import `enhance_tree(tree, root, homepage=False)` into the parent HTML builder.
No canonical files are edited by this helper itself.
"""
from lxml import etree,html

def enhance_tree(tree, root='./', homepage=False):
    head=tree.find('head') if hasattr(tree,'find') else None
    body=tree.find('body') if hasattr(tree,'find') else None
    if head is None or body is None:
        return tree
    if not head.xpath('.//link[contains(@href,"v2.css")]'):
        head.append(html.Element('link',rel='stylesheet',href=root+'assets/v2.css'))
    for s in tree.xpath('//script[@src]'):
        if s.get('src','').endswith(('data.js','app.js','ui-v2.js')):
            s.set('defer','defer')
    if not tree.xpath('//script[contains(@src,"ui-v2.js")]'):
        body.append(html.Element('script',src=root+'assets/ui-v2.js',defer='defer'))
    # User requested removal across every page; retain the methodology page/footer link.
    for notice in tree.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," demo-notice ")]'):
        parent=notice.getparent()
        if parent is not None:
            parent.remove(notice)
    if homepage:
        intros=tree.xpath('//div[contains(concat(" ",normalize-space(@class)," ")," intro ")]')
        if intros:
            intro=intros[0]
            intro.set('class',intro.get('class')+' nr-hero')
        links=tree.xpath('//section[@class="home-links"]')
        starts=tree.xpath('//*[@id="catalog-start"]')
        if links and starts:
            start=starts[0]
            parent=start.getparent()
            # Existing sections already after the catalogue retain their order.
            for section in links:
                if section.getparent() is parent and parent.index(section)<parent.index(start):
                    parent.remove(section)
                    start.addnext(section)
    return tree

# Optional server-rendered version of the review TOC; avoids requiring JS.
def review_toc(prose):
    headings=prose.xpath('.//h2')
    if len(headings)<3:
        return None
    nav=html.Element('nav',{'class':'nr-toc info-panel','aria-label':'Содержание обзора'})
    title=etree.SubElement(nav,'h2');title.text='В этом обзоре'
    ol=etree.SubElement(nav,'ol')
    for index,h in enumerate(headings,1):
        identifier=h.get('id') or 'review-section-'+str(index)
        h.set('id',identifier)
        h.set('style','scroll-margin-top:100px')
        li=etree.SubElement(ol,'li');a=etree.SubElement(li,'a',href='#'+identifier)
        a.text=''.join(h.itertext())
    return nav
