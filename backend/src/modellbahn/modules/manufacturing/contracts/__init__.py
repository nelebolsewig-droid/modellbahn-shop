"""Public contract of the manufacturing module: the only part other modules may import.

* :mod:`.events` - the manufacturing events other modules react to (the stock will book
  the good parts of a finished plate). Framework-free, so any layer may use it.

This package itself imports nothing, so importing it loads no submodule.
"""
