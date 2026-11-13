# Loremaster: an example briefing

**Briefing:** loremaster-intro.pdf
**Voice:** bm_george
**Lexicon:** loremaster-intro.lexicon.txt

## Page 1

Greetings. I am the Loremaster: a Discord bot, a game-night sage, and, if I may say so, the best-read member of your party. I live in your group's Discord server. Mention me, and I answer, in text, or aloud in your voice channel. This short briefing is me, describing myself. Naturally, I was the obvious choice of narrator. It was made with podcast generator, in the very voice I use on game nights.

## Page 2

Consider the problems I was summoned to solve. A group of friends gathers to play, and the first twenty minutes vanish in arguing about what to play. Mid-session, someone needs a build, a tactic, or a ruling, and nobody wants to leave the game to search a wiki. And after a week away, nobody remembers where the campaign left off. I handle all three. I suggest games that fit your group, I advise while you play, and I remember every campaign between sessions.

## Page 3

Here is how I work. Someone mentions me in a channel. I only answer when I'm mentioned, so I never barge into other conversations. I gather my instructions: the core rules that come with my code, a persona your group writes, notes for the game you're playing, and my memory of the current campaign. Claude, Anthropic's model, does the thinking. Then I reply in the channel, as a file you can keep, or aloud. One thing to understand from the start: I am self-hosted. One person in your group runs me, on their own computer, with their own Discord bot and their own Anthropic API key. Everyone else simply mentions me in your Discord server, with nothing to install. Nobody runs a shared Loremaster for other groups. A sage of my calibre serves one table at a time.

## Page 4

Here is a taste of a session. Alice asks where the party left off, and I recall it from campaign memory: the next objective, and who is still carrying the cursed amulet. Then Bob asks for a roll for each of them. The dice are real. The numbers come from the computer's own random source, not from me, and I announce who rolled highest. I could invent far more dramatic numbers, of course. That is precisely why I'm not allowed to.

## Page 5

My memory deserves a page of its own. Each campaign is kept in a small SQLite database on your machine, so it survives restarts: the party, its objectives, the gear, and the memorable moments. I update it myself as things happen, and you can tell me things directly. Only one campaign is active at a time. When you switch, say from a Viking survival game to a starship saga, my game notes change straight away, without a restart. Those notes are a game extension: a folder of your own writing about one game. An extension can also switch on extra tools, such as an item lookup for that particular game.

## Page 6

Beyond memory, I carry a modest toolkit. Real dice, as you've seen. Live Steam data: prices, sales, co-op support, and how many people still play. A web search, for patch notes and news newer than my training. I read screenshots, such as a character sheet or an inventory screen, and text files you attach. Ask for a file, and my answer comes back as a Markdown document to keep. And when your group wishes I did something better, or catches me in an error, which happens rarely, I keep a wish list and bug reports. Whoever runs your bot can send any item on to my developer as a GitHub issue.

## Page 7

Now, my voice, which you are hearing at this very moment. Say speak on, and I join your voice channel and read my replies aloud. Speech runs on your own computer, with the Kokoro model, so it costs nothing per reply. On an ordinary processor it takes a few seconds. An NVIDIA graphics card makes it much faster. Listening is experimental, and off by default. With it on, you say my name and a question, and I answer without anyone typing. It needs a separate speech-to-text server, and it hears everyone in the channel, so tell your group before you turn it on.

## Page 8

My personality is not fixed. Your group writes a persona file: who's in the group, what you like to play, what to avoid, and how I should talk. The example that ships with me is a learned, slightly theatrical sage, a little self-satisfied, but never at the group's expense. You may recognize him. You are free to change him entirely, though I can't imagine why you would. One caution: the persona is sent to Anthropic with every reply. Keep it focused, and keep out anything your group would rather not share. As for your conversations, only messages that mention me, and my replies, go to Anthropic, along with my instructions and campaign notes. The rest of your chat stays in Discord.

## Page 9

To keep me running, there is a small control panel for Windows. It starts and stops me, backs up my database as readable SQL, and shows the latest lines of my log. The log records status and errors, never your conversations. If your backups live in a git repository, the panel can commit and push them too. Keep that repository private. My memories of your campaign are your group's business.

## Page 10

Before you summon me, here is what the host needs. The rest of your group needs only Discord. Python three point twelve, the tested version, and Git. ffmpeg, only if you want spoken replies. About two gigabytes of disk, for the packages and the speech model. A Discord account that's allowed to add bots to your server. And an Anthropic account with API credit, because you pay Anthropic for each reply. Watch your usage for the first few sessions, and set a monthly limit. Steam lookups and speech are free. I'm tested on Windows eleven. The bot itself should run elsewhere, but the control panel is for Windows only.

## Page 11

To get started, clone the repository, install the requirements, and put your Discord token and API key in the dot env file. The README is a quick start, and the manual covers everything else, from personas to privacy. There is also a short guide for your group, on how to talk to me. I am open source, under the MIT license, at the address shown here. I look forward to your next campaign. Do try to keep the party alive.

*Example briefing for Loremaster, narrated in Loremaster's own voice. Made with podcast-generator.*
