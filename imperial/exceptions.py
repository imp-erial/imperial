# TODO: be able to interpret container, key name, line/col, etc as appropriate

class ImperialError(Exception):
	pass

class ImperialSanityError(ImperialError):
	"""
	Raised when there are conflicts in the description.
	"""
	pass

class ImperialLibraryError(ImperialError):
	"""
	Raised by an error caused by a problem in a
	library's use of the Imperial core.
	"""
	pass

class ImperialKeyError(ImperialError):
	"""
	Raised when a non-existent key was requested.
	"""
	pass
