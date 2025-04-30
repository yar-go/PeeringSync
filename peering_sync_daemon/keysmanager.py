import hashlib
import os.path
import shutil

from cryptography.hazmat.primitives.asymmetric import dsa
from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_pem_public_key
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm


class BadPublicKey(Exception):
    pass


class BadPrivateKey(Exception):
    pass


class EmptyPrivateKey(Exception):
    pass


class BadKeyPair(Exception):
    pass


class KeysExist(Exception):
    pass

class KeysNotExist(Exception):
    pass

class Key:
    def __init__(self, pb_key, pv_key):
        self.__private = pv_key
        self.__public = pb_key
        self.algorithm = hashes.SHA256()

        hasher = hashlib.sha256()
        public_pem = self.__public.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        hasher.update(public_pem)
        self.__net_id = hasher.digest()
        self.__net_id_str = hasher.hexdigest()

    @property
    def is_private(self):
        return True if self.__private else False

    @property
    def network_identifier(self):
        return self.__net_id

    @property
    def network_identifier_str(self):
        return self.__net_id_str

    def sign(self, data):
        if not self.is_private:
            raise EmptyPrivateKey
        signature = self.__private.sign(data, self.algorithm)
        return signature

    def verify(self, data, signature):
        if not signature: return False
        try:
            self.__public.verify(signature, data, hashes.SHA256())
            return True
        except InvalidSignature:
            return False

    @classmethod
    def deserialize(cls, public_pem, private_pem=None):
        try:
            public_key = load_pem_public_key(public_pem, None)
            if not isinstance(public_key, dsa.DSAPublicKey):
                raise BadPublicKey
            if private_pem:
                private_key = load_pem_private_key(private_pem, None)
                if not isinstance(private_key, dsa.DSAPrivateKey):
                    raise BadPrivateKey
            else:
                private_key = None
        except ValueError or UnsupportedAlgorithm as e:
            raise e

        if private_key:
            derived_public_key = private_key.public_key()
            if derived_public_key.public_numbers() != public_key.public_numbers():
                raise BadKeyPair

        return cls(public_key, private_key)


class KeysManager:
    def __init__(self, storage: str):
        self.storage = storage  # TODO keystore setting
        if not os.path.exists(self.storage):
            os.makedirs(self.storage)

        self.keys = dict()

    def get_all_keys(self):
        ids = os.listdir(self.storage)
        keys = list()
        for id_ in ids:
            k = self.keys.get(id_)
            if k:
                keys.append(k)
                continue
            try:
                key = self.get_key(id_)
                keys.append(key)
            except:
                pass
        return keys

    def import_keys(self, public: str, private: str) -> str:
        public_pem = public.encode("utf-8")
        private_pem = private.encode("utf-8")
        try:
            public_key = load_pem_public_key(public_pem, None)
            if not isinstance(public_key, dsa.DSAPublicKey):
                raise BadPublicKey
            if private_pem:
                private_key = load_pem_private_key(private_pem, None)
                if not isinstance(private_key, dsa.DSAPrivateKey):
                    raise BadPrivateKey
            else:
                private_key = None
        except ValueError or UnsupportedAlgorithm as e:
            raise e

        if private_key:
            derived_public_key = private_key.public_key()
            if derived_public_key.public_numbers() != public_key.public_numbers():
                raise BadKeyPair

        hasher = hashlib.sha256()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        hasher.update(public_pem)
        dir_name = hasher.hexdigest()
        dir_path = os.path.join(self.storage, dir_name)
        if os.path.exists(dir_path):
            raise KeysExist
        else:
            os.makedirs(dir_path)

        with open(os.path.join(dir_path, "public.pem"), "wt") as f:
            f.write(public_pem.decode("utf-8"))

        if private_key:
            private_pem =private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )

            with open(os.path.join(dir_path, "private.pem"), "wt") as f:
                f.write(private_pem.decode("utf-8"))

        return dir_name

    def export_keys(self, id) -> (str, str,):
        keys_dir = os.path.join(self.storage, id)
        if not os.path.exists(keys_dir):
            raise KeysNotExist

        t = os.path.join(keys_dir, "public.pem")
        if os.path.exists(t):
            with open(t, "r") as f:
                public_key_content = f.read()
        else:
            raise KeysNotExist

        t = os.path.join(keys_dir, "private.pem")
        if os.path.exists(t):
            with open(t, "r") as f:
                private_key_content = f.read()
        else:
            private_key_content = ""

        return public_key_content, private_key_content

    def get_key(self, id) -> Key:
        k = self.keys.get(id, None)
        if k:
            return k

        keys_dir = os.path.join(self.storage, id)
        if not os.path.exists(keys_dir):
            raise KeysNotExist

        path_private = os.path.join(keys_dir, "private.pem")
        path_public = os.path.join(keys_dir, "public.pem")
        if os.path.exists(path_private):
            with open(path_private) as f:
                private_pem = f.read().encode("utf-8")
        else:
            private_pem = None
        if os.path.exists(path_public):
            with open(path_public) as f:
                public_pem = f.read().encode("utf-8")

        key = Key.deserialize(public_pem, private_pem)
        self.keys[id] = key
        return key

    def delete(self, id:str):
        keys_dir = os.path.join(self.storage, id)
        if not os.path.exists(keys_dir):
            raise KeysNotExist
        if self.keys.get(id):
            self.keys.pop(id)
        shutil.rmtree(keys_dir)

    def generate_new(self):
        private_key = dsa.generate_private_key(key_size=1024)
        public_key = private_key.public_key()

        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )

        hasher = hashlib.sha256()
        hasher.update(public_pem)
        net_id = hasher.hexdigest()

        key_dir = os.path.join(self.storage, net_id)
        if not os.path.exists(key_dir):
            os.makedirs(key_dir)

        # Збереження ключів у файли
        with open(os.path.join(key_dir, "public.pem"), "wb") as f:
            f.write(public_pem)
        with open(os.path.join(key_dir, "private.pem"), "wb") as f:
            f.write(private_pem)

        return Key(public_key, private_key)


