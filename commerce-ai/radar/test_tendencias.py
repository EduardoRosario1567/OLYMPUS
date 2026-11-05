"""Testes offline para o coletor de tendencias; nao afetam bancos do usuario."""
import pathlib, tempfile, unittest
from unittest.mock import patch
import tendencias

RSS = b'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:ht="https://trends.google.com/trending/rss">
<channel>
 <item><title>organizador de mesa</title>
 <ht:approx_traffic>10K+</ht:approx_traffic>
 <pubDate>Thu, 05 Nov 2026 11:00:00 GMT</pubDate>
 <link>https://trends.google.com/trending?geo=BR</link></item>
 <item><title>organizador de mesa</title></item>
 <item><title>&lt;script&gt;alert(1)&lt;/script&gt;</title>
 <link>javascript:alert(1)</link></item>
</channel></rss>'''

class TestTendencias(unittest.TestCase):
    def test_rss_realista_e_volume(self):
        dados=tendencias.parse_rss(RSS)
        self.assertEqual(len(dados),2)
        self.assertEqual(dados[0]['volume_aproximado'],'10K+')
        self.assertIn('2026-11-05',dados[0]['publicado_em'])

    def test_deduplicacao(self):
        self.assertEqual(sum(x['termo']=='organizador de mesa'
                             for x in tendencias.parse_rss(RSS)),1)

    def test_link_nao_http(self):
        dados=tendencias.parse_rss(RSS)
        self.assertTrue(dados[1]['url'].startswith('https://'))

    def test_sem_rss(self):
        with self.assertRaises(ValueError):
            tendencias.parse_rss(b'<html/>')

    def test_xml_invalido(self):
        with self.assertRaises(tendencias.ET.ParseError):
            tendencias.parse_rss(b'<rss>')

    def test_limites_sem_rede(self):
        for limite in (0,51):
            with self.subTest(limite=limite):
                with self.assertRaises(ValueError):
                    tendencias.coletar(limite)

    def test_sqlite_e_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            raiz=pathlib.Path(temp)
            with patch.object(tendencias,'BASE',raiz),patch.object(tendencias,'DB',raiz/'t.sqlite3'):
                with tendencias.conectar() as con:
                    tendencias.gravar(con,tendencias.parse_rss(RSS))
                    tendencias.gravar(con,tendencias.parse_rss(RSS))
                    self.assertEqual(con.execute('SELECT count(*) FROM tendencias').fetchone()[0],2)
                    path,quantidade=tendencias.gerar_relatorio(con)
                self.assertEqual(quantidade,2)
                pagina=path.read_text(encoding='utf-8')
                self.assertNotIn('<script>',pagina)
                self.assertIn('&lt;script&gt;',pagina)
                self.assertTrue((raiz/'tendencias.csv').exists())

if __name__ == '__main__':
    unittest.main(verbosity=2)
