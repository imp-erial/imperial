import unittest

from imperial import util

class TestRawBytesIO(unittest.TestCase):
	def test_create_bytes(self):
		util.RawBytesIO(b"123abc")

	def test_read_bytes(self):
		b = util.RawBytesIO(b"123abc")
		self.assertEqual(b.read(3), b"123")
		self.assertEqual(b.read(3), b"abc")

	def test_readall_bytes(self):
		b = util.RawBytesIO(b"123abc")
		self.assertEqual(b.readall(), b"123abc")

	def test_seek_tell(self):
		b = util.RawBytesIO(b"123abc")
		b.seek(3)
		self.assertEqual(b.read(3), b"abc")

		b.seek(1)
		b.seek(2, util.SEEK_CUR)
		self.assertEqual(b.tell(), 3)

		b.seek(-1, util.SEEK_CUR)
		self.assertEqual(b.read(1), b"3")

		b.seek(-1, util.SEEK_END)
		self.assertEqual(b.read(1), b"c")

	def test_write_bytes(self):
		b = util.RawBytesIO(b"123abc")
		b.write(b"pp")
		b.seek(0)
		self.assertEqual(b.read(), b"pp3abc")

	def test_close(self):
		b = util.RawBytesIO(b"123abc")
		b.close()
		self.assertTrue(b.closed)
		
		with self.assertRaises(ValueError):
			b.read(1)


class TestBytesBuffer(unittest.TestCase):
	def test_create_bytes(self):
		util.BytesBuffer(b"abc123")

	def test_create_window(self):
		b = util.RawBytesIO(b"123abc456")
		return util.BytesBuffer(b, base=3, size=3)

	def test_read_bytes(self):
		bb = util.BytesBuffer(b"abc123")
		self.assertEqual(bb.read(3), b"abc")

	def test_read_from_window(self):
		b = util.RawBytesIO(b"123abc456")
		w = util.BytesBuffer(b, base=3, size=3)
		self.assertEqual(w.read(3), b"abc")

	def test_read_to_end_window(self):
		b = util.RawBytesIO(b"123abc456")
		w = util.BytesBuffer(b, base=3, size=3)
		self.assertEqual(w.read(), b"abc")
		self.assertEqual(w.read(1), b"")

	def test_readall_bytes(self):
		bb = util.BytesBuffer(b"abc123")
		self.assertEqual(bb.readall(), b"abc123")

	def test_readall_window(self):
		b = util.RawBytesIO(b"123abc456")
		w = util.BytesBuffer(b, base=3, size=3)
		self.assertEqual(w.readall(), b"abc")

	def test_seek_tell_window(self):
		b = util.RawBytesIO(b"123abc456")
		w = util.BytesBuffer(b, base=3, size=3)
		self.assertEqual(w.tell(), 0)
		w.seek(0)
		self.assertEqual(w.tell(), 0)
		self.assertEqual(w.read(1), b"a")
		self.assertEqual(w.tell(), 1)

		self.assertEqual(w.seek(-1, util.SEEK_CUR), 0)
		self.assertEqual(w.tell(), 0)

		self.assertEqual(w.seek(0, util.SEEK_END), 3)
		self.assertEqual(w.tell(), 3)

	def test_multiple_windows(self):
		b = util.RawBytesIO(b"123abc456")
		w1 = util.BytesBuffer(b, base=0, size=3)
		w2 = util.BytesBuffer(b, base=3, size=3)

		self.assertEqual(w1.read(1), b"1")
		self.assertEqual(w2.read(1), b"a")
