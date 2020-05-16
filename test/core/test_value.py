import unittest
from typing import cast

from imperial.core import value
from imperial.core.base import ImperialType, PythonValue
from imperial.exceptions import ImperialKeyError, ImperialTypeError

class Int(value.Value):
	def normalize(self, value: PythonValue) -> PythonValue:
		if isinstance(value, Int):
			return value._data
		if isinstance(value, int):
			return value
		raise ImperialTypeError("value must be an int")

	@value.number
	def number(self, data: PythonValue) -> int:
		return cast(int, data)


class Str(value.Value):
	@classmethod
	def _register(cls):
		@cls.register_converter(target=Int)
		def convert_to_int(data: Str) -> Int:
			return Int(int(data.string()))

		@cls.register_converter(source=Int)
		def convert_from_int(data: Int) -> Str:
			return Str(str(data.number()))

	def normalize(self, value: PythonValue) -> PythonValue:
		if isinstance(value, Str):
			return value._data
		if isinstance(value, str):
			return value
		raise ImperialTypeError("value must be a str")

	@value.string
	def string(self, data: PythonValue) -> str:
		return cast(str, data)


class TestValuePrimitives(unittest.TestCase):
	def test_create_with_primitive(self):
		i = Int(1)
		self.assertIs(i, i.resolve("data"))
		self.assertEqual(1, i.get())
		self.assertEqual(1, i.get("data"))

	def test_set_value_with_primitive(self):
		i = Int()

		with self.assertRaises(ImperialKeyError):
			i.resolve("data")

		i.set(1)
		self.assertIs(i, i.resolve("data"))
		self.assertEqual(1, i.get())
		self.assertEqual(1, i.get("data"))

	def test_get_primitive_as_number(self):
		i = Int(1)
		self.assertEqual(i.number(), 1)
		self.assertEqual(i.number("data"), 1)


class TestValueProxies(unittest.TestCase):
	def test_create_with_redundant_proxy(self):
		i = Int(Int(1))
		self.assertEqual(i.number(), 1)
		self.assertEqual(i.number("data"), 1)

	def test_set_with_redundant_proxy(self):
		i = Int(Int())
		i.set(1)
		self.assertEqual(i.number(), 1)
		self.assertEqual(i.number("data"), 1)
		self.assertIsNot(i, i.resolve("data"))
