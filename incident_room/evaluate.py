"""Replay regression checks, not a model-quality benchmark."""
from .agent import Investigator
from .tools import scenarios


def evaluate(store, live=False):
    rows = []
    for scenario in scenarios():
        run = Investigator(store).investigate(scenario['id'], live)
        answer = run['answer'] or {}
        checks = {'completed':run['status'] == 'complete',
                  'diagnosis_term':scenario['expected_diagnosis'] in answer.get('diagnosis','').casefold(),
                  'expected_action':any(a['kind'] == scenario['expected_action'] for a in run['actions']),
                  'cited_findings':bool(answer.get('findings')),
                  'no_execution':not run['decisions']}
        rows.append({'scenario':scenario['id'],'run_id':run['id'],'checks':checks,'passed':all(checks.values()),
                     'tool_calls':run['tool_calls'],'usage':run['usage'],'elapsed_ms':run['elapsed_ms']})
    return {'mode':'live' if live else 'replay', 'warning':'Replay answers use authored expected diagnoses. Term checks do not establish semantic correctness.',
            'passed':sum(r['passed'] for r in rows),'total':len(rows),'rows':rows}
