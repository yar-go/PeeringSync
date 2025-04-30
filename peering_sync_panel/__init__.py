import argparse

from .app import run_app


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--panel-port", type=int, default=5000, help="he")
    parser.add_argument("--sock-path", type=str, default="/tmp/peeringsync.sock", help="sock storage")
    args, _ = parser.parse_known_args()
    return args


def run():
    args = get_args()
    panel_port = args.panel_port
    sock_path = args.sock_path
    run_app(panel_port, sock_path)