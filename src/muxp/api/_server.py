import socketserver
from typing import Tuple

from ..comm import Auth
from ..comm import encode_data
from ..comm import decode_data
from ..comm import ssl_server_context


class MuxHandler(socketserver.BaseRequestHandler):
    def handle(self):
        raw_sock = self.request
        buffer = b""
        while True:
            try:
                data = raw_sock.recv(4096)
                if not data:
                    break
                buffer += data
                messages, buffer = decode_data(buffer)
                for msg in messages:
                    response = self.server.handle_message(msg)
                    if response:
                        raw_sock.sendall(encode_data(response))
            except Exception as e:
                print(f"[!] 错误: {e}")
                break


class MuxpServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True

    def __init__(self, server_address: Tuple[str, int], auth: Auth, handler_func):
        context = ssl_server_context(auth)
        self.handle_message = handler_func
        super().__init__(server_address, MuxHandler)
        self.socket = context.wrap_socket(self.socket, server_side=True)


def run_server(address: Tuple[str, int], auth: Auth, handler_func):
    server = MuxpServer(address, auth, handler_func)
    print(f"[*] muxp 服务器监听在 {address[0]}:{address[1]}")
    server.serve_forever()

