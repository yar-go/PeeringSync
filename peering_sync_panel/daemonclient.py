import socket

class DaemonSocketClient:
    def __init__(self, socket_path="/tmp/mydaemon.sock"):
        self.socket_path = socket_path

    def send_command(self, command: str) -> str:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client_socket:
            client_socket.connect(self.socket_path)
            client_socket.sendall((command).encode())

            response = b""
            while True:
                r = client_socket.recv(1024)
                if r: response += r
                else: break

            return response.decode().strip()

