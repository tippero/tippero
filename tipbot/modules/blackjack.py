#!/bin/python
#
# Cryptonote tipbot - blackjack commands
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
import hashlib
import time
import string
import random
import tipbot.config as config
from tipbot.log import log_error, log_warn, log_info, log_log
import tipbot.coinspecs as coinspecs
from tipbot.user import User
from tipbot.link import Link
from tipbot.utils import *
from tipbot.command_manager import *
from tipbot.redisdb import *
from tipbot.betutils import *

players = dict()
utf8users = set()

deck_cards = "234567890JQKA"
deck_scores = [2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10, 1]
deck_suits = [ "spades", "hearts", "diamonds", "clubs" ]
deck_unicode_suits_ordering = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 1]
deck_names = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']

def MakeNewDeck(decks,seed):
  deck = []
  for n in range(decks):
    for s in range(4):
      for c in range(13):
        deck.append(deck_cards[c]+":"+deck_suits[s])
  r = random.Random()
  r.seed(seed)
  r.shuffle(deck)
  return deck

def DrawCard(deck):
  card = deck[0]
  del deck[0]
  return card

def DrawForPlayer(link):
  identity=link.identity()
  card = DrawCard(players[identity]['deck'])
  players[identity]['player_hands'][players[identity]['player_current_hand']]['hand'].append(card)
  return card

def DrawForDealer(link):
  identity=link.identity()
  card = DrawCard(players[identity]['deck'])
  players[identity]['dealer_hand'].append(card)
  return card

def GetCardScore(card):
  idx = deck_cards.find(card.split(':')[0])
  return deck_scores[idx]

def GetCardName(card,utf8=False):
  parts = card.split(':')
  idx = deck_cards.find(parts[0])
  if utf8:
    suitidx = deck_suits.index(parts[1])
    name = chr(0b11110000) + chr(0b10011111)
    name = name + chr(0b10000010 + suitidx/2)
    name = name + chr(0b10000000 + ((suitidx+2)%4) * 0b10000 + deck_unicode_suits_ordering[idx])
    return name
  else:
    return deck_names[idx]

def GetHandScores(hand):
  score = [0]
  for card in hand:
    card_score = GetCardScore(card)
    for n in range(len(score)):
      score[n] = score[n] + card_score
    if card.split(':')[0] == 'A':
      idx = len(score)
      score.extend(score)
      while idx < len(score):
        score[idx] = score[idx] + 10
        idx = idx + 1
  return score

def GetHandScore(hand):
  scores = GetHandScores(hand)
  score = scores[0]
  for s in scores:
    if s > score and s <= 21:
      score = s
  return score

def IsSoftHand(hand):
  ace_found = False
  score = 0
  for card in hand:
    if card.split(':')[0] == 'A':
      if ace_found:
        score = score + 1
      else:
        score = score + 11
      ace_found = True
    else:
      score = score + GetCardScore(card)
  return ace_found and score <= 21

def GetPlayerCurrentHand(link):
  identity=link.identity()
  idx = players[identity]['player_current_hand']
  hand = players[identity]['player_hands'][idx]['hand']
  return hand

def GetPlayerCurrentHandScore(link):
  return GetHandScore(GetPlayerCurrentHand(link))

def HandToString(hand,utf8=False,hide_last=False,with_score=False):
  s = ""
  if hide_last:
    hand = hand[0:-1]
    hand.append('?')
  for card in hand:
    if s != "":
      if utf8:
        s = s + " "
      else:
        s = s + ", "
    if card == '?':
      if utf8:
        s = s + chr(0b11110000) + chr(0b10011111) + chr(0b10000010) + chr(0b10100000)
      else:
        s = s + card
    else:
      s = s + GetCardName(card,utf8)
  if not utf8:
    s = '['+ s + ']'
  if with_score and not hide_last:
    s = s + " (score " + str(GetHandScore(hand))+")"
  return s

def PlayerHandsToString(link,utf8=False,with_score=False):
  identity=link.identity()
  S = ""
  selected = players[identity]['player_current_hand']
  for hand in players[identity]['player_hands']:
    s = HandToString(hand['hand'],identity in utf8users,False,with_score)
    if selected == 0:
      s = ">>>" + s + "<<<"
    selected = selected - 1
    if S != "":
      S = S + ", "
    S = S + s
  return S

def UpdateBlackjackRecord(link,win,lose,units):
  try:
    RecordGameResult(link,"blackjack",win,lose,units)
  except Exception,e:
    link.send("An error has occured")

def UpdateSidebetRecord(link,sidebet,win,lose,units):
  try:
    RecordGameResult(link,"blackjack:%s"%sidebet,win,lose,units)
  except:
    link.send("An error has occured")

def SwitchToNextHand(link):
  identity=link.identity()
  log_log('switching to next hand, from current %d' % players[identity]['player_current_hand'])
  players[identity]['player_current_hand'] = players[identity]['player_current_hand'] + 1
  if players[identity]['player_current_hand'] < len(players[identity]['player_hands']):
    if not players[identity]['finished']:
      dealer_hand = players[identity]['dealer_hand']
      link.send("%s: Your hand is %s. Dealer's hand is %s" % (link.user.nick, PlayerHandsToString(link,True),HandToString(dealer_hand,identity in utf8users,True,False)))
  elif not players[identity]['finished']:
    DealerMove(link)

def IsBlackjack(hand):
  return len(hand) == 2 and GetHandScore(hand) == 21

def Win(link,blackjack):
  identity=link.identity()
  idx = players[identity]['player_current_hand']
  player_hand = players[identity]['player_hands'][idx]['hand']
  dealer_hand = players[identity]['dealer_hand']
  win_units = players[identity]['player_hands'][idx]['amount']
  if blackjack:
    win_units = win_units * 3 / 2
    link.send("%s wins %s on hand %d - BLACKJACK! - %s, dealer %s" % (link.user.nick, AmountToString(win_units), idx+1, PlayerHandsToString(link,True), HandToString(dealer_hand,identity in utf8users)))
  else:
    link.send("%s wins %s on hand %d - %s, dealer %s" % (link.user.nick, AmountToString(win_units), idx+1, PlayerHandsToString(link,True), HandToString(dealer_hand, identity in utf8users)))
  players[identity]['amount'] -= players[identity]['player_hands'][idx]['amount']
  players[identity]['player_hands'][idx]['finished'] = True
  UpdateBlackjackRecord(link,True,False,win_units)
  SwitchToNextHand(link)

def Lose(link,blackjack):
  identity=link.identity()
  idx = players[identity]['player_current_hand']
  player_hand = players[identity]['player_hands'][idx]['hand']
  dealer_hand = players[identity]['dealer_hand']
  lose_units = players[identity]['player_hands'][idx]['amount']
  if blackjack:
    link.send("%s loses %s on hand %d - %s, dealer BLACKJACK! %s" % (link.user.nick, AmountToString(lose_units), idx+1, PlayerHandsToString(link,True), HandToString(dealer_hand, identity in utf8users)))
  else:
    link.send("%s loses %s on hand %d - %s, dealer %s" % (link.user.nick, AmountToString(lose_units), idx+1, PlayerHandsToString(link,True), HandToString(dealer_hand, identity in utf8users)))
  players[identity]['amount'] -= players[identity]['player_hands'][idx]['amount']
  players[identity]['player_hands'][idx]['finished'] = True
  UpdateBlackjackRecord(link,False,True,lose_units)
  SwitchToNextHand(link)

def Draw(link,blackjack):
  identity=link.identity()
  idx = players[identity]['player_current_hand']
  player_hand = players[identity]['player_hands'][idx]['hand']
  dealer_hand = players[identity]['dealer_hand']
  if blackjack:
    link.send("%s pushes on hand %d - BLACKJACK vs BLACKJACK! - %s, dealer %s" % (link.user.nick, idx+1, PlayerHandsToString(link,True), HandToString(dealer_hand, identity in utf8users)))
  else:
    link.send("%s pushes on hand %d - %s, dealer %s" % (link.user.nick, idx+1, PlayerHandsToString(link,True), HandToString(dealer_hand, identity in utf8users)))
  players[identity]['amount'] -= players[identity]['player_hands'][idx]['amount']
  players[identity]['player_hands'][idx]['finished'] = True
  UpdateBlackjackRecord(link,False,False,0)
  SwitchToNextHand(link)

def CheckEndGame(link,force_end):
  identity=link.identity()
  player_score = GetPlayerCurrentHandScore(link)
  dealer_score = GetHandScore(players[identity]['dealer_hand'])
  dealer_blackjack = IsBlackjack(players[identity]['dealer_hand'])
  if dealer_score > 21:
    return Win(link,False)
  if player_score==21 and dealer_score==21:
    if dealer_blackjack:
      return Lose(link,True)
    else:
      return Draw(link,False)
  elif player_score==21:
    return Win(link,False)
  elif dealer_score==21:
    return Lose(link,dealer_blackjack)
  if force_end:
    if player_score > dealer_score:
      return Win(link,False)
    elif player_score < dealer_score:
      return Lose(link,False)
    else:
      return Draw(link,False)

def AreAllHandsFinished(link):
  identity=link.identity()
  for hand in players[identity]['player_hands']:
    if not hand['finished']:
      return False
  return True

def ShouldDealerHit(link):
  identity=link.identity()
  dealer_hand = players[identity]['dealer_hand']
  score = GetHandScore(dealer_hand)
  if score < 17:
    return True
  if score == 17 and IsSoftHand(dealer_hand):
    return True
  return False

def DealerMove(link):
  identity=link.identity()
  log_log('dealer move - finished: %d' % players[identity]['finished'])
  if AreAllHandsFinished(link):
    log_log('all hands finished, marking game as finished')
    players[identity]['finished'] = True
  if not players[identity]['finished']:
    if not IsBlackjack(players[identity]['dealer_hand']):
      while ShouldDealerHit(link):
        card = DrawForDealer(link)
        dealer_hand = players[identity]['dealer_hand']
        bustmsg = ""
        if GetHandScore(dealer_hand) > 21:
          bustmsg = " - Dealer busts!"
        link.send("%s: Dealer draws %s: %s%s" % (link.user.nick, GetCardName(card,identity in utf8users), HandToString(dealer_hand,identity in utf8users,False,True), bustmsg))
    players[identity]['finished'] = True
    players[identity]['player_current_hand'] = 0

  log_log('sweeping through open games')
  while players[identity]['player_current_hand'] < len(players[identity]['player_hands']):
    log_log('sweeping through hand %d' % players[identity]['player_current_hand'])
    if players[identity]['player_hands'][players[identity]['player_current_hand']]['finished']:
      log_log('%d is already finished, skipping' % players[identity]['player_current_hand'])
      players[identity]['player_current_hand'] = players[identity]['player_current_hand'] + 1
      continue
    CheckEndGame(link,True)
  log_log('done sweeping through open games')

  sidebets = players[identity]['sidebets']
  dealer_hand = players[identity]['dealer_hand']

  if sidebets['splits']:
    bet_units = sidebets['splits']
    nsplits = len(players[identity]['player_hands'])
    if nsplits == 1:
      link.send('%s did not split - you lose %s' % (link.user.nick, AmountToString(bet_units)))
      UpdateSidebetRecord(link,"splits",False,True,bet_units)

  if sidebets['buster']:
    bet_units = sidebets['buster']
    if GetHandScore(dealer_hand) > 21:
      cards = len(dealer_hand)
      if cards == 3:
        win_units = bet_units * 3 / 2
      elif cards == 4:
        win_units = bet_units * 3
      elif cards == 5:
        win_units = bet_units * 5
      elif cards == 6:
        win_units = bet_units * 11
      elif cards >= 7:
        win_units = bet_units * 21
      link.send('The dealer busted with %s cards - you win %s' % (cards, AmountToString(win_units)))
      UpdateSidebetRecord(link,"buster",True,False,win_units)
    else:
      link.send('The dealer did not bust - you lose %s' % (AmountToString(bet_units)))
      UpdateSidebetRecord(link,"buster",False,True,bet_units)

  del players[identity]

def GetNewShuffleSeed(link):
  identity=link.identity()
  try:
    if redis_hexists('blackjack:rolls',identity):
      rolls = redis_hget('blackjack:rolls',identity)
      rolls = long(rolls) + 1
    else:
      rolls = 1
  except Exception,e:
    log_error('Failed to prepare roll for %s: %s' % (identity, str(e)))
    raise

  try:
    s = GetServerSeed(link,'blackjack') + ":" + GetPlayerSeed(link,'blackjack') + ":" + str(rolls)
    seed = hashlib.sha256(s).hexdigest()
    redis_hset("blackjack:rolls",identity,rolls)
    return rolls, seed
  except Exception,e:
    log_error('Failed to roll for %s: %s' % (identity,str(e)))
    raise

def ParseSideBets(names,units):
  sidebets = {
    "total_amount_wagered": 0,
    "potential_loss": 0,
    "over13": None,
    "under13": None,
    "pair": None,
    "climber": None,
    "buster": None,
    "splits": None,
    "match": None,
    "addup": None,
  }
  if len(config.blackjack_sidebets) == 0:
    return sidebets, None

  wagered_amount = 0
  total_amount_wagered = 0
  potential_loss = 0
  payout = 0
  for name in names:
    name=name.strip()
    if name == "":
      continue
    if not name in config.blackjack_sidebets:
      return None, "Unavailable side bet: %s" % name
    if name == "over13":
      wagered_amount = units/2
      payout = wagered_amount
    elif name == "under13":
      wagered_amount = units/2
      payout = wagered_amount
    elif name == "pair":
      wagered_amount = units/2
      payout = wagered_amount * 10
    elif name == "climber":
      wagered_amount = units/2
      payout = wagered_amount * 21
    elif name == "buster":
      wagered_amount = units/2
      payout = wagered_amount * 11
    elif name == "splits":
      wagered_amount = units/2
      payout = wagered_amount * 21
    elif name == "match":
      wagered_amount = units/2
      payout = wagered_amount * 21
    elif name == "addup":
      wagered_amount = units/2
      payout = wagered_amount * 27
    else:
      return None, "Invalid side bet: %s" % name
    total_amount_wagered = total_amount_wagered + wagered_amount
    potential_loss = potential_loss + payout
    sidebets[name] = wagered_amount
  sidebets["total_amount_wagered"] = total_amount_wagered
  sidebets["potential_loss"] = potential_loss
  return sidebets, None

def GetBasicStrategyMove(link):
  identity=link.identity()
  player_hand = GetPlayerCurrentHand(link)
  player_has_soft_hand = IsSoftHand(player_hand)
  player_first_card = player_hand[0].split(':')[0]
  player_second_card = player_hand[1].split(':')[0]
  player_can_double = len(player_hand) == 2 and player_first_card != 'A'
  player_has_split = len(players[identity]['player_hands']) > 1
  player_can_split = len(player_hand) == 2 and len(players[identity]['player_hands']) < config.blackjack_split_to
  player_score = GetHandScore(player_hand)
  player_has_pair = player_first_card == player_second_card and len(player_hand)==2
  dealer_hand = players[identity]['dealer_hand']
  dealer_upcard = dealer_hand[0].split(':')[0]

  if player_score == 21:
    return "stand"

  if player_has_split:
    if player_first_card == 'A':
      return "stand"

  if player_has_pair:
    if player_first_card in ['8', 'A']:
      if player_can_split:
        return "split"
    if player_first_card in ['0', 'J', 'Q', 'K']:
      return "stand"
    if player_first_card == '9':
      if dealer_upcard in ['7', '0', 'J', 'Q', 'K', 'A']:
        return "stand"
      if player_can_split:
        return "split"
    if player_first_card in ['2', '3', '7']:
      if dealer_upcard in ['8', '9', '0', 'J', 'Q', 'K', 'A']:
        return "hit"
      if player_can_split:
        return "split"
    if player_first_card == '6':
      if dealer_upcard in ['7', '8', '9', '0', 'J', 'Q', 'K', 'A']:
        return "hit"
      if player_can_split:
        return "split"
    if player_first_card == '5':
      if dealer_upcard in ['0', 'J', 'Q', 'K', 'A']:
        return "hit"
      if player_can_double:
        return "double"
      else:
        return "hit"
    if player_first_card == '4':
      if dealer_upcard in ['5', '6']:
        if player_can_split:
          return "split"
      else:
        return "hit"

  if player_has_soft_hand:
    if player_score in [18, 19]:
      return "stand"
    if player_score == 17:
      if dealer_upcard in ['2', '7', '8']:
        return "stand"
      if dealer_upcard in ['3', '4', '5', '6']:
        if player_can_double:
          return "double"
        else:
          return "stand"
      return "hit"
    if player_score == 16:
      if dealer_upcard in ['3', '4', '5', '6']:
        if player_can_double:
          return "double"
        else:
          return "hit"
      return "hit"
    if player_score in [14, 15]:
      if dealer_upcard in ['4', '5', '6']:
        if player_can_double:
          return "double"
        else:
          return "hit"
      return "hit"
    if player_score in [12, 13]:
      if dealer_upcard in ['5', '6']:
        if player_can_double:
          return "double"
        else:
          return "hit"
      return "hit"
  else:
    if player_score >= 17:
      return "stand"
    if player_score >= 13:
      if dealer_upcard in ['7', '8', '9', '0', 'J', 'Q', 'K', 'A']:
        return "hit"
      else:
        return "stand"
    if player_score == 12:
      return "stand" if dealer_upcard in ['4', '5', '6'] else "hit"
    if player_score == 11:
      if dealer_upcard == 'A':
        return "hit"
      else:
        return "double" if player_can_double else "hit"
    if player_score == 10:
      if dealer_upcard in ['0', 'J', 'Q', 'K', 'A']:
        return "hit"
      else:
        return "double" if player_can_double else "hit"
    if player_score == 9:
      if dealer_upcard in ['3', '4', '5', '6']:
        return "double" if player_can_double else "hit"
      else:
        return "hit"
    if player_score >= 5:
      return "hit"

  log_error('GetBasicStrategyMove: missed a case: player %s, dealer %s' % (HandToString(player_hand), HandToString(dealer_hand)))
  return None

def RecordMove(link,actual):
  identity=link.identity()
  basic = GetBasicStrategyMove(link)
  log_info('%s %ss, basic strategy would %s' % (identity, actual, basic))
  try:
    p = redis_pipeline()
    tname="blackjack:strategy:"+identity
    alltname="blackjack:strategy:"
    p.hincrby(tname,"moves",1)
    if actual == basic:
      p.hincrby(tname,"matching",1)
    p.execute()
  except Exception,e:
    log_error('Failed to record move for %s: %s' % (identity, str(e)))

def Blackjack(link,cmd):
  identity=link.identity()
  if identity in players:
    link.send("%s: you already are in a game of blackjack" % link.user.nick)
    return
  try:
    amount=float(cmd[1])
    units=StringToUnits(cmd[1])
  except Exception,e:
    link.send("%s: usage: !blackjack amount" % link.user.nick)
    return

  sidebets, reason = ParseSideBets(cmd[2:],units)
  if not sidebets:
    link.send("%s: invalid side bet list: %s" % (link.user.nick, reason))
    return

  total_amount_wagered = amount + sidebets["total_amount_wagered"] / coinspecs.atomic_units
  total_units_wagered = units + sidebets["total_amount_wagered"]
  potential_loss = amount * 1.5 + sidebets["potential_loss"] / coinspecs.atomic_units
  potential_units_loss = long (potential_loss * coinspecs.atomic_units)
  log_info('%s bets a total of %s (%.16g), potential loss %s, side bets %s' % (identity, AmountToString(total_units_wagered), total_amount_wagered, AmountToString(potential_units_loss), str(sidebets)))
  valid,reason = IsBetValid(link,total_amount_wagered,config.blackjack_min_bet,config.blackjack_max_bet,potential_loss,config.blackjack_max_loss,config.blackjack_max_loss_ratio)
  if not valid:
    log_info("Dice: %s's bet refused: %s" % (identity, reason))
    link.send("%s: %s" % (link.user.nick, reason))
    return

  try:
    rolls, seed = GetNewShuffleSeed(link)
  except Exception,e:
    link.send("%s: An error occured" % link.user.nick)
    return

  players[identity] = {
    'deck': MakeNewDeck(config.blackjack_decks,seed),
    'amount': total_units_wagered,
    'base_amount': units,
    'player_hands': [dict({
      'amount': units,
      'hand': [],
      'finished': False,
    })],
    'player_current_hand': 0,
    'dealer_hand': [],
    'finished': False,
    'insurance': False,
    'sidebets': sidebets,
  }
  DrawForPlayer(link)
  DrawForDealer(link)
  DrawForPlayer(link)
  DrawForDealer(link)
  if False: # TEST FOR SPLIT
    if False:
      players[identity]['player_hands'][0]['hand'][0].split(':')[0] = 'A'
    players[identity]['player_hands'][0]['hand'][1] = players[identity]['player_hands'][0]['hand'][0]
  dealer_hand = players[identity]['dealer_hand']
  link.send("%s: Game %d starts. You draw %s. Dealer draws %s" % (link.user.nick, rolls, PlayerHandsToString(link,True),HandToString(dealer_hand,identity in utf8users,True,False)))

  player_hand = players[identity]['player_hands'][0]['hand']
  dealer_hand = players[identity]['dealer_hand']
  plain_score = GetCardScore(player_hand[0])+GetCardScore(player_hand[1])
  if sidebets['over13']:
    bet_units = sidebets['over13']
    if plain_score > 13:
      win_units = bet_units
      link.send('%s: your first two cards total %d, over 13 - you win %s' % (link.user.nick, plain_score, AmountToString(win_units)))
      UpdateSidebetRecord(link,"over13",True,False,win_units)
    else:
      link.send('%s: your first two cards total %d, not over 13 - you lose %s' % (link.user.nick, plain_score, AmountToString(bet_units)))
      UpdateSidebetRecord(link,"over13",False,True,bet_units)
  if sidebets['under13']:
    bet_units = sidebets['under13']
    if plain_score < 13:
      win_units = bet_units
      link.send('%s: your first two cards total %d, under 13 - you win %s' % (link.user.nick, plain_score, AmountToString(win_units)))
      UpdateSidebetRecord(link,"under13",True,False,win_units)
    else:
      link.send('%s: your first two cards total %d, not under 13 - you lose %s' % (link.user.nick, plain_score, AmountToString(bet_units)))
      UpdateSidebetRecord(link,"under13",False,True,bet_units)
  if sidebets['pair']:
    bet_units = sidebets['pair']
    if player_hand[0].split(':')[0] == player_hand[1].split(':')[0]:
      win_units = bet_units * 10
      link.send('%s: your first two cards are a pair - you win %s' % (link.user.nick, AmountToString(win_units)))
      UpdateSidebetRecord(link,"pair",True,False,win_units)
    else:
      link.send('%s: your first two cards are not a pair - you lose %s' % (link.user.nick, AmountToString(bet_units)))
      UpdateSidebetRecord(link,"pair",False,True,bet_units)
  if sidebets['climber']:
    bet_units = sidebets['climber']
    if GetHandScore(player_hand) == 20:
      if dealer_hand[0].split(':')[0] == 'A':
        win_units = bet_units * 21
      else:
        win_units = bet_units * GetCardScore(dealer_hand[0])
      link.send('%s: your first two cards score 20, dealer\'s first card is %s - you win %s' % (link.user.nick, GetCardName(dealer_hand[0],identity in utf8users), AmountToString(win_units)))
      UpdateSidebetRecord(link,"climber",True,False,win_units)
    else:
      link.send('%s: your first two cards do not score 20 - you lose %s' % (link.user.nick,AmountToString(bet_units)))
      UpdateSidebetRecord(link,"climber",False,True,bet_units)
  if sidebets['match']:
    bet_units = sidebets['match']
    if player_hand[0].split(':')[0] == dealer_hand[0].split(':')[0] and player_hand[1].split(':')[0] == dealer_hand[0].split(':')[0]:
      win_units = bet_units * 21
      link.send('%s: your first two cards match the dealer\'s - you win %s' % (link.user.nick,AmountToString(win_units)))
      UpdateSidebetRecord(link,"match",True,False,win_units)
    elif player_hand[0].split(':')[0] == dealer_hand[0].split(':')[0] or player_hand[1].split(':')[0] == dealer_hand[0].split(':')[0]:
      win_units = bet_units * 5
      link.send('%s: one of your first two cards match the dealer\'s - you win %s' % (link.user.nick,AmountToString(win_units)))
      UpdateSidebetRecord(link,"match",True,False,win_units)
    else:
      link.send('%s: none of your first two cards match the dealer\'s - you lose %s' % (link.user.nick,AmountToString(bet_units)))
      UpdateSidebetRecord(link,"match",False,True,bet_units)
  if sidebets['addup']:
    bet_units = sidebets['addup']
    scores = GetHandScores(player_hand)
    if GetCardScore(dealer_hand[0]) in scores:
      win_units = bet_units * 25
      link.send('%s: your first two cards\' scores add up to the dealer\'s - you win %s' % (link.user.nick,AmountToString(win_units)))
      UpdateSidebetRecord(link,"addup",True,False,win_units)
    else:
      link.send('%s: your first two cards\' scores do not add up to the dealer\'s - you lose %s' % (link.user.nick,AmountToString(bet_units)))
      UpdateSidebetRecord(link,"addup",False,True,bet_units)

  if IsBlackjack(GetPlayerCurrentHand(link)):
    if IsBlackjack(dealer_hand):
      Draw(link,True)
    else:
      Win(link,True)
    return

  if config.blackjack_insurance:
    if dealer_hand[0].split(':')[0] == 'A':
      link.send("%s: dealer's first card is an ace, you can claim !insurance as your first move" % link.user.nick)
      return

  if IsBlackjack(dealer_hand):
    Lose(link,True)

def Insurance(link,cmd):
  identity=link.identity()
  if not config.blackjack_insurance:
    return
  if not identity in players:
    link.send("%s: you are not in a game of blackjack - you can start one with !blackjack <amount>" % link.user.nick)
    return
  units = players[identity]['amount']
  enough, reason = IsPlayerBalanceAtLeast(link,units)
  if not enough:
    link.send("%s: %s - please refund your account to continue playing" % (link.user.nick, reason))
    return
  nhands = len(players[identity]['player_hands'])
  if nhands > 1 or len(GetPlayerCurrentHand(link)) > 2:
    link.send("%s: you can only claim insurance as first move" % link.user.nick)
    return
  if players[identity]['insurance']:
    link.send("%s: you can only claim insurance once" % link.user.nick)
    return
  dealer_hand = players[identity]['dealer_hand']
  if dealer_hand[0].split(':')[0] != 'A':
    link.send("%s: you can only claim insurance when the dealer's first card is an ace" % link.user.nick)
    return
  units = players[identity]['player_hands'][0]['amount']
  insurance_units = units / 2
  enough, reason = IsPlayerBalanceAtLeast(link,units + insurance_units)
  if not enough:
    link.send("%s: you do not have enough %s in your account to insure with %s" % (link.user.nick,coinspecs.name,AmountToString(insurance_units)))
    return
  if IsBlackjack(dealer_hand):
    Lose(link,True)
    # From here on, players[identity] is deleted
    win_insurance_units = insurance_units * 2
    link.send('%s wins %s insurance - dealer had a blackjack - %s' % (link.user.nick, AmountToString(win_insurance_units), HandToString(dealer_hand,identity in utf8users,False,False)))
    UpdateSidebetRecord(link,"insurance",True,False,win_insurance_units)
  else:
    link.send('%s loses %s insurance - dealer had no blackjack' % (link.user.nick, AmountToString(insurance_units)))
    UpdateSidebetRecord(link,"insurance",False,True,insurance_units)
    link.send("%s: Your hand is %s. Dealer's hand is %s" % (link.user.nick, PlayerHandsToString(link,True),HandToString(dealer_hand,identity in utf8users,True,False)))
  if identity in players:
    players[identity]['insurance'] = True

def IsCurrentPlayerHandASplitAce(link):
  identity=link.identity()
  if len(players[identity]['player_hands']) == 1:
    return False
  idx = players[identity]['player_current_hand']
  if players[identity]['player_hands'][idx]['hand'][0].split(':')[0] == 'A':
    return True
  return False

def Hit(link,cmd):
  identity=link.identity()
  if not identity in players:
    link.send("%s: you are not in a game of blackjack - you can start one with !blackjack <amount>" % link.user.nick)
    return
  units = players[identity]['amount']
  enough, reason = IsPlayerBalanceAtLeast(link,units)
  if not enough:
    link.send("%s: %s - please refund your account to continue playing" % (link.user.nick, reason))
    return
  if IsCurrentPlayerHandASplitAce(link):
    link.send("%s: You cannot hit a split ace" % (link.user.nick))
    return
  RecordMove(link, "hit")
  card = DrawForPlayer(link)
  link.send("%s: you draw %s. Your hand is %s. Dealer's hand is %s" % (link.user.nick, GetCardName(card,identity in utf8users), PlayerHandsToString(link,True),HandToString(players[identity]['dealer_hand'],identity in utf8users,True,True)))
  score = GetPlayerCurrentHandScore(link)
  if score > 21:
    Lose(link,False)
  elif score == 21:
    SwitchToNextHand(link)

def Double(link,cmd):
  identity=link.identity()
  if not identity in players:
    link.send("%s: you are not in a game of blackjack - you can start one with !blackjack <amount>" % link.user.nick)
    return
  if len(GetPlayerCurrentHand(link)) > 2:
    link.send("%s: you can not double down with more than 2 cards" % link.user.nick)
    return
  units = players[identity]['amount']
  enough, reason = IsPlayerBalanceAtLeast(link,units)
  if not enough:
    link.send("%s: %s - please refund your account to continue playing" % (link.user.nick, reason))
    return
  idx = players[identity]['player_current_hand']
  units = players[identity]['player_hands'][idx]['amount']
  enough, reason = IsPlayerBalanceAtLeast(link,units*2)
  if not enough:
    link.send("%s: you do not have enough %s in your account to double your bet on hand %d" % (link.user.nick,coinspecs.name,idx+1))
    return
  if IsCurrentPlayerHandASplitAce(link):
    link.send("%s: You cannot double down on a split ace" % (link.user.nick))
    return
  RecordMove(link,"double")
  players[identity]['player_hands'][idx]['amount'] = players[identity]['player_hands'][idx]['amount'] + units
  players[identity]['amount'] = players[identity]['amount'] + units
  card = DrawForPlayer(link)
  link.send("%s: you draw %s. Your hand is %s. Dealer's hand is %s" % (link.user.nick, GetCardName(card,identity in utf8users), PlayerHandsToString(link,True),HandToString(players[identity]['dealer_hand'],identity in utf8users,True,True)))
  score = GetPlayerCurrentHandScore(link)
  if score > 21:
    Lose(link,False)
  else:
    SwitchToNextHand(link)

def Stand(link,cmd):
  identity=link.identity()
  if not identity in players:
    link.send("%s: you are not in a game of blackjack - you can start one with !blackjack <amount>" % link.user.nick)
    return
  units = players[identity]['amount']
  enough, reason = IsPlayerBalanceAtLeast(link,units)
  if not enough:
    link.send("%s: %s - please refund your account to continue playing" % (link.user.nick, reason))
    return
  RecordMove(link,"stand")
  link.send("%s stands" % link.user.nick)
  SwitchToNextHand(link)

def Split(link,cmd):
  identity=link.identity()
  if not identity in players:
    link.send("%s: you are not in a game of blackjack - you can start one with !blackjack <amount>" % link.user.nick)
    return
  units = players[identity]['amount']
  enough, reason = IsPlayerBalanceAtLeast(link,units)
  if not enough:
    link.send("%s: %s - please refund your account to continue playing" % (link.user.nick, reason))
    return
  idx = players[identity]['player_current_hand']
  hand = GetPlayerCurrentHand(link)
  if len(hand)!=2 or GetCardScore(hand[0])!=GetCardScore(hand[1]):
    link.send("%s: only pairs with the same value can be split" % (link.user.nick))
    return
  if len(players[identity]['player_hands']) >= config.blackjack_split_to:
    link.send("%s: you can only split to %d" % (link.user.nick, config.blackjack_split_to))
    return
  enough, reason = IsPlayerBalanceAtLeast(link,units+players[identity]['base_amount'])
  if not enough:
    link.send("%s: you do not have enough %s in your account to split hand %d" % (link.user.nick,coinspecs.name,idx+1))
    return
  players[identity]['amount'] = players[identity]['amount'] + players[identity]['base_amount']
  RecordMove(link,"split")
  log_log('splitting hand %d' % idx)
  split_card_0 = hand[0]
  split_card_1 = hand[1]
  players[identity]['player_hands'].insert(idx+1,players[identity]['player_hands'][idx].copy())
  players[identity]['player_hands'][idx]['hand'] = [ split_card_0, DrawCard(players[identity]['deck']) ]
  players[identity]['player_hands'][idx+1]['hand'] = [ split_card_1, DrawCard(players[identity]['deck']) ]

  sidebets = players[identity]['sidebets']
  if sidebets['splits']:
    bet_units = sidebets['splits']
    nsplits = len(players[identity]['player_hands'])
    if nsplits == 2:
      win_units = bet_units * 5
    elif nsplits == 3:
      win_units = bet_units * (11-5)
    elif nsplits == 4:
      win_units = bet_units * (21-11)
    if nsplits == 2:
      link.send('%s splits to %d - you win %s' % (link.user.nick, nsplits, AmountToString(win_units)))
    else:
      link.send('%s resplits to %d - you win another %s' % (link.user.nick, nsplits, AmountToString(win_units)))
    UpdateSidebetRecord(link,"splits",True,False,win_units)

  dealer_hand = players[identity]['dealer_hand']
  link.send("%s: your hand is now %s. Dealer's hand is %s" % (link.user.nick,PlayerHandsToString(link),HandToString(dealer_hand,identity in utf8users,True,False)))

def Hand(link,cmd):
  identity=link.identity()
  if not identity in players:
    link.send("%s: you are not in a game of blackjack - you can start one with !blackjack <amount>" % link.user.nick)
    return
  units = players[identity]['amount']
  dealer_hand = players[identity]['dealer_hand']
  link.send("%s: your total bet is %s. Your hand is %s. Dealer's hand is %s" % (link.user.nick, AmountToString(units),PlayerHandsToString(link,True),HandToString(dealer_hand,identity in utf8users,True,False)))
  enough, reason = IsPlayerBalanceAtLeast(link,units)
  if not enough:
    link.send("%s: %s - please refund your account to continue playing" % (link.user.nick, reason))

def ResetBlackjackStats(link,cmd):
  identity=link.identity()
  sidentity = GetParam(cmd,1)
  if sidentity:
    sidentity=IdentityFromString(link,sidentity)
  if sidentity and sidentity != identity:
    if not IsAdmin(link):
      log_error('%s is not admin, cannot see blackjack stats for %s' % (identity, sidentity))
      link.send('Access denied')
      return
  else:
    sidentity=identity
  try:
    ResetGameStats(link,sidentity,"blackjack")
  except Exception,e:
    link.send("An error occured")

def ShowBlackjackStats(link,sidentity,title):
  return ShowGameStats(link,sidentity,title,"blackjack")

def GetBlackjackStats(link,cmd):
  identity=link.identity()
  sidentity = GetParam(cmd,1)
  if sidentity:
    sidentity=IdentityFromString(link,sidentity)
  if sidentity and sidentity != identity:
    if not IsAdmin(link):
      log_error('%s is not admin, cannot see blackjack stats for %s' % (identity, sidentity))
      link.send('Access denied')
      return
  else:
    sidentity=identity
  ShowBlackjackStats(link,sidentity,NickFromIdentity(sidentity))
  ShowBlackjackStats(link,"reset:"+sidentity,'%s since reset' % NickFromIdentity(sidentity))
  ShowBlackjackStats(link,'','overall')

def PlayerSeed(link,cmd):
  identity=link.identity()
  fair_string = GetParam(cmd,1)
  if not fair_string:
    link.send("Usage: !playerseed <string>")
    return
  try:
    SetPlayerSeed(link,'blackjack',fair_string)
  except Exception,e:
    log_error('Failed to save player seed for %s: %s' % (identity, str(e)))
    link.send('An error occured')

def FairCheck(link,cmd):
  identity=link.identity()
  try:
    seed = GetServerSeed(link,'blackjack')
  except Exception,e:
    log_error('Failed to get server seed for %s: %s' % (identity,str(e)))
    link.send('An error has occured')
    return
  try:
    GenerateServerSeed(link,'blackjack')
  except Exception,e:
    log_error('Failed to generate server seed for %s: %s' % (identity,str(e)))
    link.send('An error has occured')
    return
  link.send('%s: your server seed was %s - it has now been reset; see !fair for details' % (link.user.nick,str(seed)))

def Seeds(link,cmd):
  identity=link.identity()
  try:
    sh = GetServerSeedHash(link,'blackjack')
    ps = GetPlayerSeed(link,'blackjack')
  except Exception,e:
    log_error('Failed to get server seed for %s: %s' % (identity,str(e)))
    link.send('An error has occured')
    return
  link.send('%s: your server seed hash is %s' % (link.user.nick,str(sh)))
  if ps == "":
    link.send('%s: you have not set a player seed' % link.user.nick)
  else:
    link.send('%s: your player seed hash is %s' % (link.user.nick,str(ps)))

def UseUTF8(link,cmd):
  identity=link.identity()
  onoff=GetParam(cmd,1)
  if not onoff:
    if identity in utf8users:
      link.send('%s: utf8 is enabled'%link.user.nick)
    else:
      link.send('%s: utf8 is disabled'%link.user.nick)
  elif onoff=="on":
    utf8users.add(identity)
    link.send('%s: utf8 is now enabled'%link.user.nick)
  elif onoff=="off":
    utf8users.discard(identity)
    link.send('%s: utf8 is now disabled'%link.user.nick)
  else:
    link.send('usage: !utf8 [on|off]')

def Fair(link,cmd):
  link.send_private("%s's blackjack betting is provably fair" % config.tipbot_name)
  link.send_private("The deck shuffling is determined by three pieces of information:")
  link.send_private(" - your server seed. You can see its hash with !seeds")
  link.send_private(" - your player seed. Empty by default, you can set it with !playerseed")
  link.send_private(" - the game number, displayed with each game you make")
  link.send_private("To verify past games were fair, use !faircheck")
  link.send_private("You will be given your server seed, and a new one will be generated")
  link.send_private("for future games. Then follow these steps:")
  link.send_private("Create a deck: 234567890JQKA - repeated %d times (4 suits, %d decks)" % (4*config.blackjack_decks, config.blackjack_decks))
  link.send_private("Calculate the SHA-256 sum of serverseed:playerseed:gamenumber")
  link.send_private("Use the resulting string as the seed for the Mersenne Twister PRNG")
  link.send_private("Shuffle the deck using the Fisher-Yates algorithm with that PRNG")
  link.send_private("Starting cards are dealt in the order: player, dealer, player, dealer")
  link.send_private("See !faircode for Python code implementing this check")

def FairCode(link,cmd):
  link.send_private("This Python 2 code takes the seeds and game number and outputs the shuffled")
  link.send_private("deck used in the corresponding game. Run it with three arguments: server seed,")
  link.send_private("player seed (use '' if you did not set any), and game number.")

  link.send_private("import sys,hashlib,random")
  link.send_private("try:")
  link.send_private("  deck=['2','3','4','5','6','7','8','9','10','J','Q','K','A']*%s" % (4*config.blackjack_decks))
  link.send_private("  s=hashlib.sha256(sys.argv[1]+':'+sys.argv[2]+':'+sys.argv[3]).hexdigest()")
  link.send_private("  random.Random(s).shuffle(deck)")
  link.send_private("  print str(deck)")
  link.send_private("except:")
  link.send_private("  print 'need serverseed, playerseed, and game number'")

# rough house edges:
# over13: 7%
# under13: 10%
# pair: 6%
# climber: 3%
# buster: 5%
# splits: 8%
# match: 5%
# addup: 8%

def SideBets(link,cmd):
  link.send_private("Side bets are made by adding their name after the !blackjack <amount> command, eg:")
  link.send_private(" !blackjack 1 buster over13 - bets 0.5 for dealer busting, and 0.5 for first 2 cards sum over 13")
  link.send_private("Each side bet wager is for half of the amount wagered for the main blackjack game")
  link.send_private("Payouts depend on the side bet:")
  if "over13" in config.blackjack_sidebets:
    link.send_private(" * over13  - 1:1 - Player's first two cards scores over 13 (aces count as 1)")
  if "under13" in config.blackjack_sidebets:
    link.send_private(" * under13 - 1:1 - Player's first two cards scores under 13 (aces count as 1)")
  if "pair" in config.blackjack_sidebets:
    link.send_private(" * pair    - 12:1 - Player's first two cards are a pair")
  if "climber" in config.blackjack_sidebets:
    link.send_private(" * climber - 2:1 to 21:1 - Player's first two cards scores 20, payout as dealer's first card's score, ace pays 21:1")
  if "buster" in config.blackjack_sidebets:
    link.send_private(" * buster  - 3:2 to 21:1 - Dealer busts with 3 cards (3:2), 4 (3:1), 5 (5:1), 6 (11:1), or 7+ (21:1)")
  if "splits" in config.blackjack_sidebets:
    link.send_private(" * splits  - 5:1 to 21:1 - Split your hand to 2 (5:1), 3 (11:1), or 4 (21:1)")
  if "match" in config.blackjack_sidebets:
    link.send_private(" * match   - 5:1 to 21:1 - Match the dealer's first card with one (5:1) or both (21:1) or the player's first two cards")
  if "addup" in config.blackjack_sidebets:
    link.send_private(" * addup   - 27:1 - Sum of player's first two cards' scores match the dealer's first card's score")

def BlackjackHelp(link):
  link.send_private("The blackjack module is a provably fair %s blackjack betting game" % coinspecs.name)
  link.send_private("Basic usage: !blackjack <amount>")
  link.send_private("The goal is to get a hand totalling as close to 21 without going over")
  link.send_private("and have a total higher than the dealer. Suits do not matter.")
  link.send_private("Available moves are: !hit (get a new card), !stand (finish playing the curent),")
  link.send_private("hand, !double (double your bet and take a final card), !split (split a hand of")
  link.send_private("two cards with equal value), and !insurance (when the dealer's first card is an ace")
  link.send_private("See !fair and !faircode for a description of the provable fairness of the game")
  link.send_private("See !faircheck to get the server seed to check past games were fair")
  if len(config.blackjack_sidebets) > 0:
    link.send_private("See !sidebets for a list of available side bets and how to use them")



random.seed(time.time())
RegisterModule({
  'name': __name__,
  'help': BlackjackHelp,
})
RegisterCommand({
  'module': __name__,
  'name': 'blackjack',
  'parms': '<amount-in-%s>' % coinspecs.name if len(config.blackjack_sidebets) == 0 else '<amount-in-%s> [sidebet1 [sidebet2...]]' % coinspecs.name,
  'function': Blackjack,
  'registered': True,
  'help': "start a blackjack game - blackjack pays 3:2"
})
RegisterCommand({
  'module': __name__,
  'name': 'hit',
  'function': Hit,
  'registered': True,
  'help': "Hit (draw a new card on the current hand)"
})
RegisterCommand({
  'module': __name__,
  'name': 'double',
  'function': Double,
  'registered': True,
  'help': "Double down (double bet and draw a final card on the current hand)"
})
RegisterCommand({
  'module': __name__,
  'name': 'stand',
  'function': Stand,
  'registered': True,
  'help': "Stand (finish the current hand)"
})
RegisterCommand({
  'module': __name__,
  'name': 'split',
  'function': Split,
  'registered': True,
  'help': "Split current hand if first two cards are a pair - split to %d max" % config.blackjack_split_to
})
if config.blackjack_insurance:
  RegisterCommand({
    'module': __name__,
    'name': 'insurance',
    'function': Insurance,
    'registered': True,
    'help': "Insure against a dealer blackjack with half your bet (offered if the dealer's first card in an ace) - paid 2:1"
  })
RegisterCommand({
  'module': __name__,
  'name': 'hand',
  'function': Hand,
  'registered': True,
  'help': "Show your and the dealer's current hands"
})
RegisterCommand({
  'module': __name__,
  'name': 'stats',
  'parms': '[<name>]',
  'function': GetBlackjackStats,
  'registered': True,
  'help': "displays your blackjack stats"
})
RegisterCommand({
  'module': __name__,
  'name': 'resetstats',
  'parms': '[<name>]',
  'function': ResetBlackjackStats,
  'registered': True,
  'help': "resets your Blackjack stats"
})
if len(config.blackjack_sidebets) > 0:
  RegisterCommand({
    'module': __name__,
    'name': 'sidebets',
    'function': SideBets,
    'registered': True,
    'help': "List the available side bets"
  })
RegisterCommand({
  'module': __name__,
  'name': 'playerseed',
  'parms': '<string>',
  'function': PlayerSeed,
  'registered': True,
  'help': "set a custom seed to use in the hash calculation"
})
RegisterCommand({
  'module': __name__,
  'name': 'seeds',
  'function': Seeds,
  'registered': True,
  'help': "Show hash of your current server seed and your player seed"
})
RegisterCommand({
  'module': __name__,
  'name': 'utf8',
  'parms': '[on|off]',
  'function': UseUTF8,
  'registered': True,
  'help': "Enable or disable use of UTF-8 to display cards"
})
RegisterCommand({
  'module': __name__,
  'name': 'faircheck',
  'function': FairCheck,
  'registered': True,
  'help': "Check provably fair rolls"
})
RegisterCommand({
  'module': __name__,
  'name': 'fair',
  'function': Fair,
  'registered': True,
  'help': "describe the provably fair blackjack game"
})
RegisterCommand({
  'module': __name__,
  'name': 'faircode',
  'function': FairCode,
  'registered': True,
  'help': "Show sample Python code to check game fairness"
})
