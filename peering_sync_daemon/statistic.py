import dataclasses


@dataclasses.dataclass()
class Information:
    """Використовується для передачі інформації про стан завантаження та відвантаження для інших компонентів програми"""
    total_size: int
    uploaded_per_session: int
    downloaded_per_session: int
    downstate: int
    left: int
    peers_count: int
    connected_peers: int
    interesting_peers: int
    file_path: str
    identification: str
    seed_ver: int
    is_download: bool
