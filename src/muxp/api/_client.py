import socket
from typing import Tuple

from ..comm import Auth
from ..comm import encode_data
from ..comm import decode_data
from ..comm import ssl_client_context


class MuxpClient:
    def __init__(self,address: Tuple[str, int], auth: Auth):
        self.context = ssl_client_context(auth)
        raw_sock = socket.create_connection(address)
        self.sock = self.context.wrap_socket(raw_sock, server_hostname=address[0])
        self.buffer = b""

    def send(self, data: bytes):
        self.sock.sendall(encode_data(data))

    def recv(self) -> bytes|None:
        messages: list[bytes] = []
        while True:
            try:
                data = self.sock.recv(4096)
                if not data:
                    break
                self.buffer += data
                messages, self.buffer = decode_data(self.buffer)
                if messages:
                    return messages[0]
            except Exception as e:
                print(f"[!] 错误: {e}")

    def close(self):
        self.sock.close()
