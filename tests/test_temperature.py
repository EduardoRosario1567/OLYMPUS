import unittest
from olympus.agent.temperature import converter_celsius_fahrenheit

class TestTemperatureConversion(unittest.TestCase):
    def test_conversion(self):
        self.assertEqual(converter_celsius_fahrenheit(0), 32)

if __name__ == "__main__":
    unittest.main()
