#!/bin/python

import socket
import sys
from random import randint
import re
import redis
import hashlib
import json
import httplib

#----------------------------------- Settings --------------------------------------#
network = 'irc.freenode.net'
port = 6667
homechan = '#txtptest000'
try:
  irc = socket.socket ( socket.AF_INET, socket.SOCK_STREAM )
  irc.connect ( ( network, port ) )
except Exception, e:
  print 'Error initializing IRC: ' + str(e)
  exit()
print irc.recv ( 4096 )
irc.send ( 'PASS *********\r\n')
irc.send ( 'NICK txtptest\r\n' )
irc.send ( 'USER txtptest txtptest txtptest :txtptest\r\n' )
#----------------------------------------------------------------------------------#

calltable=dict()

redis_host="127.0.0.1"
redis_port=7777
try:
  redis = redis.Redis(host=redis_host,port=redis_port)
except Exception, e:
  print 'Error initializing redis: ' + str(e)
  exit()

#----------------------------------------------------------------------------------#
tipbot_address="TODO"
bitmonerod_host = '127.0.0.1'
bitmonerod_port = 6060
wallet_host = '127.0.0.1'
wallet_port = 6061
#---------------------------------- Functions -------------------------------------#
def readAdmin(host):                        # Return status 0/1
    bestand = open('admins.txt', 'r')
    for line in bestand:
        if host in line:
            status = 1
            return status
        else:
            status = 0
            return status

def GetHost(host):                            # Return Host
    host = host.split('@')[1]
    host = host.split(' ')[0]
    return host

def GetChannel(data):                        # Return Channel
    channel = data.split('#')[1]
    channel = channel.split(':')[0]
    channel = '#' + channel
    channel = channel.strip(' \t\n\r')
    return channel

def GetNick(data):                            # Return Nickname
    nick = data.split('!')[0]
    nick = nick.replace(':', ' ')
    nick = nick.replace(' ', '')
    nick = nick.strip(' \t\n\r')
    return nick

def Send(msg):
    irc.send('PRIVMSG ' + homechan + ' : ' + msg +  '\r\n')

def SendTo(where,msg):
    irc.send('PRIVMSG ' + where + ' : ' + msg +  '\r\n')

def Join(chan):
    irc.send ( 'JOIN ' + chan + '\r\n' )

def Part(chan):
    irc.send ( 'PART ' + chan + '\r\n' )

def CheckRegistered(nick,ifyes,yesdata,ifno,nodata):
  if nick not in calltable:
    calltable[nick] = []
  calltable[nick].append([ifyes,yesdata,ifno,nodata])
  SendTo('nickserv', "INFO " + nick)

def CheckAdmin(nick,ifyes,yesdata,ifno,nodata):
  if nick != "moneromooo" and nick != "moneromoo":
    SendTo(nick, "Access denied")
    return
  CheckRegistered(nick,ifyes,yesdata,ifno,nodata)

def PerformNextAction(nick,registered):
  if nick not in calltable:
    print 'Nothing in queue for ', nick
    return
  try:
    if registered:
      calltable[nick][0][0](nick,calltable[nick][0][1])
    else:
      calltable[nick][0][2](nick,calltable[nick][0][3])
    del calltable[nick][0]
  except Exception, e:
    print 'Exception in action, continuing: ' + str(e)
    del calltable[nick][0]

def GetPaymentID(nick):
  salt="2u3g55bkwrui32fi3g4bGR$j5g4ugnujb";
  p = hashlib.sha256(salt+nick).hexdigest();
  redis.hset("paymentid",p,nick)
  return p

def GetNickFromPaymendID(p):
  nick = redis.hget("paymentid",p)
  print 'PaymendID %s => %s' % (p, str(nick))
  return nick

def AmountToString(amount):
  if amount == None:
    amount = 0
  lamount=long(amount)
  if lamount < 1000000:
    samount = "%u tacoshi" % lamount
  elif lamount < 1000000000:
    samount = " %f micromonero" % (float(lamount) / 1e6)
  elif lamount < 1:
    samount = " %f millimonero" % (float(lamount) / 1e9)
  else:
    samount = "%f monero" % (float(lamount) / 1e12)
  return samount

def GetBalance(nick,data):
  print "GetBalance: checking", nick
  try:
    balance = redis.hget("balances",nick)
    if balance == None:
      balance = 0
    sbalance = AmountToString(balance)
    SendTo(nick, "%s's balance is %s" % (nick, sbalance))
  except Exception, e:
    print 'GetBalance: exception: ' + str(e)
    SendTo(nick, "An error has occured")

def AddBalance(nick,data):
  amount=data
  print 'Adding ' + amount + " to " + nick + "'s balance"
  try:
    balance = redis.hincrby("balances",nick,amount)
  except Exception, e:
    print 'AddBalance: exception: ' + str(e)
    SendTo(nick, "An error has occured")

def Tip(nick,data):
  who=data[0]
  try:
    amount=float(data[1])
  except Exception,e:
    SendTo(nick, "Usage: tip nick amount")
    return

  print "%s wants to tip %s %.12f monero" % (nick, who, amount)
  try:
    balance = redis.hget("balances",nick)
    if balance == None:
      balance = 0
    balance=long(balance)
    units=long(amount*1e12)
    if units <= 0:
      SendTo(nick, "Invalid amount")
      return
    if units > balance:
      SendTo(nick, "You only have %.12f" % (balance / 1e12))
      return
    print '%s tipping %s %u units, with balance %u' % (nick, who, units, balance)
    try:
      p = redis.pipeline()
      p.hincrby("balances",nick,-units);
      p.hincrby("balances",who,units)
      p.execute()
      SendTo(nick,"%s has tipped %s %.12f monero" % (nick, who, amount))
    except Exception, e:
      SendTo(nick, "An error occured")
      return
  except Exception, e:
    print 'Tip: exception: ' + str(e)
    SendTo(nick, "An error has occured")

def SendJSONRPCCommand(host,port,method,params):
  try:
    http = httplib.HTTPConnection(host,port)
  except Exception,e:
    print 'Error connecting to %s:%u: %s' % (host, port, str(e))
    raise
  d = dict(id="0",jsonrpc="2.0",method=method,params=params)
  try:
    j = json.dumps(d).encode()
  except Exception,e:
    print 'Failed to encode JSON: ' + str(e)
    http.close()
    raise
  print 'Sending json as body: ', j
  headers = None
  try:
    http.request("POST","/json_rpc",body=j)
  except Exception,e:
    print 'Failed to post request: ' + str(e)
    http.close()
    raise
  response = http.getresponse()
  print 'Received reply status: ', response.status
  if response.status != 200:
    print 'Error, not 200'
    http.close()
    raise RuntimeError("Error "+response.status)
  s = response.read()
  print 'Received reply: ', s
  try:
    j = json.loads(s)
  except Exception,e:
    print 'Failed to decode JSON: ' + str(e)
    http.close()
    raise
  http.close()
  return j

def SendHTMLCommand(host,port,method):
  try:
    http = httplib.HTTPConnection(host,port)
  except Exception,e:
    print 'Error connecting to %s:%u: %s' % (host, port, str(e))
    raise
  headers = None
  try:
    http.request("POST","/"+method)
  except Exception,e:
    print 'Failed to post request: ' + str(e)
    http.close()
    raise
  response = http.getresponse()
  print 'Received reply status: ', response.status
  if response.status != 200:
    print 'Error, not 200'
    http.close()
    raise RuntimeError("Error "+response.status)
  s = response.read()
  print 'Received reply: ', s
  try:
    j = json.loads(s)
  except Exception,e:
    print 'Failed to decode JSON: ' + str(e)
    http.close()
    raise
  http.close()
  return j

def SendWalletJSONRPCCommand(method,params):
  return SendJSONRPCCommand(wallet_host,wallet_port,method,params)

def SendBitmonerodJSONRPCCommand(method,params):
  return SendJSONRPCCommand(bitmonerod_host,bitmonerod_port,method,params)

def SendBitmonerodHTMLCommand(method):
  return SendHTMLCommand(bitmonerod_host,bitmonerod_port,method)

def GetHeight(nick,data):
  print '%s wants to know block height' % nick
  try:
    j = SendBitmonerodHTMLCommand("getheight")
  except Exception,e:
    SendTo(nick,"An error has occured")
    return
  print 'Got reply: ' + str(j)
  if not "height" in j:
    print 'Cannot see height in here'
    SendTo(nick, "Height not found")
    return
  SendTo(nick, "Height: %s" % str(j["height"]))

def GetTipbotBalance(nick,data):
  print '%s wants to know the tipbot balance' % nick
  try:
    j = SendWalletJSONRPCCommand("getbalance",None)
  except Exception,e:
    SendTo(nick,"An error has occured")
    return
  if not "result" in j:
    print 'result not found in reply'
    SendTo(nick, "An error has occured")
    return
  result = j["result"]
  if not "balance" in result:
    print 'balance not found in result'
    SendTo(nick, "An error has occured")
    return
  if not "unlocked_balance" in result:
    print 'unlocked_balance not found in result'
    SendTo(nick, "An error has occured")
    return
  balance = result["balance"]
  unlocked_balance = result["unlocked_balance"]
  print 'balance: %s' % str(balance)
  print 'unlocked_balance: %s' % str(unlocked_balance)
  pending = long(balance)-long(unlocked_balance)
  if pending < 0:
    print 'Negative pending balance! balance %s, unlocked %s'
    SendTo(nick, "An error has occured")
    return
  if pending == 0:
    SendTo(nick,"Tipbot balance: %s" % AmountToString(balance))
  else:
    SendTo(nick,"Tipbot balance: %s (%s pending)" % (AmountToString(unlocked_balance), AmountToString(pending)))

def Help(nick):
  SendTo(nick, "Help for the monero tipbot:")
  SendTo(nick, "!isregistered - show whether you are currently registered with freenode")
  SendTo(nick, "!balance - show your current balance")
  SendTo(nick, "!tip <nick> <amount> - tip another user")
  SendTo(nick, "!info - information about the tipbot")
  SendTo(nick, "You can send monero to your tipbot account:");
  SendTo(nick, "  Address: %s" % tipbot_address)
  SendTo(nick, "  Payment ID: %s" % GetPaymentID(nick))
  SendTo(nick, "NO WARRANTY, YOU MAY LOSE YOUR COINS")
  SendTo(nick, "Minimum withdrawal: 0.1 monero")

def Info(nick):
  SendTo(nick, "Info for the monero tipbot:")
  SendTo(nick, "Type !help for a list of commands")
  SendTo(nick, "NO WARRANTY, YOU MAY LOSE YOUR COINS")
  SendTo(nick, "By sending your monero to the tipbot, you are giving up their control")
  SendTo(nick, "to whoever runs the tipbot. Any tip you make/receive using the tipbot")
  SendTo(nick, "is obviously not anonymous. The tipbot wallet may end up corrupt, or be")
  SendTo(nick, "stolen, the server compromised, etc. While I hope this won't be the case,")
  SendTo(nick, "I will not offer any warranty whatsoever for the use of the tipbot or the")
  SendTo(nick, "return of any monero. Use at your own risk.")
  SendTo(nick, "That being said, I hope you enjoy using it :)")

#def Op(to_op, chan):
#    irc.send( 'MODE ' + chan + ' +o: ' + to_op + '\r\n')
#
#def DeOp(to_deop, chan):
#    irc.send( 'MODE ' + chan + ' -o: ' + to_deop + '\r\n')
#
#def Voice(to_v, chan):
#    irc.send( 'MODE ' + chan + ' +v: ' + to_v + '\r\n')
#
#def DeVoice(to_dv, chan):
#    irc.send( 'MODE ' + chan + ' -v: ' + to_dv + '\r\n')
#------------------------------------------------------------------------------#

buffered_data = ""
def getline(s):
  global buffered_data
  idx = buffered_data.find("\n")
  if idx == -1:
    buffered_data+=s.recv(4096)
  idx = buffered_data.find("\n")
  if idx == -1:
    ret = buffered_data
    buffered_data = ""
    return ret
  ret = buffered_data[0:idx+1]
  buffered_data = buffered_data[idx+1:]
  return ret

while True:
    action = None
    data = getline(irc)
    data = data.strip("\r\n")
    print data

    if data.find ( 'Welcome to the freenode Internet Relay Chat Network' ) != -1:
            Join(homechan)

    if data.find ( 'PING' ) != -1:
            irc.send ( 'PONG ' + data.split() [ 1 ] + '\r\n' )

    #--------------------------- Action check --------------------------------#
    if data.find(':') == -1:
        continue

    try:
        parts = data.split(':')
        if len(parts) < 3:
            continue
        text = parts[2]
        parts = parts[1].split(' ')
        who = parts[0]
        action = parts[1]
        chan = parts[2]
    except Exception, e:
        print 'Exception, continuing: ' + str(e)
        continue

    if action == None:
        continue

    print 'text: ', text
    print 'who: ', who
    print 'action: ', action
    print 'chan: ', chan

#    if data.find('#') != -1:
#        action = data.split('#')[0]
#        action = action.split(' ')[1]

#    if data.find('NICK') != -1:
#        if data.find('#') == -1:
#            action = 'NICK'

    #----------------------------- Actions -----------------------------------#
    if action == 'NOTICE':
        if who == "NickServ!NickServ@services.":
            if text.find('Information on ') != -1:
                ns_nick = text.split(' ')[2].strip("\002")
                print 'NickServ says %s is registered' % ns_nick
                PerformNextAction(ns_nick, True)
            elif text.find(' is not registered') != -1:
                ns_nick = text.split(' ')[0].strip("\002")
                print 'NickServ says %s is not registered' % ns_nick
                PerformNextAction(ns_nick, False)

    if action == 'PRIVMSG':
        if text.find('!') != -1:
            cmd = text.split('!')[1]
            cmd = cmd.split(' ')
            cmd[0] = cmd[0].strip(' \t\n\r')
            #print 'XXX found command: "%s"' % str(cmd)

            if cmd[0] == 'join':
                Join('#' + cmd[1])
            elif cmd[0] == 'part':
                Part('#' + cmd[1])
            elif cmd[0] == 'version':
                SendTo(chan, 'I am a monero tipbot, more info if you type !help')
            elif cmd[0] == 'isregistered':
                CheckRegistered(GetNick(who),SendTo,"You are registered",SendTo,"You are not registered")
            elif cmd[0] == 'balance':
                CheckRegistered(GetNick(who),GetBalance,None,SendTo,"You must be registered with Freenode to query balance")
            elif cmd[0] == 'tip':
                if len(cmd) == 3:
                    CheckRegistered(GetNick(who),Tip,[cmd[1],cmd[2]],SendTo,"You must be registered with Freenode to tip")
                else:
                    SendTo(GetNick(who), "Usage: !tip nick amount");
            elif cmd[0] == 'height':
                CheckAdmin(GetNick(who),GetHeight,None,SendTo,"You must be admin")
            elif cmd[0] == 'tipbot_balance':
                CheckAdmin(GetNick(who),GetTipbotBalance,None,SendTo,"You must be admin")
            #elif cmd[0] == 'addbalance':
            #    CheckRegistered(GetNick(who),AddBalance,cmd[1],SendTo,"You must be registered with Freenode to add balance")
            elif cmd[0] == 'info':
                Info(GetNick(who))
            elif cmd[0] == 'help':
                Help(GetNick(who))

#    if action == 'xxx_______MODE':
#        Host = GetHost(data)
#        status = readAdmin(Host)
#        if status == 0:
#            if data.find('-o') != -1:
#                to_op = data.split('-o')[1]
#                chan = GetChannel(data)
#                chan = chan.split('-o')[0]
#                Op(to_op, chan)
#
#            if data.find('+o') != -1:
#                to_deop = data.split('+o')[1]
#                chan = GetChannel(data)
#                chan = chan.split('+o')[0]
#                DeOp(to_deop, chan)
#
#    if action == 'xxx_______JOIN':
#        Host = GetHost(data)
#        status = readAdmin(Host)
#        if status == 1:
#            chan = GetChannel(data)
#            nick = GetNick(data)
#            Op(nick, chan)
