from io import BufferedIOBase, RawIOBase, SEEK_SET, SEEK_CUR, SEEK_END
from typing import Any, Callable, Optional, Union

try:
	# only in 3.8
	from typing import Literal
	SeekWhence = Literal[SEEK_SET, SEEK_CUR, SEEK_END]
except ImportError:
	SeekWhence = int

class DotMap(dict):
	def __getattr__(self, name: str) -> Any:
		return self[name]


class RawBytesIO(RawIOBase):
	"""
	A BytesIO-like object based on RawIOBase.
	"""
	blob: bytearray
	_cursor: int
	_length: int
	closed: bool

	def __init__(self, blob: bytes):
		self.blob = bytearray(blob)
		self._length = len(blob)
		self._cursor = 0

	def _raise_if_closed(self):
		if self.closed:
			raise ValueError("I/O operation on closed file.")

	def readable(self) -> bool:
		return True

	def writable(self) -> bool:
		return True

	def seekable(self) -> bool:
		return True

	def isatty(self) -> bool:
		return False

	def read(self, size: int = -1) -> bytes:
		self._raise_if_closed()
		if size == -1:
			return self.readall()
		start = self._cursor
		end = self._cursor = start + size
		return bytes(self.blob[start:end])

	def readall(self) -> bytes:
		self._raise_if_closed()
		start = self._cursor
		self._cursor = self._length
		return bytes(self.blob[start:])

	def readinto(self, b) -> int:
		self._raise_if_closed()
		start = self._cursor
		to_write = min(len(b), self._length - start)
		b[:] = self.blob[start:start+to_write]
		self._cursor += to_write
		return to_write

	def write(self, b):
		self._raise_if_closed()
		start = self._cursor
		to_write = min(len(b), self._length - start)
		self.blob[start:start+to_write] = b[:to_write]
		self._cursor += to_write
		return to_write

	def truncate(self, size: Optional[int] = None) -> int:
		if size is None:
			size = self._cursor

		if size > self._length:
			self.blob.extend(b'\0' * (size - self._length))
		elif size < self._length:
			self.blob[size:] = b''
		return size

	def seek(self, offset: int, whence: SeekWhence = SEEK_SET) -> int:
		if whence == SEEK_SET:
			self._cursor = offset
		elif whence == SEEK_CUR:
			self._cursor += offset
		elif whence == SEEK_END:
			self._cursor = self._length + offset
		else:
			raise ValueError("whence")
		if self._cursor > self._length:
			self._cursor = self._length
		return self._cursor

	def tell(self) -> int:
		return self._cursor

	def close(self):
		super().close()
		try:
			del self.blob
		except AttributeError:
			pass

class BytesBuffer(BufferedIOBase):
	"""
	Access bytes from some location in a safe and sane manner.
	"""
	raw: RawIOBase
	_base: int
	_end: int
	_cursor: int
	_unbounded: bool

	# Proxied methods
	flush: Callable[[], None]
	readable: Callable[[], bool]
	writable: Callable[[], bool]
	seekable: Callable[[], bool]
	isatty: Callable[[], bool]
	truncate: Callable[[Optional[int]], int]

	def __init__(
		self,
		blob: Union[bytes, RawIOBase] = b'',
		*,
		base: int = 0,
		size: int = -1,
		bits: int = -1
	):
		if base < 0:
			raise ValueError("base")

		self._base = base
		self._cursor = 0

		if size >= 0:
			if bits >= 0:
				bits += size * 8
			else:
				bits = size * 8
		
		if bits < 0:
			self._unbounded = True
			if isinstance(blob, bytes):
				self.raw = RawBytesIO(blob)
				self._end = len(blob)
			else:
				self.raw = blob
				cur = blob.tell()
				blob.seek(0, SEEK_END)
				self._end = blob.tell()
				blob.seek(cur)
		else:
			# TODO: support any granularity
			if bits % 8:
				raise ValueError(
					f"{self.__class__.__name__} currently only supports byte-bounded streams")
			
			size = bits // 8

			if isinstance(blob, bytes):
				self.raw = RawBytesIO(blob + b"\0" * (size - (len(blob) - base)))
				self._end = base + size
			else:
				self.raw = blob
				self._end = base + size

		self.flush = self.raw.flush
		self.readable = self.raw.readable
		self.writable = self.raw.writable
		self.seekable = self.raw.seekable
		self.isatty = self.raw.isatty
		self.truncate = self.raw.truncate

	def read(self, size=-1) -> bytes:
		if size == -1:
			return self.readall()
		start = self._base + self._cursor
		self.raw.seek(start)
		if start + size > self._end:
			size = self._end - start
		ret = self.raw.read(size)
		self._cursor = self.raw.tell() - self._base
		return ret

	def readall(self) -> bytes:
		start = self._base + self._cursor
		self.raw.seek(start)
		ret = self.raw.read(self._end - start)
		self._cursor = self._end
		return ret

	def readinto(self, b) -> int:
		start = self._base + self._cursor
		self.raw.seek(start)
		if self._end - start > len(b):
			ret = self._end - start
			if ret:
				b[:ret] = self.raw.read(ret)
		else:
			ret = self.raw.readinto(b)
			self._cursor += ret
		return ret

	def write(self, b: bytes) -> int:
		start = self._base + self._cursor
		self.raw.seek(start)
		if start + len(b) > self._end:
			b = b[:self._end - start]
		ret: int = self.raw.write(b)
		self._cursor += ret
		return ret

	def seek(self, offset: int, whence: SeekWhence = SEEK_SET):
		if whence == SEEK_SET:
			self._cursor = offset
		elif whence == SEEK_CUR:
			self._cursor += offset
		elif whence == SEEK_END:
			self._cursor = self._end - self._base + offset
		else:
			raise ValueError("whence")
		if self._base + self._cursor > self._end:
			self._cursor = self._end - self._base
		return self._cursor

	def tell(self) -> int:
		return self._cursor
