import unittest

from imperial.core import number
from imperial.exceptions import ImperialValueError

class TestNumber(unittest.TestCase):
	def test_create_primitive(self):
		n = number.Number(100)
		self.assertIsNotNone(n)

	def test_get_basic(self):
		n = number.Number(100)
		self.assertEqual(n.get(), 100)
		self.assertEqual(n.number(), 100)
		
		with self.assertRaises(ImperialValueError):
			n.string()
		
		with self.assertRaises(ImperialValueError):
			n.list()
