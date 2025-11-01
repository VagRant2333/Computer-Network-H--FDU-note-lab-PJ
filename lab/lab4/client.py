import socket
import threading
import time
import hashlib
import os
import json
import argparse

def genPacket(seq: int, flag: int, ack: int, data: bytes, ts: float) -> bytes:
    dataLen = len(data)
    header = f"{seq}|{flag}|{ack}|{dataLen}|{ts}\n"
    return header.encode("utf-8") + data

def getPacket(data: bytes):
    sep = "\n".encode("utf-8")
    pacSep = data.find(sep)

    if pacSep == -1:
        return 0, 0, 0, b"", 0.0
    header = data[: pacSep].decode("utf-8")
    payload = data[pacSep + len(sep): ]
    headerSep: list = header.split("|")
    if len(headerSep) != 5:
        return 0, 0, 0, b"", 0
    seq = int(headerSep[0])
    flag = int(headerSep[1])
    ack = int(headerSep[2])
    payloadLen = int(headerSep[3])
    ts = float(headerSep[4])
    
    return seq, flag, ack, payload[: payloadLen], ts

def getMD5(path: str) -> str:
    md5 = hashlib.md5()
    chunkSize = 1024 * 1024
    with open(path, "rb") as f:
        while True:
            data = f.read(chunkSize)
            if not data:
                break
            md5.update(data)

    return md5.hexdigest()

class CongestControl: # virtual class, for reno and vegas
    def ifACK(self, ack: int, cwnd: float, rtt) -> float: # each function return cwnd
        raise NotImplemented
    
    def ifTimeout(self, cwnd: float) -> float:
        raise NotImplemented
    
    def ifDupACK(self, cwnd) -> float:
        raise NotImplemented
    
class renoControl(CongestControl):
    def __init__(self) -> None:
        self.ssthresh: float = 16.0

    def ifACK(self, ack: int, cwnd: float, rtt) -> float:
        if cwnd < self.ssthresh: # slow start
            cwnd = cwnd + 1.0
        else:
            cwnd = cwnd + 1.0 / cwnd
        return cwnd
    
    def ifTimeout(self, cwnd: float) -> float:
        self.ssthresh = cwnd / 2.0
        return 1.0
    
    def ifDupACK(self, cwnd) -> float:
        self.ssthresh = cwnd / 2.0
        return self.ssthresh

class vegasContol(CongestControl):
    def __init__(self, a: float = 1.0, b: float = 3.0) -> None:
        self.a = a
        self.b = b
        self.minRtt = None

    def ifACK(self, ack: int, cwnd: float, rtt) -> float:
        if rtt is None:
            return cwnd + 0.5
        if self.minRtt is None:
            self.minRtt = rtt
        else:
            self.minRtt = min(self.minRtt, rtt)
        
        excepted = cwnd / self.minRtt
        actual = cwnd / rtt
        diff = excepted - actual
        if diff < self.a:
            cwnd = cwnd + 1.0
        elif diff > self.b:
            cwnd = max(1.0, cwnd - 1.0)
        return cwnd
    
    def ifTimeout(self, cwnd: float) -> float:
        return cwnd / 2.0
    
    def ifDupACK(self, cwnd) -> float:
        return max(1.0, cwnd - 1.0)
    

class GBNreceiver:
    def __init__(self, socket: socket.socket, addr, outPath: str) -> None:
        self.socket = socket
        self.addr = addr
        self.outPath = outPath
    
    def receive(self):
        buffer = {}
        expect = 0
        with open(self.outPath, "wb") as f:
            while True:
                data, addr = self.socket.recvfrom(65546)
                seq, flag, ackNum, payload, ts = getPacket(data)
                
                if seq >= expect:
                    buffer[seq] = payload
                    while expect in buffer:
                        chunk = buffer.pop(expect)
                        if chunk:
                            f.write(chunk)
                        expect += 1
                    ackPkt = genPacket(0, (1 << 0), expect, "".encode("utf-8"), time.time())
                    self.socket.sendto(ackPkt, self.addr)
                else:
                    ackPkt = genPacket(0, (1 << 0), expect, "".encode("utf-8"), time.time())
                    self.socket.sendto(ackPkt, self.addr)
                if flag & (1 << 1):
                    ackPkt = genPacket(0, (1 << 0), expect, "".encode("utf-8"), time.time())
                    self.socket.sendto(ackPkt, self.addr)
                    break

class SRreceiver:
    def __init__(self, socket: socket.socket, addr, outPath: str):
        self.socket = socket
        self.addr = addr
        self.outPath = outPath
    
    def receive(self):
        buffer = {}
        expect = 0
        with open(self.outPath, "wb") as f:
            while True:
                data, addr  = self.socket.recvfrom(65536)
                seq, flag , ackNum, payload, ts = getPacket(data)
                ackPkt = genPacket(0, (1 << 0), seq + 1, "".encode("utf-8"), time.time())
                self.socket.sendto(ackPkt, self.addr)
                if seq >= expect:
                    buffer[seq] = payload
                    while expect in buffer:
                        chunk = buffer.pop(expect)
                        if chunk:
                            f.write(chunk)
                        expect += 1
                if flag & (1 << 1):
                    ackPkt = genPacket(0, (1 << 0), expect, "".encode("utf-8"), time.time())
                    self.socket.sendto(ackPkt, self.addr)
                    break

class GBNsender:
    def __init__(self, socket: socket.socket, addr, inPath: str, cc: CongestControl, pktSize: int, maxWin: int) -> None:
        self.socket = socket
        self.addr = addr
        self.inPath = inPath
        self.cc = cc
        self.pktSize = pktSize
        self.maxWin = maxWin
        self.timerLock = threading.Lock()
    

    def ackListener(self):
        while True:
            try:
                data, addr = self.socket.recvfrom(4096)
            except socket.timeout:
                continue
            seq, flag, ackNum, payload, ts = getPacket(data)
            if flag & (1 << 0):
                if ackNum > self.base:
                    self.base = ackNum
                    if ts > 0: 
                        rtt = (time.time() - ts)
                    else:
                        rtt = None
                    self.cwnd = self.cc.ifACK(ackNum, self.cwnd, rtt)
                    with self.timerLock:
                        if self.base != self.nextIdx:
                            self.timerStart = time.time()
                        else:
                            self.timerStart = None
                    self.dupACK = 0
                else:
                    self.dupACK += 1
                    if self.dupACK >= 3:
                        self.cwnd = self.cc.ifDupACK(self.cwnd)
                        self.dupACK = 0
            if self.base >= self.npkt:
                return

    def send(self):
        self.socket.settimeout(None)
        self.chunks: list = []
        with open(self.inPath, "rb") as f:
            while True:
                chunk = f.read(self.pktSize)
                if not chunk:
                    break
                self.chunks.append(chunk)

        unique_payload = sum(len(c) for c in self.chunks)
        total_sent = 0
        t0 = None

        self.npkt = len(self.chunks)
        self.base = 0
        self.nextIdx = 0
        self.cwnd = 1.0
        self.timeout = 0.5
        self.timerStart = None
        self.dupACK = 0

        listner = threading.Thread(target=self.ackListener, daemon=True)
        listner.start()

        while self.base < self.npkt:
            window = int(min(self.maxWin, max(1, int(self.cwnd))))
            while self.nextIdx < min(self.npkt, self.base + window):
                pkt = genPacket(self.nextIdx, 0, 0, self.chunks[self.nextIdx], time.time())
                self.socket.sendto(pkt, self.addr)

                if t0 is None:
                    t0 = time.time()
                total_sent += len(self.chunks[self.nextIdx])

                if self.base == self.nextIdx:
                    self.timerStart = time.time()
                self.nextIdx += 1
            
            with self.timerLock:
                tstart = self.timerStart
            if (tstart is not None) and ((time.time() - tstart) > self.timeout):
                self.cwnd = self.cc.ifTimeout(self.cwnd)
                for p in range(self.base, min(self.nextIdx, self.base + window)):
                    pkt = genPacket(p, 0, 0, self.chunks[p], time.time())
                    self.socket.sendto(pkt, self.addr)

                    total_sent += len(self.chunks[p])
                with self.timerLock:
                    self.timerStart = time.time()

        fin = genPacket(self.npkt, (1 << 1), 0, "".encode("utf-8"), time.time())
        self.socket.sendto(fin, self.addr)
        # while True:
        #     data, addr = self.socket.recvfrom(4096)
        #     seq, flag, ackNum, payload, ts = getPacket(data)
        #     if ackNum >= self.npkt and flag & (1 << 0):
        #         break
        self.socket.settimeout(2.0)
        while True:
            try:
                data, addr = self.socket.recvfrom(4096)
            except socket.timeout:
                if self.base >= self.npkt:
                    break
                else:
                    continue
            seq, flag, ackNum, payload, ts = getPacket(data)
            if (flag & (1 << 0)) and ackNum >= self.npkt:
                break
        
        if t0 is None:
            t0 = time.time()
        dt = max(1e-9, time.time() - t0)
        goodput_mbps = unique_payload * 8 / dt / 1e6
        utilization = (unique_payload / total_sent) if total_sent > 0 else 0.0
        print(f"METRIC,mode=gbn,goodput_mbps={goodput_mbps:.3f},utilization={utilization:.4f},seconds={dt:.3f}")


class SRsender:
    def __init__(self, socket: socket.socket, addr, inPath: str, cc: CongestControl, pktSize, maxWin):
        self.socket = socket
        self.addr = addr
        self.inPath = inPath
        self.cc = cc
        self.pktSize = pktSize
        self.maxWin = maxWin
    
    def ackListener(self):
        while True:
            try:
                data, addr = self.socket.recvfrom(4046)
            except socket.timeout:
                continue
            seq, flag, ackNum, payload, ts = getPacket(data)
            if flag & (1 << 0):
                idx = ackNum - 1
                if 0 <= idx < self.npkt:
                    self.acked.add(idx)
                    if ts > 0:
                        rtt = (time.time() - ts)
                    else:
                        rtt = None
                    self.cwnd = self.cc.ifACK(ackNum, self.cwnd, rtt)
                    while self.base in self.acked:
                        self.base += 1
            
            if self.base >= self.npkt:
                return
    
    def send(self):
        self.socket.settimeout(None)
        self.chunks: list = []
        with open(self.inPath, "rb") as f:
            while True:
                chunk = f.read(self.pktSize)
                if not chunk:
                    break
                self.chunks.append(chunk)

        unique_payload = sum(len(c) for c in self.chunks)
        total_sent = 0
        t01 = None
        
        self.npkt = len(self.chunks)
        self.base = 0
        self.nextIdx = 0
        self.sent: dict = {}
        self.acked: set = set()
        self.cwnd = 1.0
        self.timeout = 0.5
        self.timers: dict = {}

        listener = threading.Thread(target=self.ackListener, daemon=True)
        listener.start()

        while self.base < self.npkt:
            window = int(min(self.maxWin, max(1, int(self.cwnd))))
            while self.nextIdx < self.npkt and self.nextIdx < self.base + window:
                pkt = genPacket(self.nextIdx, 0, 0, self.chunks[self.nextIdx], time.time())
                self.socket.sendto(pkt, self.addr)

                if t01 is None:
                    t01 = time.time()
                total_sent += len(self.chunks[self.nextIdx])
                
                self.sent[self.nextIdx] = pkt
                self.timers[self.nextIdx] = time.time()
                self.nextIdx += 1
            
            now = time.time()
            for idx in list(self.sent.keys()):
                if idx in self.acked:
                    self.sent.pop(idx)
                    self.timers.pop(idx)
            for idx, t0 in list(self.timers.items()):
                if now - t0 > self.timeout and idx not in self.acked:
                    self.cwnd = self.cc.ifTimeout(self.cwnd)
                    pkt = genPacket(idx, 0, 0, self.chunks[idx], time.time())
                    self.socket.sendto(pkt, self.addr)

                    total_sent += len(self.chunks[idx])

                    self.timers[idx] = time.time()
            
        fin = genPacket(self.npkt, (1 << 1), 0, "".encode("utf-8"), time.time())
        self.socket.sendto(fin, self.addr)
        # while True:
        #     data, addr = self.socket.recvfrom(4096)
        #     seq, flag, ackNum, payload, ts = getPacket(data)
        #     if flag & (1 << 0) and ackNum >= self.npkt:
        #         break
        print("client: waiting for FIN-ACK")
        self.socket.settimeout(2.0)
        while True:
            try:
                data, addr = self.socket.recvfrom(4096)
            except socket.timeout:
                if self.base >= self.npkt:
                    break
                else:
                    continue
            seq, flag, ackNum, payload, ts = getPacket(data)
            if (flag & (1 << 0)) and ackNum >= self.npkt:
                break
        
        if t01 is None:
            t01 = time.time()
        dt = max(1e-9, time.time() - t01)
        goodput_mbps = unique_payload * 8 / dt / 1e6
        utilization = (unique_payload / total_sent) if total_sent > 0 else 0.0
        print(f"METRIC,mode=sr,goodput_mbps={goodput_mbps:.3f},utilization={utilization:.4f},seconds={dt:.3f}")
        

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", type=str, required=True)
    parser.add_argument("--port", type=int, default=10000)
    parser.add_argument("--arq", type=str, choices=["gbn", "sr"], default="gbn")
    parser.add_argument("--cc", type=str, choices=["reno", "vegas"], default="reno")
    parser.add_argument("--pktSize", type=int, default=1024)
    parser.add_argument("--maxWin", type=int, default=64)

    sub = parser.add_subparsers(dest="operation", required=True)
    up = sub.add_parser("upload")
    up.add_argument("localPath", type=str)
    up.add_argument("remoteName", type=str)
    dl=sub.add_parser("download")
    dl.add_argument("localPath", type=str)
    dl.add_argument("remoteName", type=str)
    args = parser.parse_args()

    socketControl = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    socketControl.settimeout(10.0)
    req = {}
    if args.operation == "upload":
        if not os.path.exists(args.localPath):
            print(f"client: no such local file")
            return
        req = {
            "cmd": f"upload {os.path.basename(args.localPath)}",
            "arq": args.arq,
            "cc": args.cc,
            "remoteName": args.remoteName,
            "pktSize": args.pktSize,
            "maxWin": args.maxWin
        }
    else:
        req = {
            "cmd": f"download {args.remoteName}",
            "arq": args.arq,
            "cc": args.cc,
            "remoteName": args.remoteName,
            "pktSize": args.pktSize,
            "maxWin": args.maxWin
        }
    socketControl.sendto(json.dumps(req).encode(), (args.server, args.port))
    data, curAddr = socketControl.recvfrom(4096)
    resp = json.loads(data.decode())
    if resp.get("status") != "ok":
        print(f"client: failed to connect", resp)
        return
    dataPort = resp["dataPort"]
    socketData = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    socketData.bind(("", 0))
    serverAddr = (args.server, dataPort)
    if args.cc == "reno":
        cc = renoControl()
    else:
        cc = vegasContol()
    if args.operation == "upload":
        if args.arq == "gbn":
            sender = GBNsender(socketData, serverAddr, args.localPath, cc, args.pktSize, args.maxWin)
        else:
            sender = SRsender(socketData, serverAddr, args.localPath, cc, args.pktSize, args.maxWin)
        sender.send()

        data, curAdd = socketControl.recvfrom(4096)
        resp = json.loads(data.decode())
        serverMD5 = resp.get("md5")
        localMD5 = getMD5(args.localPath)
        print(f"client: local MD5 = {localMD5} | server MD5 = {serverMD5}")
        if localMD5 != serverMD5:
            print(f"upload failed, exiting")
            os._exit(1)
        print("client: successfully upload")
    else:
        if args.arq == "gbn":
            receiver = GBNreceiver(socketData, serverAddr, args.localPath)
        else:
            receiver = SRreceiver(socketData, serverAddr, args.localPath)
        receiver.receive()

        data, ad = socketControl.recvfrom(4096)
        resp = json.loads(data.decode())
        serverMD5 = resp.get("md5")
        localMD5 = getMD5(args.localPath)
        print(f"client: local MD5 = {localMD5} | server MD5 = {serverMD5}")
        if serverMD5 != localMD5:
            print("download failed, exiting")
            os._exit(1)
        print("client: successfully download")




if __name__ == "__main__":
    main()
