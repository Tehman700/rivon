"""Imports every module's models so `Base.metadata` describes the whole schema.

Alembic and the schema tests import this. Add each new module's models here.
"""

import rivon.business.models  # noqa: F401
import rivon.channels.models  # noqa: F401
import rivon.events.models  # noqa: F401
import rivon.platform.models  # noqa: F401
from rivon.db import Base

metadata = Base.metadata
