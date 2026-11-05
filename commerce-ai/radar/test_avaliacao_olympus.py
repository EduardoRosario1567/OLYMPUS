"""Testa a preparacao de dossies sem invocar Ollama ou Anthropic."""
import unittest
import avaliacao_olympus

class TestAvaliacaoOlympus(unittest.TestCase):
    def test_dossie_vazio(self):
        self.assertEqual(avaliacao_olympus.preparar([]),[])
    def test_nao_inventa_vendas(self):
        itens=avaliacao_olympus.preparar([{
            'codigo':'123','produto':'Produto A','correlacoes_tendencias':[],
            'decisao':'DADOS INSUFICIENTES'}])
        self.assertEqual(itens[0]['volume_vendas'],'NAO DETERMINADO')
        self.assertEqual(itens[0]['decisao_preliminar'],'DADOS INSUFICIENTES')
    def test_limite_para_prompt(self):
        dados=[{'produto':str(i)} for i in range(30)]
        self.assertEqual(len(avaliacao_olympus.preparar(dados)),10)
    def test_entrada_invalida(self):
        with self.assertRaises(ValueError):
            avaliacao_olympus.preparar({})
    def test_limina_noticias(self):
        itens=avaliacao_olympus.preparar([{
            'produto':'A','correlacoes_tendencias':[{'termo':str(i)} for i in range(20)]
        }])
        self.assertEqual(len(itens[0]['evidencias']),5)

if __name__=='__main__':
    unittest.main(verbosity=2)
