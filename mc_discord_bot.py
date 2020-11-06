#!/usr/bin/python3

# A simple discord bot by Jon Newton to connect a single (tested on vanilla) minecraft server instance to a single discord server
# written because I was challenged to do so by a family member :)
# developed for linux (tested on ubuntu).
#
# current capabilities:  
#   1: All minecraft chat is mirrored to a discord channel ('mcchat' by default)
#   2: All messages in the specified discord channel are mirrored to the minecraft chat by default
#   3: Minecraft commands can be run from discord by sending a message "<cmd> minecraft command"
#   4: Authentication such that minecraft commands can only be run by a user in a sepcified discord server role ('mc cmds' by default)
#   5: you can get the current public ip of the minecraft server from within discord by typing <ip>
#   6: you can get the list of players currently on the minecraft server from within discord by typing <who>
#   7: Written to be relatively easy to hack/extend (hopefully)
#
# Please ensure that your bot is not made public as it is only designed to be used for a single discord server at a time
# Currently, you will need to create the channel and auth role in your discord server manually.
#
# Dependencies:
#   python3 (version 3.8): apt install python3
#   discord: install: 'python3 -m pip install -U discord.py'
#   mcrcon: install: 'python3 -m pip install -U mcrcon'
# 
# QuickStart:
#   You need to have created a discord bot and invited it to your server (handy instructions here: https://discordpy.readthedocs.io/en/latest/discord.html)
#   ensure that rcon is enabled in your minecraft server settings (we use this to communicate with the server)
#   create the channel 'mcchat' in your server
#   place this python file in the same directory as your minecraft server
#   ensure your minecraft server is runnin (currently this does not work if you start the server afterwards)
#   run as follows:  DISCORD_BOT_TOKEN='mytoken' python3 mc_discord_bot.py
#   type <help> in discord and the bot should respond.
#
# (The other important settings can be changed using env vars  - see below.  )
#


import discord
from mcrcon import MCRcon
import re
from functools import reduce 
import asyncio
import re
from requests import get
import os

channelname=os.getenv("MC_DISCORD_CHANNEL", default ='mcchat')
high_priv_role=os.getenv("MC_DISCORD_PRIV_ROLE", default ='mc cmds')
rcon_host=os.getenv("RCON_HOST", default ='localhost')
rcon_pass=os.getenv("RCON_PASS", default ='minecraft')
logfile=os.getenv("MC_LOGFILE", default ='./logs/latest.log') #by default we assume you put the python file in the same dir as your server.
discord_token=os.getenv("DISCORD_BOT_TOKEN", default ='none')

if discord_token=='none':
    print("you need to set the DISCORD_BOT_TOKEN environmet variable")
    exit(1)

ip = get('https://api.ipify.org').text

##bot commands:
async def command(m,t): # run a command and return the response
    resp=mcr.command(t)
    resp="done. "+resp
    await m.channel.send(resp)

async def count_mobs(m,t): #count the number of mobs (todo)
    await m.channel.send("1, 2, 3, 4, ..   yes there are lots.")

async def say(m,t): #say something in chat
    name=m.author.nick
    id=str(m.author.id)
    #create the armor stand summoning string
    stand="summon armor_stand ~ ~ ~ {CustomNameVisible:0b,NoGravity:1b,Marker:1b,Invisible:1b,Tags:['"+id+"','discord'],CustomName:'{\"text\":\"@"+name+"\",\"bold\":true}'}"
    #summon an aromor stand as an avatar for the discord user wanting to say soemthing (the following will summon it if it does not already exist)
    #we use the discord ID as a tag so that we will have a maximum of 1 avatar per user.
    mcr.command("execute unless entity @e[type=armor_stand,limit=1,tag="+id+"] run "+stand)
    #say the message from the armor stand
    mcr.command("execute as @e[tag="+id+"] run say "+t) 
    #we leave the avatar in place in order to minimise the entities created and deleted.

async def who(m,t): # list players
    resp=mcr.command('/list')
    resp="done. "+resp
    await m.channel.send(resp)

async def server_off(m,t): # turn off server (todo)
    await m.channel.send("I'm afraid i cant do that dave")

async def get_ip(m,t): #return the public ip of the server
    await m.channel.send('Server public IP address is: {}'.format(ip))

async def bot_help(m,t):
    available_commands = list(command_lookup)
    helpcmd="<"+t+">"
    if not helpcmd in available_commands:
        await m.channel.send("available commands: "+ ",".join(available_commands)+".  You can also ask for help on a specific command by entering '<help> cmd'")
    else:
        await m.channel.send("Help for "+helpcmd+" : "+command_lookup[helpcmd]["help"])

#lookup for bot commands (this is done to make it easier to add more custom functions)
default = "<say>"
command_lookup={
    "<say>":{"fn":say, "allowed_roles": ["@everyone"], "help":"Send a message to everyone on the mc server. Usage: '<say> message'"},
    "<cmd>":{"fn":command, "allowed_roles": [high_priv_role], "help":"Runs a command on the Server. Usage: '<cmd> minecraft_command'"},
    "<count-mobs>":{"fn":count_mobs, "allowed_roles": ["@everyone"], "help":"Counts the mobs on the server. Usage: '<count-mobs>'"},
    "<server-off>":{"fn":server_off, "allowed_roles": [high_priv_role], "help":"Turns off the server. Usage: '<server-off>'"},
    "<help>": {"fn":bot_help, "allowed_roles": ["@everyone"], "help":"Yes, you need help :)"},
    "<who>": {"fn":who, "allowed_roles": ["@everyone"], "help":"List players on server.)"},
    "<ip>": {"fn":get_ip, "allowed_roles": ["@everyone"], "help":"Get the public IP address of the server)"}
}

#check user requesting command has the required role
async def auth_and_run(cmd,message,cmdtext):
    allowed_roles=command_lookup[cmd]["allowed_roles"]
    auth = reduce(lambda previous, current: previous or (current.name in allowed_roles), message.author.roles,False)
    if auth:
        await command_lookup[cmd]["fn"](message,cmdtext)
    else:
        await message.channel.send(message.author.name+" cant run the command: "+ cmd)

#regex to search for in the logfile (dont forget to escape regex code chars)
#might consider using re.compile if this is not fast enough, but it should be ok provided logging is not too busy.
log_matches=[
    {
    #To extract all server warning messages
        "search_regex":"\[Server thread\/WARN\]:",
        "extract_regex":"(?<=WARN\]: ).*",
        "msg_prepend":"SERVER WARNING: "
    },
    #To extract all server error messages
    {
        "search_regex":"\[Server thread\/ERROR\]:",
        "extract_regex":"(?<=ERROR\]: ).*",
        "msg_prepend":"SERVER ERROR: "
    }, 
    #To collect all server excluding that which starts with @ (which is what we generated)
    { 
        "search_regex":"\[Server thread\/INFO\]: \[[^@].*\] ",
        "extract_regex":"(?<=INFO\]: ).*",
        "msg_prepend":">> "
    }, 
    #To collect all player chat excluding that which starts with @ (which is what we generated)
    { 
        "search_regex":"\[Server thread\/INFO\]: <.*> ",
        "extract_regex":"(?<=INFO\]: ).*",
        "msg_prepend":">> "
    }, 
    #To announce when things die
    { 
        "search_regex":"\[Server thread\/INFO\]: [^0-9].*died, ",
        "extract_regex":"(?<=message: ).*",
        "msg_prepend":"DEATH REPORT: "
    }, 
    #To also announce where the death was
    { 
        "search_regex":"\[Server thread\/INFO\]: [^0-9].*died, ",
        "extract_regex":"x=.+y=.+z=.+[0-9]+",
        "msg_prepend":"LOCATION: "
    },
    #To announce when things die
    { 
        "search_regex":"\[Server thread\/INFO\]: [^\[].+was .+ by ",
        "extract_regex":"(?<=INFO\]: ).*",
        "msg_prepend":"PLAYER REPORT: "
    }, 
    #joined
    { 
        "search_regex":"\[Server thread\/INFO\]: [^\[].+joined the game",
        "extract_regex":"(?<=INFO\]: ).*",
        "msg_prepend":"JOINED: "
    }, 
    #left
    { 
        "search_regex":"\[Server thread\/INFO\]: [^\[].+left the game",
        "extract_regex":"(?<=INFO\]: ).*",
        "msg_prepend":"LEFT: "
    }, 
    #achievements
    { 
        "search_regex":"\[Server thread\/INFO\]: [^\[].+has made the advancement",
        "extract_regex":"(?<=INFO\]: ).*",
        "msg_prepend":"CLAP FOR: "
    }
]

#function to watch the log file
async def read_log(channel):
    # Create the subprocess; redirect the standard output into a pipe.
    proc = await asyncio.create_subprocess_exec(
        'tail', '-F', '-n','1',logfile,
        stdout=asyncio.subprocess.PIPE)
    print("Minecraft log file opened")
    # Read lines
    while True:
        data = await proc.stdout.readline()
        line = data.decode('utf-8').rstrip()
        for match in log_matches:
            #print(line)
            if re.search(match["search_regex"],line):
                extract=(re.search(match["extract_regex"],line))
                if extract:
                    await channel.send(match["msg_prepend"]+extract.group(0))

#setup the discord client async functions
client = discord.Client()
running = False

@client.event
async def on_ready():
    global running
    print('We have logged in as {0.user}'.format(client))
    guild=(client.guilds[0])
    channel=discord.utils.get(guild.channels, name=channelname)
    if running==False:
        running=True
        await read_log(channel)

@client.event
async def on_message(message):

    #we dont want to talk to ourselves!
    if message.author == client.user:
        return

    #if the message is sent to the text channel 
    if message.channel.name == channelname:

        #match for the bot command string format at the start of the message
        cmdmatch=(re.match("<.*>", message.clean_content))

        #if there is a known command at the start of the message then try to run the corresponding function
        if cmdmatch: 
            cmd=cmdmatch[0]
            cmdtext=str.strip(message.clean_content[cmdmatch.end():])
            if cmd in command_lookup:
                await auth_and_run(cmd,message,cmdtext)
            else:
                await message.channel.send("I've looked around but i cant find a command called "+cmd+"")

        #else this is the default if no command given.
        else:
            await auth_and_run(default,message,message.clean_content)

#connect to the minecraft server
mcr = MCRcon(rcon_host, rcon_pass)
try:
    mcr.connect()
except:
    print("Unable to connect to minecraft server via rcon")
    exit(1)
print("Minecraft rcon connection opened")
print("killing any old discord avatars")
print(mcr.command("kill @e[tag=discord]")) #remove anything left over from the last session.

#connect to the discord service
client.run(discord_token)
