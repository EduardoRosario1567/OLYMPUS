#!/usr/bin/env python3
"""Testes offline do adaptador Amazon BR; todos os itens são dados sintéticos."""
import csv,json,tempfile,unittest
from pathlib import Path
import amazon_catalogo_br as m
BR=m.BR
def example():
    return {'items':[{'asin':'B0ABC12345',
        'summaries':[{'marketplaceId':BR,'itemName':'Produto ficticio','brand':'Teste'}],
        'productTypes':[{'marketplaceId':BR,'productType':'KITCHEN'}],
        'salesRanks':[{'marketplaceId':BR,'classificationRanks':[{'rank':500}]}]}]}
class TestAmazonCatalogo(unittest.TestCase):
    def test_brasil(self):
        r=m.normalize(example(),'2026-11-05','API autorizada')[0]
        self.assertEqual(r['bsr'],'500')
        self.assertEqual(r['url'],'https://www.amazon.com.br/dp/B0ABC12345')
        self.assertEqual(r['categoria'],'KITCHEN')
    def test_ausentes(self):
        r=m.normalize(example(),'2026-11-05','API')[0]
        for k in ('preco','avaliacoes','vendas_mensais_estimadas','receita_mensal_estimada'):
            self.assertEqual(r[k],'')
    def test_outro_mercado(self):
        p=example();p['items'][0]['summaries'][0]['marketplaceId']='ATVPDKIKX0DER'
        self.assertEqual(m.normalize(p,'2026-11-05','API'),[])
    def test_duplicado(self):
        p=example();p['items'].append(p['items'][0])
        self.assertEqual(len(m.normalize(p,'2026-11-05','API')),1)
    def test_payload_invalido(self):
        with self.assertRaises(ValueError):m.normalize({},'2026-11-05','API')
    def test_exportacao_csv(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'input.json';out=Path(d)/'out.csv'
            src.write_text(json.dumps(example()))
            m.main(['--entrada',str(src),'--saida',str(out),'--data','2026-11-05'])
            with out.open() as f:rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['asin'],'B0ABC12345')
            self.assertEqual(tuple(rows[0].keys()),m.FIELDS)
if __name__=='__main__':unittest.main()
