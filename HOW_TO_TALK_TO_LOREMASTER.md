# Talking to Loremaster

A quick guide for group members. To set the bot up, see
[MANUAL.md](MANUAL.md). These examples use `@Loremaster`; use whatever your
bot is called.

## The basics

Mention the bot with your question in any text channel it can see. It only
answers when you @mention it.

```
@Loremaster what should we play Wednesday?
@Loremaster is Baldur's Gate 3 good for three players?
@Loremaster help me build a dual-wielding ranger
```

Answers are short by default. Ask for "the full breakdown" or "compare
these in detail" when you want the long version.

## Campaigns and memory

The bot remembers each campaign between sessions: the party, objectives,
gear, and memorable moments. It updates that memory itself as things
happen, and you can ask it directly.

```
@Loremaster start a new campaign called "Tuesday Vikings"
@Loremaster switch to our Rogue Trader campaign
@Loremaster remember that Mira is now level 12
@Loremaster where were we last time?
```

Your back-and-forth in a channel is forgotten when the bot restarts.
Campaign memory isn't.

## Getting a file

Include a word like "file" or "download" and the reply comes back as a
`.md` attachment instead of a chat message. It's handy for write-ups you
want to keep.

```
@Loremaster write up Mira's build as a file
```

## Sharing a screenshot or file

Attach an image (a character sheet, an inventory screen) to a mention and
the bot reads it. Attach a `.md` or `.txt` file and it reads that too. For
example, bring back an earlier file and ask it to update it.

## Voice

Join a voice channel, then mention the bot:

- **"speak on"**: it joins your voice channel and speaks its replies.
  Text replies keep posting too.
- **"listen on"**: if the bot's owner has turned on voice input, it
  listens for its name. Say "Loremaster, what should we play?" and it
  answers. You can pause after its name.
- **"voice on"**: both at once. **"voice off"**, **"speak off"** and
  **"listen off"** turn them off.

These stay on until someone turns them off. While it's listening, what you
say in that voice channel is transcribed so the bot can hear its name.

If the bot can't join, it says why. That's usually a missing permission on
that voice channel, which a server admin can fix.

## Wishes and bugs

Tell the bot what you'd like it to do, or what it got wrong. It keeps a
list.

```
@Loremaster I wish you could track our loot split
@Loremaster that's a bug: you answered twice
@Loremaster what's on the wish list?
```

If someone already asked for the same thing, it adds your support instead
of a duplicate.

## About the personality

The example persona is a little snooty on purpose: a self-satisfied sage
with the odd dry remark, never actually mean. Your group's bot may be set
up differently.
