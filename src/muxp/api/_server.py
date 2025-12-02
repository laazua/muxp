import enum
import logging
import socket
import socketserver
import asyncio
import traceback
import threading
from typing import Tuple, Callable, Optional
from concurrent.futures import ThreadPoolExecutor
from ..comm import Auth, encode_data, decode_data, ssl_server_context


logger = logging.getLogger('mux')
# 设置日志级别
logger.setLevel(logging.DEBUG)
# 创建控制台处理器
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
# 创建格式化器
formatter = logging.Formatter(
    '%(asctime)s | %(name)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
# 为处理器设置格式化器
console_handler.setFormatter(formatter)
# 为日志器添加处理器
logger.addHandler(console_handler)
# 避免日志向上传播（防止重复记录）
logger.propagate = False


###############################################################################
# 运行模式
###############################################################################

class Mode(enum.Enum):
    THREADING = "threading"
    THREADPOOL = "threadpool"
    ASYNCIO = "asyncio"

###############################################################################
# 常量
###############################################################################

MAX_BUFFER_SIZE = 4 * 1024 * 1024  # 最大缓冲区，防止 buffer 攻击

###############################################################################
# 通用请求处理器
###############################################################################

class MuxHandler(socketserver.BaseRequestHandler):
    """所有模式通用的请求处理器"""
    
    def setup(self):
        sock = self.request
        sock.settimeout(30)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    
    def handle(self):
        sock = self.request
        buffer = b""
        
        while True:
            try:
                data = sock.recv(4096)
                if not data:
                    break
                buffer += data
                if len(buffer) > MAX_BUFFER_SIZE:
                    logger.warning("[!] buffer too large, closing")
                    break
                msgs, buffer = decode_data(buffer)
                for msg in msgs:
                    try:
                        resp = self.server.handle_message(msg)
                        if resp is not None:
                            sock.sendall(encode_data(resp))
                    except Exception as be:
                        logger.error(f"[业务异常] {be}")
                        traceback.print_exc()
            except socket.timeout:
                break
            except ConnectionResetError:
                break
            except Exception as e:
                logger.error(f"[socket error] {e}")
                traceback.print_exc()
                break

###############################################################################
# 基础服务器类
###############################################################################

class BaseMuxpServer:
    """所有服务器实现的公共基类"""
    
    allow_reuse_address = True
    
    def __init__(self, addr, handler_func: Callable, auth: Optional[Auth] = None):
        self.auth = auth
        self.handle_message = handler_func
        super().__init__(addr, MuxHandler)
    
    def server_bind(self):
        ctx = ssl_server_context(self.auth)
        raw = socket.socket(self.address_family, self.socket_type)
        raw.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        if hasattr(socket, 'SO_KEEPALIVE'):
            raw.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        
        self.socket = raw if not self.auth else ctx.wrap_socket(raw, server_side=True)
        self.socket.bind(self.server_address)
        self.socket.listen(self.request_queue_size)
        self.server_address = self.socket.getsockname()

###############################################################################
# 1) ThreadingMixIn 服务器
###############################################################################

class ThreadingMuxpServer(socketserver.ThreadingMixIn, BaseMuxpServer, socketserver.TCPServer):
    """使用 threading 模型的服务器"""
    
    daemon_threads = True
    
    def __init__(self, addr, handler_func: Callable, auth: Optional[Auth] = None):
        super().__init__(addr, handler_func, auth)
        logger.info(f"[*] ThreadingMixIn 服务器已初始化，最大线程数受限于系统")

###############################################################################
# 2) ThreadPool 服务器（生产环境推荐）
###############################################################################

class ThreadPoolMixIn:
    """使用 ThreadPoolExecutor 处理请求"""
    
    max_workers = 200
    max_pending = 1000
    _pool: Optional[ThreadPoolExecutor] = None
    _pool_lock = threading.Lock()
    _pending_count = 0
    _pending_lock = threading.Lock()
    
    def _ensure_pool(self):
        if self._pool is None:
            with self._pool_lock:
                if self._pool is None:
                    self._pool = ThreadPoolExecutor(max_workers=self.max_workers)
                    logger.info(f"[*] 线程池已创建，最大工作线程数: {self.max_workers}")
    
    def process_request(self, request, client_address):
        with self._pending_lock:
            if self._pending_count >= self.max_pending:
                try:
                    request.close()
                except:
                    pass
                logger.warning(f"[!] 连接队列已满，拒绝连接 {client_address}")
                return
            self._pending_count += 1
        
        self._ensure_pool()
        self._pool.submit(self._process_request_worker, request, client_address)
    
    def _process_request_worker(self, request, client_address):
        try:
            self.finish_request(request, client_address)
        except Exception:
            try:
                self.handle_error(request, client_address)
            except Exception:
                traceback.print_exc()
        finally:
            with self._pending_lock:
                self._pending_count -= 1
            try:
                self.shutdown_request(request)
            except Exception:
                traceback.print_exc()
    
    def server_close(self):
        if self._pool:
            try:
                logger.info("[*] 正在关闭线程池...")
                self._pool.shutdown(wait=True)
            except Exception as e:
                logger.error(f"[!] 关闭线程池出错: {e}")
            finally:
                self._pool = None
        try:
            super().server_close()
        except AttributeError:
            pass
    
    def shutdown(self):
        try:
            super().shutdown()
        except AttributeError:
            pass
        finally:
            self.server_close()

class ThreadPoolMuxpServer(ThreadPoolMixIn, BaseMuxpServer, socketserver.TCPServer):
    """使用线程池的服务器"""
    
    def __init__(self, addr, handler_func: Callable, auth: Optional[Auth] = None):
        super().__init__(addr, handler_func, auth)
        logger.info(f"[*] ThreadPool 服务器已初始化，最大线程数: {self.max_workers}, 最大等待队列: {self.max_pending}")

###############################################################################
# 3) asyncio + TLS 服务器（高性能）
###############################################################################

class AsyncioMuxpServer:
    """异步高性能服务端，可选 TLS/纯 TCP"""
    
    def __init__(self, addr: Tuple[str, int], handler_func: Callable, auth: Optional[Auth] = None):
        self.addr = addr
        self.auth = auth
        self.handle_message = handler_func
        self.ssl_ctx = ssl_server_context(auth) if auth else None
        self._server: Optional[asyncio.AbstractServer] = None
    
    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        buffer = b""
        peer = writer.get_extra_info("peername")
        try:
            while True:
                try:
                    data = await asyncio.wait_for(reader.read(4096), timeout=30.0)
                    if not data:
                        break
                    buffer += data
                    if len(buffer) > MAX_BUFFER_SIZE:
                        break
                    msgs, buffer = decode_data(buffer)
                    for msg in msgs:
                        try:
                            resp = self.handle_message(msg)
                            if resp:
                                writer.write(encode_data(resp))
                                await writer.drain()
                        except Exception:
                            traceback.print_exc()
                except asyncio.TimeoutError:
                    continue
        except Exception:
            traceback.print_exc()
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
    
    async def start(self):
        self._server = await asyncio.start_server(
            self.handle_client,
            self.addr[0],
            self.addr[1],
            ssl=self.ssl_ctx,
            reuse_address=True,
        )
        mode = "TLS" if self.ssl_ctx else "TCP"
        logger.info(f"[*] asyncio muxp {mode} 服务器监听在 {self.addr}")
        async with self._server:
            await self._server.serve_forever()
    
    def close(self):
        if self._server and self._server.is_serving():
            self._server.close()

###############################################################################
# 统一入口
###############################################################################

def run(
    address: Tuple[str, int],
    handler_func: Callable,
    mode: Mode = Mode.THREADING,
    auth: Optional[Auth] = None,
):
    if mode == Mode.THREADING:
        logger.info(f"[*] 使用 ThreadingMixIn 启动 muxp 服务器 {address}")
        srv = ThreadingMuxpServer(address, handler_func, auth)
        srv.serve_forever()
    elif mode == Mode.THREADPOOL:
        logger.info(f"[*] 使用 ThreadPoolExecutor 启动 muxp 服务器 {address}")
        srv = ThreadPoolMuxpServer(address, handler_func, auth)
        srv.serve_forever()
    elif mode == Mode.ASYNCIO:
        logger.info(f"[*] 使用 asyncio + TLS 启动 muxp 服务器 {address}")
        server = AsyncioMuxpServer(address, handler_func, auth)
        asyncio.run(server.start())
    else:
        raise ValueError(f"未知模式：{mode}")
