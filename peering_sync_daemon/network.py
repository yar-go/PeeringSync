from .keysmanager import Key
from .seed import Seed
from .loadmanager import LoadManager
from .database import Database

import asyncio


class Network:
    def __init__(self, peer_id: bytes, key: Key, seed: Seed, files_path: str, db: Database, name: str):
        self._key = key
        self._filepath = files_path
        self._name = name
        self._loadmanager = LoadManager(key, seed, files_path, peer_id, log_func=print)
        self._loadmanager.reg_updated_peers_clb(self._seed_updated)

        self._db = db

        self._run_task = None

    def start(self):
        self._run_task = asyncio.Task(self._loadmanager.run())

    async def stop(self):
        await self._loadmanager.shutdown()
        try:
            self._run_task
        except:
            pass
        self._run_task = None

    @property
    def is_run(self):
        return bool(self._run_task)

    @property
    def identification(self):
        return self._key.network_identifier_str

    @property
    def key(self):
        return self._key

    @property
    def statistic(self):
        return self._loadmanager.get_stat()

    @property
    def name(self):
        return self._name

    @property
    def file_storage(self):
        return self._loadmanager.filesmanager.destination

    def get_status_files(self):
        return self._loadmanager.filesmanager.get_status()

    def add_peer(self, peer, outter=False):
        if outter:
            self._loadmanager.add_connected_peer(peer)
        else:
            self._loadmanager.add_unconnected_peers([peer, ])

    def get_map(self):
        return self._loadmanager.peers_map

    def check_diff_files(self):
        tmp_seed = Seed.create_seed(self._filepath, 0)
        if tmp_seed.raw == self._loadmanager.seed.raw:
            return False
        return True

    async def update_files(self):
        tmp_seed = Seed.create_seed(self._filepath)
        tmp_seed.signature = self._key.sign(tmp_seed.raw)
        await self._loadmanager.update_seed(tmp_seed)

    def _seed_updated(self, new_seed: 'Seed'):
        seed_data = new_seed.encode()
        self._db.insert_seed(self._key.network_identifier, new_seed.version, seed_data)

    @classmethod
    def open_network(cls, key, peer_id, db):
        net_id = key.network_identifier
        r = db.get_latest_seed(net_id)
        if not r:
            seed = Seed.create_empty_seed()
        else:
            seed = Seed.decode(r[1])

        f = db.get_latest_path(net_id)
        files_path = f[1]
        n = db.get_latest_name(net_id)
        if n:
            net_name = n[1]
        else: net_name = ""

        return cls(peer_id, key, seed, files_path, db, net_name)

    @classmethod
    def add_network(cls, key, path_file, name, db):
        net_id = key.network_identifier
        seed = Seed.create_empty_seed()
        db.insert_seed(net_id, 0, seed.encode())
        db.insert_path(net_id, 0, path_file)
        db.insert_name(net_id, 0, name)
