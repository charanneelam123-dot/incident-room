"""Read tools and policy-enforced action proposals over synthetic data."""
import json
from contextlib import closing
from importlib.resources import files
import math
from collections import Counter
import re
import sqlite3


def scenarios():
    return json.loads(files('incident_room').joinpath('data/scenarios.json').read_text(encoding='utf-8'))


def scenario_by_id(scenario_id):
    for scenario in scenarios():
        if scenario['id'] == scenario_id:
            return scenario
    raise ValueError('Unknown scenario')


def schema(name, description, properties, required):
    return {'type':'function', 'function':{'name':name,'description':description,
            'parameters':{'type':'object','properties':properties,'required':required,'additionalProperties':False}}}


SERVICE = {'type':'string','enum':['checkout','payments','inventory']}
SCHEMAS = [
    schema('metrics', 'Compare synthetic before/after telemetry for one service.', {'service':SERVICE}, ['service']),
    schema('logs', 'Read timestamped synthetic logs for a service.', {'service':SERVICE}, ['service']),
    schema('deployments', 'Read recent releases and configuration changes for a service.', {'service':SERVICE}, ['service']),
    schema('search_runbooks', 'Retrieve local runbook sections using lexical relevance.', {'query':{'type':'string'}}, ['query']),
    schema('propose_action', 'Queue one allowlisted sandbox action for human approval; never execute it.',
           {'kind':{'type':'string','enum':['rollback_release','rotate_test_credential','disable_feature_flag']},
            'service':SERVICE, 'target':{'type':'string'}, 'evidence_ids':{'type':'array','items':{'type':'string'}},
            'reason':{'type':'string'}}, ['kind','service','target','evidence_ids','reason'])
]


def retrieve(query):
    text = files('incident_room').joinpath('data/runbooks.md').read_text(encoding='utf-8')
    sections = [part.strip() for part in re.split(r'(?m)^# ', text) if part.strip()]
    tokenize = lambda value: re.findall(r'[a-z0-9]+', value.casefold())
    counts = [Counter(tokenize(s)) for s in sections]
    avg = sum(sum(c.values()) for c in counts)/len(counts)
    scores = []
    for index, (section, count) in enumerate(zip(sections, counts), 1):
        score = 0
        for word in set(tokenize(query)):
            df = sum(word in c for c in counts)
            idf = math.log(1+(len(counts)-df+.5)/(df+.5))
            tf = count[word]
            score += idf*tf*2.5/(tf+1.5*(.25+.75*sum(count.values())/avg))
        if score > 0:
            title, _, body = section.partition('\n')
            scores.append({'source':f'runbook-{index}','title':title,'text':body,'score':round(score,4)})
    return sorted(scores,key=lambda row:(-row['score'],row['source']))[:2]


class Tools:
    def __init__(self, scenario, run):
        self.scenario, self.run = scenario, run

    def call(self, name, args):
        definitions = {s['function']['name']:s['function']['parameters'] for s in SCHEMAS}
        if name not in definitions or not isinstance(args, dict):
            return {'error':'Unknown tool or invalid argument object'}
        spec = definitions[name]
        if set(args) != set(spec['required']):
            return {'error':'Missing or unexpected tool arguments'}
        if 'service' in args and args['service'] not in ['checkout','payments','inventory']:
            return {'error':'Unknown service'}
        if name == 'metrics':
            # Real SQL with parameter binding; the model cannot supply arbitrary SQL.
            with closing(sqlite3.connect(':memory:')) as db:
                db.row_factory = sqlite3.Row
                db.execute('CREATE TABLE metrics(service,window,requests,errors,p95_ms,db_connections)')
                db.executemany('INSERT INTO metrics VALUES(:service,:window,:requests,:errors,:p95_ms,:db_connections)',self.scenario['metrics'])
                rows = db.execute('SELECT window,requests,errors,ROUND(100.0*errors/requests,2) AS error_percent,p95_ms,db_connections FROM metrics WHERE service=? ORDER BY window DESC',(args['service'],)).fetchall()
                return {'service':args['service'],'rows':[dict(row) for row in rows],'source':'synthetic telemetry SQL'}
        if name in {'logs','deployments'}:
            return {'service':args['service'],'rows':[row for row in self.scenario[name] if row['service'] == args['service']], 'source':'synthetic '+name}
        if name == 'search_runbooks':
            if not isinstance(args['query'], str) or not 1 <= len(args['query']) <= 300:
                return {'error':'Query must contain 1–300 characters'}
            return {'sections':retrieve(args['query']), 'source':'local runbooks'}
        allowed = self.scenario['allowed_action']
        if any(args[key] != allowed[key] for key in ('kind','service','target')):
            return {'error':'Action is outside this scenario sandbox allowlist'}
        citations = args['evidence_ids']
        if not isinstance(citations, list) or not citations or any(not isinstance(e, str) or e not in self.run['evidence'] for e in citations):
            return {'error':'Action requires existing evidence IDs'}
        observations = [self.run['evidence'][e]['tool'] for e in citations]
        if 'logs' not in observations or 'deployments' not in observations:
            return {'error':'Action needs both log and deployment evidence'}
        for needed in ('logs','deployments'):
            if not any(self.run['evidence'][e]['tool'] == needed
                       and self.run['evidence'][e]['arguments'].get('service') == allowed['service']
                       and self.run['evidence'][e]['result'].get('rows') for e in citations):
                return {'error':'Action requires nonempty observations for the affected service'}
        if not isinstance(args['reason'], str) or not 3 <= len(args['reason']) <= 1000:
            return {'error':'Action reason must contain 3–1000 characters'}
        if self.run['actions']:
            return {'action':self.run['actions'][0], 'duplicate_ignored':True}
        action = {'id':'action-1', **allowed, 'reason':args['reason'], 'evidence_ids':citations,
                  'environment':'sandbox', 'status':'pending_approval','version':0}
        self.run['actions'].append(action)
        return {'action':action, 'executed':False}
