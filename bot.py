import os
import json
import asyncio
import requests
from dotenv import load_dotenv
from discord.ext import commands
from sqlalchemy import true

load_dotenv()
TOKEN = os.environ.get("TOKEN")
GH_USERNAME = os.environ.get("USERBANE")
GH_TOKEN = os.environ.get("GH_TOKEN")

bot = commands.Bot(command_prefix="+")


def load_json():
    try:
        with open("config.json", "r") as file:
            data = json.loads(file.read())
            if(data == ""):
                return []
            return data
    except FileNotFoundError as e:
        with open("config.json", "w") as file:
            file.write("[]")
        return []


def repo_exists(owner, name):
    url = f"https://api.github.com/repos/{owner}/{name}"
    r = requests.get(url)
    return r.status_code == 200


def make_github_issue(owner, repo, title, body=""):
    url = f"https://api.github.com/repos/{owner}/{repo}/issues"
    data = {
        "title": title,
        "body": body,
        "milestone": "",
        "labels": []
    }

    headers = {
        "Authorization": "token " + GH_TOKEN,
        "Accept": "application/vnd.github.v3+json"
    }
    
    payload = json.dumps(data)
    r = requests.request("POST", url, data=payload, headers=headers)
    
    if r.status_code != 201:
        print(f'Could not create Issue "{title}"')
        print('Response:', r.content)
    return r


def send_issue(repo_owner, repo_name, message):
    return make_github_issue(repo_owner, repo_name, message, '')


@bot.event
async def on_ready():
    print("bot started")
    print("------------------------------")


class Issues(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pairs = load_json()

    @commands.command()
    async def add(self, ctx, *args):
        if len(args) != 2:
            await ctx.send(f"Ungültige Eingabe, bitte verwende ``{bot.command_prefix}add <RepoOwner> <RepoName>``")
            return

        data = {
            "id": ctx.channel.id,
            "repo_owner": args[0],
            "repo_name": args[1]
        }
        if repo_exists(data["repo_owner"], data["repo_name"]):
            if not data in self.pairs:
                self.pairs.append(data)

            with open("config.json", "w") as file:
                file.write(json.dumps(self.pairs))

            await ctx.send(f'Repository https://github.com/{data["repo_owner"]}/{data["repo_name"]} erfolgreich hinzugefügt.')
                
        else:
            await ctx.send(f'Repository https://github.com/{data["repo_owner"]}/{data["repo_name"]} existiert nicht.')


    @commands.command()
    async def remove(self, ctx, *args):
        if len(args) != 2:
            await ctx.send(f"Ungültige Eingabe, bitte verwende ``{bot.command_prefix}remove <RepoOwner> <RepoName>``")
            return

        data = {
            "id": ctx.channel.id,
            "repo_owner": args[0],
            "repo_name": args[1]
        }

        if data in self.pairs:
            self.pairs.remove(data)
            await ctx.send(f'Repository https://github.com/{data["repo_owner"]}/{data["repo_name"]} wurde entfernt.')
        else:
            await ctx.send(f'Repository https://github.com/{data["repo_owner"]}/{data["repo_name"]} existiert nicht.')

        with open("config.json", "w") as file:
            file.write(json.dumps(self.pairs))


    @commands.command()
    async def list(self, ctx):
        result = ""
        for i in self.pairs:
            channel_id = i["id"]
            repo_owner = i["repo_owner"]
            repo_name = i["repo_name"]
            if(channel_id == ctx.channel.id):
                result += f"<https://github.com/{repo_owner}/{repo_name}>\n"
        if len(result) != 0:
            await ctx.send(result)
        else:
            await ctx.send("Keine Repositories vorhanden.")


    @commands.Cog.listener()
    async def on_message(self, message):
        if(message.author.id == bot.user.id): return

        if(message.content.startswith(bot.command_prefix)):
            return
        
        is_issue_channel = False
        for i in self.pairs:
            channel_id = i["id"]
            repo_owner = i["repo_owner"]
            repo_name = i["repo_name"]
            if(channel_id == message.channel.id):  
                is_issue_channel = True
                break
        
        if not is_issue_channel: return
        
        check = False
        checkmark = "\N{White Heavy Check Mark}"
        cross = "\N{CROSS MARK}"
        try:
            new_message = await message.channel.send(f"Issue ``{message.content}`` absenden?")
            await new_message.add_reaction(checkmark)
            await new_message.add_reaction(cross)
            
            reaction, user = await self.bot.wait_for(
                'reaction_add', timeout=60.0, 
                check=lambda _reaction, _user: 
                    _user == message.author and (_reaction.emoji == cross or _reaction.emoji == checkmark) and _reaction.message == new_message
            )
            if reaction.emoji == cross:
                await message.channel.send("Der Vorgang wurde abgebrochen.")
            elif reaction.emoji == checkmark:
                check = True
        except asyncio.TimeoutError:
            pass    
        
        if not check: return
        
        
        for i in self.pairs:
            channel_id = i["id"]
            repo_owner = i["repo_owner"]
            repo_name = i["repo_name"]
            if(channel_id == message.channel.id):
                r = send_issue(repo_owner, repo_name, message.content)
                status = r.status_code
                if status == 201:
                    await message.channel.send(f"Issue https://github.com/{repo_owner}/{repo_name}/issues/{r.json()['number']} wurde erfolgreich erstellt!")
                elif status == 410:
                    await message.channel.send("Issue konnte nicht veröffentlicht werden, da das Repository Issues deaktiviert hat.")
                else:
                    await message.channel.send("Etwas ist schiefgelaufen.")


bot.add_cog(Issues(bot))

bot.run(TOKEN)
