from __future__ import annotations

import typing as ty
import aurflux
import aurcore
import TOKENS


import trivia

class Triviabot:
    def __init__(self):
        self.event_router = aurcore.event.EventRouter(name="triviabot")
        self.aurflux = aurflux.Aurflux("triviabot", admin_id=TOKENS.ADMIN_ID, parent_router=self.event_router, builtins=False)

        self.aurflux.router.endpoint(":ready")(lambda ev: print("Ready!"))

    async def startup(self, token: str):
        await self.aurflux.start(token)

    async def shutdown(self):
        await self.aurflux.logout()



triviabot = Triviabot()

triviabot.aurflux.register_cog(trivia.Interface)

aurcore.aiorun(triviabot.startup(token=TOKENS.TRIVIABOT), triviabot.shutdown())
