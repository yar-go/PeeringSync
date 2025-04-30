import asyncio
import json
import os
import typing

if typing.TYPE_CHECKING:
    from networkmanager import NetworkManager

class UICominicator:
    def __init__(self, network_manager: 'NetworkManager', socket_path="/tmp/peeringsync.sock"):
        self.socket_path = socket_path
        self.server = None
        self.network_manager = network_manager

    async def start(self):
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)

        self.server = await asyncio.start_unix_server(
            self.handle_connection, path=self.socket_path
        )

        print(f"[+] Daemon listening on {self.socket_path}")
        try:
            await self.server.serve_forever()
        except asyncio.exceptions.CancelledError:
            pass

    async def stop(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            print("[+] Daemon stopped")
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)

    async def handle_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            data = await reader.read(4096)
            raw_command = data.decode().strip()

            print(f"[>] Received: {raw_command}")
            command, *args = raw_command.split("~")
            response = await self.dispatch_command(command.upper(), args)

            writer.write(response.encode() + b"\n")
            await writer.drain()
        except Exception as e:
            writer.write(f"ERROR: {str(e)}\n".encode())
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def dispatch_command(self, command: str, args: list[str]) -> str:
        # Роутинг команд
        if command == "CREATE_NETWORK":
            return await self.create_network(args)
        elif command == "IMPORT_NETWORK":
            return await self.import_network(args)
        elif command == "EXPORT_NETWORK":
            return await self.export_network(args)
        elif command == "DELETE_NETWORK":
            return await self.delete_network(args)
        elif command == "START_NETWORK":
            return await self.start_network(args)
        elif command == "STOP_NETWORK":
            return await self.stop_network(args)
        elif command == "ADD_PEERS":
            return await self.add_peers(args)
        elif command == "GET_INFO":
            return await self.get_info(args)
        elif command == "UPDATE_FILES":
            return await self.update_files(args)
        elif command == "OPEN_FOLDER":
            return await self.open_folder(args)
        else:
            return ""

    async def open_folder(self, args):
        net = args[0]
        s = self.network_manager.open_folder(net)
        r = "ok" if s else "no"
        return r

    async def update_files(self, args) -> str:
        net = args[0]
        await self.network_manager.update_files(net)
        return "ok"

    async def create_network(self, args) -> str:
        name = args[0]
        filepath = args[1]

        if len(args)>=3:
            peers = args[2].split(",")
        else: peers = list()
        i = self.network_manager.create_new_network(name, filepath, peers)
        return i

    async def import_network(self, args) -> str:
        name = args[0]
        keys = args[1]

        key_public, key_private = keys.rsplit('\n\n\n')
        key_private = key_private if key_private else ""

        filepath = args[2]
        if len(args)>=4:
            peers = args[3].split(",")
        else: peers = list()
        return self.network_manager.import_network(name, key_private, key_public, filepath, peers)

    async def export_network(self, args) -> str:
        net_id = args[0]
        pub, priv = self.network_manager.export_network_keys(net_id)
        return pub + "\n\n\n" + priv

    async def delete_network(self, args) -> str:
        net_id = args[0]
        await self.network_manager.stop_network(net_id)
        await self.network_manager.delete_network(net_id)
        return ""

    async def start_network(self, args) -> str:
        net_id = args[0]
        self.network_manager.start_network(net_id)
        return ""

    async def stop_network(self, args) -> str:
        net_id = args[0]
        await self.network_manager.stop_network(net_id)
        return "ok"

    async def add_peers(self, args) -> str:
        net_id = args[0]
        peers = args[1].split(",")
        self.network_manager.add_peers_network(net_id, peers)
        return ""

    async def get_info(self, _):
        r = self.network_manager.get_all_info()
        print(r)
        s = json.dumps(r)
        return s


# Запуск
# async def main():
#     daemon = UICominicator()
#     await daemon.start()
#
#     try:
#         while True:
#             await asyncio.sleep(3600)
#     except KeyboardInterrupt:
#         await daemon.stop()
#
# if __name__ == "__main__":
#     asyncio.run(main())
