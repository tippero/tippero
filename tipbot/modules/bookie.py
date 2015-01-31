#!/bin/python
#
# Cryptonote tipbot - bookie commands
# Copyright 2015 moneromooo
#
# The Cryptonote tipbot is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published
# by the Free Software Foundation; either version 2, or (at your option)
# any later version.
#

import sys
import os
import redis
import string
import random
import tipbot.config as config
from tipbot.log import log_error, log_warn, log_info, log_log
import tipbot.coinspecs as coinspecs
from tipbot.utils import *
from tipbot.command_manager import *
from tipbot.redisdb import *
from tipbot.betutils import *

def GetActiveBooks():
  return redis_hgetall('bookie:active')

def SweepClosingTimes():
  books = GetActiveBooks()
  if not books:
    return
  now=time.time()
  for book_index in books.keys():
    book_index = long(book_index)
    tname = "bookie:%d" % book_index
    if redis_hexists(tname,'closing_time'):
      closing_time=float(redis_hget(tname,'closing_time'))
      if closing_time<=now and not redis_hget(tname,'closed'):
        book_name=redis_hget(tname,'name')
        redis_hset(tname,'closed',1)
        log_info('Closing book #%d (%s) as scheduled, dt %s' % (book_index, book_name, TimeToString(now-closing_time)))

def Bookie(link,cmd):
  identity=link.identity()

  name = GetParam(cmd,1)
  if not name:
    link.send('usage: !bookie <name> <outcome1> <outcome2> [<outcome3>...]')
    return
  outcomes = cmd[2:]
  if len(outcomes) < 2:
    link.send('usage: !bookie <name> <outcome1> <outcome2> [<outcome3>...]')
    return

  active_books = GetActiveBooks()
  if active_books and name in active_books.values():
    link.send('A book is already active with that name')
    return

  book_index=long(redis_get('bookie:last_book') or 0)
  book_index += 1
  tname = "bookie:%d" % book_index

  log_info('%s opens book #%d for %s, with outcomes %s' % (identity, book_index, name, str(outcomes)))
  try:
    p = redis_pipeline()
    p.hset(tname,'name',name)
    for o in outcomes:
      p.sadd(tname+':outcomes',o)
    p.hset('bookie:active',book_index,name)
    redis_set('bookie:last_book',book_index)
    p.execute()
  except Exception,e:
    log_error('Bookie: Failed to register book for %s with outcomes %s: %s' % (name, str(outcomes), str(e)))
    link.send('Failed to create book')
    return
  link.send('%s opens book #%d for %s, with outcomes: %s' % (link.user.nick, book_index, name, ", ".join(outcomes)))

def Cancel(link,cmd):
  identity=link.identity()

  SweepClosingTimes()

  active_books=GetActiveBooks()
  if len(active_books) == 0:
    link.send('There is no open book to cancel')
    return

  name = GetParam(cmd,1)
  if name:
    if not name in active_books.values():
      link.send('Book not found')
      return
    book_index = long(active_books.keys()[active_books.values().index(name)])
  else:
    if len(active_books) > 1:
      link.send('There are several open books, specify the one to cancel: %s' % ", ".join(active_books.values()))
      return
    book_index = long(active_books.keys()[0])

  tname='bookie:%d' % book_index
  book_name=redis_hget(tname,'name')

  log_info('Cancelling book %d (%s)' % (book_index, book_name))
  try:
    p = redis_pipeline()
    bettors = redis_smembers(tname+':bettors')
    refundmsg = []
    for bettor in bettors:
      units = long(redis_hget(tname,bettor+":units"))
      log_info('Refunding %s to %s' % (AmountToString(units),bettor))
      p.hincrby('balances',bettor,units)
      p.hincrby('earmarked','bookie',-units)
      refundmsg.append('%s to %s' % (AmountToString(units), NickFromIdentity(bettor)))
    p.hdel('bookie:active',book_index)
    p.execute()
    if len(refundmsg) == 0:
      link.send('Book %s cancelled, nobody had bet' % book_name)
    else:
      link.send('Book %s cancelled, refunding %s' % (book_name, ", ".join(refundmsg)))
  except Exception,e:
    log_error('Cancel: Failed to cancel book: %s' % str(e))
    link.send('Failed to cancel book %s' % book_name)
    return

def Close(link,cmd):
  identity=link.identity()

  SweepClosingTimes()

  active_books=GetActiveBooks()
  if len(active_books) == 0:
    link.send('There is no open book to close')
    return

  name = GetParam(cmd,1)
  if name:
    if not name in active_books.values():
      link.send('Book not found')
      return
    book_index = long(active_books.keys()[active_books.values().index(name)])
  else:
    if len(active_books) > 1:
      link.send('There are several open books, specify the one to close: %s' % ", ".join(active_books.values()))
      return
    book_index = long(active_books.keys()[0])

  tname = "bookie:%d" % book_index
  book_name=redis_hget(tname,'name')

  log_info('Closing book %d' % book_index)
  try:
    redis_hset(tname,'closed',1)
  except Exception,e:
    log_error('Failed to close book: %s' % str(e))
    link.send('An error occured')
    return
  link.send('%s closed book #%d (%s) to new bets' % (link.user.nick, book_index, book_name))

def ScheduleClose(link,cmd):
  identity=link.identity()

  SweepClosingTimes()

  active_books=GetActiveBooks()
  if len(active_books) == 0:
    link.send('There is no open book to close')
    return

  if GetParam(cmd,2):
    name = GetParam(cmd,1)
    if not name in active_books.values():
      link.send('Book not found')
      return
    book_index = long(active_books.keys()[active_books.values().index(name)])
    parm_offset = 1
  else:
    if len(active_books) > 1:
      link.send('There are several open books, specify the one to close: %s' % ", ".join(active_books.values()))
      return
    book_index = long(active_books.keys()[0])
    parm_offset = 0

  tname = "bookie:%d" % book_index
  book_name=redis_hget(tname,'name')

  try:
    minutes = float(GetParam(cmd,1+parm_offset))
  except Exception,e:
    log_error('error getting minutes: %s' % str(e))
    link.send('usage: schedule_close [<event name>] <minutes>')
    return
  if minutes < 0:
    log_error('error: negative minutes: %f' % minutes)
    link.send('minutes to closing must not be negative')
    return

  try:
    redis_hset(tname,'closing_time',time.time()+minutes*60)
  except Exception,e:
    log_error('error setting closing time: %s' % str(e))
    link.send('Failed to schedule closing time')
    return
  link.send('Book #%d (%s) will be closed to new bets in %s' % (book_index, book_name, TimeToString(minutes*60)))

def Book(link,cmd):
  identity=link.identity()

  SweepClosingTimes()

  active_books=GetActiveBooks()
  if len(active_books) == 0:
    link.send('The book is empty')
    return

  for book_index in active_books.keys():
    book_index = long(book_index)
    tname='bookie:%s' % book_index
    try:
      name = redis_hget(tname,'name')
      outcomes = redis_smembers(tname+':outcomes')
      outcome = redis_hget(tname,identity+":outcome")
      units = redis_hget(tname,identity+":units")
    except Exception,e:
      log_error('Book: Failed to retrieve book %d: %s' % (book_index, str(e)))
      link.send('An error occured')
      return
    link.send('Book #%d is for %s, with outcomes %s' % (book_index, name, ", ".join(outcomes)))
    msg = []
    outcomes = redis_smembers(tname+':outcomes')
    for o in outcomes:
      ou = long(redis_hget(tname+":bets",o) or 0)
      if ou > 0:
        msg.append('%s are on %s' % (AmountToString(ou),o))
    if not msg:
      msg = ["There are no bets placed for %s yet" % name]
    link.send('%s' % ", ".join(msg))
    if redis_hget(tname,'closed'):
      link.send('This book is closed to new bets')
    elif redis_hexists(tname,'closing_time'):
      try:
        closing_time=float(redis_hget(tname,'closing_time'))
        link.send('This book closes to new bets in %s' % (TimeToString(closing_time-time.time())))
      except Exception,e:
        log_error('Failed to get closing time: %s' % (str(e)))
    if outcome:
      link.send('%s has %s on %s' % (NickFromIdentity(identity), AmountToString(units), outcome))
    else:
      if not redis_hget(tname,'closed'):
        link.send('%s did not bet on this book yet' % NickFromIdentity(identity))

def Bet(link,cmd):
  identity=link.identity()

  SweepClosingTimes()

  active_books=GetActiveBooks()
  if len(active_books) == 0:
    link.send('The book is empty')
    return

  if GetParam(cmd,3):
    # name outcome amount
    name = GetParam(cmd,1)
    if not name in active_books.values():
      link.send('Book not found')
      return
    book_index = long(active_books.keys()[active_books.values().index(name)])
    parm_offset = 1
  else:
    # outcome amount
    if len(active_books) > 1:
      link.send('There are several open books, specify the one to bet on: %s' % ", ".join(active_books.values()))
      return
    book_index = long(active_books.keys()[0])
    parm_offset = 0

  tname = "bookie:%d" % book_index
  book_name=redis_hget(tname,'name')

  if redis_hget(tname,'closed'):
    link.send('The %s book is closed to new bets' % book_name)
    return

  outcome = GetParam(cmd,1+parm_offset)
  amount = GetParam(cmd,2+parm_offset)
  if not outcome or not amount:
    link.send('usage: !bet [<event name>] <outcome> <amount>')
    return
  try:
    amount = float(amount)
  except Exception,e:
    link.send('usage: !bet [<event name>] <outcome> <amount>')
    return
  units = long(amount*coinspecs.atomic_units)
  if units <= 0:
    link.send("Invalid amount")
    return

  valid,reason = IsBetValid(link,amount,config.bookie_min_bet,config.bookie_max_bet,0,0,0)
  if not valid:
    log_info("Bookie: %s's bet refused: %s" % (identity, reason))
    link.send("%s: %s" % (link.user.nick, reason))
    return

  outcomes = redis_smembers(tname+':outcomes')
  if not outcome in outcomes:
    link.send("%s is not a valid outcome, try one of: %s" % (outcome, ", ".join(outcomes)))
    return
  if redis_hexists(tname,identity+":outcome"):
    previous_outcome = redis_hget(tname,identity+":outcome")
    if previous_outcome != outcome:
      link.send("%s: you can only bet on one outcome per book, and you already bet on %s" % (NickFromIdentity(identity),previous_outcome))
      return

  log_info('%s wants to bet %s on %s' % (identity, AmountToString(units), outcome))
  try:
    log_info('Bet: %s betting %s on outcome %s' % (identity, AmountToString(units), outcome))
    try:
      p = redis_pipeline()
      p.hincrby("balances",identity,-units)
      p.hincrby("earmarked","bookie",units)
      p.hincrby(tname+":bets",outcome,units)
      p.hincrby(tname,"bets",units)
      p.hset(tname,identity+":outcome",outcome)
      p.hincrby(tname,identity+":units",units)
      p.sadd(tname+":bettors",identity)
      p.execute()
      total_bet=long(redis_hget(tname,identity+":units"))
      if total_bet == units:
        link.send("%s has bet %s on %s for %s" % (NickFromIdentity(identity), AmountToString(units), outcome, book_name))
      else:
        link.send("%s has bet another %s on %s for %s, for a total of %s" % (NickFromIdentity(identity), AmountToString(units), outcome, book_name,AmountToString(total_bet)))
    except Exception, e:
      log_error("Bet: Error updating redis: %s" % str(e))
      link.send("An error occured")
      return
  except Exception, e:
    log_error('Bet: exception: %s' % str(e))
    link.send("An error has occured")

def Result(link,cmd):
  identity=link.identity()

  SweepClosingTimes()

  active_books=GetActiveBooks()
  if len(active_books) == 0:
    link.send('The book is empty')
    return

  if GetParam(cmd,2):
    # name outcome
    name = GetParam(cmd,1)
    if not name in active_books.values():
      link.send('Book not found')
      return
    book_index = long(active_books.keys()[active_books.values().index(name)])
    parm_offset = 1
  else:
    # outcome
    if len(active_books) > 1:
      link.send('There are several open books, specify the one to call result for: %s' % ", ".join(active_books.values()))
      return
    book_index = long(active_books.keys()[0])
    parm_offset = 0

  tname = "bookie:%d" % book_index
  book_name=redis_hget(tname,'name')

  outcome = GetParam(cmd,1+parm_offset)
  if not outcome:
    link.send('usage: !result [<event name>] <outcome>')
    return
  outcomes = redis_smembers(tname+':outcomes')
  if not outcome in outcomes:
    link.send("%s is not a valid outcome for %s, try one of: %s" % (outcome, book_name, ", ".join(outcomes)))
    return

  log_info('%s calls %s on book %d' % (identity, outcome, book_index))
  try:
    p = redis_pipeline()
    total_units_bet = long(redis_hget(tname,"bets") or 0)
    total_units_bet_by_winners = long(redis_hget(tname+":bets",outcome) or 0)
    resultmsg = []
    bettors = redis_smembers(tname+':bettors')
    p.hincrby("earmarked","bookie",-total_units_bet)
    for bettor in bettors:
      o = redis_hget(tname,bettor+":outcome")
      ounits = long(redis_hget(tname,bettor+":units"))
      if o == outcome:
        owinunits = long(total_units_bet * (1-config.bookie_fee) * ounits / total_units_bet_by_winners)
        if owinunits<ounits:
          owinunits=units
        resultmsg.append("%s wins %s" % (NickFromIdentity(bettor), AmountToString(owinunits)))
        p.hincrby("balances",bettor,owinunits)
      else:
        resultmsg.append("%s loses %s" % (NickFromIdentity(bettor), AmountToString(ounits)))
    p.hdel('bookie:active',book_index)
    p.execute()
    if len(bettors) == 0:
      resultmsg = ["nobody had bet"]
    log_info('Book outcome is %s - %s' % (outcome, ", ".join(resultmsg)))
    link.send('Book #%d (%s) outcome is %s - %s' % (book_index, book_name, outcome, ", ".join(resultmsg)))
  except Exception,e:
    log_error('Result: Failed to process result: %s' % str(e))
    link.send('An error occured')
    return


def Help(link):
  link.send_private("The bookie module allows you to bet on particular events")
  link.send_private("Basic usage: !bet outcome amount")
  link.send_private("Administrators can setup a book over any particular event")
  link.send_private("Anyone can then bet on one of the available outcomes until the book")
  link.send_private("closes to new bets (a player can bet only bet on one outcome per book)")
  link.send_private("After the event result is in, winners share the total amount bet")
  link.send_private("(minus bookie fee) pro rata to their original bet amount")
  link.send_private("Once placed, a bet may not be cancelled (unless the book itself")
  link.send_private("is cancelled, in which case every bettor gets a full refund)")
  link.send_private("Minimum bet %s, maximum bet %s" % (config.bookie_min_bet, config.bookie_max_bet ))



RegisterModule({
  'name': __name__,
  'help': Help,
})
RegisterCommand({
  'module': __name__,
  'name': 'bookie',
  'parms': '<event name> <outcome1> <outcome2> [<outcome3>...]',
  'function': Bookie,
  'admin': True,
  'registered': True,
  'help': "start a bookie game - bookie fee %.1f%%" % (float(config.bookie_fee)*100)
})
RegisterCommand({
  'module': __name__,
  'name': 'cancel',
  'parms': '[<event name>]',
  'function': Cancel,
  'admin': True,
  'registered': True,
  'help': "cancels a running book, refunding everyone who bet on it"
})
RegisterCommand({
  'module': __name__,
  'name': 'book',
  'function': Book,
  'registered': True,
  'help': "shows current book"
})
RegisterCommand({
  'module': __name__,
  'name': 'close',
  'parms': '[<event name>]',
  'function': Close,
  'admin': True,
  'registered': True,
  'help': "close a book to new bets"
})
RegisterCommand({
  'module': __name__,
  'name': 'schedule_close',
  'parms': '[<event name>] <minutes>',
  'function': ScheduleClose,
  'admin': True,
  'registered': True,
  'help': "schedule closing a book to new bets in X minutes"
})
RegisterCommand({
  'module': __name__,
  'name': 'result',
  'parms': '[<event name>] <outcome>',
  'function': Result,
  'admin': True,
  'registered': True,
  'help': "declare the result of a running book, paying winners"
})
RegisterCommand({
  'module': __name__,
  'name': 'bet',
  'parms': '[<event name>] <outcome> <amount>',
  'function': Bet,
  'registered': True,
  'help': "bet some %s on a particular outcome" % coinspecs.name
})
