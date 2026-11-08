"""Accesso HTTP condiviso a Google Travel.

Un solo punto per: cookie di consenso, throttling, retry/backoff e budget di
richieste. Senza il cookie di consenso Google risponde con l'interstiziale
("Prima di continuare") al posto dei risultati in tutta l'UE.
"""

from __future__ import annotations

import threading
import time

# Cookie che dichiara "solo cookie necessari": evita l'interstiziale di consenso.
CONSENT_COOKIES = {
    "SOCS": "CAESHAgBEhJnd3NfMjAyMzA4MTAtMF9SQzIaAmVuIAEaBgiA_LyaBg",
}

IMPERSONATE = "chrome_145"
IMPERSONATE_OS = "macos"
GOOGLE_ROOT = "https://www.google.com/"

MISSING_DEP = (
    "tripscout richiede il pacchetto 'primp' (e 'fast-flights' per i voli): "
    "pip install primp fast-flights"
)


class GoogleBlocked(RuntimeError):
    """Google ha risposto con una challenge o un blocco (non riprovabile a breve)."""


class BudgetExhausted(RuntimeError):
    """Esaurito il tetto di richieste di questa ricerca: i risultati sono parziali."""


def looks_blocked(text: str) -> bool:
    """True se il corpo è una pagina di consenso, di blocco o di traffico anomalo."""
    low = text.casefold()
    return (
        "/sorry/" in low
        or "unusual traffic" in low
        or "prima di continuare" in low
        or "before you continue" in low
    )


class Session:
    """Client sincrono con throttling, retry e contatore di richieste.

    Un'istanza per ricerca: il throttling è globale all'istanza, il budget pure.
    """

    def __init__(
        self,
        *,
        min_interval: float = 1.0,
        max_requests: int | None = None,
        max_retries: int = 3,
        timeout: float = 30.0,
    ) -> None:
        try:
            import primp
        except ModuleNotFoundError as exc:  # dipendenza dichiarata nel manifest
            raise RuntimeError(MISSING_DEP) from exc
        self._client = primp.Client(
            impersonate=IMPERSONATE,
            impersonate_os=IMPERSONATE_OS,
            referer=True,
            cookie_store=True,
            timeout=timeout,
        )
        self._client.set_cookies(GOOGLE_ROOT, dict(CONSENT_COOKIES))
        self._lock = threading.Lock()
        self._last = 0.0
        self._min_interval = max(0.0, min_interval)
        self._max_retries = max(0, max_retries)
        self.max_requests = max_requests
        self.requests = 0
        self.retries = 0

    @property
    def budget_left(self) -> int | None:
        return None if self.max_requests is None else max(0, self.max_requests - self.requests)

    def _reserve(self) -> None:
        with self._lock:
            if self.max_requests is not None and self.requests >= self.max_requests:
                raise BudgetExhausted(
                    f"budget di {self.max_requests} richieste esaurito"
                )
            self.requests += 1

    def _wait(self) -> None:
        with self._lock:
            gap = self._min_interval - (time.monotonic() - self._last)
            if gap > 0:
                time.sleep(gap)
            self._last = time.monotonic()

    def _run(self, call, *, expect_json: bool = False):
        """Esegue `call`, con retry su errori transitori e su risposte bloccate."""
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            self._reserve()
            self._wait()
            try:
                response = call()
            except Exception as exc:  # rete, DNS, timeout TLS
                last_error = exc
                if attempt < self._max_retries:
                    self.retries += 1
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise
            status = getattr(response, "status_code", 200)
            if status == 429 or 500 <= status < 600:
                last_error = GoogleBlocked(f"HTTP {status}")
                if attempt < self._max_retries:
                    self.retries += 1
                    time.sleep(2.0 * (attempt + 1))
                    continue
                raise last_error
            text = response.text
            if looks_blocked(text):
                last_error = GoogleBlocked("Google ha risposto con consenso/blocco")
                if attempt < self._max_retries:
                    self.retries += 1
                    time.sleep(2.0 * (attempt + 1))
                    continue
                raise last_error
            return response
        raise last_error if last_error else RuntimeError("richiesta fallita")

    def get(self, url: str, *, params: dict | None = None):
        return self._run(lambda: self._client.get(url, params=params))

    def post(self, url: str, *, body: str, headers: dict | None = None):
        return self._run(
            lambda: self._client.post(url, content=body.encode("utf-8"), headers=headers or {})
        )
