import socket
import socketserver
from typing import Tuple

from ..comm import Auth, encode_data, decode_data, ssl_server_context

MAX_BUFFER = 4 * 1024 * 1024   # 4MB 上限防止恶意攻击


class MuxHandler(socketserver.BaseRequestHandler):

    def handle(self):
        raw_sock = self.request
        raw_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        raw_sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

        buffer = b""

        while True:
            try:
                data = raw_sock.recv(4096)
                if not data:
                    break

                buffer += data
                if len(buffer) > MAX_BUFFER:
                    print("[!] 连接被关闭：缓冲区过大，可能存在攻击风险")
                    break

                messages, buffer = decode_data(buffer)

                for msg in messages:
                    try:
                        response = self.server.handle_message(msg)
                        if response:
                            raw_sock.sendall(encode_data(response))
                    except Exception as e:
                        print(f"[!] 业务处理异常: {e}")

            except ConnectionResetError:
                print("[*] 客户端主动断开")
                break
            except Exception as e:
                print(f"[!] Socket 错误: {e}")
                break


class MuxpServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True

    # 限制最大线程数，否则 ThreadingMixIn 默认无限制
    daemon_threads = True  # 避免 zombie 线程

    def __init__(self, server_address: Tuple[str, int], auth: Auth, handler_func):
        self.auth = auth
        self.handle_message = handler_func
        super().__init__(server_address, MuxHandler)

    def server_bind(self):
        """重写 server_bind 以使用 SSL 包装"""
        context = ssl_server_context(self.auth)

        sock = socket.socket(self.address_family, self.socket_type)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # 更安全
        self.socket = context.wrap_socket(sock, server_side=True, do_handshake_on_connect=True)

        self.socket.bind(self.server_address)
        self.server_address = self.socket.getsockname()
        self.socket.listen(self.request_queue_size)


def run_server(address: Tuple[str, int], auth: Auth, handler_func):
    server = MuxpServer(address, auth, handler_func)
    print(f"[*] muxp 服务器监听在 {address[0]}:{address[1]}")
    server.serve_forever()
