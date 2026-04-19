"""Infrastructure package for adapters."""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "LibrosaAudioLoader",
    "MasterUdpUploadTransport",
    "UdpShowTransport",
    "UdpTransportConfig",
    "UiMastersMapper",
]

_NAME_TO_MODULE = {
    "LibrosaAudioLoader": "audio_loader",
    "MasterUdpUploadTransport": "master_udp_upload_transport",
    "UdpShowTransport": "udp_transport",
    "UdpTransportConfig": "udp_transport",
    "UiMastersMapper": "ui_masters_mapper",
}


def __getattr__(name: str):
    module_name = _NAME_TO_MODULE.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(f".{module_name}", __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(list(globals()) + __all__))
