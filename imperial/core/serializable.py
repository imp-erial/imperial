from typing import Any, Iterator, Optional, Set, Tuple, Union

from .packable import Packable
from ..util import BytesBuffer
from ..magic import make_refs_resolver

def serialize(fun):
	resolver = make_refs_resolver(fun)
	def handler(self: "Serializable", *args: BytesBuffer) -> Optional[bytes]:
		"""
		Serialize this struct into a bytes sequence.
		"""
		if len(args) == 1:
			resolver(self).run(args[0])
			return
		elif not args:
			blob = BytesBuffer(bits=self.number(("size", "bits")))
			resolver(self).run(blob)
			blob.seek(0)
			return blob.readall()
		raise TypeError(f"serialize() takes from 0 to 1 positional arguments but {len(args)} were given")
	resolver.add_to(handler)
	handler._pack = ("Serializable", 0)
	return handler

def unserialize(fun):
	resolver = make_refs_resolver(fun)
	def handler(self: "Serializable", blob: Union[bytes, BytesBuffer] = b"", until: Set[str] = {""}):
		"""
		Unserialize this struct from a bytes sequence.
		"""
		if not blob:
			return

		if isinstance(blob, bytes):
			blob = BytesBuffer(blob)
		value = resolver(self).run(blob)
		self.set(value)
		return self
	resolver.add_to(handler)
	handler._pack = ("Serializable", 1)
	return handler

def unserialize_yield(fun):
	last_blob: BytesBuffer
	last_position: int
	last_generator: Iterator[Tuple[str, Any]]

	resolver = make_refs_resolver(fun)
	def handler(self: "Serializable", blob: Union[bytes, BytesBuffer] = b"", until: Set[str] = {""}):
		"""
		Unserialize this struct from a bytes sequence.
		Stop unserializing when all keys in "until" are satisfied.
		By default, pulls all keys it can.
		"""
		nonlocal last_blob, last_position, last_generator
		if not blob:
			# TODO: missing blob on first call handling
			blob = last_blob
			blob.seek(last_position)
		elif isinstance(blob, bytes):
			last_blob = blob = BytesBuffer(blob)
			last_generator = resolver(self).run(blob)

		# Clear what's already been defined
		until = {key for key in until if not self.keys.contains_quick(key)}
		if until:
			for key, value in last_generator:
				if key:
					self.set(key, value)
				else:
					self.set(value)
				until.discard(key)

				if not until:
					break

		last_position = blob.tell()
		return self
	resolver.add_to(handler)
	handler._pack = ("Serializable", 1)
	return handler

class Serializable(Packable):
	@serialize
	def serialize(self, blob: BytesBuffer):
		raise NotImplementedError(f"{self.__class__.__name__} must implement serialize")

	@unserialize
	def unserialize(self, blob: BytesBuffer):
		raise NotImplementedError(f"{self.__class__.__name__} must implement unserialize")
