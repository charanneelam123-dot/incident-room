from concurrent.futures import ThreadPoolExecutor
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from incident_room.agent import Investigator, validate_answer
from incident_room.evaluate import evaluate
from incident_room.store import Conflict, Store
from incident_room.tools import Tools, retrieve, scenario_by_id, scenarios


class SystemTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store = Store(Path(self.folder.name)/'test.sqlite')

    def run_example(self):
        return Investigator(self.store).investigate('checkout-pool')

    def test_all_replays_complete_with_correct_pending_actions(self):
        for scenario in scenarios():
            with self.subTest(scenario=scenario['id']):
                run = Investigator(self.store).investigate(scenario['id'])
                self.assertEqual(run['status'],'complete')
                self.assertEqual(run['answer']['diagnosis'],scenario['expected_diagnosis'])
                self.assertEqual(run['actions'][0]['status'],'pending_approval')
                self.assertEqual(run['decisions'],[])
                self.assertEqual(run['tool_calls'],7)

    def test_replay_eval_is_labeled(self):
        report = evaluate(self.store)
        self.assertEqual((report['passed'],report['total']), (3,3))
        self.assertEqual(report['mode'],'replay')
        self.assertIn('authored',report['warning'])

    def test_metrics_sql_calculates_error_rate(self):
        run = self.run_example()
        row = next(r for r in run['evidence']['E1']['result']['rows'] if r['window'] == 'after')
        self.assertEqual(row['error_percent'],25.0)

    def test_runbook_search_ranks_relevant_section(self):
        self.assertEqual(retrieve('expired credential')[0]['source'],'runbook-2')
        self.assertEqual(retrieve('qzxnotaword'),[])

    def test_unknown_tools_and_sql_injection_blocked(self):
        run = self.run_example()
        tools = Tools(scenario_by_id('checkout-pool'),run)
        for name,args in [('shell',{'command':'anything'}),('metrics',{'service':"checkout'; DROP TABLE metrics"}),('logs',{'service':'checkout','extra':1}),('logs',[]),('search_runbooks',{'query':123})]:
            with self.subTest(name=name,args=args):
                self.assertIn('error',tools.call(name,args))

    def test_wrong_action_target_blocked(self):
        run = self.run_example()
        tools = Tools(scenario_by_id('checkout-pool'),run)
        args = dict(scenario_by_id('checkout-pool')['allowed_action'],target='production',evidence_ids=['E2','E3'],reason='test reason')
        self.assertIn('error',tools.call('propose_action',args))

    def test_unknown_evidence_blocks_action(self):
        run = self.run_example()
        args = dict(scenario_by_id('checkout-pool')['allowed_action'],evidence_ids=['invented'],reason='test reason')
        self.assertIn('error',Tools(scenario_by_id('checkout-pool'),run).call('propose_action',args))

    def test_empty_or_other_service_evidence_blocks_action(self):
        run = self.run_example()
        run['evidence']['E2']['arguments']['service'] = 'payments'
        args = dict(scenario_by_id('checkout-pool')['allowed_action'],evidence_ids=['E2','E3'],reason='test reason')
        self.assertIn('error',Tools(scenario_by_id('checkout-pool'),run).call('propose_action',args))

    def test_duplicate_proposal_is_idempotent(self):
        run = self.run_example()
        args = dict(scenario_by_id('checkout-pool')['allowed_action'],evidence_ids=['E2','E3'],reason='test reason')
        Tools(scenario_by_id('checkout-pool'),run).call('propose_action',args)
        self.assertEqual(len(run['actions']),1)

    def test_bad_quote_rejected(self):
        run = self.run_example()
        run['answer']['findings'][0]['quote'] = 'invented provider message'
        with self.assertRaises(ValueError):
            validate_answer(run['answer'],run['evidence'])

    def test_unknown_evidence_rejected(self):
        run = self.run_example()
        run['answer']['findings'][0]['evidence_id'] = 'E999'
        with self.assertRaises(ValueError):
            validate_answer(run['answer'],run['evidence'])

    def test_action_cannot_be_cited_as_observation(self):
        run = self.run_example()
        run['answer']['findings'][0]['evidence_id'] = 'E7'
        with self.assertRaises(ValueError):
            validate_answer(run['answer'],run['evidence'])

    def test_budget_stop_preserves_partial_evidence(self):
        run = Investigator(self.store,max_calls=1).investigate('checkout-pool')
        self.assertEqual(run['status'],'incomplete')
        self.assertEqual(len(run['evidence']),1)
        self.assertIsNone(run['answer'])

    @patch.dict(os.environ,{},clear=True)
    def test_missing_live_credentials_is_visible_failure(self):
        run = Investigator(self.store).investigate('checkout-pool',True)
        self.assertEqual(run['status'],'incomplete')
        self.assertIn('OPENAI_API_KEY',run['errors'][0])

    @patch('incident_room.agent.model_call')
    def test_live_loop_calls_tools_and_repairs_rejected_report(self,mock):
        replay = self.run_example()
        tool_calls = []
        for n,(name,args) in enumerate([('metrics',{'service':'checkout'}),('logs',{'service':'checkout'}),('deployments',{'service':'checkout'}),('search_runbooks',{'query':'connection pool'}),('metrics',{'service':'payments'})]):
            tool_calls.append({'id':str(n),'type':'function','function':{'name':name,'arguments':json.dumps(args)}})
        # Four calls per turn maximum, followed by an invalid quote and a corrected final response.
        bad_answer = copy.deepcopy(replay['answer'])
        bad_answer['findings'][0]['quote'] = 'an invented line of text'
        mock.side_effect = [({'role':'assistant','tool_calls':tool_calls[:4]}, {'total_tokens':10}),
                            ({'role':'assistant','tool_calls':tool_calls[4:]}, {'total_tokens':10}),
                            ({'role':'assistant','content':json.dumps(bad_answer)}, {'total_tokens':10}),
                            ({'role':'assistant','content':json.dumps(replay['answer'])}, {'total_tokens':10})]
        run = Investigator(self.store).investigate('checkout-pool',True)
        self.assertEqual(run['status'],'complete')
        self.assertEqual(run['usage']['total_tokens'],40)
        self.assertTrue(any(e['kind'] == 'validation_rejected' for e in run['events']))

    @patch('incident_room.agent.model_call',return_value=({'role':'assistant','tool_calls':[{'id':'x','function':{'name':'logs','arguments':'{"service":"checkout"}'}}]}, {'total_tokens':10}))
    def test_model_step_budget_is_enforced(self,mock):
        run = Investigator(self.store,max_steps=2).investigate('checkout-pool',True)
        self.assertEqual(run['status'],'incomplete')
        self.assertEqual(mock.call_count,2)

    @patch('incident_room.agent.model_call',return_value=({'role':'assistant','content':'{}'}, {'total_tokens':50}))
    def test_token_budget_stops_before_another_call(self,mock):
        run = Investigator(self.store,token_budget=20).investigate('checkout-pool',True)
        self.assertEqual(run['status'],'incomplete')
        self.assertEqual(mock.call_count,1)

    def test_approval_writes_only_sandbox_record(self):
        run = self.run_example()
        result = self.store.decide(run['id'],'action-1','approve',0,'Checked original observations')
        self.assertEqual(result['state'],'simulated_applied')
        self.assertFalse(result['external_system_changed'])
        self.assertEqual(len(self.store.get(run['id'])['decisions']),1)

    def test_rejection_does_not_apply_simulation(self):
        run = self.run_example()
        self.assertEqual(self.store.decide(run['id'],'action-1','reject',0,'Need another check')['state'],'rejected')

    def test_duplicate_approval_conflicts(self):
        run = self.run_example()
        self.store.decide(run['id'],'action-1','approve',0,'Checked evidence')
        with self.assertRaises(Conflict):
            self.store.decide(run['id'],'action-1','approve',0,'Checked evidence again')

    def test_concurrent_approvals_only_one_wins(self):
        run = self.run_example()
        def decide(_):
            try:
                self.store.decide(run['id'],'action-1','approve',0,'Checked evidence')
                return 'won'
            except Conflict:
                return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(pool.map(decide,range(2)),['won','conflict'])

    def test_incomplete_investigation_cannot_be_approved(self):
        run = self.run_example()
        run['status'] = 'incomplete'
        self.store.save(run)
        with self.assertRaises(Conflict):
            self.store.decide(run['id'],'action-1','approve',0,'Checked evidence')

    def test_wrong_version_and_empty_reason_blocked(self):
        run = self.run_example()
        for version,reason in [(1,'Checked'),(False,'Checked'),(0,' ')]:
            with self.subTest(version=version,reason=reason),self.assertRaises(ValueError):
                self.store.decide(run['id'],'action-1','approve',version,reason)

    def test_reopen_preserves_run_and_decision(self):
        run = self.run_example()
        self.store.decide(run['id'],'action-1','reject',0,'Need more evidence')
        reopened = Store(self.store.path).get(run['id'])
        self.assertEqual(reopened['answer'],run['answer'])
        self.assertEqual(reopened['decisions'][0]['decision'],'reject')


if __name__ == '__main__':
    unittest.main()
