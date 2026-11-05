import datetime as dt
import unittest
import commerce_integrado as c

def row(asin,price='12.50',date='2026-10-21',title='Produto teste'):
    return dict(asin=asin,titulo=title,categoria='Casa',marca='Teste',
      preco=price,moeda='BRL',avaliacoes='10',nota='4.5',data_observacao=date,
      url='https://www.amazon.com.br/dp/'+asin,fonte='Fonte teste',
      vendas_mensais_estimadas='',metodo_estimativa='')

class TestCommerceIntegrado(unittest.TestCase):
    def test_empty(self):
        result=c.payload([],dt.date(2026,11,5))
        self.assertEqual(result['total'],0)
        self.assertEqual(result['categories'],[])
        self.assertIn('Sem dados',c.page(result))
    def test_historical(self):
        result=c.payload([row('B0ABC12345')],dt.date(2026,11,5))
        self.assertEqual(result['historical'],1)
        self.assertTrue(result['products'][0]['stale'])
        self.assertEqual(result['products'][0]['price'],12.5)
    def test_missing_price_not_zero(self):
        result=c.payload([row('B0ABC12345','')],dt.date(2026,11,5))
        self.assertIsNone(result['products'][0]['price'])
    def test_html_escaping(self):
        result=c.payload([row('B0ABC12345',title='</script><script>alert(1)</script>')],dt.date(2026,11,5))
        output=c.page(result)
        self.assertNotIn('</script><script>alert(1)</script>',output)
        self.assertIn('\\u003c/script',output)
    def test_future_date(self):
        label,stale=c.age_label('2026-12-01',dt.date(2026,11,5))
        self.assertTrue(stale)
        self.assertIn('futura',label)
    def test_zero_review_distinct_from_missing(self):
        item=row('B0ABC12345');item['avaliacoes']='0'
        result=c.payload([item],dt.date(2026,11,5))
        self.assertEqual(result['products'][0]['reviews'],0)

if __name__=='__main__':
    unittest.main()
