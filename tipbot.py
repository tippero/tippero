#!/bin/python
#
# Cryptonote tipbot
# Copyright 2014 moneromooo
# Inspired by "Simple Python IRC bot" by berend
#
# The Cryptonote tipbot is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published
# by the Free Software Foundation; either version 2, or (at your option)
# any later version.
#

import socket
import select
import sys
import random
import re
import redis
import hashlib
import json
import httplib
import time
import string

tipbot_name = "monero-testnet-tipbot"
irc_network = 'irc.freenode.net'
irc_port = 6667
irc_homechan = '#txtptest000'
irc_timeout_seconds = 600

redis_host="127.0.0.1"
redis_port=7777

bitmonerod_host = 'testfull.monero.cc' # '127.0.0.1'
bitmonerod_port = 28081 # 6060
wallet_host = '127.0.0.1'
wallet_port = 6061
wallet_update_time = 30 # seconds
coin=1e12
coin_name = "Monero"
coin_denominations = [[1000000, 1, "piconero"], [1000000000, 1e6, "micronero"], [1000000000000, 1e9, "millinero"]]
address_length = [95, 95] # min/max size of addresses
address_prefix = ['4', '9'] # allowed prefixes of addresses
withdrawal_fee = 10000000000
min_withdraw_amount = 2*withdrawal_fee
withdraw_disabled = False
disable_withdraw_on_error = True
web_wallet_url = "https://mymonero.com/" # None is there's none

admins = ["moneromooo", "moneromoo"]

# list of nicks to ignore for rains - bots, trolls, etc
no_rain_to_nicks = []

userstable=dict()
registered_users=set()
calltable=dict()
last_wallet_update_time = None
last_ping_time = time.time()



def log(stype,msg):
  header = "%s\t%s\t" % (time.ctime(time.time()),stype)
  print "%s%s" % (header, str(msg).replace("\n","\n"+header))

def log_error(msg):
  log("ERROR",msg)

def log_warn(msg):
  log("WARNING",msg)

def log_info(msg):
  log("INFO",msg)

def log_log(msg):
  log("LOG",msg)

def log_IRCRECV(msg):
  log("IRCRECV",msg)

def log_IRCSEND(msg):
  log("IRCSEND",msg)

def SendIRC(msg):
  log_IRCSEND(msg)
  irc.send(msg + '\r\n')

def connect_to_irc(network,port):
  global irc
  try:
    irc = socket.socket ( socket.AF_INET, socket.SOCK_STREAM )
    irc.connect ( ( network, port ) )
  except Exception, e:
    log_error( 'Error initializing IRC: %s' % str(e))
    exit()
  log_IRCRECV(irc.recv ( 4096 ))
  SendIRC ( 'PASS *********')
  SendIRC ( 'NICK %s' % tipbot_name)
  SendIRC ( 'USER %s %s %s :%s' % (tipbot_name, tipbot_name, tipbot_name, tipbot_name))

def connect_to_redis(host,port):
  try:
    return redis.Redis(host=host,port=port)
  except Exception, e:
    log_error( 'Error initializing redis: %s' % str(e))
    exit()

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

def GetPassword():
  try:
    f = open('tipbot-password.txt', 'r')
    for p in f:
      p = p.strip("\r\n")
      f.close()
      return p
  except Exception,e:
    log_error('could not fetch password: %s' % str(e))
    raise
    return "xxx"

def Send(msg):
    SendIRC ('PRIVMSG ' + irc_homechan + ' : ' + msg)

def SendTo(where,msg):
    SendIRC ('PRIVMSG ' + where + ' : ' + msg)

def Join(chan):
    SendIRC ( 'JOIN ' + chan)

def Part(chan):
    SendIRC ( 'PART ' + chan)

def Who(chan):
    SendIRC ( 'WHO ' + chan)

def IsParamPresent(parms,idx):
  return len(parms) > idx

def GetParam(parms,idx):
  if IsParamPresent(parms,idx):
    return parms[idx]
  return None

def CheckRegistered(nick,ifyes,yesdata,ifno,nodata):
  if nick not in calltable:
    calltable[nick] = []
  calltable[nick].append([ifyes,yesdata,ifno,nodata])
  if nick in registered_users:
    PerformNextAction(nick,True)
  else:
    SendTo('nickserv', "ACC " + nick)

def IsAdmin(nick):
  return nick in admins

def CheckAdmin(nick,ifyes,yesdata,ifno,nodata):
  if not IsAdmin(nick):
    log_warn('CheckAdmin: nick %s is not admin, cannot call %s with %s' % (str(nick),str(ifyes),str(yesdata)))
    SendTo(nick, "Access denied")
    return
  CheckRegistered(nick,ifyes,yesdata,ifno,nodata)

def PerformNextAction(nick,registered):
  if registered:
    registered_users.add(nick)
  else:
    registered_users.discard(nick)
  if nick not in calltable:
    log_error( 'Nothing in queue for %s' % nick)
    return
  try:
    if registered:
      calltable[nick][0][0](nick,calltable[nick][0][1])
    else:
      calltable[nick][0][2](nick,calltable[nick][0][3])
    del calltable[nick][0]
  except Exception, e:
    log_error('PerformNextAction: Exception in action, continuing: %s' % str(e))
    del calltable[nick][0]

def GetPaymentID(nick):
  salt="2u3g55bkwrui32fi3g4bGR$j5g4ugnujb";
  p = hashlib.sha256(salt+nick).hexdigest();
  try:
    redis.hset("paymentid",p,nick)
  except Exception,e:
    log_error('GetPaymentID: failed to set payment ID for %s to redis: %s' % (nick,str(e)))
  return p

def GetTipbotAddress():
  try:
    j = SendWalletJSONRPCCommand("getaddress",None)
    if not "result" in j:
      log_error('GetTipbotAddress: No result found in getaddress reply')
      return ERROR
    result = j["result"]
    if not "address" in result:
      log_error('GetTipbotAddress: No address found in getaddress reply')
      return ERROR
    return result["address"]
  except Exception,e:
    log_error("GetTipbotAddress: Error retrieving tipbot address: %s" % str(e))
    return "ERROR"

def GetNickFromPaymendID(p):
  nick = redis.hget("paymentid",p)
  log_log('PaymendID %s => %s' % (p, str(nick)))
  return nick

def AmountToString(amount):
  if amount == None:
    amount = 0
  lamount=long(amount)
  samount = None
  if lamount == 0:
    samount = "0 %s" % coin_name
  else:
    for den in coin_denominations:
      if lamount < den[0]:
        samount = "%.16g %s" % (float(lamount) / den[1], den[2])
        break
  if not samount:
      samount = "%.16g %s" % (float(lamount) / coin, coin_name)
  log_log("AmountToString: %s -> %s" % (str(amount),samount))
  return samount

def GetBalance(nick,data):
  log_log("GetBalance: checking %s" % nick)
  sendto=data[0]
  try:
    balance = redis.hget("balances",nick)
    if balance == None:
      balance = 0
    sbalance = AmountToString(balance)
    SendTo(sendto, "%s's balance is %s" % (nick, sbalance))
  except Exception, e:
    log_error('GetBalance: exception: %s' % str(e))
    SendTo(sendto, "An error has occured")

def AddBalance(nick,data):
  amount=data
  log_info("AddBalance: Adding %s to %s's balance" % (AmountToString(amount),nick))
  try:
    balance = redis.hincrby("balances",nick,amount)
  except Exception, e:
    log_error('AddBalance: exception: %s' % str(e))
    SendTo(nick, "An error has occured")

def Tip(nick,data):
  sendto=data[0]
  who=data[1]
  try:
    amount=float(data[2])
  except Exception,e:
    SendTo(sendto, "Usage: tip nick amount")
    return
  units=long(amount*coin)
  if units <= 0:
    SendTo(sendto, "Invalid amount")
    return

  log_info("Tip: %s wants to tip %s %s" % (nick, who, AmountToString(units)))
  try:
    balance = redis.hget("balances",nick)
    if balance == None:
      balance = 0
    balance=long(balance)
    if units > balance:
      SendTo(sendto, "You only have %s" % (AmountToString(balance)))
      return
    log_info('Tip: %s tipping %s %u units, with balance %u' % (nick, who, units, balance))
    try:
      p = redis.pipeline()
      p.hincrby("balances",nick,-units);
      p.hincrby("balances",who,units)
      p.execute()
      SendTo(sendto,"%s has tipped %s %s" % (nick, who, AmountToString(units)))
    except Exception, e:
      SendTo(sendto, "An error occured")
      return
  except Exception, e:
    log_error('Tip: exception: %s' % str(e))
    SendTo(sendto, "An error has occured")

def ScanWho(nick,data):
  chan=data[0]
  userstable[chan] = dict()
  Who(chan)

def Rain(nick,data):
  chan=data[0]
  try:
    amount=float(data[1])
  except Exception,e:
    SendTo(sendto, "Usage: rain amount [users]")
    return
  users = GetParam(data,2)
  if users:
    try:
      users=long(users)
    except Exception,e:
      SendTo(sendto, "Usage: rain amount [users]")
      return

  if amount <= 0:
    SendTo(sendto, "Usage: rain amount [users]")
    return
  if users != None and users <= 0:
    SendTo(sendto, "Usage: rain amount [users]")
    return
  units = long(amount * coin)

  try:
    balance = redis.hget("balances",nick)
    if balance == None:
      balance = 0
    balance=long(balance)
    if units > balance:
      SendTo(sendto, "You only have %s" % (AmountToString(balance)))
      return

    userlist = userstable[chan].keys()
    userlist.remove(nick)
    for n in no_rain_to_nicks:
      userlist.remove(n)
    if users == None or users > len(userlist):
      users = len(userlist)
      everyone = True
    else:
      everyone = False
    if users == 0:
      SendTo(sendto, "Nobody eligible for rain")
      return
    if units < users:
      SendTo(sendto, "This would mean not even an atomic unit per nick")
      return
    log_info("%s wants to rain %s on %s users in %s" % (nick, AmountToString(units), users, chan))
    log_log("users in %s: %s" % (chan, str(userlist)))
    random.shuffle(userlist)
    userlist = userlist[0:users]
    log_log("selected users in %s: %s" % (chan, userlist))
    user_units = long(units / users)

    if everyone:
      msg = "%s rained %s on everyone in the channel" % (nick, AmountToString(user_units))
    else:
      msg = "%s rained %s on:" % (nick, AmountToString(user_units))
    pipe = redis.pipeline()
    pipe.hincrby("balances",nick,-units)
    for user in userlist:
      pipe.hincrby("balances",user,user_units)
      if not everyone:
        msg = msg + " " + user
    pipe.execute()
    SendTo(sendto, "%s" % msg)

  except Exception,e:
    log_error('Rain: exception: %s' % str(e))
    SendTo(sendto, "An error has occured")
    return

def RainActive(nick,data):
  chan=data[0]
  amount=GetParam(data,1)
  hours=GetParam(data,2)
  minfrac=GetParam(data,3)

  try:
    amount=float(amount)
    if amount <= 0:
      raise RuntimeError("")
  except Exception,e:
    SendTo(sendto, "Invalid amount")
    return
  try:
    hours=float(hours)
    if hours <= 0:
      raise RuntimeError("")
  except Exception,e:
    SendTo(sendto, "Invalid hours")
    return
  if minfrac:
    try:
      minfrac=float(minfrac)
      if minfrac < 0 or minfrac > 1:
        raise RuntimeError("")
    except Exception,e:
      SendTo(sendto, "minfrac must be a number between 0 and 1")
      return
  else:
    minfrac = 0

  units = long(amount * coin)

  try:
    balance = redis.hget("balances",nick)
    if balance == None:
      balance = 0
    balance=long(balance)
    if units > balance:
      SendTo(sendto, "You only have %s" % (AmountToString(balance)))
      return

    now = time.time()
    userlist = userstable[chan].keys()
    userlist.remove(nick)
    for n in no_rain_to_nicks:
      userlist.remove(n)
    weights=dict()
    weight=0
    for n in userlist:
      t = userstable[chan][n]
      if t == None:
        continue
      dt = now - t
      if dt <= hours * 3600:
        w = (1 * (hours * 3600 - dt) + minfrac * (1 - (hours * 3600 - dt))) / (hours * 3600)
        weights[n] = w
        weight += w

    if len(weights) == 0:
      SendTo(sendto, "Nobody eligible for rain")
      return

#    if units < users:
#      SendTo(sendto, "This would mean not even an atomic unit per nick")
#      return

    pipe = redis.pipeline()
    pipe.hincrby("balances",nick,-units)
    rained_units = 0
    nnicks = 0
    minu=None
    maxu=None
    for n in weights:
      user_units = long(units * weights[n] / weight)
      if user_units <= 0:
        continue
      log_info("%s rained %s on %s (last active %f hours ago)" % (nick, AmountToString(user_units),n,GetTimeSinceActive(chan,n)/3600))
      pipe.hincrby("balances",n,user_units)
      rained_units += user_units
      if not minu or user_units < minu:
        minu = user_units
      if not maxu or user_units > maxu:
        maxu = user_units
      nnicks = nnicks+1

    if maxu == None:
      SendTo(sendto, "This would mean not even an atomic unit per nick")
      return

    pipe.execute()
    log_info("%s rained %s - %s (total %s, acc %s) on the %d nicks active in the last %f hours" % (nick, AmountToString(minu), AmountToString(maxu), AmountToString(units), AmountToString(rained_units), nnicks, hours))
    SendTo(sendto, "%s rained %s - %s on the %d nicks active in the last %f hours" % (nick, AmountToString(minu), AmountToString(maxu), nnicks, hours))

  except Exception,e:
    log_error('Rain: exception: %s' % str(e))
    SendTo(sendto, "An error has occured")
    return

def DisableWithdraw(nick,data):
  global withdraw_disabled
  if nick:
    log_warn('DisableWithdraw: disabled by %s' % nick)
  else:
    log_warn('DisableWithdraw: disabled')
  withdraw_disabled = True

def EnableWithdraw(nick,data):
  global withdraw_disabled
  log_info('EnableWithdraw: enabled by %s' % nick)
  withdraw_disabled = False

def CheckDisableWithdraw():
  if disable_withdraw_on_error:
    DisableWithdraw(None,None)

def IsValidAddress(address):
  if len(address) < address_length[0] or len(address) > address_length[1]:
    return False
  for prefix in address_prefix:
    if address.startswith(prefix):
      return True
  return False

def Withdraw(nick,data):
  address=data[0]
  if not IsValidAddress(address):
    SendTo(nick, "Invalid address")
    return
  amount = GetParam(data,1)
  if amount:
    try:
      famount=float(amount)
      if (famount < 0):
        raise RuntimeError("")
      amount = long(famount * coin)
      amount += withdrawal_fee
    except Exception,e:
      SendTo(nick, "Invalid amount")
      return

  if min_withdraw_amount <= 0 or withdrawal_fee <= 0 or min_withdraw_amount < withdrawal_fee:
    log_error('Withdraw: Inconsistent withdrawal settings')
    SendTo(nick, "An error has occured")
    return

  log_info("Withdraw: %s wants to withdraw %s to %s" % (nick, AmountToString(amount) if amount else "all", address))

  if withdraw_disabled:
    log_error('Withdraw: disabled')
    SendTo(nick, "Sorry, withdrawal is disabled due to a wallet error which requires admin assistance")
    return

  try:
    balance = redis.hget("balances",nick)
    if balance == None:
      balance = 0
    balance=long(balance)
  except Exception, e:
    log_error('Withdraw: exception: %s' % str(e))
    SendTo(nick, "An error has occured")
    return

  if amount:
    if amount > balance:
      log_info("Withdraw: %s trying to withdraw %s, but only has %s" % (nick,AmountToString(amount),AmountToString(balance)))
      SendTo(nick, "You only have %s" % AmountToString(balance))
      return
  else:
    amount = balance

  if amount <= 0 or amount < min_withdraw_amount:
    log_info("Withdraw: Minimum withdrawal balance: %s, %s cannot withdraw %s" % (AmountToString(min_withdraw_amount),nick,AmountToString(amount)))
    SendTo(nick, "Minimum withdrawal balance: %s, cannot withdraw %s" % (AmountToString(min_withdraw_amount),AmountToString(amount)))
    return
  try:
    fee = long(withdrawal_fee)
    topay = long(amount - fee)
    log_info('Withdraw: Raw: fee: %s, to pay: %s' % (str(fee), str(topay)))
    log_info('Withdraw: fee: %s, to pay: %s' % (AmountToString(fee), AmountToString(topay)))
    params = {
      'destinations': [{'address': address, 'amount': topay}],
      'payment_id': GetPaymentID(nick),
      'fee': fee,
      'mixin': 0,
      'unlock_time': 0,
    }
    j = SendWalletJSONRPCCommand("transfer",params)
  except Exception,e:
    log_error('Withdraw: Error in transfer: %s' % str(e))
    CheckDisableWithdraw()
    SendTo(nick,"An error has occured")
    return
  if not "result" in j:
    log_error('Withdraw: No result in transfer reply')
    CheckDisableWithdraw()
    SendTo(nick,"An error has occured")
    return
  result = j["result"]
  if not "tx_hash" in result:
    log_error('Withdraw: No tx_hash in transfer reply')
    CheckDisableWithdraw()
    SendTo(nick,"An error has occured")
    return
  tx_hash = result["tx_hash"]
  log_info('%s has withdrawn %s, tx hash %s' % (nick, amount, str(tx_hash)))
  SendTo(nick, "Tx sent: %s" % tx_hash)

  try:
    redis.hincrby("balances",nick,-amount)
  except Exception, e:
    log_error('Withdraw: FAILED TO SUBTRACT BALANCE: exception: %s' % str(e))
    CheckDisableWithdraw()

def SendJSONRPCCommand(host,port,method,params):
  try:
    http = httplib.HTTPConnection(host,port)
  except Exception,e:
    log_error('SendJSONRPCCommand: Error connecting to %s:%u: %s' % (host, port, str(e)))
    raise
  d = dict(id="0",jsonrpc="2.0",method=method,params=params)
  try:
    j = json.dumps(d).encode()
  except Exception,e:
    log_error('SendJSONRPCCommand: Failed to encode JSON: %s' % str(e))
    http.close()
    raise
  log_log('SendJSONRPCCommand: Sending json as body: %s' % j)
  headers = None
  try:
    http.request("POST","/json_rpc",body=j)
  except Exception,e:
    log_error('SendJSONRPCCommand: Failed to post request: %s' % str(e))
    http.close()
    raise
  response = http.getresponse()
  log_log('SendJSONRPCCommand: Received reply status: %s' % response.status)
  if response.status != 200:
    log_error('SendJSONRPCCommand: Error, not 200: %s' % str(response.status))
    http.close()
    raise RuntimeError("Error "+response.status)
  s = response.read()
  log_log('SendJSONRPCCommand: Received reply: %s' % str(s))
  try:
    j = json.loads(s)
  except Exception,e:
    log_error('SendJSONRPCCommand: Failed to decode JSON: %s' % str(e))
    http.close()
    raise
  http.close()
  return j

def SendHTMLCommand(host,port,method):
  try:
    http = httplib.HTTPConnection(host,port)
  except Exception,e:
    log_error('SendHTMLCommand: Error connecting to %s:%u: %s' % (host, port, str(e)))
    raise
  headers = None
  try:
    http.request("POST","/"+method)
  except Exception,e:
    log_error('SendHTMLCommand: Failed to post request: %s' % str(e))
    http.close()
    raise
  response = http.getresponse()
  log_log('SendHTMLCommand: Received reply status: %s' % response.status)
  if response.status != 200:
    log_error('SendHTMLCommand: Error, not 200: %s' % str(response.status))
    http.close()
    raise RuntimeError("Error "+response.status)
  s = response.read()
  log_log('SendHTMLCommand: Received reply: %s' % s)
  try:
    j = json.loads(s)
  except Exception,e:
    log_error('SendHTMLCommand: Failed to decode JSON: %s' % str(e))
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
  log_info('GetHeight: %s wants to know block height' % nick)
  try:
    j = SendBitmonerodHTMLCommand("getheight")
  except Exception,e:
    log_error('GetHeight: error: %s' % str(e))
    SendTo(nick,"An error has occured")
    return
  log_log('GetHeight: Got reply: %s' % str(j))
  if not "height" in j:
    log_error('GetHeight: Cannot see height in here')
    SendTo(nick, "Height not found")
    return
  height=j["height"]
  log_info('GetHeight: geight is %s' % str(height))
  SendTo(nick, "Height: %s" % str(height))

def GetTipbotBalance(nick,data):
  log_info('%s wants to know the tipbot balance' % nick)
  try:
    j = SendWalletJSONRPCCommand("getbalance",None)
  except Exception,e:
    SendTo(nick,"An error has occured")
    return
  if not "result" in j:
    log_error('GetTipbotBalance: result not found in reply')
    SendTo(nick, "An error has occured")
    return
  result = j["result"]
  if not "balance" in result:
    log_error('GetTipbotBalance: balance not found in result')
    SendTo(nick, "An error has occured")
    return
  if not "unlocked_balance" in result:
    log_error('GetTipbotBalance: unlocked_balance not found in result')
    SendTo(nick, "An error has occured")
    return
  balance = result["balance"]
  unlocked_balance = result["unlocked_balance"]
  log_log('GetTipbotBalance: balance: %s' % str(balance))
  log_log('GetTipbotBalance: unlocked_balance: %s' % str(unlocked_balance))
  pending = long(balance)-long(unlocked_balance)
  if pending < 0:
    log_error('GetTipbotBalance: Negative pending balance! balance %s, unlocked %s' % (str(balance),str(unlocked)))
    SendTo(nick, "An error has occured")
    return
  if pending == 0:
    log_info("GetTipbotBalance: Tipbot balance: %s" % AmountToString(balance))
    SendTo(nick,"Tipbot balance: %s" % AmountToString(balance))
  else:
    log_info("GetTipbotBalance: Tipbot balance: %s (%s pending)" % (AmountToString(unlocked_balance), AmountToString(pending)))
    SendTo(nick,"Tipbot balance: %s (%s pending)" % (AmountToString(unlocked_balance), AmountToString(pending)))

def DumpUsers(nick,data):
  log_info(str(userstable))

def Help(nick):
  time.sleep(0.5)
  SendTo(nick, "Help for %s:" % tipbot_name)
  SendTo(nick, "!isregistered - show whether you are currently registered with freenode")
  SendTo(nick, "!balance - show your current balance")
  time.sleep(0.5)
  SendTo(nick, "!tip <nick> <amount> - tip another user")
  SendTo(nick, "!rain <amount> [<users>] - rain some %s on everyone (or just a few)" % coin_name)
  SendTo(nick, "!rainactive <amount> <hours> [minfrac]- rain some %s on who was active recently" % coin_name)
  SendTo(nick, "!withdraw <address> [<amount>] - withdraw part or all of your balance")
  SendTo(nick, "!info - information about the tipbot")
  time.sleep(0.5)
  SendTo(nick, "You can send %s to your tipbot account:" % coin_name);
  SendTo(nick, "  Address: %s" % GetTipbotAddress())
  SendTo(nick, "  Payment ID: %s" % GetPaymentID(nick))
  SendTo(nick, "NO WARRANTY, YOU MAY LOSE YOUR COINS")
  time.sleep(0.5)
  SendTo(nick, "Minimum withdrawal: %s" % AmountToString(min_withdraw_amount))
  SendTo(nick, "Withdrawal fee: %s" % AmountToString(withdrawal_fee))
  if web_wallet_url:
    time.sleep(0.5)
    SendTo(nick, "No %s address ? You can use %s" % (coin_name, web_wallet_url))

def Info(nick):
  time.sleep(0.5)
  SendTo(nick, "Info for %s:" % tipbot_name)
  SendTo(nick, "Type !help for a list of commands")
  SendTo(nick, "NO WARRANTY, YOU MAY LOSE YOUR COINS")
  time.sleep(0.5)
  SendTo(nick, "By sending your %s to the tipbot, you are giving up their control" % coin_name)
  SendTo(nick, "to whoever runs the tipbot. Any tip you make/receive using the tipbot")
  SendTo(nick, "is obviously not anonymous. The tipbot wallet may end up corrupt, or be")
  SendTo(nick, "stolen, the server compromised, etc. While I hope this won't be the case,")
  time.sleep(0.5)
  SendTo(nick, "I will not offer any warranty whatsoever for the use of the tipbot or the")
  SendTo(nick, "return of any %s. Use at your own risk." % coin_name)
  SendTo(nick, "That being said, I hope you enjoy using it :)")

def InitScanBlockHeight():
  try:
    scan_block_height = redis.get("scan_block_height")
    scan_block_height = long(scan_block_height)
  except Exception,e:
    try:
      redis.set("scan_block_height",0)
    except Exception,e:
      log_error('Failed to initialize scan_block_height: %s' % str(e))

def UpdateCoin():
  global last_wallet_update_time
  if last_wallet_update_time == None:
    last_wallet_update_time = 0
  t=time.time()
  dt = t - last_wallet_update_time
  if dt < wallet_update_time:
    return
  try:
    try:
      scan_block_height = redis.get("scan_block_height")
      scan_block_height = long(scan_block_height)
    except Exception,e:
      log_error('Failed to get scan_block_height: %s' % str(e))
      last_wallet_update_time = time.time()
      return

    full_payment_ids = redis.hgetall("paymentid")
    #print 'Got full payment ids: %s' % str(full_payment_ids)
    payment_ids = []
    for pid in full_payment_ids:
      payment_ids.append(pid)
    #print 'Got payment ids: %s' % str(payment_ids)
    params = {
      "payment_ids": payment_ids,
      "min_block_height": scan_block_height
    }
    j = SendWalletJSONRPCCommand("get_bulk_payments",params)
    #print 'Got j: %s' % str(j)
    if "result" in j:
      result = j["result"]
      if "payments" in result:
        payments = result["payments"]
        log_info('UpdateCoin: Got %d payments' % len(payments))
        for p in payments:
          log_log('UpdateCoin: Looking at payment %s' % str(p))
          bh = p["block_height"]
          if bh > scan_block_height:
            scan_block_height = bh
        log_log('UpdateCoin: seen payments up to block %d' % scan_block_height)
        try:
          pipe = redis.pipeline()
          pipe.set("scan_block_height", scan_block_height)
          log_log('UpdateCoin: processing payments')
          for p in payments:
            payment_id=p["payment_id"]
            tx_hash=p["tx_hash"]
            amount=p["amount"]
            try:
              recipient = GetNickFromPaymendID(payment_id)
              log_info('UpdateCoin: Found payment %s to %s for %s' % (tx_hash,recipient, AmountToString(amount)))
              pipe.hincrby("balances",recipient,amount);
            except Exception,e:
              log_error('UpdateCoin: No nick found for payment id %s, tx hash %s, amount %s' % (payment_id, tx_hash, amount))
          log_log('UpdateCoin: Executing received payments pipeline')
          pipe.execute()
        except Exception,e:
          log_error('UpdateCoin: failed to set scan_block_height: %s' % str(e))
      else:
        log_log('UpdateCoin: No payments in get_bulk_payments reply')
    else:
      log_error('UpdateCoin: No results in get_bulk_payments reply')
  except Exception,e:
    log_error('UpdateCoin: Failed to get bulk payments: %s' % str(e))
  last_wallet_update_time = time.time()

def UpdateLastActiveTime(chan,nick):
  if not chan in userstable:
    log_error("UpdateLastActiveTime: %s spoke in %s, but %s not found in users table" % (nick, chan, chan))
    userstable[chan] = dict()
  if not nick in userstable[chan]:
    log_error("UpdateLastActiveTime: %s spoke in %s, but was not found in that channel's users table" % (nick, chan))
    userstable[chan][nick] = None
  userstable[chan][nick] = time.time()

def GetTimeSinceActive(chan,nick):
  if not chan in userstable:
    log_error("GetTimeSinceActive: channel %s not found in users table" % chan)
    return None
  if not nick in userstable[chan]:
    log_error("GetTimeSinceActive: %s not found in channel %s's users table" % (nick, chan))
    return None
  t = userstable[chan][nick]
  if t == None:
    return None
  dt = time.time() - t
  if dt < 0:
    log_error("GetTimeSinceActive: %s active in %s in the future" % (nick, chan))
    return None
  return dt

def GetActiveNicks(chan,seconds):
  nicks = []
  if not chan in userstable:
    return []
  now = time.time()
  for nick in userstable[chan]:
    t = userstable[chan][nick]
    if t == None:
      continue
    dt = now - t
    if dt < 0:
      log_error("GetActiveNicks: %s active in %s in the future" % (nick, chan))
      continue
    if dt < seconds:
      nicks.append(nick)
  return nicks

def ShowActivity(nick,data):
  achan=data[0]
  anick=data[1]
  activity = GetTimeSinceActive(achan,anick)
  if activity:
    SendTo(nick,"%s was active in %s %f seconds ago" % (anick,achan,activity))
  else:
    SendTo(nick,"%s was never active in %s" % (anick,achan))

#def Op(to_op, chan):
#    SendIRC( 'MODE ' + chan + ' +o: ' + to_op)
#
#def DeOp(to_deop, chan):
#    SendIRC( 'MODE ' + chan + ' -o: ' + to_deop)
#
#def Voice(to_v, chan):
#    SendIRC( 'MODE ' + chan + ' +v: ' + to_v)
#
#def DeVoice(to_dv, chan):
#    SendIRC( 'MODE ' + chan + ' -v: ' + to_dv)
#------------------------------------------------------------------------------#

buffered_data = ""
def getline(s):
  global buffered_data
  idx = buffered_data.find("\n")
  if idx == -1:
    try:
      (r,w,x)=select.select([s.fileno()],[],[],1)
      if s.fileno() in r:
        newdata=s.recv(4096,socket.MSG_DONTWAIT)
      else:
        newdata = None
      if s.fileno() in x:
        log_error('getline: IRC socket in exception set')
        newdata = None
    except Exception,e:
      log_error('getline: Exception: %s' % str(e))
      # Broken pipe when we get kicked for spam
      if str(e).find("Broken pipe") != -1:
        raise
      newdata = None
    if newdata == None:
      return None
    buffered_data+=newdata
  idx = buffered_data.find("\n")
  if idx == -1:
    ret = buffered_data
    buffered_data = ""
    return ret
  ret = buffered_data[0:idx+1]
  buffered_data = buffered_data[idx+1:]
  return ret



connect_to_irc(irc_network,irc_port)
redis = connect_to_redis(redis_host,redis_port)
InitScanBlockHeight()

while True:
    action = None
    try:
      data = getline(irc)
    except Exception,e:
      log_warn('Exception fron getline, we were probably disconnected, reconnecting in 5 seconds')
      time.sleep(5)
      last_ping_time = time.time()
      connect_to_irc(irc_network,irc_port)
      continue

    # All that must be done even when nothing from IRC - data may be None here
    UpdateCoin()

    if data == None:
      if time.time() - last_ping_time > irc_timeout_seconds:
        log_warn('%s seconds without PING, reconnecting in 5 seconds' % irc_timeout_seconds)
        time.sleep(5)
        last_ping_time = time.time()
        connect_to_irc(irc_network,irc_port)
      continue

    data = data.strip("\r\n")
    log_IRCRECV(data)

    # consider any IRC data as a ping
    last_ping_time = time.time()

    if data.find ( 'Welcome to the freenode Internet Relay Chat Network' ) != -1:
      userstable = dict()
      registered_users.clear()
      SendTo("nickserv", "IDENTIFY %s" % GetPassword())
      Join(irc_homechan)
      #ScanWho(None,[irc_homechan])

    if data.find ( 'PING' ) == 0:
      log_log('Got PING, replying PONG')
      last_ping_time = time.time()
      SendIRC ( 'PONG ' + data.split() [ 1 ])
      continue

    if data.find('ERROR :Closing Link:') == 0:
      log_warn('We were kicked from IRC, reconnecting in 5 seconds')
      time.sleep(5)
      last_ping_time = time.time()
      connect_to_irc(irc_network,irc_port)
      continue

    #--------------------------- Action check --------------------------------#
    if data.find(':') == -1:
      continue

    try:
        cparts = data.split(':')
        if len(cparts) < 2:
            continue
        if len(cparts) >= 3:
          text = cparts[2]
        else:
          text = ""
        parts = cparts[1].split(' ')
        who = parts[0]
        action = parts[1]
        chan = parts[2]
    except Exception, e:
        log_error('main parser: Exception, continuing: %s' % str(e))
        continue

    if action == None:
        continue

    #print 'text: ', text
    #print 'who: ', who
    #print 'action: ', action
    #print 'chan: ', chan

#    if data.find('#') != -1:
#        action = data.split('#')[0]
#        action = action.split(' ')[1]

#    if data.find('NICK') != -1:
#        if data.find('#') == -1:
#            action = 'NICK'

    #----------------------------- Actions -----------------------------------#
    try:
      if action == 'NOTICE':
        if who == "NickServ!NickServ@services.":
            #if text.find('Information on ') != -1:
            #    ns_nick = text.split(' ')[2].strip("\002")
            #    print 'NickServ says %s is registered' % ns_nick
            #    PerformNextAction(ns_nick, True)
            #elif text.find(' is not registered') != -1:
            #    ns_nick = text.split(' ')[0].strip("\002")
            #    print 'NickServ says %s is not registered' % ns_nick
            #    PerformNextAction(ns_nick, False)
            if text.find(' ACC ') != -1:
              stext  = text.split(' ')
              ns_nick = stext[0]
              ns_acc = stext[1]
              ns_status = stext[2]
              if ns_acc == "ACC":
                if ns_status == "3":
                  log_info('NickServ says %s is identified' % ns_nick)
                  PerformNextAction(ns_nick, True)
                else:
                  log_info('NickServ says %s is not identified' % ns_nick)
                  PerformNextAction(ns_nick, False)
              else:
                log_error('ACC line not as expected...')

      elif action == '352':
        try:
          who_chan = parts[3]
          who_chan_user = parts[7]
          if not who_chan_user in userstable[who_chan]:
            userstable[who_chan][who_chan_user] = None
          log_log("New list of users in %s: %s" % (who_chan, str(userstable[who_chan].keys())))
        except Exception,e:
          log_error('Failed to parse "who" line: %s: %s' % (data, str(e)))

      elif action == '353':
        try:
          who_chan = parts[4]
          who_chan_users = cparts[2].split(" ")
          for who_chan_user in who_chan_users:
            if not who_chan_user in userstable[who_chan]:
              if who_chan_user[0] == "@":
                who_chan_user = who_chan_user[1:]
              userstable[who_chan][who_chan_user] = None
          log_log("New list of users in %s: %s" % (who_chan, str(userstable[who_chan].keys())))
        except Exception,e:
          log_error('Failed to parse "who" line: %s: %s' % (data, str(e)))

      elif action == 'PRIVMSG':
        UpdateLastActiveTime(chan,GetNick(who))
        exidx = text.find('!')
        if exidx != -1 and len(text)>exidx+1 and text[exidx+1] in string.ascii_letters:
            cmd = text.split('!')[1]
            cmd = cmd.split(' ')
            cmd[0] = cmd[0].strip(' \t\n\r')

            if chan[0] == '#':
              sendto=chan
            else:
              sendto=GetNick(who)
            log_log('Found command: "%s" in channel "%s", replying to %s' % (str(cmd), str(chan), sendto))

            #if cmd[0] == 'join':
            #    Join('#' + cmd[1])
            #elif cmd[0] == 'part':
            #    Part('#' + cmd[1])
            if cmd[0] == 'help':
                Help(GetNick(who))
            elif cmd[0] == 'isregistered':
                CheckRegistered(GetNick(who),SendTo,"You are registered",SendTo,"You are not registered")
            elif cmd[0] == 'balance':
                CheckRegistered(GetNick(who),GetBalance,[sendto],SendTo,"You must be registered with Freenode to query balance")
            elif cmd[0] == 'tip':
                if len(cmd) == 3:
                    parms=[sendto]
                    parms.extend(cmd[1:])
                    CheckRegistered(GetNick(who),Tip,parms,SendTo,"You must be registered with Freenode to tip")
                else:
                    SendTo(GetNick(who), "Usage: !tip nick amount");
            elif cmd[0] == 'withdraw':
                if len(cmd) == 2 or len(cmd) == 3:
                    CheckRegistered(GetNick(who),Withdraw,cmd[1:],SendTo,"You must be registered with Freenode to withdraw")
                else:
                    SendTo(GetNick(who), "Usage: !withdraw address");
            elif cmd[0] == 'info':
                Info(GetNick(who))
            elif cmd[0] == 'rain':
                if chan[0] == '#':
                  if len(cmd) == 2 or len(cmd) == 3:
                    parms=[chan]
                    parms.extend(cmd[1:])
                    CheckRegistered(GetNick(who),Rain,parms,SendTo,"You must be registered with Freenode to rain")
                  else:
                    SendTo(sendto, "Usage: !rain amount [users]");
                else:
                  SendTo(sendto, "Raining can only be done in a channel")
            elif cmd[0] == 'rainactive':
                if chan[0] == '#':
                  if len(cmd) == 3 or len(cmd) == 4:
                    parms=[chan]
                    parms.extend(cmd[1:])
                    CheckRegistered(GetNick(who),RainActive,parms,SendTo,"You must be registered with Freenode to rain")
                  else:
                    SendTo(sendto, "Usage: !rain amount [users]");
                else:
                  SendTo(sendto, "Raining can only be done in a channel")
            # admin commands
            elif cmd[0] == 'height':
                CheckAdmin(GetNick(who),GetHeight,None,SendTo,"You must be admin")
            elif cmd[0] == 'tipbot_balance':
                CheckAdmin(GetNick(who),GetTipbotBalance,None,SendTo,"You must be admin")
            elif cmd[0] == 'addbalance':
                CheckAdmin(GetNick(who),AddBalance,cmd[1],SendTo,"You must be admin")
            elif cmd[0] == 'scanwho':
                CheckAdmin(GetNick(who),ScanWho,[chan],SendTo,"You must be admin")
            elif cmd[0] == 'enable_withdraw':
                CheckAdmin(GetNick(who),EnableWithdraw,None,SendTo,"You must be admin")
            elif cmd[0] == 'disable_withdraw':
                CheckAdmin(GetNick(who),DisableWithdraw,None,SendTo,"You must be admin")
            elif cmd[0] == 'dump_users':
                CheckAdmin(GetNick(who),DumpUsers,None,SendTo,"You must be admin")
            elif cmd[0] == 'show_activity':
                if len(cmd)==3:
                  CheckAdmin(GetNick(who),ShowActivity,cmd[1:],SendTo,"You must be admin")
                else:
                  SendTo(sendto,"Usage: show_activity channel nick")
            else:
                SendTo(GetNick(who), "Invalid command, try !help")

      elif action == 'JOIN':
        nick = GetNick(who)
        log_info('%s joined the channel' % nick)
        if not chan in userstable:
          userstable[chan] = dict()
        if nick in userstable[chan]:
          log_warn('%s joined, but already in %s' % (nick, chan))
        else:
          userstable[chan][nick] = None
        log_log("New list of users in %s: %s" % (chan, str(userstable[chan].keys())))

      elif action == 'PART':
        nick = GetNick(who)
        log_info('%s left the channel' % nick)
        if not nick in userstable[chan]:
          log_warn('%s left, but was not in %s' % (nick, chan))
        else:
          del userstable[chan][nick]
        log_log("New list of users in %s: %s" % (chan, str(userstable[chan].keys())))

      elif action == 'QUIT':
        nick = GetNick(who)
        log_info('%s quit' % nick)
        removed_list = ""
        for chan in userstable:
          log_log("Checking in %s" % chan)
          if nick in userstable[chan]:
            removed_list = removed_list + " " + chan
            del userstable[chan][nick]
            log_log("New list of users in %s: %s" % (chan, str(userstable[chan].keys())))

      elif action == 'NICK':
        nick = GetNick(who)
        new_nick = text
        log_info('%s renamed to %s' % (nick, new_nick))
        for c in userstable:
          log_log('checking %s' % c)
          if nick in userstable[c]:
            del userstable[c][nick]
            if new_nick in userstable[c]:
              log_warn('%s is the new name of %s, but was already in %s' % (new_nick, nick, c))
            else:
              userstable[c][new_nick] = None
          log_log("New list of users in %s: %s" % (c, str(userstable[c].keys())))

    except Exception,e:
      log_error('Exception in top level action processing: %s' % str(e))

