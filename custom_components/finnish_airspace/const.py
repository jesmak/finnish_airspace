"""Constants for Finnish Airspace."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "finnish_airspace"
TITLE: Final = "Finnish Airspace"

ATTRIBUTION: Final = "Fintraffic ANS, ais.fi"

USER_AGENT: Final = "FinnishAirspace/1.0.0 (https://github.com/jesmak/finnish_airspace; Home Assistant integration)"

# The content of the IFR bulletin for the whole Helsinki FIR, in ISO-8859-1 by its own markup.
BULLETIN_URL: Final = "https://www.ais.fi/bulletins/efinen.htm"
# In UTF-8 by its own markup.
ENR_5_1_URL: Final = "https://www.ais.fi/eaip/currently_effective/eAIP/EF-ENR%205.1-en-GB.html"
# An AIRAC supplement has "A_" before its year.
SUPPLEMENT_URL: Final = "https://www.ais.fi/aipsup/Sup/S{year}/EF_SUP_{airac}{year}_{number:03d}_en.pdf"

# The bulletin is updated every half hour, and the page says when next. Polled a little after that.
POLL: Final = timedelta(minutes=30)
AFTER_UPDATE: Final = timedelta(minutes=3)
# A page late to update, or one from a node of the CDN still behind, is fetched again after this.
LATE: Final = timedelta(minutes=5)
ENR_5_1_POLL: Final = timedelta(days=1)
# A supplement no NOTAM has named for this long is forgotten.
SUPPLEMENT_KEPT: Final = timedelta(days=30)

EVENT_NEW_RESTRICTION: Final = f"{DOMAIN}_new_restriction"

MAP_FEED_VERSION: Final = 1
