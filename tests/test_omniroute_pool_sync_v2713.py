import importlib.util
from pathlib import Path


def load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / 'scripts/omniroute_pool_sync.py'
    spec = importlib.util.spec_from_file_location('pool_sync_v2713', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_free_classifier_is_fail_closed():
    mod = load_module()
    assert mod._is_openrouter_free({'id':'openrouter/foo/bar:free'})
    assert mod._is_openrouter_free({'id':'openrouter/foo/bar', 'pricing':{'prompt':'0','completion':'0'}})
    assert not mod._is_openrouter_free({'id':'openrouter/foo/bar'})
    assert not mod._is_openrouter_free({'id':'ollama/foo:free'})


def test_expanded_combo_preserves_existing_order():
    mod = load_module()
    src = {'models':[{'model':'openrouter/a:free'},{'model':'openrouter/b:free'}], 'strategy':'priority'}
    body = mod._combo_body('Conding-free', ['openrouter/a:free','openrouter/b:free','openrouter/c:free'], src)
    assert [x['model'] for x in body['models']] == [
        'openrouter/a:free','openrouter/b:free','openrouter/c:free'
    ]


def test_transactional_expand_success(monkeypatch, tmp_path):
    mod = load_module()
    mod.ROOT = tmp_path
    mod.SNAPSHOT_DIR = tmp_path / 'snapshots'
    baseline = {
        'id':'orig-id','name':'Conding-free','models':[{'model':'openrouter/a:free'}],
        'strategy':'priority','config':{'maxRetries':1}
    }
    store = {'Conding-free': dict(baseline)}
    seq = {'id':0}

    def create(body, key):
        seq['id'] += 1
        row = dict(body); row['id'] = f'id-{seq["id"]}'
        store[body['name']] = row
        return True, 'fake'
    def delete(cid, key):
        for name,row in list(store.items()):
            if row.get('id') == cid:
                del store[name]
                return True, 200
        return False, 404
    def find(name): return store.get(name)
    def probe(name, key, timeout=1): return (name in store, 200 if name in store else 404, 'openrouter/a:free')

    monkeypatch.setattr(mod, '_create_combo', create)
    monkeypatch.setattr(mod, '_delete_combo', delete)
    monkeypatch.setattr(mod, '_find_combo', find)
    monkeypatch.setattr(mod, '_probe', probe)
    status = {}
    ok = mod._transactional_expand(baseline, ['openrouter/a:free','openrouter/b:free'], 'k', status)
    assert ok is True
    assert status['baseline_update'] == 'expanded_and_verified'
    assert [x['model'] for x in store['Conding-free']['models']] == ['openrouter/a:free','openrouter/b:free']
    assert not any(n.startswith('Conding-free-candidate-') or n.startswith('Conding-free-backup-') for n in store)


def test_transactional_expand_rolls_back_when_final_probe_fails(monkeypatch, tmp_path):
    mod = load_module()
    mod.ROOT = tmp_path
    baseline = {
        'id':'orig-id','name':'Conding-free','models':[{'model':'openrouter/a:free'}],
        'strategy':'priority','config':{'maxRetries':1}
    }
    store = {'Conding-free': dict(baseline)}
    seq = {'id':0, 'baseline_creations':0}
    def create(body, key):
        seq['id'] += 1
        if body['name'] == 'Conding-free': seq['baseline_creations'] += 1
        row = dict(body); row['id'] = f'id-{seq["id"]}'
        store[body['name']] = row
        return True, 'fake'
    def delete(cid, key):
        for name,row in list(store.items()):
            if row.get('id') == cid:
                del store[name]; return True, 200
        return False,404
    def find(name): return store.get(name)
    def probe(name, key, timeout=1):
        if name.startswith('Conding-free-candidate-'): return True,200,'x'
        if name == 'Conding-free':
            models=[x['model'] for x in store.get(name,{}).get('models',[])]
            if 'openrouter/b:free' in models: return False,500,''
            return True,200,'openrouter/a:free'
        return True,200,'x'
    monkeypatch.setattr(mod,'_create_combo',create)
    monkeypatch.setattr(mod,'_delete_combo',delete)
    monkeypatch.setattr(mod,'_find_combo',find)
    monkeypatch.setattr(mod,'_probe',probe)
    status={}
    ok=mod._transactional_expand(baseline,['openrouter/a:free','openrouter/b:free'],'k',status)
    assert ok is False
    assert status['baseline_update']=='rolled_back'
    assert [x['model'] for x in store['Conding-free']['models']] == ['openrouter/a:free']
