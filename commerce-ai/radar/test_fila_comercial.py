"""Testes offline para fila de investigacao comercial."""
import pathlib
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import fila_comercial

class TestFilaComercial(unittest.TestCase):
    def test_produto_sem_noticia(self):
        self.assertEqual(fila_comercial.classificar("fone bluetooth",[])[0],"INVESTIGAR PRODUTO")
    def test_produto_com_noticia(self):
        self.assertEqual(fila_comercial.classificar("luminaria solar",[{"titulo":"noticia"}])[0],"ANALISAR CONTEXTO")
    def test_politica_e_futebol(self):
        for termo in ("cr7","edital ibge","feminicidio"):
            self.assertEqual(fila_comercial.classificar(termo,[])[0],"ASSUNTO GERAL")
    def test_vazio_nao_cria_oportunidades(self):
        with tempfile.TemporaryDirectory() as d:
            base=pathlib.Path(d)
            with patch.object(fila_comercial,"BASE",base):
                con=sqlite3.connect(":memory:")
                self.assertEqual(fila_comercial.carregar(con),[])
                fila_comercial.salvar([])
                self.assertTrue((base/"fila_comercial.html").exists())
    def test_historico_sem_preco(self):
        with tempfile.TemporaryDirectory() as d:
            base=pathlib.Path(d)
            with patch.object(fila_comercial,"BASE",base):
                con=sqlite3.connect(":memory:")
                con.execute("CREATE TABLE tendencias (termo TEXT,volume_aproximado TEXT,publicado_em TEXT,url TEXT,fonte TEXT,coletado_em TEXT)")
                con.execute("INSERT INTO tendencias VALUES ('fone bluetooth','100+','2026-11-05','','Google','2026-11-05')")
                dados=fila_comercial.carregar(con)
                self.assertEqual(len(dados),1)
                self.assertEqual(dados[0]["lucro"],"NAO DETERMINADO")
                self.assertEqual(dados[0]["volume_vendas"],"NAO DETERMINADO")
if __name__=="__main__":
    unittest.main(verbosity=2)
