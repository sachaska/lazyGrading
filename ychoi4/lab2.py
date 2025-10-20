"""
CPSC5520 - Lab 2
Yunsung Choi
Date: 2024-10-14

Version2: Modified from lab1.py to implement a simple leader election algorithm(bully).

************************************************
            Version 1:
************************************************
1. connect to GCD
2. send 'HOWDY' to GCD
3. recv list of members from GCD
4. for each member in the list:
    a. connect to member
    b. send 'BEGIN' to member
    c. recv reply from member
5. print each reply from members and exit
************************************************
The lab requires simple socket programming.
We know that the GCD will send a pickled list of dicts with 'host' and 'port' keys,
and that each member will send either a pickled tuple or raw error bytes (in error cases).
Therefore, we can safely assume that:
    1) the data will fit within a single recv call of 1024 bytes 
       (no looping needed to collect all data),
    2) both the GCD and members behave as specified, 
       so we may skip format validation of the received data.
************************************************
            Version 2 updates:
************************************************
- each node has a unique p_id (days until birthday, SU_ID)
- upon startup, each node joins GCD with (p_id, listen_addr)
- each node maintains a members list dict[p_id] = (host, port)
- upon joining, GCD returns current members list
- each node starts an election upon joining GCD
- election algorithm (bully):
    - send 'ELECT' message with members list to all higher p_id members
    - if no response within timeout, become leader and send 'I_AM_LEADER' to all members
    - if receive 'ELECT' message, reply with 'GOT_IT'
      and start own election if not already in progress
    - if receive 'I_AM_LEADER' message, update current leader
- EXTRA_CREDIT:
    - periodically probe the leader to check if it's alive
    - simulate random failure and recovery for testing
    - when recovered, re-join GCD and start election
    - IGNORE ALL MESSAGES while failed (EXPECT: failed: empty response)

************************************************
How to run:
1. Start GCD server (gcd2.py):
    python3 gcd2.py PORT#
    Example:
    python3 gcd2.py 50600

2. Start multiple nodes (lab2.py):
    python3 lab2.py GCD_HOST GCD_PORT LISTEN_PORT SU_ID B-DAY(MM-DD)
   Example:
    python3 lab2.py cs2.seattleu.edu 50600 60301 12345678 05-15
    python3 lab2.py cs2.seattleu.edu 50600 60302 87654321 12-01
    python3 lab2.py cs2.seattleu.edu 50600 60303 11223344 07-30
    python3 lab2.py cs2.seattleu.edu 50600 60304 44332211 03-10 ...

3. Observe the output for joining, election, leader announcement, probing,
   and simulated failures/recoveries.

* Please ensure that the LISTEN_PORTs are unique for each node.
************************************************
"""

import pickle
import socket
import socketserver
import threading
import time
from datetime import date
import sys

import random # for simulating message loss in testing

GCD_MSG ='HOWDY'
PEER_MSG='BEGIN'
BUF_SZ = 1024 #tcp recv buffer size
PEER_TIMEOUT = 1.5 #seconds
ELECTION_WAIT = 2.0 #seconds to wait for election responses

MSG_ELECT = 'ELECT'
MSG_LEADER = 'I_AM_LEADER'
MSG_PROBE = 'PROBE'
RESP_GOT_IT = 'GOT_IT'

def days_until_bday(mmdd: str) ->int:
    """Calculate days until next birthday given MM-DD string."""
    today = date.today()
    m, d = map(int, mmdd.split('-'))
    y = today.year
    bday_this_year = date(y, m, d)
    if bday_this_year < today:
        bday_next = date(today.year + 1, m, d)
    else:
        bday_next = bday_this_year
    return (bday_next - today).days

def is_higher(a, b) -> bool:
    # (bday, su_id) > (bday, su_id)
    print(type(a[1]), type(b[1]))
    return a > b

# Handler for incoming TCP requests to the node 
# peer <-> peer communication: ELECT, I_AM_LEADER, PROBE
# Handles 'ELECT' and 'I_AM_LEADER' messages
class ThreadedTCPRequestHandler(socketserver.BaseRequestHandler):
    def handle(self):
        node: "Node" = self.server.node
        if node.failed:
            return # simulate failure in testing - IGNORE ALL MESSAGES while failed: EXPECT failed: empty response

        
        try:
            raw = self.request.recv(BUF_SZ)
            name, data = pickle.loads(raw)
        except Exception as e:
            return
        
        # handle 'ELECT' message
        if name == MSG_ELECT:
            try:
                node.merge_members(data)
            finally:
                try:
                    self.request.sendall(pickle.dumps(RESP_GOT_IT))
                except Exception:
                    pass

            # start election if not already in progress
            if not node.election_in_progress.is_set():
                threading.Thread(
                    target=node.start_election,
                    args=('election message received',),
                    daemon=True
                ).start()

        # handle 'I_AM_LEADER' message
        elif name == MSG_LEADER:
            node.set_leader(tuple(data))

        # handle 'PROBE' message
        elif name == MSG_PROBE:
            try:
                self.request.sendall(pickle.dumps(RESP_GOT_IT))
            except Exception:
                pass

        
                

# Main Node class
class Node:
    def __init__(self, gcd_host, gcd_port, listen_port, su_id, b_day):
        self.gcd = (gcd_host, int(gcd_port))
        self.listen = ('localhost', int(listen_port))
        self.p_id = (days_until_bday(b_day), su_id)# (days , SU_ID)

    
        self.leader_pid = None  # current leader's p_id
        self.members: dict = {} # dict[p_id] = (host, port)
        self.election_in_progress = threading.Event()

        self.server = socketserver.ThreadingTCPServer(self.listen, ThreadedTCPRequestHandler)
        self.server.node = self  # pass reference to Node instance

        self.failed = False # for simulating failure in testing

    def run(self):
        # Start a thread with the server -- that thread will then start one
        # more thread for each request
        server_thread = threading.Thread(target=self.server.serve_forever)
        # Exit the server thread when the main thread terminates
        server_thread.daemon = True
        server_thread.start()
        print(f"LISTEN {self.listen} pid={self.p_id}")

        #GCD join and start election
        self.join_gcd()
        self.start_election('start')

        #EXTRA - loop to probe leader periodically and loop to simulate failure
        #can be commented out if not needed
        self.probe_loop()
        self.simulate_failure()

        # Keep the main thread alive, or the process will exit.
        # Use Ctrl-C to stop
        try:
            while True:
                time.sleep(10)
        except KeyboardInterrupt:
            print("Shutting down....")
        finally:
            self.server.shutdown()
            self.server.server_close()
            sys.exit(0)

    # function to join GCD and handle communication with members
    def join_gcd(self):
        #gcd2.py protocol:  ('HOWDY', (pid, listen_addr)) 
        payload = (GCD_MSG, (self.p_id, self.listen))
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(PEER_TIMEOUT)
            s.connect(self.gcd)
            s.sendall(pickle.dumps(payload))
            data = s.recv(BUF_SZ) #format checking skipped
        group = pickle.loads(data) # expect a list of dicts with 'host' and 'port' keys
        group[self.p_id] = self.listen # add self to members list to ensure self-inclusion
        self.members = group # replace current members list
        print(f"joined: {self.members}")

    # merge incoming members dict into current members dict
    def merge_members(self, incoming: dict):
        before = len(self.members)
        self.members.update(incoming)
        self.members.setdefault(self.p_id, self.listen) # ensure self-inclusion
        if len(self.members) > before:
            print(f"members merged: {self.members}")

    # start election process
    # reason: string indicating why election started 
    # ex: 'start', 'election message received', 'leader probe failed', 'recovered'
    def start_election(self, reason: str):
        if self.election_in_progress.is_set():
            return
        self.election_in_progress.set()
        print(f"ELECTION started ({reason})")

        # send election message to all higher p_id members
        higher = [(pid, addr) for pid, addr in self.members.items() if is_higher(pid, self.p_id)]

        # if no higher members, become leader immediately
        if not higher:
            self.become_leader()
            return
        
        # send election messages that has higher p_id
        got_any = threading.Event()
        for pid, addr in higher:
            threading.Thread(target=self.send_election, args=(pid, addr, got_any), daemon=True).start()
            
        # wait for any higher member to respond
        waited, step = 0.0, 0.5
        while waited < ELECTION_WAIT and not got_any.is_set():
            time.sleep(step)
            waited += step

        # if no responses, become leader
        if not got_any.is_set():
            self.become_leader()
            return
        
        # otherwise, wait for leader announcement
        # if no leader announced within timeout then assume the higher failed AFTER response
        # therefore, restart election
        def wait_for_leader():
            t = 2.0 * ELECTION_WAIT
            slept =0.0
            while slept < t:
                if not self.election_in_progress.is_set() or self.leader_pid is not None:
                    return
                time.sleep(0.25)
                slept += 0.25
            print("No leader announced within timeout, restarting election")
            self.election_in_progress.clear()
            self.start_election('Timeout waiting for leader')
        threading.Thread(target=wait_for_leader, daemon=True).start()

    # send election message to the member(with higher p_id) and wait for response
    def send_election(self, pid, addr, got_flag: threading.Event):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(PEER_TIMEOUT)
                s.connect(addr)
                s.sendall(pickle.dumps((MSG_ELECT, self.members)))
                data = s.recv(BUF_SZ)

            # simulate random message loss in testing
            if not data:
                raise RuntimeError("empty response") # because of failure simulation
            
            resp = pickle.loads(data) # expect "GOT_IT"

            if resp == RESP_GOT_IT:
                print(f"Election response from {pid} at {addr}")
                got_flag.set()
        except Exception as e:
            print(f"Election message to {pid} at {addr} failed: {e}")

    # become leader and notify all members
    def become_leader(self):
        self.leader_pid = self.p_id
        print(f"I_AM_LEADER {self.p_id}")

        # notify all members of new leader
        for pid, addr in self.members.items():
            if pid == self.p_id:
                continue
            threading.Thread(target=self.send_leader, args=(addr,), daemon=True).start() # args=(addr,) !!!as a tuple!!!
        self.election_in_progress.clear()

    # send I_AM_LEADER message to the members
    def send_leader(self, addr):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(PEER_TIMEOUT)
                s.connect(addr)
                s.sendall(pickle.dumps((MSG_LEADER, self.p_id)))
        except Exception as e:
            print(f"Leader announcement to {addr} failed: {e}")

    # set new leader upon receiving I_AM_LEADER message
    def set_leader(self, leader_pid):
        self.leader_pid = leader_pid
        print(f"New leader is {self.leader_pid}")
        self.election_in_progress.clear()

    # EXTRA CREDIT
    # periodically probe the leader to check if it's alive
    def probe_loop(self):
        def loop():
            while True:
                if self.failed:
                    time.sleep(0.5); continue # skip probing while failed
                
                # if not leader, probe the leader
                if self.leader_pid and self.leader_pid != self.p_id:
                    addr = self.members.get(self.leader_pid)

                    # if leader address known, send probe
                    if addr and not self.failed:
                        ok = self.send_probe(addr)
                        if not ok:
                            print(f"PROBE failed to leader {self.leader_pid} at {addr}")
                            try:
                                # re-join GCD to get updated members list
                                self.join_gcd()
                            except Exception as e:
                                print(f"Re-join GCD failed: {e}")
                            # start new election
                            self.start_election('leader probe failed')
                # wait random time before next probe
                time.sleep(random.uniform(0.5, 3.0))
        # start probe loop in a separate thread
        threading.Thread(target=loop, daemon=True).start()

    # send probe message to leader and expect RESP_GOT_IT
    def send_probe(self, addr) -> bool:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(PEER_TIMEOUT)
                s.connect(addr)
                s.sendall(pickle.dumps((MSG_PROBE, None)))
                data = s.recv(BUF_SZ)
                resp = pickle.loads(data) # expect "GOT_IT"
                return resp == RESP_GOT_IT
        except Exception as e:
            return False
        
    # EXTRA
    # simulate random failure and recovery for testing
    # when recovered, re-join GCD and start election
    # IGNORE ALL MESSAGES while failed //(expect failed: empty response)//
    def simulate_failure(self):
        def loop():
            while True:
                time.sleep(random.uniform(0.0, 10.0))
                #fail begins
                self.failed = True
                print(f"Simulating failure of node {self.p_id}")
                time.sleep(random.uniform(1.0, 4.0))
                #restore
                self.failed = False
                print(f"Node {self.p_id} recovered from failure")
                try:
                    self.join_gcd() # re-join GCD
                except Exception as e:
                    print(f"Re-join GCD failed: {e}")
                self.start_election('recovered') # start new election
        threading.Thread(target=loop, daemon=True).start() 

if __name__ == '__main__':
    if len(sys.argv) != 6:
        print("Usage: python3 lab1.py GCD_HOST GCD_PORT LISTEN_PORT SU_ID B-DAY(MM-DD)")
        sys.exit(1)
    if sys.argv[5][2] != '-' or len(sys.argv[5]) != 5:
        print("B-DAY must be in MM-DD format")
        sys.exit(1)
    
    # read info from command line arguments
    GCD_HOST = sys.argv[1]
    GCD_PORT = int(sys.argv[2])
    LISTEN_PORT = int(sys.argv[3])
    SU_ID = int(sys.argv[4])
    B_DAY = sys.argv[5]

    # create and run node
    node = Node(GCD_HOST, GCD_PORT, LISTEN_PORT, SU_ID, B_DAY)
    node.run()



