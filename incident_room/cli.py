import argparse
import json
from pathlib import Path

from .agent import Investigator
from .evaluate import evaluate
from .store import Store
from .tools import scenarios


def main(argv=None):
    parser = argparse.ArgumentParser(description='Investigate a simulated outage with evidence-linked tools.')
    parser.add_argument('--db', default='reports/incident-room.sqlite')
    commands = parser.add_subparsers(dest='command', required=True)
    investigate = commands.add_parser('investigate')
    investigate.add_argument('scenario', choices=[s['id'] for s in scenarios()])
    investigate.add_argument('--live',action='store_true')
    investigate.add_argument('--out',type=Path)
    evaluate_parser = commands.add_parser('evaluate')
    evaluate_parser.add_argument('--live',action='store_true')
    decision = commands.add_parser('decide')
    decision.add_argument('run_id')
    decision.add_argument('action_id')
    decision.add_argument('decision',choices=['approve','reject'])
    decision.add_argument('--reason', required=True)
    commands.add_parser('list')
    serve = commands.add_parser('serve')
    serve.add_argument('--port',type=int,default=8787)
    args = parser.parse_args(argv)
    store = Store(args.db)
    if args.command == 'serve':
        from .server import serve
        serve(store,args.port)
        return 0
    try:
        if args.command == 'investigate':
            result = Investigator(store).investigate(args.scenario,args.live)
            if args.out:
                args.out.parent.mkdir(parents=True,exist_ok=True)
                args.out.write_text(json.dumps(result,indent=2),encoding='utf-8')
        elif args.command == 'evaluate':
            result = evaluate(store,args.live)
        elif args.command == 'decide':
            result = store.decide(args.run_id,args.action_id,args.decision,0,args.reason)
        else:
            result = store.list()
    except (KeyError,ValueError,OSError) as error:
        parser.error(str(error))
    print(json.dumps(result,indent=2))
    if args.command == 'investigate' and result['status'] != 'complete':
        return 2
    if args.command == 'evaluate' and result['passed'] != result['total']:
        return 2
    return 0
