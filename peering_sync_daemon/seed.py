import hashlib
import os
import tempfile
import time
from collections import OrderedDict
from math import ceil

from .bitfield import BitField
from .filesmanager import FilesManager
from .bencoder import BenCoder

class Seed:
    def __init__(self, data, signature=b""):
        self._raw = data
        self._data = BenCoder.decode(data)
        self._signature = signature
        self._full_file_size = sum([i['length'] for i in self._data["files"]])

    @property
    def raw(self):
        return self._raw

    @property
    def signature(self):
        return self._signature

    @signature.setter
    def signature(self, value):
        if isinstance(value, bytes):
            self._signature = value
        else:
            raise ValueError("Bad type")

    @property
    def version(self):
        return self._data['version']

    @property
    def countFiles(self):
        return len(self._data.get("files", [""]))

    @property
    def files(self):
        files = [(i['length'], i['path'], i.get("hash")) for i in self._data["files"]]
        return files

    @property
    def length(self):
        return self._full_file_size

    @property
    def piece_length(self):
        return self._data["piece length"]

    @property
    def pieces(self):
        return self._data["pieces"]

    def encode(self):
        s = self._signature if self._signature else b""
        d = self._raw
        return BenCoder.encode([s,d,])

    @classmethod
    def decode(cls, data):
        try:
            s, d = BenCoder.decode(data)
            return cls(d, s)
        except:
            return None

    @classmethod
    def create_seed(cls, path, version=None):
        if version is None:
            version = int(time.time())
        with open(os.path.join(path, ".syncdir"), "wb") as f:
            f.write(b"PeeringSync")


        file_paths = []
        for root, dirs, files in os.walk(path):
            for name in files:
                file_paths.append(os.path.join(root, name))

        if not len(file_paths):
            raise Exception("Empty folder")

        files = list()
        total_size_bytes = 0
        for file_path in file_paths:
            with open(file_path, "rb") as f:
                content = f.read()
                file_hash = hashlib.sha1(content).digest()
            total_size_bytes += os.path.getsize(file_path)
            file_path_exp = os.path.relpath(file_path, path)
            d = OrderedDict()
            d["length"] = os.path.getsize(file_path)
            d["path"] = file_path_exp
            d["hash"] = file_hash
            files.append(d)

        piece_length = 64 * 1024
        max_pieces = 200
        while total_size_bytes / piece_length > max_pieces:
            piece_length *= 2

        bitfield = BitField(ceil(total_size_bytes / piece_length), version)
        f = [ (i["length"], i["path"], i["hash"]) for i in files ]
        fm = FilesManager(total_size_bytes, bitfield, piece_length, path, f)
        pieces = b""
        for i in range(len(fm.bitfield)):
            pieces += hashlib.sha1(fm.read_piece(i)).digest()

        res = OrderedDict()

        res["version"] = version
        res["piece length"] = piece_length
        res["files"] = files
        res["pieces"] = pieces

        bencoded = BenCoder.encode(res)

        return cls(bencoded)

    @classmethod
    def create_empty_seed(cls):
        with tempfile.TemporaryDirectory() as tmpdirname:
            empty_seed = cls.create_seed(tmpdirname, 0)

        return empty_seed

