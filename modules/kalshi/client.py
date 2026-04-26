import base64
import logging
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

logger = logging.getLogger(__name__)

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"


class KalshiClient:
    def __init__(self, key_id: str, private_key_path: str):
        self._key_id = key_id
        self._private_key = self._load_key(private_key_path)

    def _load_key(self, path: str):
        pem = Path(path).read_bytes()
        return serialization.load_pem_private_key(pem, password=None)

    def _auth_headers(self, method: str, path: str) -> dict:
        ts = int(datetime.now(timezone.utc).timestamp() * 1000)
        msg = f"{ts}{method}{path}".encode()
        sig = self._private_key.sign(
            msg,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )
        return {
            "KALSHI-ACCESS-KEY": self._key_id,
            "KALSHI-ACCESS-TIMESTAMP": str(ts),
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode(),
        }

    async def get(self, path: str, params: dict | None = None) -> dict:
        """Signed GET request. path must NOT include query string."""
        headers = self._auth_headers("GET", path)
        async with aiohttp.ClientSession() as session:
            async with session.get(
                BASE_URL + path, headers=headers, params=params
            ) as resp:
                resp.raise_for_status()
                return await resp.json()
