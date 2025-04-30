import asyncio
import inspect
import struct

from .peer import Peer


class ConnectionReceiver:
    def __init__(self, host:str, port:int, peer_id:bytes):
        self.__host = host
        self.__port = port
        self.__peer_id = peer_id
        self.__clb_networks_keys = None  # (void) -> list(active_keys)
        self.__clb_peer_connected = None  # (network_identifier, Peer) -> void
        self.__srv = None
        self.__working_state = False

    @property
    def is_working(self) -> bool:
        return self.__working_state

    @property
    def address(self) -> str:
        return f"{self.__host}:{self.__port}"

    async def listen(self):
        self.__working_state = True
        self.__srv = await asyncio.start_server(self.__peer_connected, self.__host, self.__port)
        try:
            await self.__srv.serve_forever()
        except asyncio.exceptions.CancelledError:
            self.__working_state = False

    async def stop(self):
        self.__srv.close()
        await self.__srv.wait_closed()

    async def __peer_connected(self, reader, writer):
        try:
            r = await reader.read(81)
        except:
            await self.__safe_close(writer)
            return

        if not r or len(r) < 80: return
        _, r_pstr, r_reversed, r_info_hash, r_peer_id = struct.unpack(f"!B{len(r) - 61}s8s32s20s", r)

        pstr = bytearray(b"PeeringSync protocol")
        if not pstr == r_pstr:
            await self.__safe_close(writer)
            return

        if not self.__clb_networks_keys:
            await self.__safe_close(writer)
            return

        key = None
        for k in self.__clb_networks_keys():
            if k.network_identifier == r_info_hash:
                key = k
                break
        if key is None:
            await self.__safe_close(writer)
            return

        host, port = writer.get_extra_info("peername")
        p = Peer.construct(host, port, r_peer_id, reader, writer, key)

        handshake = struct.pack(f"!B{len(pstr)}s8s32s20s",
                                len(pstr), pstr, bytearray(8),
                                r_info_hash, self.__peer_id)
        try:
            await self.__safe_write(handshake, writer)
        except:
            return

        if self.__clb_peer_connected:
            self.__clb_peer_connected(r_info_hash, p)

    def reg_clb_networks_getter(self, clb):
        self.__clb_networks_keys = clb

    def reg_clb_peer_connected(self, clb):
        self.__clb_peer_connected = clb

    async def __safe_write(self, data: bytes, writer_stream) -> bool:
        try:
            writer_stream.write(data)
            await writer_stream.drain()
            return True
        except:
            writer_stream.close()
            await writer_stream.wait_closed()
            return False

    async def __safe_close(self, writer):
        try:
            writer.close()
            await writer.wait_closed()
        except:
            pass
