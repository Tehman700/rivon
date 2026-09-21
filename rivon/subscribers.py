"""Imports every module that registers event subscribers.

The worker and the relay import this so both processes know the same
subscribers. Add each module's subscribers here as modules are built.
"""

import rivon.channels.echo  # noqa: F401
