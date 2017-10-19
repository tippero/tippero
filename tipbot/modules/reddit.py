#!/bin/python
#
# Cryptonote tipbot - Reddit
# Copyright 2015 moneromooo
#
# The Cryptonote tipbot is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published
# by the Free Software Foundation; either version 2, or (at your option)
# any later version.
#

import sys
import string
import time
import threading
import re
import praw
import logging
import tipbot.config as config
from tipbot.log import log_error, log_warn, log_info, log_log
from tipbot.user import User
from tipbot.link import Link
from tipbot.utils import *
from tipbot.command_manager import *
from tipbot.network import *

#import logging
#logging.basicConfig(level=logging.DEBUG)

class RedditNetwork(Network):
  def __init__(self,name):
    Network.__init__(self,name)
    self.last_update_time=0
    self.logged_in=False
    self.last_seen_ids=None
    self.thread=None

  def is_identified(self,link):
    # all reddit users are identified
    return True

  def connect(self):
    if self.thread:
      return False
    try:
      cfg=config.network_config[self.name]
      self.login=cfg['login']
      password=GetPassword(self.name+'/password')
      self.subreddits=cfg['subreddits']
      user_agent=cfg['user_agent']
      self.update_period=cfg['update_period']
      self.load_limit=cfg['load_limit']
      self.keyword=cfg['keyword']
      self.use_unread_api=cfg['use_unread_api']
      self.cache_timeout=cfg['cache_timeout']
      client_id=GetPassword(self.name+'/client_id')
      client_secret=GetPassword(self.name+'/client_secret')
      username=GetPassword(self.name+'/username')

      if False:
        handler = logging.StreamHandler()
        handler.setLevel(logging.DEBUG)
        logger = logging.getLogger('prawcore')
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)

      self.reddit=praw.Reddit(client_id=client_id,client_secret=client_secret,password=password,user_agent=user_agent,username=username)
      log_info("Logged in reddit as " + str(self.reddit.user.me()))
      self.items_cache=dict()

      self.stop = False
      self.thread = threading.Thread(target=self.run)
      self.thread.start()
      self.logged_in=True

    except Exception,e:
      log_error('Failed to login to reddit: %s' % str(e))
      return False
    return True

  def disconnect(self):
    log_info('Reddit disconnect')
    if not self.thread:
      return
    log_info('Shutting down Reddit thread')
    self.stop = True
    self.thread.join()
    self.thread = None
    self.items_cache=None
    self.reddit = None

  def send_group(self,group,msg,data=None):
    item=data
    if not item:
      log_error('RedditNetwork: no item found in send_group: cannot send %s' % (msg))
      return
    self._schedule_reply(item,None,msg)

  def send_user(self,user,msg,data=None):
    item=data
    if not item:
      # new PM
      self._schedule_reply(None,user.nick,msg)
    else:
      # reply to PM
      self._schedule_reply(item,None,msg)

  def is_acceptable_command_prefix(self,s):
    s=s.strip()
    if s=="":
      return True
    if s.lower() == self.keyword.lower():
      return True
    return False

  def _parse(self,item,is_pm):
    if not hasattr(item,'author'):
      return
    if not hasattr(item.author,'name'):
      log_warn('author of %s has no name field, ignored' % str(item.id))
      if True:
        try:
          item.mark_read()
        except Exception,e:
          log_warn('Failed to mark %s as read: %s' % (item.id,str(e)))
      return

    author=self.canonicalize(item.author.name)
    if author and author==self.canonicalize(self.login):
      return

    if item.id in self.last_seen_ids:
      log_log('Already seen %s %.1f hours ago by %s: %s (%s), skipping' % (item.id,age/3600,str(author),repr(title),repr(item.body)))
      try:
        item.mark_read()
      except Exception,e:
        log_warn('Failed to mark %s as read: %s' % (item.id,str(e)))
      return

    age=time.time()-item.created_utc
    ts=long(float(item.created_utc))
    title=item.link_title if hasattr(item,'link_title') else None

    log_log('Parsing new item %s from %.1f hours ago by %s: %s (%s)' % (item.id,age/3600,str(author),repr(title),repr(item.body)))
    self.last_seen_ids.add(item.id)
    redis_sadd('reddit:last_seen_ids',item.id)

    if is_pm or item.body.lower().find(self.keyword.lower()) >= 0:
      group=None
      #if not is_pm and hasattr(item,'subreddit'):
      #  group=Group(self,item.subreddit.display_name)
      group = None
      self.items_cache[item.fullname]=item
      link=Link(self,User(self,author),group,item)
      for line in item.body.split('\n'):
        if is_pm:
          exidx=line.find('!')
          if exidx!=-1 and len(line)>exidx+1 and line[exidx+1] in string.ascii_letters and self.is_acceptable_command_prefix(line[:exidx]):
            cmd=line[exidx+1:].split(' ')
            while '' in cmd:
              cmd.remove('')
            cmd[0] = cmd[0].strip(' \t\n\r')
            log_info('Found command from %s: %s' % (link.identity(), str(cmd)))
            if self.on_command:
              self.on_command(link,cmd)

        else:
          # reddit special: +x as a reply means tip
          if not is_pm and hasattr(item,'parent_id'):
            if re.search("\+[0-9]*(\.[0-9]*)?[\t ]+"+self.keyword,line) or re.search(self.keyword+"[\t ]+\+[0-9]*(\.[0-9]*)?",line):
              line=line.replace(self.keyword,'').strip()
              if self.on_command:
                try:
                  parent_item=next(self.reddit.info([item.parent_id]))
                  if not hasattr(parent_item,'author'):
                    raise RuntimeError('Parent item has no author')
                  author=parent_item.author.name
                  match=re.search("\+[0-9]*(\.[0-9]*)?",line)
                  amount=match.group(0)
                  if amount!='+':
                    synthetic_cmd=['tip',author,amount.replace('+','')]
                    log_log('Running synthetic command: %s' % (str(synthetic_cmd)))
                    self.on_command(link,synthetic_cmd)
                except Exception,e:
                  log_error('Failed to tip %s\'s parent: %s' % (item.id,str(e)))
    if True:
      try:
        item.mark_read()
      except Exception,e:
        log_warn('Failed to mark %s as read: %s' % (item.id,str(e)))

  def _schedule_reply(self,item,recipient,text):
    log_log('scheduling reply to %s:%s: %s' % (item.id if item else '""',recipient or '""',text))
    if item:
      ndata = redis_llen('reddit:replies')
      if ndata > 0:
        prev_item = redis_lindex('reddit:replies',ndata-1)
        if prev_item:
          prev_parts=prev_item.split(':',2)
          prev_fullname=prev_parts[0]
          prev_recipient=prev_parts[1]
          prev_text=prev_parts[2]
          if prev_fullname==item.fullname:
            log_log('Appending to previous item, also for the same fullname')
            new_text=prev_text+"\n\n"+text
            redis_lset('reddit:replies',ndata-1,(item.fullname if item else "")+":"+(recipient or "")+":"+new_text)
            return

    redis_rpush('reddit:replies',(item.fullname if item else "")+":"+(recipient or "")+":"+text)

  def _post_next_reply(self):
    data=redis_lindex('reddit:replies',0)
    if not data:
      return False
    parts=data.split(':',2)
    fullname=parts[0]
    recipient=parts[1]
    text=parts[2]

    text = text.replace('\n\n','\n\n  &nbsp;  \n\n').replace('\n','  \n')

    try:
      if recipient:
        # PM
        self.reddit.send_message(recipient,"Reply from %s"%self.login,text,raise_captcha_exception=True)
        log_info('Posted message to %s: %s' % (recipient,text))
      else:
        # subreddit or reply to PM
        item = None
        log_info('looking for "%s" in %s' % (str(fullname),str(self.items_cache)))
        if fullname in self.items_cache:
          item=self.items_cache[fullname]
        if not item:
          item = self.reddit.mesage(fullname)
        if not item:
          gen=self.reddit.info([fullname])
          item=next(gen, None)
        if not item:
          log_error('Failed to find item %s to post %s' % (fullname,text))
          redis_lpop('reddit:replies')
          return True
        reply_item=item.reply(text)
        log_info('Posted reply to %s: %s' % (fullname,text))
        if reply_item and hasattr(reply_item,'id'):
          redis_sadd('reddit:last_seen_ids',reply_item.id)

      redis_lpop('reddit:replies')

    except Exception,e:
      log_error('Error sending %s, will retry: %s' % (data,str(e)))
      return False

    return True

  def canonicalize(self,name):
    return name.lower()

  def update(self):
    return True

  def _check(self):
    now=time.time()
    if now-self.last_update_time < self.update_period:
      return True
    self.last_update_time=now

    if not self.last_seen_ids:
      self.last_seen_ids=redis_smembers('reddit:last_seen_ids')
      log_log('loaded last seen ids: %s ' % str(self.last_seen_ids))

    if self.use_unread_api:
      for message in self.reddit.get_unread():
        self._parse(message,not message.was_comment)

    else:
      for message in self.reddit.inbox.unread(limit=self.load_limit):
        #if not message.was_comment:
          self._parse(message,True)

      #print "Submissions from %s" % ("+".join(self.subreddits))
      #sr=self.reddit.subreddit("+".join(self.subreddits))
      #for s in sr.new(limit=self.load_limit):
      #  for comment in s.comments:
      #    self._parse(comment,False)

    while self._post_next_reply():
      pass

    log_log('RedditNetwork: update done in %.1f seconds' % float(time.time()-self.last_update_time))
    return True

  def run(self):
    while not self.stop:
      try:
        self._check()
      except Exception,e:
        log_error('Exception in RedditNetwork:_check: %s' % str(e))
      time.sleep(1)

RegisterNetwork("reddit",RedditNetwork)
