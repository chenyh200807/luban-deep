import gzip, json, re, collections
rows=[json.loads(l) for l in gzip.open("qb_full_snapshot.jsonl.gz","rt")]
byid={r['id']:r for r in rows}
refs={int(k):v for k,v in json.load(open("refs_by_qid.json")).items()}

MARK=re.compile(r'【(题干|问题|背景资料)】')
PUNCT=re.compile(r'[\s　，。、；：？！“”‘’（）()《》〈〉·—…\-,.;:?!"\'\[\]{}<>/\\|`~@#$%^&*_+=]')
LEADNUM=re.compile(r'^[（(]?\d{1,3}[）).、．]?')
def norm(s):
    s=s or ''
    s=MARK.sub('',s)
    s=LEADNUM.sub('',s.strip())
    return PUNCT.sub('',s)
def stemof(r): return r.get('question_stem') or r.get('stem') or ''

fam=collections.defaultdict(list)
for r in rows:
    k=norm(stemof(r))
    if k: fam[k].append(r)

REINGEST=re.compile(r'^EXAM_(19|20)\d{2}_')
def ans_text(r):
    """Unwrap the serialization difference the re-ingest batch introduced (str -> ["str"]).
    Per plan 3.x: array-wrapping is NOT an authority signal."""
    ca=r.get('correct_answer')
    if ca is None: return ''
    while isinstance(ca,list) and len(ca)==1: ca=ca[0]
    if isinstance(ca,str): return ca.strip()
    return json.dumps(ca,ensure_ascii=False)

CONTRIB_COLS=['source_chunk_id','analysis','grading_rubric','background_context','source','source_meta',
              'structured_rules','grading_keywords','logic_rule','node_code','exam_year','exam_session',
              'options','testing_focus','trap_type','related_image','image_url','cited_standard_codes',
              'difficulty','tags','option_reasoning','based_on_version','parent_id']
def nonempty(v):
    if v is None: return False
    if isinstance(v,str): return v.strip()!=''
    if isinstance(v,(list,dict)): return len(v)>0
    return True

cand=[]; rejected=collections.Counter()
for k,g in fam.items():
    if len(g)<2: continue
    inb=[r for r in g if REINGEST.match(r.get('original_id') or '')]
    out=[r for r in g if not REINGEST.match(r.get('original_id') or '')]
    if not inb or not out: continue
    for r in inb:
        why=[]
        if nonempty(r.get('source_chunk_id')): why.append('has_chunk')
        # contributes nothing the out-of-batch twins lack
        contrib=[c for c in CONTRIB_COLS if nonempty(r.get(c)) and not any(nonempty(o.get(c)) for o in out)]
        if contrib: why.append('contributes:'+','.join(contrib))
        # answer not longer than best twin
        if len(ans_text(r))>max(len(ans_text(o)) for o in out): why.append('answer_longer')
        held=refs.get(r['id'],[])
        if held: why.append('referenced:'+','.join(held))
        for w in why: rejected[w.split(':')[0]]+=1
        if why: pass
        else: cand.append({'id':r['id'],'original_id':r['original_id'],'source_type':r['source_type'],
                           'question_type':r['question_type'],'family_key':k[:60],
                           'keep_candidates':[o['id'] for o in out]})
cand.sort(key=lambda x:x['id'])
print("B1 candidates (re-ingest, twin outside batch, no chunk, contributes nothing, answer<=twin, ZERO downstream refs):", len(cand))
print("rejected reasons:", dict(rejected))
ids=[c['id'] for c in cand]
print("id range", min(ids), max(ids), "| within 17059-17509:", sum(1 for i in ids if 17059<=i<=17509))
json.dump(cand, open("b1_candidates.json","w"), ensure_ascii=False, indent=1)
# also: referenced re-ingest twins = B2
b2=[]
for k,g in fam.items():
    if len(g)<2: continue
    inb=[r for r in g if REINGEST.match(r.get('original_id') or '')]
    out=[r for r in g if not REINGEST.match(r.get('original_id') or '')]
    if not inb or not out: continue
    for r in inb:
        if refs.get(r['id']): b2.append(r['id'])
print("B2 (same shape but referenced):", len(sorted(set(b2))))
json.dump(sorted(set(b2)), open("b2_referenced.json","w"))
