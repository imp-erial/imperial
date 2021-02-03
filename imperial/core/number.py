from .key import Key, estimate
from .base import PythonValue
from .value import Value, number
from .serializable import Serializable, serialize, unserialize
from ..util import BytesBuffer
from ..exceptions import ImperialSanityError, ImperialSerializationError, ImperialTypeError


class BaseNumber(Value):
	"""
	For types to inhereit when they represent abstract numbers.
	That is, when they're not packable.
	However, note that Number does subclass this.
	"""
	@classmethod
	def _register(cls):
		super()._register()

		# Intuitions
		@cls.register
		class Min(Key):
			"""
			The actual value of this {type} cannot be less than min.
			This is an inclusive lower bound.
			"""

			type = BaseNumber
			keyname = "min"

			@estimate
			def strictly_equal(self, data: BaseNumber) -> int:
				return data.number()

		@cls.register
		class Max(Key):
			"""
			The actual value of this {type} cannot be greater than max.
			This is an inclusive upper bound.
			"""

			type = BaseNumber
			keyname = "max"

			@estimate
			def strictly_equal(self, data: BaseNumber) -> int:
				return data.number()

	@classmethod
	def normalize(cls, value: PythonValue):
		if isinstance(value, int):
			return value
		raise ImperialTypeError(value, expects=int)

	@number
	def number(self, data: PythonValue) -> int:
		return data


class Number(BaseNumber, Serializable):
	"""
	The fundamental numerical atom.
	"""
	@serialize
	def serialize(self, blob: BytesBuffer, *, data, endian, sign):
		# Whole bytes only
		nbits = blob.len_bits()
		if nbits % 8 != 0:
			raise ImperialSerializationError("{type} cannot serialize partial bytes")

		value = data.number()
		nbytes = len(blob)
		signed = sign.get() is Number.Sign.SIGNED

		# Only signed values can be negative
		if not signed and value < 0:
			raise ImperialSanityError("unsigned numbers cannot be negative")

		try:
			b = value.to_bytes(nbytes, endian.string(), signed=signed)
		except OverflowError:
			raise ImperialSanityError(
				"{type} {extra.value} is too big for {extra.bytes}",
				extra={
				"value": value,
				"bytes": self.string("size"),
				},
			) from None

		blob.write(b)

	@unserialize
	def unserialize(self, blob: BytesBuffer, *, endian, sign):
		signed = sign.get() is Number.Sign.SIGNED
		value = int.from_bytes(blob.read(), endian.string(), signed=signed)
		return value

	# @stringify
	# def stringify(self, data):
	# 	# TODO: form
	# 	return str(data.number())

	# @parse
	# def parse(self, string: str):
	# 	# TODO: form
	# 	try:
	# 		return int(string)
	# 	except ValueError:
	# 		raise ImperialParsingError.GenericNotValid(string) from None
