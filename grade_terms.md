Account		
Style (not using oop, no comments, etc)	
Uses non-blocking socket send and receive	
Uses non-blocking socket accept and connect.	
Starts an election on startup.	
Declares victory when it is the highest known pid.	
When starting an election, sends ELECT messages to all other possible processes with pid greater than own.	
When declaring victory sends a I_AM_LEADER to everyone.	
Updates internal list of members from all other incoming messages with a member list payload.
Correctly joins group via GCD.	
Declares itself victor after a specified time has transpired without having received any of the expected GOT_IT responses.	
Reinitiates an election after a specified time has transpired without having received an expected I_AM_LEADER message.	
Starts an election when an ELECT message is received.	
Prints out a terse log of its activities and communications	Stops trying to send or receive a message after failing to succeed for a specified amount of time.	
Extra Credit: PROBE message	
Extra Credit: Feigning Failure
Comment				