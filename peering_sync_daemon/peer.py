import asyncio
import time
import struct
import typing

from .bitfield import BitField
from .bencoder import BenCoder
from .keysmanager import Key
from .seed import Seed


class PeerNotConnected(Exception):
    pass


class Peer:
    def __init__(self, ip: str, port: int, peer_id=None):
        self._ip = ip.strip()
        self._port = port
        self._peer_id = peer_id

        self._stream_reader: asyncio.StreamReader | None = None
        self._stream_writer: asyncio.StreamWriter | None = None
        self._connected = False

        self._am_choking = True
        self._am_interested = False
        self._peer_choking = True
        self._peer_interested = False

        self._keep_aliver_task: asyncio.Task | None = None
        self._last_message_time = 0

        self._requested_blocks: dict[tuple[int, int], tuple[int, asyncio.Future]] = dict()
        self._requested_seed_future = None
        self._requested_peers_future = None

        self._data_taker_clb: typing.Callable | None = None
        self._key: Key | None = None
        self._bitfield = None

        self._version_files_clb = None

    @property
    def ip(self):
        return self._ip

    @property
    def port(self):
        return self._port

    @property
    def id(self):
        return self._peer_id

    @property
    def connected(self):
        return self._connected

    @property
    def am_choking(self):
        return self._am_choking

    @property
    def am_choked(self):
        return self._peer_choking

    @property
    def am_interesting(self):
        return self._am_interested

    @property
    def am_interested(self):
        return self._peer_interested

    @property
    def bitfield(self):
        return self._bitfield

    async def connect(self, key: Key, peer_id: bytes, timeout: int = 3) -> bool:
        self._key = key
        info_hash = key.network_identifier

        async def _keep_aliver():
            await asyncio.sleep(5)
            while True:  # norma
                if time.time() - self._last_message_time >= 10 and not self.am_choked:
                    await self.keep_alive()
                await asyncio.sleep(1)

        del self._stream_writer
        del self._stream_reader
        self._stream_writer = self._stream_reader = None
        try:
            self._stream_reader, self._stream_writer = \
                await asyncio.wait_for(asyncio.open_connection(self.ip, self.port), timeout)
        except:
            return False

        pstr = bytearray(b"PeeringSync protocol")
        reversed_ = bytearray(8)
        handshake = struct.pack(f"!B{len(pstr)}s8s32s20s",
                                len(pstr), pstr, reversed_,
                                info_hash, peer_id)

        try:
            await self._safe_write(handshake)
            r = await self._stream_reader.read(len(handshake))
        except:
            return False

        if not r:
            return False

        _, r_pstr, r_reversed, r_info_hash, r_peer_id = struct.unpack(f"!B{len(r) - 61}s8s32s20s", r)
        # TODO (may) remove "61"

        if info_hash == r_info_hash and (self._peer_id is None or self._peer_id == r_peer_id):
            self._connected = True
            self._peer_id = r_peer_id
            self._am_choking = self._peer_choking = True
            self._am_interested = self._peer_interested = False
            self._keep_aliver_task = asyncio.create_task(_keep_aliver())
            self._last_message_time = time.time()
            return True

        try:
            self._stream_writer.close()
            await self._stream_writer.wait_closed()
        except:
            pass
        return False

    async def disconnect(self) -> None:
        if not self._connected:
            return None
        self._connected = False
        self._keep_aliver_task.cancel()
        try: await self._keep_aliver_task
        except asyncio.CancelledError: pass
        [i[1].cancel() for i in self._requested_blocks.values()]

        try:
            if not self._stream_writer.is_closing():
                self._stream_writer.close()
                await self._stream_writer.wait_closed()
        except: pass

        self._peer_choking = self._am_choking = True
        self._am_interested = self._peer_interested = True
        self._last_message_time = 0

    async def listen(self) -> None:
        if not self._connected:
            raise PeerNotConnected()

        buffer = bytes()
        while self._connected:
            try:
                data = await self._stream_reader.read(2**14)
            except:
                await self.disconnect()
                break
            if not data:
                await self.disconnect()
                break
            buffer += data

            while len(buffer) >= 4:
                message_len = int.from_bytes(buffer[:4])
                if not len(buffer) >= message_len + 4:
                    break

                if message_len == 0:
                    pass  # TODO keep-alive
                    buffer = buffer[4:]
                    continue

                message_id = buffer[4]
                message = buffer[5:4 + message_len]
                if message_id == 0:  # Choke
                    self._peer_choking = True
                elif message_id == 1:  # Unchoke
                    self._peer_choking = False
                elif message_id == 2:  # interested
                    self._peer_interested = True
                elif message_id == 3:  # uninterested
                    self._peer_interested = False
                elif message_id == 4:  # have
                    index = struct.unpack('!i', message)[0]
                    self._bitfield.set(index)
                elif message_id == 5:  # bitfield
                    bits_count, ver, bits = struct.unpack(f"!ii{len(message)-8}s", message)
                    self.receive_bitfield(bits_count, ver, bits)
                elif message_id == 6:  # requests
                    index, begin, length = struct.unpack(f'!iii', message)
                    self._me_requested(index, begin, length)
                elif message_id == 7:  # piece
                    index, begin, block = struct.unpack(f'!ii{message_len-9}s', message)
                    self._get_piece(index, begin, block)
                elif message_id == 8:  # cancel
                    pass
                elif message_id == 9:  # port
                    pass  # DHT. I can nothing to do now

                elif message_id in (100,):  # master commands
                    signature_length = int.from_bytes(message[:4])
                    signature = message[4:signature_length+4]
                    data = message[signature_length+4:]
                    if self._key.verify(data,signature):
                        pass

                elif message_id == 10:  # seed version
                    (version) = struct.unpack("!L", message)
                    self._version_files_clb(self, version)
                elif message_id == 11:  # seed requested
                    self._me_requested_seed()
                elif message_id == 12:  # seed
                    self._get_seed(message)
                elif message_id == 13:  # peers request
                    self._me_requested_peers()
                elif message_id == 14:  # peers answer
                    self._get_peers(message)

                buffer = buffer[4 + message_len:]

    async def send_master_data(self, message_id: int, data: bytes):
        signature = self._key.sign(data)
        sig_size = len(signature)
        data_size = len(data)
        all_zise = data_size + sig_size
        query = struct.pack(f'!iBi{sig_size}s{data_size}s', all_zise+5,
                            message_id, sig_size, signature, data)

        await self._safe_write(query)
        self._last_message_time = time.time()

    async def send_slave_data(self, message_id: int, data: bytes):
        data_size = len(data)
        query = struct.pack(f'!iBi{data_size}s', data_size+5, message_id, data)

        await self._safe_write(query)
        self._last_message_time = time.time()

    def _me_requested(self, index:int, begin:int, lenght:int) -> None:
        if not self._data_taker_clb:
            return
        self._data_taker_clb(self, "request", index, begin, lenght)

    async def send_version_files(self, version: int):  # version is unix time
        data = struct.pack("!L", version)
        await self.send_master_data(10, data)

    async def send_piece(self, data: bytes, index: int, begin: int) -> None:
        query = struct.pack(f'!ibii{len(data)}s', 9+len(data), 7, index, begin, data)
        await self._safe_write(query)
        self._last_message_time = time.time()

    async def keep_alive(self) -> None:
        query = bytearray(b"\x00\x00\x00\x00")
        await self._safe_write(query)
        self._last_message_time = time.time()

    async def have(self, index: int) -> None:
        query = struct.pack(f'!ibi', 5, 4, index)
        await self._safe_write(query)
        self._last_message_time = time.time()

    async def interested(self) -> None:
        query = bytearray(b"\x00\x00\x00\x01\x02")
        await self._safe_write(query)
        self._am_interested = True
        self._last_message_time = time.time()

    async def uninterested(self) -> None:
        query = bytearray(b"\x00\x00\x00\x01\x03")
        await self._safe_write(query)
        self._am_interested = False
        self._last_message_time = time.time()

    async def choke(self) -> None:
        query = bytearray(b"\x00\x00\x00\x01\x00")
        await self._safe_write(query)
        self._am_choking = True
        self._last_message_time = time.time()

    async def unchoke(self) -> None:
        query = bytearray(b"\x00\x00\x00\x01\x01")
        await self._safe_write(query)
        self._am_choking = False
        self._last_message_time = time.time()

    async def send_bitfield(self, bitfield: BitField) -> None:
        query = struct.pack(f'!ibii{len(bitfield.bits)}s',
                            1 + 4 + 4 + len(bitfield.bits), 5, len(bitfield), bitfield.version, bitfield.bits)
        await self._safe_write(query)
        self._last_message_time = time.time()

    def receive_bitfield(self, bits_count, ver, bits):
        self._bitfield = BitField(bits_count, ver, bits)

    async def request(self, index: int, begin: int, length: int) -> bytes:
        future = asyncio.get_running_loop().create_future()
        self._requested_blocks[(index, begin,)] = (length, future,)

        query = struct.pack('!iB3i', 13, 6, index, begin, length)
        await self._safe_write(query)
        self._last_message_time = time.time()
        return await future

    async def cancel_piece(self, index:int, begin: int, length: int) -> None:
        if not (t := self._requested_blocks.get((index, begin,))): return
        length_d, future = t
        if not length_d == length:
            raise Exception("Bad length")
        future.cancel()
        self._requested_blocks.pop((index, begin,))

        query = struct.pack('!iB3i', 13, 8, index, begin, length)
        await self._safe_write(query)
        self._last_message_time = time.time()

    def reg_data_taker(self, clb) -> None:
        self._data_taker_clb = clb

    async def request_seed(self,):
        future = asyncio.get_running_loop().create_future()
        self._requested_seed_future = future

        query = struct.pack('!iB', 1, 11)
        await self._safe_write(query)
        self._last_message_time = time.time()
        return await future

    async def request_peers(self,):
        future = asyncio.get_running_loop().create_future()
        self._requested_peers_future = future

        query = struct.pack('!iB', 1, 13)
        await self._safe_write(query)
        self._last_message_time = time.time()
        return await future

    def _get_seed(self, message):
        s = Seed.decode(message)
        if self._requested_seed_future:
            self._requested_seed_future.set_result(s)
        self._requested_seed_future = None

    def _get_peers(self, message):
        s = BenCoder.decode(message)
        if self._requested_peers_future:
            self._requested_peers_future.set_result(s)
        self._requested_peers_future = None

    def _me_requested_seed(self):
        if not self._data_taker_clb:
            return
        self._data_taker_clb(self, "seed", 0, 0, 0)

    def _me_requested_peers(self):
        if not self._data_taker_clb:
            return
        self._data_taker_clb(self, "peers", 0, 0, 0)

    async def send_seed(self, seed: Seed):
        data = seed.encode()
        query = struct.pack(f'!ib{len(data)}s', 1+len(data), 12,  data)
        await self._safe_write(query)
        self._last_message_time = time.time()

    async def send_peers(self, peer_map):
        data = BenCoder.encode(peer_map)
        query = struct.pack(f'!ib{len(data)}s', 1+len(data), 14,  data)
        await self._safe_write(query)
        self._last_message_time = time.time()

    def _get_piece(self, index: int, begin: int, block: bytes) -> None:
        if not (t := self._requested_blocks.get((index, begin,))): return
        _, future = t

        future.set_result(block)
        self._requested_blocks.pop((index, begin,))

    def reg_version_files_clb(self, clb):  # (self, version)
        self._version_files_clb = clb

    async def _safe_write(self, data: bytes) -> None:
        # if self._stream_writer.is_closing():
        #     await self.disconnect()
        #     return
        try:
            self._stream_writer.write(data)
            await self._stream_writer.drain()
        except:
            await self.disconnect()
            return

    @classmethod
    def de_peer(cls, data) -> typing.Self:
        if isinstance(data, dict):
            if all([i in data.keys() for i in ("ip", 'port')]):
                return cls(ip=data['ip'], port=data['port'], peer_id=data.get('peer id'))
        if isinstance(data, list) or isinstance(data, tuple):
            if len(data) == 2:
                return cls(ip=data[0], port=data[1])

    def __repr__(self):
        return f"Peer {self.id if self.id else ''} {self.ip}:{self.port}"

    def __eq__(self, other):
        if self.ip == other.ip and self.port == other.port: return True
        return False

    def __hash__(self):
        return hash((self.ip, self.port))

    @classmethod
    def construct(cls, host:str, port: int, peer_id:int, reader, writer, key):
        peer = Peer(host, port, peer_id)
        peer._key = key
        peer._stream_reader = reader
        peer._stream_writer = writer
        peer._connected = True
        peer._am_choking = peer._peer_choking = True
        peer._am_interested = peer._peer_interested = False

        async def _keep_aliver():
            await asyncio.sleep(5)
            while True: # Norma
                if time.time() - peer._last_message_time >= 10 and not peer.am_choked:
                    await peer.keep_alive()
                await asyncio.sleep(1)

        peer._keep_aliver_task = asyncio.create_task(_keep_aliver())
        peer._last_message_time = time.time()

        return peer
