import csv
import json
import pathlib
import tempfile
import unittest
from unittest import mock
import coletor_amazon_spapi as a

BR=a.BR
def item(asin='B0ABC12345'):
    return {'asin':asin,'summaries':[{'marketplaceId':BR,'itemName':'Produto de teste','brand':'Marca de teste'}],
            'productTypes':[{'marketplaceId':BR,'productType':'HOME'}]}
def config():
    return {'client_id':'teste_id','client_secret':'teste_secret',
            'refresh_token':'teste_refresh','keywords':['lampada led'],
            'pages_per_keyword':2}
class TestColetorAmazon(unittest.TestCase):
    def test_without_config_is_not_connected(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNone(a.read_config(pathlib.Path(folder)/'inexistente.json'))
    def test_private_permissions_required(self):
        with tempfile.TemporaryDirectory() as folder:
            path=pathlib.Path(folder)/'credentials.json'
            path.write_text(json.dumps(config()))
            path.chmod(0o644)
            with self.assertRaisesRegex(ValueError,'0600'):a.read_config(path)
            path.chmod(0o600)
            self.assertEqual(a.read_config(path)['keywords'],['lampada led'])
    def test_keywords_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            path=pathlib.Path(folder)/'credentials.json'
            c=config();c['keywords']=['t']*6
            path.write_text(json.dumps(c));path.chmod(0o600)
            with self.assertRaises(ValueError):a.read_config(path)
    def test_query_parameters_and_token_header(self):
        with mock.patch.object(a,'request_json',return_value={'items':[]}) as request:
            a.search('luminaria solar','token_teste')
        url=request.call_args.args[0]
        self.assertIn('marketplaceIds='+BR,url)
        self.assertIn('keywords=luminaria+solar',url)
        self.assertIn('summaries',url)
        self.assertEqual(request.call_args.args[1]['x-amz-access-token'],'token_teste')
    def test_collect_pages_and_deduplicate(self):
        responses=[
            {'items':[item('B0ABC12345')],'pagination':{'nextToken':'TOKEN2'}},
            {'items':[item('B0ABC12345'),item('B0DEF67890')]}
        ]
        with mock.patch.object(a,'token',return_value='token_de_teste'):
            out,events=a.collect(config(),fetch=lambda *args:responses.pop(0),sleeper=lambda _:None)
        self.assertEqual(len(out),2)
        self.assertEqual(len(events),2)
        self.assertEqual(out[0]['preco'],'')
        self.assertEqual(out[0]['vendas_mensais_estimadas'],'')
    def test_empty_no_file(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNone(a.write_inbox([],pathlib.Path(folder)))
            self.assertEqual(list(pathlib.Path(folder).iterdir()),[])
    def test_csv_from_mocked_api(self):
        with tempfile.TemporaryDirectory() as folder:
            result=a.write_inbox(a.normalize({'items':[item()]},'2026-11-05','fonte teste'),pathlib.Path(folder))
            with result.open(encoding='utf8') as f:
                rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['asin'],'B0ABC12345')
            self.assertEqual(rows[0]['vendas_mensais_estimadas'],'')
if __name__=='__main__':unittest.main()
