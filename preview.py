from os import getenv
from tornado.web import RequestHandler, Application
from tornado.ioloop import IOLoop


class MainHandler(RequestHandler):

    def get(self):
        self.write(
            f"""<html>
              <head>
              </head>
              <body>
                <iframe width="100%" height="100%"
                src="{getenv('VIDEO_PREVIEW')}">
                </iframe>
              </body>
            </html>"""
        )


app = Application([
    (r"/", MainHandler),
])

app.listen(80)
IOLoop.current().start()
