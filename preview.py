from os import getenv
from tornado.web import RequestHandler, Application
from tornado.ioloop import IOLoop


class MainHandler(RequestHandler):

    def get(self):
        self.render('./templates/preview.html', video_preview=getenv("VIDEO_PREVIEW"))


app = Application([
    (r"/", MainHandler),
])

app.listen(80)
IOLoop.current().start()
