import datetime as dt
import sqlite3
import tempfile
import unittest
from pathlib import Path
import xray_br as x

def row(asin,price='20',reviews='10',cat='Casa',date='2026-10-21'):
    return dict(asin=asin,titulo='Produto teste',marca='Marca A',categoria=cat,preco=price,
       moeda='BRL',avaliacoes=reviews,nota='4.5',bsr='',vendedores='',
       vendas_mensais_estimadas='',receita_mensal_estimada='',data_observacao=date,
       url='https://www.amazon.com.br/dp/'+asin,fonte='Fonte sintetica')

class TestXrayBR(unittest.TestCase):
    def test_empty(self):
        data=x.analyse([],dt.date(2026,11,5))
        self.assertEqual(data['observados'],0)
        self.assertEqual(data['categorias'],0)
    def test_medians(self):
        data=x.analyse([row('B0AAA11111'),row('B0AAA22222','40','30')],dt.date(2026,11,5))['analises'][0]
        self.assertEqual(data['preco_mediano'],'30')
        self.assertEqual(data['avaliacoes_medianas'],'20')
        self.assertEqual(data['maior_frac_avaliacoes_amostra_pct'],'75.00')
        self.assertIsNone(data['estimativa_vendas'])
    def test_missing_not_zero(self):
        data=x.analyse([row('B0AAA11111','',''),row('B0AAA22222','20','0')],dt.date(2026,11,5))['analises'][0]
        self.assertEqual(data['precos_disponiveis'],1)
        self.assertEqual(data['avaliacoes_disponiveis'],1)
        self.assertEqual(data['avaliacoes_medianas'],'0')
    def test_staleness(self):
        data=x.analyse([row('B0AAA11111')],dt.date(2026,11,5))
        self.assertEqual(data['observacoes_mais_de_7_dias'],1)
    def test_html_escape(self):
        data=x.analyse([dict(row('B0AAA11111'),titulo='<script>alert(1)</script>')],dt.date(2026,11,5))
        page=x.render(data)
        self.assertIn('&lt;script&gt;',page)
        self.assertNotIn('<script>alert(1)</script>',page)
    def test_read_latest_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/'db.sqlite3'
            columns=('marketplace','asin','titulo','marca','categoria','preco','moeda','avaliacoes','nota','bsr','vendedores','vendas_mensais_estimadas','receita_mensal_estimada','data_observacao','url','fonte')
            with sqlite3.connect(str(db)) as con:
                con.execute('CREATE TABLE blackbox_amazon_br ('+','.join(k+' TEXT' for k in columns)+')')
                for item in (row('B0AAA11111','10','1',date='2026-10-21'),row('B0AAA11111','20','2',date='2026-11-01')):
                    con.execute('INSERT INTO blackbox_amazon_br VALUES ('+','.join('?' for _ in columns)+')',
                        tuple('amazon.com.br' if k=='marketplace' else item.get(k) for k in columns))
            found=x.load(db)
            self.assertEqual(len(found),1)
            self.assertEqual(found[0]['preco'],'20')

if __name__=='__main__':
    unittest.main()
