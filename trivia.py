from __future__ import annotations

import asyncio as aio
import random
import typing as ty

import Levenshtein
import gspread
from aurflux import Aurflux, AurfluxCog, AurfluxEvent, MessageContext
from aurflux.response import Response

import TOKENS

if ty.TYPE_CHECKING:
    import discord

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']


def load_gspread_sheet():
    gc = gspread.service_account(filename=TOKENS.SA_KEYPATH, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    sheet = gc.open_by_key(TOKENS.SPREADSHEET_ID).get_worksheet(0)
    return sheet


class Question:
    @staticmethod
    def parse_row(row: ty.List[str]):
        return {
            "question": row[0],
            "winner"  : row[1],
            "answer"  : row[2],
            "choices" : row[3:]
        }

    def __init__(self, question: str, winner: str, answer: str, choices: ty.List[str], index: int):
        self.index = index
        self.question = question
        self.winner = winner
        self.answer = answer
        self.choices = choices

        self.type_ = "mc" if any(choices) else "fr"

    def is_correct(self, guess: str):
        if self.type_ == "mc":
            guess_index = ord(guess[0].lower()) - 97
            return (0 <= guess_index < len(self.choices)
                    and self.choices[guess_index] == self.answer)

        elif self.type_ == "fr":
            return Levenshtein.ratio(guess.lower(), self.answer) > .85

    def __str__(self):
        if self.type_ == "mc":
            return "\n".join((
                self.question,
                "",
                *[f'{chr(i + 97)}) {option}' for i, option in enumerate(self.choices)]
            ))
        elif self.type_ == "fr":
            return self.question


class Interface(AurfluxCog):

    def load_questions(self):
        self.sheet = load_gspread_sheet()
        self.questions = [Question(**Question.parse_row(question), index=index) for index, question in enumerate(self.sheet.get_all_values()[1:], start=1)]
        random.shuffle(self.questions)

    def __init__(self, aurflux: Aurflux):
        super().__init__(aurflux)
        self.sheet = None
        self.questions = None
        self.load_questions()

    def route(self):
        @self.register
        @self.aurflux.commandeer(name="ask", parsed=False)
        async def _(ctx: MessageContext, *_):
            """
            Asks a random question
            :param ctx:
            :param _:
            :return:
            """
            try:
                question = self.questions.pop()
            except IndexError:
                yield Response("Out of questions!")
                return
            yield Response(content=str(question), reaction=None)
            lock = aio.Lock()

            async def is_winner(ev: AurfluxEvent) -> bool:
                async with lock:
                    return question.is_correct(ev.args[0].content)

            winner: discord.Message = (await self.aurflux.router.wait_for(":message", check=is_winner)).args[0]
            yield Response(content=f"{winner.author.mention} got it correct! {question.answer}")
            self.sheet.update_cell(question.index + 1, 2, f"{winner.author} {winner.author.mention}")

        @self.register
        @self.aurflux.commandeer(name="refresh", parsed=False)
        async def _(ctx: MessageContext, *_):
            """
            Pulls questions & resets asked questions
            :param ctx:
            :param _:
            :return:
            """
            self.load_questions()
            return Response(content=f"Downloaded {len(self.questions)} questions")
