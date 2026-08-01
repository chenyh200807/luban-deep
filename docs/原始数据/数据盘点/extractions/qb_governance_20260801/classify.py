import gzip,json,re,collections
rows=[json.loads(l) for l in gzip.open("backup_task22_rows.jsonl.gz","rt")]
def txt(r): return (r.get('question_stem') or r.get('stem') or '')
MCQ=re.compile(r'(下列|以下).{0,30}(的是|包括|有)\s*[?？:：]?\s*$|正确的是|错误的是|不正确的是|不属于|属于.{0,10}的是|哪项|哪一项|哪个')
BLANK=re.compile(r'_{2,}|＿{2,}|__')
CASE=re.compile(r'【背景资料】|背景资料|事件[一二三四五六1-6]|问题\s*[1-6一二三四五六]\s*[：:.、]')
agg=collections.defaultdict(collections.Counter)
disputes=collections.defaultdict(list)
for r in rows:
    st=r['source_type']; s=txt(r)
    a=agg[st]
    a['n']+=1
    if r.get('options'): a['has_options']+=1
    if (r.get('background_context') or '').strip(): a['has_bg']+=1; disputes[st].append(('bg',r['id']))
    if CASE.search(s): a['case_marker']+=1; disputes[st].append(('case_marker',r['id']))
    if BLANK.search(s): a['blank']+=1
    elif MCQ.search(s): a['mcq_shaped']+=1
    else: a['open_short']+=1
    if len(s)<12: a['tiny_stem']+=1
    if r.get('parent_id'): a['has_parent']+=1
    if r.get('case_group_id'): a['has_case_group']+=1
    a['src:'+str(r.get('source'))[:24]]+=1
for st,c in agg.items():
    print('==',st)
    for k,v in sorted(c.items(), key=lambda kv:(-kv[1])): print(f'   {k:34s} {v}')
print()
for st,d in disputes.items():
    print('DISPUTE',st,len(d), collections.Counter(x[0] for x in d))
json.dump({st:[x[1] for x in d] for st,d in disputes.items()}, open('disputes.json','w'))
