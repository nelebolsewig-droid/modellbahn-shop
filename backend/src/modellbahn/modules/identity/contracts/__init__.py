"""Public contract of the identity module: the only part other modules may import.

* :mod:`.events` - the identity events other modules react to (e.g. sales adopts
  guest orders on ``EmailVerified`` and removes addresses on ``AccountDeleted``)
  and the types they carry. Framework-free, so any layer may use it.
* :mod:`.accounts` - a read-only facade for account data. It queries the database
  and therefore belongs in another module's application or infrastructure layer.

This package itself imports neither, so importing one does not load the other.
"""
