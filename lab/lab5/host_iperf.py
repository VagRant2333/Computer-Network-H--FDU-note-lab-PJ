from mininet.topo import Topo
from mininet.net import Mininet
from mininet.link import TCLink
from mininet.util import dumpNodeConnections
from mininet.log import setLogLevel
from mininet.node import OVSBridge
import time
import threading

# LOSS_BETWEEN_SWITCHES = 0
# LOSS_BETWEEN_SWITCHES = 1
# LOSS_BETWEEN_SWITCHES = 5
LOSS_BETWEEN_SWITCHES = 10


class MyTopo(Topo):
    def __init__(self):
        super(MyTopo, self).__init__()

        h1 = self.addHost("H1", ip="10.0.0.1", mac="00:00:00:00:ff:01")
        h2 = self.addHost("H2", ip="10.0.0.2", mac="00:00:00:00:ff:02")
        h3 = self.addHost("H3", ip="10.0.0.3", mac="00:00:00:00:ff:03")
        h4 = self.addHost("H4", ip="10.0.0.4", mac="00:00:00:00:ff:04")

        s1 = self.addSwitch("S1")
        s2 = self.addSwitch("S2")

        self.addLink(h1, s1, bw=10, delay="2ms")
        self.addLink(h2, s1, bw=20, delay="10ms")
        self.addLink(h3, s2, bw=10, delay="2ms")
        self.addLink(h4, s2, bw=20, delay="10ms")
        self.addLink(s1, s2, bw=20, delay="2ms", loss=LOSS_BETWEEN_SWITCHES)


def flow1(h1, h3):
    print("[Flow1] Start server on H3:5001")
    h3.cmd("iperf -s -p 5001 &")
    print("[Flow1] Client H1 -> H3, t=0~20s, interval=0.5s")
    result = h1.cmd("iperf -c 10.0.0.3 -p 5001 -t 20 -i 0.5")
    print("========== Flow1 Result (H1 -> H3) ==========")
    print(result)


def flow2(h2, h4):
    time.sleep(10)
    print("[Flow2] Start server on H4:5002 at t=10s")
    h4.cmd("iperf -s -p 5002 &")
    print("[Flow2] Client H2 -> H4, t=10~30s, interval=0.5s")
    result = h2.cmd("iperf -c 10.0.0.4 -p 5002 -t 20 -i 0.5")
    print("========== Flow2 Result (H2 -> H4) ==========")
    print(result)


def perfTest():
    topo = MyTopo()
    net = Mininet(
        topo=topo,
        link=TCLink,
        switch=OVSBridge,
        controller=None
    )
    net.start()

    print("[Net] Host connections:")
    dumpNodeConnections(net.hosts)

    h1, h2, h3, h4 = net.get("H1", "H2", "H3", "H4")

    t1 = threading.Thread(target=flow1, args=(h1, h3))
    t2 = threading.Thread(target=flow2, args=(h2, h4))

    t1.start()
    t2.start()

    time.sleep(40)
    net.stop()


if __name__ == "__main__":
    setLogLevel("info")
    perfTest()