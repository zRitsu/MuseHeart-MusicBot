from os import getenv
from tornado.web import RequestHandler, Application
from tornado.ioloop import IOLoop


class MainHandler(RequestHandler):

    def get(self):
        self.write(
            f"""
            <html>
                <head>
                </head>
                <body>
                    <table border="1" style="width: 100%; height: 100%;">
                      <tr>
                          <td style="width: 100%; height: 100%;">
                            <iframe width="100%" height="100%"
                                src="{getenv('VIDEO_PREVIEW')}">
                            </iframe><br>
                          </td>
                      </tr>
                    </table><br>
            
                    <table border="1">
                      <tr>
                          <td><b style="font-size: 30px;">Exemplo do suporte a multi-voice:</b></td>
                      </tr>
                      <tr>
                        <td>
                            <video width="100%" height="100%" controls>
                                <source src="https://user-images.githubusercontent.com/74823568/200150891-825f23d7-83e0-44c5-8524-1e8a61a01b5e.mp4" type="video/mp4">
                                Seu navegador não suporta a reprodução deste vídeo.
                            </video>
                        </td>
                      </tr>
                    </table><br>
            
                    <table border="1">
                      <tr>
                          <td><b style="font-size: 30px;">Exemplo com canal de song-request em palco com multiplos bots (função de stage_announce ativado):</b></td>
                      </tr>
                      <tr>
                        <td>
                            <video width="100%" height="100%" controls>
                                <source src="https://user-images.githubusercontent.com/74823568/220428141-9cba4e2f-6864-409d-868d-8d2f7d22a5b6.mp4" type="video/mp4">
                                Seu navegador não suporta a reprodução deste vídeo.
                            </video>
                        </td>
                      </tr>
                    </table><br>
            
                    <table border="1">
                      <tr>
                          <td><b style="font-size: 30px;">Exemplo com canal de song-request em canal de forum com múltiplos bots:</b></td>
                      </tr>
                      <tr>
                        <td>
                            <video width="100%" height="100%" controls>
                                <source src="https://user-images.githubusercontent.com/74823568/198839619-a90cf199-fca2-4432-a379-c99145f3d640.mp4" type="video/mp4">
                                Seu navegador não suporta a reprodução deste vídeo.
                            </video>
                        </td>
                      </tr>
                    </table>
                </body>
            </html>
            """
        )


app = Application([
    (r"/", MainHandler),
])

app.listen(80)
IOLoop.current().start()
