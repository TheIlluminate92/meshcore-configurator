"""Bounded TCP framing and awaited socket cleanup for Companion operations."""
import asyncio
from meshcore import TCPConnection


class ClosingTCPConnection(TCPConnection):
    MAX_FRAME = 300

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.closed = asyncio.Event()
        self.closing = False
        self.buffer = bytearray()
        self.pending = asyncio.Queue(maxsize=1024)
        self.worker = None

    class MCClientProtocol(TCPConnection.MCClientProtocol):
        def connection_made(self, transport):
            self.cx.closed.clear()
            super().connection_made(transport)

        def connection_lost(self, exc):
            self.cx.transport = None
            self.cx.closed.set()
            if not self.cx.closing:
                super().connection_lost(exc)

    async def connect(self):
        self.closing = False
        self.buffer.clear()
        return await super().connect()

    async def dispatch_frames(self):
        while not self.pending.empty():
            frame = self.pending.get_nowait()
            if self.reader is not None:
                await self.reader.handle_rx(frame)

    def fail_frame(self):
        self.buffer.clear()
        if self.transport is not None:
            self.transport.close()

    def handle_rx(self, data):
        if self.closing:
            return
        # Network delivery may coalesce hundreds of frames. Never recurse per
        # frame or create an unbounded collection of reader tasks.
        if len(data) + len(self.buffer) > 65536:
            self.fail_frame(); return
        self.buffer.extend(data)
        while self.buffer:
            marker = self.buffer.find(b'>')
            if marker < 0:
                self.buffer.clear(); return
            del self.buffer[:marker]
            if len(self.buffer) < 3:
                return
            length = int.from_bytes(self.buffer[1:3], 'little')
            if not 1 <= length <= self.MAX_FRAME:
                self.fail_frame(); return
            if len(self.buffer) < length + 3:
                return
            frame = bytes(self.buffer[3:3+length])
            del self.buffer[:3+length]
            try:
                self.pending.put_nowait(frame)
            except asyncio.QueueFull:
                self.fail_frame(); return
            self._receive_count += 1
            if self.worker is None or self.worker.done():
                self.worker = self._spawn_background(self.dispatch_frames())

    async def send(self, data):
        if self.closing or self.transport is None or self.transport.is_closing():
            raise ConnectionError('TCP connection closed. Reconnect and read the device.')
        if not 1 <= len(data) <= self.MAX_FRAME:
            raise ValueError('Invalid Companion frame length.')
        if self.transport.get_write_buffer_size() > 65536:
            self.fail_frame()
            raise ConnectionError('TCP peer stopped reading. Reconnect the device.')
        self.transport.write(b'<' + len(data).to_bytes(2, 'little') + data)

    async def disconnect(self):
        self.closing = True
        transport = self.transport
        if transport is not None:
            transport.close()
            try:
                await asyncio.wait_for(self.closed.wait(), 3)
            except asyncio.TimeoutError:
                transport.abort()
            finally:
                self.transport = None
        tasks = [task for task in self._background_tasks if task is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.buffer.clear()
        while not self.pending.empty():
            self.pending.get_nowait()
