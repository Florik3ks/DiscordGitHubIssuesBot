from collections import defaultdict
from datetime import datetime, timedelta
import os
import json
import asyncio
from datetime import timezone
from typing import Any, Dict
import requests
from dotenv import load_dotenv
import discord
from discord.ext import commands
from sqlalchemy import desc, true

load_dotenv()
TOKEN = os.environ.get("TOKEN")
GH_TOKEN = os.environ.get("GH_TOKEN", "")

bot = commands.Bot(command_prefix="+")


class GitHubIssue(object):
    def __init__(self, **kwargs) -> None:
        self.title = kwargs.get("title", "")
        self.attachments = kwargs.get("attachments", [])
        self.body = kwargs.get("body", None)
        self.expire = datetime.now(timezone.utc) + timedelta(minutes=5)
        self.pairs = load_json()
        
    async def send(self, message: discord.Message):
        for i in self.pairs:
            channel_id = i["id"]
            if channel_id == message.channel.id:
                repo_owner = i["repo_owner"]
                repo_name = i["repo_name"]
                
                r = send_issue(repo_owner, repo_name, self.title, self.render_body())
                
                status = r.status_code
                if status == 201:
                    await message.channel.send(f"Issue https://github.com/{repo_owner}/{repo_name}/issues/{r.json()['number']} wurde erfolgreich erstellt!")
                elif status == 410:
                    await message.channel.send("Issue konnte nicht veröffentlicht werden, da das Repository Issues deaktiviert hat.")
                else:
                    await message.channel.send("Etwas ist schiefgelaufen.")
                    
                    
    def render_body(self):
        b = self.body or ""
        if self.attachments:
            b += "\n\n### Bilder:  \n"
            for a in self.attachments:
                b += f"![Bild]({a.url})\n"
        return b
        
        


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
    r = requests.post(url, data=payload, headers=headers)
    
    if r.status_code != 201:
        print(f'Could not create Issue "{title}". Errorcode: {r.status_code}')
        print('Response:', r.content)
    return r


async def send_issue(issue: GitHubIssue, channel: discord.TextChannel):
    for pair in load_json():
        if pair["id"] == channel.id:
            repo_owner = pair["repo_owner"]
            repo_name = pair["repo_name"]
            break
    else:
        await channel.send(embed=basic_embed(title="Error", description="Invalid channel id"))
        return
    r = make_github_issue(repo_owner, repo_name, issue.title, issue.render_body())
    status = r.status_code
    if status == 201:
        await channel.send(embed=basic_embed(
            title="Issue `%s`" % issue.title, 
            description=f"Issue wurde erfolgreich unter https://github.com/{repo_owner}/{repo_name}/issues/{r.json()['number']} erstellt!"
        ))
        return True
    elif status == 410:
        await channel.send(embed=basic_embed(
            title="Error", 
            description="Issue konnte nicht veröffentlicht werden, da das Repository Issues deaktiviert hat."
        ))
    else:
        await channel.send(embed=basic_embed(
            title="Error",
            description="Etwas ist schiefgelaufen."
        ))
    return False
    

def basic_embed(*,
    title: str,
    description: str = "",
) -> discord.Embed:
    return discord.Embed(title=title, description=description)
    


@bot.event
async def on_ready():
    print("bot started")
    print("------------------------------")


class Issues(commands.Cog):
    
    current_issues: Dict[int, GitHubIssue] = {}
    
    
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
            if data not in self.pairs:
                self.pairs.append(data)

            with open("config.json", "w") as file:
                file.write(json.dumps(self.pairs))

            await ctx.send(f'Repository <https://github.com/{data["repo_owner"]}/{data["repo_name"]}> erfolgreich hinzugefügt.')

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
            await ctx.send(f'Repository <https://github.com/{data["repo_owner"]}/{data["repo_name"]}> wurde entfernt.')
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
    async def on_message(self, message: discord.Message):
        # sourcery skip: low-code-quality
        if message.author.id == bot.user.id or message.content.startswith(bot.command_prefix):
            return
        
        for pair in self.pairs:
            channel_id = pair["id"]
            if channel_id == message.channel.id:
                break
        else:
            return
        
        checkmark = "\N{White Heavy Check Mark}"
        cross = "\N{CROSS MARK}"
        memo = "\N{MEMO}"
        
        if Issues.current_issues.get(message.author.id) is None:
            issue = Issues.current_issues.setdefault(message.author.id, GitHubIssue())
            issue.title = message.content
            
            if not issue.title and message.attachments:
                issue.title = "Siehe Bilder:"
            
            try:
                desc = "Issue `%s` absenden?" % issue.title
                desc += f"\n{memo} um einen Kommenar hinzuzufügen\n{cross} um den Vorgang abzubrechen\n{checkmark} um zu betstätigen und den Issue abzusenden"
                issue_message: discord.Message = await message.channel.send(embed=basic_embed(
                    title="Issue absenden?",
                    description=desc
                ))
                await issue_message.add_reaction(memo)
                await issue_message.add_reaction(cross)
                await issue_message.add_reaction(checkmark)
                
                reaction, user = await self.bot.wait_for(
                    "reaction_add", timeout=60.0, 
                    check=lambda _reaction, _user: 
                        _user == message.author and _reaction.emoji in (checkmark, cross, memo) and _reaction.message == issue_message
                )
                if reaction.emoji == cross:
                    Issues.current_issues.pop(message.author.id, None)
                    await message.channel.send(embed=basic_embed(title="User cancel", description="Vorgang wurde aufgrund von User abgebrochen"))
                
                elif reaction.emoji == checkmark:
                    issue.attachments.extend(message.attachments.copy())
                    r = await send_issue(issue, message.channel)
                    if r:
                        Issues.current_issues.pop(message.author.id, None)
                        
                    
                elif reaction.emoji == memo:
                    await message.channel.send(embed=basic_embed(title="Nachricht eingeben", description="In den nächsten 10min wird eine Nachrich erwartet, welche als Kommentar an den Issue gehangen wird"))
            
            except asyncio.TimeoutError:
                Issues.current_issues.pop(message.author.id, None)
                return
        else:
            issue = Issues.current_issues.get(message.author.id)
            if issue is None:
                await message.channel.send(embed=basic_embed(title="Error", description="Etwas ist schief gelaufen, probieren sie es noch einmal"))
                return

            issue.body = message.content
            issue.attachments.extend(message.attachments.copy())
            
            try:
                issue_message = await message.channel.send(embed=basic_embed(
                    title="Folgenden Issue hochladen",
                    description="Titel: `%s`\nNachricht:\n```md\n%s```" % (issue.title, issue.render_body())
                ))
                await issue_message.add_reaction(cross)
                await issue_message.add_reaction(checkmark)
                
                reaction, user = await self.bot.wait_for(
                    "reaction_add", timeout=60.0, 
                    check=lambda _reaction, _user: 
                        _user == message.author and _reaction.emoji in (checkmark, cross, memo) and _reaction.message == issue_message
                )
                if reaction.emoji == cross:
                    Issues.current_issues.pop(message.author.id, None)
                    await message.channel.send(embed=basic_embed(title="User cancel", description="Vorgang wurde aufgrund von User abgebrochen"))
                
                elif reaction.emoji == checkmark:
                    issue.attachments.extend(message.attachments)
                    r = await send_issue(issue, message.channel)
                    if r:                
                       Issues.current_issues.pop(message.author.id, None)
            
            except asyncio.TimeoutError:
                Issues.current_issues.pop(message.author.id, None)
                return
            
        for user_id, issue in Issues.current_issues.items():
            if issue.expire < datetime.now(timezone.utc):
                Issues.current_issues.pop(user_id)
                print("Removed expired issue from %i" % user_id)
            


bot.add_cog(Issues(bot))

bot.run(TOKEN)
