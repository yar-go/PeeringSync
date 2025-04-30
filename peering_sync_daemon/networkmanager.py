import base64
import dataclasses
import os
import platform
import subprocess

from .keysmanager import KeysManager, Key
from .database import Database
from .network import Network
from .peer import Peer
from .bencoder import BenCoder


class NetworkManager:
    def __init__(self, keysmanager: 'KeysManager', database: 'Database', peer_id, own_address):
        self._km = keysmanager
        self._db = database
        self._own_peer_id = peer_id
        self._own_address = own_address

        self._networks = dict()
        self._load_networks()

    def _load_networks(self):
        keys = self._km.get_all_keys()
        for k in keys:
            n = Network.open_network(k, self._own_peer_id, self._db)
            n.start()
            self._networks[n.identification] = n

    def create_new_network(self, name, filepath, peers: list[str]):
        key = self._km.generate_new()
        self._add_network(key, filepath, name, peers)
        return key.network_identifier_str

    async def update_files(self,network_id):
        n = self._networks.get(network_id)
        if not n:
            return None
        await n.update_files()

    def import_network(self, name, key_private, key_public, filepath, peers):
        path_name = self._km.import_keys(key_public, key_private)
        key = self._km.get_key(path_name)
        return self._add_network(key, filepath, name, peers)

    def open_folder(self, network_id):
        n = self._networks.get(network_id)
        if not n: return
        open_folder(n.file_storage)

    def export_network_keys(self, network_id):
        n = self._networks.get(network_id)
        if not n:
            return None, None
        k: Key = n.key
        public, private = self._km.export_keys(k.network_identifier_str)
        return public, private

    async def delete_network(self, network_id):
        await self.stop_network(network_id)
        try: self._networks.pop(network_id)
        except KeyError: pass
        try: self._km.delete(network_id)
        except: pass

    def start_network(self, network_id):
        n = self._networks.get(network_id)
        if n:
            n.start()
            return True
        return False

    async def stop_network(self, network_id):
        n = self._networks.get(network_id)
        if n and n.is_run:
            await n.stop()
            return True
        return False

    def add_peers_network(self, network_id, peers):
        n = self._networks.get(network_id)
        for p in peers:
            host, port = p.split(":")
            k = Peer(host, port)
            n.add_peer(k)

    def get_all_info(self):
        result = dict()
        networks = list()

        for net in list(self._networks.values()):
            r = dict()
            r['name'] = net.name
            r['statistic'] = dataclasses.asdict(net.statistic)
            r['identification_str'] = net.identification
            # r['map'] = BenCoder.encode(net.get_map())
            r['map'] = base64.b64encode(BenCoder.encode(net.get_map())).decode('utf-8')
            r['check_updates'] = net.check_diff_files()
            r['files'] = net.get_status_files()
            networks.append(r)
        result['networks'] = networks
        result["own_peer_id"] =  self._own_peer_id.decode()
        result["own_address"] = self._own_address

        return result

    def _add_network(self, key, filepath, name, peers):
        Network.add_network(key, filepath, name, self._db)
        network = Network.open_network(key, self._own_peer_id, self._db)
        self._networks[network.identification] = network
        for p in peers:
            host, port = p.split(":")
            k = Peer(host, port)
            network.add_peer(k)
        network.start()
        return key.network_identifier_str

    def add_outter_peer(self, network_identification, peer):
        networks = list(self._networks.values())
        for n in networks:
            if n.key.network_identifier == network_identification:
                    n.add_peer(peer, outter=True)
                    break

    def get_working_network_ids(self):
        networks = list(self._networks.values())
        keys_ids = [i.key for i in networks if i.is_run]
        return keys_ids

    async def stop_all(self):
        for net in list(self._networks.keys()):
            await self.stop_network(net)


def open_folder(folder_path):
    if not os.path.isdir(folder_path):
        print(f"Помилка: Папка '{folder_path}' не існує.")
        return False

    system = platform.system()
    try:
        if system == 'Windows':
            os.startfile(folder_path)
        elif system == 'Darwin':
            subprocess.call(['open', folder_path])
        elif system == 'Linux':
            subprocess.call(['xdg-open', folder_path])
        else:
            print(f"Непідтримувана операційна система: {system}")
            return False

        print(f"Папку '{folder_path}' успішно відкрито.")
        return True

    except Exception as e:
        print(f"Помилка при відкритті папки: {e}")
        return False