# código original obtido no repositório: https://github.com/iv-org/youtube-trusted-session-generator
import pprint
import traceback
from typing import Optional

import nodriver
from nodriver import start, cdp, loop
import json

class Browser:

    def __init__(self):
        self.browser: Optional[nodriver.Browser] = None
        self.tab: Optional[nodriver.Tab] = None
        self.data = {}

    async def main_session_gen(self, sandbox=True, browser_executable_path=None):
        self.browser = await start(headless=False, sandbox=sandbox, browser_executable_path=browser_executable_path)
        print("[INFO] launching browser.")
        self.tab = self.browser.main_tab
        self.tab.add_handler(cdp.network.RequestWillBeSent, self.send_handler)
        await self.tab.get('https://www.youtube.com/embed/jNQXAC9IVRw')
        await self.tab.wait(cdp.network.RequestWillBeSent)
        button_play = await self.tab.select("#movie_player")
        await button_play.click()
        await self.tab.wait(cdp.network.RequestWillBeSent)
        print("[INFO] waiting additional 30 seconds for slower connections.")
        await self.tab.sleep(30)

    async def send_handler(self, event: cdp.network.RequestWillBeSent):
        if "/youtubei/v1/player" in event.request.url:
            post_data = event.request.post_data
            post_data_json = json.loads(post_data)
            self.data = {
                "visitor_data": post_data_json["context"]["client"]["visitorData"],
                "po_token": post_data_json["serviceIntegrityDimensions"]["poToken"]
            }
            self.browser.stop()
            await self.tab.aclose()
        return

if __name__ == '__main__':

    b = Browser()

    try:
        loop().run_until_complete(b.main_session_gen(sandbox=False))
    except ConnectionRefusedError:
        pass
    except:
        traceback.print_exc()

    pprint.pprint(b.data)
