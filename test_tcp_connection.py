import asyncio
import unittest
from tcp_connection import ClosingTCPConnection


class TCPChecks(unittest.IsolatedAsyncioTestCase):
    async def test_real_socket_fragmented_order_and_awaited_close(self):
        received=[]; frames=[]; peer_closed=asyncio.Event()
        async def serve(reader,writer):
            received.append(await reader.readexactly(4))
            for piece in (b'>',b'\x02\0a',b'b>\x01\0c'):
                writer.write(piece); await writer.drain(); await asyncio.sleep(0)
            await reader.read(); peer_closed.set(); writer.close(); await writer.wait_closed()
        server=await asyncio.start_server(serve,'127.0.0.1',0)
        cx=ClosingTCPConnection('127.0.0.1',server.sockets[0].getsockname()[1])
        class Reader:
            async def handle_rx(self,frame): frames.append(frame)
        cx.set_reader(Reader())
        try:
            await cx.connect(); await cx.send(b'x')
            for _ in range(100):
                if len(frames)==2: break
                await asyncio.sleep(.01)
            self.assertEqual(frames,[b'ab',b'c'])
            self.assertEqual(received,[b'<\x01\0x'])
            await cx.disconnect(); await asyncio.wait_for(peer_closed.wait(),1)
            self.assertIsNone(cx.transport)
            with self.assertRaises(ConnectionError): await cx.send(b'x')
            await cx.disconnect()
        finally:
            await cx.disconnect(); server.close(); await server.wait_closed()

    async def test_coalesced_flood_is_bounded_without_recursion(self):
        cx=ClosingTCPConnection('unused',5000)
        closed=[]
        class Transport:
            def close(self): closed.append(True)
        cx.transport=Transport(); cx.reader=None
        cx.handle_rx(b'>\x01\0x'*5000)
        self.assertTrue(closed)
        self.assertLessEqual(cx.pending.qsize(),1024)
        cx.transport=None
        await cx.disconnect()

    async def test_invalid_lengths_close_without_delivering(self):
        for header in (b'>\0\0', b'>\xff\xff'):
            cx=ClosingTCPConnection('unused',5000); closed=[]
            class Transport:
                def close(self): closed.append(True)
            cx.transport=Transport(); cx.reader=None
            cx.handle_rx(header)
            self.assertTrue(closed); self.assertTrue(cx.pending.empty())
            cx.transport=None; await cx.disconnect()

    async def test_large_contact_response_and_random_fragmentation(self):
        import random
        randomizer=random.Random(20260915)
        expected=[bytes(randomizer.randrange(256) for _ in range(176)) for _ in range(350)]
        wire=b''.join(b'>'+len(frame).to_bytes(2,'little')+frame for frame in expected)
        for fragmented in (False,True):
            cx=ClosingTCPConnection('unused',5000); got=[]
            class Reader:
                async def handle_rx(self,frame): got.append(frame)
            cx.set_reader(Reader())
            if fragmented:
                offset=0
                while offset<len(wire):
                    size=randomizer.randint(1,1200); cx.handle_rx(wire[offset:offset+size]); offset+=size
            else:
                cx.handle_rx(wire)
            await cx.worker
            self.assertEqual(got,expected)
            await cx.disconnect()
