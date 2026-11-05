"""Testes deterministas do Radar, sem API externa nem alteracao no banco real."""
import datetime as dt
import pathlib
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import radar

class TestRadar(unittest.TestCase):
    def test_margem_contribuicao(self):
        lucro, pct = radar.margem('129.90','62','12','15','6','5')
        self.assertEqual(lucro, radar.Decimal('23.62'))
        self.assertEqual(pct, radar.Decimal('18.18'))

    def test_margem_negativa(self):
        lucro, pct = radar.margem('50','55','10','15','6','5')
        self.assertLess(lucro,0)
        self.assertLess(pct,0)

    def test_preco_zero_rejeitado(self):
        with self.assertRaises(ValueError):
            radar.margem('0','2','0','10','0','0')

    def test_taxas_excessivas(self):
        with self.assertRaises(ValueError):
            radar.margem('50','2','0','70','30','0')

    def test_valor_invalido(self):
        for invalido in ('NaN','Infinity','-1','abc'):
            with self.subTest(valor=invalido):
                with self.assertRaises(ValueError):
                    radar.decimal(invalido)

    def test_filtra_apenas_brasil(self):
        payload={'products':[
            {'code':'7891234567890','product_name':'Produto BR',
             'brands':'Teste','countries_tags':['en:brazil']},
            {'code':'12345678','product_name':'Produto US',
             'countries_tags':['en:united-states']},
            {'code':'7891234567891','product_name':'Sem pais'},
        ]}
        rows=radar.normalizar(payload)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0][0],'7891234567890')

    def test_deduplicacao(self):
        item={'code':'7891234567890','product_name':'A','countries_tags':['en:brazil']}
        self.assertEqual(len(radar.normalizar({'products':[item,item]})),1)

    def test_resposta_malformada(self):
        for payload in ({}, {'products':{}}, []):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    radar.normalizar(payload)

    def test_codigo_invalido(self):
        rows=radar.normalizar({'products':[
            {'code':'x123','product_name':'Falso','countries_tags':['en:brazil']},
            {'code':'12345678','product_name':'','countries_tags':['en:brazil']}
        ]})
        self.assertEqual(rows,[])

    def test_limite_consulta(self):
        with self.assertRaises(ValueError):
            radar.coletar(None,51)
        with self.assertRaises(ValueError):
            radar.coletar(None,0)

    def test_banco_e_relatorio_isolados(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho=pathlib.Path(tmp)
            with patch.object(radar,'BASE',caminho),patch.object(radar,'DB',caminho/'radar.sqlite3'):
                with radar.banco() as con:
                    con.execute('INSERT INTO produtos VALUES (?,?,?,?,?)',
                       ('7891234567890','Produto Teste','Marca','https://example.org/item','2026-11-05'))
                    radar.relatorio(con)
                    self.assertEqual(con.execute('SELECT count(*) FROM produtos').fetchone()[0],1)
                html=(caminho/'relatorio.html').read_text(encoding='utf-8')
                self.assertIn('Produto Teste',html)
                self.assertIn('SEM COTACAO',html)

    def test_escapa_html_no_relatorio(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho=pathlib.Path(tmp)
            with patch.object(radar,'BASE',caminho),patch.object(radar,'DB',caminho/'radar.sqlite3'):
                with radar.banco() as con:
                    con.execute('INSERT INTO produtos VALUES (?,?,?,?,?)',
                        ('7891234567890','<script>alert(1)</script>','Marca',
                         'https://example.org/item','2026-11-05'))
                    radar.relatorio(con)
                html=(caminho/'relatorio.html').read_text(encoding='utf-8')
                self.assertNotIn('<script>',html)
                self.assertIn('&lt;script&gt;',html)

if __name__=='__main__':
    unittest.main(verbosity=2)
