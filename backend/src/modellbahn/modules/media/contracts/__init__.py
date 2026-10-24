"""Public contract of the media module: the only part other modules may import.

* :mod:`.events` - the media events other modules react to and the types they carry.
  Framework-free, so any layer may use it.
* :mod:`.images` - a read-only facade for images (state, facts, rendered sizes with
  their URLs) and the foreign key target for galleries. It queries the database and
  therefore belongs in another module's application or infrastructure layer.

This package itself imports neither, so importing one does not load the other.
"""
