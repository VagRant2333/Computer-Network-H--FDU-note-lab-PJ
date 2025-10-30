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
    headerSep: list = header.split("\n")
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

class receiver: # virtual class, for GBN and SR
    def __init__(self, socket: socket.socket, addr, outPath: str, mode, pktSize: int) -> None:
        self.socket = socket
        self.addr = addr
        self.outPath = outPath
        self.mode = mode
        self.pktSize = pktSize
        self.filelock = threading.Lock()
    
    def handle(self) :
        raise NotImplementedError
    

class GBNreceiver(receiver):
    def handle(self):
        expect = 0
        with open(self.outPath, "wb") as f:
            while True:
                data, addr1 = self.socket.recvfrom(65536)
                seq, flag, ack, payload, ts = getPacket(data)
                ackFlag = 1 << 0
                if seq == expect:
                    if payload:
                        f.write(payload)
                        expect += 1
                    ackPacket = genPacket(0, ackFlag, expect, "".encode("utf-8"), time.time())
                    self.socket.sendto(ackPacket, self.addr)
                else:
                    ackPacket = genPacket(0, ackFlag, expect, "".encode("utf-8"), time.time())
                    self.socket.sendto(ackPacket, self.addr)
                if flag & (1 << 1):
                    ackPacket = genPacket(0, ackFlag, expect, "".encode("utf-8"), time.time())
                    self.socket.sendto(ackPacket, self.addr)
                    break

class SRRreveiver(receiver):
    def handle(self):
        packetBuff: dict = {}
        expect = 0
        with open(self.outPath, "wb") as f:
            while True:
                data, addr1 = self.socket.recvfrom(65536)
                seq, flag, ack, payload, ts = getPacket(data)
                ackFlag = 1 << 0
                ackPacket = genPacket(0, ackFlag, seq + 1, b"", time.time())
                self.socket.sendto(ackPacket, self.addr)
                if seq >= expect:
                    packetBuff[seq] = payload
                    while expect in packetBuff:
                        chunk = packetBuff.pop(expect)
                        if chunk:
                            f.write(chunk)
                        expect += 1
                
                if flag & (1 << 1):
                    ackPacket = genPacket(0, ackFlag, expect, b"", time.time())
                    self.socket.sendto(ackPacket, self.addr)
                    break

class sender:
    def __init__(self, socket: socket.socket, addr, inPath: str, mode: str, cc: CongestControl, pktSize: int, maxWin: int) -> None:
        self.socket = socket
        self.addr = addr
        self.inPath = inPath
        self.mode = mode
        self.cc = cc
        self.pktSize = pktSize
        self.maxWin = maxWin
        self.lock = threading.Lock()

    def send(self) -> None:
        raise NotImplemented

class GBNsender(sender):

    def ackListen(self):
        while True:
            data, recAddr = self.socket.recvfrom(2048)
            seq, flag, ackNum, payload, ts = getPacket(data)
            if flag & (1 << 0):
                now = time.time()
                if ts > 0:
                    rtt = (now - ts)
                else:
                    rtt = None
                with self.ackLock:
                    if ackNum > self.base:
                        self.base = ackNum
                        self.cwnd = self.cc.ifACK(ackNum, self.cwnd, rtt)
                        if self.base != self.nextSeq:
                            self.timerStart = time.time()
                        else:
                            self.timerStart = None
                    else:
                        self.dupACKcount += 1
                        if self.dupACKcount >= 3:
                            self.cwnd = self.cc.ifDupACK(self.cwnd)
                            self.dupACKcount = 0
                            if self.base < self.npkt:
                                pkt = genPacket(self.base, 0, 0, self.chunks[self.base], time.time())
                                self.socket.sendto(pkt, self.addr)
                                self.timerStart = time.time()
            if self.base >= self.npkt:
                return

    def send(self):
        self.chunks: list = []
        with open(self.inPath, "rb") as f:
            while True:
                cur = f.read(self.pktSize)
                if not cur:
                    break
                self.chunks.append(cur)
        self.npkt = len(self.chunks)
        self.base = 0
        self.nextSeq = 0
        self.cwnd = 1.0
        self.timeout = 0.5
        self.timerStart = None
        self.dupACKcount = 0
        self.ackLock = threading.Lock()

        listener = threading.Thread(target=self.ackListen, daemon=True)
        listener.start()

        while self.base < self.npkt:
            window = int(min(self.maxWin, max(1, int(self.cwnd))))
            while self.nextSeq < min(self.base + window, self.npkt):
                pkt = genPacket(self.nextSeq, 0, 0, self.chunks[self.nextSeq], time.time())
                self.socket.sendto(pkt, self.addr)
                if self.base == self.nextSeq:
                    self.timerStart = time.time()
                self.nextSeq += 1
            if self.timerStart and (time.time() - self.timerStart) > self.timeout:
                self.cwnd = self.cc.ifTimeout(self.cwnd)
                for p in range(self.base, min(self.nextSeq, self.base + window)): # resend base -> nexSeq-1
                    pkt = genPacket(p, 0, 0, self.chunks[p], time.time())
                    self.socket.sendto(pkt, self.addr)
                self.timerStart = time.time()
        finPkt = genPacket(self.npkt, (1 << 1), 0, "".encode("utf-8"), time.time())
        self.socket.sendto(finPkt, self.addr)

        while True:
            data, recAddr = self.socket.recvfrom(2048)
            seq, flag, ackNum, payload, ts = getPacket(data)
            if flag & (1 << 0) and ackNum > self.npkt:
                break


class SRsender(sender):
    def ackListen(self):
        while True:
            data, revAddr = self.socket.recvfrom(2048)
            seq, flag, ackNum, payload, ts = getPacket(data)
            if flag & (1 << 0):
                idx = ackNum - 1
                if 0 <= idx < self.npkt:
                    with self.ackLock:
                        self.acked.add(idx)
                        if ts > 0:
                            rtt = (time.time() - ts)
                        else:
                            rtt = None
                        self.cwnd = self.cc.ifACK(ackNum, self.cwnd, rtt)
                        while self.base in self.acked:
                            self.base += 1
            if self.base >= self.npkt:
                break
    
    def send(self):
        self.chunks: list = []
        with open(self.inPath, "rb") as f:
            while True:
                p = f.read(self.pktSize)
                if not p:
                    break
                self.chunks.append(p)
        
        self.npkt = len(self.chunks)
        self.base = 0
        self.sent: dict = {}
        self.acked: set = set()
        self.cwnd = 1.0
        self.timeout = 0.5
        self.timers: dict = {}
        self.ackLock = threading.Lock()

        listener = threading.Thread(target=self.ackListen, daemon=True)
        listener.start()

        nextIdx = 0
        while self.base < self.npkt:
            window = int(min(self.maxWin, max(1, int(self.cwnd))));
            while nextIdx < self.npkt and nextIdx < self.base + window:
                pkt = genPacket(nextIdx, 0, 0, self.chunks[nextIdx], time.time())
                self.socket.sendto(pkt, self.addr)
                self.timers[nextIdx] = time.time()
                self.sent[nextIdx] = self.timers[nextIdx]
                nextIdx += 1
            
            now = time.time()
            with self.ackLock:
                for idx in list(self.timers.keys()):
                    if idx in self.acked:
                        self.timers.pop(idx)
                        self.sent.pop(idx)
                
                for idx, t0 in list(self.timers.items()):
                    if idx not in self.acked and now - t0 > self.timeout:
                        self.cwnd = self.cc.ifTimeout(self.cwnd)
                        pkt = genPacket(idx, 0, 0, self.chunks[idx], time.time())
                        self.socket.sendto(pkt, self.addr)
                        self.timers[idx] = time.time()
        
        finalPkt = genPacket(self.npkt, (1 << 1), 0, "".encode("utf-8"), time.time())
        self.socket.sendto(finalPkt, self.addr)
        while True:
            data, recAddr = self.socket.recvfrom(2048)
            seq, flag, ackNum, payload, ts = getPacket(data)
            if flag & (1 << 0) and ackNum >= self.npkt:
                break

class FTPserver:
    def __init__(self, port: int, storage: str):
        self.port = port
        self.storage = storage
        os.makedirs(storage, exist_ok=True)
        self.socketControl = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socketControl.bind(("", port))
        print(f"server is listening on {port}")

    def serverCycle(self):
        while True:
            data, addr = self.socketControl.recvfrom(2048)
            try:
                req = json.loads(data.decode())
            except Exception:
                continue

            cmd = req.get("cmd")
            arqMode = req.get("arq")
            ccName = req.get("cc")
            pktSize = int(req.get("pktSize", 1024))
            maxWin = int(req.get("maxWin", 64))
            print(f"server: get request from {cmd} | arq mode = {arqMode} | cc = {ccName}")
            socketData = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            socketData.bind(("", 0))# bind to 0 so udp automatically bind a port
            dataPort = socketData.getsockname()[1]
            resp = {"status": "ok", "dataPort": dataPort}
            self.socketControl.sendto(json.dumps(resp).encode(), addr)
            listener = threading.Thread(target=self.handle, args=(socketData, addr, req), daemon=True)
            listener.start()



    def handle(self, socketData: socket.socket, addr, req: dict):
        cmd = req["cmd"]
        arqMode = req.get("arq", "gbn")
        ccName = req.get("cc")
        pktSize = int(req.get("pktSize", 1024))
        maxWin = int(req.get("maxWin", 64))
        if ccName == "vegas":
            cc = vegasContol()
        else:
            cc = renoControl()
        if cmd.startswith("upload"):
            remoteName = req.get("remoteName", "./storage")
            outPath = os.path.join(self.storage, remoteName)
            print(f"server: get upload from client, stored at {outPath}")
            if arqMode == "sr":
                recv = SRRreveiver(socketData, addr, outPath, arqMode, pktSize)
            else:
                recv = GBNreceiver(socketData, addr, outPath, arqMode, pktSize)
            recv.handle()
            fileMD5 = getMD5(outPath)
            resp = {"status": "done", "md5": fileMD5}
            self.socketControl.sendto(json.dumps(resp).encode(), addr)
            print(f"server: upload {remoteName} finished | md5 = {fileMD5}")
        elif cmd.startswith("download"):
            remoteName = req.get("remoteName", "")
            inPath = os.path.join(self.storage, remoteName)
            if not os.path.exists(inPath):
                resp = {"status": "error", "why": "file not exist"}
                self.socketControl.sendto(json.dumps(resp).encode(), addr)
                socketData.close()
                return
            print(f"server: start downloading file {inPath}")
            if arqMode == "sr":
                sender = SRsender(socketData, addr, inPath, arqMode, cc, pktSize, maxWin)
            else:
                sender = GBNsender(socketData, addr, inPath, arqMode, cc, pktSize, maxWin)
            sender.send()
            fileMD5 = getMD5(inPath)
            resp = {"status": "done", "md5": fileMD5}
            self.socketControl.sendto(json.dumps(resp).encode(), addr)
            print(f"server: download finished {remoteName} | md5 = {fileMD5}")
        else:
            resp = {"status": "error", "why": "unknown command"}
            self.socketControl.sendto(json.dumps(resp).encode(), addr)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=10000)
    parser.add_argument("--storage", type=str, help="enter local storage file")
    args = parser.parse_args()
    server = FTPserver(args.port, args.storage)
    server.serverCycle()

if __name__ == "__main__":
    main()



