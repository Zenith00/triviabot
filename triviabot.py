from __future__ import annotations

import typing as ty
import aurflux
import aurcore as aur
import TOKENS


import trivia

class Triviabot:
    def __init__(self):
        self.event_router = aur.EventRouterHost(name="triviabot")
        self.flux_client = aurflux.FluxClient("triviabot", admin_id=TOKENS.ADMIN_ID, parent_router=self.event_router, builtins=True)

        # self.aurflux.router.endpoint(":ready")(lambda ev: print("Ready!"))

    async def startup(self, token: str):
        await self.flux_client.startup(token)

    async def shutdown(self):
        await self.flux_client.shutdown()



triviabot = Triviabot()

triviabot.flux_client.register_cog(trivia.Trivia)
print(triviabot.event_router)

aur.aiorun(triviabot.startup(token=TOKENS.TRIVIABOT), triviabot.shutdown())
