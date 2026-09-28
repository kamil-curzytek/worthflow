"""Makes outbound HTTPS calls trust the OS certificate store, not just certifi's
bundled list. Needed on machines where a corporate proxy or antivirus does TLS
inspection with a root CA that's trusted by Windows but isn't in certifi.
Call once, before any outbound HTTPS request (exchange rates, future AI APIs).
"""

_injected = False


def ensure_system_trust_store() -> None:
    global _injected
    if _injected:
        return
    import truststore

    truststore.inject_into_ssl()
    _injected = True
