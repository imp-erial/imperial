import unittest

from imperial import exceptions
from imperial.core import base, dynamic, key

class Int(base.ImperialType):
	@classmethod
	def normalize(cls, value):
		return int(value)

	def get_basic(self):
		return self._data
	
	def set_basic(self, value):
		self._data = self.normalize(value)

class Adder(dynamic.Dynamic):
	@classmethod
	def _register(cls):
		@cls.register
		class A(key.Key):
			type = Int
			keyname = "a"

			@key.calculate
			def from_b(self, b, data):
				return data.get() - b.get()

		@cls.register
		class B(key.Key):
			type = Int
			keyname = "b"

			@key.calculate
			def from_a(self, a, data):
				return data.get() - a.get()

		@cls.register
		class Data(key.Key):
			type = Int
			keyname = "data"

			@key.calculate
			def from_b(self, a, b):
				return a.get() + b.get()
	
	def get_basic(self):
		return self.get("data")


class TestAdder(unittest.TestCase):
	def test_get_unset_basic(self):
		t = Adder()
		t.set("a", 1)
		t.set("b", 8)

		self.assertEqual(t.get("a"), 1)
		self.assertEqual(t.get("b"), 8)
		self.assertEqual(t.get(), 9)

	def test_get_unset_basic_no_b(self):
		t = Adder()
		t.set("a", 1)

		with self.assertRaises(exceptions.ImperialKeyError):
			t.get()
