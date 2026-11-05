import pathlib
import tempfile
import unittest
from unittest.mock import patch
import contexto

RSS=b'''<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:ht="https://trends.google.com/trending/rss">
 <channel><item><title>cr7</title>
 <ht:news_item><ht:news_item_title>Noticia de futebol</ht:news_item_title>
 <ht:news_item_source>Veiculo</ht:news_item_source>
 <ht:news_item_url>https://example.com/futebol</ht:news_item_url></ht:news_item>
 <ht:news_item><ht:news_item_title>Repetida</ht:news_item_title>
 <ht:news_item_url>https://example.com/futebol</ht:news_item_url></ht:news_item>
 <ht:news_item><ht:news_item_title>Insegura</ht:news_item_title>
 <ht:news_item_url>javascript:alert(1)</ht:news_item_url></ht:news_item>
 </item><item><title>&lt;script&gt;ruim&lt;/script&gt;</title></item></channel>
</rss>'''

class TestContexto(unittest.TestCase):
    def test_parseia_noticias(self):
        resultados=contexto.parsear(RSS)
        self.assertEqual(len(resultados),2)
        self.assertEqual(len(resultados[0][1]),1)
        self.assertEqual(resultados[0][1][0][1],"Veiculo")

    def test_descarta_duplicados_e_urls_inseguras(self):
        resultados=contexto.parsear(RSS)
        self.assertEqual(resultados[0][1][0][2],"https://example.com/futebol")

    def test_rejeita_documento_nao_rss(self):
        with self.assertRaises(ValueError):
            contexto.parsear(b"<html/>")

    def test_relatorio_escapa_html(self):
        with tempfile.TemporaryDirectory() as d:
            base=pathlib.Path(d)
            with patch.object(contexto,"BASE",base):
                contexto.salvar(contexto.parsear(RSS))
                text=(base/"contexto_tendencias.html").read_text(encoding="utf-8")
                self.assertIn("&lt;script&gt;",text)
                self.assertNotIn("<script>",text)
                self.assertTrue((base/"contexto_tendencias.csv").exists())

if __name__=="__main__":
    unittest.main()
