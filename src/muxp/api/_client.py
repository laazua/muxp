import asyncio
import socket
import time
import traceback
import threading
from typing import Tuple, Optional, List
from ..comm import Auth, encode_data, decode_data, ssl_client_context

class Client:
    def __init__(self,
                 address: Tuple[str, int],
                 auth: Optional[Auth] = None,
                 timeout: float = 10.0,
                 auto_reconnect: bool = True,
                 max_reconnect_attempts: int = 3,
                 reconnect_delay: float = 1.0):
        self.address = address
        self.auth = auth
        self.timeout = timeout
        self.auto_reconnect = auto_reconnect
        self.max_reconnect_attempts = max_reconnect_attempts
        self.reconnect_delay = reconnect_delay
        self.context = ssl_client_context(auth)
        self.sock: Optional[socket.socket] = None
        self.buffer = b""
        self._connect_lock = threading.Lock()
        self._last_connect_time = 0
        self._min_reconnect_interval = 1.0
        self.connect()

    def connect(self):
        with self._connect_lock:
            current_time = time.time()
            if current_time - self._last_connect_time < self._min_reconnect_interval:
                time.sleep(self._min_reconnect_interval - (current_time - self._last_connect_time))
            if self.sock:
                try: self.sock.close()
                except: pass
                self.sock = None
            try:
                raw_sock = socket.create_connection(self.address, timeout=self.timeout)
                self.sock = raw_sock if not self.auth else self.context.wrap_socket(raw_sock, server_hostname=self.address[0])
                self.sock.settimeout(self.timeout)
                self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                self._last_connect_time = time.time()
                self.buffer = b""
            except Exception as e:
                self.sock = None
                raise ConnectionError(f"连接失败: {e}")

    def _reconnect_with_retry(self):
        if not self.auto_reconnect:
            raise ConnectionError("连接断开且自动重连已禁用")
        last_error = None
        for attempt in range(self.max_reconnect_attempts):
            try:
                if attempt > 0:
                    delay = self.reconnect_delay * (2 ** (attempt - 1))
                    time.sleep(delay)
                self.connect()
                return True
            except Exception as e:
                last_error = e
        raise ConnectionError(f"重连失败 ({self.max_reconnect_attempts} 次尝试): {last_error}")

    def _ensure_connected(self):
        if not self.sock:
            self._reconnect_with_retry()
        return True

    def send(self, data: bytes):
        if not self._ensure_connected(): raise ConnectionError("无法建立连接")
        encoded = encode_data(data)
        for attempt in range(self.max_reconnect_attempts + 1):
            try:
                if attempt > 0: self._reconnect_with_retry()
                self.sock.sendall(encoded)
                return
            except (socket.error, ConnectionError, OSError, BrokenPipeError) as e:
                if attempt < self.max_reconnect_attempts and self.auto_reconnect: continue
                else: raise ConnectionError(f"发送失败: {e}")

    def recv(self, timeout: Optional[float] = None) -> Optional[bytes]:
        if not self._ensure_connected(): return None
        original_timeout = self.sock.gettimeout()
        try:
            if timeout is not None: self.sock.settimeout(timeout)
            while True:
                try:
                    chunk = self.sock.recv(4096)
                    if not chunk:
                        if self.auto_reconnect:
                            self._reconnect_with_retry()
                            continue
                        return None
                    self.buffer += chunk
                    msgs, self.buffer = decode_data(self.buffer)
                    if msgs: return msgs[0]
                except socket.timeout: return None
        finally:
            if timeout is not None: self.sock.settimeout(original_timeout)

    def recv_all(self, timeout: Optional[float] = None) -> List[bytes]:
        if not self._ensure_connected(): return []
        messages = []
        original_timeout = self.sock.gettimeout()
        try:
            if timeout is not None: self.sock.settimeout(timeout)
            msgs, self.buffer = decode_data(self.buffer)
            messages.extend(msgs)
            try:
                chunk = self.sock.recv(4096)
                if chunk:
                    self.buffer += chunk
                    msgs, self.buffer = decode_data(self.buffer)
                    messages.extend(msgs)
            except socket.timeout: pass
        finally:
            if timeout is not None: self.sock.settimeout(original_timeout)
        return messages

    def close(self):
        if self.sock:
            try: self.sock.close()
            except: pass
            finally:
                self.sock = None
                self.buffer = b""

    def __enter__(self): return self
    def __exit__(self, exc_type, exc_val, exc_tb): self.close()


class AsyncClient:
    """异步客户端，可选 TLS/纯 TCP"""
    
    def __init__(self, address: Tuple[str, int], auth: Optional[Auth] = None,
                 timeout: float = 10.0, auto_reconnect: bool = False, max_reconnect_attempts: int = 3):
        self.address = address
        self.timeout = timeout
        self.auto_reconnect = auto_reconnect
        self.max_reconnect_attempts = max_reconnect_attempts
        self.ssl_ctx = ssl_client_context(auth) if auth else None
        
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.buffer = b""
        self._msg_queue: Optional[asyncio.Queue] = None
        self._recv_task: Optional[asyncio.Task] = None
        self._connected = False
        self._connect_lock = asyncio.Lock()
        self._recv_event = asyncio.Event()
    
    async def connect(self):
        async with self._connect_lock:
            if self._connected:
                return
            await self._close_internal()
            last_error = None
            for attempt in range(self.max_reconnect_attempts):
                try:
                    if attempt > 0:
                        delay = min(1.0 * (2 ** attempt), 10.0)
                        await asyncio.sleep(delay)
                    
                    self.reader, self.writer = await asyncio.wait_for(
                        asyncio.open_connection(
                            self.address[0],
                            self.address[1],
                            ssl=self.ssl_ctx,
                            server_hostname=self.address[0] if self.ssl_ctx else None
                        ),
                        timeout=self.timeout
                    )
                    
                    self._msg_queue = asyncio.Queue(maxsize=1000)
                    self._recv_event.clear()
                    self._connected = True
                    self._recv_task = asyncio.create_task(self._recv_loop())
                    return
                except Exception as e:
                    last_error = e
            raise ConnectionError(f"异步连接失败 ({self.max_reconnect_attempts} 次尝试): {last_error}")
    
    async def _ensure_connected(self):
        if not self._connected or (self._recv_task and self._recv_task.done()):
            await self.connect()
        return True
    
    async def _recv_loop(self):
        try:
            while self._connected and self.reader:
                try:
                    chunk = await asyncio.wait_for(self.reader.read(4096), timeout=self.timeout)
                    if not chunk:
                        break
                    self.buffer += chunk
                    msgs, self.buffer = decode_data(self.buffer)
                    for msg in msgs:
                        await self._msg_queue.put(msg)
                        self._recv_event.set()
                except asyncio.TimeoutError:
                    continue
                except Exception:
                    traceback.print_exc()
                    break
        finally:
            self._connected = False
    
    async def send(self, data: bytes):
        await self._ensure_connected()
        encoded = encode_data(data)
        self.writer.write(encoded)
        await self.writer.drain()
    
    async def recv(self, timeout: Optional[float] = None) -> Optional[bytes]:
        await self._ensure_connected()
        start = time.time()
        while True:
            if not self._msg_queue.empty():
                return await self._msg_queue.get()
            if timeout is not None and (time.time() - start) >= timeout:
                return None
            try:
                wait_time = 0.1
                if timeout:
                    wait_time = min(wait_time, timeout - (time.time() - start))
                await asyncio.wait_for(self._recv_event.wait(), timeout=wait_time)
                self._recv_event.clear()
            except asyncio.TimeoutError:
                continue
    
    async def _close_internal(self):
        self._connected = False
        self._recv_event.clear()
        if self._recv_task and not self._recv_task.done():
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                pass
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass
            finally:
                self.reader = None
                self.writer = None
        self.buffer = b""
        self._msg_queue = None
    
    async def close(self):
        async with self._connect_lock:
            await self._close_internal()
