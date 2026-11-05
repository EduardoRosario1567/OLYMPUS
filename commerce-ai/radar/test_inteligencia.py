"""Testes isolados do motor de evidencias, sem rede e sem alterar bancos reais."""
import datetime as dt
import pathlib
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import inteligencia
import radar
import tendencias

class TestInteligencia(unittest.TestCase):
    def test_relacao_sem_palavra_generica(self):
        self.assertTrue(inteligencia.relacionar('Fone Bluetooth Teste','fone bluetooth'))
        self.assertFalse(inteligencia.relacionar('Coca Cola LT','cr7'))
        self.assertFalse(inteligencia.relacionar('Mesa de madeira','mesa'))
    def test_sem_cotacao_nao_inventa_margem(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d)
            with patch.object(radar,'DB',root/'dados.sqlite3'),patch.object(tendencias,'DB',root/'dados.sqlite3'),patch.object(inteligencia,'BASE',root):
                with radar.banco() as con:
                    con.execute("INSERT INTO produtos VALUES (?,?,?,?,?)",(
                        '7891234567890','Fone Bluetooth Teste','Teste','https://example.org/item','2026-11-05'))
                    con.commit()
                with tendencias.conectar() as con:
                    tendencias.gravar(con,[{
                        'termo':'fone bluetooth','volume_aproximado':'500+',
                        'publicado_em':'2026-11-05','url':'https://trends.google.com/',
                        'fonte':'https://trends.google.com/trending/rss?geo=BR'}])
                    dossies=inteligencia.analisar(con,dt.date(2026,11,5))
                self.assertEqual(len(dossies),1)
                self.assertEqual(len(dossies[0]['correlacoes_tendencias']),1)
                self.assertIsNone(dossies[0]['margem_contribuicao_estimada_pct'])
                self.assertEqual(dossies[0]['decisao'],'DADOS INSUFICIENTES')
                self.assertEqual(dossies[0]['volume_vendas'],'NAO DETERMINADO')
    def test_relatorio_e_entrada_ia(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d)
            with patch.object(inteligencia,'BASE',root):
                inteligencia.salvar([{
                    'produto':'<script>Teste</script>','correlacoes_tendencias':[],
                    'margem_contribuicao_estimada_pct':None,
                    'decisao':'DADOS INSUFICIENTES','alertas':['SEM COTACAO']
                }])
                html=(root/'inteligencia_comercial.html').read_text(encoding='utf-8')
                self.assertIn('&lt;script&gt;',html)
                self.assertNotIn('<script>',html)
                import json
                payload=json.loads((root/'entrada_olympus.json').read_text(encoding='utf-8'))
                self.assertFalse(payload['modelo_executado'])
    def test_sem_tendencias(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d)
            with patch.object(radar,'DB',root/'a.sqlite3'),patch.object(inteligencia,'BASE',root):
                with radar.banco() as con:
                    con.execute("INSERT INTO produtos VALUES (?,?,?,?,?)",(
                        '7891234567890','Fone Bluetooth','Teste','https://example.org/item','2026-11-05'))
                    con.commit()
                    dossies=inteligencia.analisar(con,dt.date(2026,11,5))
                self.assertEqual(dossies[0]['decisao'],'DADOS INSUFICIENTES')
                self.assertFalse(dossies[0]['correlacoes_tendencias'])

if __name__=='__main__':
    unittest.main(verbosity=2)
