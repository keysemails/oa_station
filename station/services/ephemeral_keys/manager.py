"""
Ephemeral Key Manager

Manages ephemeral API keys programmatically via the OpenRouter API.
"""

from typing import Optional, List, Dict, Any
import httpx
from loguru import logger


class EphemeralKeyManager:
    """Manager for ephemeral API keys."""

    BASE_URL = "https://openrouter.ai/api/v1/keys"

    def __init__(self, management_key: str):
        """
        Initialize the ephemeral key manager.

        Args:
            management_key: OpenRouter management API key

        Raises:
            ValueError: If no management key is provided
        """
        if not management_key:
            raise ValueError("Management key is required")

        self.management_key = management_key
        self.headers = {
            "Authorization": f"Bearer {self.management_key}",
            "Content-Type": "application/json"
        }
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create a shared httpx client for connection reuse."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=self.headers,
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        """Close the shared HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def create_key(
        self,
        name: str,
        limit: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Create a new API key.

        Args:
            name: Name/label for the API key
            limit: Optional credit limit in USD

        Returns:
            Dict containing 'key' (the actual API key) and 'data' (key metadata including hash)

        Raises:
            httpx.HTTPError: If the API request fails
        """
        payload = {"name": name}
        if limit is not None:
            payload["limit"] = limit

        client = self._get_client()
        response = await client.post(self.BASE_URL, json=payload)
        response.raise_for_status()
        return response.json()

    async def list_keys(self) -> List[Dict[str, Any]]:
        """
        List all existing API keys.

        Returns:
            List of key metadata dictionaries

        Raises:
            httpx.HTTPError: If the API request fails
        """
        client = self._get_client()
        response = await client.get(self.BASE_URL)
        response.raise_for_status()
        data = response.json()
        return data.get("data", [])

    async def update_key(
        self,
        key_hash: str,
        name: Optional[str] = None,
        limit: Optional[float] = None,
        disabled: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        Update an existing API key's attributes.

        Args:
            key_hash: Hash identifier of the key to update
            name: New name/label for the key
            limit: New credit limit in USD
            disabled: Whether to disable the key

        Returns:
            Updated key metadata

        Raises:
            httpx.HTTPError: If the API request fails
        """
        payload = {}
        if name is not None:
            payload["name"] = name
        if limit is not None:
            payload["limit"] = limit
        if disabled is not None:
            payload["disabled"] = disabled

        if not payload:
            raise ValueError("At least one attribute (name, limit, disabled) must be provided")

        client = self._get_client()
        response = await client.patch(f"{self.BASE_URL}/{key_hash}", json=payload)
        response.raise_for_status()
        return response.json()

    async def delete_key(self, key_hash: str) -> Dict[str, Any]:
        """
        Delete an API key.

        Args:
            key_hash: Hash identifier of the key to delete

        Returns:
            Response data from the deletion

        Raises:
            httpx.HTTPError: If the API request fails
        """
        client = self._get_client()
        response = await client.delete(f"{self.BASE_URL}/{key_hash}")
        response.raise_for_status()
        return response.json()
