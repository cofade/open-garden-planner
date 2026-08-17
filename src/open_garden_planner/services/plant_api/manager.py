"""Plant API manager with fallback chain."""

import logging
from typing import Any

from open_garden_planner.models.plant_data import PlantSpeciesData

from .base import PlantAPIClient, PlantAPIError, PlantDetailUnavailableError
from .perenual_client import PerenualClient
from .permapeople_client import PermapeopleClient
from .trefle_client import TrefleClient

logger = logging.getLogger(__name__)


class PlantAPIManager:
    """Manager for plant API clients with automatic fallback.

    Implements the fallback chain specified in the PRD:
    1. Trefle.io (primary) - Comprehensive botanical database, 400,000+ species
    2. Perenual (secondary) - Most reliable, active maintenance
    3. Permapeople (tertiary) - Community-driven
    4. Bundled database (offline fallback) - Not yet implemented
    5. User-defined entries (always available) - Not yet implemented

    The manager automatically tries each service in order until one succeeds.
    """

    def __init__(
        self,
        trefle_api_token: str | None = None,
        perenual_api_key: str | None = None,
        permapeople_key_id: str | None = None,
        permapeople_key_secret: str | None = None,
    ) -> None:
        """Initialize the plant API manager.

        Args:
            trefle_api_token: Optional Trefle API token
            perenual_api_key: Optional Perenual API key
            permapeople_key_id: Optional Permapeople key ID
            permapeople_key_secret: Optional Permapeople key secret
        """
        self._clients: list[PlantAPIClient] = []

        # Initialize clients in fallback order (Trefle first)
        try:
            trefle = TrefleClient(api_token=trefle_api_token)
            self._clients.append(trefle)
            logger.info("Trefle client initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize Trefle client: {e}")

        try:
            perenual = PerenualClient(api_key=perenual_api_key)
            self._clients.append(perenual)
            logger.info("Perenual client initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize Perenual client: {e}")

        try:
            permapeople = PermapeopleClient(
                key_id=permapeople_key_id,
                key_secret=permapeople_key_secret,
            )
            self._clients.append(permapeople)
            logger.info("Permapeople client initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize Permapeople client: {e}")

        # TODO: Add bundled database client when implemented

    @property
    def configured_source_count(self) -> int:
        """Number of API clients that have the credentials needed to
        attempt a request (`client.is_configured()`), NOT just how many
        clients exist in the fallback chain.

        Lets a caller (e.g. the search dialog, #302) distinguish "no plant
        databases are configured at all" from "search ran and matched
        nothing" -- both surface as an empty result list from `search()`.
        `PlantAPIManager`'s constructor always appends a Trefle/Perenual/
        Permapeople client regardless of whether credentials were supplied
        (their `__init__` never raises on a missing token/key), so counting
        `len(self._clients)` would always report "configured" even with zero
        real credentials -- this counts only the ones that actually are.

        Returns:
            Count of clients in the fallback chain whose `is_configured()`
            returns True. Says nothing about current reachability -- see
            `check_status()` / `get_available_sources()` for that.
        """
        return sum(1 for c in self._clients if c.is_configured())

    def search(self, query: str, limit: int = 10) -> list[PlantSpeciesData]:
        """Search for plants across custom library and all available APIs.

        First searches the custom plant library, then tries each API in order
        until one succeeds. Custom plants are shown first in the results.

        A client that *answers* -- returns normally, even with an empty list
        -- means "no match", not "failure" (#302: a search for a real but
        unlisted variety, e.g. "mahachanok", was misreported as "All plant
        APIs failed" even though every configured API responded cleanly with
        zero results). A client with no credentials (`is_configured()` is
        False) is skipped entirely -- it is never attempted and never
        counted as having failed. Only when every *configured* client raises
        (or there are no configured clients and no custom-library results)
        is this a genuine failure.

        Args:
            query: Search term (plant name or partial name)
            limit: Maximum number of results to return

        Returns:
            List of matching plant species data. An empty list means the
            search ran successfully but matched nothing -- NOT a failure.

        Raises:
            PlantAPIError: Only if every configured API client raised (i.e.
                none of them could even answer) and no custom plants were
                found. A client answering with zero results is never treated
                as a failure.
        """
        if not query or not query.strip():
            return []

        results: list[PlantSpeciesData] = []

        # First, search custom plant library
        try:
            from open_garden_planner.services.plant_library import get_plant_library

            library = get_plant_library()
            custom_results = library.search_plants(query)
            if custom_results:
                logger.info(f"Custom library returned {len(custom_results)} results")
                results.extend(custom_results)
        except Exception as e:
            logger.warning(f"Custom library search failed: {e}")

        # If we have enough results from custom library, return them
        if len(results) >= limit:
            return results[:limit]

        # Try each API in order
        last_error: Exception | None = None
        any_client_answered = False
        remaining_limit = limit - len(results)

        for client in self._clients:
            if not client.is_configured():
                logger.debug(f"{client.name} is not configured (no credentials), skipping")
                continue

            try:
                logger.info(f"Trying {client.name} API for search: '{query}'")
                api_results = client.search(query, remaining_limit)
                any_client_answered = True

                if api_results:
                    logger.info(f"{client.name} returned {len(api_results)} results")
                    results.extend(api_results)
                    break  # Got results from an API, stop trying others
                else:
                    logger.info(f"{client.name} returned no results")

            except PlantAPIError as e:
                logger.warning(f"{client.name} API failed: {e}")
                last_error = e
                continue
            except Exception as e:
                logger.error(f"Unexpected error with {client.name}: {e}")
                last_error = e
                continue

        # If we have any results (custom or API), return them
        if results:
            return results[:limit]

        # At least one configured client answered (even with zero matches)
        # -- that is an honest "no match", not a failure. Returning [] here
        # (rather than raising) is the fix for #302.
        if any_client_answered:
            return []

        # No client had credentials to even attempt a request, and no
        # custom-library results: nothing was tried, so nothing failed
        # either. Checked via `configured_source_count`, not `self._clients`
        # -- the constructor always appends a client per provider regardless
        # of whether real credentials were supplied (#302 follow-up: an
        # uncredentialed client's `is_configured() == False` skip above means
        # `self._clients` alone can no longer answer "was anything usable
        # configured?").
        if self.configured_source_count == 0:
            return []

        # Every configured client raised and none could answer -- genuine
        # failure.
        error_msg = "All plant APIs failed"
        if last_error:
            error_msg += f": {last_error}"
        raise PlantAPIError(error_msg)

    def get_by_id(self, plant_id: str, source: str) -> PlantSpeciesData:
        """Get detailed plant data by ID from a specific source.

        Args:
            plant_id: Unique identifier in the source's database
            source: Source name ("perenual", "permapeople", etc.)

        Returns:
            Complete plant species data

        Raises:
            PlantAPIError: If the API request fails or source not found
        """
        # Find the client for this source
        for client in self._clients:
            if client.name.lower() == source.lower():
                try:
                    return client.get_by_id(plant_id)
                except PlantDetailUnavailableError:
                    # Not a failure -- pass through unwrapped so callers can
                    # distinguish it from a genuine error (#297 round 4).
                    raise
                except PlantAPIError as e:
                    raise PlantAPIError(f"Failed to get plant from {source}: {e}") from e

        raise PlantAPIError(f"No client available for source: {source}")

    def get_available_sources(self) -> list[str]:
        """Get list of currently available API sources.

        Returns:
            List of source names that are operational
        """
        available = []
        for client in self._clients:
            try:
                if client.is_available():
                    available.append(client.name)
            except Exception as e:
                logger.debug(f"Failed to check {client.name} availability: {e}")
                continue

        return available

    def check_status(self) -> dict[str, Any]:
        """Check status of all configured API clients.

        Returns:
            Dictionary mapping client names to their availability status
        """
        status = {}
        for client in self._clients:
            try:
                is_available = client.is_available()
                status[client.name] = {
                    "available": is_available,
                    "configured": True,
                }
            except Exception as e:
                status[client.name] = {
                    "available": False,
                    "configured": True,
                    "error": str(e),
                }

        return status
