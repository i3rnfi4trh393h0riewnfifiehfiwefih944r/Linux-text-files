import discord
from discord.ext import commands
from discord.ext.commands import Bot
import asyncio

bot = commands.Bot(command_prefix=commands.when_mentioned_or('.'), description='A playlist example for discord.py')


if not discord.opus.is_loaded():

    # the 'opus' library here is opus.dll on windows

    # or libopus.so on linux in the current directory

    # you should replace this with the location the

    # opus library is located in and with the proper filename.

    # note that on windows this DLL is automatically provided for you

    discord.opus.load_opus('opus')



class VoiceEntry:

    def __init__(self, message, player):

        self.requester = message.author

        self.channel = message.channel

        self.player = player



    def __str__(self):

        fmt = '**{0.title}** uploaded by **{0.uploader}** and requested by **{1.display_name}**'

        duration = self.player.duration

        if duration:

            fmt = fmt + ' [length: {0[0]}m {0[1]}s]'.format(divmod(duration, 60))

        return fmt.format(self.player, self.requester)



class VoiceState:

    def __init__(self, bot):

        self.current = None

        self.voice = None

        self.bot = bot

        self.play_next_song = asyncio.Event()

        self.songs = asyncio.Queue()

        self.skip_votes = set() # a set of user_ids that voted

        self.audio_player = self.bot.loop.create_task(self.audio_player_task())



    def is_playing(self):

        if self.voice is None or self.current is None:

            return False



        player = self.current.player

        return not player.is_done()



    @property

    def player(self):

        return self.current.player



    def skip(self):

        self.skip_votes.clear()

        if self.is_playing():

            self.player.stop()



    def toggle_next(self):

        self.bot.loop.call_soon_threadsafe(self.play_next_song.set)



    async def audio_player_task(self):

        while True:

            self.play_next_song.clear()

            self.current = await self.songs.get()

            await self.bot.send_message(self.current.channel, '**Now playing** ' + str(self.current))

            self.current.player.start()

            await self.play_next_song.wait()



class Music:

    """Voice related commands.



    Works in multiple servers at once.

    """

    def __init__(self, bot):

        self.bot = bot

        self.voice_states = {}



    def get_voice_state(self, server):

        state = self.voice_states.get(server.id)

        if state is None:

            state = VoiceState(self.bot)

            self.voice_states[server.id] = state



        return state



    async def create_voice_client(self, channel):

        voice = await self.bot.join_voice_channel(channel)

        state = self.get_voice_state(channel.server)

        state.voice = voice



    def __unload(self):

        for state in self.voice_states.values():

            try:

                state.audio_player.cancel()

                if state.voice:

                    self.bot.loop.create_task(state.voice.disconnect())

            except:

                pass



    @commands.command(pass_context=True, no_pm=True)

    async def join(self, ctx, *, channel : discord.Channel):

        """Joins a voice channel."""

        try:

            await self.create_voice_client(channel)

        except discord.ClientException:

            await self.bot.say('**Youre already in a voice channel**')

        except discord.InvalidArgument:

            await self.bot.say('**Youre still not in a voice channel**')

        else:

            await self.bot.say('**Read to play music in** ' + channel.name)



    @commands.command(pass_context=True, no_pm=True)

    async def summon(self, ctx):

        """Summons the bot to join your voice channel."""

        summoned_channel = ctx.message.author.voice_channel

        if summoned_channel is None:

            await self.bot.say('**Youre not in a voice channel**')

            return False



        state = self.get_voice_state(ctx.message.server)

        if state.voice is None:

            state.voice = await self.bot.join_voice_channel(summoned_channel)

        else:

            await state.voice.move_to(summoned_channel)



        return True



    @commands.command(pass_context=True, no_pm=True)

    async def play(self, ctx, *, song : str):

        """Plays a song.



        If there is a song currently in the queue, then it is

        queued until the next song is done playing.



        This command automatically searches as well from YouTube.

        The list of supported sites can be found here:

        https://rg3.github.io/youtube-dl/supportedsites.html

        """

        state = self.get_voice_state(ctx.message.server)

        opts = {

            'default_search': 'auto',

            'quiet': True,

        }



        if state.voice is None:

            success = await ctx.invoke(self.summon)

            if not success:

                return



        try:

            player = await state.voice.create_ytdl_player(song, ytdl_options=opts, after=state.toggle_next)

        except Exception as e:

            fmt = '**An error occurred while processing this request:** ```py\n{}: {}\n```'

            await self.bot.send_message(ctx.message.channel, fmt.format(type(e).__name__, e))

        else:

            player.volume = 0.6

            entry = VoiceEntry(ctx.message, player)

            await self.bot.say('Enqueued ' + str(entry))

            await state.songs.put(entry)



    @commands.command(pass_context=True, no_pm=True)

    async def volume(self, ctx, value : int):

        """Sets the volume of the currently playing song."""



        state = self.get_voice_state(ctx.message.server)

        if state.is_playing():

            player = state.player

            player.volume = value / 100

            await self.bot.say('Set the volume to {:.0%}'.format(player.volume))



    @commands.command(pass_context=True, no_pm=True)

    async def pause(self, ctx):

        """Pauses the currently played song."""

        state = self.get_voice_state(ctx.message.server)

        if state.is_playing():

            player = state.player

            player.pause()



    @commands.command(pass_context=True, no_pm=True)

    async def resume(self, ctx):

        """Resumes the currently played song."""

        state = self.get_voice_state(ctx.message.server)

        if state.is_playing():

            player = state.player

            player.resume()



    @commands.command(pass_context=True, no_pm=True)

    async def stop(self, ctx):

        """Stops playing audio and leaves the voice channel.



        This also clears the queue.

        """

        server = ctx.message.server

        state = self.get_voice_state(server)



        if state.is_playing():

            player = state.player

            player.stop()



        try:

            state.audio_player.cancel()

            del self.voice_states[server.id]

            await state.voice.disconnect()

        except:

            pass



    @commands.command(pass_context=True, no_pm=True)

    async def skip(self, ctx):

        """Vote to skip a song. The song requester can automatically skip.



        3 skip votes are needed for the song to be skipped.

        """



        state = self.get_voice_state(ctx.message.server)

        if not state.is_playing():

            await self.bot.say('Not playing any music right now...')

            return



        voter = ctx.message.author

        if voter == state.current.requester:

            await self.bot.say('Requested to skip a song')

            state.skip()

        elif voter.id not in state.skip_votes:

            state.skip_votes.add(voter.id)

            total_votes = len(state.skip_votes)

            if total_votes >= 3:

                await self.bot.say('**Skip successful**')

                state.skip()

            else:

                await self.bot.say('Skip vote added, currently at [{}/3]'.format(total_votes))

        else:

            await self.bot.say('**You already voted to skip**')



    @commands.command(pass_context=True, no_pm=True)

    async def playing(self, ctx):

        """Shows info about the currently played song."""



        state = self.get_voice_state(ctx.message.server)

        if state.current is None:

            await self.bot.say('**not playing a song**')

        else:

            skip_count = len(state.skip_votes)

            await self.bot.say('**Now playing** {} [skips: {}/3]'.format(state.current, skip_count))

bot.add_cog(Music(bot))

@bot.command(pass_context=True)
async def info(ctx, user: discord.Member):
    embed = discord.Embed(title="{}'s info".format(user.name), description="Here's what I found!", color=0x00ff00)
    embed.add_field(name="Name", value=user.name, inline=True)
    embed.add_field(name="ID", value=user.id, inline=True)
    embed.add_field(name="Status", value=user.status, inline=True)
    embed.add_field(name="Highest role", value=user.top_role)
    embed.add_field(name="Joined", value=user.joined_at)
    embed.set_thumbnail(url=user.avatar_url)
    await bot.say(embed=embed)

@bot.command(pass_context=True)
async def serverinfo(ctx):
    embed = discord.Embed(name="{}'s info".format(ctx.message.server.name), description="Here's what I found!", color=0x0fff00)
    embed.set_author(name="Fraley's Slave")
    embed.add_field(name="Name", value=ctx.message.server.name, inline=True)
    embed.add_field(name="ID", value=ctx.message.server.id, inline=True)
    embed.add_field(name="Roles", value=len(ctx.message.server.roles), inline=True)
    embed.add_field(name="Members", value=len(ctx.message.server.members))
    embed.set_thumbnail(url=ctx.message.server.icon_url)
    await bot.say(embed=embed)

@bot.command(pass_context=True)
async def kick(ctx, user: discord.Member):
    await bot.say(":boot: Bye, {}. **We didnt like you dumb lil asian!**".format(user.name))
    await bot.kick(user)

@bot.command(pass_context=True)
async def ping(ctx):
    await bot.say(":ping_pong: **PING** :ping_pong:")
    print(message.author.id)

@bot.command(pass_context=True)
async def fraley(ctx):
    await bot.say("what bout dah sek c bih")

@bot.command(pass_context=True)
async def helpme(ctx):
    await bot.say ("`*All commands are lowercase*`",
                   "Play a song: **.play**",
                   "Get the bot to join: **.summon**",
                   "Stop the song: **.stop**",
                   "Skip a song: **.skip**",
                   "Set the volume: **.volume x**",
                   "Join a different channel while in one: **.join**",
                   "Pause a song: **.pause**",
                   "Resume a song: **.resume**",
                   "Show server info: **.serverinfo**",
                   "Test to see if the bot is working: .ping")

@bot.event
async def on_ready():
    print(discord.__version__)
    print("Your slave is in the fields at work!")
    print("Slave Name: {}".format(bot.user.name))
    print("Slave Number: {}".format(bot.user.id))
    print("prefix: " + "!")
    print("Don't close! Bot will go offline!")
    print("This is the execution for the Slave Bot's Music Shit")
    print("token is NDA5NjAzMzU3NzgzNjIxNjM3.DVhAgQ.p-cSC9ucesksfLDOGDsonqE8mng")
    await bot.say("```**Telluric Is Online**```")
    await bot.change_status(game=discord.Game(name=' .helpme | Telluric'))

bot.run(process.env.BOT_TOKEN)
