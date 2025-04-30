import argparse
import asyncio
import random
import signal

from .networkmanager import NetworkManager
from .connectionreciever import  ConnectionReceiver
from .uicomunicator import UICominicator
from .keysmanager import KeysManager
from .database import Database


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("host", help="the listhening host")
    parser.add_argument("port", help="the listhening port")
    parser.add_argument("--db-name", type=str, default="PeeringSync.db", help="metainfo db")
    parser.add_argument("--keys-path", type=str, default="./keys", help="keys storage")
    parser.add_argument("--sock-path", type=str, default="/tmp/peeringsync.sock", help="sock storage")

    args, _ = parser.parse_known_args()
    return args


async def run():
    global networkmanager,connectionreciever, uicomunicator, tasks
    args = get_args()

    host = args.host
    port = args.port
    db_name = args.db_name
    keys_path = args.keys_path
    sock_path = args.sock_path

    peer_id = b"-PS0001-" + bytes([random.randint(48, 57) for _ in range(12)])

    km = KeysManager(keys_path)
    db = Database(db_name)
    db.create_tables(db_name)

    networkmanager = NetworkManager(km,db, peer_id, f"{host}:{port}")
    connectionreciever = ConnectionReceiver(host, port, peer_id)
    uicomunicator = UICominicator(networkmanager, sock_path)

    connectionreciever.reg_clb_networks_getter(networkmanager.get_working_network_ids)
    connectionreciever.reg_clb_peer_connected(networkmanager.add_outter_peer)

    tasks = list()
    tasks.append(asyncio.Task(uicomunicator.start()))
    tasks.append(asyncio.Task(connectionreciever.listen()))

class ShutdownException(SystemExit):
    pass


def sigint_clb():
    raise ShutdownException()


def main():
    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGINT, sigint_clb)

    async def shutdown():
        await networkmanager.stop_all()
        await uicomunicator.stop()
        await connectionreciever.stop()

        await asyncio.gather(*tasks)

    try:
        loop.run_until_complete(run())
        loop.run_forever()
    except ShutdownException:
        loop.run_until_complete(shutdown())

