"""SQLite persistence with transactional approval and optimistic concurrency."""
import json
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import uuid


class Conflict(ValueError):
    pass


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, scenario TEXT NOT NULL, mode TEXT NOT NULL,
                    status TEXT NOT NULL, document TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS decisions (
                    run_id TEXT NOT NULL, action_id TEXT NOT NULL,
                    version INTEGER NOT NULL, decision TEXT NOT NULL, reason TEXT NOT NULL,
                    result TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(run_id, action_id)
                );
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, scenario, mode):
        run_id = uuid.uuid4().hex
        document = {'id':run_id, 'scenario':scenario, 'mode':mode, 'status':'queued',
                    'events':[], 'evidence':{}, 'actions':[], 'answer':None, 'usage':{}, 'errors':[]}
        with self.connect() as db:
            db.execute('INSERT INTO runs(id,scenario,mode,status,document) VALUES(?,?,?,?,?)',
                       (run_id,scenario,mode,'queued',json.dumps(document)))
        return document

    def save(self, document):
        with self.connect() as db:
            db.execute('UPDATE runs SET status=?,document=? WHERE id=?',
                       (document['status'],json.dumps(document),document['id']))

    def get(self, run_id):
        with self.connect() as db:
            row = db.execute('SELECT document FROM runs WHERE id=?',(run_id,)).fetchone()
            if row is None:
                raise KeyError('Investigation not found')
            document = json.loads(row['document'])
            decisions = db.execute('SELECT * FROM decisions WHERE run_id=? ORDER BY created_at', (run_id,)).fetchall()
            document['decisions'] = [dict(r, result=json.loads(r['result'])) for r in decisions]
            return document

    def list(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT id,scenario,mode,status,created_at FROM runs ORDER BY rowid DESC LIMIT 30')]

    def decide(self, run_id, action_id, decision, expected_version, reason):
        if decision not in {'approve','reject'} or type(expected_version) is not int or expected_version != 0:
            raise ValueError('Expected approve/reject and pending version 0')
        if not isinstance(reason, str) or not 3 <= len(reason.strip()) <= 500:
            raise ValueError('An operator reason of 3–500 characters is required')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT document FROM runs WHERE id=?',(run_id,)).fetchone()
            if row is None:
                raise KeyError('Investigation not found')
            document = json.loads(row['document'])
            if document['status'] != 'complete':
                raise Conflict('Only completed investigations can receive a decision')
            action = next((a for a in document['actions'] if a['id'] == action_id), None)
            if action is None:
                raise KeyError('Action not found')
            if db.execute('SELECT 1 FROM decisions WHERE run_id=? AND action_id=?',(run_id,action_id)).fetchone():
                raise Conflict('This action already has a decision')
            # This state change is purely a simulation record. There is no external executor.
            result = {'environment':'sandbox', 'state':'simulated_applied' if decision == 'approve' else 'rejected',
                      'kind':action['kind'], 'target':action['target'], 'external_system_changed':False}
            db.execute('INSERT INTO decisions(run_id,action_id,version,decision,reason,result) VALUES(?,?,?,?,?,?)',
                       (run_id,action_id,1,decision,reason.strip(),json.dumps(result)))
            return result
