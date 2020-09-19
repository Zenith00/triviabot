from __future__ import annotations

import asyncio as aio
import random
import typing as ty
import concurrent.futures
import threading
import Levenshtein
import discord
import aurcore as aur
import aurflux.cog
import itertools as itt
import aurflux.utils
import gspread
from aurflux import FluxEvent

from aurflux.auth import Record
from aurflux.command import Response
from aurflux.context import GuildMessageContext, GuildTextChannelContext
from aurflux.errors import CommandError
import dataclasses as dtcs
import TOKENS
import random as rnd

EMOJI = {
   "A": "🇦",
   "B": "🇧",
   "C": "🇨",
   "D": "🇩",
}
EMOJI_INVERSE = {v: k for k, v in EMOJI.items()}

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

GC = gspread.service_account(filename=TOKENS.SA_KEYPATH, scopes=["https://www.googleapis.com/auth/spreadsheets"])

# @dtcs.dataclass
# class PointTypes:
#    trivia: ty.Dict[str, int] = {"per": 5, "max": 50, "col": "C"}
#    easter: ty.Dict[str, int] = {"per": 50, "max": 50, "col": "D"}
#    workshop: ty.Dict[str, int] = {"per": 10, "max": 50, "col": "E"}
#    karaoke: ty.Dict[str, int] = {"per": 25, "max": 50, "col": "F"}
#

POINT_TYPES = {
   "trivia"  : {"per": 5, "max": 50, "col": "C"},
   "easter"  : {"per": 50, "max": 50, "col": "D"},
   "workshop": {"per": 25, "max": 50, "col": "E"},
   "karaoke" : {"per": 25, "max": 50, "col": "F"},
   "manual"  : {"per": 0, "max": None, "col": "G"},
}


class Question:
   @staticmethod
   def parse_row(row: ty.List[str]):
      return {
         "question": row[0],
         "answer"  : row[1],
         "choices" : row[2:]
      }

   def __init__(self, question: str, answer: str, choices: ty.List[str], index: int):
      self.index = index
      self.question = question
      self.answer = answer
      self.choices = [choice for choice in choices if choice]

      self.type_ = "mc" if len(self.choices) > 1 else "fr"
      if self.type_ == "mc":
         if self.answer not in self.choices:
            print("ERROR!")
            print(self.index)
            print(self.question)
            print("--")
      if self.type_ == "fr":
         print("ERROR!")
         print(self.index)
         print(self.question)
         print("--")
   @property
   def correct_letter(self) -> str:
      return chr(ord("A") + self.choices.index(self.answer))

   #
   # def is_correct(self, guess: str):
   #    print(f"Checking answer {guess} against {self.answer}")
   #    if self.type_ == "mc":
   #       guess_index = ord(guess[0].lower()) - 97
   #       return (0 <= guess_index < len(self.choices)
   #               and self.choices[guess_index] == self.answer)
   #
   #    elif self.type_ == "fr":
   #       return Levenshtein.ratio(guess.lower(), self.answer) > .85

   def __str__(self):
      if self.type_ == "mc":
         return "\n".join((
            self.question,
            "",
            *[f'{chr(i + 97)}) {option}' for i, option in enumerate(self.choices)]
         ))
      elif self.type_ == "fr":
         return self.question


class PointRec:
   def __init__(self):
      self.sheet = GC.open_by_key(TOKENS.POINTS_SPREADSHEET).get_worksheet(0)
      self.lock = threading.Lock()

   def add_points_bulk(self, members: ty.List[discord.Member], point_type: str, point_overrides: ty.List[int] = None):
      print("Starting adding points")
      with self.lock:
         print("Lock entered!")
         member_ids = self.sheet.col_values(2, value_render_option="UNFORMATTED_VALUE")[1:]
         member_points = self.sheet.col_values(ord(POINT_TYPES[point_type]['col']) - ord("A") + 1, value_render_option="UNFORMATTED_VALUE")[1:]

         batch_dicts = []
         for member, manual_inc in itt.zip_longest(members, point_overrides or [], fillvalue=None):
            print(f"trying member {member.id} in {member_ids}")
            start_points = 0
            try:
               member_index = member_ids.index(str(member.id))
               start_points = int(member_points[member_index]) if len(member_points) > member_index else 0
            except ValueError as e:
               member_index = len(member_ids) + len(batch_dicts)
               batch_dicts.append({"range": f"A{member_index + 2}:B{member_index + 2}", "values": [[member.name, str(member.id)]]})

            new_points = (start_points + manual_inc) if manual_inc else min(start_points + POINT_TYPES[point_type]["per"], POINT_TYPES[point_type]["max"])
            print("Done ")
            print(batch_dicts)
            batch_dicts.append({"range": f"{POINT_TYPES[point_type]['col']}{member_index + 2}", "values": [[new_points]]})
         print("BATCH DICTS")
         print(batch_dicts)
         self.sheet.batch_update(batch_dicts, value_input_option="RAW")

   def add_points(self, member: discord.Member, point_type: str, point_override: int):
      print("ADDING POINTS!")
      self.add_points_bulk([member], point_type, [point_override])

   def gen_leaderboard(self, n: int) -> ty.Tuple[ty.List[int], ty.List[int]]:
      member_ids = self.sheet.col_values(2, value_render_option="UNFORMATTED_VALUE")[1:]
      member_points = self.sheet.col_values(8, value_render_option="UNFORMATTED_VALUE")[1:]

      return zip(*sorted(zip(member_ids, member_points), key=lambda x: x[1], reverse=True)[:n])


class Trivia(aurflux.cog.FluxCog):

   @property
   def default_auths(self) -> ty.List[Record]:
      return [Record(rule="ALLOW", target_id=discord.Permissions(manage_guild=True).value, target_type="PERMISSION")]

   def load_questions(self):
      sheet = GC.open_by_key(TOKENS.QUESTIONS_SPREADSHEET).get_worksheet(0)
      questions = [Question(**Question.parse_row(question), index=index) for index, question in enumerate(sheet.get_all_values()[1:], start=1)]
      random.shuffle(questions)
      return questions

   def __init__(self, *args, **kwargs):
      super().__init__(*args, **kwargs)
      self.questions: ty.List[Question] = self.load_questions()
      self.points = PointRec()
      self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)

   def load(self):

      @self.router.listen_for(":question")
      @aur.Eventful.decompose
      async def _(ctx: GuildTextChannelContext, *args, **kwargs):
         try:
            cfg = self.flux.CONFIG.of(ctx)
            print(ctx.config_identifier)
            question = self.questions.pop()

            message = await ctx.channel.send(content=str(question))
            for emoji in EMOJI.values():
               await aio.gather(message.add_reaction(emoji))

            await aio.sleep(cfg["wait_for_s"])
            await ctx.channel.send(f"Finished! The answer was `{question.answer}`")
            message = await ctx.channel.fetch_message(message.id)

            corrects = set()
            incorrects = set()

            for reaction in message.reactions:
               print(EMOJI_INVERSE)
               if reaction.emoji == EMOJI[question.correct_letter]:
                  async for user in reaction.users():
                     corrects.add(user)
               else:
                  async for user in reaction.users():
                     incorrects.add(user)
            self.executor.submit(self.points.add_points_bulk, list(corrects - incorrects), "trivia").add_done_callback(lambda f: f.result())

         except IndexError:
            await self.flux.get_channel(285094955993530368).send(f"Out of questions. {self.flux.CONFIG.of(ctx)['prefix']}refresh to reload.")
            return

      @self._commandeer(name="ask", parsed=False)
      async def _(ctx: GuildMessageContext, *_):
         """
         ask
         ==
         Asks a random question
         ==
         ==
         :param ctx:
         :param _:
         :return:
         """
         print(self.router)
         await self.router.submit(FluxEvent(self.flux, ":question", ctx=GuildTextChannelContext(flux=self.flux, channel=ctx.channel)))

         return Response(reaction=None)
         # try:
         #    question = self.questions.pop()
         # except IndexError:
         #    yield aurflux.command.Response("Out of questions!")
         #    return
         # yield Response(content=str(question), reaction=[])
         # lock = aio.Lock()

         # async def is_winner(ev: FluxEvent) -> bool:
         #    print("checking ")
         #    print(ev)
         #    async with lock:
         #       res = question.is_correct(ev.args[0].content)
         #       print(res)
         #       return res

         # winner: discord.Message = (await self.router.wait_for("flux:message", check=is_winner)).args[0]
         # yield Response(content=f"{winner.author.mention} got it correct! {question.answer}")
         # self.sheet.update_cell(question.index + 1, 2, f"{winner.author} {winner.author.mention}")

      @self._commandeer(name="refresh", parsed=False)
      async def _(ctx: GuildMessageContext, *_):
         """
         refresh
         ==
         Pulls questions & resets asked questions
         ==

         ==
         :param ctx:
         :param _:
         :return:
         """
         self.load_questions()
         return Response(content=f"Downloaded {len(self.questions)} questions")

      @self._commandeer(name="leaderboard", parsed=False)
      async def _(ctx: GuildMessageContext, args):
         """
         leaderboard (#num)
         ==
         Gets the leaderboard of top `#num` users
         ==
         (#num): Number of users to get. Defaults to 10
         ==
         :param ctx:
         :param args:
         :return:
         """
         try:
            num = int(args.strip())
         except ValueError as e:
            raise CommandError(str(e))
         except AttributeError:  # args is None
            num = 10

         embed = discord.Embed(title="🎖Leaderboard🎖")
         m_ids, points = self.points.gen_leaderboard(num)
         embed.add_field(name="Member", value="\n".join([str(ctx.guild.get_member(int(m_id))) for m_id in m_ids]), inline=True)
         embed.add_field(name="Points", value="\n".join([str(p) for p in points]), inline=True)

         return Response(embed=embed)

      @self._commandeer(name="addpoints", parsed=False)
      async def _(ctx: GuildMessageContext, args):
         """
         addpoints [type] <member>
         addpoints [manual/m] <member> (#pts)
         ==
         Adds points to `<member>`'s score
         ==
         #points: the number of points to add;
         [type]: [easter/trivia/workshop/karaoke/e/t/w/k]
         The category of points to add;
         [manual/m]: [manual/m];
         <member>: the member to add points to;
         (#pts): number of points to add if `[type]` is manual/m
         ==
         :param ctx:
         :param target:
         :return:
         """
         type_, target_r, manual, *_ = [*args.split(" "), None]
         if manual:
            try:
               manual = int(manual)
            except ValueError:
               raise CommandError(f"`{manual}` not recognized as an integer number")

         try:
            matched_type = [point_type for point_type in POINT_TYPES if point_type.startswith(type_)][0]
         except IndexError:
            raise CommandError(f"`{type_}` not recognized as a valid point type. See help")
         if manual and matched_type != "manual":
            yield Response(f"Ignoring points: `{manual}` because of defined point values for {matched_type}")
         try:
            target_member_id = aurflux.utils.find_mentions(target_r)[0]
         except IndexError:
            raise CommandError(f"Could not find member in {target_r}")

         target_member = ctx.guild.get_member(target_member_id)
         if not target_member:
            raise CommandError(f"Could not find member in server: <@{target_member_id}>")
         with open("points.log", "a") as f:
            f.write(f"{target_member_id}, {matched_type}, {manual}")
         self.executor.submit(self.points.add_points, target_member, matched_type, manual).add_done_callback(lambda f: f.result())
         yield Response(f"Added {POINT_TYPES[matched_type]['per'] or manual} points to {target_member.mention} for {matched_type}")

      # @self.router.listen_for(":autoask")
      # async def autoask(ev: FluxEvent):
      #    pass

      @self._commandeer(name="autoask", parsed=False)
      async def _(ctx: GuildMessageContext, args):
         """
         autoask
         ==
         Toggles autoasking
         ==

         ==
         :param ctx:
         :param args:
         :return:
         """

         async def auto_loop():
            print("Entering autoask loop")
            while ctx.config["autoask"]:
               print("Autoask still enabled! Running...")
               await aio.sleep(ctx.config["autoask_every_m"] * 60)
               print("Sleep done!")
               if not ctx.config["autoask"]:
                  break
               autoask_dests = ctx.config["autoask_channels"]
               if not autoask_dests:
                  continue
               dest = ctx.flux.get_channel(rnd.choice(autoask_dests))
               await ctx.channel.send(f"Automatically asking a question in {dest.mention}\nCall autoask or triviaconf to disable")
               await self.router.submit(FluxEvent(self.flux, ":question", ctx=GuildTextChannelContext(flux=self.flux, channel=dest)))

         print("==")
         print(ctx.config["autoask"])
         async with ctx.flux.CONFIG.writeable_conf(ctx) as cfg_w:
            cfg_w["autoask"] = not ctx.config["autoask"]
         yield Response(f"{('Disabling', 'Enabling')[int(ctx.config['autoask'])]} autoask")

         print(bool(ctx.config["autoask"]))
         if ctx.config["autoask"]:
            print("Creating!")
            aio.create_task(auto_loop())

      @self._commandeer(name="triviaconf", parsed=False)
      async def _(ctx: GuildMessageContext, args):
         """
         triviaconf [setting] (*values)
         ==
         Sets [setting] to (*values)
         ==
         [setting]: [autoask/autoask_every_m/autoask_channels/wait_for_s];
         (*values): If not provided, displays current setting.
         `autoask [true/false]` enables/disables auto asking questions
         `autoask_every_m 20` = post a question every 20 minutes
         `autoask_channels <channel> <channel2> *` ask in one of these random channels
         `wait_for_s 15` wait 15 seconds for reactions to a trivia question
         ==
         :param ctx:
         :param target:
         :return:
         """
         triviaconfs = ["autoask", "autoask_every_m", "autoask_channels", "wait_for_s"]
         if not args:
            yield Response("```" + "\n".join([f'{k} : {ctx.config[k]}' for k in triviaconfs]) + "\n```")
            return
         setting, values, *_ = [*args.split(" ", 1), None]

         if setting not in triviaconfs:
            yield Response("Setting must be `[autoask_every_m/autoask_channels/wait_for_s]`!", errored=True)
            return
         values = values.strip()
         if setting == "autoask_every_m":
            if not values:
               yield Response("Disabling autoask, minute setting is unchanged")
               setting = "autoask"
               val = False
            else:
               val = int(values.strip())
               yield Response(f"Automatically asking a question every {val} minutes")
         elif setting == "autoask_channels":
            val = aurflux.utils.find_mentions(values)
            yield Response(f"Setting autoask to channels:\n {' '.join([f'<#{id_}>' for id_ in val])}")
         elif setting == "wait_for_s":
            val = int(values)
            yield Response(f"Waiting for {val} seconds after asking a question for responses")
         elif setting == "autoask":
            val = bool(values.lower())

         async with self.flux.CONFIG.writeable_conf(ctx) as cfg_w:
            cfg_w[setting] = val
