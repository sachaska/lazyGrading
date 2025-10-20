In this lab we will join a group. This group will be fully interconnected (like a round table) and we will endeavor to choose a leader using the bully algorithm
Links to an external site. (textbook pp. 283-285). Choosing a leader is a form of consensus.
You will program a node in the group in Python 3.
It will:
Have an identity which is the pair: (days until your mother's next birthday, your SU ID)
Join the group by talking to the GCD with a HOWDY message.
Participate in elections.
Notice when the current leader has failed and initiate an election. (Extra Credit)
Pretend to fail every once in a while and then subsequently recover. (Extra Credit)
Details:
The "least" of two identities is the one with fewer days until the birthday, or if their mothers have the same birthday, then the one with the smaller SU ID.
A process listens for other members wanting to send messages to it.
A process connects to each higher process by sending an ELECT message to the higher process's listening server as described in the message protocol below.
Detecting a failed leader is done by each process sending occasional PROBE messages to her.
All messages are pickled and are a pair (message_name, message_data), where message_name is the text of the message name (that is, one of 'HOWDY', 'ELECT', 'I_AM_LEADER', or 'PROBE') and the message_data is specified in the protocol below or, if there is no message data, use None. Message responses, when they exist, can either be just pickled text or data as specified in the protocol below.
Peer sockets must be non-blocking, i.e. you mustn't block waiting for the receipt of the GOT_IT when sending an ELECT message (think about why this would cause our peers to think we had failed). You must use the ThreadingTCPServer
Links to an external site. class from the socketserver library to accomplish this.
Protocol
HOWDY Message
When starting up, contact the GCD and send a HOWDY message, which is a double: (process_id, listen_address) and whose response is a list of all the other members (some of which may now be failed). The message content's process_id is the identity pair (days_to_moms_birthday, SU ID) and the listen_address is the pair (host, port) of your listening server. The returned data structure is a dictionary of all group members, keyed listen_address with values of corresponding process_id. You then start an election.
ELECT Message
You initiate an election when you first join the group or whenever you notice the leader has failed. The ELECT message is sent to each member with a higher process id than your own. If you are the highest process id in the group or if none of the higher processes respond within the given time limit, you win the election. If you win an election, you immediately send a I_AM_LEADER message to everyone. While you are waiting for responses from higher processes, you put yourself into an election-in-progress state.
The ELECT message is a list of all the current (alive or failed) group members, including yourself. This is the same format as the list returned from the HOWDY message.
When you receive an ELECT message, you update your membership list with any members you didn't already know about, then you respond with the text GOT_IT. If you are currently in an election, that's all you do. If you aren't in an election, then proceed as though you are initiating a new election.
I_AM_LEADER Message
The I_AM_LEADER message is sent by the group leader when she wins an election. The message data is the new leader's identity. There is no response to a I_AM_LEADER message.
If you receive an I_AM_LEADER message, then change your state to not be election-in-progress and note the (possibly) new leader.
PROBE Message (Extra Credit)
The PROBE message is sent occasionally to the group leader by all the other members of the group. There is no message data. The response is the text GOT_IT. Between each PROBE message, choose a random amount of time between 500 and 3000ms. A failed PROBE will trigger a new election, but in this case re-register with the GCD first to get the latest peer list before starting the election.
Up to five points of extra credit (only if you get 60 points or more on the main assignment).
Feigning Failure (Extra Credit)
At startup and whenever you recover from a previous feigned failure, start a timer and when the timer goes off, pretend you have failed, then eventually recover and go back to normal operation. The time to your next failure should be chosen each time randomly between 0 and 10000ms and the length of your failure should be chosen independently between 1000 and 4000ms. You can feign failure by either closing all your sockets, including the listening port or by just ignoring all incoming messages. Recovery is done by starting your listening server and initiating an election.
Up to five points of extra credit (only if you get 60 points or more on the main assignment).
Hand In
Like last week, but with your file named lab2.py, on CS1:
[cs1]$ ~lundeenk/5520/submit/lab2 
Guidance
Python.org has a good how-to on sockets
Links to an external site..
You can use my gcd2.py
Download gcd2.py for testing. If you are testing on CS2, to avoid conflicts, use the port number: .
Be aware of your various threads accessing the same data structures. You may not need any synchronization beyond what is provided by the Python interpreter
Links to an external site., but beware.
Note that the example at the end of the socketserver doc page is basically what we want for the incoming messages, so you might want to start with that. The class ThreadingTCPServer since Python3.7 is now defined in the socketserver library, so we can change their example to use it:
 [lundeenk@cs2 ~]$ cat example_server.py # like the example from python socketserver doc
"""Example threaded server based on example at end of python.org's
socketserver documentation page.
see: https://docs.python.org/3/library/socketserver.html

Changes to their example:
o Use the predefined socketserver.ThreadingTCPServer instead of mixing our own
o Use the shared server object to demo IPC with shared memory (server.notes)

Kevin Lundeen for SeattleU/CPSC5520 f23
"""
import socket
import threading
import socketserver



class ThreadedTCPRequestHandler(socketserver.BaseRequestHandler):
    def handle(self):
        data = str(self.request.recv(1024), 'ascii')
        cur_thread = threading.current_thread()
        response = "{}: {}".format(cur_thread.name, data)
        self.request.sendall(bytes(response, 'ascii'))

        # self is a different object for each thread, but it has references
        # to the server's object, too, so we can share that
        self.server.notes.append(response)  # append to a list is thread-safe



def client(ip, port, message):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((ip, port))
        sock.sendall(bytes(message, 'ascii'))
        response = str(sock.recv(1024), 'ascii')
        print("Received: {}".format(response))



if __name__ == "__main__":
    # Port 0 means to select an arbitrary unused port
    HOST, PORT = "localhost", 0

    server = socketserver.ThreadingTCPServer((HOST, PORT), ThreadedTCPRequestHandler)
    server.notes = []  # set up a place for all the threads to add notes
    with server:
        ip, port = server.server_address

        # Start a thread with the server -- that thread will then start one
        # more thread for each request
        server_thread = threading.Thread(target=server.serve_forever)
        # Exit the server thread when the main thread terminates
        server_thread.daemon = True
        server_thread.start()
        print("Server loop running in thread:", server_thread.name)

        client(ip, port, "Hello World 1")
        client(ip, port, "Hello World 2")
        client(ip, port, "Hello World 3")

        print('\nHere are the notes appended by each thread:')
        for note in server.notes:
            print(note)  # print out the notes appended by each thread
        server.shutdown()

[lundeenk@cs2 ~]$ python3.11 example_server.py # run the demo
Server loop running in thread: Thread-1 (serve_forever)
Received: Thread-2 (process_request_thread): Hello World 1
Received: Thread-3 (process_request_thread): Hello World 2
Received: Thread-4 (process_request_thread): Hello World 3

Here are the notes appended by each thread:
Thread-2 (process_request_thread): Hello World 1
Thread-3 (process_request_thread): Hello World 2
Thread-4 (process_request_thread): Hello World 3
     


You'll want to do the outgoing messages in threads, too, to make them non-blocking. Note that the sockets themselves will still be blocking (do not call socket.setblocking(false)) but they each have their own thread and so don't block the communications with other peers. (Threads are easier than selectors so don't use selectors.)
If you use a message queue like I do, then you'll have to be careful to coordinate access to that queue. If a thread were to append a message at the same time the main thread is processing the queue, that could lead to a race condition. To handle this, I recommend a monitor pattern, like Java has built in to its thread-safe objects. I use Python's threading.Event to handle the notification and waiting around the monitor. In my code lab2.message_sync and lab2.message_flag are both Event objects constructed in the Lab2 constructor. The message_sync Event is designed to lock out the threads while the main thread is harvesting messages. The message_flag Event is designed to notify the main thread when there have been messages appended to the message queue (lab2.messages is my message queue). Here are the two methods I use to synchronize access to the message queue: report_message is for the threads to use and harvest_message is for the main thread. You can use these without attribution if you want.



