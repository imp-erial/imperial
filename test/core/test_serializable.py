import unittest

from imperial import exceptions
from imperial.core import key, serializable
from imperial.util import BytesBuffer, RawBytesIO
from imperial.magic import BASIC


class PosInt(serializable.Serializable):
	has_basic = True

	@classmethod
	def _register(cls):
		@cls.register
		class SizeKey(key.Key):
			type = Size
			default = 4
			keyname = "size"

	@classmethod
	def normalize(cls, value):
		if isinstance(value, PosInt):
			return value._data

		i = int(value)
		if i < 0:
			raise exceptions.ImperialTypeError(value, expects=cls)
		return i

	number = serializable.Serializable.get

	def get_basic(self):
		return self._data

	def set_basic(self, value):
		self._data = self.normalize(value)

	@serializable.serialize
	def serialize(self, blob: BytesBuffer):
		blob.write(self._data.to_bytes(self.get("size"), "little"))

	@serializable.unserialize
	def unserialize(self, blob: BytesBuffer) -> int:
		return int.from_bytes(blob.read(self.get("size")), "little")


class Size(PosInt):
	has_basic = True

	@classmethod
	def _register(cls):
		@cls.register
		class Bits(key.Key):
			type = PosInt
			keyname = "bits"

			@key.calculate(BASIC)
			def from_basic(self, basic):
				return basic.get() * 8


class Pair(serializable.Serializable):
	@classmethod
	def _register(cls):
		@cls.register
		class Left(key.Key):
			type = PosInt
			keyname = "left"

		@cls.register
		class Right(key.Key):
			type = PosInt
			keyname = "right"

	@serializable.serialize
	def serialize(self, blob: BytesBuffer):
		blob.write(self.number("left").to_bytes(2, "little"))
		blob.write(self.number("right").to_bytes(2, "little"))

	@serializable.unserialize_yield
	def unserialize(self, blob: BytesBuffer) -> int:
		left = int.from_bytes(blob.read(2), "little")
		yield "left", {"": left, "size": 2}

		right = int.from_bytes(blob.read(2), "little")
		yield "right", {"": right, "size": 2}


class TestSerializable(unittest.TestCase):
	def test_serialize_bytes(self):
		one = PosInt(1)
		self.assertEqual(one.serialize(), b"\x01\x00\x00\x00")

	def test_serialize_stream(self):
		b = RawBytesIO(b"\x01\x02\x03\x04\x05\x06\x07\x08")
		bb = BytesBuffer(b, base=1, size=4)
		ten = PosInt(10)
		self.assertIsNone(ten.serialize(bb))
		b.seek(0)
		self.assertEqual(b.readall(), b"\x01\x0a\x00\x00\x00\x06\x07\x08")

	def test_unserialize_bytes(self):
		one = PosInt()
		one.unserialize(b"\x01\x00\x00\x00")
		self.assertEqual(one.get(), 1)

	def test_unserialize_stream(self):
		bb = BytesBuffer(b"\x01\x02\x03\x04\x05\x06\x07\x08", base=1, size=4)
		num = PosInt()
		num.unserialize(bb)
		self.assertEqual(num.get(), 0x05040302)

	def test_unserialize_yield_bytes(self):
		pair = Pair()
		pair.unserialize(b"\x01\x00\x02\x00", {"left"})
		self.assertEqual(pair.get("left"), 1)
		self.assertFalse("right" in dict(pair.keys))

		pair.unserialize()
		self.assertEqual(pair.get("right"), 2)


if __name__ == "__main__":
	unittest.main()
