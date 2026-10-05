import base64
import json
from unittest.mock import patch

from olympus.agent.action_normalizer import normalize_action_data
from olympus.agent.delivery_sources import DeliverySources
from olympus.agent.executor import ActionExecutor
from tests.test_delivery_sources import commons

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=')


def test_asset_import_saves_local_image_and_retrieved_credit(tmp_path):
    data = commons()
    info = data['query']['pages'][0]['imageinfo'][0]
    info['mime'] = 'image/png'
    info['url'] = 'https://upload.wikimedia.org/wikipedia/commons/a/a1/Coffee.png'
    action = normalize_action_data({'type': 'import_asset', 'target': 'assets/coffee.png',
                                    'payload': {'title': 'File:Coffee.jpg'}})
    with patch.object(DeliverySources, '_json', return_value=data), patch.object(DeliverySources, '_image_bytes', return_value=PNG):
        result = ActionExecutor(str(tmp_path)).execute(action)
    assert result.success, result.error
    assert (tmp_path/'assets/coffee.png').read_bytes() == PNG
    credit = json.loads((tmp_path/'assets/coffee.png.source.json').read_text())
    assert credit['author'] == 'Photographer'
    assert credit['license'] == 'CC BY 4.0'
    assert credit['source_url'] == 'https://commons.wikimedia.org/wiki/File:Coffee.jpg'
    assert result.metadata['files_modified'] == ['assets/coffee.png', 'assets/coffee.png.source.json']


def test_asset_import_rejects_html_and_preserves_existing_files(tmp_path):
    from olympus.agent.actions import AgentAction, ActionType
    (tmp_path/'assets').mkdir()
    (tmp_path/'assets/coffee.png').write_bytes(b'original')
    with patch.object(DeliverySources, '_json', return_value=commons()):
        result = ActionExecutor(str(tmp_path)).execute(AgentAction(ActionType.IMPORT_ASSET,
            'assets/coffee.png', {'title': 'File:Coffee.jpg'}))
    assert not result.success
    assert (tmp_path/'assets/coffee.png').read_bytes() == b'original'
