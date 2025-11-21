from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import OVSController
from mininet.link import TCLink
from mininet.log import setLogLevel


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

        self.addLink(s1, s2, bw=20, delay="2ms", loss=10)



topos = {"mytopo": MyTopo}


def run_iperf_tests():
    topo = MyTopo()
    net = Mininet(topo=topo, link=TCLink, controller=OVSController)
    net.start()

    print("=== Ping All ===")
    net.pingAll()

    h1, h2, h3, h4 = net.get("H1", "H2", "H3", "H4")

    print("\n=== iperf: H1 <-> H2 ===")
    net.iperf((h1, h2))

    print("\n=== iperf: H2 <-> H4 ===")
    net.iperf((h2, h4))

    print("\n=== iperf: H3 <-> H4 ===")
    net.iperf((h3, h4))

    net.stop()


if __name__ == "__main__":
    setLogLevel("info")
    run_iperf_tests()