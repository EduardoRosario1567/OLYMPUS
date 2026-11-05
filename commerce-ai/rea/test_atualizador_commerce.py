"""Testes offline da rotina local de atualizacao do OLYMPUS."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import atualizador_commerce as a

class TestAtualizador(unittest.TestCase):
    def test_sem_banco(self):
        with mock.patch.object(a,"DB",Path("/tmp/olympus-database-inexistente-12345.sqlite3")):
            self.assertEqual(a.dates()["produtos_no_banco"],0)
    def test_contagem_e_data(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/"db.sqlite3"
            with sqlite3.connect(str(db)) as con:
                con.execute("CREATE TABLE blackbox_amazon_br (marketplace TEXT,asin TEXT,data_observacao TEXT)")
                con.executemany("INSERT INTO blackbox_amazon_br VALUES (?,?,?)",[
                    ("amazon.com.br","B0AAA11111","2026-10-21"),
                    ("amazon.com.br","B0AAA11111","2026-10-22"),
                    ("amazon.com.br","B0AAA22222","2026-11-03"),
                    ("amazon.com","B0AAA33333","2026-11-04"),
                ])
            with mock.patch.object(a,"DB",db):
                result=a.dates()
            self.assertEqual(result["produtos_no_banco"],2)
            self.assertEqual(result["data_mais_recente_observacao"],"2026-11-03")
    def test_status_atomico(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"status.json"
            with mock.patch.object(a,"STATUS",p):
                a.write_status({"status":"OK","novos_dados_nesta_execucao":False})
            self.assertTrue(p.exists())
            self.assertFalse(p.with_suffix(".json.tmp").exists())
            self.assertEqual(json.loads(p.read_text())["status"],"OK")
    def test_intervalo(self):
        self.assertEqual(a.INTERVAL,21600)

if __name__=="__main__":
    unittest.main()
